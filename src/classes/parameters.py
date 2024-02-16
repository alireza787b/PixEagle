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
    VIDEO_SOURCE_IDENTIFIER = "../resources/test1.mp4"

    # Specify how many recent frames the VideoHandler should store.
    STORE_LAST_FRAMES = 5 


    # ----- Tracking Configuration -----
    # Specifies the default algorithm to use for tracking. This can be easily changed to support
    # different tracking needs or to experiment with algorithm performance.
    # Future expansions might include custom algorithms or integrating machine learning models.
    DEFAULT_TRACKING_ALGORITHM = "CSRT"
    # Additional parameters specific to tracking algorithms can be added here. For example,
    # algorithm-specific thresholds, feature selectors, etc. This provides a centralized
    # location to tune tracking behavior.
    TRACKING_PARAMETERS = {
        "CSRT": {"padding": 0.5, "multichannel": True},
        "KCF": {"fixed_window": True, "multiscale": True},
        # Additional algorithm-specific parameters can be defined here.
    }

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
