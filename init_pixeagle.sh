#!/bin/bash

# init_pixeagle.sh
# Initialization script for the PixEagle project
# This script sets up the environment for PixEagle, including Python virtual environment,
# installs required Python packages, and handles the configuration files.
# It also informs the user about additional dependencies like Node.js and npm.

# Function to display the PixEagle banner
display_banner() {
    echo -e "\n██████╗ ██╗  ██████╗ ███████╗     ███████╗ █████╗  ██████╗ ██╗     ███████╗"
    echo -e "██╔══██╗██║ ██╔══██╗██╔════╝     ██╔════╝██╔══██╗██╔════╝ ██║     ██╔════╝"
    echo -e "██████╔╝██║ ██║  █████╗       █████╗  ███████║██║  ███╗██║     █████╗  "
    echo -e "██╔═══╝ ██║ ██║ ██╔══██╗██╔══╝       ██╔══╝  ██╔══██║██║   ██║██║     ██╔══╝  "
    echo -e "██║     ██║ ██║ ██████╔╝███████╗     ███████╗██║  ██║╚██████╔╝███████╗███████╗"
    echo -e "╚═╝     ╚═╝╚═╝        ╚═════╝ ╚══════╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝\n"
    echo -e "Welcome to PixEagle Initialization Script\n"
    echo -e "For more information and latest documentation, visit:"
    echo -e "👉 GitHub: https://github.com/alireza787b/PixEagle\n"
    sleep 1  # Wait for 1 second
}

# Function to check Python version
check_python_version() {
    if ! command -v python3 &> /dev/null
    then
        echo -e "❌ Python 3 is not installed. Please install Python 3.9 or later."
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    REQUIRED_VERSION="3.9"

    if [[ $(echo -e "$PYTHON_VERSION\n$REQUIRED_VERSION" | sort -V | head -n1) = "$REQUIRED_VERSION" ]]; then
        echo -e "✅ Python version $PYTHON_VERSION detected."
    else
        echo -e "❌ Python version $PYTHON_VERSION detected. Python 3.9 or later is required."
        exit 1
    fi
}

# Function to create virtual environment
create_virtualenv() {
    if [ ! -d "venv" ]; then
        echo -e "📁 Virtual environment not found. Creating one..."
        python3 -m venv venv
        echo -e "✅ Virtual environment created."
    else
        echo -e "✅ Virtual environment already exists."
    fi
}

# Function to activate virtual environment and install requirements
install_requirements() {
    source venv/bin/activate
    echo -e "📦 Installing Python dependencies from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
    echo -e "✅ Python dependencies installed."
    deactivate
}

# Function to create config.yaml from config_default.yaml
create_config() {
    cp "$DEFAULT_CONFIG" "$USER_CONFIG"
    echo -e "\n✅ Created '$USER_CONFIG' from '$DEFAULT_CONFIG'."
}

# Function to generate .env file from dashboard env_default.yaml
generate_dashboard_env() {
    echo -e "🔄 Generating '.env' file in '$DASHBOARD_DIR' from '$DASHBOARD_DEFAULT_CONFIG'..."

    # Check if .env file exists
    DASHBOARD_ENV_FILE="$DASHBOARD_DIR/.env"
    if [ -f "$DASHBOARD_ENV_FILE" ]; then
        echo -e "⚠️  .env file '$DASHBOARD_ENV_FILE' already exists."
        echo -e "Do you want to overwrite it with default values?"
        echo -e "⚠️  Warning: This will overwrite your current .env file and cannot be undone."
        read -p "Type 'yes' to overwrite or 'no' to keep your existing .env file [yes/no]: " choice
        case "$choice" in
            yes|Yes|Y|y )
                ;;
            no|No|N|n )
                echo -e "👍 Keeping existing .env file '$DASHBOARD_ENV_FILE'."
                return
                ;;
            * )
                echo -e "❌ Invalid input. Please run the script again and type 'yes' or 'no'."
                exit 1
                ;;
        esac
    fi

    source venv/bin/activate
    python3 << EOF
import yaml
import os

