# PixEagle
# PixEagle Project

## Overview

PixEagle aims to integrate advanced tracking and drone control capabilities with a focus on modularity, efficiency, and expandability. Below is the initial approach to the project structure and class design.

## Project Directory Structure

PixEagle/
├── src/
│   ├── classes/
│   │   ├── video_handler.py # Handles video input from various sources
│   │   ├── drone_controller.py # Manages drone commands and state
│   │   ├── tracker.py # Implements object tracking functionalities
│   │   ├── communicator.py # Handles communication and data reporting
│   │   └── parameters.py # Centralizes configuration settings
│   │
│   └── main.py # Main application logic
│
├── requirements.txt # Project dependencies
└── README.md # Project overview and documentation



## Classes and Responsibilities

### VideoHandler

- **Purpose**: Manages video inputs from different sources (e.g., USB camera, video files, streaming URLs).
- **Functionality**: Dynamically selects video source based on runtime parameters or user input and provides video frames to the application.

### DroneController

- **Purpose**: Controls and monitors the state of the drone, integrating with drone flight software and hardware.
- **Functionality**: Handles takeoff, landing, and in-flight commands, adjusting for tracking and navigation.

### Tracker

- **Purpose**: Facilitates object tracking within the video feed.
- **Functionality**: Allows user interaction for ROI selection and uses OpenCV to track the selected object, reporting its position and deviations.

### Communicator

- **Purpose**: Manages external communication for data reporting and control signals.
- **Functionality**: Could be used for logging, displaying tracking information, or communicating with external systems.

### Parameters

- **Purpose**: Stores and manages all configuration settings for the project.
- **Functionality**: Includes settings for video source selection, tracking parameters, and any other configurable aspects of the project.

## Initial Flow in `main.py`

1. **Initialization**: Start by setting up the `Parameters` to define the project's operational settings.
2. **Video Source Setup**: Initialize `VideoHandler` based on the selected video source from `Parameters`.
3. **User Interaction**: Enable user interaction for selecting an ROI within the video feed, initiating tracking.
4. **Tracking and Reporting**: Utilize `Tracker` to monitor and report the object's position, with `Communicator` managing any necessary output or data communication.


## Project Status: Under Active Development

The PixEagle project is in the early stages of development. Our team is dedicated to building a robust platform that leverages PX4 for flight control, incorporates AI for smart decision-making, and utilizes advanced tracking for precise object following and interaction.

## How to Contribute

We welcome contributions from developers, researchers, and enthusiasts in the fields of drone technology, AI, and robotics. Here's how you can contribute:

- **Check Out Current Issues:** Browse through the issues to find something you're interested in.
- **Discuss Your Ideas:** Have a suggestion? Open an issue to share your ideas with the team.
- **Contribute Code:** Submit a pull request with your changes or new features.

## Setup Instructions

To get started with the PixEagle project, follow these steps:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/alireza787b/PixEagle.git
