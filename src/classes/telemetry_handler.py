# src/classes/telemetry_handler.py

import socket
import json
from datetime import datetime
from classes.parameters import Parameters

class TelemetryHandler:
    def __init__(self, controller):
        self.controller = controller
        self.send_rate = Parameters.TELEMETRY_SEND_RATE
        self.send_interval = 1.0 / self.send_rate  # Convert rate to interval in seconds
        self.last_sent_time = datetime.utcnow()
        self.latest_tracker_data = None
        self.latest_follower_data = None

        if Parameters.ENABLE_UDP_STREAM:
            self.host = Parameters.UDP_HOST
            self.port = Parameters.UDP_PORT
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.server_address = (self.host, self.port)

    def should_send_telemetry(self):
        current_time = datetime.utcnow()
        return (current_time - self.last_sent_time).total_seconds() >= self.send_interval

    def gather_tracker_data(self):
        timestamp = datetime.utcnow().isoformat()
        tracker_started = self.controller.tracking_started is not None
        data = {
            'bounding_box': self.controller.tracker.normalized_bbox,
            'center': self.controller.tracker.normalized_center,
            'timestamp': timestamp,
            'tracker_started': tracker_started
        }
        self.latest_tracker_data = data
        return data

    def gather_follower_data(self):
        timestamp = datetime.utcnow().isoformat()
        # Placeholder example; adjust according to actual follower data structure
        data = {
            'follower_status': self.controller.following_active,
            'timestamp': timestamp
        }
        self.latest_follower_data = data
        return data

    def send_telemetry(self):
        if self.should_send_telemetry():
            tracker_data = self.gather_tracker_data()
            follower_data = self.gather_follower_data()
            
            if Parameters.ENABLE_UDP_STREAM:
                message = json.dumps({'tracker': tracker_data, 'follower': follower_data})
                self.udp_socket.sendto(message.encode('utf-8'), self.server_address)
                
            self.last_sent_time = datetime.utcnow()
