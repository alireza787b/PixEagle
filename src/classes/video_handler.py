import cv2
import time
import threading
import logging

class VideoHandler:
    """Handles video capture from various sources (USB camera, CSI camera, RTSP/UDP stream, or file) with GStreamer for efficiency."""
    def __init__(self, source, width=None, height=None):
        """
        Initialize the VideoHandler.
        :param source: Video source (int for webcam, string for file/URL).
        :param width: Desired width (if applicable).
        :param height: Desired height (if applicable).
        """
        self.source = source
        self.width = width
        self.height = height
        self.capture = None
        self.running = False
        self.thread = None
        self.last_frame = None
        self.lock = threading.Lock()
        self.source_type = None  # "camera", "network", or "file"
        self._reconnect_attempts = 0

    def _build_pipeline(self):
        """Build a GStreamer pipeline string for the given source if needed."""
        # Determine source type
        src = self.source
        pipeline = None
        if isinstance(src, int) or src.isdigit():
            # USB/CSI camera (by index)
            self.source_type = "camera"
            index = int(src)
            # Use v4l2 backend via OpenCV directly (we can still set properties later)
            return None  # indicate we will use direct index (OpenCV will choose backend)
        if isinstance(src, str):
            # Check if file path
            if not src.startswith(("rtsp://", "http://", "https://", "udp://")):
                # Likely a file path
                self.source_type = "file"
                # GStreamer pipeline for file (if GStreamer is desired for hardware accel)
                # We use decodebin for simplicity; for heavy files, hardware decode could be inserted.
                pipeline = f"filesrc location=\"{src}\" ! decodebin ! videoconvert"
            else:
                # Network stream (RTSP/HTTP/UDP)
                self.source_type = "network"
                if src.startswith("rtsp://"):
                    # RTSP stream pipeline
                    # latency=0 (or a low value) to minimize internal buffering on rtspsrc
                    pipeline = f"rtspsrc location=\"{src}\" latency=0 ! decodebin ! videoconvert"
                elif src.startswith("udp://"):
                    # UDP stream (assuming RTP payload, e.g., from another GStreamer)
                    # Note: adjust caps depay if needed for different codec, here assuming H264 over RTP.
                    pipeline = f"udpsrc uri=\"{src}\" ! application/x-rtp, encoding-name=H264 ! rtph264depay ! h264parse ! v4l2h264dec ! videoconvert"
                else:
                    # HTTP or other network stream that might be MJPEG, etc.
                    pipeline = f"souphttpsrc location=\"{src}\" ! decodebin ! videoconvert"
            # After videoconvert, add appsink with appropriate properties
            pipeline += " ! appsink max-buffers=1 drop=true sync=false"
        return pipeline

    def start(self):
        """Start video capture in a separate thread."""
        pipeline = self._build_pipeline()
        if pipeline is None:
            # OpenCV direct capture (camera)
            try:
                # Use cv2.CAP_V4L2 to ensure V4L2 backend for cameras
                self.capture = cv2.VideoCapture(int(self.source), cv2.CAP_V4L2)
            except Exception as e:
                logging.error(f"Failed to open camera {self.source}: {e}")
                raise
            # Set resolution if specified
            if self.width and self.height:
                self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            # Try to set minimal buffering (if supported)
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            # Open with GStreamer pipeline
            logging.info(f"Opening video source with GStreamer pipeline: {pipeline}")
            # Note: CAP_GSTREAMER is needed to interpret the pipeline string
            self.capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self.capture or not self.capture.isOpened():
            logging.error("Unable to open video source.")
            raise RuntimeError("Could not open video source.")
        self.running = True
        # Start the capture thread
        self.thread = threading.Thread(target=self._capture_loop, name="VideoCaptureThread", daemon=True)
        self.thread.start()
        logging.info("VideoHandler thread started for source: %s", self.source)
        return self

    def _capture_loop(self):
        """Background thread function to continuously capture frames."""
        # If the source is a live camera/stream, we want to continuously grab frames.
        # For files, we still loop but will break when file ends.
        while self.running:
            ret, frame = self.capture.read()
            if not ret or frame is None:
                # If we reach here, either the source ended or an error occurred.
                if self.source_type == "file":
                    logging.info("Video file has ended.")
                    break  # end of video file
                elif self.source_type == "network":
                    logging.warning("Lost connection to network stream. Attempting to reconnect...")
                    # Attempt simple reconnection logic for network streams
                    self._reconnect_attempts += 1
                    self.capture.release()
                    time.sleep(1)  # brief pause before reconnect
                    if self._reconnect_attempts <= 3:  # try a few times
                        try:
                            # Rebuild and reopen pipeline
                            pipeline = self._build_pipeline()
                            self.capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                            if self.capture.isOpened():
                                logging.info("Reconnected to network stream.")
                                continue  # go back to reading frames
                        except Exception as e:
                            logging.error(f"Reconnection attempt failed: {e}")
                    logging.error("Failed to reconnect after multiple attempts, stopping capture.")
                    break
                else:
                    # For USB/CSI cameras, breaking on failure (could also attempt reopen if needed)
                    logging.error("Camera capture returned no frame. Stopping capture thread.")
                    break
            self._reconnect_attempts = 0  # reset on successful read
            # Store the frame in a thread-safe way
            with self.lock:
                # If desired, we could downscale frame here for processing to save CPU (e.g., cv2.resize).
                self.last_frame = frame
        # Release capture and signal that we are no longer running
        if self.capture:
            self.capture.release()
        self.running = False
        logging.info("VideoHandler thread ending for source: %s", self.source)

    def get_frame(self):
        """
        Get the latest captured frame (thread-safe).
        :return: The newest frame as a NumPy array (or None if no frame available).
        """
        with self.lock:
            if self.last_frame is not None:
                # Return a copy to avoid issues if the capture thread overwrites the buffer
                return self.last_frame.copy()
            else:
                return None

    def stop(self):
        """Stop the video capture thread."""
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        self.thread = None
        self.last_frame = None
        logging.info("VideoHandler stopped.")

