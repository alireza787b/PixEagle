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
HOST=10.223.0.5 # IP address of the receiving PC (QGroundControl machine)
PORT=2000

# Function to clean up on exit
cleanup() {
    echo "Cleaning up..."
    pkill -f "gst-launch-1.0"
    echo "Cleanup complete."
}

# Set the trap to clean up on script exit
trap cleanup EXIT

# Start the GStreamer pipeline
echo "Starting GStreamer pipeline..."
gst-launch-1.0 -v \
    nvarguscamerasrc sensor-id=$SENSOR_ID ! \
    "video/x-raw(memory:NVMM), width=(int)$WIDTH, height=(int)$HEIGHT, format=(string)NV12, framerate=(fraction)$FRAMERATE/1" ! \
    nvvidconv flip-method=$FLIP_METHOD ! \
    videoconvert ! \
    x264enc tune=zerolatency bitrate=5000000 speed-preset=superfast ! \
    h264parse ! \
    rtph264pay name=pay0 pt=96 config-interval=-1 ! \
    udpsink host=$HOST port=$PORT sync=false &
    
GST_PID=$!

# Wait for the GStreamer pipeline to start
sleep 5

# Check if the GStreamer pipeline is running
if ! ps -p $GST_PID > /dev/null; then
    echo "Failed to start GStreamer pipeline. Exiting."
    exit 1
fi

echo "Streaming started. Stream is being sent to $HOST:$PORT"

# Wait for the GStreamer pipeline to exit
wait $GST_PID
