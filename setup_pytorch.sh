#!/bin/bash

# PyTorch Setup Script for macOS, Linux, Windows (WSL), and Raspberry Pi
# Usage:
#   ./setup_pytorch.sh [cpu|gpu]

# Determine the architecture
ARCH=$(uname -m)
OS=$(uname -s)

# Default to CPU if no argument is provided
TARGET=${1:-cpu}

install_pytorch_linux() {
  if [ "$TARGET" == "gpu" ]; then
    echo "Installing PyTorch with GPU support for Linux..."
    pip3 install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu113
  else
    echo "Installing PyTorch with CPU support for Linux..."
    pip3 install torch torchvision torchaudio
  fi
}

install_pytorch_mac() {
  if [ "$TARGET" == "gpu" ]; then
    echo "GPU support is not available for macOS. Installing CPU version..."
  fi
  echo "Installing PyTorch with CPU support for macOS..."
  pip3 install torch torchvision torchaudio
}

install_pytorch_windows() {
  if [ "$TARGET" == "gpu" ]; then
    echo "Installing PyTorch with GPU support for Windows (WSL)..."
    pip3 install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu113
  else
    echo "Installing PyTorch with CPU support for Windows (WSL)..."
    pip3 install torch torchvision torchaudio
  fi
}

install_pytorch_raspberrypi() {
  echo "PyTorch installation for Raspberry Pi might require a specific wheel or building from source due to ARM architecture."
  echo "Please check the PyTorch forums or the official website for the latest instructions on installing PyTorch on ARM devices."
  # Example for a specific PyTorch version (ensure compatibility with your device and Python version)
  # pip3 install https://<URL to compatible wheel>
}

# Installation logic based on OS and architecture
case $OS in
  "Linux")
    if [ "$ARCH" == "x86_64" ]; then
      install_pytorch_linux
    elif [ "$ARCH" == "armv7l" ] || [ "$ARCH" == "aarch64" ]; then
      install_pytorch_raspberrypi
    else
      echo "Unsupported architecture for Linux."
    fi
    ;;
  "Darwin")
    install_pytorch_mac
    ;;
  *)
    echo "Unsupported operating system. This script supports macOS, Linux, and Raspberry Pi."
    ;;
esac
