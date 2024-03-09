# src/classes/parameters.py

class Parameters:
    """
    Central configuration class for the PixEagle project.
    Contains settings for video sources, tracking algorithms, application behavior,
    and debugging options. Designed for easy expansion to accommodate new features.
    """

    # ----- Video Source Configuration -----
    VIDEO_SOURCE_TYPE = "VIDEO_FILE"  # Options: "VIDEO_FILE", "USB_CAMERA", "RTSP_STREAM", "UDP_STREAM", "HTTP_STREAM"

    # For VIDEO_FILE, specify the path to the video file
    # Example: VIDEO_FILE_PATH = "resources/test1.mp4"
    VIDEO_FILE_PATH = "resources/test1.mp4"

    # For USB_CAMERA, specify the camera index as an integer
    # Example: CAMERA_INDEX = 0 for the default webcam
    CAMERA_INDEX = 0

    # For RTSP_STREAM, specify the RTSP URL as a string
    # Example: RTSP_URL = "rtsp://username:password@ip_address:port/stream"
    RTSP_URL = ""
    
    # For UDP_STREAM, specify the UDP URL or endpoint as a string
    # Example: UDP_URL = "udp://@IP_ADDRESS:PORT"
    UDP_URL = "udp://172.21.144.1:12345"


    # For HTTP_STREAM, specify the HTTP URL for the MJPEG stream as a string
    # Example: HTTP_URL = "http://IP_ADDRESS:PORT/stream"
    # I used MJPEG Streamer downloaded from microsoft app store
    # HTTP localhost loopback doesnt work!
    HTTP_URL = "http://172.21.144.1:8100"



    FRAME_TITLE = "Video"

    # Default frame rate (FPS) used when automatic detection fails or isn't applicable
    DEFAULT_FPS = 30  # Adjust this based on your typical video source or application requirements  

    # Specify how many recent frames the VideoHandler should store.
    STORE_LAST_FRAMES = 5 
    
    USE_ESTIMATOR = False  # Toggle to enable/disable the position estimator
    ESTIMATOR_HISTORY_LENGTH = 5  # Number of past estimations to store


    # Segmentation parameters
    SEGMENTATION_ALGORITHMS = ["GrabCut", "Watershed",'yolov8s-seg','yolov8n-oiv7','yolov8s-obb']  # Example: Extend with more algorithms as needed
    DEFAULT_SEGMENTATION_ALGORITHM = "yolo/yolov8n-oiv7"


    # ----- Detector Configuration -----
    # Toggle to enable/disable the feature detection and smart re-detection
    USE_DETECTOR = True
    
    AUTO_REDETECT = True
    
    
    #Add a new parameter for the detection algorithm
    DETECTION_ALGORITHM = "TemplateMatching"  # Default to FeatureMatching. Change to "TemplateMatching" as needed.
    
    # Parameters specific to Template Matching (if any)
    # For example, the template matching method
    TEMPLATE_MATCHING_METHOD = "TM_CCOEFF_NORMED"
    
    # Specifies the default algorithm to use for feature detection.
    DEFAULT_FEATURE_EXTRACTION_ALGORITHM = "ORB"
    # Minimum number of good matches required for smart re-detection to be considered successful
    MIN_MATCH_COUNT = 10
    
    ORB_FLENN_TRESH = 0.8
    
    # Feature extraction parameters for ORB or any other algorithms you plan to use
    ORB_FEATURES = 2000  # Example: Number of features to extract with ORB
    # FLANN matcher parameters for feature matching in smart re-detection
    FLANN_INDEX_LSH = 6
    FLANN_TABLE_NUMBER = 6  # Example: LSH table number
    FLANN_KEY_SIZE = 12  # Example: Size of the key in LSH
    FLANN_MULTI_PROBE_LEVEL = 1  # Example: Multi-probe level in LSH (0 is exact search)
    FLANN_SEARCH_PARAMS = {"checks": 50}  # Search parameters for FLANN

    # Template Matching Method Name
    TEMPLATE_MATCHING_METHOD = "TM_CCOEFF_NORMED"

    # ----- Tracking Configuration -----
    # Specifies the default algorithm to use for tracking. This can be easily changed to support
    # different tracking needs or to experiment with algorithm performance.
    # Future expansions might include custom algorithms or integrating machine learning models.
    DEFAULT_TRACKING_ALGORITHM = "CSRT"
    # PFT , CSRT
    # Color of the tracking rectangle (B, G, R format)
    TRACKING_RECTANGLE_COLOR = (255, 0, 0)  # Blue color for the bounding box
    
    # Color of the center circle (B, G, R format)
    CENTER_CIRCLE_COLOR = (0, 255, 0)  # Green color for the center point

    
    USE_SEGMENTATION_FOR_TRACKING = True  # True to use segmentation on manual selection, False to use manual selection directly

    
    CENTER_HISTORY_LENGTH = 10  # Number of past center points to store

    PARTICLE_FILTER_NUM_PARTICLES = 200  # Number of particles used in the filter
    PARTICLE_FILTER_SIMILARITY_MEASURE = "MSE_color"  # The similarity measure used for comparing particles to the target
    PARTICLE_FILTER_SIGMA = 5  # Sigma value used in the similarity calculation to control sensitivity
    PARTICLE_FILTER_SIGMA_MOVE_NEAR = 15  # Standard deviation of movement for particles close to the target
    PARTICLE_FILTER_SIGMA_MOVE_FAR = 30  # Standard deviation of movement for particles far from the target
    PARTICLE_FILTER_SIGMA_RATIO = 0.5  # Ratio of particles considered 'near' to the target

    # ----- Application Behavior -----
    # Determines how the Region of Interest (ROI) is selected. Options are "MANUAL" for user selection,
    # and "AUTO" for automatic detection (which might be implemented in future versions).
    ROI_SELECTION_MODE = "MANUAL"
    # Defines whether the tracking window and other visual feedback should be displayed.
    # Useful for debugging or demonstration purposes.
    SHOW_TRACKING_WINDOW = True
    # Determines whether deviations from the center or other metrics should be displayed.
    # This can be expanded to include more complex metrics as the project evolves.
    DISPLAY_DEVIATIONS = True

    # ----- Debugging and Logging -----
    # Enables verbose logging for debugging purposes. This might include detailed logs on
    # tracking performance, errors, or system metrics.
    ENABLE_DEBUGGING = True
    # Path to save log files. This provides a centralized location for log storage, making
    # it easier to review system behavior or diagnose issues.
    LOG_FILE_PATH = "logs/tracking_log.txt"


    # System connection configuration
    SYSTEM_ADDRESS = "udp://:14540"

    # PID gains for X, Y, and Z axes
    PID_GAINS = {
        "x": {"p": 1, "i": 0.1, "d": 0.05},
        "y": {"p": 1, "i": 0.1, "d": 0.05},
        "z": {"p": 1, "i": 0.1, "d": 0.05}
    }

    # Rate of descent and minimum descent height
    RATE_OF_DESCENT = 0.5  # Negative for descending
    MIN_DESCENT_HEIGHT = 4  # Meters


    CAMERA_YAW_OFFSET = 0
    
    SETPOINT_PUBLISH_RATE_S = 0.1
    ENABLE_SETPOINT_DEBUGGING = True
    # ----- Future Expansion -----
    # Placeholder for future parameters. This section can be used to outline planned expansions,
    # such as new video stream types, integration with additional hardware, or advanced tracking features.
    # FUTURE_PARAMETER = "value"
