import asyncio
import logging
import signal
from classes.app_controller import AppController
import cv2
import threading
from uvicorn import Config, Server
from classes.fastapi_handler import FastAPIHandler
from classes.parameters import Parameters

def start_fastapi_server(controller):
    """
    Starts the FastAPI server in a separate thread.
    
    Args:
        controller (AppController): The application controller instance.
        
    Returns:
        tuple: The server instance and the server thread.
    """
    # Pass the controller's video_handler and telemetry_handler to FastAPIHandler
    fastapi_handler = FastAPIHandler(controller.video_handler, controller.telemetry_handler, controller)
    app = fastapi_handler.app

    # Configure the server using host and port from Parameters
    config = Config(app=app, host=Parameters.HTTP_STREAM_HOST, port=Parameters.HTTP_STREAM_PORT, log_level="info")
    server = Server(config)
    
    # Run the server in a separate thread to avoid blocking
    server_thread = threading.Thread(target=server.run)
    server_thread.start()
    
    # Assign the server instance to the handler for shutdown
    fastapi_handler.server = server
    return server, server_thread

async def main():
    """
    Main function to initialize the application and run the main loop.
    """
    logging.basicConfig(level=logging.DEBUG)
    controller = AppController()

    # Start the FastAPI server
    server, server_thread = start_fastapi_server(controller)

    def shutdown_handler(signum, frame):
        """
        Signal handler to gracefully shutdown the application.
        
        Args:
            signum (int): The signal number.
            frame (FrameType): The current stack frame.
        """
        logging.info("Shutting down...")
        asyncio.create_task(controller.shutdown())
        server.should_exit = True  # Gracefully stop the FastAPI server
        controller.shutdown_flag = True  # Set the shutdown flag to stop the main loop

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    controller.shutdown_flag = False  # Initialize the shutdown flag

    while not controller.shutdown_flag:
        frame = controller.video_handler.get_frame()
        if frame is None:
            break  # End of video or camera feed error

        frame = await controller.update_loop(frame)
        controller.show_current_frame()

        key = cv2.waitKey(controller.video_handler.delay_frame) & 0xFF
        if key == ord('q'):  # Quit program
            logging.info("Quitting...")
            controller.shutdown_flag = True  # Set the shutdown flag to stop the main loop
        else:
            await controller.handle_key_input_async(key, frame)

    # Perform the shutdown sequence
    await controller.shutdown()
    server.should_exit = True  # Ensure the FastAPI server is stopped
    server_thread.join()  # Wait for the server thread to finish
    cv2.destroyAllWindows()  # Destroy all OpenCV windows

if __name__ == "__main__":
    asyncio.run(main())
