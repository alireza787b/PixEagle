# src/classes/parameters.py

class Parameters:
    """
    Central configuration class for the PixEagle project.
    Contains settings for video sources, tracking algorithms, application behavior,
    and debugging options. Designed for easy expansion to accommodate new features.

    
    """

    # ----- Video Source Configuration -----
    VIDEO_SOURCE_TYPE = "CSI_CAMERA"  # Options: "VIDEO_FILE", "USB_CAMERA", "RTSP_STREAM", "UDP_STREAM", "HTTP_STREAM", "CSI_CAMERA"
    # Not all methods tested yet.

    # For VIDEO_FILE, specify the path to the video file
    # Example: VIDEO_FILE_PATH = "resources/test1.mp4"
    VIDEO_FILE_PATH = "resources/test7.mp4"

    # For USB_CAMERA, specify the camera index as an integer
    # Example: CAMERA_INDEX = 0 for the default webcam
    CAMERA_INDEX = 1

    # For RTSP_STREAM, specify the RTSP URL as a string
    # Example: RTSP_URL = "rtsp://username:password@ip_address:port/stream"
    RTSP_URL = "rtsp://172.21.144.1:8554"
    
    # For UDP_STREAM, specify the UDP URL or endpoint as a string
    # Example: UDP_URL = "udp://@IP_ADDRESS:PORT"
    UDP_URL = "udp://172.21.144.1:5000"

    # For HTTP_STREAM, specify the HTTP URL for the MJPEG stream as a string
    # Example: HTTP_URL = "http://IP_ADDRESS:PORT/stream"
    # I used MJPEG Streamer downloaded from microsoft app store
    # HTTP localhost loopback doesnt work!
    HTTP_URL = "http://172.21.144.1:8100"

    # For CSI_CAMERA, specify the sensor ID (usually 0 or 1)
    # For CSI Camera, ensure OpenCV is built with GStreamer support.
    # If issues arise, check `test_Ver.py` to verify GStreamer is enabled in OpenCV.
    CSI_SENSOR_ID = 0

    # For CSI_CAMERA, specify the sensor ID (usually 0 or 1)
    CSI_SENSOR_ID = 0

    # Additional Parameters
    STORE_LAST_FRAMES = 100
    DEFAULT_FPS = 30
    CSI_WIDTH = 1280
    CSI_HEIGHT = 720
    CSI_FRAMERATE = 30
    CSI_FLIP_METHOD = 0

  


    # ----- Telemetry and Streaming Configuration -----
    ENABLE_TELEMETRY = True
    TELEMETRY_SEND_RATE = 2  # Hz
    TELEMETRY_FLASK_ENDPOINT = '/telemetry'
    
    ENABLE_UDP_STREAM = False
    UDP_HOST = '127.0.0.1'
    UDP_PORT = 5550
    
    WEBSOCK_HOST = '127.0.0.1'
    WEBSOCK_PORT = 5551
    
    ENABLE_FOLLOWER_TELEMETRY = True

    ENABLE_STREAMING = True
    HTTP_STREAM_HOST = '0.0.0.0'
    HTTP_STREAM_PORT = 5077
    STREAM_WIDTH = 640
    STREAM_HEIGHT = 480
    STREAM_QUALITY = 80  # JPEG quality 0-100
    STREAM_FPS = 30  # target FPS
    STREAM_PROCESSED_OSD = True

    # ----- PX4 MAVSDK Configuration -----
    EXTERNAL_MAVSDK_SERVER = True       # If we are working on Windows (or need to load mavsdk_server manually), we should handle the MAVSDK Server Differently in PX4 Controller Class
    SYSTEM_ADDRESS = "udp://172.21.148.30:14540"

    # ----- Frame and Estimation Configuration -----
    FRAME_TITLE = "Video"
    DEFAULT_FPS = 30  # Default frame rate (FPS)
    STORE_LAST_FRAMES = 5  # Number of recent frames to store
    USE_ESTIMATOR = False  # Enable/disable the position estimator
    ESTIMATOR_HISTORY_LENGTH = 5  # Number of past estimations to store
    SHOW_VIDEO_WINDOW = True # If using headless or with React web-app you wont need this window anymore

    # ----- Segmentation Configuration -----
    SEGMENTATION_ALGORITHMS = ["GrabCut", "Watershed", 'yolov8s-seg', 'yolov8n-oiv7', 'yolov8s-obb']
    DEFAULT_SEGMENTATION_ALGORITHM = "yolo/yolov8n-oiv7"
    USE_SEGMENTATION_FOR_TRACKING = True  # Use segmentation on manual selection

    # ----- Detector Configuration -----
    USE_DETECTOR = True  # Enable/disable feature detection and smart re-detection
    AUTO_REDETECT = True  # Enable automatic re-detection
    DETECTION_ALGORITHM = "TemplateMatching"  # Default detection algorithm
    TEMPLATE_MATCHING_METHOD = "TM_CCOEFF_NORMED"  # Template matching method
    DEFAULT_FEATURE_EXTRACTION_ALGORITHM = "ORB"  # Default feature extraction algorithm
    MIN_MATCH_COUNT = 10  # Minimum number of good matches for re-detection
    ORB_FLENN_TRESH = 0.8  # ORB FLENN threshold
    ORB_FEATURES = 2000  # Number of features to extract with ORB
    FLANN_INDEX_LSH = 6  # FLANN matcher parameters
    FLANN_TABLE_NUMBER = 6
    FLANN_KEY_SIZE = 12
    FLANN_MULTI_PROBE_LEVEL = 1
    FLANN_SEARCH_PARAMS = {"checks": 50}

    # ----- Tracking Configuration -----
    DEFAULT_TRACKING_ALGORITHM = "CSRT"  # Default tracking algorithm
    TRACKING_RECTANGLE_COLOR = (255, 0, 0)  # Blue color for the bounding box
    CENTER_CIRCLE_COLOR = (0, 255, 0)  # Green color for the center point
    CENTER_HISTORY_LENGTH = 10  # Number of past center points to store
    PARTICLE_FILTER_NUM_PARTICLES = 200  # Number of particles in the filter
    PARTICLE_FILTER_SIMILARITY_MEASURE = "MSE_color"  # Similarity measure for particles
    PARTICLE_FILTER_SIGMA = 5  # Sigma value for similarity calculation
    PARTICLE_FILTER_SIGMA_MOVE_NEAR = 15  # Standard deviation of movement for near particles
    PARTICLE_FILTER_SIGMA_MOVE_FAR = 30  # Standard deviation of movement for far particles
    PARTICLE_FILTER_SIGMA_RATIO = 0.5  # Ratio of particles considered 'near' to the target

    # ----- Follower Configuration -----
    # General settings
    ROI_SELECTION_MODE = "MANUAL"  # ROI selection mode
    SHOW_TRACKING_WINDOW = True  # Show tracking window
    DISPLAY_DEVIATIONS = False  # Display deviations
    TRACKED_BBOX_STYLE = 'fancy'  # Options: 'normal', 'fancy'
    FOLLOWER_MODE = 'ground_view'  # 'ground_view' or 'front_view'
    DEFAULT_DISTANCE = 200  # Default distance for calculations
    CONTROL_STRATEGY = 'constant_altitude'  # 'constant_altitude' or 'constant_distance'
    # If the target moves vertically in the frame, adjust using altitude or distance
    # 'constant_altitude': Adjust altitude to keep target at desired vertical position in frame.
    # 'constant_distance': Adjust forward/backward distance to keep target at desired vertical position in frame.
    TARGET_POSITION_MODE = 'center'  # 'center' or 'initial'


    # Control and PID parameters
    """
    PID_GAINS (dict): Contains the PID gains for each control axis. The PID controller helps
            to minimize the error between the current state and the desired setpoint. Adjustments to these
            gains can be made based on the drone's response during flight tests.

            - Proportional (P) Gain: Determines how aggressively the PID reacts to the current error. Increasing
              this value will make the drone respond more quickly to errors, but too high a value can lead to
              oscillations and instability.
            
            - Integral (I) Gain: Addresses the cumulative error in the system, helping to eliminate steady-state
              errors. Adjusting this gain helps when the drone fails to reach the setpoint, but too much can
              lead to overshooting and oscillations.
            
            - Derivative (D) Gain: Reacts to the rate of change of the error, providing a damping effect.
              Increasing this gain helps to reduce overshooting and settling time, improving the stability.

        Example usage:
            To increase responsiveness, consider increasing the 'P' gain, but monitor for instability.
            If the drone consistently overshoots the target, increase the 'D' gain for better damping.
            If there is a persistent offset that never corrects itself, increase the 'I' gain slightly.
    """
    PID_GAINS = {
        "x": {"p": 6, "i": 0.3, "d": 1.5},  
        "y": {"p": 6, "i": 0.3, "d": 1.5}, 
        "z": {"p": 1, "i": 0.01, "d": 0.01}
    }

    PROPORTIONAL_ON_MEASUREMENT = False  # Default: False, change to True to enable PoM
    """
    Proportional on Measurement (PoM) helps to reduce overshoot and improve stability in control systems by applying the proportional term based on the current measurement rather than the setpoint error.
    This method is beneficial for processes with significant delay between control action and measured effect.
    For more information, visit: http://brettbeauregard.com/blog/2017/06/introducing-proportional-on-measurement/
    """
    
    ENABLE_ANTI_WINDUP = True  # Set to True to enable anti-windup, False to disable
    ANTI_WINDUP_BACK_CALC_COEFF = 0.1  # Coefficient for back-calculation method

    # Velocity and descent limits
    VELOCITY_LIMITS = {'x': 10.0, 'y': 10.0, 'z': 5.0}  # Maximum velocity limits
    ENABLE_DESCEND_TO_TARGET = True # If True, It will Descend (or Climb) based on below parameters
    MIN_DESCENT_HEIGHT = 20  # Minimum descent height
    MAX_RATE_OF_DESCENT = 1  # Maximum rate of descent

    # Target aim configuration
    DESIRE_AIM = (0, 0)  # Desired normalized position in the camera frame
    
    # IS_CAMERA_GIMBALED (bool): Specifies if the camera is gimbaled.
    #         True if the camera has gimbal stabilization, False otherwise.
    #         If False, orientation-based adjustments are applied to compensate for pitch and roll effects.
    IS_CAMERA_GIMBALED = False  # Example: False for non-gimbaled camera setups
    
    # IS_CAMERA_GIMBALED (bool): Specifies if the camera is gimbaled.
    #         True if the camera has gimbal stabilization, False otherwise.
    #         If False, orientation-based adjustments are applied to compensate for pitch and roll effects.
    IS_CAMERA_GIMBALED = False  # Example: False for non-gimbaled camera setups


    #     BASE_ADJUSTMENT_FACTOR_X (float): Base adjustment factor for the X-axis,
    #         used to compensate for roll effects on the camera view at a reference altitude (typically ground level).
    #         This factor is inversely scaled based on altitude to adjust the perceived target position in the camera frame.
    BASE_ADJUSTMENT_FACTOR_X = 0.1  # Adjust based on experimental data


    #     BASE_ADJUSTMENT_FACTOR_Y (float): Base adjustment factor for the Y-axis,
    #         used to compensate for pitch effects on the camera view at a reference altitude.
    #         Like the X-axis factor, this is inversely scaled with altitude.
    BASE_ADJUSTMENT_FACTOR_Y = 0.1  # Adjust based on experimental data


    #     ALTITUDE_FACTOR (float): A coefficient used to scale the BASE_ADJUSTMENT_FACTORS
    #         with altitude, providing a method to diminish the adjustment impact as altitude increases.
    #         Higher values mean quicker reduction of the adjustment effect with altitude.
    ALTITUDE_FACTOR = 0.005  # This needs to be fine-tuned through testing

    # Gain scheduling configuration
    """
    Gain scheduling allows the drone control system to adapt PID gains based on the current altitude,
    ensuring optimal responsiveness and stability across different flying conditions. This approach
    compensates for variations in drone dynamics such as air density and wind effects and target tracking dynamics at different altitudes.

    The gains are scheduled in brackets that cover typical operational altitudes, with the assumption that
    control needs vary with altitude. 

    Attributes:
        ALTITUDE_GAIN_SCHEDULE (dict): A dictionary where the keys are tuples representing altitude ranges
            in meters AGL (Above Ground Level), and the values are dictionaries setting the PID gains for
            x, y, and z axes.
        ENABLE_GAIN_SCHEDULING (bool): Flag to enable or disable gain scheduling.
        GAIN_SCHEDULING_PARAMETER (str): The parameter used by the scheduling function to determine
            which gain set to apply, typically 'current_altitude'.
    """
    ALTITUDE_GAIN_SCHEDULE = {
        (0, 20): {"x": {"p": 5.5, "i": 0.2, "d": 0.4}, "y": {"p": 5.5, "i": 0.2, "d": 0.4}, "z": {"p": 1, "i": 0.01, "d": 0.1}},
        (20, 50): {"x": {"p": 6, "i": 0.25, "d": 0.5}, "y": {"p": 6, "i": 0.25, "d": 0.5}, "z": {"p": 1, "i": 0.015, "d": 0.15}},
        (50, 100): {"x": {"p": 6.5, "i": 0.3, "d": 0.6}, "y": {"p": 6.5, "i": 0.3, "d": 0.6}, "z": {"p": 1, "i": 0.02, "d": 0.2}},
        (100, 150): {"x": {"p": 6, "i": 0.3, "d": 1.0}, "y": {"p": 6, "i": 0.3, "d": 1.0}, "z": {"p": 1, "i": 0.01, "d": 0.01}},
        (150, 200): {"x": {"p": 5.5, "i": 0.25, "d": 0.8}, "y": {"p": 5.5, "i": 0.25, "d": 0.8}, "z": {"p": 1, "i": 0.01, "d": 0.05}}
    }
    ENABLE_GAIN_SCHEDULING = False
    GAIN_SCHEDULING_PARAMETER = 'current_altitude' # better to change it to distance and implement it for front view tracking

    # Camera and setpoint configurations
    CAMERA_YAW_OFFSET = 0
    SETPOINT_PUBLISH_RATE_S = 0.1
    ENABLE_SETPOINT_DEBUGGING = False

    # ----- Debugging and Logging -----
    ENABLE_DEBUGGING = True  # Enable verbose logging
    LOG_FILE_PATH = "logs/tracking_log.txt"  # Path to save log files

