# src/classes/video_handler.py
import cv2
from .parameters import Parameters
from collections import deque

class VideoHandler:
    """
    Handles video input from various sources, such as video files or USB cameras.
    Capable of storing a recent history of video frames for later retrieval.

    Attributes:
        cap (cv2.VideoCapture): OpenCV video capture object.
        frame_history (deque): Stores the most recent frames.
    """

    def __init__(self):
        """
        Initializes the video source based on the configuration and prepares
        frame storage if required.
        """
        self.cap = None  # VideoCapture object
        self.frame_history = deque(maxlen=Parameters.STORE_LAST_FRAMES)
        self.width = None  # Width of the video source
        self.height = None  # Height of the video source
        self.delay_frame = self.init_video_source()
        
        self.init_video_source()

    def init_video_source(self):
        """
        Initializes the video source based on the configuration specified in Parameters.

        This method sets up the `cv2.VideoCapture` object (`self.cap`) to capture video
        from the specified source, which can be a video file or a USB camera. The method
        determines the appropriate delay between frames (`delay_frame`) to regulate the
        playback speed or processing rate, based on the source's frames per second (FPS).

        Future enhancements can include support for additional video source types, such as
        RTSP (Real Time Streaming Protocol) streams, UDP (User Datagram Protocol) streams,
        or other network video services by extending the conditional checks to handle new
        `VIDEO_SOURCE_TYPE` values and initializing `cv2.VideoCapture` with the appropriate
        network URLs or identifiers.

        Raises:
            ValueError: If the video source cannot be opened or if an unsupported video
            source type is specified in the Parameters.

        Returns:
            int: The calculated delay in milliseconds between frames, based on the source FPS.
        """
        if Parameters.VIDEO_SOURCE_TYPE == "VIDEO_FILE":
            self.cap = cv2.VideoCapture(Parameters.VIDEO_SOURCE_IDENTIFIER)
            # Retrieve width and height from the video source
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
            # Attempt to retrieve the FPS of the video source
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = Parameters.DEFAULT_FPS  # Fallback to default if detection fails
            delay_frame = max(int(1000 / fps), 1)  # Ensure delay is at least 1ms
        elif Parameters.VIDEO_SOURCE_TYPE == "USB_CAMERA":
            # Initialize USB camera. VIDEO_SOURCE_IDENTIFIER is expected to be the camera index as a string
            camera_index = int(Parameters.VIDEO_SOURCE_IDENTIFIER)  # Convert identifier to integer
            self.cap = cv2.VideoCapture(camera_index)
            fps = self.cap.get(cv2.CAP_PROP_FPS)  # Attempt to retrieve the FPS of the USB camera
            if fps <= 0:
                fps = Parameters.DEFAULT_FPS  # Use default FPS if unable to retrieve
            delay_frame = max(int(1000 / fps), 1)  # Calculate delay based on FPS
        else:
            # Handle other source types if necessary
            raise ValueError(f"Unsupported video source type: {Parameters.VIDEO_SOURCE_TYPE}")

        if not self.cap or not self.cap.isOpened():
            raise ValueError(f"Could not open video source: {Parameters.VIDEO_SOURCE_IDENTIFIER}")
        
        return delay_frame



    def get_frame(self):
        """
        Reads and returns the next frame from the video source.
        Also stores the frame in the history if required.

        Returns:
            frame (numpy.ndarray or None): The next video frame, or None if there are no more frames.
        """
        if self.cap:
            ret, frame = self.cap.read()
            if ret:
                self.frame_history.append(frame)
                return frame
            else:
                # End of video file or error reading frame
                return None
        else:
            return None

    def get_last_frames(self):
        """
        Returns the most recent frames stored in the history.

        Returns:
            A list of the most recent frames, up to the number specified in Parameters.STORE_LAST_FRAMES.
            Returns an empty list if no frames are available.
        """
        return list(self.frame_history)
    
    def clear_frame_history(self):
        """
        Clears the entire frame history, effectively resetting the stored frames.
        """
        self.frame_history.clear()

    def release(self):
        """
        Releases the video source and any associated resources.
        """
        if self.cap:
            self.cap.release()

    def test_video_feed(self):
            """
            Displays the video feed to verify that the video source is correctly initialized
            and frames can be read. Press 'q' to quit the test.
            """
            print("Testing video feed. Press 'q' to exit.")
            while True:
                frame = self.get_frame()
                if frame is None:
                    print("No more frames to display, or an error occurred.")
                    break

                cv2.imshow("Test Video Feed", frame)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            self.release()
            cv2.destroyAllWindows()