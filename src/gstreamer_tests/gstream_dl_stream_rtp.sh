#!/bin/bash

# Check if GStreamer is installed
if ! command -v gst-launch-1.0 &> /dev/null; then
    echo "GStreamer is not installed. Please install it first."
    exit 1
fi

# Set default values for the CSI camera parameters
SENSOR_ID=0
WIDTH=1920
HEIGHT=1080
FRAMERATE=30
FLIP_METHOD=0
# HOST=10.223.0.5 # Change to your remote computer IP
HOST=127.0.0.1 # Change to your remote computer IP
PORT=5000

# Run the GStreamer pipeline to stream the CSI camera feed over UDP
gst-launch-1.0 -v \
    nvarguscamerasrc sensor-id=$SENSOR_ID ! \
    "video/x-raw(memory:NVMM), width=(int)$WIDTH, height=(int)$HEIGHT, format=(string)NV12, framerate=(fraction)$FRAMERATE/1" ! \
    nvvidconv flip-method=$FLIP_METHOD ! \
    videoconvert ! \
    x264enc tune=zerolatency bitrate=5000 speed-preset=superfast ! \
    "video/x-h264, stream-format=byte-stream" ! \
    rtph264pay ! \
    udpsink host=$HOST port=$PORT

# Print camera info
echo "CSI Camera Info:"
echo "  Sensor ID: $SENSOR_ID"
echo "  Resolution: ${WIDTH}x${HEIGHT}"
echo "  Frame Rate: $FRAMERATE FPS"
echo "  Flip Method: $FLIP_METHOD"
echo "  Streaming to: $HOST:$PORT"
