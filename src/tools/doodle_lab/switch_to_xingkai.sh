#!/bin/bash
# Script: switch_to_xingkai.sh
# Author: Alireza Ghaderi
# Date: Dec 2024
# Description: This script configures the Ethernet interface to use a static IP for XK-F301E.
#              It ensures the Wi-Fi interface remains the default for internet access.
#              Additionally, it performs both local and internet connectivity tests.

# ============================
# User-configurable parameters
# ============================

INTERFACE="eth0"                      # Network interface to be configured (Ethernet)
STATIC_IP="192.168.0.226/24"          # Static IP address for Ethernet
# GATEWAY="192.168.0.251"             # Gateway for Doodle Labs network (Removed to prevent overriding Wi-Fi gateway)
LOCAL_PING_TARGET="192.168.0.1"       # Local Ethernet gateway or another local device IP
INTERNET_PING_TARGET="8.8.8.8"        # External IP for internet connectivity test (Google DNS)
CONNECTION_NAME="Wired connection 1"  # Name of the NetworkManager connection (adjust if needed)

# ============================
# Function Definitions
# ============================

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

# ============================
# Start of the Script
# ============================

info "Starting the process to switch to Doodle Labs Network..."

# =====================================
# 1. Flush Current IP Configuration
# =====================================

info "Flushing current IP configuration on $INTERFACE..."
if sudo ip addr flush dev $INTERFACE; then
    success "Successfully flushed IP configuration."
else
    error "Failed to flush IP configuration."
    exit 1
fi

# =====================================
# 2. Set Static IP Configuration
# =====================================

info "Setting static IP to $STATIC_IP on $INTERFACE..."
if sudo ip addr add $STATIC_IP dev $INTERFACE && sudo ip link set $INTERFACE up; then
    success "Static IP configuration applied successfully."
else
    error "Failed to set static IP configuration."
    exit 1
fi

# =====================================
# 3. Remove Default Route via Ethernet
# =====================================

# === Removed Section: Adding default route via Ethernet gateway ===
# Explanation:
# Adding a default route via the Ethernet gateway overrides the default route set by the Wi-Fi interface.
# This causes all internet traffic to attempt to go through Ethernet, which may not have internet access,
# leading to loss of internet connectivity.
#
# # Adding default route via gateway $GATEWAY...
# if sudo ip route add default via $GATEWAY; then
#     success "Default route added successfully."
# else
#     error "Failed to add default route. Please check your gateway settings."
#     exit 1
# fi

success "Default route via Ethernet is not set to preserve Wi-Fi internet access."

# =====================================
# 4. Make Static IP Configuration Persistent
# =====================================

info "Attempting to make the static IP configuration persistent across reboots..."
if systemctl is-active --quiet NetworkManager; then
    # Using NetworkManager to persist the settings without setting a gateway
    if sudo nmcli connection modify "$CONNECTION_NAME" ipv4.addresses "$STATIC_IP" ipv4.gateway "" ipv4.method manual && \
       sudo nmcli connection modify "$CONNECTION_NAME" connection.autoconnect yes; then
        success "Static IP configuration made persistent via NetworkManager."
    else
        error "Failed to make static IP configuration persistent via NetworkManager."
        prompt_user "Please consider manually configuring the static IP settings or using the ifupdown method."
    fi
elif [ -f /etc/network/interfaces ]; then
    # Using the traditional ifupdown method without gateway
    echo -e "auto $INTERFACE\niface $INTERFACE inet static\n\taddress ${STATIC_IP%/*}\n\tnetmask 255.255.255.0" | sudo tee /etc/network/interfaces.d/$INTERFACE.cfg > /dev/null
    if [ $? -eq 0 ]; then
        success "Static IP configuration made persistent via /etc/network/interfaces."
    else
        error "Failed to make static IP configuration persistent via /etc/network/interfaces."
        prompt_user "Please consider manually configuring the static IP settings."
    fi
else
    prompt_user "Could not find a known network management system. Ensure your network is configured correctly."
fi

# =====================================
# 5. Restart Networking Services
# =====================================

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

# =====================================
# 6. Connectivity Tests
# =====================================

# === Local Connectivity Test ===
info "Testing local Ethernet connectivity by pinging $LOCAL_PING_TARGET..."
if ping -c 4 $LOCAL_PING_TARGET &> /dev/null; then
    success "Successfully connected to the local Ethernet device at $LOCAL_PING_TARGET."
else
    error "Failed to reach $LOCAL_PING_TARGET. Please check your local Ethernet connection."
    prompt_user "Ensure that the local Ethernet device is up and properly configured."
    # Not exiting here as internet connectivity is more critical
fi

# === Internet Connectivity Test ===
info "Testing internet connectivity by pinging $INTERNET_PING_TARGET..."
if ping -c 4 $INTERNET_PING_TARGET &> /dev/null; then
    success "Successfully connected to the internet via Wi-Fi."
else
    error "Failed to reach $INTERNET_PING_TARGET. Please check your internet connection."
    prompt_user "Ensure that your Wi-Fi is connected and has internet access."
    exit 1
fi

# =====================================
# 7. Final Report
# =====================================

info "Process complete. Your device is now configured for local Ethernet and internet access via Wi-Fi."
