# src/classes/flow_controller.py
import asyncio
import logging
import threading
import signal
import time
import cv2
from classes.app_controller import AppController
from classes.parameters import Parameters

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

    def main_loop(self):
        """
        Main loop to handle video processing, user inputs, and the main application flow.
        """
        try:
            # Create a persistent event loop
            loop = asyncio.get_event_loop()

            while not self.controller.shutdown_flag:
                frame = self.controller.video_handler.get_frame()
                if frame is None:
                    logging.warning("📹 FlowController: No frame from video_handler - breaking loop")
                    break

                # DEBUG: Log every 200th frame to verify flow controller is running
                if not hasattr(self, '_flow_frame_count'):
                    self._flow_frame_count = 0
                self._flow_frame_count += 1
                if self._flow_frame_count % 200 == 0:
                    logging.info(f"📹 FLOW_CONTROLLER RUNNING: Processing frame #{self._flow_frame_count}")

                # Run the update loop within the persistent event loop
                frame = loop.run_until_complete(self.controller.update_loop(frame))
                self.controller.show_current_frame()

                # Handle frame timing and keyboard input
                # In headless mode (SHOW_VIDEO_WINDOW=false), cv2.waitKey() fails without GUI backend
                # Use time.sleep() for frame timing instead
                if Parameters.SHOW_VIDEO_WINDOW:
                    # GUI mode: use cv2.waitKey for timing and keyboard input
                    key = cv2.waitKey(self.controller.video_handler.delay_frame) & 0xFF
                    if key == ord('q'):
                        logging.info("⚡ Quit requested via 'q' key...")
                        self.controller.shutdown_flag = True
                    else:
                        # Handle key input within the persistent event loop
                        loop.run_until_complete(self.controller.handle_key_input_async(key, frame))
                else:
                    # Headless mode: use time.sleep for frame timing (convert ms to seconds)
                    # Keyboard input not available - use API or signals to control
                    delay_seconds = self.controller.video_handler.delay_frame / 1000.0
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)

        except KeyboardInterrupt:
            logging.info("⚡ Keyboard interrupt received - shutting down gracefully...")
            self.controller.shutdown_flag = True
            self._shutdown_initiated = True  # Mark as initiated from main loop too
        except Exception as e:
            logging.error(f"💥 Unexpected error in main loop: {e}")
            self.controller.shutdown_flag = True
            self._shutdown_initiated = True

        # Ensure proper shutdown
        logging.info("🛑 Starting graceful shutdown sequence...")

        # Add overall timeout for shutdown process
        import os
        shutdown_timer = threading.Timer(10.0, lambda: os._exit(1))  # Force exit after 10 seconds
        shutdown_timer.daemon = True
        shutdown_timer.start()

        try:
            loop.run_until_complete(self.controller.shutdown())
            logging.info("✅ App controller shutdown complete")
        except Exception as e:
            logging.error(f"❌ Error during app controller shutdown: {e}")

        # Stop the FastAPI server
        try:
            if hasattr(self.controller.api_handler, 'stop'):
                loop.run_until_complete(self.controller.api_handler.stop())
                logging.info("✅ FastAPI handler stopped")
        except Exception as e:
            logging.error(f"❌ Error stopping FastAPI handler: {e}")

        # Wait for server thread with timeout
        try:
            logging.info("⏳ Waiting for server thread to finish...")
            self.server_thread.join(timeout=3.0)  # Wait max 3 seconds
            if self.server_thread.is_alive():
                logging.warning("⚠️ Server thread did not stop within timeout - forcing shutdown")
                # Don't wait longer - just exit
            else:
                logging.info("✅ Server thread stopped")
        except Exception as e:
            logging.error(f"❌ Error joining server thread: {e}")

        # Close windows
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.destroyAllWindows()

        # Cancel the emergency shutdown timer
        shutdown_timer.cancel()

        logging.info("🎯 Application shutdown complete - exiting")

        # Force exit immediately (don't wait for daemon threads)
        os._exit(0)  # More forceful than sys.exit()


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

        logging.info(f"🛑 Shutdown signal received ({signum}) - initiating graceful shutdown...")
        self._shutdown_initiated = True
        self.controller.shutdown_flag = True

        # Don't run async operations in signal handler - let main loop handle cleanup
        # The main loop will detect shutdown_flag and handle proper cleanup
