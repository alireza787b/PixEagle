import asyncio
import logging
import threading
import signal
import cv2
from uvicorn import Config, Server
from classes.app_controller import AppController
from classes.parameters import Parameters

def start_fastapi_server(controller):
    """
    Initializes and starts the FastAPI server in a separate thread.
    """
    logging.debug("Initializing FastAPI server...")
    fastapi_handler = controller.api_handler
    app = fastapi_handler.app

    config = Config(app=app, host=Parameters.HTTP_STREAM_HOST, port=Parameters.HTTP_STREAM_PORT, log_level="info")
    server = Server(config)
    
    server_thread = threading.Thread(target=server.run)
    server_thread.start()
    logging.debug("FastAPI server started on a separate thread.")
    return server, server_thread

def main():
    """
    Main function to initialize the application and run the main loop.
    """
    logging.basicConfig(level=logging.INFO)
    logging.debug("Starting main application...")

    controller = AppController()
    server, server_thread = start_fastapi_server(controller)

    def shutdown_handler(signum, frame):
        """
        Signal handler to gracefully shutdown the application.

        Args:
            signum (int): The signal number.
            frame (FrameType): The current stack frame.
        """
        logging.info("Shutting down...")
        asyncio.run(controller.shutdown())
        controller.shutdown_flag = True

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    controller.shutdown_flag = False

    try:
        while not controller.shutdown_flag:
            frame = controller.video_handler.get_frame()
            if frame is None:
                break

            frame = asyncio.run(controller.update_loop(frame))
            controller.show_current_frame()

            key = cv2.waitKey(controller.video_handler.delay_frame) & 0xFF
            if key == ord('q'):
                logging.info("Quitting...")
                controller.shutdown_flag = True
            else:
                asyncio.run(controller.handle_key_input_async(key, frame))

    except Exception as e:
        logging.error(f"An error occurred: {e}")

    asyncio.run(controller.shutdown())
    server.should_exit = True
    server_thread.join()  # Wait for the FastAPI server thread to finish
    cv2.destroyAllWindows()
    logging.debug("Application shutdown complete.")

if __name__ == "__main__":
    main()
