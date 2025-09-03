# src/classes/telemetry_handler.py
import logging
import socket
import json
from datetime import datetime, timedelta
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType

class TelemetryHandler:
    def __init__(self, app_controller, tracking_started_flag):
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
        self.app_controller = app_controller
        self.tracker = self.app_controller.tracker
        self.follower = self.app_controller.follower
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
        Get the latest tracker telemetry data using the enhanced flexible schema.
        
        Returns:
            dict: The tracker telemetry data with backwards compatibility.
        """
        timestamp = datetime.utcnow().isoformat()
        tracker_started = self.tracking_started_flag()
        
        try:
            # Try to get structured tracker output
            if hasattr(self.app_controller, 'get_tracker_output'):
                tracker_output = self.app_controller.get_tracker_output()
                if tracker_output:
                    return self._format_tracker_data(tracker_output, timestamp, tracker_started)
            
            # Fallback to legacy method for backwards compatibility
            return self._get_legacy_tracker_data(timestamp, tracker_started)
            
        except Exception as e:
            logging.error(f"Error getting tracker data: {e}")
            return self._get_legacy_tracker_data(timestamp, tracker_started)
    
    def _format_tracker_data(self, tracker_output: TrackerOutput, timestamp: str, tracker_started: bool) -> dict:
        """
        Format structured TrackerOutput for telemetry with enhanced metadata.
        
        Args:
            tracker_output (TrackerOutput): Structured tracker data
            timestamp (str): Current timestamp
            tracker_started (bool): Tracking status
            
        Returns:
            dict: Formatted telemetry data
        """
        # Base telemetry data with backwards compatibility
        data = {
            # Legacy fields for backwards compatibility
            'bounding_box': tracker_output.normalized_bbox,
            'center': tracker_output.position_2d,
            'timestamp': timestamp,
            'tracker_started': tracker_started,
            
            # Enhanced structured data
            'tracker_data': {
                'data_type': tracker_output.data_type.value,
                'tracker_id': tracker_output.tracker_id,
                'tracking_active': tracker_output.tracking_active,
                'confidence': tracker_output.confidence,
                'timestamp': tracker_output.timestamp
            }
        }
        
        # Add data type specific information
        if tracker_output.data_type == TrackerDataType.POSITION_2D:
            data['tracker_data'].update({
                'position_2d': tracker_output.position_2d,
                'bbox_pixel': tracker_output.bbox,
                'normalized_bbox': tracker_output.normalized_bbox
            })
            
        elif tracker_output.data_type == TrackerDataType.POSITION_3D:
            data['tracker_data'].update({
                'position_3d': tracker_output.position_3d,
                'position_2d': tracker_output.position_3d[:2] if tracker_output.position_3d else None,
                'depth': tracker_output.position_3d[2] if tracker_output.position_3d else None
            })
            
        elif tracker_output.data_type == TrackerDataType.ANGULAR:
            data['tracker_data'].update({
                'angular': tracker_output.angular,
                'bearing': tracker_output.angular[0] if tracker_output.angular else None,
                'elevation': tracker_output.angular[1] if tracker_output.angular else None
            })
            
        elif tracker_output.data_type == TrackerDataType.MULTI_TARGET:
            data['tracker_data'].update({
                'targets': tracker_output.targets,
                'target_count': len(tracker_output.targets) if tracker_output.targets else 0,
                'selected_target_id': tracker_output.target_id
            })
        
        # Add velocity data if available
        if tracker_output.velocity:
            data['tracker_data']['velocity'] = {
                'vx': tracker_output.velocity[0],
                'vy': tracker_output.velocity[1],
                'magnitude': (tracker_output.velocity[0]**2 + tracker_output.velocity[1]**2)**0.5
            }
        
        # Add quality metrics if available
        if tracker_output.quality_metrics:
            data['tracker_data']['quality_metrics'] = tracker_output.quality_metrics
        
        # Add capabilities information
        if hasattr(self.app_controller, 'get_tracker_capabilities'):
            capabilities = self.app_controller.get_tracker_capabilities()
            if capabilities:
                data['tracker_data']['capabilities'] = capabilities
        
        return data
    
    def _get_legacy_tracker_data(self, timestamp: str, tracker_started: bool) -> dict:
        """
        Fallback method for legacy tracker data extraction.
        
        Args:
            timestamp (str): Current timestamp
            tracker_started (bool): Tracking status
            
        Returns:
            dict: Legacy format tracker data
        """
        return {
            'bounding_box': getattr(self.tracker, 'normalized_bbox', None),
            'center': getattr(self.tracker, 'normalized_center', None),
            'timestamp': timestamp,
            'tracker_started': tracker_started,
            'tracker_data': {
                'data_type': 'position_2d',
                'tracker_id': 'legacy_tracker',
                'tracking_active': tracker_started,
                'confidence': getattr(self.tracker, 'confidence', None),
                'legacy_mode': True
            }
        }

    def get_follower_data(self):
        """
        Get the latest follower telemetry data using the enhanced unified interface.
        
        Returns:
            dict: The follower telemetry data.
        """
        if self.follower is not None:
            try:
                # Use the enhanced telemetry interface
                telemetry = self.follower.get_follower_telemetry() if Parameters.ENABLE_FOLLOWER_TELEMETRY else {}
                
                # Add application-level information
                telemetry['following_active'] = self.app_controller.following_active
                
                # Use the new unified interface to get profile name
                if hasattr(self.follower, 'get_display_name'):
                    telemetry['profile_name'] = self.follower.get_display_name()
                elif hasattr(self.follower, 'follower') and hasattr(self.follower.follower, 'get_display_name'):
                    telemetry['profile_name'] = self.follower.follower.get_display_name()
                else:
                    # Fallback for older interface
                    telemetry['profile_name'] = getattr(self.follower, 'mode', 'Unknown')
                
                return telemetry
                
            except Exception as e:
                logging.error(f"Error getting follower telemetry: {e}")
                return {
                    'error': str(e),
                    'following_active': self.app_controller.following_active,
                    'profile_name': 'Error',
                    'timestamp': datetime.utcnow().isoformat()
                }
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
        # logging.debug(f"Latest tracker data: {self.latest_tracker_data}")
        # logging.debug(f"Latest follower data: {self.latest_follower_data}")


