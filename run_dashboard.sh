#!/bin/bash

#########################################
# Script to run the PixEagle React Dashboard
# 
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
#
# This script automates the process of starting the React
# server for the PixEagle dashboard. It allows customization
# of the port and provides step-by-step progress updates.
#
# Usage: ./run_dashboard.sh
#
#########################################

# Parameters (modify if needed)
PORT=3001

# Optionally allow the port to be passed as an argument
if [ ! -z "$1" ]; then
  PORT=$1
fi

# Function to display a header message
function header_message() {
  echo "=========================================="
  echo "$1"
  echo "=========================================="
}

# 1. Navigate to the PixEagle dashboard directory
header_message "Navigating to the PixEagle dashboard directory"
cd /path/to/your/dashboard || { echo "Failed to navigate to dashboard directory"; exit 1; }
echo "Current directory: $(pwd)"

# 2. Check if npm is installed
header_message "Checking if npm is installed"
if ! command -v npm &> /dev/null
then
    echo "npm could not be found. Please install Node.js and npm before proceeding."
    exit 1
else
    echo "npm is installed."
fi

# 3. Install required npm packages
header_message "Installing npm packages"
npm install
if [ $? -eq 0 ]; then
  echo "npm packages installed successfully."
else
  echo "Failed to install npm packages."
  exit 1
fi

# 4. Start the React server on the specified port
header_message "Starting the React server on port $PORT"
PORT=$PORT npm start

# 5. Provide information on what the script is doing
header_message "Server Information"
echo "The PixEagle dashboard is being served on http://localhost:$PORT"
echo "To access it from another device on the network, replace 'localhost' with your device's IP address."
echo "This dashboard provides a web interface for interacting with PixEagle, a system designed for UAV/UGV control and monitoring."

# 6. End message
header_message "Dashboard Server Running"
echo "The server is now running and can be accessed via your browser."
