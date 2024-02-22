
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
    - `detector.py`: Base class for object detection.
    - `detector_interface.py`: Interface for detectors.
    - `feature_matching_detector.py`: Implements feature matching for object detection.
    - `parameters.py`: Manages configuration settings.
    - `position_estimator.py`: Implements position estimation.
    - `segmentor.py`: Handles object segmentation.
    - `template_matcher.py`: Implements template matching for object detection.
    - `tracker.py`: Facilitates object tracking.
    - `video_handler.py`: Manages video input sources.


## Key Components
###AppController
Central controller that manages the application's main functionalities, orchestrating the flow between detection, tracking, and video handling.

### Detector and DetectorInterface
Defines the base structure and interface for object detection modules, allowing for extensibility and integration of different detection algorithms.

### FeatureMatchingDetector
Specializes in detecting objects based on feature matching, enhancing the application's ability to recognize objects in various conditions.

### Parameters
Stores and manages all configuration settings, including detection parameters and video source configurations.

### PositionEstimator
Provides algorithms for estimating the position of detected objects, crucial for tracking accuracy.

### Segmentor
Implements advanced segmentation algorithms to improve object detection and tracking in complex scenes.

### TemplateMatcher
Utilizes template matching techniques for object detection, offering a straightforward method for recognizing objects based on stored templates.

### Tracker
Employs advanced tracking algorithms to maintain object identity across frames, essential for continuous monitoring and analysis.

### VideoHandler
Handles video inputs from various sources, including files and cameras, ensuring flexible input options for processing and analysis.

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

## Troubleshooting
Fixing libGL.so.1 Missing Error
If you encounter an ImportError related to libGL.so.1, install the OpenGL libraries with:

```bash
sudo apt-get update
sudo apt-get install -y libgl1-mesa-glx
 ```
 
This is often required for OpenCV's image and video display functionalities.


## Contribution Guidelines

We welcome contributions from developers, researchers, and enthusiasts in drone technology, AI, and robotics. You can contribute by checking out current issues, discussing your ideas, or submitting pull requests with new features or improvements.

## Project Status

PixEagle is under active development, focusing on leveraging PX4 for flight control, incorporating AI for smart decision-making, and utilizing advanced tracking for precise object interaction.


