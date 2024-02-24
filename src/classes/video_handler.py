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
        Initializes the video source based on the updated configuration specified in Parameters.

        This method sets up the `cv2.VideoCapture` object (`self.cap`) to capture video from various sources,
        including video files, USB cameras, and RTSP streams. The selection is based on the `VIDEO_SOURCE_TYPE`
        parameter in the `Parameters` class. Specific parameters for each source type (e.g., file path, camera index, RTSP URL)
        are utilized to initialize the video capture.

        The method also calculates the appropriate delay between frames (`delay_frame`) based on the video source's FPS.
        This is crucial for regulating the playback speed or processing rate, especially when automatic FPS detection fails.

        Enhancements can include support for additional video source types by adding new parameters in the `Parameters`
        class and extending the conditional logic within this method.

        Raises:
            ValueError: If the video source cannot be opened or if an unsupported video source type is specified.

        Returns:
            int: The calculated delay in milliseconds between frames, based on the detected or default FPS.
        """
        # Initialize the video capture object based on the source type
        if Parameters.VIDEO_SOURCE_TYPE == "VIDEO_FILE":
            self.cap = cv2.VideoCapture(Parameters.VIDEO_FILE_PATH)
        elif Parameters.VIDEO_SOURCE_TYPE == "USB_CAMERA":
            self.cap = cv2.VideoCapture(Parameters.CAMERA_INDEX)
        elif Parameters.VIDEO_SOURCE_TYPE == "RTSP_STREAM":
            self.cap = cv2.VideoCapture(Parameters.RTSP_URL)
        elif Parameters.VIDEO_SOURCE_TYPE == "UDP_STREAM":
            # Initialize UDP stream using the provided UDP URL
            self.cap = cv2.VideoCapture(Parameters.UDP_URL)
        else:
            raise ValueError(f"Unsupported video source type: {Parameters.VIDEO_SOURCE_TYPE}")

        # Check if the video source was successfully opened
        if not self.cap or not self.cap.isOpened():
            raise ValueError("Could not open video source with the provided settings.")
    
        # Retrieve and set video properties such as width, height, and FPS
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = Parameters.DEFAULT_FPS  # Use a default FPS if detection fails or isn't applicable

        # Calculate the frame delay to maintain playback speed or processing rate
        delay_frame = max(int(1000 / fps), 1)  # Ensure delay is at least 1ms to avoid division by zero

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