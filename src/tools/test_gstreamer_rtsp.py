import cv2

# Define the GStreamer pipeline for RTSP streaming
# Note: protocols=tcp and latency=200 are required for reliable streaming
# UDP may cause "Invalid input packet" errors due to packet loss
rtsp_url = "rtsp://192.168.0.108:554/stream=0"
gst_pipeline = f"rtspsrc location={rtsp_url} protocols=tcp latency=200 ! decodebin ! videoconvert ! video/x-raw,format=BGR ! appsink"

# Initialize the VideoCapture object with the GStreamer pipeline
cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    print("Error: Unable to open video stream.")
else:
    print("Successfully connected to the video stream.")

    # Read frames from the stream
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to retrieve frame.")
            break

        # Process the frame (e.g., apply computer vision algorithms)
        # For now, we just print the frame dimensions
        print(f"Frame dimensions: {frame.shape}")

    cap.release()
    print("Video stream closed.")
