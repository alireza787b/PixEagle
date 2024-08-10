import cv2
from .parameters import Parameters
from collections import deque
import time
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class VideoHandler:
    """
    Handles video input from various sources, such as video files or USB cameras.
    Capable of storing a recent history of video frames for later retrieval.
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
        pipeline = (
            "nvarguscamerasrc sensor-id=%d ! "
            "video/x-raw(memory:NVMM), width=(int)%d, height=(int)%d, format=(string)NV12, framerate=(fraction)%d/1 ! "
            "nvvidconv flip-method=%d ! "
            "video/x-raw, format=(string)I420, width=(int)%d, height=(int)%d ! "
            "videoconvert ! "
            "video/x-raw, format=(string)BGR ! "
            "videoscale ! "
            "appsink"
            % (sensor_id, capture_width, capture_height, framerate, flip_method, capture_width, capture_height)
        )
        logger.debug(f"Constructed GStreamer pipeline: {pipeline}")
        return pipeline

    def init_video_source(self, max_retries=5, retry_delay=1):
        """
        Initializes the video source based on the configuration specified in Parameters.
        Sets up the `cv2.VideoCapture` object (`self.cap`) to capture video from various sources.

        Returns:
            int: The calculated delay in milliseconds between frames, based on the detected or default FPS.
        """
        for attempt in range(max_retries):
            logger.debug(f"Attempt {attempt + 1} to open video source.")
            try:
                self.cap = self._create_capture_object()
                if self.cap and self.cap.isOpened():
                    logger.debug("Successfully opened video source.")
                    break
                else:
                    logger.warning(f"Failed to open video source on attempt {attempt + 1}.")
            except Exception as e:
                logger.error(f"Exception occurred while opening video source: {e}")
            time.sleep(retry_delay)
        else:
            raise ValueError("Could not open video source with the provided settings after maximum retries.")

        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self.cap.get(cv2.CAP_PROP_FPS) or Parameters.DEFAULT_FPS
        delay_frame = max(int(1000 / fps), 1)  # Ensure delay is at least 1ms to avoid division by zero

        return delay_frame

    def _create_capture_object(self):
        """
        Creates and returns a cv2.VideoCapture object based on the video source type.

        Returns:
            cv2.VideoCapture: The video capture object.
        """
        source_initializers = {
            "VIDEO_FILE": lambda: cv2.VideoCapture(Parameters.VIDEO_FILE_PATH),
            "USB_CAMERA": lambda: cv2.VideoCapture(Parameters.CAMERA_INDEX),
            "RTSP_STREAM": lambda: cv2.VideoCapture(Parameters.RTSP_URL),
            "UDP_STREAM": lambda: cv2.VideoCapture(Parameters.UDP_URL, cv2.CAP_FFMPEG),
            "HTTP_STREAM": lambda: cv2.VideoCapture(Parameters.HTTP_URL),
            "CSI_CAMERA": lambda: cv2.VideoCapture(
                self.gstreamer_pipeline(
                    sensor_id=Parameters.CSI_SENSOR_ID,
                    capture_width=Parameters.CSI_WIDTH,
                    capture_height=Parameters.CSI_HEIGHT,
                    framerate=Parameters.CSI_FRAMERATE,
                    flip_method=Parameters.CSI_FLIP_METHOD,
                ),
                cv2.CAP_GSTREAMER,
            ),
        }

        if Parameters.VIDEO_SOURCE_TYPE not in source_initializers:
            raise ValueError(f"Unsupported video source type: {Parameters.VIDEO_SOURCE_TYPE}")

        return source_initializers[Parameters.VIDEO_SOURCE_TYPE]()

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
                self.current_raw_frame = frame
                self.frame_history.append(frame)
                return frame
            else:
                logger.warning("Failed to read frame from video source.")
                return None
        else:
            logger.error("Video capture object is not initialized.")
            return None

    def get_last_frames(self):
        """
        Returns the most recent frames stored in the history.

        Returns:
            list: The most recent frames, up to the number specified in Parameters.STORE_LAST_FRAMES.
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
            logger.debug("Video source released.")

    def test_video_feed(self):
        """
        Displays the video feed to verify that the video source is correctly initialized
        and frames can be read. Press 'q' to quit the test.
        """
        logger.info("Testing video feed. Press 'q' to exit.")
        while True:
            frame = self.get_frame()
            if frame is None:
                logger.info("No more frames to display, or an error occurred.")
                break

            cv2.imshow("Test Video Feed", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        self.release()
        cv2.destroyAllWindows()
