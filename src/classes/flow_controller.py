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
    def __init__(self):
        """
        Initializes the FlowController, including the AppController and FastAPI server.
        """
        logging.debug("Initializing FlowController...")

        # Initialize AppController
        self.controller = AppController()

        # Initialize FastAPI server
        self.server, self.server_thread = self.start_fastapi_server()

        # Setup signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)

        self.controller.shutdown_flag = False
        self._shutdown_initiated = False  # Prevent multiple shutdown calls

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

        # Frame counter for periodic logging
        self._flow_frame_count = 0

    def start_fastapi_server(self):
        """
        Initializes and starts the FastAPI server in a separate thread.
        """
        logging.debug("Initializing FastAPI server...")
        fastapi_handler = self.controller.api_handler

        # Start the FastAPI server using the async start method
        def run_server():
            asyncio.run(fastapi_handler.start(
                host=Parameters.HTTP_STREAM_HOST,
                port=Parameters.HTTP_STREAM_PORT
            ))

        server_thread = threading.Thread(target=run_server)
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

    def main_loop(self):
        """
        Main loop to handle video processing, user inputs, and the main application flow.
        """
        try:
            # Create a persistent event loop
            loop = asyncio.get_event_loop()

            while not self.controller.shutdown_flag:
                t_loop_start = time.monotonic()

                frame = self.controller.video_handler.get_frame()
                if frame is None:
                    logging.warning("FlowController: No frame from video_handler - continuing in degraded mode")
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

        self._shutdown()

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

        loop = asyncio.get_event_loop()

        try:
            loop.run_until_complete(self.controller.shutdown())
            logging.info("App controller shutdown complete")
        except Exception as e:
            logging.error(f"Error during app controller shutdown: {e}")

        try:
            if hasattr(self.controller.api_handler, 'stop'):
                loop.run_until_complete(self.controller.api_handler.stop())
                logging.info("FastAPI handler stopped")
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
        logging.info("Application shutdown complete - exiting")
        os._exit(0)


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
