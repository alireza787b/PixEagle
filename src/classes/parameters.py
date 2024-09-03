# src/classes/parameters.py
#TODO:  make a param config.ini or sth. and make this class read and intiilzied by that ini file so easily can import/expert configs

class Parameters:
    """
    Central configuration class for the PixEagle project.
    Contains settings for video sources, tracking algorithms, application behavior,
    and debugging options. Designed for easy expansion to accommodate new features.

    
    """

    # ----- Video Source Configuration -----
    VIDEO_SOURCE_TYPE = "USB_CAMERA"  # Options: "VIDEO_FILE", "USB_CAMERA", "RTSP_STREAM", "UDP_STREAM", "HTTP_STREAM", "CSI_CAMERA"
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

    # Ensure OpenCV is built with GStreamer support for efficient video processing.
    # To verify, run: python3 -c "import cv2; print(cv2.getBuildInformation())" and check for 'GStreamer' in the output.

    # CSI Camera Sensor ID
    # Typically `0` for the first camera, `1` for the second.
    CSI_SENSOR_ID = 0

    # General Parameters
    STORE_LAST_FRAMES = 100  # Number of frames to store in memory
    DEFAULT_FPS = 30  # Default frames per second for streaming and recording

    # Camera Resolution & Frame Rate
    # - Low Quality: 640x480 @ 30fps (Lower bandwidth, less CPU usage)
    # - Medium Quality: 1280x720 @ 30fps (Balanced performance)
    # - High Quality: 1920x1080 @ 30fps (Good detail, more processing required)
    # - Max Quality: 4608x2592 @ 14fps (Highest resolution, limited by hardware)
    CSI_WIDTH = 1280
    CSI_HEIGHT = 720
    CSI_FRAMERATE = 30

    # Image Orientation (Flip Method)
    # 0 - None (default), 1 - Rotate 90° CW, 2 - Upside Down, 3 - Rotate 90° CCW, etc.
    CSI_FLIP_METHOD = 0

    # Quick Setup Examples:
    # - Low Quality: 
    #   CSI_WIDTH = 640, CSI_HEIGHT = 480, CSI_FRAMERATE = 30, CSI_FLIP_METHOD = 0
    # - High Quality: 
    #   CSI_WIDTH = 1920, CSI_HEIGHT = 1080, CSI_FRAMERATE = 30, CSI_FLIP_METHOD = 0
    # - Max Quality: 
    #   CSI_WIDTH = 4608, CSI_HEIGHT = 2592, CSI_FRAMERATE = 14, CSI_FLIP_METHOD = 0


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
    STREAM_WIDTH = 1920
    STREAM_HEIGHT = 1080
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
    USE_MAVLINK2REST = False     # Enable or disable MAVLink2Rest usage, If set to False will keep using mavsdk for telemtery receiving
    FOLLOWER_DATA_REFRESH_RATE = 2
    ROI_SELECTION_MODE = "MANUAL"  # ROI selection mode
    SHOW_TRACKING_WINDOW = True  # Show tracking window
    DISPLAY_DEVIATIONS = False  # Display deviations
    TRACKED_BBOX_STYLE = 'fancy'  # Options: 'normal', 'fancy'
    FOLLOWER_MODE = 'chase_follower'  # Options: Down Looking Camera: ['ground_view'], Front View Camera: ['constant_distance', 'constant_position', 'chase_follower']
    ENABLE_ALTITUDE_CONTROL = True  # Set to True if altitude control is needed in 'constant_position' mode


    TARGET_POSITION_MODE = 'center'  # 'center' or 'initial'


    # ---- Yaw Control Parameters only for front view target follower ----
    
    ENABLE_YAW_CONTROL = False
    # Enable or disable yaw control. Set to False if yaw control is not needed. (Only for Constant Distance Mode)
    
    # Yaw control parameters
    YAW_CONTROL_THRESHOLD = 0.3  # Threshold to start applying yaw control based on error
    
   
    
    YAW_LATERAL_BLEND_FACTOR = 0.5
    # Blending factor for yaw and lateral control. This determines how much yaw control is blended
    # with lateral movement when the target reaches the edges of the camera view. 
    # A value of 0.5 means 50% yaw control and 50% lateral control at full blending.

    YAW_DEAD_ZONE = 0.2
    # Dead zone percentage for yaw corrections. 
    # This defines a small zone around the center of the camera view where no yaw corrections are applied.
    # This helps prevent constant small adjustments when the target is only slightly off-center.
    
    # ---- Vertical Error Recalculation Parameters ----
    
    VERTICAL_RECALC_DELAY = 0.1  # seconds
    # Delay after yaw before recalculating vertical corrections. 
    # This allows the drone to stabilize after yawing before applying pitch or altitude corrections.
    
    YAW_PITCH_SYNC_FACTOR = 0.5
    # Factor that controls how aggressively pitch is adjusted after a yaw movement. 
    # A higher value means more aggressive pitch corrections. This helps keep the target centered vertically after yaw adjustments.
        
    

    ENABLE_GIMBAL_PRIORITY = True
    # Prioritize gimbal adjustments over drone yaw. If set to True and the camera is gimbaled, 
    # small orientation corrections will be handled by the gimbal instead of yawing the drone. This helps reduce unnecessary drone rotations.
    
    # ---- Adaptive Control Parameters ----
    
    ADAPTIVE_YAW_CONTROL = False
    # If enabled, thresholds and blending factors will be dynamically adjusted based on the target's speed and other environmental factors. 
    # This allows the drone to adapt to different conditions, making the tracking more robust in dynamic environments.


        # ----- Chase Follower Rate Limits Configuration -----
    # Define maximum limits for roll, pitch, yaw, and thrust in the ChaseFollower mode
    MAX_ROLL_RATE = 10.0  # Maximum roll rate in degrees per second
    MAX_PITCH_RATE = 10.0  # Maximum pitch rate in degrees per second
    MAX_YAW_RATE = 10.0  # Maximum yaw rate in degrees per second
    MAX_THRUST = 1.0  # Maximum thrust (normalized between 0 and 1)
    MIN_GROUND_SPEED = 0 # For Chase mode throttle control
    MAX_GROUND_SPEED = 20 # For Chase mode throttle control
    TARGET_SPEED = 5

    # Control and PID parameters
    """
    PID_GAINS (dict): Contains the PID gains for each control axis. The PID controller helps
            to minimize the error between the current state and the desired setpoint. Adjustments to these
            gains can be made based on the drone's response during flight tests.

            - Proportional (P) Gain: Determines how aggressively the PID reacts to the current error.
            - Integral (I) Gain: Addresses the cumulative error in the system.
            - Derivative (D) Gain: Reacts to the rate of change of the error.

        Example usage:
            Adjust 'P' gain for responsiveness, 'I' gain for steady-state error correction, 
            and 'D' gain for damping oscillations.
    """
    PID_GAINS = {
        "x": {"p": 6, "i": 0.3, "d": 1.5},  # For lateral movement
        "y": {"p": 6, "i": 0.3, "d": 1.5},  # For lateral movement
        "z": {"p": 2, "i": 0.03, "d": 0.05},  # For vertical movement (altitude)
        "roll_rate": {"p": 4, "i": 0.1, "d": 0.2},  # For controlling roll rate
        "pitch_rate": {"p": 100, "i": 2, "d": 20},  # For controlling pitch rate
        "yaw_rate": {"p": 40, "i": 8, "d": 2},  # For controlling yaw rate
        "thrust": {"p": 2, "i": 0.2, "d": 0.1},  # For controlling forward velocity via thrust
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
    ENABLE_DESCEND_TO_TARGET = False # If True, It will Descend (or Climb) based on below parameters
    MIN_DESCENT_HEIGHT = 20  # Minimum descent height
    MAX_CLIMB_HEIGHT = 100 # Maximum climb hieght
    MAX_RATE_OF_DESCENT = 2  # Maximum rate of descent
    MAX_YAW_RATE = 10  # Maximum yaw rate in degrees per second


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
    
    # ----- GStreamer Configuration -----
    ENABLE_GSTREAMER_STREAM = False  # Toggle to enable or disable GStreamer streaming
    GSTREAMER_HOST = "127.0.0.1"  # IP address of the target machine (e.g., QGroundControl)
    GSTREAMER_PORT = 2000  # Port to stream the video over UDP

    # Bitrate for the video stream in bits per second
    # Higher bitrate = better video quality but more bandwidth usage
    # Lower bitrate = worse video quality but less bandwidth usage
    GSTREAMER_BITRATE = 2000

    GSTREAMER_WIDTH = 1280
    GSTREAMER_HEIGHT = 720


    # Frame rate for the video stream
    # Higher frame rate = smoother video but more CPU/GPU usage and bandwidth
    # Lower frame rate = less smooth video but reduced CPU/GPU usage and bandwidth
    GSTREAMER_FRAMERATE = 15

    # Size of the buffer in bytes for UDP sink
    # Larger buffer = smoother streaming with more resistance to network jitter but higher latency
    # Smaller buffer = lower latency but more sensitive to network instability
    GSTREAMER_BUFFER_SIZE = 50000000

    # GStreamer encoder speed preset
    # Faster preset = lower CPU usage but potentially lower video quality
    # Slower preset = higher video quality but increased CPU usage
    GSTREAMER_SPEED_PRESET = "ultrafast"  # Options: "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"

    # Keyframe interval for H.264 encoding
    # Lower value = more frequent keyframes, better recovery from packet loss but higher bandwidth usage
    # Higher value = fewer keyframes, lower bandwidth usage but harder recovery from packet loss
    GSTREAMER_KEY_INT_MAX = 30  # I-frame every second at 30 fps

    # Tuning for the encoder
    # "zerolatency" = minimizes latency, "film" = better quality for stored video, higher latency
    GSTREAMER_TUNE = "zerolatency"  # Options: "zerolatency", "film", "grain", "stillimage", "fastdecode", "psnr", "ssim"

    # Contrast adjustment for the video stream
    # Higher contrast = more pronounced differences between light and dark areas
    # Lower contrast = more muted visual differences
    GSTREAMER_CONTRAST = 5.0  # 1.0 is default, higher values increase contrast

    # Brightness adjustment for the video stream
    # Higher brightness = lighter overall image
    # Lower brightness = darker overall image
    GSTREAMER_BRIGHTNESS = 10  # 0.0 is default, positive values increase brightness

    # Saturation adjustment for the video stream
    # Higher saturation = more vivid colors
    # Lower saturation = more muted colors
    GSTREAMER_SATURATION = 5  # 1.0 is default, higher values increase saturation


    # MAVLink Configuration
    mavlink_enabled = True  # Enable or disable MAVLink integration
    mavlink_host = "172.21.148.30"  # Configurable MAVLink host
    mavlink_port = 8088  # Configurable MAVLink port
    mavlink_polling_interval = 0.5  # Polling interval in seconds

    # Data points to extract from the MAVLink JSON response
    # Each key corresponds to a data field that will be displayed on the OSD
    mavlink_data_points = {
    "latitude": "/vehicles/1/components/1/messages/GLOBAL_POSITION_INT/message/lat",
    "longitude": "/vehicles/1/components/1/messages/GLOBAL_POSITION_INT/message/lon",
    "altitude_msl": "/vehicles/1/components/1/messages/ALTITUDE/message/altitude_amsl",  # MSL Altitude
    "altitude_agl": "/vehicles/1/components/1/messages/ALTITUDE/message/altitude_relative",  # AGL Altitude
    "voltage": "/vehicles/1/components/1/messages/SYS_STATUS/message/voltage_battery",
    "airspeed": "/vehicles/1/components/1/messages/VFR_HUD/message/airspeed",
    "groundspeed": "/vehicles/1/components/1/messages/VFR_HUD/message/groundspeed",
    "climb": "/vehicles/1/components/1/messages/VFR_HUD/message/climb",
    "roll": "/vehicles/1/components/1/messages/ATTITUDE/message/roll",
    "pitch": "/vehicles/1/components/1/messages/ATTITUDE/message/pitch",
    "heading": "/vehicles/1/components/1/messages/VFR_HUD/message/heading",
    "vdop": "/vehicles/1/components/1/messages/GPS_RAW_INT/message/vdop",
    "hdop": "/vehicles/1/components/1/messages/GPS_RAW_INT/message/hdop",
    "satellites_visible": "/vehicles/1/components/1/messages/GPS_RAW_INT/message/satellites_visible",
    "flight_mode": "/vehicles/1/components/1/messages/HEARTBEAT/message/custom_mode",
    "arm_status": "/vehicles/1/components/1/messages/HEARTBEAT/message/base_mode"
    }


    # OSD Configuration
    OSD_ENABLED = True
    OSD_CONFIG = {
        "name": {
            "enabled": True,
            "text": "PixEagle",
            "position": (3, 5),  # Top left corner, 3% from left, 5% from top
            "color": (255, 255, 255),  # White
            "font_size": 0.7
        },
        "datetime": {
            "enabled": True,
            "position": (98, 5),  # Top right corner, slightly inward to avoid clipping
            "color": (255, 255, 255),  # White
            "font_size": 0.6,
            "alignment": "right"
        },
        "crosshair": {
            "enabled": True,
            "color": (0, 255, 0),  # Green
            "thickness": 2,
            "length": 15  # Larger crosshair for better targeting visibility
        },
        "attitude_indicator": {
            "enabled": True,
            "position": (50, 50),  # Center of the screen
            "size": (70, 70),  # Larger size for better visibility
            "horizon_color": (255, 255, 255),  # White
            "grid_color": (200, 200, 200),  # Light gray for the grid
            "thickness": 2  # Thickness of the lines
        },
        "mavlink_data": {
            "enabled": True,
            "fields": {
                "heading": {
                    "position": (45, 30),  # Centered above the attitude indicator and crosshair
                    "font_size": 0.5,
                    "color": (255, 255, 255)  # White
                },
                "airspeed": {
                    "position": (10, 45),  # Left of the attitude indicator, aligned with its center
                    "font_size": 0.5,
                    "color": (255, 255, 255)  # White
                },
                "groundspeed": {
                    "position": (10, 55),  # Below airspeed
                    "font_size": 0.5,
                    "color": (255, 255, 255)  # White
                },
                "altitude_msl": {
                    "position": (65, 45),  # Right of the attitude indicator, aligned with its center
                    "font_size": 0.45,
                    "color": (255, 255, 255)  # White
                },
                "altitude_agl": {
                    "position": (65, 55),  # Below altitude_msl
                    "font_size": 0.45,
                    "color": (255, 255, 255)  # White
                },
                "roll": {
                    "position": (45, 75),  # Centered below the attitude indicator
                    "font_size": 0.5,
                    "color": (255, 255, 255)  # White
                },
                "pitch": {
                    "position": (45, 80),  # Below roll, centered
                    "font_size": 0.5,
                    "color": (255, 255, 255)  # White
                },
                "latitude": {
                    "position": (2, 92),  # Lower left corner
                    "font_size": 0.3,
                    "color": (255, 255, 255)  # White
                },
                "longitude": {
                    "position": (2, 96),  # Lower left corner
                    "font_size": 0.3,
                    "color": (255, 255, 255)  # White
                },
                "satellites_visible": {
                    "position": (2, 88),  # Lower left corner
                    "font_size": 0.4,
                    "color": (255, 255, 255)  # White
                },
                "hdop": {
                    "position": (2, 84),  # Lower left corner
                    "font_size": 0.4,
                    "color": (255, 255, 255)  # White
                },
                "voltage": {
                    "position": (2, 12),  # Upper left corner
                    "font_size": 0.4,
                    "color": (255, 255, 255)  # White
                },
                "arm_status": {
                    "position": (2, 16),  # Upper left corner
                    "font_size": 0.5,
                    "color": (255, 255, 255)  # White
                },
                "flight_mode": {
                    "position": (45, 10),  # Center top
                    "font_size": 0.5,
                    "color": (0, 0, 255),  # Red for critical information
                    "alignment": "center"
                }
            }
        },
        "tracker_status": {
            "enabled": True,
            "position": (75, 92),  # Lower right corner, near other status fields
            "font_size": 0.4,
            "color": (255, 255, 0)  # Yellow for status information
        },
        "follower_status": {
            "enabled": True,
            "position": (75, 96),  # Lower right corner, below tracker_status
            "font_size": 0.4,
            "color": (255, 255, 0)  # Yellow for status information
        }
    }
