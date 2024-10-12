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
# By default, it runs in production mode, serving the optimized
# build files. Use the -d flag to run in development mode.
#
# Default Usage: ./run_dashboard.sh
# Custom Port:   ./run_dashboard.sh <PORT>
# Custom Dir:    ./run_dashboard.sh <PORT> <DASHBOARD_DIR>
# Development Mode: ./run_dashboard.sh -d
#
# Flags:
#   -d : Run in development mode (default is production mode)
#
# Example:
#   ./run_dashboard.sh -d 3001
#   (Runs the dashboard in development mode on port 3001)
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

# Initialize variables
MODE="production"
POSITIONAL_ARGS=()

# Function to display usage instructions
display_usage() {
  echo "Usage: $0 [-d] [PORT] [DASHBOARD_DIR]"
  echo ""
  echo "Flags:"
  echo "  -d, --development : Run in development mode (default is production mode)"
  echo "  -h, --help        : Display this help message"
  echo ""
  echo "Positional Arguments:"
  echo "  PORT           : Port to run the server on (default: $DEFAULT_PORT)"
  echo "  DASHBOARD_DIR  : Path to the dashboard directory (default: $DEFAULT_DASHBOARD_DIR)"
  echo ""
  echo "Examples:"
  echo "  $0            # Runs in production mode on default port"
  echo "  $0 -d         # Runs in development mode on default port"
  echo "  $0 4000       # Runs in production mode on port 4000"
  echo "  $0 -d 4000    # Runs in development mode on port 4000"
}

# Parse options
while [[ $# -gt 0 ]]; do
  case $1 in
    -d|--development)
      MODE="development"
      shift # Remove argument from processing
      ;;
    -h|--help)
      display_usage
      exit 0
      ;;
    -*|--*)
      echo "Unknown option $1"
      display_usage
      exit 1
      ;;
    *)
      POSITIONAL_ARGS+=("$1") # Save positional argument
      shift
      ;;
  esac
done

# Restore positional arguments
set -- "${POSITIONAL_ARGS[@]}"

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
echo "Mode: $MODE"
echo "Using dashboard directory: $DASHBOARD_DIR"
echo "Server will run on port: $PORT"
echo "You can modify the directory or port by editing the script or passing them as arguments."
echo ""
if [ "$MODE" = "development" ]; then
  echo "Note: Development mode provides hot-reloading and detailed error messages."
else
  echo "Note: Production mode serves the optimized build for better performance."
fi
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

# 6. Start the server based on the mode
header_message "Starting the Dashboard Server in $MODE mode on port $PORT"

# Set the PORT environment variable
export PORT="$PORT"

if [ "$MODE" = "development" ]; then
  # Start the development server
  npm start
  if [ $? -eq 0 ]; then
    echo "✅ Development server started successfully on port $PORT."
  else
    echo "❌ Failed to start the development server. Please check the error messages above."
    exit 1
  fi
else
  # Build the app
  header_message "Building the app for production"
  npm run build
  if [ $? -ne 0 ]; then
    echo "❌ Build failed. Please check the error messages above."
    exit 1
  else
    echo "✅ Build completed successfully."
  fi

  # Check if 'serve' is installed
  if ! npx --no-install serve --version &> /dev/null; then
    echo "📦 'serve' package is not installed. Installing locally..."
    npm install --save-dev serve
    if [ $? -ne 0 ]; then
      echo "❌ Failed to install 'serve'. Please install it manually."
      exit 1
    else
      echo "✅ 'serve' installed successfully."
    fi
  else
    echo "✅ 'serve' is already installed."
  fi

  # Start the server using 'serve'
  header_message "Serving the production build on port $PORT"
  npx serve -s build -l $PORT
  if [ $? -eq 0 ]; then
    echo "✅ Production server started successfully on port $PORT."
  else
    echo "❌ Failed to start the production server. Please check the error messages above."
    exit 1
  fi
fi

# 7. Provide information on what the script is doing
header_message "Server Information"
if [ "$MODE" = "development" ]; then
  echo "🌐 The PixEagle dashboard is running in development mode on http://localhost:$PORT"
  echo "🌐 Development mode provides hot-reloading and detailed error messages."
else
  echo "🌐 The PixEagle dashboard is being served on http://localhost:$PORT"
  echo "🌐 Production mode serves the optimized build for better performance."
fi
echo "🌐 To access it from another device on the network, replace 'localhost' with your device's IP address."
echo "ℹ️  This dashboard provides a web interface for interacting with PixEagle, a system designed for UAV/UGV control and monitoring."
echo ""

# 8. End message
header_message "Dashboard Server Running"
echo "🎉 The server is now running and can be accessed via your browser."
echo "👉 Press Ctrl+C to stop the server at any time."
