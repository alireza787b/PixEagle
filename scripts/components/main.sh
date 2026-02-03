#!/bin/bash

# ============================================================================
# scripts/components/main.sh - PixEagle Main Python Application Runner
# ============================================================================
# Runs the main Python application for PixEagle.
#
# Features:
#   - Activates the Python virtual environment
#   - Auto-restart support (exit code 42)
#   - Development mode with enhanced debugging
#
# Usage:
#   bash scripts/components/main.sh
#   bash scripts/components/main.sh --dev
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

# Get directories
SCRIPTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

# Default Parameters
VENV_DIR="$PIXEAGLE_DIR/venv"
PYTHON_INTERPRETER="$VENV_DIR/bin/python"
DEVELOPMENT_MODE=false
RESTART_EXIT_CODE=42

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev|-d)
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
    echo "Development mode: ENABLED"
    echo "   - Enhanced debugging and logging"
    echo "   - Auto-reload on file changes (if supported)"
else
    echo "Production mode: ENABLED"
fi
echo "Working directory: $PIXEAGLE_DIR"

# 2. Check if the virtual environment exists
header_message "Checking Virtual Environment"
if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment found at $VENV_DIR."
else
    echo "Virtual environment not found at $VENV_DIR."
    echo "Run: make init (or bash scripts/init.sh)"
    exit 1
fi

# 3. Check if the Python interpreter is valid
header_message "Checking Python Interpreter"
if ! command -v $PYTHON_INTERPRETER &> /dev/null; then
    echo "Python interpreter $PYTHON_INTERPRETER could not be found."
    exit 1
else
    echo "Python interpreter $PYTHON_INTERPRETER is available."
fi

# 4. Run the main Python application with restart support
MAIN_SCRIPT="$PIXEAGLE_DIR/src/main.py"

if [ -f "$MAIN_SCRIPT" ]; then
    header_message "Running the PixEagle Main Python Script"

    # Set environment variables for development mode
    if [ "$DEVELOPMENT_MODE" = true ]; then
        export PIXEAGLE_DEV_MODE=true
        export FLASK_DEBUG=1
        export PYTHONUNBUFFERED=1
        echo "Development environment variables set"
    fi

    # Restart loop: continues running until exit code is not 42
    while true; do
        echo "Starting PixEagle backend..."
        $PYTHON_INTERPRETER $MAIN_SCRIPT
        exit_code=$?

        if [ $exit_code -eq $RESTART_EXIT_CODE ]; then
            echo ""
            header_message "Restart Requested (Exit Code 42)"
            echo "Restarting PixEagle in 2 seconds..."
            echo "This restart was triggered by the configuration manager."
            sleep 2
            echo ""
            continue
        elif [ $exit_code -eq 0 ]; then
            echo "PixEagle main script executed successfully."
            break
        else
            echo "PixEagle exited with error code: $exit_code"
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
