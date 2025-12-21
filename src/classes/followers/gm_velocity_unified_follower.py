# src/classes/followers/gimbal_follower.py

"""
GMVelocityUnifiedFollower Module - Clean Architecture Implementation
========================================================

Modern, clean implementation of GMVelocityUnifiedFollower using the new transformation
and target loss handling architecture. Designed for maintainability,
testability, and full integration with PixEagle safety systems.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- Mount-aware coordinate transformations (VERTICAL/HORIZONTAL)
- Unified target loss handling (works with any tracker)
- Circuit breaker integration for safe testing
- Zero hardcoding - fully YAML configurable
- Clean integration with existing follower patterns
- Comprehensive safety systems (RTL, emergency stop, altitude limits)
"""

import time
import math
import logging
from typing import Tuple, Optional, Dict, Any

from classes.followers.base_follower import BaseFollower
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.parameters import Parameters
from classes.followers.custom_pid import CustomPID

# Initialize logger before imports that might fail
logger = logging.getLogger(__name__)

# NOTE: Advanced gimbal transformation and target loss handling modules are optional
# The gimbal follower uses simplified, integrated coordinate transformation
# and target loss handling rather than separate architecture components
try:
    from classes.target_loss_handler import (
        create_target_loss_handler, TargetLossHandler, ResponseAction
    )
    TARGET_LOSS_HANDLER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Advanced target loss handler not available: {e}")
    TARGET_LOSS_HANDLER_AVAILABLE = False

# Import VelocityCommand for legacy callback methods
try:
    from classes.gimbal_transforms import VelocityCommand
except ImportError:
    # Create a simple local VelocityCommand if not available
    from dataclasses import dataclass

    @dataclass
    class VelocityCommand:
        """Simple velocity command container for backward compatibility."""
        forward: float = 0.0
        right: float = 0.0
        down: float = 0.0
        yaw_rate: float = 0.0

# Import circuit breaker for integration
try:
    from classes.circuit_breaker import FollowerCircuitBreaker
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False