class FlowController:
    """Manages the flow of frames from VideoHandler through the processing pipeline in a separate thread for real-time performance."""
    def __init__(self, video_handler, processor=None):
        """
        :param video_handler: An instance of VideoHandler (already started).
        :param processor: Optional function or callable to process frames. If None, a default pass-through is used.
        """
        self.video_handler = video_handler
        self.processor = processor if processor is not None else self.default_processor
        self.running = False
        self.thread = None

    def default_processor(self, frame):
        """
        Default frame processing (can be replaced with actual image processing algorithm).
        For demonstration, we convert the frame to grayscale.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # (Additional processing like detection or tracking would go here)
        return gray

    def _process_loop(self):
        """Background thread that fetches frames and processes them."""
        logging.info("Processing thread started.")
        while self.running:
            # Retrieve the latest frame from the VideoHandler
            frame = self.video_handler.get_frame()
            if frame is None:
                # No frame available at the moment; small sleep to avoid busy-wait
                if not self.video_handler.running:
                    # VideoHandler has stopped (e.g., source ended), so exit loop
                    break
                time.sleep(0.01)
                continue
            # Process the frame (this could be time-consuming)
            processed = None
            try:
                processed = self.processor(frame)
            except Exception as e:
                logging.error(f"Error during frame processing: {e}", exc_info=True)
            # (If there is an output module, it could receive the `processed` frame here.
            # For example, we could display the frame or send it over a network.)
            # In this example, we won't display to keep things headless and efficient.
            # We can simulate a brief output delay if needed or simply omit it.
            # Optionally, one could add cv2.imshow here (in main thread ideally) or send to another thread.
        logging.info("Processing thread ending.")

    def start(self):
        """Start the processing loop in a separate thread."""
        if not self.video_handler or not self.video_handler.running:
            raise RuntimeError("VideoHandler must be running before starting FlowController.")
        self.running = True
        self.thread = threading.Thread(target=self._process_loop, name="ProcessingThread", daemon=True)
        self.thread.start()
        return self

    def stop(self):
        """Stop processing loop."""
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        self.thread = None
        logging.info("FlowController stopped.")

class AppController:
    """High-level controller for the Pixeagle application, managing the VideoHandler and FlowController."""
    def __init__(self, source, width=None, height=None, processor=None):
        """
        :param source: Video source (camera index, file path, or URL).
        :param width, height: Optional resolution for the video source.
        :param processor: Optional custom processor function for frames.
        """
        self.source = source
        self.width = width
        self.height = height
        self.processor = processor
        self.video_handler = None
        self.flow_controller = None

    def start(self):
        """Start the video capture and processing."""
        logging.info("Starting Pixeagle system with source: %s", self.source)
        # Configure logging level and format (could be made configurable)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        # Initialize and start video handling
        self.video_handler = VideoHandler(self.source, self.width, self.height)
        self.video_handler.start()
        # Initialize and start processing flow
        self.flow_controller = FlowController(self.video_handler, processor=self.processor)
        self.flow_controller.start()
        logging.info("Pixeagle processing started.")
        return self

    def stop(self):
        """Stop the processing and video capture."""
        logging.info("Stopping Pixeagle system.")
        if self.flow_controller:
            self.flow_controller.stop()
        if self.video_handler:
            self.video_handler.stop()
        logging.info("Pixeagle system stopped.")

# Example usage (would typically be in a main guard or separate script):
# if __name__ == "__main__":
#     app = AppController(source="rtsp://192.168.0.100:554/stream1", width=1280, height=720)
#     app.start()
#     try:
#         while True:
#             time.sleep(1)  # Keep main thread alive while background threads run
#     except KeyboardInterrupt:
#         app.stop()
