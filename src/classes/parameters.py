# src/classes/parameters.py

class Parameters:
    """
    Central configuration class for the PixEagle project.
    Contains settings for video sources, tracking algorithms, application behavior,
    and debugging options. Designed for easy expansion to accommodate new features.
    """

    # ----- Video Source Configuration -----
    VIDEO_SOURCE_TYPE = "USB_CAMERA"  # Options: "VIDEO_FILE", "USB_CAMERA", "RTSP_STREAM", "UDP_STREAM", "HTTP_STREAM"

    # For VIDEO_FILE, specify the path to the video file
    # Example: VIDEO_FILE_PATH = "resources/test1.mp4"
    VIDEO_FILE_PATH = "resources/test5.mp4"

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

    #If we are working on Windows (or need to load mavsdk_server manually), we should handle the MAVSDK Server Differently in PX4 Controller Class
    EXTERNAL_MAVSDK_SERVER = True


    ENABLE_TELEMETRY = True
    TELEMETRY_SEND_RATE = 2  # Hz
    TELEMETRY_FLASK_ENDPOINT = '/telemetry'

    ENABLE_UDP_STREAM = False
    UDP_HOST = '127.0.0.1'
    UDP_PORT = 5550

    WEBSOCK_HOST = '127.0.0.1'
    WEBSOCK_PORT = 5551
    
    
    ENABLE_FOLLOWER_TELEMETRY = True

    FRAME_TITLE = "Video"

    # Streaming parameters
    ENABLE_STREAMING = True
    HTTP_STREAM_HOST = '0.0.0.0'
    HTTP_STREAM_PORT = 5077

    STREAM_WIDTH = 640
    STREAM_HEIGHT = 480
    STREAM_QUALITY = 80  # JPEG quality 0-100
    STREAM_FPS = 30  # target FPS
    STREAM_PROCESSED_OSD = True
    
    
    #Later on also develope a new mode where instead of connectin to drone, it just sends setpoints over UDP
    DIRECT_PX4_MAVSDK = True
    
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
    
    
    
    
    TRACKED_BBOX_STYLE = 'fancy'  # Options: 'normal', 'fancy'
    
    DISPLAY_DEVIATIONS = True

    # ----- Debugging and Logging -----
    # Enables verbose logging for debugging purposes. This might include detailed logs on
    # tracking performance, errors, or system metrics.
    ENABLE_DEBUGGING = True
    # Path to save log files. This provides a centralized location for log storage, making
    # it easier to review system behavior or diagnose issues.
    LOG_FILE_PATH = "logs/tracking_log.txt"


    # System connection configuration
    SYSTEM_ADDRESS = "udp://172.21.148.30:14540"
    #SYSTEM_ADDRESS = "udp://:18570"
    #SYSTEM_ADDRESS = "udp://:14540@172.21.148.30:14550"

    # Default PID gains
    PID_GAINS = {
        "x": {"p": 5, "i": 0.3, "d": 0.5},
        "y": {"p": 5, "i": 0.3, "d": 0.5},
        "z": {"p": 1, "i": 0.01, "d": 0.01}
    }

    # Gain scheduling for different altitude ranges
    ALTITUDE_GAIN_SCHEDULE = {
        (0, 5): {"x": {"p": 1.2, "i": 0.02, "d": 0.02}, "y": {"p": 1.2, "i": 0.02, "d": 0.02}, "z": {"p": 1.1, "i": 0.02, "d": 0.02}},
        (5, 15): {"x": {"p": 1.0, "i": 0.015, "d": 0.015}, "y": {"p": 1.0, "i": 0.015, "d": 0.015}, "z": {"p": 0.9, "i": 0.015, "d": 0.015}},
        (15, 30): {"x": {"p": 0.9, "i": 0.01, "d": 0.01}, "y": {"p": 0.9, "i": 0.01, "d": 0.01}, "z": {"p": 0.8, "i": 0.01, "d": 0.01}},
        (30, 50): {"x": {"p": 0.8, "i": 0.005, "d": 0.005}, "y": {"p": 0.8, "i": 0.005, "d": 0.005}, "z": {"p": 0.7, "i": 0.005, "d": 0.005}},
        (50, 100): {"x": {"p": 0.7, "i": 0.003, "d": 0.003}, "y": {"p": 0.7, "i": 0.003, "d": 0.003}, "z": {"p": 0.6, "i": 0.003, "d": 0.003}}
    }

    # Enable or disable gain scheduling
    ENABLE_GAIN_SCHEDULING = False
    GAIN_SCHEDULING_PARAMETER = 'current_altitude'
    
    # Bounds for velocity outputs
    VELOCITY_LIMITS = {"x": 10.0, "y": 10.0, "z": 5.0}  # Maximum velocity in m/s

    # Safety and operational parameters
    MIN_DESCENT_HEIGHT = 10  # meters
    MAX_RATE_OF_DESCENT = 0.0  # meters per second

    #Desired normalized position of aiming for put the target in screen
    DESIRE_AIM = (0,0)

    CAMERA_YAW_OFFSET = 0
    
    SETPOINT_PUBLISH_RATE_S = 0.1
    ENABLE_SETPOINT_DEBUGGING = True
    # ----- Future Expansion -----
    # Placeholder for future parameters. This section can be used to outline planned expansions,
    # such as new video stream types, integration with additional hardware, or advanced tracking features.
    # FUTURE_PARAMETER = "value"




