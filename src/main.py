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
            break  # End of video or camera feed erro
        if tracking_started:
            success, _ = tracker.update(frame)
            if success:
                frame = tracker.draw_tracking(frame)  # Draw tracking info and report deviation
                if Parameters.USE_ESTIMATOR == True:   
                    frame = tracker.draw_estimate(frame)  # Draw tracking info and report deviation

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
