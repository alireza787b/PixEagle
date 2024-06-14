import asyncio
from classes.app_controller import AppController
from classes.parameters import Parameters
import cv2
import socket
import json
from datetime import datetime

async def main():
    controller = AppController()
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = (Parameters.UDP_HOST, Parameters.UDP_PORT)

    while True:
        frame = controller.video_handler.get_frame()
        if frame is None:
            break  # End of video or camera feed error

        frame = await controller.update_loop(frame)
        controller.show_current_frame()

        timestamp = datetime.utcnow().isoformat()
        tracker_started = controller.tracking_started is not None
        data = {
            'bounding_box': controller.tracker.bbox,
            'center': controller.tracker.normalized_center,
            'timestamp': timestamp,
            'tracker_started': tracker_started
        }
        message = json.dumps(data)
        udp_socket.sendto(message.encode('utf-8'), server_address)

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
