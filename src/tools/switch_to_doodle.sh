#!/bin/bash
# Script: switch_to_doodle.sh
# Author: Alireza Ghaderi
# Date: August 2024
# Description: This script configures the Ethernet interface to use a static IP for Doodle Labs communication.
#              It also performs a connectivity test to ensure the setup is correct.

# User-configurable parameters
INTERFACE="eth0" # Network interface to be configured
STATIC_IP="10.223.80.36/16" # Static IP address (Subnet /16: 255.255.0.0)
GATEWAY="10.223.80.34" # Gateway for Doodle Labs network
PING_TARGET="$GATEWAY" # IP address to ping (Doodle Labs gateway for testing connection)

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
info "Starting the process to switch to Doodle Labs Network..."

# Flushing current IP configuration
info "Flushing current IP configuration on $INTERFACE..."
if sudo ip addr flush dev $INTERFACE; then
    success "Successfully flushed IP configuration."
else
    error "Failed to flush IP configuration."
    exit 1
fi

# Setting static IP configuration
info "Setting static IP to $STATIC_IP with gateway $GATEWAY on $INTERFACE..."
if sudo ip addr add $STATIC_IP dev $INTERFACE && sudo ip link set $INTERFACE up; then
    success "Static IP configuration applied successfully."
else
    error "Failed to set static IP configuration."
    exit 1
fi

# Adding default route via gateway
info "Adding default route via gateway $GATEWAY..."
if sudo ip route add default via $GATEWAY; then
    success "Default route added successfully."
else
    error "Failed to add default route. Please check your gateway settings."
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

# Testing connectivity to Doodle Labs network
info "Testing connectivity to Doodle Labs gateway by pinging $PING_TARGET..."
if ping -c 4 $PING_TARGET &> /dev/null; then
    success "Successfully connected to Doodle Labs network."
else
    error "Failed to reach $PING_TARGET. Please check your network configuration."
    prompt_user "Ensure that the GCS node or Doodle Labs gateway is up and properly configured."
    exit 1
fi

info "Process complete. Your device is now configured for Doodle Labs network."