config_file = "$DASHBOARD_DEFAULT_CONFIG"
env_file = os.path.join("$DASHBOARD_DIR", '.env')

with open(config_file, 'r') as f:
    config = yaml.safe_load(f)

with open(env_file, 'w') as f:
    for key, value in config.items():
        f.write(f"{key}={value}\n")
EOF
    deactivate
    echo -e "✅ Generated '.env' file."
}

# Main script starts here
display_banner

# Run apt update
echo -e "🔄 Updating package lists..."
sudo apt update

# Check Python version
check_python_version

# Create virtual environment if not exists
create_virtualenv

# Install requirements
install_requirements

# Define directories and config files
BASE_DIR="$(pwd)"
CONFIG_DIR="$BASE_DIR/configs"
DEFAULT_CONFIG="$CONFIG_DIR/config_default.yaml"
USER_CONFIG="$CONFIG_DIR/config.yaml"

# Inform the user about the base directory
echo -e "\nUsing base directory: '$BASE_DIR'"

# Check if configs directory exists
if [ ! -d "$CONFIG_DIR" ]; then
    echo -e "🗂  Configuration directory '$CONFIG_DIR' does not exist. Creating it now..."
    mkdir -p "$CONFIG_DIR"
    echo -e "✅ Directory '$CONFIG_DIR' created."
fi

# Check if config_default.yaml exists
if [ ! -f "$DEFAULT_CONFIG" ]; then
    echo -e "❌ Error: Default configuration file '$DEFAULT_CONFIG' not found."
    echo -e "Please ensure that '$DEFAULT_CONFIG' exists in the '$CONFIG_DIR' directory."
    exit 1
fi

# Check if config.yaml exists
if [ ! -f "$USER_CONFIG" ]; then
    echo -e "⚙️  User configuration file '$USER_CONFIG' does not exist."
    create_config
else
    echo -e "⚠️  User configuration file '$USER_CONFIG' already exists."
    echo -e "Do you want to reset it to default values?"
    echo -e "⚠️  Warning: This will overwrite your current configuration and cannot be undone."
    read -p "Type 'yes' to reset or 'no' to keep your existing configuration [yes/no]: " choice
    case "$choice" in
        yes|Yes|Y|y )
            create_config
            echo -e "✅ Configuration file '$USER_CONFIG' has been reset to default values."
            ;;
        no|No|N|n )
            echo -e "👍 Keeping existing configuration file '$USER_CONFIG'."
            ;;
        * )
            echo -e "❌ Invalid input. Please run the script again and type 'yes' or 'no'."
            exit 1
            ;;
    esac
fi

# Handle dashboard configuration
DASHBOARD_DIR="$BASE_DIR/dashboard"
DASHBOARD_DEFAULT_CONFIG="$DASHBOARD_DIR/env_default.yaml"

# Check if dashboard directory exists
if [ ! -d "$DASHBOARD_DIR" ]; then
    echo -e "❌ Dashboard directory '$DASHBOARD_DIR' does not exist."
    echo -e "Please ensure that '$DASHBOARD_DIR' exists."
    exit 1
fi

# Check if dashboard default config exists
if [ ! -f "$DASHBOARD_DEFAULT_CONFIG" ]; then
    echo -e "❌ Error: Default dashboard configuration file '$DASHBOARD_DEFAULT_CONFIG' not found."
    echo -e "Please ensure that '$DASHBOARD_DEFAULT_CONFIG' exists in the '$DASHBOARD_DIR' directory."
    exit 1
fi

# Generate .env file from dashboard env_default.yaml
generate_dashboard_env

echo -e "\n🎉 Initialization complete."
echo -e "🚀 You can now start using PixEagle. Happy flying!\n"

echo -e "📢 Note:"
echo -e "👉 You might need to install Node.js and npm if they are not already installed."
echo -e "   Using 'apt install' may install an outdated version."
echo -e "   It's recommended to refer to the official Node.js website and follow the instructions for your operating system:"
echo -e "   https://nodejs.org/en/download/package-manager/"
echo -e "👉 Please edit '$USER_CONFIG' and '$DASHBOARD_DIR/.env' to configure settings according to your system."
