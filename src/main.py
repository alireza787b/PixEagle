import asyncio
import logging
import signal
import cv2
from classes.app_controller import AppController
from classes.fastapi_handler import FastAPIHandler
from classes.parameters import Parameters

async def start_fastapi_server(controller):
    logging.debug("Initializing FastAPI server...")
    await controller.start_api_handler()

async def main():
    logging.basicConfig(level=logging.DEBUG)
    logging.debug("Starting main application...")

    controller = AppController()

    # Start the FastAPI server within the main event loop
    server_task = asyncio.create_task(start_fastapi_server(controller))

    def shutdown_handler(signum, frame):
        logging.info("Shutting down...")
        asyncio.create_task(controller.shutdown())
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
    await server_task
    cv2.destroyAllWindows()
    logging.debug("Application shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())
