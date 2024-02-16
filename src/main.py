# src/main.py

from classes.video_handler import VideoHandler
import cv2

def main():
    video_handler = VideoHandler()  # Initialize the VideoHandler

    while True:
        frame = video_handler.get_frame()  # Get the next frame from the video handler
        if frame is None:
            break  # If no frame is returned, the video has ended or there was an error

        cv2.imshow("Video Feed", frame)  # Display the current frame

        # Break the loop and end the program if the user presses 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    video_handler.release()  # Release the video source
    cv2.destroyAllWindows()  # Close all OpenCV windows

if __name__ == "__main__":
    main()
