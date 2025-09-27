# src/classes/flow_controller.py
import asyncio
import logging
import threading
import signal
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
        # Stop the FastAPI server
        if hasattr(self.controller.api_handler, 'stop'):
            loop.run_until_complete(self.controller.api_handler.stop())
        self.server_thread.join()  # Wait for the FastAPI server thread to finish
        if Parameters.SHOW_VIDEO_WINDOW:
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
        # Stop the FastAPI server
        if hasattr(self.controller.api_handler, 'stop'):
            asyncio.run(self.controller.api_handler.stop())
        self.controller.shutdown_flag = True
