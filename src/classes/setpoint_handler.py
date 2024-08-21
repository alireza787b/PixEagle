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
        
        Raises:
            ValueError: If the profile is not defined.
        """
        self.profile_name = self.normalize_profile_name(profile_name)
        self.fields: Dict[str, float] = {}

        # Initialize the fields based on the profile
        if self.profile_name in SETPOINT_PROFILES:
            self.initialize_fields(SETPOINT_PROFILES[self.profile_name])
            logger.info(f"SetpointHandler initialized with profile: {self.profile_name}")
        else:
            raise ValueError(f"Profile '{profile_name}' is not defined. Available profiles: {list(SETPOINT_PROFILES.keys())}")
        
    @staticmethod
    def normalize_profile_name(profile_name: str) -> str:
        """
        Normalizes the profile name to ensure it matches the defined profile keys.

        Args:
            profile_name (str): The raw profile name input.

        Returns:
            str: The normalized profile name (e.g., capitalized and formatted correctly).
        """
        return profile_name.replace("_", " ").title()

    def initialize_fields(self, field_names: list):
        """
        Initializes the fields for the given profile.

        Args:
            field_names (list): A list of field names to initialize.
        """
        for field in field_names:
            self.fields[field] = 0.0  # Initialize all fields to 0.0
        logger.debug(f"Fields initialized for profile '{self.profile_name}': {self.fields}")

    def set_field(self, field_name: str, value: float):
        """
        Sets the value of a specific field in the setpoint.
        
        Args:
            field_name (str): The name of the field to set.
            value (float): The value to assign to the field.
        
        Raises:
            ValueError: If the field name is not valid for the current profile or if the value is not a float.
        """
        if field_name in self.fields:
            try:
                self.fields[field_name] = float(value)  # Ensure the value is a float
                logger.debug(f"Setpoint updated: {field_name} = {value}")
            except ValueError:
                raise ValueError(f"The value for {field_name} must be a numeric type (int or float).")
        else:
            raise ValueError(f"Field '{field_name}' is not valid for profile '{self.profile_name}'. Valid fields: {list(self.fields.keys())}")

    
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
        logger.info(f"All setpoints for profile '{self.profile_name}' have been reset to default (0.0)")

    def timestamp_setpoint(self):
        """
        Adds a timestamp to the setpoints for telemetry or logging purposes.
        """
        self.fields["timestamp"] = datetime.utcnow().isoformat()
        logger.debug(f"Setpoint timestamp added: {self.fields['timestamp']}")
