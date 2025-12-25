#!/bin/bash

#########################################
# PixEagle Main Python Application Runner
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
#
# This script automates the process of running the main
# Python application for PixEagle. It activates the Python
# virtual environment and executes the main script located
# at ~/PixEagle/src/main.py.
#
# Default Usage: ./run_main.sh
# Custom Interpreter: ./run_main.sh <PYTHON_INTERPRETER>
#
#########################################

# Default Parameters (user can modify these)
VENV_DIR=~/PixEagle/venv
PYTHON_INTERPRETER=$VENV_DIR/bin/python
DEVELOPMENT_MODE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --dev)
      DEVELOPMENT_MODE=true
      shift
      ;;
    *)
      # Assume it's a Python interpreter path
      PYTHON_INTERPRETER=$1
      shift
      ;;
  esac
done

# Function to display a header message
function header_message() {
  echo "=========================================="
  echo "$1"
  echo "=========================================="
}

# 1. Display initial information
header_message "Starting PixEagle Main Application"
echo "Using Python interpreter: $PYTHON_INTERPRETER"
if [ "$DEVELOPMENT_MODE" = true ]; then
    echo "🔧 Development mode: ENABLED"
    echo "   • Enhanced debugging and logging"
    echo "   • Auto-reload on file changes (if supported)"
else
    echo "🚀 Production mode: ENABLED"
fi
echo "You can modify the interpreter by editing the script or passing it as an argument."

# 2. Check if the virtual environment exists and activate it, otherwise use provided interpreter
header_message "Checking Virtual Environment"
if [ -d "$VENV_DIR" ]; then
  echo "Virtual environment found at $VENV_DIR."
else
  echo "Virtual environment not found at $VENV_DIR."
  echo "Ensure the virtual environment exists, or the script will use the provided Python interpreter."
fi

# 3. Check if the Python interpreter is valid
header_message "Checking Python Interpreter"
if ! command -v $PYTHON_INTERPRETER &> /dev/null
then
    echo "Python interpreter $PYTHON_INTERPRETER could not be found."
    exit 1
else
    echo "Python interpreter $PYTHON_INTERPRETER is available."
fi

# 4. Run the main Python application with restart support
MAIN_SCRIPT=~/PixEagle/src/main.py
RESTART_EXIT_CODE=42

if [ -f "$MAIN_SCRIPT" ]; then
  header_message "Running the PixEagle Main Python Script"

  # Set environment variables for development mode
  if [ "$DEVELOPMENT_MODE" = true ]; then
    export PIXEAGLE_DEV_MODE=true
    export FLASK_DEBUG=1
    export PYTHONUNBUFFERED=1
    echo "🔧 Development environment variables set"
  fi

  # Restart loop: continues running until exit code is not 42
  while true; do
    echo "🚀 Starting PixEagle backend..."
    $PYTHON_INTERPRETER $MAIN_SCRIPT
    exit_code=$?

    if [ $exit_code -eq $RESTART_EXIT_CODE ]; then
      echo ""
      header_message "🔄 Restart Requested (Exit Code 42)"
      echo "Restarting PixEagle in 2 seconds..."
      echo "This restart was triggered by the configuration manager."
      sleep 2
      echo ""
      continue
    elif [ $exit_code -eq 0 ]; then
      echo "PixEagle main script executed successfully."
      break
    else
      echo "❌ PixEagle exited with error code: $exit_code"
      echo "Please check the error messages above."
      exit $exit_code
    fi
  done
else
  echo "Main Python script $MAIN_SCRIPT not found. Please check the path."
  exit 1
fi

# 5. End message
header_message "PixEagle Application Execution Completed"
echo "The PixEagle main application has finished running."
