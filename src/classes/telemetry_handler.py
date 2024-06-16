
import socket
import json
from datetime import datetime, timedelta
from classes.parameters import Parameters

class TelemetryHandler:
    def __init__(self, controller):
        self.host = Parameters.UDP_HOST
        self.port = Parameters.UDP_PORT
        self.send_rate =  Parameters.TELEMETRY_SEND_RATE
        
        
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_address = (self.host, self.port)
        self.send_interval = 1.0 / self.send_rate  # Convert rate to interval in seconds

        self.last_sent_time = datetime.utcnow()
        self.controller = controller

    def should_send_telemetry(self):
        current_time = datetime.utcnow()
        return (current_time - self.last_sent_time).total_seconds() >= self.send_interval

    def send_telemetry(self):
        if self.should_send_telemetry():
            timestamp = datetime.utcnow().isoformat()
            tracker_started = self.controller.tracking_started is not None
            data = {
                'bounding_box': self.controller.tracker.normalized_bbox,
                'center': self.controller.tracker.normalized_center,
                'timestamp': timestamp,
                'tracker_started': tracker_started
            }
            message = json.dumps(data)
            self.udp_socket.sendto(message.encode('utf-8'), self.server_address)
            self.last_sent_time = datetime.utcnow()
