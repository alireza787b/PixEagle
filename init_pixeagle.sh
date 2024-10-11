#!/bin/bash

# init_pixeagle.sh
# Initialization script for the PixEagle project
# This script sets up the environment for PixEagle, including Python virtual environment,
# installs required Python packages, and handles the configuration files.
# It also informs the user about additional dependencies like Node.js and npm.

# Function to display the Pix Eagle banner
display_banner() {
    echo -e "\n██████╗ ██╗  ██████╗ ███████╗     ███████╗ █████╗  ██████╗ ██╗     ███████╗"
    echo -e "██╔══██╗██║ ██╔══██╗██╔════╝     ██╔════╝██╔══██╗██╔════╝ ██║     ██╔════╝"
    echo -e "██████╔╝██║ ██║       ╔╝█████╗       █████╗  ███████║██║  ███╗██║     █████╗  "
    echo -e "██╔═══╝ ██║ ██║ ██╔══██╗██╔══╝       ██╔══╝  ██╔══██║██║   ██║██║     ██╔══╝  "
    echo -e "██║     ██║ ██║ ██████╔╝███████╗     ███████╗██║  ██║╚██████╔╝███████╗███████╗"
    echo -e "╚═╝     ╚═╝╚═╝        ╚═════╝ ╚══════╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝\n"
    echo -e "Welcome to Pix Eagle Initialization Script\n"
    echo -e "For more information and latest documentation, visit:"
    echo -e "👉 GitHub: https://github.com/alireza787b/PixEagle\n"
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

# Function to create dashboard config
create_dashboard_config() {
    cp "$DASHBOARD_DEFAULT_CONFIG" "$DASHBOARD_USER_CONFIG"
    echo -e "\n✅ Created '$DASHBOARD_USER_CONFIG' from '$DASHBOARD_DEFAULT_CONFIG'."
}

# Function to generate .env file from dashboard config.yaml
generate_dashboard_env() {
    echo -e "🔄 Generating '.env' file in '$DASHBOARD_DIR' from '$DASHBOARD_USER_CONFIG'..."
    source venv/bin/activate
    python3 << EOF
import yaml
import os

config_file = "$DASHBOARD_USER_CONFIG"
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
DASHBOARD_USER_CONFIG="$DASHBOARD_DIR/config.yaml"

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

# Check if dashboard user config exists
if [ ! -f "$DASHBOARD_USER_CONFIG" ]; then
    echo -e "⚙️  Dashboard configuration file '$DASHBOARD_USER_CONFIG' does not exist."
    create_dashboard_config
else
    echo -e "⚠️  Dashboard configuration file '$DASHBOARD_USER_CONFIG' already exists."
    echo -e "Do you want to reset it to default values?"
    echo -e "⚠️  Warning: This will overwrite your current dashboard configuration and cannot be undone."
    read -p "Type 'yes' to reset or 'no' to keep your existing dashboard configuration [yes/no]: " choice
    case "$choice" in
        yes|Yes|Y|y )
            create_dashboard_config
            echo -e "✅ Dashboard configuration file '$DASHBOARD_USER_CONFIG' has been reset to default values."
            ;;
        no|No|N|n )
            echo -e "👍 Keeping existing dashboard configuration file '$DASHBOARD_USER_CONFIG'."
            ;;
        * )
            echo -e "❌ Invalid input. Please run the script again and type 'yes' or 'no'."
            exit 1
            ;;
    esac
fi

# Generate .env file from dashboard config.yaml
generate_dashboard_env

echo -e "\n🎉 Initialization complete."
echo -e "🚀 You can now start using PixEagle. Happy flying!\n"

echo -e "📢 Note:"
echo -e "👉 You might need to install Node.js and npm if they are not already installed."
echo -e "   You can install them by running 'sudo apt install nodejs npm' or refer to the Node.js website."
echo -e "👉 Please edit '$USER_CONFIG' and '$DASHBOARD_USER_CONFIG' to configure settings according to your system."