class GMVelocityUnifiedFollower(BaseFollower):
    """
    Modern GMVelocityUnifiedFollower implementation using clean architecture.

    Integrates mount-aware transformations, unified target loss handling,
    and comprehensive safety systems for professional drone control.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initialize GMVelocityUnifiedFollower with new architecture.

        Args:
            px4_controller: PX4 interface for drone control
            initial_target_coords: Initial target coordinates (required by factory interface)
        """
        self.setpoint_profile = "gimbal_unified"  # GMVelocityUnifiedFollower always uses gimbal_unified profile
        self.follower_name = "GMVelocityUnifiedFollower"
        self.initial_target_coords = initial_target_coords

        # Load configuration from Parameters (needed for display name)
        self.config = getattr(Parameters, 'GMVelocityUnifiedFollower', {})
        if not self.config:
            raise ValueError("GMVelocityUnifiedFollower configuration not found in Parameters")

        # Set basic attributes needed for display name
        self.mount_type = self.config.get('MOUNT_TYPE', 'VERTICAL')
        self.control_mode = self.config.get('CONTROL_MODE', 'VELOCITY')

        # Initialize base follower with gimbal_unified setpoint profile
        super().__init__(px4_controller, self.setpoint_profile)

        # Initialize target loss handler (optional advanced feature)
        self.target_loss_handler = None
        if TARGET_LOSS_HANDLER_AVAILABLE:
            target_loss_config = self.config.get('TARGET_LOSS_HANDLING', {})
            try:
                self.target_loss_handler = create_target_loss_handler(target_loss_config, self.follower_name)
                self._register_target_loss_callbacks()
                logger.info(f"Target loss handler initialized with {target_loss_config.get('CONTINUE_VELOCITY_TIMEOUT', 3.0)}s timeout")
            except Exception as e:
                logger.warning(f"Failed to initialize target loss handler: {e} - using basic target loss logic")
                self.target_loss_handler = None

        # Control parameters
        self.max_velocity = self.config.get('MAX_VELOCITY', 8.0)
        # Use unified limit access (follower-specific overrides global SafetyLimits)
        self.max_yaw_rate = Parameters.get_effective_limit('MAX_YAW_RATE', 'GMVelocityUnifiedFollower')

        # Safety parameters using unified limit access
        self.emergency_stop_enabled = self.config.get('EMERGENCY_STOP_ENABLED', True)
        self.min_altitude_safety = Parameters.get_effective_limit('MIN_ALTITUDE', 'GMVelocityUnifiedFollower')
        self.max_altitude_safety = Parameters.get_effective_limit('MAX_ALTITUDE', 'GMVelocityUnifiedFollower')
        self.max_safety_violations = self.config.get('MAX_SAFETY_VIOLATIONS', 5)

        # Performance parameters
        self.update_rate = self.config.get('UPDATE_RATE', 20.0)
        self.command_smoothing_enabled = self.config.get('COMMAND_SMOOTHING_ENABLED', True)
        self.smoothing_factor = self.config.get('SMOOTHING_FACTOR', 0.8)

        # State tracking
        self.last_velocity_command: Optional[VelocityCommand] = None
        self.last_update_time = time.time()
        self.following_active = False
        self.emergency_stop_active = False

        # Enhanced Safety State (PHASE 3.3)
        self.altitude_safety_active = False
        self.last_safe_altitude = None
        self.safety_violations_count = 0
        self.last_safety_check_time = time.time()
        self.rtl_triggered = False
        self.altitude_recovery_in_progress = False

        # Statistics
        self.total_follow_calls = 0
        self.successful_transformations = 0
        self.target_loss_events = 0
        self.safety_interventions = 0

        # === Forward Velocity Control System ===
        # Based on 2024 guidance control research for reliable target interception
        self.forward_velocity_mode = self.config.get('FORWARD_VELOCITY_MODE', 'CONSTANT')
        self.base_forward_speed = self.config.get('BASE_FORWARD_SPEED', 2.0)
        self.current_forward_velocity = 0.0
        self.max_forward_velocity = self.config.get('MAX_FORWARD_VELOCITY', 5.0)
        self.forward_acceleration = self.config.get('FORWARD_ACCELERATION', 2.0)
        self.last_ramp_update_time = time.time()

        # === Lateral guidance configuration ===
        self.lateral_guidance_mode = self.config.get('LATERAL_GUIDANCE_MODE', 'coordinated_turn')
        self.enable_auto_mode_switching = self.config.get('ENABLE_AUTO_MODE_SWITCHING', False)
        self.guidance_mode_switch_velocity = self.config.get('GUIDANCE_MODE_SWITCH_VELOCITY', 3.0)
        self.active_lateral_mode = self.lateral_guidance_mode

        # === PID Controllers (initialized after mode determination) ===
        self.pid_right = None      # For sideslip mode (lateral velocity)
        self.pid_yaw_speed = None  # For coordinated turn mode (yaw rate)
        self.pid_down = None       # For vertical velocity (both modes)

        # Cache frequently accessed configuration parameters for performance
        self._cache_config_parameters()

        # Initialize PID controllers based on mount configuration and mode
        self._initialize_pid_controllers()

        logger.info(f"GMVelocityUnifiedFollower initialized: {self.mount_type} mount, {self.control_mode} control, {self.active_lateral_mode} guidance")

    def _cache_config_parameters(self):
        """Cache frequently accessed configuration parameters for performance optimization."""
        # Coordinate transformation parameters (accessed in every control loop)
        self.neutral_pitch = self.config.get('NEUTRAL_PITCH_ANGLE', 0.0)
        self.pitch_scaling_factor = self.config.get('PITCH_VELOCITY_SCALING', 0.15)
        self.pitch_deadzone = self.config.get('PITCH_DEADZONE_DEGREES', 2.0)
        self.max_roll_angle = self.config.get('MAX_ROLL_ANGLE', 90.0)
        self.max_pitch_angle = self.config.get('MAX_PITCH_ANGLE', 90.0)
        self.lateral_invert = self.config.get('INVERT_LATERAL_CONTROL', False)
        self.vertical_invert = self.config.get('INVERT_VERTICAL_CONTROL', False)

        # Performance optimization flags
        self.debug_logging_enabled = logger.isEnabledFor(logging.DEBUG)

        # Event-based logging state
        self.last_logged_mode = None
        self.last_logged_velocity = None
        self.significant_velocity_change_threshold = 0.5  # m/s

    def _initialize_pid_controllers(self):
        """Initialize PID controllers based on lateral guidance mode and configuration."""
        try:
            # Get initial setpoint (center of frame for gimbal following)
            setpoint_x = 0.0  # Center for gimbal following
            setpoint_y = 0.0  # Center for vertical control

            # Determine active lateral guidance mode
            self.active_lateral_mode = self._get_active_lateral_mode()

            # Initialize vertical PID controller (used in both modes)
            self.pid_down = CustomPID(
                *self._get_pid_gains('vel_body_down'),
                setpoint=setpoint_y,
                output_limits=(-2.0, 2.0)  # Limit vertical velocity
            )

            if self.active_lateral_mode == 'sideslip':
                # Sideslip Mode: Direct lateral velocity control
                self.pid_right = CustomPID(
                    *self._get_pid_gains('vel_body_right'),
                    setpoint=setpoint_x,
                    output_limits=(-3.0, 3.0)  # Limit lateral velocity
                )
                logger.debug(f"Sideslip mode PID initialized with gains {self._get_pid_gains('vel_body_right')}")

            elif self.active_lateral_mode == 'coordinated_turn':
                # Coordinated Turn Mode: Yaw rate control
                self.pid_yaw_speed = CustomPID(
                    *self._get_pid_gains('yawspeed_deg_s'),
                    setpoint=setpoint_x,
                    output_limits=(-45.0, 45.0)  # Limit yaw rate
                )
                logger.debug(f"Coordinated turn mode PID initialized with gains {self._get_pid_gains('yawspeed_deg_s')}")

            if self.debug_logging_enabled:
                logger.debug(f"PID controllers initialized for {self.active_lateral_mode} mode")

        except Exception as e:
            logger.error(f"Error initializing PID controllers: {e}")
            raise

    def _get_pid_gains(self, control_field: str) -> Tuple[float, float, float]:
        """Get PID gains for a specific control field from global PID configuration."""
        try:
            # Get PID gains from the global PID section (same as other followers)
            pid_config = getattr(Parameters, 'PID', None)
            if not pid_config:
                logger.warning("PID configuration not found in Parameters - using defaults")
                return 1.0, 0.0, 0.1

            pid_gains = pid_config.get('PID_GAINS', {})
            if not pid_gains:
                logger.warning("PID_GAINS section not found in PID configuration - using defaults")
                return 1.0, 0.0, 0.1

            gains = pid_gains.get(control_field)
            if not gains:
                logger.warning(f"PID gains for {control_field} not found - using defaults")
                return 1.0, 0.0, 0.1

            # Handle both uppercase and lowercase key formats
            p_gain = gains.get('p', gains.get('P', 1.0))
            i_gain = gains.get('i', gains.get('I', 0.0))
            d_gain = gains.get('d', gains.get('D', 0.1))

            logger.debug(f"PID gains for {control_field}: P={p_gain}, I={i_gain}, D={d_gain}")
            return p_gain, i_gain, d_gain

        except Exception as e:
            logger.error(f"Error getting PID gains for {control_field}: {e}")
            return 1.0, 0.0, 0.1  # Safe defaults

    # === MOUNT-AWARE COORDINATE TRANSFORMATION FUNCTIONS ===
    #
    # COORDINATE SYSTEM DOCUMENTATION:
    #
    # This implementation provides mount-aware coordinate transformations that handle
    # the fundamental differences between VERTICAL and HORIZONTAL gimbal mounts.
    #
    # VERTICAL MOUNT (typical for inspection/surveillance drones):
    # - Camera points down when gimbal is in neutral position
    # - Level/neutral: pitch=90°, roll=0°, yaw=0°
    # - Look up (ascend): pitch < 90° → negative vel_body_down
    # - Look down (descend): pitch > 90° → positive vel_body_down
    # - Look right: roll < 0° → lateral control (configurable direction)
    #
    # HORIZONTAL MOUNT (typical for racing/FPV drones):
    # - Camera points forward when gimbal is in neutral position
    # - Level/neutral: pitch=0°, roll=0°, yaw=0°
    # - Pitch up (ascend): pitch > 0° → negative vel_body_down
    # - Pitch down (descend): pitch < 0° → positive vel_body_down
    # - Roll right: roll > 0° → positive lateral control
    #
    # OUTPUT COORDINATE FRAME (NED/Body Frame):
    # - vel_body_fwd: Forward velocity (positive = forward)
    # - vel_body_right: Right velocity (positive = right)
    # - vel_body_down: Down velocity (positive = down, negative = up)
    # - yawspeed_deg_s: Yaw rate (positive = clockwise)

    def _transform_gimbal_to_control_frame(self, yaw_deg: float, pitch_deg: float, roll_deg: float) -> Tuple[float, float]:
        """
        Transform gimbal angles to normalized control errors based on mount type.

        This function implements mount-aware coordinate transformations that handle
        the fundamental differences between VERTICAL and HORIZONTAL gimbal mounts:

        VERTICAL Mount (pitch 90° = level):
        - Neutral/level: pitch=90°, roll=0°, yaw=0°
        - Look up: pitch < 90° → should ascend (negative vel_body_down)
        - Look down: pitch > 90° → should descend (positive vel_body_down)
        - Look right: roll < 0° → lateral control

        HORIZONTAL Mount (pitch 0° = level):
        - Standard drone conventions apply
        - Forward pitch positive → forward motion
        - Right roll positive → right motion

        Args:
            yaw_deg: Gimbal yaw angle in degrees
            pitch_deg: Gimbal pitch angle in degrees
            roll_deg: Gimbal roll angle in degrees

        Returns:
            Tuple[float, float]: (lateral_error, vertical_error) normalized to ±1.0 range
        """
        try:
            if self.mount_type == 'VERTICAL':
                return self._transform_vertical_mount(yaw_deg, pitch_deg, roll_deg)
            elif self.mount_type == 'HORIZONTAL':
                return self._transform_horizontal_mount(yaw_deg, pitch_deg, roll_deg)
            else:
                logger.error(f"Unknown mount type: {self.mount_type}. Defaulting to VERTICAL.")
                return self._transform_vertical_mount(yaw_deg, pitch_deg, roll_deg)

        except Exception as e:
            logger.error(f"Error in coordinate transformation: {e}")
            return 0.0, 0.0  # Safe neutral values

    def _transform_vertical_mount(self, yaw_deg: float, pitch_deg: float, roll_deg: float) -> Tuple[float, float]:
        """
        Transform gimbal angles for VERTICAL mount configuration.

        VERTICAL mount coordinate system:
        - Level/neutral: pitch = 90°, roll = 0°, yaw = 0°
        - Look up (ascend): pitch < 90° → negative vel_body_down
        - Look down (descend): pitch > 90° → positive vel_body_down
        - Look right: roll < 0° → negative lateral control
        - Look left: roll > 0° → positive lateral control

        Args:
            yaw_deg: Gimbal yaw angle in degrees
            pitch_deg: Gimbal pitch angle in degrees
            roll_deg: Gimbal roll angle in degrees

        Returns:
            Tuple[float, float]: (lateral_error, vertical_error) normalized to ±1.0
        """
        # VERTICAL mount neutral position
        neutral_pitch_vertical = 90.0  # Level = 90° for vertical mount
        neutral_roll = 0.0

        # Calculate angular errors from neutral position
        pitch_error = pitch_deg - neutral_pitch_vertical  # >0 = looking down, <0 = looking up
        roll_error = roll_deg - neutral_roll  # >0 = looking left, <0 = looking right

        # Normalize errors to ±1.0 range with systematic direction handling
        vertical_error = pitch_error / self.max_pitch_angle  # Positive = descend, Negative = ascend

        # Apply systematic roll direction convention handling
        roll_direction_multiplier = self._get_roll_direction_multiplier()
        lateral_error = (roll_error * roll_direction_multiplier) / self.max_roll_angle

        # Apply configuration-based inversions if needed
        if self.vertical_invert:
            vertical_error = -vertical_error
        if self.lateral_invert:
            lateral_error = -lateral_error

        # Clamp to safe range
        lateral_error = max(-1.0, min(1.0, lateral_error))
        vertical_error = max(-1.0, min(1.0, vertical_error))

        if self.debug_logging_enabled:
            logger.debug(f"🏔️ VERTICAL transform: P={pitch_deg:.1f}°(err={pitch_error:.1f}°) R={roll_deg:.1f}°(err={roll_error:.1f}°×{roll_direction_multiplier}) → lat={lateral_error:.3f} vert={vertical_error:.3f}")

        return lateral_error, vertical_error

    def _transform_horizontal_mount(self, yaw_deg: float, pitch_deg: float, roll_deg: float) -> Tuple[float, float]:
        """
        Transform gimbal angles for HORIZONTAL mount configuration.

        HORIZONTAL mount coordinate system (standard drone conventions):
        - Level/neutral: pitch = 0°, roll = 0°, yaw = 0°
        - Pitch up: pitch > 0° → ascend (negative vel_body_down)
        - Pitch down: pitch < 0° → descend (positive vel_body_down)
        - Roll right: roll > 0° → right lateral control
        - Roll left: roll < 0° → left lateral control

        Args:
            yaw_deg: Gimbal yaw angle in degrees
            pitch_deg: Gimbal pitch angle in degrees
            roll_deg: Gimbal roll angle in degrees

        Returns:
            Tuple[float, float]: (lateral_error, vertical_error) normalized to ±1.0
        """
        # HORIZONTAL mount neutral position (standard drone conventions)
        neutral_pitch_horizontal = self.neutral_pitch  # From config (typically 0°)
        neutral_roll = 0.0

        # Calculate angular errors from neutral position
        pitch_error = pitch_deg - neutral_pitch_horizontal  # >0 = pitch up, <0 = pitch down
        roll_error = roll_deg - neutral_roll  # >0 = roll right, <0 = roll left

        # Normalize errors to ±1.0 range with systematic direction handling
        # Note: For horizontal mount, positive pitch = ascend, so we invert for vel_body_down
        vertical_error = -pitch_error / self.max_pitch_angle  # Positive pitch = negative vel_body_down (ascend)

        # Apply systematic roll direction convention handling (same as vertical mount)
        roll_direction_multiplier = self._get_roll_direction_multiplier()
        lateral_error = (roll_error * roll_direction_multiplier) / self.max_roll_angle

        # Apply configuration-based inversions if needed
        if self.vertical_invert:
            vertical_error = -vertical_error
        if self.lateral_invert:
            lateral_error = -lateral_error

        # Clamp to safe range
        lateral_error = max(-1.0, min(1.0, lateral_error))
        vertical_error = max(-1.0, min(1.0, vertical_error))

        if self.debug_logging_enabled:
            logger.debug(f"📐 HORIZONTAL transform: P={pitch_deg:.1f}°(err={pitch_error:.1f}°) R={roll_deg:.1f}°(err={roll_error:.1f}°×{roll_direction_multiplier}) → lat={lateral_error:.3f} vert={vertical_error:.3f}")

        return lateral_error, vertical_error

    def _get_roll_direction_multiplier(self) -> float:
        """
        Get the systematic direction multiplier for roll-to-yaw mapping.

        This handles different gimbal roll conventions robustly:
        - POSITIVE: Look right = positive roll → need +1.0 multiplier
        - NEGATIVE: Look right = negative roll → need -1.0 multiplier

        The multiplier ensures:
        - Look right → positive yaw_speed (turn right)
        - Look left → negative yaw_speed (turn left)

        Returns:
            float: Direction multiplier (+1.0 or -1.0)
        """
        roll_right_sign = self.config.get('ROLL_RIGHT_SIGN', 'NEGATIVE')

        if roll_right_sign == 'POSITIVE':
            # Gimbal convention: Look right = positive roll
            # Raw error: roll - 0, so right = positive error
            # We want: positive error → positive yaw_speed (right turn)
            return +1.0
        else:
            # Gimbal convention: Look right = negative roll (default/legacy)
            # Raw error: roll - 0, so right = negative error
            # We want: negative error → positive yaw_speed (right turn)
            return -1.0

    def _calculate_forward_velocity(self, pitch_deg: float, dt: float) -> float:
        """
        Calculate forward velocity using research-based guidance control methods.

        This function implements multiple forward velocity control modes based on
        2024 guidance control research for reliable target interception.

        RESEARCH BACKGROUND:
        - Pitch-based speed control FAILS at target interception (speed→0 when aligned)
        - Constant speed ensures reliable target approach and interception
        - Proportional Navigation (PN) is industry standard for optimal guidance
        - Hybrid approaches provide best performance across scenarios

        CURRENT IMPLEMENTATION:
        - CONSTANT mode: Fixed forward speed with smooth ramping
        - Ensures drone always approaches target (never stops when aligned)
        - Foundation for future Proportional Navigation upgrade

        FUTURE MODES (ready for implementation):
        - PROPORTIONAL_NAV: speed = base_speed + K × line_of_sight_rate
        - HYBRID: Distance-based mode switching for optimal performance

        Args:
            pitch_deg: Current gimbal pitch angle in degrees
            dt: Time delta for ramping calculations

        Returns:
            float: Forward velocity in m/s
        """
        try:
            if self.forward_velocity_mode == 'CONSTANT':
                # CONSTANT SPEED MODE (Current Implementation)
                # Research-proven approach for reliable target interception
                target_velocity = min(self.base_forward_speed, self.max_forward_velocity)

                # Smooth ramping from current speed to target (prevents sudden jumps)
                velocity_change = self.forward_acceleration * dt

                if self.current_forward_velocity < target_velocity:
                    self.current_forward_velocity = min(
                        self.current_forward_velocity + velocity_change,
                        target_velocity
                    )
                elif self.current_forward_velocity > target_velocity:
                    self.current_forward_velocity = max(
                        self.current_forward_velocity - velocity_change,
                        target_velocity
                    )

                if self.debug_logging_enabled:
                    logger.debug(f"🚀 CONSTANT speed: target={target_velocity:.2f}, current={self.current_forward_velocity:.2f}, ramp_rate={velocity_change:.3f}")

                return self.current_forward_velocity

            elif self.forward_velocity_mode == 'PITCH_BASED':
                # LEGACY MODE (Problematic - kept for backward compatibility)
                # WARNING: This mode has the "stops at target" problem
                pitch_error = self._get_forward_pitch_error(pitch_deg)

                if abs(pitch_error) > self.pitch_deadzone:
                    target_velocity = min(abs(pitch_error) * self.pitch_scaling_factor, self.max_forward_velocity)
                    velocity_change = self.forward_acceleration * dt

                    if self.current_forward_velocity < target_velocity:
                        self.current_forward_velocity = min(
                            self.current_forward_velocity + velocity_change,
                            target_velocity
                        )
                    else:
                        self.current_forward_velocity = max(
                            self.current_forward_velocity - velocity_change,
                            target_velocity
                        )
                else:
                    # WARNING: This causes the "stops at target" problem!
                    self.current_forward_velocity = max(
                        self.current_forward_velocity - self.forward_acceleration * dt,
                        0.0
                    )

                if self.debug_logging_enabled:
                    logger.debug(f"⚠️ PITCH_BASED: pitch_error={pitch_error:.1f}°, speed={self.current_forward_velocity:.2f} (legacy mode)")

                return self.current_forward_velocity

            elif self.forward_velocity_mode == 'PROPORTIONAL_NAV':
                # FUTURE IMPLEMENTATION: Proportional Navigation Guidance Law
                # Based on missile guidance research - optimal for moving targets
                #
                # IMPLEMENTATION NOTES:
                # 1. Calculate line-of-sight (LOS) rate from gimbal angle changes
                # 2. Apply PN law: speed = base_speed + navigation_gain × |LOS_rate|
                # 3. Ensures optimal interception paths and collision courses
                # 4. Handles moving targets better than constant speed
                #
                # FORMULA: V = V_base + N × |λ̇|
                # Where: N = navigation constant (typically 3-5)
                #        λ̇ = line-of-sight rate (rad/s)
                #
                # TODO: Implement when LOS rate calculation is available
                logger.warning("PROPORTIONAL_NAV mode not yet implemented - falling back to CONSTANT")
                return self._calculate_forward_velocity_constant_mode(dt)

            else:
                logger.error(f"Unknown forward velocity mode: {self.forward_velocity_mode} - using CONSTANT")
                return self._calculate_forward_velocity_constant_mode(dt)

        except Exception as e:
            logger.error(f"Error calculating forward velocity: {e}")
            return 0.0  # Safe fallback

    def _calculate_forward_velocity_constant_mode(self, dt: float) -> float:
        """Helper method for constant speed mode (used by fallbacks)."""
        target_velocity = min(self.base_forward_speed, self.max_forward_velocity)
        velocity_change = self.forward_acceleration * dt

        if self.current_forward_velocity < target_velocity:
            self.current_forward_velocity = min(
                self.current_forward_velocity + velocity_change,
                target_velocity
            )
        elif self.current_forward_velocity > target_velocity:
            self.current_forward_velocity = max(
                self.current_forward_velocity - velocity_change,
                target_velocity
            )

        return self.current_forward_velocity

    def _get_forward_pitch_error(self, pitch_deg: float) -> float:
        """
        Calculate pitch error for legacy pitch-based forward velocity control.

        NOTE: This method is kept for backward compatibility with PITCH_BASED mode.
        The PITCH_BASED mode has known issues and is not recommended for production use.

        Args:
            pitch_deg: Current gimbal pitch angle in degrees

        Returns:
            float: Pitch error in degrees for forward velocity calculation
        """
        if self.mount_type == 'VERTICAL':
            # For vertical mount, forward motion is based on deviation from level (90°)
            return pitch_deg - 90.0
        else:
            # For horizontal mount, use configured neutral pitch
            return pitch_deg - self.neutral_pitch

    def _get_active_lateral_mode(self) -> str:
        """
        Determines the active lateral guidance mode based on configuration and flight state.

        Returns:
            str: 'sideslip' or 'coordinated_turn'
        """
        try:
            # Get configured mode
            configured_mode = self.lateral_guidance_mode

            # Check for auto-switching based on forward velocity
            if self.enable_auto_mode_switching:
                switch_velocity = self.guidance_mode_switch_velocity

                if self.current_forward_velocity >= switch_velocity:
                    return 'coordinated_turn'  # High speed: use coordinated turns
                else:
                    return 'sideslip'  # Low speed: use sideslip

            # Use configured mode
            return configured_mode

        except Exception as e:
            logger.error(f"Error determining lateral mode: {e}")
            return 'coordinated_turn'  # Safe default

    def _switch_lateral_mode(self, new_mode: str) -> None:
        """
        Switches between lateral guidance modes dynamically.

        Args:
            new_mode (str): New lateral guidance mode ('sideslip' or 'coordinated_turn')
        """
        try:
            if new_mode == self.active_lateral_mode:
                return  # Already in the requested mode

            if self.debug_logging_enabled:
                logger.debug(f"Switching lateral guidance mode: {self.active_lateral_mode} → {new_mode}")
            else:
                logger.info(f"📐 Guidance mode: {new_mode}")
            self.active_lateral_mode = new_mode

            # Initialize PID controllers for the new mode
            setpoint_x = 0.0  # Center for gimbal following

            if new_mode == 'sideslip' and self.pid_right is None:
                # Initialize sideslip PID controller
                self.pid_right = CustomPID(
                    *self._get_pid_gains('vel_body_right'),
                    setpoint=setpoint_x,
                    output_limits=(-3.0, 3.0)
                )
                logger.debug("Sideslip PID controller initialized during mode switch")

            elif new_mode == 'coordinated_turn' and self.pid_yaw_speed is None:
                # Initialize coordinated turn PID controller
                self.pid_yaw_speed = CustomPID(
                    *self._get_pid_gains('yawspeed_deg_s'),
                    setpoint=setpoint_x,
                    output_limits=(-45.0, 45.0)
                )
                logger.debug("Coordinated turn PID controller initialized during mode switch")

        except Exception as e:
            logger.error(f"Error switching lateral mode to {new_mode}: {e}")

    def _register_target_loss_callbacks(self):
        """Register callbacks for target loss response actions."""

        def continue_velocity_callback(response_data: Dict[str, Any]) -> bool:
            """Handle velocity continuation during target loss."""
            try:
                if self.last_velocity_command and response_data.get('velocity_continuation', False):
                    # Apply velocity decay if configured
                    velocity_cmd = self.last_velocity_command
                    decay_factor = response_data.get('velocity_decay_factor', 1.0)

                    if decay_factor < 1.0:
                        # Apply decay to velocity command
                        velocity_cmd.forward *= decay_factor
                        velocity_cmd.right *= decay_factor
                        velocity_cmd.yaw_rate *= decay_factor

                        logger.debug(f"Applied velocity decay: factor={decay_factor:.3f}")

                    # Continue with last velocity (with optional decay)
                    self._apply_velocity_command(velocity_cmd, "target_loss_continuation")
                    return True
                return False
            except Exception as e:
                logger.error(f"Error in continue velocity callback: {e}")
                return False

        def rtl_callback(response_data: Dict[str, Any]) -> bool:
            """Handle Return to Launch trigger."""
            try:
                if response_data.get('trigger_rtl', False):
                    rtl_altitude = response_data.get('rtl_altitude', self.config.get('TARGET_LOSS_HANDLING', {}).get('RTL_ALTITUDE', 50.0))

                    logger.warning(f"Target loss timeout - triggering RTL at {rtl_altitude}m altitude")

                    # Log the RTL event
                    self.log_follower_event(
                        "target_loss_rtl_triggered",
                        loss_duration=response_data.get('metadata', {}).get('loss_duration', 0.0),
                        rtl_altitude=rtl_altitude,
                        circuit_breaker_blocked=response_data.get('circuit_breaker_blocked', False)
                    )

                    # Trigger RTL if not blocked by circuit breaker
                    if not response_data.get('circuit_breaker_blocked', False):
                        # This would integrate with PX4 RTL functionality
                        # self.px4_controller.trigger_return_to_launch()
                        pass

                    return True
                return False
            except Exception as e:
                logger.error(f"Error in RTL callback: {e}")
                return False

        def hold_position_callback(response_data: Dict[str, Any]) -> bool:
            """Handle hold position command."""
            try:
                # Send zero velocity command to hold position
                hold_command = VelocityCommand(0.0, 0.0, 0.0, 0.0)
                self._apply_velocity_command(hold_command, "target_loss_hold_position")
                logger.info("Holding position due to target loss")
                return True
            except Exception as e:
                logger.error(f"Error in hold position callback: {e}")
                return False

        # Register the callbacks
        self.target_loss_handler.register_response_callback(ResponseAction.CONTINUE_VELOCITY, continue_velocity_callback)
        self.target_loss_handler.register_response_callback(ResponseAction.RETURN_TO_LAUNCH, rtl_callback)
        self.target_loss_handler.register_response_callback(ResponseAction.HOLD_POSITION, hold_position_callback)

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculate control commands based on tracker data and update the setpoint handler.

        This method implements the core gimbal follower control logic:
        1. Process gimbal angles or angular velocity data from tracker
        2. Transform coordinates based on mount configuration
        3. Apply safety validation and limits
        4. Update setpoint handler with transformed commands

        Args:
            tracker_data: TrackerOutput with gimbal angles or angular velocity data

        Raises:
            ValueError: If tracker data is invalid or incompatible
            RuntimeError: If transformation or command application fails
        """
        # DEBUG: Log only when debug is enabled for performance
        if self.debug_logging_enabled:
            logger.debug(f"🔧 calculate_control_commands() called - data_type: {tracker_data.data_type}, tracking_active: {tracker_data.tracking_active}")

        try:
            current_time = time.time()
            dt = current_time - self.last_ramp_update_time
            self.last_ramp_update_time = current_time

            # Extract and process gimbal data
            if tracker_data.data_type == TrackerDataType.GIMBAL_ANGLES:
                # Process gimbal angles (yaw, pitch, roll in degrees)
                gimbal_angles = tracker_data.angular
                if gimbal_angles is None:
                    raise ValueError("GIMBAL_ANGLES tracker data missing angular field")

                if len(gimbal_angles) < 3:
                    raise ValueError(f"GIMBAL_ANGLES expects 3 values (yaw, pitch, roll), got {len(gimbal_angles)}")

                yaw_deg, pitch_deg, roll_deg = gimbal_angles[0], gimbal_angles[1], gimbal_angles[2]

                # Event-based logging: only log significant angle changes
                if self.debug_logging_enabled:
                    logger.debug(f"🎯 Processing gimbal angles: Y={yaw_deg:.1f}° P={pitch_deg:.1f}° R={roll_deg:.1f}°")

                # === FORWARD VELOCITY CONTROL SYSTEM ===
                # Based on 2024 guidance control research for reliable target interception
                #
                # RESEARCH INSIGHTS:
                # - Current pitch-based method FAILS at target interception (speed→0 when aligned)
                # - Industry standard: Proportional Navigation (PN) with constant base speed
                # - Best practice: Constant speed ensures reliable target approach
                #
                # FUTURE UPGRADE PATH:
                # 1. CONSTANT speed (current) - reliable interception
                # 2. PROPORTIONAL_NAV - optimal guidance law (speed = base + K×LOS_rate)
                # 3. HYBRID - distance-based switching between modes
                forward_velocity = self._calculate_forward_velocity(pitch_deg, dt)

                # === MOUNT-AWARE COORDINATE TRANSFORMATION ===
                # Transform gimbal angles to control errors based on mount type
                lateral_error, vertical_error = self._transform_gimbal_to_control_frame(
                    yaw_deg, pitch_deg, roll_deg
                )

                # === LATERAL CONTROL (MODE-DEPENDENT) ===
                # Check if mode switching is needed
                new_mode = self._get_active_lateral_mode()
                if new_mode != self.active_lateral_mode:
                    self._switch_lateral_mode(new_mode)

                # Calculate lateral guidance commands based on active mode
                right_velocity = 0.0
                yaw_speed = 0.0

                if self.active_lateral_mode == 'sideslip':
                    # Sideslip Mode: Direct lateral velocity, no yaw
                    right_velocity = self.pid_right(lateral_error) if self.pid_right else 0.0
                    yaw_speed = 0.0

                elif self.active_lateral_mode == 'coordinated_turn':
                    # Coordinated Turn Mode: Yaw to track, no sideslip
                    right_velocity = 0.0
                    yaw_speed = self.pid_yaw_speed(lateral_error) if self.pid_yaw_speed else 0.0

                # === VERTICAL CONTROL ===
                # Calculate vertical command using mount-aware transformed error
                # vertical_error is normalized: positive = descend, negative = ascend
                # vel_body_down: positive = down, negative = up (NED/body frame convention)
                down_velocity = self.pid_down(vertical_error) if self.pid_down else 0.0

                # Apply velocity commands using coordinate frame-aware methods
                # These commands work correctly in both BODY and NED modes:
                # - BODY mode: Commands applied directly to body frame
                # - NED mode: Commands converted using drone attitude from MAVLink (like body_velocity_chase)
                # - Forward velocity: Body frame forward direction
                # - Right velocity: Body frame right direction
                # - Down velocity: Body frame down direction (NED convention)
                # - Yaw speed: Angular rate in degrees per second
                self.set_command_field("vel_body_fwd", forward_velocity)
                self.set_command_field("vel_body_right", right_velocity)
                self.set_command_field("vel_body_down", down_velocity)
                self.set_command_field("yawspeed_deg_s", yaw_speed)

                # Event-based logging: only log significant velocity or mode changes
                self._log_velocity_changes(forward_velocity, right_velocity, down_velocity, yaw_speed)

            elif tracker_data.data_type == TrackerDataType.ANGULAR:
                # Process angular rate data (input is rad/s, convert to deg/s for MAVSDK)
                angular_data = tracker_data.angular
                if angular_data is None:
                    raise ValueError("ANGULAR tracker data missing angular field")

                # For angular rates, expect (pitch_rate, yaw_rate) tuple in rad/s
                if len(angular_data) < 2:
                    raise ValueError(f"ANGULAR expects at least 2 values, got {len(angular_data)}")

                pitch_rate_rad, yaw_rate_rad = angular_data[0], angular_data[1]

                # Convert rad/s to deg/s (MAVSDK standard)
                import math
                pitch_deg_s = math.degrees(pitch_rate_rad)
                yaw_deg_s = math.degrees(yaw_rate_rad)

                # Apply angular rates using deg/s field names (MAVSDK standard)
                # Angular rates work the same in both BODY and NED modes
                self.set_command_field("rollspeed_deg_s", 0.0)  # No roll for gimbal following
                self.set_command_field("pitchspeed_deg_s", pitch_deg_s)
                self.set_command_field("yawspeed_deg_s", yaw_deg_s)
                self.set_command_field("thrust", self.config.get('DEFAULT_THRUST', 0.5))

                logger.debug(f"Applied angular rates (deg/s): pitch={pitch_deg_s:.2f}, yaw={yaw_deg_s:.2f}")

            else:
                # Unsupported tracker data type
                raise ValueError(f"Unsupported tracker data type: {tracker_data.data_type}")

        except Exception as e:
            logger.error(f"Error in calculate_control_commands: {e}")
            raise RuntimeError(f"Failed to calculate gimbal control commands: {e}")

    def follow_target(self, tracker_output: TrackerOutput) -> bool:
        """
        Main target following method.

        Args:
            tracker_output: Unified tracker output from any tracker type

        Returns:
            bool: True if following was successful, False otherwise
        """
        self.total_follow_calls += 1
        current_time = time.time()

        # DEBUG: Log follow_target calls only when debug enabled (performance optimization)
        if self.debug_logging_enabled:
            logger.debug(f"🎯 follow_target() called #{self.total_follow_calls} - tracking_active: {tracker_output.tracking_active}")

        try:
            # Comprehensive Safety Checks (PHASE 3.3)
            safety_status = self._perform_safety_checks(current_time)
            if not safety_status['safe_to_proceed']:
                logger.warning(f"Safety check failed: {safety_status['reason']} - blocking follow command")
                self.safety_interventions += 1
                self.log_follower_event("safety_intervention", **safety_status)
                return False

            # Handle target loss logic (with or without advanced handler)
            tracking_active = tracker_output.tracking_active

            if self.target_loss_handler:
                # Use advanced target loss handler if available
                loss_response = self.target_loss_handler.update_tracker_status(tracker_output)
                tracking_active = loss_response['tracking_active']

                # Log state changes
                if loss_response.get('state_changed', False):
                    self.log_follower_event(
                        "target_state_change",
                        new_state=loss_response['target_state'],
                        tracking_active=tracking_active,
                        recommended_actions=loss_response.get('recommended_actions', [])
                    )

            # Check if we should continue with normal following
            if tracking_active:
                # Normal tracking - extract gimbal angles and transform
                success = self._process_normal_tracking(tracker_output, current_time)
                if success:
                    self.successful_transformations += 1
                return success
            else:
                # Target lost - use basic or advanced target loss handling
                if self.target_loss_handler:
                    logger.debug(f"Target lost - state: {loss_response.get('target_state', 'LOST')}, actions: {loss_response.get('recommended_actions', [])}")
                else:
                    logger.debug("Target lost - using basic target loss handling")

                # Target loss handler callbacks are automatically executed (if available)
                # Just return False to indicate tracking is not active
                return False

        except Exception as e:
            logger.error(f"Error in follow_target: {e}")
            self.log_follower_event("follow_target_error", error=str(e))
            return False

        finally:
            self.last_update_time = current_time

    def _process_normal_tracking(self, tracker_output: TrackerOutput, current_time: float) -> bool:
        """
        Process normal tracking when target is active.

        Args:
            tracker_output: Active tracker output
            current_time: Current timestamp

        Returns:
            bool: True if processing was successful
        """
        try:
            # DEBUG: Log normal tracking processing (only when debug enabled)
            if self.debug_logging_enabled:
                logger.debug(f"🔄 Processing normal tracking - data_type: {tracker_output.data_type}, angular: {tracker_output.angular}")

            # Use the standard calculate_control_commands method
            self.calculate_control_commands(tracker_output)

            # Update state
            self.following_active = True
            self.last_tracker_output = tracker_output

            logger.debug("Normal tracking processed successfully")
            return True

        except Exception as e:
            logger.error(f"Error in normal tracking processing: {e}")
            return False

    # NOTE: Gimbal angle extraction is handled directly in calculate_control_commands()
    # This eliminates redundant processing and improves performance

    def _apply_velocity_command(self, velocity_command: VelocityCommand, source: str):
        """
        Apply velocity command to the drone.

        NOTE: This method is primarily used by target loss handler callbacks.
        Normal gimbal control uses set_command_field() for coordinate frame-aware control.

        Args:
            velocity_command: Velocity command to apply
            source: Source description for logging
        """
        try:
            # Safety checks
            if not self._validate_velocity_command(velocity_command):
                logger.warning(f"Velocity command failed safety validation (source: {source})")
                return

            # Apply smoothing if enabled
            if self.command_smoothing_enabled and self.last_velocity_command is not None:
                velocity_command = self._apply_velocity_smoothing(velocity_command)

            # Log the command
            logger.debug(f"Applying velocity command (source: {source}): "
                        f"fwd={velocity_command.forward:.3f}, right={velocity_command.right:.3f}, "
                        f"down={velocity_command.down:.3f}, yaw_rate={velocity_command.yaw_rate:.1f}")

            # Circuit breaker integration
            if self.is_circuit_breaker_active():
                self.log_follower_event(
                    "velocity_command_circuit_breaker",
                    source=source,
                    forward=velocity_command.forward,
                    right=velocity_command.right,
                    down=velocity_command.down,
                    yaw_rate=velocity_command.yaw_rate
                )
                return

            # Apply to setpoint handler
            self._update_setpoint_fields(velocity_command)

            # Log successful application
            self.log_follower_event(
                "velocity_command_applied",
                source=source,
                forward=velocity_command.forward,
                right=velocity_command.right,
                yaw_rate=velocity_command.yaw_rate
            )

        except Exception as e:
            logger.error(f"Error applying velocity command: {e}")

    def _validate_velocity_command(self, velocity_command: VelocityCommand) -> bool:
        """Validate velocity command against safety limits."""
        try:
            # Extract and validate numerical values with proper type checking
            try:
                forward = float(velocity_command.forward)
                right = float(velocity_command.right)
                down = float(velocity_command.down)
                yaw_rate = float(velocity_command.yaw_rate)
            except (TypeError, ValueError) as e:
                logger.warning(f"Velocity command contains non-numeric values: {e}")
                return False

            values = [forward, right, down, yaw_rate]

            # Check for NaN or infinity using proper math functions
            if any(math.isnan(v) or math.isinf(v) for v in values):
                logger.warning("Velocity command contains NaN or infinity values")
                return False

            # Check individual velocity components against limits
            if (abs(forward) > self.max_velocity or
                abs(right) > self.max_velocity or
                abs(down) > self.max_velocity):
                logger.warning(f"Velocity command exceeds limits: fwd={forward:.2f}, right={right:.2f}, down={down:.2f} (max={self.max_velocity})")
                return False

            # Check yaw rate against limits
            if abs(yaw_rate) > self.max_yaw_rate:
                logger.warning(f"Yaw rate exceeds limits: {yaw_rate:.2f} (max={self.max_yaw_rate})")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating velocity command: {e}")
            return False

    def _apply_velocity_smoothing(self, new_command: VelocityCommand) -> VelocityCommand:
        """Apply exponential smoothing to velocity commands."""
        if self.last_velocity_command is None:
            return new_command

        alpha = self.smoothing_factor
        return VelocityCommand(
            forward=alpha * new_command.forward + (1 - alpha) * self.last_velocity_command.forward,
            right=alpha * new_command.right + (1 - alpha) * self.last_velocity_command.right,
            down=alpha * new_command.down + (1 - alpha) * self.last_velocity_command.down,
            yaw_rate=alpha * new_command.yaw_rate + (1 - alpha) * self.last_velocity_command.yaw_rate
        )

    def _update_setpoint_fields(self, velocity_command: VelocityCommand):
        """
        Update setpoint handler fields using coordinate frame-aware methods.

        This method uses set_command_field() to ensure proper coordinate frame handling:
        - BODY mode: Commands applied directly to body frame
        - NED mode: Commands converted using drone attitude from MAVLink (like body_velocity_chase)
        """
        try:
            # Use coordinate frame-aware command setting (works for both BODY and NED modes)
            # These commands automatically handle coordinate frame conversion:
            # - BODY mode: Applied directly to body frame
            # - NED mode: Converted using drone attitude from MAVLink
            self.set_command_field("vel_body_fwd", velocity_command.forward)
            self.set_command_field("vel_body_right", velocity_command.right)
            self.set_command_field("vel_body_down", velocity_command.down)
            self.set_command_field("yawspeed_deg_s", velocity_command.yaw_rate)

        except Exception as e:
            logger.error(f"Error updating setpoint fields: {e}")

    def validate_target_coordinates(self, tracker_output: TrackerOutput) -> bool:
        """
        Validate tracker output for gimbal following.

        Args:
            tracker_output: Tracker output to validate

        Returns:
            bool: True if valid for gimbal following
        """
        try:
            # Check tracker output type
            if not isinstance(tracker_output, TrackerOutput):
                return False

            # Check if data type is supported
            supported_types = [TrackerDataType.GIMBAL_ANGLES, TrackerDataType.ANGULAR]
            if tracker_output.data_type not in supported_types:
                return False

            # Check if angular data is present when tracking is active
            if tracker_output.tracking_active:
                if not tracker_output.angular or len(tracker_output.angular) < 2:
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating target coordinates: {e}")
            return False

    def extract_target_coordinates(self, tracker_output: TrackerOutput) -> Optional[Tuple[float, float]]:
        """
        Extract target coordinates for compatibility with base follower interface.

        Args:
            tracker_output: Tracker output

        Returns:
            Tuple of (x, y) coordinates or None
        """
        try:
            if not tracker_output.tracking_active:
                return None

            # For gimbal, we can extract the angular data as coordinates
            if tracker_output.angular and len(tracker_output.angular) >= 2:
                # Return normalized angular coordinates
                yaw = tracker_output.angular[0] if len(tracker_output.angular) > 0 else 0.0
                pitch = tracker_output.angular[1] if len(tracker_output.angular) > 1 else 0.0

                # Normalize angles to [-1, 1] range for UI/validation
                # Yaw: -180° to +180° maps to -1.0 to +1.0
                normalized_yaw = max(-1.0, min(1.0, yaw / 180.0))
                # Pitch: -90° to +90° maps to -1.0 to +1.0
                normalized_pitch = max(-1.0, min(1.0, pitch / 90.0))

                return (normalized_yaw, normalized_pitch)

            return None

        except Exception as e:
            logger.error(f"Error extracting target coordinates: {e}")
            return None

    def emergency_stop(self):
        """Trigger emergency stop - immediately stop all movement."""
        logger.warning("⚠️ Emergency stop triggered")

        self.emergency_stop_active = True
        self.following_active = False

        # Send zero velocity commands using coordinate frame-aware methods
        try:
            self.set_command_field("vel_body_fwd", 0.0)
            self.set_command_field("vel_body_right", 0.0)
            self.set_command_field("vel_body_down", 0.0)
            self.set_command_field("yawspeed_deg_s", 0.0)
        except Exception as e:
            logger.error(f"Failed to set emergency zero velocities: {e}")

        # Reset target loss handler state if available
        if self.target_loss_handler:
            self.target_loss_handler.reset_state()

        self.log_follower_event("emergency_stop_triggered")

    def reset_emergency_stop(self) -> None:
        """Reset emergency stop state."""
        logger.info("✅ Emergency stop reset")
        self.emergency_stop_active = False
        self.log_follower_event("emergency_stop_reset")

    # ==================== Enhanced Safety Systems (PHASE 3.3) ====================

    def _perform_safety_checks(self, current_time: float) -> Dict[str, Any]:
        """
        Perform comprehensive safety checks before allowing follow commands.

        Returns:
            Dict with 'safe_to_proceed' boolean and 'reason' for any failures
        """
        # CIRCUIT BREAKER: Skip all safety checks when testing mode is enabled
        try:
            from classes.circuit_breaker import FollowerCircuitBreaker
            disable_safety = getattr(Parameters, 'CIRCUIT_BREAKER_DISABLE_SAFETY', False)
            if disable_safety and FollowerCircuitBreaker.is_active():
                logger.debug("Circuit breaker mode: Skipping all safety checks for testing")
                return {
                    'safe_to_proceed': True,
                    'reason': 'circuit_breaker_testing_mode',
                    'circuit_breaker_active': True
                }
        except ImportError:
            pass  # Circuit breaker not available

        # 1. Emergency stop check
        if self.emergency_stop_active:
            return {
                'safe_to_proceed': False,
                'reason': 'emergency_stop_active',
                'severity': 'critical'
            }

        # 2. RTL status check
        if self.rtl_triggered:
            return {
                'safe_to_proceed': False,
                'reason': 'rtl_in_progress',
                'severity': 'high'
            }

        # 3. Altitude safety check
        altitude_status = self._check_altitude_safety()
        if not altitude_status['safe']:
            return {
                'safe_to_proceed': False,
                'reason': f"altitude_violation_{altitude_status['violation_type']}",
                'severity': 'high',
                'current_altitude': altitude_status.get('current_altitude'),
                'safe_range': f"{self.min_altitude_safety}-{self.max_altitude_safety}m"
            }

        # 4. Safety violation accumulation check
        if self.safety_violations_count >= self.max_safety_violations:
            return {
                'safe_to_proceed': False,
                'reason': 'excessive_safety_violations',
                'severity': 'medium',
                'violation_count': self.safety_violations_count
            }

        # 5. Command rate limiting check (more lenient - only block if too frequent)
        min_interval = 1.0 / (self.update_rate * 2)  # Allow 2x the configured rate for safety checks
        if current_time - self.last_safety_check_time < min_interval:
            return {
                'safe_to_proceed': False,
                'reason': 'rate_limited',
                'severity': 'low',
                'min_interval': min_interval
            }

        # All safety checks passed
        self.last_safety_check_time = current_time
        return {
            'safe_to_proceed': True,
            'reason': 'all_checks_passed'
        }

    def _check_altitude_safety(self) -> Dict[str, Any]:
        """Check if drone altitude is within safe operating range."""
        # Skip safety checks in circuit breaker test mode
        try:
            from classes.circuit_breaker import FollowerCircuitBreaker
            if FollowerCircuitBreaker.should_skip_safety_checks():
                logger.debug("Altitude safety check skipped (circuit breaker test mode)")
                return {'safe': True, 'current_altitude': 0.0}
        except ImportError:
            pass  # Circuit breaker not available, continue with normal safety checks

        try:
            # Get current altitude using same pattern as other followers
            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)

            # Check altitude bounds
            if current_altitude < self.min_altitude_safety:
                return {
                    'safe': False,
                    'violation_type': 'too_low',
                    'current_altitude': current_altitude,
                    'threshold': self.min_altitude_safety
                }
            elif current_altitude > self.max_altitude_safety:
                return {
                    'safe': False,
                    'violation_type': 'too_high',
                    'current_altitude': current_altitude,
                    'threshold': self.max_altitude_safety
                }
            else:
                # Altitude is safe
                self.last_safe_altitude = current_altitude
                return {
                    'safe': True,
                    'current_altitude': current_altitude
                }

        except Exception as e:
            logger.error(f"Error checking altitude safety: {e}")
            return {
                'safe': False,
                'violation_type': 'status_unavailable',
                'error': str(e)
            }

    def trigger_emergency_stop(self, reason: str = "manual_trigger"):
        """Enhanced emergency stop with comprehensive state reset."""
        logger.critical(f"🚨 EMERGENCY STOP: {reason}")

        self.emergency_stop_active = True
        self.following_active = False
        self.velocity_continuation_active = False
        self.altitude_recovery_in_progress = False

        # Zero all velocity commands immediately using coordinate frame-aware methods
        try:
            self.set_command_field("vel_body_fwd", 0.0)
            self.set_command_field("vel_body_right", 0.0)
            self.set_command_field("vel_body_down", 0.0)
            logger.info("Emergency velocity zero commands applied")
        except Exception as e:
            logger.error(f"Failed to apply emergency velocity commands: {e}")

        # Reset target loss handler
        self.target_loss_handler.reset_state()

        # Log emergency event
        self.log_follower_event("emergency_stop", reason=reason,
                              timestamp=time.time(), safety_interventions=self.safety_interventions)

    def trigger_return_to_launch(self, reason: str = "safety_timeout", altitude: float = None):
        """Enhanced RTL with safety integration."""
        if self.rtl_triggered:
            logger.warning("RTL already in progress")
            return False

        rtl_altitude = altitude or self.config.get('TARGET_LOSS_HANDLING', {}).get('RTL_ALTITUDE', 50.0)

        logger.warning(f"🏠 RTL triggered: {reason} (alt: {rtl_altitude}m)")

        # Circuit breaker check
        try:
            from classes.circuit_breaker import FollowerCircuitBreaker
            if FollowerCircuitBreaker.is_active():
                FollowerCircuitBreaker.log_command_instead_of_execute(
                    command_type="return_to_launch",
                    follower_name=self.follower_name,
                    reason=reason,
                    rtl_altitude=rtl_altitude,
                    safety_interventions=self.safety_interventions
                )
                logger.info("RTL blocked by circuit breaker - logged instead")
                return False
        except ImportError:
            pass

        # Execute RTL
        try:
            self.px4_controller.send_return_to_launch_command()
            self.rtl_triggered = True
            self.following_active = False

            self.log_follower_event("rtl_triggered", reason=reason,
                                  altitude=rtl_altitude, timestamp=time.time())
            return True
        except Exception as e:
            logger.error(f"Failed to execute RTL: {e}")
            return False

    def reset_safety_state(self) -> None:
        """Reset all safety-related state variables."""
        logger.info("Resetting safety state for GMVelocityUnifiedFollower")

        self.emergency_stop_active = False
        self.altitude_safety_active = False
        self.safety_violations_count = 0
        self.rtl_triggered = False
        self.altitude_recovery_in_progress = False

        self.log_follower_event("safety_state_reset", timestamp=time.time())

    def _log_velocity_changes(self, forward: float, right: float, down: float, yaw_speed: float) -> None:
        """Log velocity commands only when they change significantly (event-based)."""
        try:
            current_velocity = (round(forward, 2), round(right, 2), round(down, 2), round(yaw_speed, 1))

            # Check for significant changes or mode changes
            velocity_changed = (
                self.last_logged_velocity is None or
                abs(current_velocity[0] - self.last_logged_velocity[0]) > self.significant_velocity_change_threshold or
                abs(current_velocity[1] - self.last_logged_velocity[1]) > self.significant_velocity_change_threshold or
                abs(current_velocity[2] - self.last_logged_velocity[2]) > self.significant_velocity_change_threshold or
                abs(current_velocity[3] - self.last_logged_velocity[3]) > 10.0  # 10°/s yaw change
            )

            mode_changed = self.last_logged_mode != self.active_lateral_mode

            if velocity_changed or mode_changed:
                logger.info(f"🚁 Gimbal→Velocity [{self.active_lateral_mode}]: fwd={current_velocity[0]} right={current_velocity[1]} down={current_velocity[2]} yaw={current_velocity[3]}°/s")
                self.last_logged_velocity = current_velocity
                self.last_logged_mode = self.active_lateral_mode

        except Exception as e:
            if self.debug_logging_enabled:
                logger.debug(f"Error logging velocity changes: {e}")

    def get_display_name(self) -> str:
        """Get display name for UI."""
        return f"Gimbal Follower ({self.mount_type} mount, {self.control_mode} control)"

    def get_status_info(self) -> Dict[str, Any]:
        """Get comprehensive status information."""
        return {
            'follower_type': 'GMVelocityUnifiedFollower',
            'display_name': self.get_display_name(),
            'following_active': self.following_active,
            'emergency_stop_active': self.emergency_stop_active,
            'configuration': {
                'mount_type': self.mount_type,
                'control_mode': self.control_mode,
                'max_velocity': self.max_velocity,
                'max_yaw_rate': self.max_yaw_rate
            },
            'coordinate_transformation': {
                'mount_type': self.mount_type,
                'control_mode': self.control_mode,
                'lateral_guidance_mode': self.active_lateral_mode
            },
            'target_loss_handler': self.target_loss_handler.get_statistics(),
            'statistics': {
                'total_follow_calls': self.total_follow_calls,
                'successful_transformations': self.successful_transformations,
                'success_rate': (self.successful_transformations / max(1, self.total_follow_calls)) * 100
            },
            'last_velocity_command': (
                {
                    'forward': self.last_velocity_command.forward,
                    'right': self.last_velocity_command.right,
                    'down': self.last_velocity_command.down,
                    'yaw_rate': self.last_velocity_command.yaw_rate
                } if self.last_velocity_command else None
            ),
            'circuit_breaker_active': self.is_circuit_breaker_active()
        }

    def get_follower_telemetry(self) -> Dict[str, Any]:
        """
        Override base telemetry to include gimbal-specific information,
        target loss handling state, and safety system status.
        """
        # Get base telemetry from parent class
        telemetry = super().get_follower_telemetry()

        # Add gimbal-specific information
        telemetry.update({
            # Gimbal Configuration
            'gimbal_mount_type': self.mount_type,
            'gimbal_control_mode': self.control_mode,
            'transformation_active': True,

            # Target Loss Handler State
            'target_loss_handler': {
                'state': self.target_loss_handler.get_current_state() if self.target_loss_handler else 'UNAVAILABLE',
                'timeout_remaining': self.target_loss_handler.get_timeout_remaining() if self.target_loss_handler else 0.0,
                'velocity_continuation_active': self.target_loss_handler.is_continuing_velocity() if self.target_loss_handler else False,
                'statistics': self.target_loss_handler.get_statistics() if self.target_loss_handler else {}
            },

            # Safety System Status
            'safety_systems': {
                'emergency_stop_active': self.emergency_stop_active,
                'altitude_safety_active': self.altitude_safety_active,
                'rtl_triggered': self.rtl_triggered,
                'safety_violations_count': self.safety_violations_count,
                'altitude_recovery_in_progress': self.altitude_recovery_in_progress,
                'min_altitude_limit': self.min_altitude_safety,
                'max_altitude_limit': self.max_altitude_safety
            },

            # Circuit Breaker Status
            'circuit_breaker_active': self.is_circuit_breaker_active(),

            # Performance Statistics
            'performance': {
                'total_follow_calls': self.total_follow_calls,
                'successful_transformations': self.successful_transformations,
                'success_rate_percent': (self.successful_transformations / max(1, self.total_follow_calls)) * 100,
                'recent_velocity_magnitude': (
                    (self.last_velocity_command.forward**2 +
                     self.last_velocity_command.right**2 +
                     self.last_velocity_command.down**2)**0.5
                    if self.last_velocity_command else 0.0
                )
            },

            # Enhanced Status
            'enhanced_status': {
                'display_name': self.get_display_name(),
                'last_command_timestamp': time.time() if self.last_velocity_command else None,
                'coordinate_transformation_ready': True  # Always ready since it's integrated
            }
        })

        return telemetry

    def __str__(self) -> str:
        """String representation for debugging."""
        return f"GMVelocityUnifiedFollower(mount={self.mount_type}, control={self.control_mode}, active={self.following_active})"