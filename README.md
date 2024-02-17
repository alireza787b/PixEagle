
# PixEagle

## Overview

PixEagle is an innovative project designed to enhance drone control and tracking capabilities. It emphasizes modularity, efficiency, and expandability, integrating advanced tracking technologies with drone control systems. The project leverages cutting-edge AI and computer vision techniques to achieve precise object tracking and drone navigation.

## Project Directory Structure

- `README.md`: Project overview and documentation.
- `requirements.txt`: Lists the project dependencies.
- `resources/`: Contains test video files for development and testing.
- `setup_pytorch.sh`: Script to set up PyTorch environment.
- `src/`: Source code directory.
  - `main.py`: Entry point of the application.
  - `test_Ver.py`: Test script for verification.
  - `classes/`: Contains core classes.
    - `app_controller.py`: Orchestrates the application flow.
    - `parameters.py`: Manages configuration settings.
    - `position_estimator.py`: Implements position estimation.
    - `segmentor.py`: Handles object segmentation.
    - `tracker.py`: Facilitates object tracking.
    - `video_handler.py`: Manages video input sources.

## Key Components

### AppController
Central controller that manages the application's main functionalities, including tracking and segmentation.

### Parameters
Stores and manages all configuration settings, including video source and tracking parameters.

### PositionEstimator
Utilizes Kalman filters for accurate position estimation of tracked objects.

### Segmentor
Implements segmentation algorithms to refine object tracking, supporting algorithms like GrabCut.

### Tracker
Employs OpenCV for object tracking, allowing for dynamic ROI selection based on user input.

### VideoHandler
Handles video inputs from various sources, such as video files, USB cameras, and streaming URLs.

## Getting Started

To set up the PixEagle project, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/alireza787b/PixEagle.git
   ```
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the setup script for PyTorch (if necessary):
   ```bash
   ./setup_pytorch.sh
   ```
4. Execute the main application:
   ```bash
   python src/main.py
   ```

## Contribution Guidelines

We welcome contributions from developers, researchers, and enthusiasts in drone technology, AI, and robotics. You can contribute by checking out current issues, discussing your ideas, or submitting pull requests with new features or improvements.

## Project Status

PixEagle is under active development, focusing on leveraging PX4 for flight control, incorporating AI for smart decision-making, and utilizing advanced tracking for precise object interaction.


