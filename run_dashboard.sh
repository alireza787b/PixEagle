#!/bin/bash

#########################################
# PixEagle Dashboard Server Script
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
#
# This script automates the process of starting the React
# server for the PixEagle dashboard. It includes customizable
# parameters for the port and directory, and provides step-by-step
# progress updates. It intelligently handles npm installations
# and checks for required versions of Node.js and npm.
#
# Default Usage: ./run_dashboard.sh
# Custom Port:   ./run_dashboard.sh <PORT>
# Custom Dir:    ./run_dashboard.sh <PORT> <DASHBOARD_DIR>
#
#########################################

# Minimum required versions
MIN_NODE_VERSION=12
MIN_NPM_VERSION=6

# Default Parameters (user can modify these)
DEFAULT_PORT=3000
DEFAULT_DASHBOARD_DIR="$HOME/PixEagle/dashboard"

# Resolve script directory to support execution from any location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Optionally allow the port and directory to be passed as arguments
PORT="${1:-$DEFAULT_PORT}"
DASHBOARD_DIR="${2:-$DEFAULT_DASHBOARD_DIR}"

# Function to display a header message
function header_message() {
  echo "=========================================="
  echo "$1"
  echo "=========================================="
}

# Function to compare semantic version numbers
version_ge() {
  printf '%s\n%s' "$2" "$1" | sort -V -C
}

# 1. Display initial information
header_message "Starting PixEagle Dashboard Server"
echo "Using dashboard directory: $DASHBOARD_DIR"
echo "Server will run on port: $PORT"
echo "You can modify the directory or port by editing the script or passing them as arguments."
echo ""

# 2. Navigate to the PixEagle dashboard directory
header_message "Navigating to the PixEagle dashboard directory"
if [ -d "$DASHBOARD_DIR" ]; then
  cd "$DASHBOARD_DIR" || { echo "❌ Failed to navigate to $DASHBOARD_DIR"; exit 1; }
  echo "✅ Current directory: $(pwd)"
else
  echo "❌ Directory $DASHBOARD_DIR does not exist. Please check the path."
  exit 1
fi
echo ""

# 3. Check if Node.js and npm are installed and meet minimum version requirements
header_message "Checking Node.js and npm installations"

# Check Node.js
if ! command -v node &> /dev/null; then
  echo "❌ Node.js is not installed. Please install Node.js version $MIN_NODE_VERSION or higher."
  exit 1
else
  NODE_VERSION=$(node -v | sed 's/v//')
  if version_ge "$NODE_VERSION" "$MIN_NODE_VERSION"; then
    echo "✅ Node.js version $NODE_VERSION is installed."
  else
    echo "❌ Node.js version $NODE_VERSION is installed. Please upgrade to version $MIN_NODE_VERSION or higher."
    exit 1
  fi
fi

# Check npm
if ! command -v npm &> /dev/null; then
  echo "❌ npm is not installed. Please install npm version $MIN_NPM_VERSION or higher."
  exit 1
else
  NPM_VERSION=$(npm -v)
  if version_ge "$NPM_VERSION" "$MIN_NPM_VERSION"; then
    echo "✅ npm version $NPM_VERSION is installed."
  else
    echo "❌ npm version $NPM_VERSION is installed. Please upgrade to version $MIN_NPM_VERSION or higher."
    exit 1
  fi
fi
echo ""

# 4. Install required npm packages if necessary
header_message "Installing npm packages"

# Check if node_modules exists
if [ -d "node_modules" ]; then
  echo "🔍 node_modules directory exists. Checking for outdated packages..."
  OUTDATED_PACKAGES=$(npm outdated --depth=0)
  if [ -z "$OUTDATED_PACKAGES" ]; then
    echo "✅ All npm packages are up-to-date."
  else
    echo "⚠️  Outdated packages found. Updating..."
    npm install
    if [ $? -eq 0 ]; then
      echo "✅ npm packages updated successfully."
    else
      echo "❌ Failed to update npm packages. Please check the error messages above."
      exit 1
    fi
  fi
else
  echo "📁 node_modules directory not found. Installing packages..."
  # Use npm ci if package-lock.json exists
  if [ -f "package-lock.json" ]; then
    echo "🔒 package-lock.json found. Running 'npm ci' for a clean installation..."
    npm ci
  else
    echo "🔍 package-lock.json not found. Running 'npm install'..."
    npm install
  fi
  if [ $? -eq 0 ]; then
    echo "✅ npm packages installed successfully."
  else
    echo "❌ Failed to install npm packages. Please check the error messages above."
    exit 1
  fi
fi
echo ""

# 5. Check if the server is already running on the specified port
header_message "Checking if server is already running on port $PORT"
if lsof -i tcp:"$PORT" &> /dev/null; then
  echo "⚠️  A process is already running on port $PORT. Attempting to kill it..."
  PID=$(lsof -t -i tcp:"$PORT")
  if kill -9 "$PID" &> /dev/null; then
    echo "✅ Successfully killed process $PID."
  else
    echo "❌ Failed to kill process $PID. Please free up port $PORT manually."
    exit 1
  fi
else
  echo "✅ Port $PORT is free."
fi
echo ""

# 6. Start the React server on the specified port
header_message "Starting the React server on port $PORT"

# Set the PORT environment variable and start the server
export PORT="$PORT"

# Start the server and redirect output to a log file
npm start -- --port "$PORT"
if [ $? -eq 0 ]; then
  echo "✅ React server started successfully on port $PORT."
else
  echo "❌ Failed to start the React server. Please check the error messages above."
  exit 1
fi
echo ""

# 7. Provide information on what the script is doing
header_message "Server Information"
echo "🌐 The PixEagle dashboard is being served on http://localhost:$PORT"
echo "🌐 To access it from another device on the network, replace 'localhost' with your device's IP address."
echo "ℹ️  This dashboard provides a web interface for interacting with PixEagle, a system designed for UAV/UGV control and monitoring."
echo ""

# 8. End message
header_message "Dashboard Server Running"
echo "🎉 The server is now running and can be accessed via your browser."
echo "👉 Press Ctrl+C to stop the server at any time."
