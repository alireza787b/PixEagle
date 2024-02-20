# src/classes/parameters.py

class Parameters:
    """
    Central configuration class for the PixEagle project.
    Contains settings for video sources, tracking algorithms, application behavior,
    and debugging options. Designed for easy expansion to accommodate new features.
    """

    # ----- Video Source Configuration -----
    # Defines the type of video source to be used. Options include "VIDEO_FILE", "USB_CAMERA", "RTSP_STREAM".
    # Future expansions might include "HTTP_STREAM", "UDP_STREAM", etc.
    VIDEO_SOURCE_TYPE = "VIDEO_FILE"
    # Identifier for the video source. This could be a path to a video file,
    # an integer for a USB camera index, or a URL for a video stream.
    VIDEO_SOURCE_IDENTIFIER = "resources/test1.mp4"
    #VIDEO_SOURCE_IDENTIFIER = 0

    # Default frame rate (FPS) used when automatic detection fails or isn't applicable
    DEFAULT_FPS = 30  # Adjust this based on your typical video source or application requirements  

    # Specify how many recent frames the VideoHandler should store.
    STORE_LAST_FRAMES = 5 
    
    USE_ESTIMATOR = False  # Toggle to enable/disable the position estimator
    ESTIMATOR_HISTORY_LENGTH = 5  # Number of past estimations to store


    # Segmentation parameters
    SEGMENTATION_ALGORITHMS = ["GrabCut", "Watershed",'yolov8s-seg','yolov8n-oiv7','yolov8s-obb']  # Example: Extend with more algorithms as needed
    DEFAULT_SEGMENTATION_ALGORITHM = "yolov8n-oiv7"


    # ----- Detector Configuration -----
    # Toggle to enable/disable the feature detection and smart re-detection
    USE_DETECTOR = True
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
    # PARTICLE_FILTER , CSRT
    

    
    USE_SEGMENTATION_FOR_TRACKING = True  # True to use segmentation on manual selection, False to use manual selection directly

    
    CENTER_HISTORY_LENGTH = 10  # Number of past center points to store


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

    # ----- Future Expansion -----
    # Placeholder for future parameters. This section can be used to outline planned expansions,
    # such as new video stream types, integration with additional hardware, or advanced tracking features.
    # FUTURE_PARAMETER = "value"
