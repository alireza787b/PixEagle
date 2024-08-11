#!/bin/bash

# Check if GStreamer is installed
if ! command -v gst-launch-1.0 &> /dev/null; then
    echo "GStreamer is not installed. Please install it first."
    exit 1
fi

# Set the port to listen on
PORT=2000

# Run the GStreamer pipeline to receive and display the video stream
gst-launch-1.0 -v udpsrc port=$PORT caps="application/x-rtp, media=video, encoding-name=H264, payload=96" ! \
    rtph264depay ! avdec_h264 ! videoconvert ! autovideosink sync=false
