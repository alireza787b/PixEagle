import logging
from datetime import datetime
from typing import Dict

# Set up logging
logger = logging.getLogger(__name__)

# Define profiles for different application modes
SETPOINT_PROFILES = {
    "Ground View": ["vel_x", "vel_y", "vel_z"],
    "Front View": ["vel_x", "vel_y", "vel_z", "yaw_rate"],
    "Aerial Photography": ["pos_x", "pos_y", "pos_z", "yaw_rate"],
    "Attitude Control": ["roll_rate", "pitch_rate", "yaw_rate", "thrust"],
    # More profiles can be added here as needed
}

class SetpointHandler:
    def __init__(self, profile_name: str):
        """
        Initializes the SetpointHandler with the specified application-based profile.
        
        Args:
            profile_name (str): The name of the application profile (e.g., "Ground View", "Front View").
        """
        self.profile_name = profile_name
        self.fields: Dict[str, float] = {}
        
        # Initialize the fields based on the profile
        if profile_name in SETPOINT_PROFILES:
            self.initialize_fields(SETPOINT_PROFILES[profile_name])
            logger.info(f"SetpointHandler initialized with profile: {profile_name}")
        else:
            raise ValueError(f"Profile {profile_name} is not defined.")
        
    def initialize_fields(self, field_names: list):
        """
        Initializes the fields for the given profile.
        
        Args:
            field_names (list): A list of field names to initialize.
        """
        for field in field_names:
            self.fields[field] = 0.0  # Initialize all fields to 0.0
        logger.debug(f"Fields initialized: {self.fields}")
    
    def set_field(self, field_name: str, value: float):
        """
        Sets the value of a specific field in the setpoint.
        
        Args:
            field_name (str): The name of the field to set.
            value (float): The value to assign to the field.
        """
        if field_name in self.fields:
            self.fields[field_name] = value
            logger.debug(f"Setpoint updated: {field_name} = {value}")
        else:
            raise ValueError(f"Field {field_name} is not valid for profile {self.profile_name}")
    
    def get_fields(self) -> Dict[str, float]:
        """
        Returns the current fields of the setpoint.
        
        Returns:
            dict: The current fields of the setpoint.
        """
        logger.debug(f"Retrieving setpoint fields: {self.fields}")
        return self.fields
    
    def report(self) -> str:
        """
        Generates a report of the current setpoint values.
        
        Returns:
            str: A human-readable report of the setpoint values.
        """
        report = f"Setpoint Profile: {self.profile_name}\n"
        for field, value in self.fields.items():
            report += f"{field}: {value}\n"
        logger.info(f"Generated setpoint report: {report}")
        return report

    def reset_setpoints(self):
        """
        Resets all setpoints to their default values (0.0).
        """
        for field in self.fields:
            self.fields[field] = 0.0
        logger.info("All setpoints have been reset to default (0.0)")

    def timestamp_setpoint(self):
        """
        Adds a timestamp to the setpoints for telemetry or logging purposes.
        """
        self.fields["timestamp"] = datetime.utcnow().isoformat()
        logger.debug(f"Setpoint timestamp added: {self.fields['timestamp']}")