# Reminder and Note for Drone Camera Streaming Setup:

# To simulate camera tracking for drone operations in X-Plane, we use a setup where the camera feed from the drone is streamed and then simulated as a physical camera using SparkoCam. This feed is then streamed to the WSL environment for processing with PX4 SITL and the PixEagle tracker.

# Initial Setup Steps:
# --------------------
# 1. Ensure GStreamer is installed on both Windows and WSL. The installation should include the base, good, bad, and ugly plugin sets to support a wide range of formats and protocols.

# 2. After installing GStreamer, remember to add its bin directory to your system's PATH environment variable. This enables you to run GStreamer commands from any command prompt or terminal window without specifying the full path to the executables.

#    Example for adding to PATH on Windows:
#    - Right-click on 'This PC' or 'My Computer' and select 'Properties'.
#    - Navigate to 'Advanced system settings' -> 'Environment Variables'.
#    - Under 'System Variables', find and select 'Path', then click 'Edit'.
#    - Add the path to your GStreamer bin directory, typically 'C:\gstreamer\1.0\x86_64\bin'.
#    - Click 'OK' to close all dialogues.

# 3. To list available video capture devices (cameras) that can be used with GStreamer, use the following command. This helps in identifying the correct device path or name for streaming:

#    On Windows:
# gst-device-monitor-1.0 Video/Source

# This command lists all video sources along with their capabilities and device paths. Look for the device name or path related to SparkoCam or any other camera you intend to use.

# Streaming Command on Windows (Sender):
# --------------------------------------
# Use the following GStreamer command to stream the SparkoCam Video feed to the WSL environment. This command captures the video from SparkoCam, encodes it, and sends it over UDP to the specified WSL IP and port.

# gst-launch-1.0 -v mfvideosrc device-path="\\?\root#image#0000#{e5323777-f976-4f5b-9b55-b94699c46e44}\global" ! videoconvert ! x264enc tune=zerolatency bitrate=500 speed-preset=superfast ! rtph264pay ! udpsink host=172.21.148.30 port=5000

# Ensure to replace the device-path with the correct path for your setup and adjust the host IP and port as necessary for your WSL environment.

# Receiving Command in WSL (Receiver):
# -----------------------------------
# In the WSL environment, use the following GStreamer command to receive the streamed video. This command listens on the specified port for the incoming UDP stream, decodes the H.264 video, and displays it.



# Ensure to replace the device-path with the correct path for your setup and adjust the host IP and port as necessary for your WSL environment.

# Receiving Command in WSL (Receiver):
# -----------------------------------
# In the WSL environment, use the following GStreamer command to receive the streamed video. This command listens on the specified port for the incoming UDP stream, decodes the H.264 video, and displays it.



# Ensure to replace the device-path with the correct path for your setup and adjust the host IP and port as necessary for your WSL environment.

# Receiving Command in WSL (Receiver):
# -----------------------------------
# In the WSL environment, use the following GStreamer command to receive the streamed video. This command listens on the specified port for the incoming UDP stream, decodes the H.264 video, and displays it.

# gst-launch-1.0 -v udpsrc port=5000 caps="application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264" ! rtph264depay ! avdec_h264 ! videoconvert ! autovideosink


# This setup enables real-time video feed processing in WSL, facilitating simulations for camera tracking on drones within the X-Plane ecosystem and interaction with PX4 SITL and PixEagle tracker.

# Additional Notes:
# -----------------
# - Verify the UDP port (e.g., 5000) is not blocked by firewall settings on both Windows and WSL to ensure smooth communication.
# - Adjust bitrate and encoder settings based on network capacity and desired video quality for optimal performance.

# This approach provides a flexible method for simulating and processing drone camera feeds, essential for development and testing scenarios involving drone tracking and control systems.

