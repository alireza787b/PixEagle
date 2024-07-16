import asyncio
import logging
import signal
from classes.app_controller import AppController
import cv2
import threading

def start_fastapi_server(controller):
    from uvicorn import Config, Server
    from classes.fastapi_handler import FastAPIHandler

    # Pass the controller's video_handler and telemetry_handler to FastAPIHandler
    fastapi_handler = FastAPIHandler(controller.video_handler, controller.telemetry_handler)
    app = fastapi_handler.app

    config = Config(app=app, host="0.0.0.0", port=8000, log_level="info")
    server = Server(config)
    
    # Run the server in a separate thread to avoid blocking
    server_thread = threading.Thread(target=server.run)
    server_thread.start()
    
    return server, server_thread

async def main():
    logging.basicConfig(level=logging.DEBUG)
    controller = AppController()

    server, server_thread = start_fastapi_server(controller)

    def shutdown_handler(signum, frame):
        logging.info("Shutting down...")
        asyncio.create_task(controller.shutdown())
        server.should_exit = True  # Gracefully stop the FastAPI server

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    while True:
        frame = controller.video_handler.get_frame()
        if frame is None:
            break  # End of video or camera feed error

        frame = await controller.update_loop(frame)
        controller.show_current_frame()

        key = cv2.waitKey(controller.video_handler.delay_frame) & 0xFF
        if key == ord('q'):  # Quit program
            logging.info("Quitting...")
            break
        else:
            await controller.handle_key_input_async(key, frame)

    await controller.shutdown()
    server.should_exit = True  # Ensure the FastAPI server is stopped
    server_thread.join()  # Wait for the server thread to finish
    controller.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    asyncio.run(main())
