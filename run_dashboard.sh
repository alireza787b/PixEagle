#!/bin/bash

#########################################
# PixEagle Dashboard Server Script
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
#
# This script automates the process of starting the React
# server for the PixEagle dashboard, which is located in
# the ~/PixEagle/dashboard directory. It includes customizable
# parameters for the port and directory, and provides step-by-step
# progress updates.
#
# Default Usage: ./run_dashboard.sh
# Custom Port:   ./run_dashboard.sh <PORT>
# Custom Dir:    ./run_dashboard.sh <PORT> <DASHBOARD_DIR>
#
#########################################

# Default Parameters (user can modify these)
DEFAULT_PORT=3001
DASHBOARD_DIR=~/PixEagle/dashboard

# Optionally allow the port and directory to be passed as arguments
if [ ! -z "$1" ]; then
  PORT=$1
else
  PORT=$DEFAULT_PORT
fi

if [ ! -z "$2" ]; then
  DASHBOARD_DIR=$2
fi

# Function to display a header message
function header_message() {
  echo "=========================================="
  echo "$1"
  echo "=========================================="
}

# 1. Display initial information
header_message "Starting PixEagle Dashboard Server"
echo "Using dashboard directory: $DASHBOARD_DIR"
echo "Server will run on port: $PORT"
echo "You can modify the directory or port by editing the script or passing them as arguments."

# 2. Navigate to the PixEagle dashboard directory
header_message "Navigating to the PixEagle dashboard directory"
if [ -d "$DASHBOARD_DIR" ]; then
  cd "$DASHBOARD_DIR" || { echo "Failed to navigate to $DASHBOARD_DIR"; exit 1; }
  echo "Current directory: $(pwd)"
else
  echo "Directory $DASHBOARD_DIR does not exist. Please check the path."
  exit 1
fi

# 3. Check if npm is installed
header_message "Checking if npm is installed"
if ! command -v npm &> /dev/null
then
    echo "npm could not be found. Please install Node.js and npm before proceeding."
    exit 1
else
    echo "npm is installed."
fi

# 4. Install required npm packages
header_message "Installing npm packages"
npm install
if [ $? -eq 0 ]; then
  echo "npm packages installed successfully."
else
  echo "Failed to install npm packages. Please check the error messages above."
  exit 1
fi

# 5. Start the React server on the specified port
header_message "Starting the React server on port $PORT"
PORT=$PORT npm start

# 6. Provide information on what the script is doing
header_message "Server Information"
echo "The PixEagle dashboard is being served on http://localhost:$PORT"
echo "To access it from another device on the network, replace 'localhost' with your device's IP address."
echo "This dashboard provides a web interface for interacting with PixEagle, a system designed for UAV/UGV control and monitoring."

# 7. End message
header_message "Dashboard Server Running"
echo "The server is now running and can be accessed via your browser."
