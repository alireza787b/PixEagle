import asyncio
import logging
import threading
import signal
import cv2
import numpy as np
from uvicorn import Config, Server
from classes.app_controller import AppController
from classes.parameters import Parameters

class FlowController:
    def __init__(self):
        """
        Initializes the FlowController by creating the AppController, starting the FastAPI server,
        and setting up signal handlers for graceful shutdown.
        """
        logging.info("Initializing FlowController...")
        # Create an instance of AppController (which internally starts the video and processing threads)
        self.controller = AppController()
        self.shutdown_flag = False

        # Start FastAPI server in a separate thread
        self.server, self.server_thread = self.start_fastapi_server()

        # Register signal handlers for SIGINT and SIGTERM for graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)

    def start_fastapi_server(self):
        """
        Initializes and starts the FastAPI server on a separate thread.
        Returns:
            server: The Uvicorn Server instance.
            server_thread: The Thread running the FastAPI server.
        """
        logging.info("Initializing FastAPI server...")
        fastapi_handler = self.controller.api_handler  # AppController must expose its FastAPI handler
        app = fastapi_handler.app

        config = Config(app=app, host=Parameters.HTTP_STREAM_HOST, 
                        port=Parameters.HTTP_STREAM_PORT, log_level="info")
        server = Server(config)
        server_thread = threading.Thread(target=server.run, name="FastAPIServerThread", daemon=True)
        server_thread.start()
        logging.info("FastAPI server started on a separate thread.")
        return server, server_thread

    def start(self):
        """
        Starts the AppController's video capture and processing pipeline.
        """
        logging.info("Starting the AppController (video capture and processing)...")
        self.controller.start()

    def main_loop(self):
        """
        Main loop that retrieves the latest processed frame from the AppController,
        displays it (if enabled), and handles key inputs.
        Press 'q' to initiate shutdown.
        """
        logging.info("Entering main loop. Press 'q' to quit.")
        try:
            while not self.shutdown_flag:
                # Retrieve the most recent processed frame; this should be updated by the processing thread.
                frame = self.controller.get_processed_frame()
                if frame is None:
                    # If no frame is available and ALLOW_NO_VIDEO_MODE is enabled, use a dummy black frame.
                    if getattr(Parameters, "ALLOW_NO_VIDEO_MODE", True):
                        width = int(getattr(Parameters, "STREAM_WIDTH", 640))
                        height = int(getattr(Parameters, "STREAM_HEIGHT", 480))
                        frame = np.zeros((height, width, 3), dtype=np.uint8)
                        logging.debug("No frame captured. Using dummy black frame.")
                    else:
                        continue

                # Display the frame if the video window is enabled.
                if Parameters.SHOW_VIDEO_WINDOW:
                    cv2.imshow(Parameters.FRAME_TITLE, frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        logging.info("User requested exit (q pressed).")
                        self.shutdown_flag = True
                    else:
                        # Handle other key inputs asynchronously (e.g., toggling segmentation or tracking)
                        asyncio.run(self.controller.handle_key_input_async(key, frame))
                else:
                    # If display is disabled, sleep briefly to reduce CPU usage.
                    cv2.waitKey(1)
        except Exception as e:
            logging.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            self.shutdown()

    def shutdown(self):
        """
        Gracefully shuts down the application by stopping the AppController,
        signaling the FastAPI server to exit, and cleaning up windows.
        """
        logging.info("Shutting down FlowController...")
        self.controller.stop()
        if self.server:
            self.server.should_exit = True
        if self.server_thread:
            self.server_thread.join(timeout=5)
        cv2.destroyAllWindows()
        logging.info("Application shutdown complete.")

    def shutdown_handler(self, signum, frame):
        """
        Signal handler for graceful shutdown when SIGINT or SIGTERM is received.
        """
        logging.info(f"Received shutdown signal ({signum}). Initiating shutdown.")
        self.shutdown_flag = True
