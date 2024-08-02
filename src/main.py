import asyncio
import logging
import signal
import cv2
from uvicorn import Config, Server
from classes.app_controller import AppController
from classes.parameters import Parameters

async def start_fastapi_server(controller):
    """
    Initializes and configures the FastAPI server to run within the event loop.

    Args:
        controller (AppController): The application controller instance.

    Returns:
        Server: The running FastAPI server.
    """
    logging.debug("Initializing FastAPI server...")
    fastapi_handler = controller.api_handler
    app = fastapi_handler.app

    config = Config(app=app, host=Parameters.HTTP_STREAM_HOST, port=Parameters.HTTP_STREAM_PORT, log_level="info")
    server = Server(config)

    async def run_server():
        await server.serve()

    server_task = asyncio.create_task(run_server())
    logging.debug("FastAPI server task created.")
    
    return server, server_task

async def main():
    """
    Main function to initialize the application and run the main loop.
    """
    logging.basicConfig(level=logging.DEBUG)
    logging.debug("Starting main application...")

    controller = AppController()
    logging.debug("AppController initialized.")

    server, server_task = await start_fastapi_server(controller)
    logging.debug("FastAPI server started.")

    def shutdown_handler(signum, frame):
        """
        Signal handler to gracefully shutdown the application.

        Args:
            signum (int): The signal number.
            frame (FrameType): The current stack frame.
        """
        logging.info("Shutting down...")
        asyncio.create_task(controller.shutdown())
        controller.shutdown_flag = True

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    controller.shutdown_flag = False

    try:
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

            await asyncio.sleep(0)  # Yield control to the event loop

    except Exception as e:
        logging.error(f"An error occurred: {e}")

    await controller.shutdown()
    server.should_exit = True
    server_task.cancel()  # Cancel the FastAPI server task
    try:
        await server_task  # Ensure the server task completes
    except asyncio.CancelledError:
        pass
    cv2.destroyAllWindows()
    logging.debug("Application shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())
