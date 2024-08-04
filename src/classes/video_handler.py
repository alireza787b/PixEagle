import cv2
from .parameters import Parameters
from collections import deque
import time
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

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
        self.current_raw_frame = None
        self.current_osd_frame = None

    def gstreamer_pipeline(self, sensor_id=0, capture_width=1280, capture_height=720, framerate=30, flip_method=0):
        """
        Generates a GStreamer pipeline string for accessing a CSI camera.
        """
        return (
            "nvarguscamerasrc sensor-id=%d ! "
            "video/x-raw(memory:NVMM), width=(int)%d, height=(int)%d, format=(string)NV12, framerate=(fraction)%d/1 ! "
            "nvvidconv flip-method=%d ! "
            "video/x-raw, width=(int)%d, height=(int)%d, format=(string)BGRx ! "
            "videoconvert ! "
            "video/x-raw, format=(string)BGR ! appsink"
            % (sensor_id, capture_width, capture_height, framerate, flip_method, capture_width, capture_height)
        )

    def init_video_source(self, max_retries=5, retry_delay=1):
        """
        Initializes the video source based on the updated configuration specified in Parameters.
        This method sets up the `cv2.VideoCapture` object (`self.cap`) to capture video from various sources,
        including video files, USB cameras, RTSP streams, UDP streams, HTTP streams, and CSI cameras.
        Raises:
            ValueError: If the video source cannot be opened after max_retries or if an unsupported video source type is specified.
        Returns:
            int: The calculated delay in milliseconds between frames, based on the detected or default FPS.
        """
        # Initialize the video capture object based on the source type
        for attempt in range(max_retries):
            logging.debug(f"Attempt {attempt + 1} to open video source.")
            try:
                if Parameters.VIDEO_SOURCE_TYPE == "VIDEO_FILE":
                    self.cap = cv2.VideoCapture(Parameters.VIDEO_FILE_PATH)
                elif Parameters.VIDEO_SOURCE_TYPE == "USB_CAMERA":
                    self.cap = cv2.VideoCapture(Parameters.CAMERA_INDEX)
                elif Parameters.VIDEO_SOURCE_TYPE == "RTSP_STREAM":
                    self.cap = cv2.VideoCapture(Parameters.RTSP_URL)
                elif Parameters.VIDEO_SOURCE_TYPE == "UDP_STREAM":
                    self.cap = cv2.VideoCapture(Parameters.UDP_URL, cv2.CAP_FFMPEG)
                elif Parameters.VIDEO_SOURCE_TYPE == "HTTP_STREAM":
                    self.cap = cv2.VideoCapture(Parameters.HTTP_URL)
                elif Parameters.VIDEO_SOURCE_TYPE == "CSI_CAMERA":
                    pipeline = self.gstreamer_pipeline(
                        sensor_id=Parameters.CSI_SENSOR_ID,
                        capture_width=Parameters.CSI_WIDTH,
                        capture_height=Parameters.CSI_HEIGHT,
                        framerate=Parameters.CSI_FRAMERATE,
                        flip_method=Parameters.CSI_FLIP_METHOD
                    )
                    self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                else:
                    raise ValueError(f"Unsupported video source type: {Parameters.VIDEO_SOURCE_TYPE}")

                # Check if the video source was successfully opened
                if self.cap and self.cap.isOpened():
                    logging.debug("Successfully opened video source.")
                    break
                else:
                    logging.warning(f"Failed to open video source on attempt {attempt + 1}.")
                
            except Exception as e:
                logging.error(f"Exception occurred while opening video source: {e}")

            # If the video source was not successfully opened, wait before retrying
            time.sleep(retry_delay)
        else:
            # If the video source could not be opened after max_retries, raise an error
            raise ValueError("Could not open video source with the provided settings after maximum retries.")

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
            self.current_raw_frame = frame
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
        logging.info("Testing video feed. Press 'q' to exit.")
        while True:
            frame = self.get_frame()
            if frame is None:
                logging.info("No more frames to display, or an error occurred.")
                break

            cv2.imshow("Test Video Feed", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        self.release()
        cv2.destroyAllWindows()
