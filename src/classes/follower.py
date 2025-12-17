# src/classes/follower.py
import logging
from typing import Tuple, Dict, Any, List, Type, Optional
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler

logger = logging.getLogger(__name__)

class FollowerFactory:
    """
    Schema-aware follower factory that dynamically manages follower modes
    based on the unified command schema. Provides extensible registration
    and validation for all follower implementations.
    """
    
    # Class-level registry for follower implementations
    _follower_registry: Dict[str, Type] = {}
    _registry_initialized = False
    
    @classmethod
    def _initialize_registry(cls):
        """
        Initializes the follower registry with available implementations.
        Uses lazy loading to avoid circular imports.
        """
        if cls._registry_initialized:
            return
            
        try:
            # Import follower implementations lazily
            from classes.followers.ground_target_follower import GroundTargetFollower
            from classes.followers.constant_distance_follower import ConstantDistanceFollower
            from classes.followers.constant_position_follower import ConstantPositionFollower
            from classes.followers.attitude_rate_follower import AttitudeRateFollower, ChaseFollower
            from classes.followers.body_velocity_chase_follower import BodyVelocityChaseFollower
            from classes.followers.gimbal_follower import GimbalFollower
            from classes.followers.gimbal_vector_body_follower import GimbalVectorBodyFollower
            from classes.followers.fixed_wing_follower import FixedWingFollower

            # Register followers with their schema profile names
            # Note: 'attitude_rate' is the new name, 'chase_follower' kept for backward compatibility
            cls._follower_registry = {
                'ground_view': GroundTargetFollower,
                'constant_distance': ConstantDistanceFollower,
                'constant_position': ConstantPositionFollower,
                'chase_follower': AttitudeRateFollower,  # Backward compatible name
                'attitude_rate': AttitudeRateFollower,   # New preferred name
                'body_velocity_chase': BodyVelocityChaseFollower,
                'gimbal_unified': GimbalFollower,
                'gimbal_vector_body': GimbalVectorBodyFollower,
                'fixed_wing': FixedWingFollower          # Professional fixed-wing with L1/TECS
            }
            
            cls._registry_initialized = True
            logger.info(f"Follower registry initialized with {len(cls._follower_registry)} implementations")
            
        except ImportError as e:
            logger.error(f"Failed to import follower implementations: {e}")
            raise
    
    @classmethod
    def register_follower(cls, profile_name: str, follower_class: Type) -> bool:
        """
        Registers a new follower implementation for a specific profile.
        
        Args:
            profile_name (str): The schema profile name.
            follower_class (Type): The follower class to register.
            
        Returns:
            bool: True if registration successful, False otherwise.
        """
        try:
            cls._initialize_registry()
            
            # Validate that the profile exists in schema
            available_profiles = SetpointHandler.get_available_profiles()
            if profile_name not in available_profiles:
                logger.error(f"Cannot register follower for unknown profile '{profile_name}'. "
                           f"Available profiles: {available_profiles}")
                return False
            
            # Validate that the class has required methods
            required_methods = ['calculate_control_commands', 'follow_target']
            for method in required_methods:
                if not hasattr(follower_class, method):
                    logger.error(f"Follower class {follower_class.__name__} missing required method: {method}")
                    return False
            
            cls._follower_registry[profile_name] = follower_class
            logger.info(f"Registered follower {follower_class.__name__} for profile '{profile_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Error registering follower: {e}")
            return False
    
    @classmethod
    def get_available_modes(cls) -> List[str]:
        """
        Returns a list of all available follower modes.
        
        Returns:
            List[str]: List of available follower mode names.
        """
        cls._initialize_registry()
        return list(cls._follower_registry.keys())
    
    @classmethod
    def get_follower_info(cls, profile_name: str) -> Dict[str, Any]:
        """
        Returns detailed information about a specific follower profile.
        
        Args:
            profile_name (str): The profile name to query.
            
        Returns:
            Dict[str, Any]: Profile information including schema details.
        """
        try:
            cls._initialize_registry()
            
            # Get schema information
            schema_info = SetpointHandler.get_profile_info(profile_name)
            
            # Get implementation information
            implementation_info = {
                'implementation_available': profile_name in cls._follower_registry,
                'implementation_class': cls._follower_registry.get(profile_name).__name__ if profile_name in cls._follower_registry else None
            }
            
            return {**schema_info, **implementation_info}
            
        except Exception as e:
            logger.error(f"Error getting follower info for '{profile_name}': {e}")
            return {}
    
    @classmethod
    def create_follower(cls, profile_name: str, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Creates and returns a follower instance for the specified profile.
        
        Args:
            profile_name (str): The follower profile name.
            px4_controller: The PX4 controller instance.
            initial_target_coords (Tuple[float, float]): Initial target coordinates.
            
        Returns:
            BaseFollower: An instance of the appropriate follower class.
            
        Raises:
            ValueError: If the profile is invalid or implementation not found.
        """
        cls._initialize_registry()
        
        # Normalize profile name
        normalized_name = SetpointHandler.normalize_profile_name(profile_name)
        
        # Check if profile exists in schema
        available_profiles = SetpointHandler.get_available_profiles()
        if normalized_name not in available_profiles:
            raise ValueError(f"Invalid follower profile '{profile_name}'. "
                           f"Available profiles: {available_profiles}")
        
        # Check if implementation is available
        if normalized_name not in cls._follower_registry:
            raise ValueError(f"No implementation found for profile '{profile_name}'. "
                           f"Available implementations: {list(cls._follower_registry.keys())}")
        
        # Create the follower instance
        follower_class = cls._follower_registry[normalized_name]
        try:
            logger.debug(f"Creating follower instance: {follower_class.__name__} for profile '{profile_name}'")
            return follower_class(px4_controller, initial_target_coords)
            
        except Exception as e:
            logger.error(f"Failed to create follower instance for '{profile_name}': {e}")
            raise

class Follower:
    """
    Enhanced follower manager that provides a unified interface for drone control
    using schema-aware follower implementations. Supports dynamic mode switching
    and comprehensive telemetry.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the Follower with the PX4 controller and initial target coordinates.

        Args:
            px4_controller: The PX4 controller instance for controlling the drone.
            initial_target_coords (Tuple[float, float]): Initial target coordinates for the follower.

        Raises:
            ValueError: If the initial_target_coords are not valid or follower mode is invalid.
        """
        # Validate initial target coordinates
        self._validate_target_coordinates(initial_target_coords)
        
        self.px4_controller = px4_controller
        self.mode = Parameters.FOLLOWER_MODE
        self.initial_target_coords = initial_target_coords
        
        # Create the follower instance using the factory
        try:
            self.follower = FollowerFactory.create_follower(
                self.mode, 
                self.px4_controller, 
                self.initial_target_coords
            )
            logger.info(f"Initialized Follower with mode: {self.mode} "
                       f"({self.follower.get_display_name()})")
            
        except Exception as e:
            logger.error(f"Failed to initialize follower with mode '{self.mode}': {e}")
            raise
    
    def _validate_target_coordinates(self, target_coords: Tuple[float, float]) -> None:
        """
        Validates initial target coordinates.
        
        Args:
            target_coords (Tuple[float, float]): Target coordinates to validate.
            
        Raises:
            ValueError: If coordinates are invalid.
        """
        if not isinstance(target_coords, tuple) or len(target_coords) != 2:
            raise ValueError(f"Invalid initial_target_coords: {target_coords}. "
                           f"Must be a tuple of (x, y) coordinates.")
        
        x, y = target_coords
        if not all(isinstance(coord, (int, float)) for coord in [x, y]):
            raise ValueError(f"Invalid coordinate types: {target_coords}. "
                           f"Expected numeric values.")
    
    # ==================== Core Follower Interface ====================
    
    def follow_target(self, tracker_data):
        """
        Sends control commands to follow a target based on tracker data.

        Args:
            tracker_data: The current tracker data to follow. Can be TrackerOutput object or legacy tuple.

        Returns:
            The result of the follower's `follow_target` method.
            
        Raises:
            ValueError: If tracker data is invalid.
        """
        logger.debug(f"Following target with data type: {type(tracker_data)}")
        
        try:
            # Call the follower's follow_target method directly
            # The individual follower will handle TrackerOutput validation and extraction
            result = self.follower.follow_target(tracker_data)
            return result
            
        except Exception as e:
            logger.error(f"Failed to follow target with data {tracker_data}: {e}")
            raise
    
    def get_follower_telemetry(self) -> Dict[str, Any]:
        """
        Returns comprehensive telemetry data from the current follower.

        Returns:
            Dict[str, Any]: Complete telemetry data including schema information.
        """
        try:
            # Get follower telemetry
            telemetry = self.follower.get_follower_telemetry()
            
            # Add manager-level information
            telemetry.update({
                'manager_mode': self.mode,
                'manager_status': 'active',
                'available_modes': FollowerFactory.get_available_modes(),
                'implementation_class': self.follower.__class__.__name__
            })
            
            logger.debug(f"Follower telemetry: {len(telemetry)} fields")
            return telemetry
            
        except Exception as e:
            logger.error(f"Failed to retrieve telemetry data: {e}")
            return {
                'error': str(e),
                'manager_mode': self.mode,
                'manager_status': 'error',
                'timestamp': self.follower.get_follower_telemetry().get('timestamp', 'unknown')
            }
    
    # ==================== Schema-Aware Control Methods ====================
    
    def get_control_type(self) -> str:
        """
        Determines the type of control command to send based on the current follower mode.
        
        Returns:
            str: The control type ('attitude_rate' or 'velocity_body').
        """
        try:
            return self.follower.get_control_type()
        except Exception as e:
            logger.error(f"Error getting control type: {e}")
            return 'velocity_body'  # Safe default
    
    def get_display_name(self) -> str:
        """
        Returns the human-readable display name for the current follower mode.
        
        Returns:
            str: The display name.
        """
        try:
            return self.follower.get_display_name()
        except Exception as e:
            logger.error(f"Error getting display name: {e}")
            return self.mode.replace('_', ' ').title()
    
    def get_description(self) -> str:
        """
        Returns the description for the current follower mode.
        
        Returns:
            str: The mode description.
        """
        try:
            return self.follower.get_description()
        except Exception as e:
            logger.error(f"Error getting description: {e}")
            return "No description available"
    
    def get_available_fields(self) -> List[str]:
        """
        Returns the list of available command fields for the current follower.
        
        Returns:
            List[str]: List of available field names.
        """
        try:
            return self.follower.get_available_fields()
        except Exception as e:
            logger.error(f"Error getting available fields: {e}")
            return []
    
    # ==================== Mode Management ====================
    
    def switch_mode(self, new_mode: str, preserve_target_coords: bool = True) -> bool:
        """
        Switches to a different follower mode dynamically.
        
        Args:
            new_mode (str): The new follower mode to switch to.
            preserve_target_coords (bool): Whether to preserve current target coordinates.
            
        Returns:
            bool: True if switch successful, False otherwise.
        """
        try:
            # Use current target coords if preserving, otherwise use initial
            target_coords = (
                self.initial_target_coords if preserve_target_coords 
                else (0.0, 0.0)
            )
            
            # Create new follower instance
            new_follower = FollowerFactory.create_follower(
                new_mode, 
                self.px4_controller, 
                target_coords
            )
            
            # Switch to new follower
            old_mode = self.mode
            self.follower = new_follower
            self.mode = new_mode
            
            logger.info(f"Successfully switched follower mode: {old_mode} → {new_mode}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to switch follower mode to '{new_mode}': {e}")
            return False
    
    @classmethod
    def get_available_modes(cls) -> List[str]:
        """
        Returns a list of all available follower modes.
        
        Returns:
            List[str]: List of available mode names.
        """
        return FollowerFactory.get_available_modes()
    
    @classmethod
    def get_mode_info(cls, mode_name: str) -> Dict[str, Any]:
        """
        Returns detailed information about a specific follower mode.
        
        Args:
            mode_name (str): The mode name to query.
            
        Returns:
            Dict[str, Any]: Mode information.
        """
        return FollowerFactory.get_follower_info(mode_name)
    
    # ==================== Status and Debug Methods ====================
    
    def get_status_report(self) -> str:
        """
        Generates a comprehensive status report for debugging.
        
        Returns:
            str: Formatted status report.
        """
        try:
            report = f"\n{'='*60}\n"
            report += f"Follower Manager Status Report\n"
            report += f"{'='*60}\n"
            report += f"Current Mode: {self.mode}\n"
            report += f"Display Name: {self.get_display_name()}\n"
            report += f"Control Type: {self.get_control_type()}\n"
            report += f"Description: {self.get_description()}\n"
            report += f"Implementation: {self.follower.__class__.__name__}\n"
            report += f"Available Fields: {', '.join(self.get_available_fields())}\n"
            report += f"Available Modes: {', '.join(self.get_available_modes())}\n"
            
            # Add follower-specific status
            if hasattr(self.follower, 'get_status_report'):
                report += f"\n{self.follower.get_status_report()}"
            
            report += f"{'='*60}\n"
            return report
            
        except Exception as e:
            return f"Error generating status report: {e}"
    
    def validate_current_mode(self) -> bool:
        """
        Validates that the current follower mode is properly configured.
        
        Returns:
            bool: True if valid, False otherwise.
        """
        try:
            # Check if follower is initialized
            if not hasattr(self, 'follower') or self.follower is None:
                logger.error("Follower not initialized")
                return False
            
            # Validate follower profile consistency
            if hasattr(self.follower, 'validate_profile_consistency'):
                return self.follower.validate_profile_consistency()
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating current mode: {e}")
            return False
    
    # ==================== Backward Compatibility ====================
    
    def get_follower_mode(self):
        """
        Backward compatibility method for legacy code.
        
        Returns:
            BaseFollower: The current follower instance.
        """
        logger.warning("get_follower_mode() is deprecated, use .follower property directly")
        return self.follower