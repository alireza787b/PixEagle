#!/bin/bash

# Ensure GStreamer is installed
if ! command -v gst-launch-1.0 &> /dev/null; then
    echo "GStreamer is not installed. Please install it first."
    exit 1
fi

# Define parameters
SENSOR_ID=0
WIDTH=1920
HEIGHT=1080
FRAMERATE=30
FLIP_METHOD=0
HOST=10.223.0.5 # IP address of the MacBook (QGroundControl machine)
PORT=2000
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
SDP_FILE="$SCRIPT_DIR/stream.sdp"

# Function to clean up on exit
cleanup() {
    echo "Cleaning up..."
    pkill -f "gst-launch-1.0"
    rm -f $SDP_FILE
    echo "Cleanup complete."
}

# Set the trap to clean up on script exit
trap cleanup EXIT

# Create SDP file
echo "Creating SDP file at $SDP_FILE..."
cat <<EOF > $SDP_FILE
v=0
o=- 0 0 IN IP4 $HOST
s=GStreamer
c=IN IP4 $HOST
t=0 0
a=tool:GStreamer
m=video $PORT RTP/AVP 96
a=rtpmap:96 H264/90000
EOF

# Verify SDP file creation
if [ ! -f $SDP_FILE ]; then
    echo "Failed to create SDP file at $SDP_FILE. Exiting."
    exit 1
fi

# Start the GStreamer pipeline
echo "Starting GStreamer pipeline..."
gst-launch-1.0 -v \
    nvarguscamerasrc sensor-id=$SENSOR_ID ! \
    "video/x-raw(memory:NVMM), width=(int)$WIDTH, height=(int)$HEIGHT, format=(string)NV12, framerate=(fraction)$FRAMERATE/1" ! \
    nvvidconv flip-method=$FLIP_METHOD ! \
    videoconvert ! \
    x264enc tune=zerolatency bitrate=5000000 speed-preset=superfast ! \
    rtph264pay config-interval=1 pt=96 ! \
    udpsink host=$HOST port=$PORT &
    
GST_PID=$!

# Wait for the GStreamer pipeline to start
sleep 5

# Check if the GStreamer pipeline is running
if ! ps -p $GST_PID > /dev/null; then
    echo "Failed to start GStreamer pipeline. Exiting."
    exit 1
fi

echo "Streaming started. Stream is being sent to $HOST:$PORT. Use this SDP file for configurations if needed: $SDP_FILE"

# Wait for the GStreamer pipeline to exit
wait $GST_PID
