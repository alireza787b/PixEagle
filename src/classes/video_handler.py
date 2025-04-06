import cv2
import time
import logging
from collections import deque
from classes.parameters import Parameters

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class VideoHandler:
    """
    Handles video input from various sources (video files, USB cameras, RTSP streams, UDP, HTTP, and CSI cameras).
    Provides a mechanism to store a recent history of frames.
    
    Supported VIDEO_SOURCE_TYPE values:
      - "VIDEO_FILE": Reads from a video file.
      - "USB_CAMERA": Reads from a USB camera.
      - "RTSP_OPENCV": Reads from an RTSP stream using OpenCV's default backend.
      - "RTSP_GSTREAMER": Reads from an RTSP stream using a custom GStreamer pipeline.
      - "UDP_STREAM": Reads from a UDP stream.
      - "HTTP_STREAM": Reads from an HTTP stream.
      - "CSI_CAMERA": Reads from a CSI camera using a GStreamer pipeline.
    """

    def __init__(self):
        """
        Initializes the video source based on the configuration from Parameters.
        Also initializes frame history and computes frame delay based on the stream's FPS.
        """
        self.cap = None  # OpenCV VideoCapture object
        self.frame_history = deque(maxlen=Parameters.STORE_LAST_FRAMES)  # Frame history storage
        self.width = None   # Video frame width
        self.height = None  # Video frame height
        self.delay_frame = self.init_video_source()  # Frame delay in milliseconds

        # Current frames for processing and streaming
        self.current_raw_frame = None
        self.current_osd_frame = None

        # Resized versions for streaming
        self.current_resized_raw_frame = None
        self.current_resized_osd_frame = None

    def gstreamer_pipeline_csi(self, sensor_id=0, capture_width=1280, capture_height=720,
                               framerate=30, flip_method=0):
        """
        Constructs a GStreamer pipeline string for a CSI camera.
        
        Returns:
            str: A GStreamer pipeline for CSI camera input.
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
        logger.debug(f"Constructed CSI GStreamer pipeline: {pipeline}")
        return pipeline

    def rtsp_gstreamer_pipeline(self, rtsp_url, latency=1000):
        """
        Constructs a GStreamer pipeline string for an RTSP stream using the GStreamer backend.
        
        Args:
            rtsp_url (str): The RTSP stream URL.
            latency (int): Latency in milliseconds to control buffering.
            
        Returns:
            str: A GStreamer pipeline for RTSP input.
        """
        pipeline = (
        f"rtspsrc location={rtsp_url} latency={latency} ! "
        "rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! appsink"
        )
        logger.debug(f"Constructed RTSP GStreamer pipeline: {pipeline}")
        return pipeline

    def init_video_source(self, max_retries=5, retry_delay=1):
        """
        Initializes the video source based on VIDEO_SOURCE_TYPE from Parameters.
        Retries opening the video source up to max_retries if needed.
        
        Returns:
            int: Frame delay (ms) computed from FPS.
        
        Raises:
            ValueError: If the video source cannot be opened after the maximum retries.
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
                logger.error(f"Exception while opening video source: {e}")
            time.sleep(retry_delay)
        else:
            raise ValueError("Could not open video source after max retries.")

        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self.cap.get(cv2.CAP_PROP_FPS) or Parameters.DEFAULT_FPS
        delay_frame = max(int(1000 / fps), 1)
        logger.debug(f"Video source properties - Width: {self.width}, Height: {self.height}, FPS: {fps}")
        return delay_frame

    def _create_capture_object(self):
        """
        Creates and returns a cv2.VideoCapture object based on the VIDEO_SOURCE_TYPE.
        
        Returns:
            cv2.VideoCapture: The initialized video capture object.
        
        Raises:
            ValueError: If an unsupported VIDEO_SOURCE_TYPE is specified.
        """
        source_initializers = {
            "VIDEO_FILE": lambda: cv2.VideoCapture(Parameters.VIDEO_FILE_PATH),
            "USB_CAMERA": lambda: cv2.VideoCapture(Parameters.CAMERA_INDEX),
            "RTSP_OPENCV": lambda: cv2.VideoCapture(Parameters.RTSP_URL),
            "RTSP_GSTREAMER": lambda: cv2.VideoCapture(
                self.rtsp_gstreamer_pipeline(Parameters.RTSP_URL, latency=Parameters.RTSP_LATENCY),
                cv2.CAP_GSTREAMER
            ),
            "UDP_STREAM": lambda: cv2.VideoCapture(Parameters.UDP_URL, cv2.CAP_FFMPEG),
            "HTTP_STREAM": lambda: cv2.VideoCapture(Parameters.HTTP_URL),
            "CSI_CAMERA": lambda: cv2.VideoCapture(
                self.gstreamer_pipeline_csi(
                    sensor_id=Parameters.CSI_SENSOR_ID,
                    capture_width=Parameters.CSI_WIDTH,
                    capture_height=Parameters.CSI_HEIGHT,
                    framerate=Parameters.CSI_FRAMERATE,
                    flip_method=Parameters.CSI_FLIP_METHOD,
                ),
                cv2.CAP_GSTREAMER
            ),
        }
        if Parameters.VIDEO_SOURCE_TYPE not in source_initializers:
            raise ValueError(f"Unsupported video source type: {Parameters.VIDEO_SOURCE_TYPE}")
        logger.debug(f"Initializing video source: {Parameters.VIDEO_SOURCE_TYPE}")
        return source_initializers[Parameters.VIDEO_SOURCE_TYPE]()

    def get_frame(self):
        """
        Reads and returns the next frame from the video source.
        Also stores the frame in the history.
        
        Returns:
            np.ndarray or None: The captured frame or None if reading fails.
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
        Returns:
            list: A list of the most recent frames stored in history.
        """
        return list(self.frame_history)

    def clear_frame_history(self):
        """Clears the stored frame history."""
        self.frame_history.clear()

    def update_resized_frames(self, width, height):
        """
        Resizes the raw and OSD frames for streaming.
        
        Args:
            width (int): The target width.
            height (int): The target height.
        """
        # Resize raw frame
        if self.current_raw_frame is not None:
            try:
                self.current_resized_raw_frame = cv2.resize(self.current_raw_frame, (width, height))
            except Exception as e:
                logger.error(f"Error resizing raw frame: {e}")
                self.current_resized_raw_frame = None
        else:
            self.current_resized_raw_frame = None

        # Resize OSD frame
        if self.current_osd_frame is not None:
            try:
                self.current_resized_osd_frame = cv2.resize(self.current_osd_frame, (width, height))
            except Exception as e:
                logger.error(f"Error resizing OSD frame: {e}")
                self.current_resized_osd_frame = None
        else:
            self.current_resized_osd_frame = None

    def release(self):
        """
        Releases the video capture object and any associated resources.
        """
        if self.cap:
            self.cap.release()
            logger.debug("Video source released.")

    def test_video_feed(self):
        """
        Displays the video feed in a window for testing purposes.
        Press 'q' to exit the test.
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
