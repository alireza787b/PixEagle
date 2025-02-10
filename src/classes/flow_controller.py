# src/classes/flow_controller.py
import asyncio
import logging
import threading
import signal
import cv2
import numpy as np  # Added numpy import for dummy frame creation
from uvicorn import Config, Server
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

    def start_fastapi_server(self):
        """
        Initializes and starts the FastAPI server in a separate thread.
        """
        logging.debug("Initializing FastAPI server...")
        fastapi_handler = self.controller.api_handler
        app = fastapi_handler.app

        config = Config(app=app, host=Parameters.HTTP_STREAM_HOST, port=Parameters.HTTP_STREAM_PORT, log_level="info")
        server = Server(config)
        
        server_thread = threading.Thread(target=server.run)
        server_thread.start()
        logging.debug("FastAPI server started on a separate thread.")
        return server, server_thread

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
                    # If no frame is captured and ALLOW_NO_VIDEO_MODE is true,
                    # create a dummy black frame using STREAM_WIDTH and STREAM_HEIGHT.
                    if  getattr(Parameters, "ALLOW_NO_VIDEO_MODE", True):
                        width = int(getattr(Parameters, "STREAM_WIDTH", 640))
                        height = int(getattr(Parameters, "STREAM_HEIGHT", 480))
                        frame = np.zeros((height, width, 3), dtype=np.uint8)
                        logging.debug("No frame captured. Using dummy black frame due to video processing disabled.")
                    else:
                        break

                # Run the update loop within the persistent event loop
                frame = loop.run_until_complete(self.controller.update_loop(frame))
                self.controller.show_current_frame()

                key = cv2.waitKey(self.controller.video_handler.delay_frame) & 0xFF
                if key == ord('q'):
                    logging.info("Quitting...")
                    self.controller.shutdown_flag = True
                else:
                    # Handle key input within the persistent event loop
                    loop.run_until_complete(self.controller.handle_key_input_async(key, frame))

        except Exception as e:
            logging.error(f"An error occurred: {e}")

        # Ensure proper shutdown
        loop.run_until_complete(self.controller.shutdown())
        self.server.should_exit = True
        self.server_thread.join()  # Wait for the FastAPI server thread to finish
        cv2.destroyAllWindows()
        logging.debug("Application shutdown complete.")

    def shutdown_handler(self, signum, frame):
        """
        Signal handler to gracefully shutdown the application.

        Args:
            signum (int): The signal number.
            frame (FrameType): The current stack frame.
        """
        logging.info("Shutting down...")
        asyncio.run(self.controller.shutdown())
        self.controller.shutdown_flag = True
