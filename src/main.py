import asyncio
import logging
import signal
import cv2
import threading
from uvicorn import Config, Server
from classes.app_controller import AppController
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
    logging.debug("Initializing FastAPI server...")
    fastapi_handler = FastAPIHandler(controller.video_handler, controller.telemetry_handler, controller)
    app = fastapi_handler.app

    config = Config(app=app, host=Parameters.HTTP_STREAM_HOST, port=Parameters.HTTP_STREAM_PORT, log_level="info")
    server = Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    fastapi_handler.server = server
    logging.debug("FastAPI server started.")

    return server, server_thread

async def main():
    """
    Main function to initialize the application and run the main loop.
    """
    logging.basicConfig(level=logging.DEBUG)
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
        asyncio.create_task(controller.shutdown())
        server.should_exit = True
        controller.shutdown_flag = True

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    controller.shutdown_flag = False

    while not controller.shutdown_flag:
        frame = controller.video_handler.get_frame()
        if frame is None:
            break

        frame = await controller.update_loop(frame)
        controller.show_current_frame()

        key = cv2.waitKey(controller.video_handler.delay_frame) & 0xFF
        if key == ord('q'):
            logging.info("Quitting...")
            controller.shutdown_flag = True
        else:
            await controller.handle_key_input_async(key, frame)

    await controller.shutdown()
    server.should_exit = True
    server_thread.join()
    cv2.destroyAllWindows()
    logging.debug("Application shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())
