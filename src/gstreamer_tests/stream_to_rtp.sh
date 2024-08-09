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

# OSD (On-Screen Display) settings
ENABLE_OSD=true            # Global toggle for enabling/disabling OSD
CROSSHAIR_TEXT="+"         # Crosshair symbol
CROSSHAIR_FONT="Sans, 50"  # Crosshair font and size
CROSSHAIR_COLOR="red"      # Crosshair color
TITLE_TEXT="PixEagle"      # Title text
TITLE_FONT="Sans, 30"      # Title font and size
TITLE_COLOR="white"        # Title color
TITLE_POSITION="top"       # Title position (top or bottom)
TIMESTAMP_FONT="Sans, 20"  # Timestamp font and size
TIMESTAMP_COLOR="yellow"   # Timestamp color
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
if [ "$ENABLE_OSD" = true ]; then
    OSD_ELEMENTS="
        textoverlay text=\"$CROSSHAIR_TEXT\" font-desc=\"$CROSSHAIR_FONT\" color=\"$CROSSHAIR_COLOR\" valignment=center halignment=center !
        clockoverlay text=\"$TITLE_TEXT\" font-desc=\"$TITLE_FONT\" color=\"$TITLE_COLOR\" halignment=left valignment=$TITLE_POSITION shaded-background=true !
        clockoverlay font-desc=\"$TIMESTAMP_FONT\" color=\"$TIMESTAMP_COLOR\" halignment=right valignment=bottom time-format=\"$TIMESTAMP_FORMAT\" shaded-background=true !"
else
    OSD_ELEMENTS=""
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