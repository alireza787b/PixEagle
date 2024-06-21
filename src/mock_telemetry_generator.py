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

import asyncio
import json
import random
import signal
import sys
from datetime import datetime
from aiohttp import web
from flask import Flask, jsonify, Response, request
from flask_cors import CORS
import threading
import time
from simple_pid import PID
from classes.parameters import Parameters

app = Flask(__name__)
CORS(app)

# Initialize global variables
current_center = [0, 0]  # Initial center of the bounding box
bounding_box_size = [0.2, 0.2]  # Width and height of the bounding box
velocities = {'vel_x': 0, 'vel_y': 0, 'vel_z': 0}  # Initial velocities

# Initialize PID controllers
pid_x = PID(1.0, 0.1, 0.05, setpoint=0)
pid_y = PID(1.0, 0.1, 0.05, setpoint=0)
pid_z = PID(1.0, 0.1, 0.05, setpoint=0)

pid_x.output_limits = (-5, 5)  # Velocity limits in m/s
pid_y.output_limits = (-5, 5)
pid_z.output_limits = (-5, 5)

def normalize(value, min_value, max_value):
    return (value - min_value) / (max_value - min_value) * 2 - 1

def move_center():
    """
    Simulate movement of the bounding box center.
    """
    global current_center
    max_move = 0.05
    current_center[0] += random.uniform(-max_move, max_move)
    current_center[1] += random.uniform(-max_move, max_move)
    # Keep center within normalized bounds
    current_center[0] = max(-1, min(1, current_center[0]))
    current_center[1] = max(-1, min(1, current_center[1]))

def generate_tracker_data():
    move_center()
    bounding_box = [
        current_center[0] - bounding_box_size[0] / 2,  # x_min
        -current_center[1] - bounding_box_size[1] / 2, # y_min (inverted)
        bounding_box_size[0],                          # width
        bounding_box_size[1]                           # height
    ]
    center = [current_center[0], -current_center[1]]  # Inverted y-coordinate
    return {
        'bounding_box': bounding_box,
        'center': center,
        'timestamp': datetime.utcnow().isoformat(),
        'tracker_started': True
    }

def update_velocities():
    """
    Update follower velocities to follow the center movement.
    """
    global velocities

    target_x, target_y = current_center
    error_x = target_x
    error_y = -target_y  # Invert y for consistency

    velocities['vel_x'] = pid_x(error_y)
    velocities['vel_y'] = pid_y(error_x)
    velocities['vel_z'] = pid_z(-target_y)  # Simple control for descent

def generate_follower_data():
    update_velocities()
    return {
        'vel_x': velocities['vel_x'],
        'vel_y': velocities['vel_y'],
        'vel_z': velocities['vel_z'],
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'active'
    }

@app.route('/telemetry/tracker_data', methods=['GET'])
def tracker_data():
    data = generate_tracker_data()
    print(f"Generated Tracker Data: {data}")
    return jsonify(data)

@app.route('/telemetry/follower_data', methods=['GET'])
def follower_data():
    data = generate_follower_data()
    print(f"Generated Follower Data: {data}")
    return jsonify(data)

@app.route('/video_feed', methods=['GET'])
def video_feed():
    def generate():
        while True:
            time.sleep(1)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + b'\xFF\xD8\xFF' + b'\r\n')
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

def start_mock_server():
    app.run(host=Parameters.HTTP_STREAM_HOST, port=Parameters.HTTP_STREAM_PORT)

def signal_handler(signal, frame):
    print('Shutting down gracefully...')
    sys.exit(0)

if __name__ == "__main__":
    print("Starting Mock Telemetry Generator...")
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    threading.Thread(target=start_mock_server).start()
    while True:
        time.sleep(1)
        move_center()
        update_velocities()
        print(f"Current Center: {current_center}, Velocities: {velocities}")
