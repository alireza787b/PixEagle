#!/bin/bash
# Script: switch_to_internet.sh
# Author: Alireza Ghaderi
# Date: August 2024
# Description: This script configures the Ethernet interface to use DHCP for internet access.
#              It also performs a connectivity test to ensure the setup is correct.

# User-configurable parameters
INTERFACE="eth0" # Network interface to be configured
PING_TARGET="8.8.8.8" # IP address to ping (Google DNS server for testing internet connection)

# Function to display information to the user
function info {
    echo -e "\e[34m[INFO]\e[0m $1"
}

# Function to display success messages
function success {
    echo -e "\e[32m[SUCCESS]\e[0m $1"
}

# Function to display error messages
function error {
    echo -e "\e[31m[ERROR]\e[0m $1"
}

# Function to prompt user action
function prompt_user {
    echo -e "\e[33m[NOTE]\e[0m $1"
}

# Start of the script
info "Starting the process to switch to Internet via DHCP..."

# Flushing current IP configuration
info "Flushing current IP configuration on $INTERFACE..."
if sudo ip addr flush dev $INTERFACE; then
    success "Successfully flushed IP configuration."
else
    error "Failed to flush IP configuration."
    exit 1
fi

# Requesting DHCP lease
info "Requesting a new DHCP lease on $INTERFACE..."
if sudo dhclient $INTERFACE; then
    success "DHCP lease obtained successfully."
else
    error "Failed to obtain DHCP lease. Please check your connection."
    exit 1
fi

# Restarting networking services (handling different cases)
info "Attempting to restart networking services..."
if systemctl is-active --quiet NetworkManager; then
    if sudo systemctl restart NetworkManager; then
        success "NetworkManager restarted successfully."
    else
        error "Failed to restart NetworkManager."
        prompt_user "Please consider manually restarting NetworkManager or reconfiguring your network interface."
    fi
elif systemctl is-active --quiet systemd-networkd; then
    if sudo systemctl restart systemd-networkd; then
        success "systemd-networkd restarted successfully."
    else
        error "Failed to restart systemd-networkd."
        prompt_user "Please consider manually restarting systemd-networkd or reconfiguring your network interface."
    fi
else
    prompt_user "No known networking service found. Skipping service restart. Ensure your network is configured correctly."
fi

# Testing internet connectivity
info "Testing internet connectivity by pinging $PING_TARGET..."
if ping -c 4 $PING_TARGET &> /dev/null; then
    success "Internet connection is active."
else
    error "Failed to reach $PING_TARGET. Please check your network connection."
    prompt_user "Ensure that your router or internet gateway is up and properly configured."
    exit 1
fi

info "Process complete. Your device is now connected to the Internet via DHCP."
