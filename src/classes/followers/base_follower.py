# src/classes/followers/base_follower.py
"""
Base Follower Module - Abstract Base Class for All Followers
=============================================================

This module provides the BaseFollower abstract base class that all follower
implementations inherit from. It provides centralized safety management,
schema-aware setpoint handling, and common utilities.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi

Safety Integration (v5.0.0+):
- SafetyManager REQUIRED for all followers
- Centralized limits from Safety.GlobalLimits with FollowerOverrides
- Automatic limit caching per follower
- check_safety() method for altitude/velocity validation
- Validated set_command_field() with automatic clamping
"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, List, Optional, Union
from classes.setpoint_handler import SetpointHandler
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
import math
import time
from datetime import datetime

# Initialize logger early (before any try/except blocks that might use it)
logger = logging.getLogger(__name__)

# Import SafetyManager for centralized safety limit management
try:
    from classes.safety_manager import SafetyManager, get_safety_manager
    from classes.safety_types import (
        SafetyStatus, SafetyAction, VelocityLimits,
        AltitudeLimits, RateLimits, FollowerLimits
    )
    SAFETY_MANAGER_AVAILABLE = True
except ImportError:
    logger.warning("SafetyManager not available, using legacy limit handling")
    SAFETY_MANAGER_AVAILABLE = False

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

# Import follower logger for unified logging
try:
    from classes.follower_logger import FollowerLogger
    FOLLOWER_LOGGER_AVAILABLE = True
except ImportError:
    logger.warning("FollowerLogger not available, using standard logging")
    FOLLOWER_LOGGER_AVAILABLE = False

# Import collections for rate limiting
from collections import defaultdict

class RateLimitedLogger:
    """
    Rate-limited logger to prevent log spam in high-frequency control loops.

    Ensures the same error message is logged at most once per interval,
    preventing log flooding when errors occur at 20Hz or higher rates.
    """

    def __init__(self, interval: float = 5.0):
        """
        Initialize the rate-limited logger.

        Args:
            interval (float): Minimum seconds between logging the same message key.
                            Default is 5.0 seconds.
        """
        self.last_log_time: Dict[str, float] = defaultdict(float)
        self.interval = interval

    def log_rate_limited(self, logger_instance, level: str, key: str, message: str) -> bool:
        """
        Log message only if interval has passed since last log with same key.

        Args:
            logger_instance: Logger instance to use for logging
            level (str): Log level ('debug', 'info', 'warning', 'error', 'critical')
            key (str): Unique key for this message type (for rate limiting)
            message (str): The message to log

        Returns:
            bool: True if message was logged, False if rate-limited
        """
        current_time = time.time()
        if current_time - self.last_log_time[key] >= self.interval:
            getattr(logger_instance, level)(message)
            self.last_log_time[key] = current_time
            return True
        return False


class ErrorAggregator:
    """
    Aggregate errors and report summary periodically.

    Instead of logging individual errors at high frequency, this class
    tracks error counts and reports summaries at regular intervals.
    """

    def __init__(self, report_interval: float = 10.0):
        """
        Initialize the error aggregator.

        Args:
            report_interval (float): Seconds between summary reports. Default is 10.0.
        """
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.last_report_time = time.time()
        self.report_interval = report_interval

    def record_error(self, error_key: str, logger_instance=None) -> None:
        """
        Record an error occurrence.

        Args:
            error_key (str): Unique identifier for this error type
            logger_instance: Optional logger to use for reporting summaries
        """
        self.error_counts[error_key] += 1

        # Report summary if interval elapsed
        current_time = time.time()
        if logger_instance and current_time - self.last_report_time >= self.report_interval:
            self._report_summary(logger_instance)

    def _report_summary(self, logger_instance) -> None:
        """
        Report error summary and reset counters.

        Args:
            logger_instance: Logger to use for reporting
        """
        if self.error_counts:
            logger_instance.warning(f"Error summary (last {self.report_interval:.0f}s):")
            for error_key, count in sorted(self.error_counts.items()):
                logger_instance.warning(f"  {error_key}: {count} occurrences")
            self.error_counts.clear()
        self.last_report_time = time.time()


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

        # Initialize logging utilities to prevent log spam in high-frequency control loops
        self._rate_limiter = RateLimitedLogger(interval=5.0)  # Log same error max once per 5 seconds
        self._error_aggregator = ErrorAggregator(report_interval=10.0)  # Report summary every 10 seconds

        # Initialize unified follower logger for consistent, spam-reduced logging
        if FOLLOWER_LOGGER_AVAILABLE:
            self.follower_logger = FollowerLogger(
                follower_name=self.__class__.__name__,
                logger=logger,
                spam_cooldown=5.0,
                summary_interval=30.0
            )
        else:
            # Fallback if FollowerLogger not available
            self.follower_logger = None

        # Initialize centralized safety management (v3.5.0+)
        self._safety_violation_count = 0
        self._last_safety_check_time = 0.0
        self._safety_check_interval = 0.05  # 20Hz safety checks
        self._last_safety_result = None  # Cache real result (not hardcoded ok) for rate-limited checks
        self.rtl_triggered = False  # Deduplicate RTL calls (WP9)

        # v5.0.0: SafetyManager is now required (single source of truth)
        if not SAFETY_MANAGER_AVAILABLE:
            raise RuntimeError("SafetyManager is required in v5.0.0+. Check your imports.")

        try:
            self.safety_manager = get_safety_manager()
            # Derive follower config name from class (e.g., MCVelocityChaseFollower -> MC_VELOCITY_CHASE)
            self._follower_config_name = self._derive_follower_config_name()

            # Warn if SafetyManager hasn't loaded config (using fallback values)
            if not self.safety_manager._initialized:
                logger.warning(f"SafetyManager not initialized from config - using hardcoded fallbacks. "
                               f"Ensure config file has 'Safety' section.")

            # Safety limits are dynamic properties - read fresh from SafetyManager
            logger.info(f"SafetyManager initialized for {self._follower_config_name}: "
                       f"vel_limits={self.velocity_limits}, alt_limits={self.altitude_limits}")
        except Exception as e:
            logger.error(f"SafetyManager initialization failed: {e}")
            raise RuntimeError(f"SafetyManager required but failed: {e}")

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
        # NaN/Inf guard: reject non-finite values before they corrupt the setpoint (WP9)
        if not math.isfinite(value):
            logger.error(
                f"Rejecting non-finite command value for {field_name}: {value!r} "
                f"(follower={self.__class__.__name__})"
            )
            return False

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

    # ==================== PID Utility Methods ====================

    def _update_pid_gains_from_config(self, pid_controller, axis: str, profile_name: str) -> None:
        """
        Update PID controller gains from Parameters configuration.

        This is a common pattern across followers - extracted to base class for DRY principle.
        Eliminates code duplication in mc_velocity_position, mc_velocity_distance, mc_velocity_chase.

        Args:
            pid_controller: CustomPID instance to update (must have Kp, Ki, Kd attributes)
            axis: PID axis name (e.g., 'mc_yawspeed_deg_s', 'mc_vel_body_down', 'fw_roll_rate')
            profile_name: Follower profile name for logging (e.g., 'MC Velocity Position')

        Raises:
            ValueError: If axis not found in Parameters.PID_GAINS or gains are invalid

        Example:
            self._update_pid_gains_from_config(self.pid_yaw_rate, 'mc_yawspeed_deg_s', 'MC Velocity Chase')
        """
        try:
            from classes.parameters import Parameters

            # Validate axis exists
            if axis not in Parameters.PID_GAINS:
                available = list(Parameters.PID_GAINS.keys())
                raise ValueError(f"Unsupported PID axis '{axis}'. Available: {available}")

            # Get gains
            gains = Parameters.PID_GAINS[axis]
            p_gain = gains['p']
            i_gain = gains['i']
            d_gain = gains['d']

            # Validate gain values
            if any(not isinstance(g, (int, float)) or g < 0 for g in [p_gain, i_gain, d_gain]):
                raise ValueError(f"Invalid PID gains for axis '{axis}': p={p_gain}, i={i_gain}, d={d_gain}")

            # Update controller
            pid_controller.Kp = p_gain
            pid_controller.Ki = i_gain
            pid_controller.Kd = d_gain

            logger.debug(f"[{profile_name}] Updated {axis} PID gains: P={p_gain}, I={i_gain}, D={d_gain}")

        except KeyError as e:
            logger.error(f"[{profile_name}] PID gains not found for axis '{axis}': {e}")
            raise
        except Exception as e:
            logger.error(f"[{profile_name}] Error updating PID gains for axis '{axis}': {e}")
            raise

    # ==================== Safety Management Methods ====================

    def _derive_follower_config_name(self) -> str:
        """
        Derive the config section name from the class name.

        Converts class names like 'MCVelocityChaseFollower' to 'MC_VELOCITY_CHASE'
        for config lookup.

        Returns:
            str: The config section name (e.g., 'MC_VELOCITY_CHASE')
        """
        class_name = self.__class__.__name__

        # Remove 'Follower' suffix if present
        if class_name.endswith('Follower'):
            class_name = class_name[:-8]

        # Convert CamelCase to UPPER_SNAKE_CASE
        # Handle special prefixes (MC, GM, FW)
        result = []
        i = 0
        while i < len(class_name):
            char = class_name[i]

            # Handle uppercase sequences (like MC, GM, FW)
            if char.isupper():
                # Check if this is part of an acronym (consecutive uppercase)
                acronym = char
                j = i + 1
                while j < len(class_name) and class_name[j].isupper():
                    # If next char after this is lowercase, this uppercase belongs to next word
                    if j + 1 < len(class_name) and class_name[j + 1].islower():
                        break
                    acronym += class_name[j]
                    j += 1

                if len(acronym) > 1:
                    # This is an acronym
                    if result:
                        result.append('_')
                    result.append(acronym)
                    i = j
                else:
                    # Single uppercase - start of new word
                    if result and result[-1] != '_':
                        result.append('_')
                    result.append(char)
                    i += 1
            else:
                result.append(char.upper())
                i += 1

        return ''.join(result)

    # ==================== Dynamic Safety Limit Properties ====================
    # These properties read fresh from SafetyManager on each access, allowing
    # config changes to take effect immediately without follower restart.

    @property
    def velocity_limits(self):
        """Get velocity limits from SafetyManager (v5.0.0+: single source of truth)."""
        return self.safety_manager.get_velocity_limits(self._follower_config_name)

    @property
    def altitude_limits(self):
        """Get altitude limits from SafetyManager (v5.0.0+: single source of truth)."""
        return self.safety_manager.get_altitude_limits(self._follower_config_name)

    @property
    def rate_limits(self):
        """Get rate limits from SafetyManager (v5.0.0+: single source of truth)."""
        return self.safety_manager.get_rate_limits(self._follower_config_name)

    def check_safety(self) -> 'SafetyStatus':
        """
        Centralized safety check - validates altitude and velocity limits.

        This method should be called by followers before applying commands.
        It checks:
        1. Altitude safety (if enabled)
        2. Velocity magnitude limits
        3. Violation counting

        Returns:
            SafetyStatus: Status with safe flag, reason, and recommended action
        """
        current_time = time.time()

        # Rate-limit safety checks to avoid overhead
        if current_time - self._last_safety_check_time < self._safety_check_interval:
            # Return the last real result so violations remain visible within the cache window
            if self._last_safety_result is not None:
                return self._last_safety_result
            if SAFETY_MANAGER_AVAILABLE:
                return SafetyStatus.ok()
            else:
                return type('SafetyStatus', (), {'safe': True, 'reason': 'ok', 'action': None})()

        self._last_safety_check_time = current_time

        # Use SafetyManager if available
        if self.safety_manager:
            try:
                # Check altitude safety
                current_alt = getattr(self.px4_controller, 'current_altitude', None)
                if current_alt is not None:
                    alt_status = self.safety_manager.check_altitude_safety(
                        current_alt,
                        self._follower_config_name
                    )
                    if not alt_status.safe:
                        self._handle_safety_violation(alt_status)
                        self._last_safety_result = alt_status
                        return alt_status

                ok_status = SafetyStatus.ok()
                self._last_safety_result = ok_status
                return ok_status

            except Exception as e:
                logger.warning(f"Safety check error: {e}")
                return SafetyStatus.ok()  # Fail-open for now

        # Legacy safety check
        return self._check_safety_legacy()

    def _check_safety_legacy(self):
        """Legacy safety check when SafetyManager is not available."""
        from classes.parameters import Parameters

        # Check if altitude safety is enabled
        altitude_safety_enabled = getattr(Parameters, 'ALTITUDE_SAFETY_ENABLED', True)
        if not altitude_safety_enabled:
            return type('SafetyStatus', (), {'safe': True, 'reason': 'disabled', 'action': None})()

        # Get current altitude
        current_alt = getattr(self.px4_controller, 'current_altitude', None)
        if current_alt is None:
            return type('SafetyStatus', (), {'safe': True, 'reason': 'no_altitude', 'action': None})()

        # Check bounds
        min_alt = self.altitude_limits.min_altitude
        max_alt = self.altitude_limits.max_altitude

        if current_alt < min_alt:
            return type('SafetyStatus', (), {
                'safe': False,
                'reason': f'altitude_low: {current_alt:.1f}m < {min_alt:.1f}m',
                'action': 'clamp'
            })()

        if current_alt > max_alt:
            return type('SafetyStatus', (), {
                'safe': False,
                'reason': f'altitude_high: {current_alt:.1f}m > {max_alt:.1f}m',
                'action': 'clamp'
            })()

        return type('SafetyStatus', (), {'safe': True, 'reason': 'ok', 'action': None})()

    def _handle_safety_violation(self, status: 'SafetyStatus') -> None:
        """
        Handle a safety violation by logging and incrementing violation count.

        Args:
            status: The SafetyStatus describing the violation
        """
        self._safety_violation_count += 1

        # Rate-limited logging
        self._rate_limiter.log_rate_limited(
            logger, 'warning',
            f'safety_violation_{self._follower_config_name}',
            f"Safety violation #{self._safety_violation_count} in {self._follower_config_name}: {status.reason}"
        )

        # Log event for circuit breaker integration
        self.log_follower_event(
            'safety_violation',
            reason=status.reason,
            action=str(status.action) if hasattr(status, 'action') else 'unknown',
            violation_count=self._safety_violation_count
        )

    def clamp_velocity(self, vel_fwd: float, vel_right: float, vel_down: float) -> tuple:
        """
        Clamp velocity components to configured limits.

        Args:
            vel_fwd: Forward velocity (m/s)
            vel_right: Right velocity (m/s)
            vel_down: Down velocity (m/s)

        Returns:
            tuple: (clamped_fwd, clamped_right, clamped_down)
        """
        import numpy as np

        clamped_fwd = np.clip(vel_fwd, -self.velocity_limits.forward, self.velocity_limits.forward)
        clamped_right = np.clip(vel_right, -self.velocity_limits.lateral, self.velocity_limits.lateral)
        clamped_down = np.clip(vel_down, -self.velocity_limits.vertical, self.velocity_limits.vertical)

        return (clamped_fwd, clamped_right, clamped_down)

    def clamp_rate(self, rate_value: float, rate_type: str = 'yaw') -> float:
        """
        Clamp a rate value to configured limits.

        Args:
            rate_value: Rate in rad/s
            rate_type: One of 'yaw', 'pitch', 'roll'

        Returns:
            float: Clamped rate in rad/s
        """
        import numpy as np

        limit = getattr(self.rate_limits, rate_type, self.rate_limits.yaw)
        return float(np.clip(rate_value, -limit, limit))

    def is_altitude_safety_enabled(self) -> bool:
        """
        Check if altitude safety is enabled for this follower.

        Returns:
            bool: True if altitude safety checks should be performed
        """
        if self.safety_manager:
            return self.safety_manager.is_altitude_safety_enabled(self._follower_config_name)

        # Legacy check
        return getattr(self.altitude_limits, 'safety_enabled', True)

    def get_effective_limit(self, limit_name: str) -> float:
        """
        Get an effective limit value using SafetyManager with legacy fallback.

        Args:
            limit_name: The name of the limit (e.g., 'MAX_VELOCITY_FORWARD')

        Returns:
            float: The limit value
        """
        if self.safety_manager:
            return self.safety_manager.get_limit(limit_name, self._follower_config_name)

        # Legacy fallback
        from classes.parameters import Parameters
        return Parameters.get_effective_limit(limit_name, self._follower_config_name)

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
                    # Use rate-limited logging to prevent log spam at 20Hz
                    error_key = f"incompatible_{follower_class_name}_{data_type}"
                    error_msg = (
                        f"Tracker data incompatible: {follower_class_name} cannot use {data_type} tracker. "
                        f"Check tracker configuration or switch to a compatible tracker type."
                    )
                    self._rate_limiter.log_rate_limited(logger, 'error', error_key, error_msg)
                    self._error_aggregator.record_error(error_key, logger)
                    return False
                    
            except Exception as e:
                logger.warning(f"Schema manager compatibility check failed: {e}, falling back to legacy validation")
                # Fall through to legacy validation
        
        # Legacy validation - check if tracker provides required data types
        required_types = self.get_required_tracker_data_types()
        for required_type in required_types:
            if not self._has_required_data(tracker_data, required_type):
                # Use rate-limited logging for legacy validation as well
                error_key = f"missing_data_{self.__class__.__name__}_{required_type.value}"
                error_msg = (
                    f"Tracker missing required data: {self.__class__.__name__} requires "
                    f"{required_type.value} but tracker does not provide it."
                )
                self._rate_limiter.log_rate_limited(logger, 'warning', error_key, error_msg)
                self._error_aggregator.record_error(error_key, logger)
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

    def _trigger_rtl(self, reason: str) -> None:
        """
        Trigger Return to Launch mode (WP9: consolidated from fw/mc_attitude_rate).

        Deduplicates calls via self.rtl_triggered flag so rapid safety checks
        do not spam multiple RTL commands.

        Args:
            reason (str): Human-readable reason string for logs/events.
        """
        if self.rtl_triggered:
            return

        self.rtl_triggered = True
        logger.critical(f"TRIGGERING RTL [{self.__class__.__name__}] — Reason: {reason}")

        try:
            if self.px4_controller and hasattr(self.px4_controller, 'trigger_return_to_launch'):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()  # noqa: F841 (kept for exception branch)
                    asyncio.create_task(self.px4_controller.trigger_return_to_launch())
                except RuntimeError:
                    asyncio.run(self.px4_controller.trigger_return_to_launch())
                logger.critical("RTL command issued successfully")
        except Exception as e:
            logger.error(f"Failed to trigger RTL: {e}")

        if hasattr(self, 'log_follower_event'):
            self.log_follower_event('rtl_triggered', reason=reason)