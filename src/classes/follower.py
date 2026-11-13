# src/classes/follower.py
import logging
import math
from typing import Tuple, Dict, Any, List, Type, Optional
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler
from classes.tracker_output import TrackerOutput

logger = logging.getLogger(__name__)


def _requires_image_aim(profile_name: str) -> bool:
    return "POSITION_2D" in SetpointHandler.get_profile_info(profile_name)["required_tracker_data"]


def _validated_image_aim(coords) -> Tuple[float, float]:
    if not isinstance(coords, (tuple, list)) or len(coords) != 2:
        raise ValueError("initial_target_coords must be a finite numeric (x, y) pair")
    try:
        valid = all(isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) for value in coords)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("initial_target_coords must be a finite numeric (x, y) pair")
    return tuple(coords)


def _initial_target_coords(profile_name: str, coords) -> Optional[Tuple[float, float]]:
    return _validated_image_aim(coords) if _requires_image_aim(profile_name) else None


def resolve_initial_target_coords(
    profile_name: str, tracker_output: Optional[TrackerOutput], *,
    target_position_mode: str, desired_aim,
) -> Optional[Tuple[float, float]]:
    """Resolve an image aim only when the declared follower input requires one.

    This does not replace target/source readiness or create tracker evidence.
    """
    if not _requires_image_aim(profile_name):
        return None
    if target_position_mode == "initial":
        if not isinstance(tracker_output, TrackerOutput):
            raise ValueError("initial_target_coords requires typed tracker output")
        return _validated_image_aim(tracker_output.position_2d)
    if target_position_mode == "center":
        return _validated_image_aim(desired_aim)
    raise ValueError("target_position_mode must be initial or center")


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
    def get_removed_aliases(cls) -> Dict[str, str]:
        """Return migration-only aliases from the validated command contract."""
        return SetpointHandler.get_removed_profile_aliases()

    @classmethod
    def _initialize_registry(cls):
        """
        Initializes the follower registry with available implementations.
        Uses lazy loading to avoid circular imports.

        Naming Convention: {vehicle}_{control}_{behavior}
        - vehicle: mc_ (multicopter), fw_ (fixed-wing), gm_ (gimbal)
        - control: velocity, navigation, attitude_rate
        - behavior: optional descriptor (chase, ground, distance, position, vector, unified)
        """
        if cls._registry_initialized:
            return

        try:
            # Import follower implementations with new naming convention
            from classes.followers.mc_velocity_ground_follower import MCVelocityGroundFollower
            from classes.followers.mc_velocity_distance_follower import MCVelocityDistanceFollower
            from classes.followers.mc_velocity_position_follower import MCVelocityPositionFollower
            from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower
            from classes.followers.mc_attitude_rate_follower import MCAttitudeRateFollower
            from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
            from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower
            from classes.followers.fw_attitude_rate_follower import FWAttitudeRateFollower
            from classes.followers.fw_navigation_chase_follower import FWNavigationChaseFollower

            # Primary registry with new naming convention
            cls._follower_registry = {
                # Multicopter - Velocity Control
                'mc_velocity_chase': MCVelocityChaseFollower,
                'mc_velocity_ground': MCVelocityGroundFollower,
                'mc_velocity_distance': MCVelocityDistanceFollower,
                'mc_velocity_position': MCVelocityPositionFollower,

                # Multicopter - Attitude Rate Control
                'mc_attitude_rate': MCAttitudeRateFollower,

                # Fixed-Wing - Native Navigation and research direct rates
                'fw_navigation_chase': FWNavigationChaseFollower,
                'fw_attitude_rate': FWAttitudeRateFollower,

                # Gimbal - Velocity Control
                'gm_velocity_chase': GMVelocityChaseFollower,
                'gm_velocity_vector': GMVelocityVectorFollower,
            }

            # v5.0.0: Deprecated aliases are NO LONGER registered
            # They will raise errors with migration hints when used

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
    def create_follower(cls, profile_name: str, px4_controller, initial_target_coords: Optional[Tuple[float, float]]):
        """
        Creates and returns a follower instance for the specified profile.

        Args:
            profile_name (str): The follower profile name.
            px4_controller: The PX4 controller instance.
            initial_target_coords: Image aim; None for non-image input contracts.

        Returns:
            BaseFollower: An instance of the appropriate follower class.

        Raises:
            ValueError: If the profile is invalid or implementation not found.
        """
        cls._initialize_registry()

        # Normalize profile name
        normalized_name = SetpointHandler.normalize_profile_name(profile_name)

        # v5.0.0: Raise error for removed aliases with migration hint
        removed_aliases = cls.get_removed_aliases()
        if normalized_name in removed_aliases:
            new_name = removed_aliases[normalized_name]
            raise ValueError(
                f"Follower mode '{normalized_name}' was removed in v5.0.0. "
                f"Please update your configuration to use '{new_name}' instead."
            )
        
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
        initial_target_coords = _initial_target_coords(normalized_name, initial_target_coords)
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
    using schema-aware follower implementations and comprehensive telemetry.

    A control profile is immutable for one follow session. Profile changes are
    persisted while inactive and create a new follower/commander generation on
    the next start; live handler replacement would split command ownership.
    """

    def __init__(self, px4_controller, initial_target_coords: Optional[Tuple[float, float]]):
        """
        Initializes the Follower with the PX4 controller and initial target coordinates.

        Args:
            px4_controller: The PX4 controller instance for controlling the drone.
            initial_target_coords: Image aim; None for non-image input contracts.

        Raises:
            ValueError: If the initial_target_coords are not valid or follower mode is invalid.
        """
        self.px4_controller = px4_controller
        self.mode = Parameters.FOLLOWER_MODE
        self.initial_target_coords = _initial_target_coords(self.mode, initial_target_coords)
        
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
                'timestamp': 'unknown'
            }
    
    # ==================== Schema-Aware Control Methods ====================
    
    def get_control_type(self) -> str:
        """
        Determines the type of control command to send based on the current follower mode.
        
        Returns:
            str: The control type (`attitude_rate` or `velocity_body_offboard`).

        Raises:
            RuntimeError: If the active follower cannot report its control type.
        """
        try:
            return self.follower.get_control_type()
        except Exception as e:
            logger.error(f"Error getting control type: {e}")
            raise RuntimeError(
                "Unable to determine the active follower control type"
            ) from e

    def get_airframe_phase(self) -> str:
        """Return the active strategy phase, or the static profile's phase."""
        try:
            return self.follower.get_airframe_phase()
        except Exception as e:
            logger.error(f"Error getting airframe phase: {e}")
            raise RuntimeError(
                "Unable to determine the active follower airframe phase"
            ) from e

    def get_last_command_intent(self):
        """Return the latest atomic command intent produced by the active follower."""
        try:
            getter = getattr(self.follower, 'get_last_command_intent', None)
            if callable(getter):
                return getter()
            return None
        except Exception as e:
            logger.error(f"Error getting last command intent: {e}")
            return None

    def prepare_for_target_transition(self, reason: str) -> bool:
        """Forward the fail-closed target-transition hook to the implementation."""
        try:
            prepare = getattr(self.follower, 'prepare_for_target_transition', None)
            if not callable(prepare):
                logger.error(
                    "Follower %s has no target-transition contract",
                    self.follower.__class__.__name__,
                )
                return False
            return bool(prepare(reason))
        except Exception as e:
            logger.error(f"Failed to prepare follower target transition: {e}")
            return False

    def validate_tracker_compatibility(self, tracker_data) -> bool:
        """
        Forward tracker compatibility checks to the active follower implementation.

        AppController interacts with this manager, so manager-level forwarding
        keeps the runtime path aligned with concrete follower behavior.
        """
        try:
            validator = getattr(self.follower, 'validate_tracker_compatibility', None)
            if callable(validator):
                return bool(validator(tracker_data))
            return False
        except Exception as e:
            logger.error(f"Error validating tracker compatibility: {e}")
            return False

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
    
