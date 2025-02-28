# src/classes/video_handler.py
import cv2
import time
import logging
from collections import deque
from classes.parameters import Parameters

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class VideoHandler:
    """
    Handles video input from various sources, such as video files, USB cameras, and RTSP streams.
    Capable of storing a recent history of video frames for later retrieval.
    """

    def __init__(self):
        """
        Initializes the video source based on the configuration and prepares
        frame storage if required.
        """
        self.cap = None  # VideoCapture object
        self.frame_history = deque(maxlen=Parameters.STORE_LAST_FRAMES)  # Stores the history of frames
        self.width = None  # Actual width of the video source
        self.height = None  # Actual height of the video source
        self.delay_frame = self.init_video_source()  # Delay between frames (ms)

        # Raw and processed frames for later use
        self.current_raw_frame = None      # Raw unprocessed frame
        self.current_osd_frame = None      # Processed frame (e.g., with OSD)

        # Resized frames for streaming
        self.current_resized_raw_frame = None
        self.current_resized_osd_frame = None

    def gstreamer_pipeline(self, sensor_id=0, capture_width=1280, capture_height=720,
                           framerate=30, flip_method=0):
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
            % (sensor_id, capture_width, capture_height, framerate,
               flip_method, capture_width, capture_height)
        )
        logger.debug(f"Constructed GStreamer pipeline: {pipeline}")
        return pipeline

    def init_video_source(self, max_retries=5, retry_delay=1):
        """
        Initializes the video source based on the configuration specified in Parameters.
        Sets up the `cv2.VideoCapture` object.
        """
        for attempt in range(max_retries):
            logger.debug(f"Attempt {attempt + 1} to open video source.")
            try:
                self.cap = self._create_capture_object()  # Create capture object based on source type
                if self.cap and self.cap.isOpened():
                    logger.debug("Successfully opened video source.")
                    break
                else:
                    logger.warning(f"Failed to open video source on attempt {attempt + 1}.")
            except Exception as e:
                logger.error(f"Exception while opening video source: {e}")
            time.sleep(retry_delay)
        else:
            raise ValueError("Could not open video source after max retries.")

        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self.cap.get(cv2.CAP_PROP_FPS) or Parameters.DEFAULT_FPS  # Use default if FPS is unavailable
        delay_frame = max(int(1000 / fps), 1)
        return delay_frame

    def _create_capture_object(self):
        """
        Creates a cv2.VideoCapture object based on the video source type in Parameters.
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
        Also stores the frame in history if needed.
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
        """
        return list(self.frame_history)

    def clear_frame_history(self):
        """ Clears the entire frame history. """
        self.frame_history.clear()

    def update_resized_frames(self, width, height):
        """
        Resizes the raw_frame and osd_frame for streaming exactly once per update loop.
        """
        # Resize RAW frame
        if self.current_raw_frame is not None:
            self.current_resized_raw_frame = cv2.resize(self.current_raw_frame, (width, height))
        else:
            self.current_resized_raw_frame = None

        # Resize OSD frame
        if self.current_osd_frame is not None:
            self.current_resized_osd_frame = cv2.resize(self.current_osd_frame, (width, height))
        else:
            self.current_resized_osd_frame = None

    def release(self):
        """ Releases the video source and resources. """
        if self.cap:
            self.cap.release()
            logger.debug("Video source released.")

    def test_video_feed(self):
        """
        Displays the video feed to verify the source. Press 'q' to quit the test.
        """
        logger.info("Testing video feed. Press 'q' to exit.")
        while True:
            frame = self.get_frame()
            if frame is None:
                logger.info("No more frames or an error occurred.")
                break
            cv2.imshow("Test Video Feed", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        self.release()
        cv2.destroyAllWindows()
