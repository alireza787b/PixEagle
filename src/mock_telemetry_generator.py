# src/mock_telemetry_generator.py
"""
Mock Telemetry Generator

This script generates simulated telemetry data for a tracking and follower system.
It runs a Flask server to serve the generated telemetry data as JSON responses.
The data includes a normalized bounding box and velocities to simulate realistic motion.

- OpenCV:
  - Default: Top-left (0, 0)
  - Normalized: Center (0, 0), Top-left (-1, 1), Bottom-right (1, -1)

- Chart.js:
  - Normalized: Center (0, 0), Top-left (-1, 1), Bottom-right (1, -1)

Axis Definitions:
- Both systems use normalized coordinates, but the y-axis needs to be inverted for Chart.js.
- OpenCV coordinates are typically in a range relative to the frame, but we normalize to a range of [-1, 1].

Transformation and Conversion:
- Center Point:
  - Inverted y-coordinate to match Chart.js: { x: center[0], y: center[1] * -1 }

- Bounding Box:
  - Provided as [x, y, width, height] in OpenCV
  - To correctly scale the bounding box for Chart.js, we need to:
    - Double the width and height for the normalized range.
    - Invert the y-coordinates.
  - Transformed Coordinates:
    - Top-left: { x: x, y: -y }
    - Top-right: { x: x + 2*width, y: -y }
    - Bottom-right: { x: x + 2*width, y: -y - 2*height }
    - Bottom-left: { x: x, y: -y - 2*height }
"""
import logging
from flask import Flask, jsonify, Response
from flask_cors import CORS
import threading
import time
import random
from datetime import datetime
import signal
import sys
from simple_pid import PID
from classes.parameters import Parameters

# Configuring logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app)

# Initialize global variables for telemetry simulation
current_center = [0, 0]
bounding_box_size = [0.2, 0.2]
velocities = {'vel_x': 0, 'vel_y': 0, 'vel_z': 0}

# Setup PID controllers
pid_controllers = {
    'x': PID(1.0, 0.1, 0.05, setpoint=0, output_limits=(-5, 5)),
    'y': PID(1.0, 0.1, 0.05, setpoint=0, output_limits=(-5, 5)),
    'z': PID(1.0, 0.1, 0.05, setpoint=0, output_limits=(-5, 5))
}

def normalize(value, min_value=-1, max_value=1):
    """ Normalize a value to the range [-1, 1] """
    return (value - min_value) / (max_value - min_value) * 2 - 1

def move_center():
    """ Simulate movement of the center of the bounding box """
    global current_center
    max_move = 0.05
    current_center = [max(-1, min(1, current_center[i] + random.uniform(-max_move, max_move))) for i in range(2)]

def generate_telemetry_data():
    """ Generate the bounding box and center telemetry data """
    move_center()
    x, y = current_center
    return {
        'bounding_box': [x - bounding_box_size[0] / 2, -y - bounding_box_size[1] / 2, bounding_box_size[0], bounding_box_size[1]],
        'center': [x, -y],
        'timestamp': datetime.utcnow().isoformat(),
        'tracker_started': True
    }

def update_velocities():
    """ Update velocities based on PID controllers """
    global velocities
    target_x, target_y = current_center
    velocities['vel_x'] = pid_controllers['x'](target_x)
    velocities['vel_y'] = pid_controllers['y'](-target_y)
    velocities['vel_z'] = pid_controllers['z'](-target_y)

@app.route('/telemetry/tracker_data', methods=['GET'])
def tracker_data():
    data = generate_telemetry_data()
    logging.info(f"Generated Tracker Data: {data}")
    return jsonify(data)

@app.route('/telemetry/follower_data', methods=['GET'])
def follower_data():
    update_velocities()
    data = {
        'vel_x': velocities['vel_x'],
        'vel_y': velocities['vel_y'],
        'vel_z': velocities['vel_z'],
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'active'
    }
    logging.info(f"Generated Follower Data: {data}")
    return jsonify(data)

def run_server():
    app.run(host=Parameters.HTTP_STREAM_HOST, port=Parameters.HTTP_STREAM_PORT)

def graceful_shutdown(signal, frame):
    logging.info('Shutting down gracefully...')
    sys.exit(0)

if __name__ == "__main__":
    logging.info("Starting Mock Telemetry Generator...")
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        graceful_shutdown(None, None)
