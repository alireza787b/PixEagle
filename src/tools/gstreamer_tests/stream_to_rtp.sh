#!/bin/bash
# Stream to RTP/UDP 264 . Optimized for QGC.
#!/bin/bash
# GStreamer RTP/UDP Streaming Script - Optimized for QGroundControl
#
# This script streams video from a camera source to a specified host and port using RTP/UDP. 
# It is optimized for use with QGroundControl (QGC) and supports On-Screen Display (OSD) elements 
# like crosshairs, title, timestamp, and grid overlay.
#
# Requirements:
# - GStreamer must be installed on the system (`gst-launch-1.0`).
#
# Parameters:
# - SENSOR_ID: ID of the camera sensor (default: 0).
# - WIDTH: Width of the video stream (default: 1920).
# - HEIGHT: Height of the video stream (default: 1080).
# - FRAMERATE: Frame rate of the video stream (default: 30).
# - FLIP_METHOD: Method to flip the video (default: 0).
# - HOST: IP address of the receiving machine (e.g., QGroundControl).
# - PORT: UDP port for streaming.
#
# OSD Settings:
# - ENABLE_OSD: Toggle to enable/disable OSD elements.
# - ENABLE_CROSSHAIR: Toggle to enable/disable the crosshair overlay.
# - ENABLE_TITLE: Toggle to enable/disable the title overlay.
# - ENABLE_TIMESTAMP: Toggle to enable/disable the timestamp overlay.
# - ENABLE_GRID: Toggle to enable/disable the grid overlay.
#
# Cleanup:
# - The script sets a trap to ensure that the GStreamer pipeline is terminated and temporary 
#   files (e.g., the SDP file) are removed when the script exits.
#
# SDP File:
# - An SDP file is created to describe the multimedia session, which can be used by clients 
#   like QGroundControl to configure and connect to the stream.
#
# GStreamer Pipeline:
# - Captures video, applies OSD elements (if enabled), encodes in H.264, and streams over 
#   RTP/UDP to the specified host and port.
#
# Usage:
# - Run the script and provide the necessary parameters. The stream will start automatically 
#   and can be viewed on the specified receiving machine using the SDP file.

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
HOST=192.168.1.163 # IP address of the MacBook (QGroundControl machine)
PORT=2000
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
SDP_FILE="$SCRIPT_DIR/stream.sdp"

# OSD (On-Screen Display) settings
ENABLE_OSD=true             # Global toggle for enabling/disabling OSD
ENABLE_CROSSHAIR=true       # Toggle for enabling/disabling the crosshair
ENABLE_TITLE=true           # Toggle for enabling/disabling the title
ENABLE_TIMESTAMP=true       # Toggle for enabling/disabling the timestamp
ENABLE_GRID=false           # Toggle for enabling/disabling the grid overlay

CROSSHAIR_TEXT="+"          # Crosshair symbol
CROSSHAIR_FONT="Sans, 50"   # Crosshair font and size
CROSSHAIR_COLOR="0xFFFF0000" # Crosshair color (in ARGB format, red: 0xFFFF0000)

TITLE_TEXT="PixEagle"       # Title text
TITLE_FONT="Sans, 30"       # Title font and size
TITLE_COLOR="0xFFFFFFFF"    # Title color (in ARGB format, white: 0xFFFFFFFF)
TITLE_POSITION="top"        # Title position (top or bottom)

TIMESTAMP_FONT="Sans, 20"   # Timestamp font and size
TIMESTAMP_COLOR="0xFFFFFF00" # Timestamp color (in ARGB format, yellow: 0xFFFFFF00)
TIMESTAMP_FORMAT="%Y-%m-%d %H:%M:%S" # Timestamp format

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

# Prepare OSD elements if enabled
OSD_ELEMENTS=""
if [ "$ENABLE_OSD" = true ]; then
    if [ "$ENABLE_CROSSHAIR" = true ]; then
        OSD_ELEMENTS+="textoverlay text=\"$CROSSHAIR_TEXT\" font-desc=\"$CROSSHAIR_FONT\" valignment=center halignment=center ! "
    fi
    if [ "$ENABLE_TITLE" = true ]; then
        OSD_ELEMENTS+="textoverlay text=\"$TITLE_TEXT\" font-desc=\"$TITLE_FONT\" valignment=$TITLE_POSITION halignment=left ! "
    fi
    if [ "$ENABLE_TIMESTAMP" = true ]; then
        OSD_ELEMENTS+="clockoverlay font-desc=\"$TIMESTAMP_FONT\" valignment=bottom halignment=right time-format=\"$TIMESTAMP_FORMAT\" shaded-background=true ! "
    fi
    if [ "$ENABLE_GRID" = true ]; then
        OSD_ELEMENTS+="cairooverlay draw-on-top=true ! "
    fi
fi

# Start the GStreamer pipeline with OSD elements if enabled
echo "Starting GStreamer pipeline..."
gst-launch-1.0 -v \
    nvarguscamerasrc sensor-id=$SENSOR_ID ! \
    "video/x-raw(memory:NVMM), width=(int)$WIDTH, height=(int)$HEIGHT, format=(string)NV12, framerate=(fraction)$FRAMERATE/1" ! \
    nvvidconv flip-method=$FLIP_METHOD ! \
    videoconvert ! \
    $OSD_ELEMENTS \
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

echo "Streaming started with OSD elements. Stream is being sent to $HOST:$PORT. Use this SDP file for configurations if needed: $SDP_FILE"

# Wait for the GStreamer pipeline to exit
wait $GST_PID
