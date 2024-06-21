# src/main.py
import asyncio
import logging
import signal
from classes.app_controller import AppController
import cv2

async def main():
    logging.basicConfig(level=logging.DEBUG)
    controller = AppController()

    def shutdown_handler(signum, frame):
        logging.info("Shutting down...")
        asyncio.ensure_future(controller.shutdown())

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
    controller.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    asyncio.run(main())
