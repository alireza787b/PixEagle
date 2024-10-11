#!/bin/bash

# init_pixeagle.sh
# Initialization script for the PixEagle project
# This script checks for the existence of configs/config.ini in the user's home directory
# If it does not exist, it creates it by copying configs/config_default.ini
# If it exists, it warns the user and asks if they want to reset to default values

# Configurable base directory (change this if needed)
BASE_DIR="$HOME/PixEagle"
CONFIG_DIR="$BASE_DIR/configs"
DEFAULT_CONFIG="$CONFIG_DIR/config_default.ini"
USER_CONFIG="$CONFIG_DIR/config.ini"

# Function to create config.ini from config_default.ini
create_config() {
    cp "$DEFAULT_CONFIG" "$USER_CONFIG"
    echo -e "\n✅ Created '$USER_CONFIG' from '$DEFAULT_CONFIG'."
}

# Function to display the Pix Eagle banner
display_banner() {
    echo -e "\n██████╗ ██╗  ██████╗ ███████╗     ███████╗ █████╗  ██████╗ ██╗     ███████╗"
    echo -e "██╔══██╗██║██║ ██╔══██╗██╔════╝     ██╔════╝██╔══██╗██╔════╝ ██║     ██╔════╝"
    echo -e "██████╔╝██║██║       ╔╝█████╗       █████╗  ███████║██║  ███╗██║     █████╗  "
    echo -e "██╔═══╝ ██║██║ ██╔══██╗██╔══╝       ██╔══╝  ██╔══██║██║   ██║██║     ██╔══╝  "
    echo -e "██║     ██║██║ ██████╔╝███████╗     ███████╗██║  ██║╚██████╔╝███████╗███████╗"
    echo -e "╚═╝     ╚═╝╚═╝        ╚═════╝ ╚══════╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝\n"
    echo -e "Welcome to Pix Eagle Initialization Script\n"
    echo -e "For more information and latest documentation, visit:"
    echo -e "👉 GitHub: https://github.com/alireza787b/PixEagle\n"
}
# Main script starts here
display_banner

# Inform the user about the base directory
echo -e "Using base directory: '$BASE_DIR'\n"

# Check if configs directory exists
if [ ! -d "$CONFIG_DIR" ]; then
    echo -e "🗂  Configuration directory '$CONFIG_DIR' does not exist. Creating it now..."
    mkdir -p "$CONFIG_DIR"
    echo -e "✅ Directory '$CONFIG_DIR' created.\n"
fi

# Check if config_default.ini exists
if [ ! -f "$DEFAULT_CONFIG" ]; then
    echo -e "❌ Error: Default configuration file '$DEFAULT_CONFIG' not found."
    echo -e "Please ensure that '$DEFAULT_CONFIG' exists in the '$CONFIG_DIR' directory."
    exit 1
fi

# Check if config.ini exists
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
            echo -e "✅ Configuration file '$USER_CONFIG' has been reset to default values.\n"
            ;;
        no|No|N|n )
            echo -e "👍 Keeping existing configuration file '$USER_CONFIG'.\n"
            ;;
        * )
            echo -e "❌ Invalid input. Please run the script again and type 'yes' or 'no'."
            exit 1
            ;;
    esac
fi

echo -e "🎉 Initialization complete.\n"
echo -e "🚀 You can now start using PixEagle. Happy flying!\n"
