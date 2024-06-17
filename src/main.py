import asyncio
import logging
from classes.app_controller import AppController
from classes.parameters import Parameters
import cv2

async def main():
    logging.basicConfig(level=logging.DEBUG)
    controller = AppController()

    while True:
        frame = controller.video_handler.get_frame()
        if frame is None:
            break  # End of video or camera feed error

        frame = await controller.update_loop(frame)
        controller.show_current_frame()

        key = cv2.waitKey(controller.video_handler.delay_frame) & 0xFF
        if key == ord('q'):  # Quit program
            break
        else:
            await controller.handle_key_input_async(key, frame)  # Use await here

    await controller.shutdown()  # Ensure a clean shutdown
    controller.video_handler.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    asyncio.run(main())  # Start the asyncio event loop with main()
