from classes.video_handler import VideoHandler
from classes.tracker import Tracker
from classes.parameters import Parameters
import cv2

def main():
    video_handler = VideoHandler()
    tracker = Tracker()
    tracking_started = False
    deviation_display = Parameters.DISPLAY_DEVIATIONS

    while True:
        frame = video_handler.get_frame()
        if frame is None:
            break  # End of video or camera feed error

        if tracking_started:
            success, bbox = tracker.update(frame)
            if success:
                # Draw bounding box and center dot on the frame
                p1 = (int(bbox[0]), int(bbox[1]))
                p2 = (int(bbox[0] + bbox[2]), int(bbox[1] + bbox[3]))
                center = (int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2))
                
                cv2.rectangle(frame, p1, p2, (255,0,0), 2, 1)
                cv2.circle(frame, center, 5, (0,0,255), -1)  # Red dot at the center

                if deviation_display:
                    frame_center = (frame.shape[1] // 2, frame.shape[0] // 2)
                    deviation = (center[0] - frame_center[0], center[1] - frame_center[1])
                    print(f"Deviation from center: {deviation}")

        # Display the frame after modifications
        cv2.imshow("Tracking", frame)

        key = cv2.waitKey(video_handler.delay_frame) & 0xFF  # Use dynamic delay based on video FPS
        if key == ord('q'):  # Quit program
            break
        elif key == ord('t') and not tracking_started:  # Start tracking
            # Temporarily pause the video feed to select ROI
            bbox = cv2.selectROI("Tracking", frame, False, False)
            cv2.destroyWindow("ROI selector")
            if bbox and bbox[2] > 0 and bbox[3] > 0:  # Check if bbox is valid
                tracker.start_tracking(frame, bbox)
                tracking_started = True
            else:
                print("Tracking canceled or invalid ROI.")
        elif key == ord('c') and tracking_started:  # Cancel tracking
            tracking_started = False
            tracker.init_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM)  # Reinitialize tracker

    video_handler.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
