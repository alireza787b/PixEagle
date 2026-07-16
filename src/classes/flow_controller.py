# src/classes/flow_controller.py
import asyncio
import logging
import platform
import threading
import signal
import time
import cv2
from classes.app_controller import AppController
from classes.parameters import Parameters

logger = logging.getLogger(__name__)


class FlowController:
    LOOP_TASK_STOP_TIMEOUT_S = 2.0

    def __init__(self):
        """
        Initializes the FlowController, including the AppController and FastAPI server.
        """
        logging.debug("Initializing FlowController...")

        # Initialize AppController
        self.controller = AppController()
        self.controller.shutdown_flag = False
        self._shutdown_initiated = False
        self._api_server_error = None

        # Flight-affecting async work has a stable owner independent of Uvicorn.
        self.flight_loop, self.flight_thread = self.start_flight_event_loop()
        self.controller.bind_flight_event_loop(self.flight_loop)

        # Initialize FastAPI server
        try:
            self.server, self.server_thread = self.start_fastapi_server()
        except Exception:
            self.stop_flight_event_loop()
            raise

        # Setup signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)

        # Windows high-resolution timer (improves time.sleep from ~15ms to ~1ms precision)
        self._windows_timer_set = False
        if platform.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.winmm.timeBeginPeriod(1)
                self._windows_timer_set = True
                logger.debug("Windows high-resolution timer enabled (1ms precision)")
            except Exception:
                logger.debug("Windows high-resolution timer not available")

        # Pipeline timing mode
        self._pipeline_mode = str(
            getattr(Parameters, "PIPELINE_MODE", "REALTIME")
        ).strip().upper()
        if self._pipeline_mode not in ("REALTIME", "MAX_THROUGHPUT", "DETERMINISTIC_REPLAY"):
            logger.warning(
                "Unknown PIPELINE_MODE '%s', defaulting to REALTIME",
                self._pipeline_mode
            )
            self._pipeline_mode = "REALTIME"

        logger.info("Pipeline mode: %s", self._pipeline_mode)

        # For DETERMINISTIC_REPLAY: track last frame PTS for timestamp-based pacing
        self._last_frame_pts_ms = None
        self._last_video_playback_epoch = None

        # Frame counter for periodic logging
        self._flow_frame_count = 0

    def start_flight_event_loop(self):
        """Start the stable event-loop owner for PX4 and commander lifecycle."""
        flight_loop = asyncio.new_event_loop()
        started = threading.Event()

        def run_flight_loop():
            asyncio.set_event_loop(flight_loop)
            started.set()
            try:
                flight_loop.run_forever()
            finally:
                self._cancel_and_drain_loop_tasks(
                    flight_loop,
                    label="flight event loop",
                )
                flight_loop.close()

        flight_thread = threading.Thread(
            target=run_flight_loop,
            name="PixEagleFlightLoop",
        )
        flight_thread.start()
        if not started.wait(timeout=5.0) or not flight_loop.is_running():
            flight_loop.call_soon_threadsafe(flight_loop.stop)
            flight_thread.join(timeout=5.0)
            raise RuntimeError("PixEagle flight event loop failed to start")
        return flight_loop, flight_thread

    @classmethod
    def _cancel_and_drain_loop_tasks(
        cls,
        loop: asyncio.AbstractEventLoop,
        *,
        label: str,
        timeout_s: float | None = None,
    ) -> dict:
        """Cancel loop-owned tasks with a deadline and explicit diagnostics."""
        tasks = {task for task in asyncio.all_tasks(loop) if not task.done()}
        if not tasks:
            return {"clean": True, "cancelled": 0, "unresolved": []}

        for task in tasks:
            task.cancel()

        deadline_s = cls.LOOP_TASK_STOP_TIMEOUT_S if timeout_s is None else max(
            0.0,
            float(timeout_s),
        )

        async def wait_for_tasks():
            return await asyncio.wait(tasks, timeout=deadline_s)

        done, pending = loop.run_until_complete(wait_for_tasks())
        for task in done:
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("%s task stopped with error: %s", label, exc)

        unresolved = sorted(
            task.get_name() or repr(task.get_coro())
            for task in pending
        )
        if unresolved:
            logger.critical(
                "%s shutdown deadline expired after %.2f s; unresolved tasks: %s",
                label,
                deadline_s,
                ", ".join(unresolved),
            )
        return {
            "clean": not unresolved,
            "cancelled": len(tasks),
            "unresolved": unresolved,
        }

    def stop_flight_event_loop(self) -> None:
        """Stop the flight owner only after application cleanup has completed."""
        flight_loop = getattr(self, "flight_loop", None)
        flight_thread = getattr(self, "flight_thread", None)
        if flight_loop is not None and not flight_loop.is_closed() and flight_loop.is_running():
            flight_loop.call_soon_threadsafe(flight_loop.stop)
        if flight_thread is not None and flight_thread is not threading.current_thread():
            flight_thread.join(timeout=5.0)
            if flight_thread.is_alive():
                logging.error("Flight event-loop thread did not stop within timeout")

    def _fail_closed_after_api_server_exit(self, reason: str) -> None:
        """Stop flight-affecting work if the operator/API control surface exits."""
        self.controller.shutdown_flag = True
        self._api_server_error = reason
        flight_loop = getattr(self, "flight_loop", None)
        if flight_loop is None or flight_loop.is_closed() or not flight_loop.is_running():
            logging.critical(
                "API server exited and flight cleanup could not be scheduled: %s",
                reason,
            )
            return

        try:
            cleanup = asyncio.run_coroutine_threadsafe(
                self.controller.shutdown(),
                flight_loop,
            )
            cleanup.result(timeout=10.0)
        except Exception as exc:
            logging.critical(
                "API server exited and bounded flight cleanup failed (%s): %s",
                reason,
                exc,
            )

    def start_fastapi_server(self):
        """
        Initializes and starts the FastAPI server in a separate thread.
        """
        logging.debug("Initializing FastAPI server...")
        fastapi_handler = self.controller.api_handler
        server_loop = asyncio.new_event_loop()
        self.server_loop = server_loop

        # Start the FastAPI server using the async start method
        def run_server():
            loop = server_loop
            asyncio.set_event_loop(loop)

            # Suppress Windows ProactorEventLoop ConnectionResetError noise.
            # On Windows, the Proactor transport fires _call_connection_lost
            # when clients disconnect (browser tab close, WebSocket drop).
            # The socket is already dead — the cleanup error is harmless.
            if platform.system() == "Windows":
                _default_handler = loop.get_exception_handler()

                def _windows_exception_handler(loop, context):
                    exception = context.get("exception")
                    if isinstance(exception, ConnectionResetError):
                        logger.debug(
                            "Suppressed Windows Proactor connection cleanup: %s",
                            context.get("message", ""),
                        )
                        return
                    # Delegate everything else to the default handler
                    if _default_handler is not None:
                        _default_handler(loop, context)
                    else:
                        loop.default_exception_handler(context)

                loop.set_exception_handler(_windows_exception_handler)

            exit_reason = "FastAPI server stopped"
            try:
                loop.run_until_complete(fastapi_handler.start(
                    host=Parameters.HTTP_STREAM_HOST,
                    port=Parameters.HTTP_STREAM_PORT
                ))
            except Exception as exc:
                exit_reason = f"FastAPI server failed: {type(exc).__name__}: {exc}"
                logging.exception(exit_reason)
            finally:
                self._fail_closed_after_api_server_exit(exit_reason)
                self._cancel_and_drain_loop_tasks(
                    loop,
                    label="FastAPI event loop",
                )
                loop.close()

        server_thread = threading.Thread(target=run_server, name="PixEagleFastAPI")
        server_thread.start()
        logging.debug("FastAPI server started on a separate thread.")
        return None, server_thread  # Return None for server since we're using the handler's start method

    def _compute_frame_delay(self, processing_elapsed_ms: float) -> int:
        """
        Compute the correct frame delay based on pipeline mode.

        Args:
            processing_elapsed_ms: Time spent processing the current frame (ms).

        Returns:
            Delay in milliseconds. 0 means no delay (MAX_THROUGHPUT).
        """
        target_delay_ms = self.controller.video_handler.delay_frame

        if self._pipeline_mode == "MAX_THROUGHPUT":
            # No artificial delay — process as fast as hardware allows
            return 0

        if self._pipeline_mode == "DETERMINISTIC_REPLAY":
            # Pace based on source video timestamps (PTS)
            cap = self.controller.video_handler.cap
            if cap is not None:
                current_pts_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                if self._last_frame_pts_ms is not None and current_pts_ms > 0:
                    pts_delta_ms = current_pts_ms - self._last_frame_pts_ms
                    if pts_delta_ms > 0:
                        # Subtract processing time from PTS-based delay
                        remaining = pts_delta_ms - processing_elapsed_ms
                        self._last_frame_pts_ms = current_pts_ms
                        return max(1, int(remaining))
                self._last_frame_pts_ms = current_pts_ms
            # Fallback: use target FPS pacing if PTS unavailable
            return max(1, int(target_delay_ms - processing_elapsed_ms))

        # REALTIME mode (default): subtract processing time from target interval
        remaining = target_delay_ms - processing_elapsed_ms
        return max(1, int(remaining))

    def _observe_video_playback_epoch(self, frame_status) -> None:
        """Reset deterministic PTS pacing when a video file starts a new epoch."""
        if not isinstance(frame_status, dict):
            return
        epoch = frame_status.get("video_file_playback_epoch")
        if isinstance(epoch, bool) or not isinstance(epoch, int):
            return

        previous = getattr(self, "_last_video_playback_epoch", None)
        self._last_video_playback_epoch = epoch
        if previous is not None and epoch != previous:
            self._last_frame_pts_ms = None

    def main_loop(self):
        """
        Main loop to handle video processing, user inputs, and the main application flow.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:

            while not self.controller.shutdown_flag:
                t_loop_start = time.monotonic()

                frame = self.controller.video_handler.get_frame()
                frame_status = {}
                if hasattr(self.controller.video_handler, "get_frame_status"):
                    frame_status = self.controller.video_handler.get_frame_status()
                self._observe_video_playback_epoch(frame_status)
                if frame is None:
                    logging.warning("FlowController: No frame from video_handler - continuing in degraded mode")
                    loop.run_until_complete(
                        self.controller.handle_video_frame_unavailable(frame_status)
                    )
                    delay_seconds = self.controller.video_handler.delay_frame / 1000.0
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)
                    continue

                # Periodic logging
                self._flow_frame_count += 1
                if self._flow_frame_count % 200 == 0:
                    logging.info(f"FLOW_CONTROLLER RUNNING: Processing frame #{self._flow_frame_count}")

                # Process frame
                t_process_start = time.monotonic()
                frame = loop.run_until_complete(self.controller.update_loop(frame))
                self.controller.show_current_frame()
                processing_ms = (time.monotonic() - t_process_start) * 1000.0

                # Compute correct delay accounting for processing time
                wait_ms = self._compute_frame_delay(processing_ms)

                # Handle frame timing and keyboard input
                if Parameters.SHOW_VIDEO_WINDOW:
                    # GUI mode: cv2.waitKey for timing + keyboard capture
                    # Minimum 1ms to allow OpenCV event processing
                    key = cv2.waitKey(max(1, wait_ms)) & 0xFF
                    if key == ord('q'):
                        logging.info("Quit requested via 'q' key...")
                        self.controller.shutdown_flag = True
                    else:
                        loop.run_until_complete(self.controller.handle_key_input_async(key, frame))
                else:
                    # Headless mode: time.sleep for frame pacing
                    if wait_ms > 1:
                        time.sleep(wait_ms / 1000.0)

                # Update pipeline metrics (for observability)
                loop_total_ms = (time.monotonic() - t_loop_start) * 1000.0
                self._update_pipeline_metrics(processing_ms, wait_ms, loop_total_ms)

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received - shutting down gracefully...")
            self.controller.shutdown_flag = True
            self._shutdown_initiated = True
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {e}")
            self.controller.shutdown_flag = True
            self._shutdown_initiated = True

        try:
            self._shutdown()
        finally:
            if not loop.is_closed():
                loop.close()
            asyncio.set_event_loop(None)

    def _update_pipeline_metrics(self, processing_ms: float, wait_ms: float, loop_total_ms: float):
        """Update pipeline metrics on the controller for API exposure."""
        metrics = getattr(self.controller, '_pipeline_metrics', None)
        if metrics is not None:
            target_fps = self.controller.video_handler.fps or 30
            budget_ms = 1000.0 / max(target_fps, 1)
            metrics['total_processing_ms'] = round(processing_ms, 2)
            metrics['frame_pacing_ms'] = round(wait_ms, 2)
            metrics['loop_total_ms'] = round(loop_total_ms, 2)
            metrics['fps_actual'] = round(1000.0 / max(loop_total_ms, 0.1), 1)
            metrics['fps_target'] = round(target_fps, 1)
            metrics['budget_utilization'] = round(processing_ms / max(budget_ms, 0.1), 3)
            metrics['pipeline_mode'] = self._pipeline_mode
            metrics['capture_mode'] = getattr(self.controller.video_handler, '_capture_mode', '')
            metrics['frame_id'] = self._flow_frame_count
            metrics['total_frames'] = self._flow_frame_count
            if processing_ms > budget_ms:
                metrics['overrun_count'] = metrics.get('overrun_count', 0) + 1

    def _shutdown(self):
        """Graceful shutdown sequence."""
        logging.info("Starting graceful shutdown sequence...")

        import os
        shutdown_timer = threading.Timer(10.0, lambda: os._exit(1))
        shutdown_timer.daemon = True
        shutdown_timer.start()

        try:
            flight_loop = getattr(self, "flight_loop", None)
            if (
                flight_loop is None
                or flight_loop.is_closed()
                or not flight_loop.is_running()
            ):
                raise RuntimeError("Flight event loop is unavailable during shutdown")
            shutdown_future = asyncio.run_coroutine_threadsafe(
                self.controller.shutdown(),
                flight_loop,
            )
            shutdown_future.result(timeout=10.0)
            logging.info("App controller shutdown complete")
        except Exception as e:
            logging.error(f"Error during app controller shutdown: {e}")

        try:
            server_loop = getattr(self, "server_loop", None)
            if (
                hasattr(self.controller.api_handler, "stop")
                and server_loop is not None
                and not server_loop.is_closed()
                and server_loop.is_running()
            ):
                stop_future = asyncio.run_coroutine_threadsafe(
                    self.controller.api_handler.stop(),
                    server_loop,
                )
                stop_future.result(timeout=5.0)
                logging.info("FastAPI handler stopped")
            elif server_loop is not None and not server_loop.is_running():
                logging.info("FastAPI event loop already stopped")
        except Exception as e:
            logging.error(f"Error stopping FastAPI handler: {e}")

        try:
            logging.info("Waiting for server thread to finish...")
            self.server_thread.join(timeout=3.0)
            if self.server_thread.is_alive():
                logging.warning("Server thread did not stop within timeout - forcing shutdown")
            else:
                logging.info("Server thread stopped")
        except Exception as e:
            logging.error(f"Error joining server thread: {e}")

        self.stop_flight_event_loop()

        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.destroyAllWindows()

        # Release Windows high-resolution timer
        if self._windows_timer_set:
            try:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

        shutdown_timer.cancel()
        logging.info("Application shutdown complete")


    def shutdown_handler(self, signum, frame):
        """
        Signal handler to gracefully shutdown the application.

        Args:
            signum (int): The signal number.
            frame (FrameType): The current stack frame.
        """
        # Prevent multiple shutdown calls
        if self._shutdown_initiated:
            logging.debug(f"Shutdown signal {signum} ignored - already shutting down")
            return

        logging.info(f"Shutdown signal received ({signum}) - initiating graceful shutdown...")
        self._shutdown_initiated = True
        self.controller.shutdown_flag = True

        # Don't run async operations in signal handler - let main loop handle cleanup
        # The main loop will detect shutdown_flag and handle proper cleanup
