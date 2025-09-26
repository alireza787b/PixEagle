# src/classes/followers/base_follower.py
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, List, Optional, Union
from classes.setpoint_handler import SetpointHandler
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
import time
from datetime import datetime

# Import schema manager for compatibility checking
try:
    from classes.schema_manager import get_schema_manager
    SCHEMA_MANAGER_AVAILABLE = True
except ImportError:
    logger.warning("Schema manager not available for follower compatibility checks")
    SCHEMA_MANAGER_AVAILABLE = False

# Import circuit breaker for event logging
try:
    from classes.circuit_breaker import FollowerCircuitBreaker
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False


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
    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculate control commands based on tracker data and update the setpoint handler.

        This method must be implemented by all concrete follower classes to define
        their specific control logic. The implementation should extract the necessary
        data from the TrackerOutput based on the follower's requirements.

        Args:
            tracker_data (TrackerOutput): Structured tracker data with all available information.
            
        Raises:
            NotImplementedError: If not implemented by concrete class.
        """
        pass

    @abstractmethod
    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Synchronously calculates and applies control commands to follow the target.

        This method must be implemented by all concrete follower classes to define
        their specific following behavior. It should calculate and set commands 
        but NOT send them directly (that's handled by the async control loop).

        Args:
            tracker_data (TrackerOutput): Structured tracker data with position, confidence, etc.
            
        Returns:
            bool: True if successful, False otherwise.
            
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
            logger.debug(f"Successfully set {field_name} = {value:.3f} for {self.get_display_name()}")
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
    
    def validate_target_coordinates(self, target_data) -> bool:
        """
        Validates target data format and extracts coordinates for validation.
        Supports both legacy tuple format and new TrackerOutput format.
        
        Args:
            target_data: Target data to validate. Can be Tuple[float, float] or TrackerOutput.
            
        Returns:
            bool: True if valid, False otherwise.
        """
        try:
            # Handle TrackerOutput objects
            from classes.tracker_output import TrackerOutput
            if isinstance(target_data, TrackerOutput):
                # Use the existing extraction method
                coords = self.extract_target_coordinates(target_data)
                if coords is None:
                    logger.warning(f"Could not extract valid coordinates from TrackerOutput")
                    return False
                # Continue with coordinate validation
                x, y = coords
            
            # Handle legacy tuple/list format  
            elif isinstance(target_data, (tuple, list)) and len(target_data) == 2:
                x, y = target_data
                if not all(isinstance(coord, (int, float)) for coord in [x, y]):
                    logger.warning(f"Invalid coordinate types in tuple: {target_data}. Expected numeric values.")
                    return False
            
            # Invalid format
            else:
                logger.warning(f"Invalid target data format: {type(target_data)}. Expected TrackerOutput or tuple of 2 floats.")
                return False
            
            # Check reasonable bounds (normalized coordinates should be between -2 and 2)
            if not all(-2.0 <= coord <= 2.0 for coord in [x, y]):
                logger.warning(f"Target coordinates out of reasonable bounds: ({x}, {y})")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error validating target data: {e}")
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

    # ==================== Circuit Breaker Integration ====================

    def log_follower_event(self, event_type: str, **event_data) -> None:
        """
        Log follower events for debugging and testing.

        When circuit breaker is active, this provides visibility into follower
        behavior and decision-making without executing actual commands.

        Args:
            event_type (str): Type of event (e.g., "target_acquired", "safety_stop")
            **event_data: Event-specific data as keyword arguments
        """
        if CIRCUIT_BREAKER_AVAILABLE:
            follower_name = self.__class__.__name__
            FollowerCircuitBreaker.log_follower_event(
                event_type=event_type,
                follower_name=follower_name,
                **event_data
            )
        else:
            # Fallback logging when circuit breaker not available
            event_str = ", ".join([f"{k}={v}" for k, v in event_data.items()])
            logger.debug(f"{self.__class__.__name__} EVENT: {event_type} - {event_str}")

    def is_circuit_breaker_active(self) -> bool:
        """
        Check if circuit breaker is currently active.

        Returns:
            bool: True if in testing mode (commands logged, not executed)
        """
        return CIRCUIT_BREAKER_AVAILABLE and FollowerCircuitBreaker.is_active()

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

    # ==================== Tracker Data Validation & Compatibility ====================
    
    def get_required_tracker_data_types(self) -> List[TrackerDataType]:
        """
        Returns the list of tracker data types that this follower requires to function.
        Reads from schema instead of hardcoding for true extensibility.
        
        Returns:
            List[TrackerDataType]: Required tracker data types from schema
        """
        try:
            # Get tracker data requirements from schema
            if hasattr(self, 'setpoint_handler') and self.setpoint_handler:
                profile_config = self.setpoint_handler.profile_config
                required_data_names = profile_config.get('required_tracker_data', ['POSITION_2D'])
                
                # Convert string names to TrackerDataType enums
                required_types = []
                for name in required_data_names:
                    try:
                        data_type = TrackerDataType[name.upper()]
                        required_types.append(data_type)
                    except KeyError:
                        logger.warning(f"Unknown tracker data type in schema: {name}")
                
                return required_types
            else:
                logger.warning("No setpoint handler available, using fallback required tracker data types")
                return [TrackerDataType.POSITION_2D]  # Fallback
                
        except Exception as e:
            logger.error(f"Error reading required tracker data types from schema: {e}")
            return [TrackerDataType.POSITION_2D]  # Safe fallback
    
    def get_optional_tracker_data_types(self) -> List[TrackerDataType]:
        """
        Returns the list of optional tracker data types this follower can utilize.
        Reads from schema instead of hardcoding for true extensibility.
        
        Returns:
            List[TrackerDataType]: Optional tracker data types from schema
        """
        try:
            # Get optional tracker data from schema
            if hasattr(self, 'setpoint_handler') and self.setpoint_handler:
                profile_config = self.setpoint_handler.profile_config
                optional_data_names = profile_config.get('optional_tracker_data', [])
                
                # Convert string names to TrackerDataType enums
                optional_types = []
                for name in optional_data_names:
                    try:
                        data_type = TrackerDataType[name.upper()]
                        optional_types.append(data_type)
                    except KeyError:
                        logger.warning(f"Unknown tracker data type in schema: {name}")
                
                return optional_types
            else:
                logger.warning("No setpoint handler available, using fallback optional tracker data types")
                return [TrackerDataType.BBOX_CONFIDENCE, TrackerDataType.VELOCITY_AWARE]  # Fallback
                
        except Exception as e:
            logger.error(f"Error reading optional tracker data types from schema: {e}")
            return []  # Safe fallback
    
    def validate_tracker_compatibility(self, tracker_data: TrackerOutput) -> bool:
        """
        Validates if the tracker data is compatible with this follower's requirements.
        Uses schema manager for advanced compatibility checking when available.
        
        Args:
            tracker_data (TrackerOutput): Tracker data to validate
            
        Returns:
            bool: True if compatible, False otherwise
        """
        if not tracker_data or not tracker_data.tracking_active:
            logger.debug("Tracker data is inactive or None")
            return False
        
        # Use schema manager for advanced compatibility checking
        if SCHEMA_MANAGER_AVAILABLE:
            try:
                schema_manager = get_schema_manager()
                follower_class_name = self.__class__.__name__
                data_type = tracker_data.data_type.value.upper()
                
                compatibility = schema_manager.check_follower_compatibility(follower_class_name, data_type)
                
                if compatibility in ['required', 'preferred', 'compatible', 'optional']:
                    logger.debug(f"Schema manager: {follower_class_name} has {compatibility} compatibility with {data_type}")
                    return True
                else:
                    logger.warning(f"Schema manager: {follower_class_name} incompatible with {data_type}")
                    return False
                    
            except Exception as e:
                logger.warning(f"Schema manager compatibility check failed: {e}, falling back to legacy validation")
                # Fall through to legacy validation
        
        # Legacy validation - check if tracker provides required data types
        required_types = self.get_required_tracker_data_types()
        for required_type in required_types:
            if not self._has_required_data(tracker_data, required_type):
                logger.warning(f"Tracker missing required data type: {required_type.value}")
                return False
        
        logger.debug(f"Tracker data is compatible with {self.get_display_name()}")
        return True
    
    def _has_required_data(self, tracker_data: TrackerOutput, data_type: TrackerDataType) -> bool:
        """
        Checks if tracker data contains the required data type.
        
        Args:
            tracker_data (TrackerOutput): Tracker data to check
            data_type (TrackerDataType): Required data type
            
        Returns:
            bool: True if data is available
        """
        if data_type == TrackerDataType.POSITION_2D:
            return tracker_data.position_2d is not None
        elif data_type == TrackerDataType.POSITION_3D:
            return tracker_data.position_3d is not None
        elif data_type == TrackerDataType.ANGULAR:
            return tracker_data.angular is not None
        elif data_type == TrackerDataType.GIMBAL_ANGLES:
            return tracker_data.angular is not None
        elif data_type == TrackerDataType.BBOX_CONFIDENCE:
            return (tracker_data.bbox is not None or 
                   tracker_data.normalized_bbox is not None)
        elif data_type == TrackerDataType.VELOCITY_AWARE:
            return tracker_data.velocity is not None
        elif data_type == TrackerDataType.MULTI_TARGET:
            return tracker_data.targets is not None
        elif data_type == TrackerDataType.EXTERNAL:
            return tracker_data.raw_data is not None
        return False
    
    def extract_target_coordinates(self, tracker_data: TrackerOutput) -> Optional[Tuple[float, float]]:
        """
        Extracts 2D target coordinates from tracker data for backwards compatibility.
        
        Args:
            tracker_data (TrackerOutput): Tracker data to extract from
            
        Returns:
            Optional[Tuple[float, float]]: 2D coordinates or None
        """
        logger.debug(f"Extracting coordinates from tracker data: position_2d={tracker_data.position_2d}, "
                    f"position_3d={tracker_data.position_3d}, tracking_active={tracker_data.tracking_active}")
        
        # Try primary position data first
        if tracker_data.position_2d:
            logger.debug(f"Using position_2d coordinates: {tracker_data.position_2d}")
            return tracker_data.position_2d
        
        # Extract from 3D if available
        if tracker_data.position_3d:
            coords = tracker_data.position_3d[:2]
            logger.debug(f"Using position_3d coordinates (2D slice): {coords}")
            return coords
        
        # Convert from angular if needed (would need additional context)
        if tracker_data.angular:
            logger.warning("Angular data cannot be directly converted to 2D coordinates without additional context")
            return None
        
        logger.warning(f"No compatible position data found in tracker output: "
                      f"position_2d={tracker_data.position_2d}, position_3d={tracker_data.position_3d}, "
                      f"angular={tracker_data.angular}")
        return None
    
    def follow_target_legacy(self, target_coords: Tuple[float, float]) -> bool:
        """
        Legacy method for backwards compatibility with old follower interface.
        
        This method creates a minimal TrackerOutput from legacy coordinates
        and calls the new follow_target method.
        
        Args:
            target_coords (Tuple[float, float]): Legacy 2D coordinates
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create minimal tracker output for backwards compatibility
            legacy_tracker_data = TrackerOutput(
                data_type=TrackerDataType.POSITION_2D,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id="legacy_input",
                position_2d=target_coords,
                metadata={"legacy_input": True}
            )
            
            return self.follow_target(legacy_tracker_data)
            
        except Exception as e:
            logger.error(f"Error in legacy follow_target: {e}")
            return False