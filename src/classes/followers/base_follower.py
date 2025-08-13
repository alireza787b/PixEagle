# src/classes/followers/base_follower.py
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, List, Optional
from classes.setpoint_handler import SetpointHandler
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class BaseFollower(ABC):
    """
    Enhanced abstract base class for different follower modes.
    
    This class provides a unified interface for all follower implementations with:
    - Schema-aware setpoint management
    - Type-safe field access
    - Standardized validation
    - Enhanced telemetry interface
    - Extensible configuration support
    
    All concrete follower classes must inherit from this base class and implement
    the required abstract methods.
    """
    
    def __init__(self, px4_controller, profile_name: str):
        """
        Initializes the BaseFollower with schema-aware setpoint management.

        Args:
            px4_controller: Instance of PX4Controller to control the drone.
            profile_name (str): The name of the setpoint profile to use 
                              (e.g., "Ground View", "Constant Position").
        
        Raises:
            ValueError: If the profile is not defined in the schema.
            FileNotFoundError: If the schema file cannot be found.
        """
        self.px4_controller = px4_controller
        self.profile_name = profile_name
        
        # Initialize schema-aware setpoint handler
        try:
            self.setpoint_handler = SetpointHandler(profile_name)
            # Assign setpoint handler to px4_controller for backward compatibility
            self.px4_controller.setpoint_handler = self.setpoint_handler
            
        except Exception as e:
            logger.error(f"Failed to initialize SetpointHandler for profile '{profile_name}': {e}")
            raise
        
        # Initialize telemetry tracking
        self._telemetry_metadata = {
            'initialization_time': datetime.utcnow().isoformat(),
            'profile_name': self.get_display_name(),
            'control_type': self.get_control_type()
        }
        
        logger.info(f"BaseFollower initialized with profile: {self.get_display_name()} "
                   f"(control type: {self.get_control_type()})")
    
    # ==================== Abstract Methods ====================
    
    @abstractmethod
    def calculate_control_commands(self, target_coords: Tuple[float, float]) -> None:
        """
        Calculate control commands based on target coordinates and update the setpoint handler.

        This method must be implemented by all concrete follower classes to define
        their specific control logic.

        Args:
            target_coords (Tuple[float, float]): The coordinates of the target to follow.
            
        Raises:
            NotImplementedError: If not implemented by concrete class.
        """
        pass

    @abstractmethod
    async def follow_target(self, target_coords: Tuple[float, float]):
        """
        Asynchronously sends control commands to follow the target.

        This method must be implemented by all concrete follower classes to define
        their specific following behavior.

        Args:
            target_coords (Tuple[float, float]): The coordinates of the target to follow.
            
        Raises:
            NotImplementedError: If not implemented by concrete class.
        """
        pass
    
    # ==================== Schema-Aware Methods ====================
    
    def get_available_fields(self) -> List[str]:
        """
        Returns the list of available command fields for this follower profile.
        
        Returns:
            List[str]: List of field names available for this profile.
        """
        return list(self.setpoint_handler.get_fields().keys())
    
    def get_control_type(self) -> str:
        """
        Returns the control type for this follower profile.
        
        Returns:
            str: The control type ('velocity_body' or 'attitude_rate').
        """
        return self.setpoint_handler.get_control_type()
    
    def get_display_name(self) -> str:
        """
        Returns the human-readable display name for this follower profile.
        
        Returns:
            str: The display name.
        """
        return self.setpoint_handler.get_display_name()
    
    def get_description(self) -> str:
        """
        Returns the description for this follower profile.
        
        Returns:
            str: The profile description.
        """
        return self.setpoint_handler.get_description()
    
    # ==================== Field Access Methods ====================
    
    def set_command_field(self, field_name: str, value: float) -> bool:
        """
        Sets a command field value with validation and error handling.
        
        Args:
            field_name (str): The name of the field to set.
            value (float): The value to assign to the field.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            self.setpoint_handler.set_field(field_name, value)
            logger.debug(f"Successfully set {field_name} = {value} for {self.get_display_name()}")
            return True
            
        except ValueError as e:
            logger.warning(f"Failed to set field {field_name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting field {field_name}: {e}")
            return False
    
    def get_command_field(self, field_name: str) -> Optional[float]:
        """
        Gets a command field value safely.
        
        Args:
            field_name (str): The name of the field to get.
            
        Returns:
            Optional[float]: The field value, or None if not found.
        """
        try:
            fields = self.setpoint_handler.get_fields()
            return fields.get(field_name)
            
        except Exception as e:
            logger.error(f"Error getting field {field_name}: {e}")
            return None
    
    def get_all_command_fields(self) -> Dict[str, float]:
        """
        Returns all current command field values.
        
        Returns:
            Dict[str, float]: Dictionary of all field values.
        """
        try:
            return self.setpoint_handler.get_fields()
        except Exception as e:
            logger.error(f"Error getting command fields: {e}")
            return {}
    
    def reset_command_fields(self) -> bool:
        """
        Resets all command fields to their schema-defined default values.
        
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            self.setpoint_handler.reset_setpoints()
            logger.info(f"Reset all command fields for {self.get_display_name()}")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting command fields: {e}")
            return False
    
    # ==================== Validation Methods ====================
    
    def validate_target_coordinates(self, target_coords: Tuple[float, float]) -> bool:
        """
        Validates target coordinates format and range.
        
        Args:
            target_coords (Tuple[float, float]): Target coordinates to validate.
            
        Returns:
            bool: True if valid, False otherwise.
        """
        try:
            if not isinstance(target_coords, (tuple, list)) or len(target_coords) != 2:
                logger.warning(f"Invalid target coordinates format: {target_coords}. Expected tuple of 2 floats.")
                return False
            
            x, y = target_coords
            if not all(isinstance(coord, (int, float)) for coord in [x, y]):
                logger.warning(f"Invalid target coordinate types: {target_coords}. Expected numeric values.")
                return False
            
            # Check reasonable bounds (normalized coordinates should be between -1 and 1)
            if not all(-2.0 <= coord <= 2.0 for coord in [x, y]):
                logger.warning(f"Target coordinates out of reasonable bounds: {target_coords}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error validating target coordinates: {e}")
            return False
    
    def validate_profile_consistency(self) -> bool:
        """
        Validates that the current profile configuration is consistent with the schema.
        
        Returns:
            bool: True if valid, False otherwise.
        """
        try:
            return self.setpoint_handler.validate_profile_consistency()
        except Exception as e:
            logger.error(f"Profile validation failed: {e}")
            return False
    
    # ==================== Enhanced Telemetry Interface ====================
    
    def get_follower_telemetry(self) -> Dict[str, Any]:
        """
        Returns comprehensive telemetry data including command fields and metadata.

        Returns:
            Dict[str, Any]: Complete telemetry data with fields, profile info, and metadata.
        """
        try:
            # Get base telemetry from setpoint handler
            telemetry = self.setpoint_handler.get_telemetry_data()
            
            # Add follower-specific metadata
            telemetry.update(self._telemetry_metadata)
            
            # Add runtime information
            telemetry.update({
                'available_fields': self.get_available_fields(),
                'field_count': len(self.get_available_fields()),
                'last_update': datetime.utcnow().isoformat(),
                'validation_status': self.validate_profile_consistency()
            })
            
            logger.debug(f"Generated telemetry for {self.get_display_name()}: {len(telemetry)} fields")
            return telemetry
            
        except Exception as e:
            logger.error(f"Error generating telemetry: {e}")
            return {
                'error': str(e),
                'profile_name': self.profile_name,
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def update_telemetry_metadata(self, key: str, value: Any) -> None:
        """
        Updates telemetry metadata with custom information.
        
        Args:
            key (str): Metadata key to update.
            value (Any): Value to assign.
        """
        try:
            self._telemetry_metadata[key] = value
            logger.debug(f"Updated telemetry metadata: {key} = {value}")
        except Exception as e:
            logger.error(f"Error updating telemetry metadata: {e}")
    
    # ==================== Status and Debug Methods ====================
    
    def get_status_report(self) -> str:
        """
        Generates a comprehensive status report for debugging and monitoring.
        
        Returns:
            str: Formatted status report.
        """
        try:
            report = f"\n{'='*50}\n"
            report += f"Follower Status Report: {self.get_display_name()}\n"
            report += f"{'='*50}\n"
            report += f"Profile: {self.profile_name}\n"
            report += f"Control Type: {self.get_control_type()}\n"
            report += f"Description: {self.get_description()}\n"
            report += f"Available Fields: {', '.join(self.get_available_fields())}\n"
            report += f"Validation Status: {'✓ Valid' if self.validate_profile_consistency() else '✗ Invalid'}\n"
            
            report += f"\nCurrent Command Values:\n"
            for field, value in self.get_all_command_fields().items():
                report += f"  {field}: {value:.3f}\n"
            
            report += f"\nTelemetry Metadata:\n"
            for key, value in self._telemetry_metadata.items():
                report += f"  {key}: {value}\n"
            
            report += f"{'='*50}\n"
            
            return report
            
        except Exception as e:
            return f"Error generating status report: {e}"
    
    def log_status(self, level: str = 'info') -> None:
        """
        Logs the current status report at the specified level.
        
        Args:
            level (str): Logging level ('debug', 'info', 'warning', 'error').
        """
        try:
            report = self.get_status_report()
            log_method = getattr(logger, level.lower(), logger.info)
            log_method(report)
        except Exception as e:
            logger.error(f"Error logging status: {e}")
    
    # ==================== Utility Methods ====================
    
    def is_field_available(self, field_name: str) -> bool:
        """
        Checks if a specific field is available for this profile.
        
        Args:
            field_name (str): Field name to check.
            
        Returns:
            bool: True if field is available, False otherwise.
        """
        return field_name in self.get_available_fields()
    
    def get_required_fields(self) -> List[str]:
        """
        Returns the list of required fields for this profile.
        
        Returns:
            List[str]: List of required field names.
        """
        try:
            profile_config = self.setpoint_handler.profile_config
            return profile_config.get('required_fields', [])
        except Exception as e:
            logger.error(f"Error getting required fields: {e}")
            return []
    
    def get_optional_fields(self) -> List[str]:
        """
        Returns the list of optional fields for this profile.
        
        Returns:
            List[str]: List of optional field names.
        """
        try:
            profile_config = self.setpoint_handler.profile_config
            return profile_config.get('optional_fields', [])
        except Exception as e:
            logger.error(f"Error getting optional fields: {e}")
            return []
    
    # ==================== Backward Compatibility ====================
    
    @property
    def latest_velocities(self) -> Dict[str, Any]:
        """
        Backward compatibility property for legacy code.
        
        Returns:
            Dict[str, Any]: Legacy velocity data format.
        """
        try:
            fields = self.get_all_command_fields()
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'status': 'active' if any(abs(v) > 0.001 for v in fields.values()) else 'idle',
                **fields
            }
        except Exception:
            return {'timestamp': None, 'status': 'error'}