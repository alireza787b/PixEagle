# src/classes/telemetry_handler.py
import logging
import socket
import json
from datetime import datetime, timedelta
from classes.parameters import Parameters

class TelemetryHandler:
    def __init__(self, tracker, follower, tracking_started_flag):
        """
        Initialize the TelemetryHandler with necessary parameters and dependencies.
        
        Args:
            tracker (Tracker): An instance of the tracker to gather data from.
            follower (Follower): An instance of the follower to gather data from.
            tracking_started_flag (callable): A callable that returns the current tracking state.
        """
        self.host = Parameters.UDP_HOST
        self.port = Parameters.UDP_PORT
        self.send_rate = Parameters.TELEMETRY_SEND_RATE
        self.enable_udp = Parameters.ENABLE_UDP_STREAM

        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_address = (self.host, self.port)
        self.send_interval = 1.0 / self.send_rate  # Convert rate to interval in seconds

        self.last_sent_time = datetime.utcnow()
        self.tracker = tracker
        self.follower = follower
        self.tracking_started_flag = tracking_started_flag  # Store the callable
        self.latest_tracker_data = {}
        self.latest_follower_data = {}

    def should_send_telemetry(self):
        """
        Check if the telemetry data should be sent based on the send interval.
        
        Returns:
            bool: True if the telemetry data should be sent, False otherwise.
        """
        current_time = datetime.utcnow()
        return (current_time - self.last_sent_time).total_seconds() >= self.send_interval

    def get_tracker_data(self):
        """
        Get the latest tracker telemetry data.
        
        Returns:
            dict: The tracker telemetry data.
        """
        timestamp = datetime.utcnow().isoformat()
        tracker_started = self.tracking_started_flag()  # Use the callable to check if tracking is started
        return {
            'bounding_box': self.tracker.normalized_bbox,
            'center': self.tracker.normalized_center,
            'timestamp': timestamp,
            'tracker_started': tracker_started
        }

    def get_follower_data(self):
        """
        Get the latest follower telemetry data.
        
        Returns:
            dict: The follower telemetry data.
        """
        if self.follower is not None:
            telemetry = self.follower.get_follower_telemetry() if Parameters.ENABLE_FOLLOWER_TELEMETRY else {}
            telemetry['following_active'] = self.follower.following_active
            return telemetry
        return {}

    def gather_telemetry_data(self):
        """
        Gather telemetry data from all enabled sources.
        
        Returns:
            dict: A dictionary containing telemetry data from all sources.
        """
        data = {
            'tracker_data': self.get_tracker_data(),
            'follower_data': self.get_follower_data(),
        }
        return data

    def send_telemetry(self):
        """
        Send the telemetry data via UDP if conditions are met and update the latest telemetry data.
        """
        if self.should_send_telemetry() and self.enable_udp:
            data = self.gather_telemetry_data()
            message = json.dumps(data)
            self.udp_socket.sendto(message.encode('utf-8'), self.server_address)
            self.last_sent_time = datetime.utcnow()
            logging.debug(f"Telemetry sent: {data}")
        
        # Update the latest telemetry data regardless of UDP sending
        self.latest_tracker_data = self.get_tracker_data()
        if Parameters.ENABLE_FOLLOWER_TELEMETRY:
            self.latest_follower_data = self.get_follower_data()
        logging.debug(f"Latest tracker data: {self.latest_tracker_data}")
        logging.debug(f"Latest follower data: {self.latest_follower_data}")

