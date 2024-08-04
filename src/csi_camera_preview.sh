#!/bin/bash

# Check if GStreamer is installed
if ! command -v gst-launch-1.0 &> /dev/null; then
    echo "GStreamer is not installed. Please install it first."
    exit 1
fi

# Set default values for the CSI camera parameters
SENSOR_ID=0
WIDTH=1280
HEIGHT=720
FRAMERATE=30
FLIP_METHOD=0

# Run the GStreamer pipeline to preview the CSI camera feed and print information
gst-launch-1.0 -v \
    nvarguscamerasrc sensor-id=$SENSOR_ID ! \
    "video/x-raw(memory:NVMM), width=(int)$WIDTH, height=(int)$HEIGHT, format=(string)NV12, framerate=(fraction)$FRAMERATE/1" ! \
    nvvidconv flip-method=$FLIP_METHOD ! \
    "video/x-raw, format=(string)I420, width=(int)$WIDTH, height=(int)$HEIGHT" ! \
    videoconvert ! \
    "video/x-raw, format=(string)BGR" ! \
    videoscale ! \
    nveglglessink sync=false

# Print camera info
echo "CSI Camera Info:"
echo "  Sensor ID: $SENSOR_ID"
echo "  Resolution: ${WIDTH}x${HEIGHT}"
echo "  Frame Rate: $FRAMERATE FPS"
echo "  Flip Method: $FLIP_METHOD"
