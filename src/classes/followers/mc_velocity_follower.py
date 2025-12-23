# src/classes/followers/mc_velocity_follower.py
"""
Multicopter Target Follower Module - Professional Dual-Mode Guidance
====================================================================

This module implements the MCVelocityFollower class for professional multicopter
target following with dual lateral guidance modes and optional Proportional Navigation.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- Dual lateral guidance modes: YAW_TO_TARGET and CRAB_STRAFE
- Multiple forward velocity modes: CONSTANT, PN (Proportional Navigation), LOS
- Body velocity offboard control (vel_body_fwd, vel_body_right, vel_body_down, yawspeed_deg_s)
- Target loss handling with HOVER behavior (multicopter advantage)
- Altitude safety monitoring with RTL capability
- Velocity saturation protection
- Emergency stop functionality
- Comprehensive telemetry and status reporting

Lateral Guidance Modes:
======================
- **YAW_TO_TARGET (Default)**: Drone rotates to face target, then pursues forward
  Best for: Natural flight behavior, high-speed pursuit, good forward visibility
  Control: vel_body_fwd = ramp, vel_body_right = 0, yawspeed = PID(horiz_err)

- **CRAB_STRAFE**: Drone maintains heading while strafing laterally
  Best for: Close range tracking, gimbal-stabilized cameras, responsive tracking
  Control: vel_body_fwd = ramp, vel_body_right = PID(horiz_err), yawspeed = 0

Forward Velocity Modes:
======================
- **CONSTANT**: Simple ramped acceleration to maximum velocity
- **PN (Proportional Navigation)**: Military-standard guidance with LOS rate scaling
- **LOS (Line-of-Sight)**: Direct velocity toward target

Critical Differences from Fixed-Wing:
====================================
- Can HOVER on target loss (instead of orbit)
- Can strafe laterally (CRAB_STRAFE mode)
- Uses velocity_body_offboard (not attitude_rate)
- No stall protection needed
- Zero forward velocity is acceptable
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
import numpy as np
import time
from enum import Enum
from typing import Tuple, Optional, Dict, Any, List, Deque
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class LateralGuidanceMode(Enum):
    """Lateral guidance mode enumeration for multicopter following."""
    YAW_TO_TARGET = "yaw_to_target"    # Rotate to face target, fly forward
    CRAB_STRAFE = "crab_strafe"         # Maintain heading, strafe laterally


class ForwardVelocityMode(Enum):
    """Forward velocity control mode enumeration."""
    CONSTANT = "constant"               # Simple ramp to max velocity
    PROPORTIONAL_NAVIGATION = "pn"      # Military-standard PN guidance
    LINE_OF_SIGHT = "los"               # Direct velocity toward target


class TargetLossAction(Enum):
    """Action to take when target is lost."""
    HOVER = "hover"                     # Hover in place (multicopter advantage)
    RTL = "rtl"                         # Return to launch
    SLOW_FORWARD = "slow_forward"       # Continue at reduced velocity


class MCVelocityFollower(BaseFollower):
    """
    Professional multicopter target follower with dual-mode lateral guidance.

    This follower uses offboard body velocity commands (forward, right, down, yaw speed)
    to achieve smooth target tracking with configurable lateral guidance modes,
    optional Proportional Navigation, and comprehensive safety monitoring.

    Control Strategy:
    ================
    - **Forward Velocity**: Ramped/PN/LOS controlled approach velocity
    - **Lateral Guidance**: Dual-mode approach:
      * YAW_TO_TARGET: Turn to face target (v_right = 0, yaw_rate ≠ 0)
      * CRAB_STRAFE: Strafe to center target (v_right ≠ 0, yaw_rate = 0)
    - **Vertical Control**: PID-controlled down velocity for altitude tracking

    Safety Features:
    ===============
    - Target loss triggers HOVER behavior (not orbit like fixed-wing)
    - Altitude safety monitoring with automatic RTL
    - Velocity saturation protection
    - Emergency stop capability
    - Comprehensive error handling

    Advantages over Fixed-Wing:
    ==========================
    - Can hover on target loss (no orbit required)
    - Can strafe laterally for responsive tracking
    - Zero forward velocity is acceptable
    - Uses stable velocity_body_offboard control
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the MCVelocityFollower with schema-aware dual-mode guidance.

        Args:
            px4_controller: Instance of PX4Controller to control the drone.
            initial_target_coords (Tuple[float, float]): Initial target coordinates.

        Raises:
            ValueError: If initial coordinates are invalid or schema initialization fails.
            RuntimeError: If PID controller initialization fails.
        """
        # Initialize with mc_velocity profile for offboard velocity control
        super().__init__(px4_controller, "mc_velocity")

        # Validate and store initial target coordinates
        if not self.validate_target_coordinates(initial_target_coords):
            raise ValueError(f"Invalid initial target coordinates: {initial_target_coords}")

        self.initial_target_coords = initial_target_coords

        # Get configuration section
        config = getattr(Parameters, 'MC_VELOCITY', {})

        # === LATERAL GUIDANCE MODE ===
        lateral_mode_str = config.get('LATERAL_GUIDANCE_MODE', 'yaw_to_target')
        self.lateral_guidance_mode = self._parse_lateral_mode(lateral_mode_str)
        self.enable_auto_mode_switching = config.get('ENABLE_AUTO_MODE_SWITCHING', False)
        self.auto_switch_distance_threshold = config.get('AUTO_SWITCH_DISTANCE_THRESHOLD', 20.0)

        # === FORWARD VELOCITY MODE ===
        fwd_mode_str = config.get('FORWARD_VELOCITY_MODE', 'constant')
        self.forward_velocity_mode = self._parse_forward_mode(fwd_mode_str)

        # === FORWARD VELOCITY PARAMETERS ===
        self.initial_forward_velocity = config.get('INITIAL_FORWARD_VELOCITY', 0.0)
        self.max_forward_velocity = config.get('MAX_FORWARD_VELOCITY', 8.0)
        self.forward_ramp_rate = config.get('FORWARD_RAMP_RATE', 2.0)

        # === PROPORTIONAL NAVIGATION PARAMETERS ===
        self.pn_navigation_constant = config.get('PN_NAVIGATION_CONSTANT', 4.0)
        self.pn_los_smoothing_alpha = config.get('PN_LOS_SMOOTHING_ALPHA', 0.3)
        self.pn_max_velocity_scale = config.get('PN_MAX_VELOCITY_SCALE', 2.0)
        self.pn_base_velocity = config.get('PN_BASE_VELOCITY', 4.0)

        # === LINE-OF-SIGHT PARAMETERS ===
        self.los_distance_gain = config.get('LOS_DISTANCE_GAIN', 0.5)
        self.los_max_velocity = config.get('LOS_MAX_VELOCITY', 10.0)

        # === TARGET LOSS HANDLING (HOVER BEHAVIOR) ===
        self.target_loss_timeout = config.get('TARGET_LOSS_TIMEOUT', 2.0)
        target_loss_action_str = config.get('TARGET_LOSS_ACTION', 'hover')
        self.target_loss_action = self._parse_target_loss_action(target_loss_action_str)
        self.target_loss_coord_threshold = config.get('TARGET_LOSS_COORDINATE_THRESHOLD', 990)
        self.ramp_down_on_target_loss = config.get('RAMP_DOWN_ON_TARGET_LOSS', True)
        self.slow_forward_velocity = config.get('SLOW_FORWARD_VELOCITY', 1.0)

        # === ALTITUDE SAFETY ===
        self.enable_altitude_safety = config.get('ENABLE_ALTITUDE_SAFETY', True)
        self.min_altitude_limit = Parameters.get_effective_limit('MIN_ALTITUDE', 'MC_VELOCITY')
        self.max_altitude_limit = Parameters.get_effective_limit('MAX_ALTITUDE', 'MC_VELOCITY')
        self.altitude_check_interval = config.get('ALTITUDE_CHECK_INTERVAL', 0.1)
        self.rtl_on_altitude_violation = config.get('RTL_ON_ALTITUDE_VIOLATION', True)
        self.altitude_warning_buffer = Parameters.get_effective_limit('ALTITUDE_WARNING_BUFFER', 'MC_VELOCITY')

        # === VELOCITY SATURATION PROTECTION ===
        self.enable_velocity_magnitude_limit = config.get('ENABLE_VELOCITY_MAGNITUDE_LIMIT', True)
        self.max_velocity_magnitude = config.get('MAX_VELOCITY_MAGNITUDE', 12.0)

        # === COMMAND SMOOTHING ===
        self.velocity_smoothing_enabled = config.get('VELOCITY_SMOOTHING_ENABLED', True)
        self.smoothing_factor = config.get('SMOOTHING_FACTOR', 0.8)

        # === SAFETY ===
        self.emergency_stop_enabled = config.get('EMERGENCY_STOP_ENABLED', True)
        self.max_tracking_error = config.get('MAX_TRACKING_ERROR', 1.5)

        # === RATE LIMITS (rad/s internally, matches position follower pattern) ===
        from math import radians, degrees
        self.max_yaw_rate_rad = radians(Parameters.get_effective_limit('MAX_YAW_RATE', 'MC_VELOCITY'))
        self._degrees = degrees  # Store for use in update_control()

        # === PERFORMANCE ===
        self.control_update_rate = config.get('CONTROL_UPDATE_RATE', 20.0)
        self.enable_altitude_control = config.get('ENABLE_ALTITUDE_CONTROL', True)

        # === RUNTIME STATE INITIALIZATION ===

        # Forward velocity state
        self.current_forward_velocity = self.initial_forward_velocity
        self.target_forward_velocity = self.max_forward_velocity
        self.last_update_time = time.time()

        # Target tracking state
        self.target_lost = False
        self.target_loss_start_time = None
        self.last_valid_target_coords = initial_target_coords

        # Safety monitoring state
        self.emergency_stop_active = False
        self.last_altitude_check_time = time.time()
        self.altitude_violation_count = 0

        # Velocity smoothing state
        self.smoothed_right_velocity = 0.0
        self.smoothed_down_velocity = 0.0
        self.smoothed_yaw_speed = 0.0
        self.smoothed_forward_velocity = 0.0

        # Active lateral guidance mode tracking
        self.active_lateral_mode = self.lateral_guidance_mode

        # Proportional Navigation state
        self.los_angle_history: Deque[Tuple[float, float]] = deque(maxlen=10)
        self.smoothed_los_rate = 0.0
        self.last_los_angle = None
        self.last_los_time = None

        # Telemetry tracking
        self.total_commands_issued = 0
        self.target_loss_events = 0
        self.mode_switch_events = 0

        # Initialize PID controllers
        self._initialize_pid_controllers()

        # Update telemetry metadata
        self.update_telemetry_metadata('controller_type', 'velocity_body_offboard')
        self.update_telemetry_metadata('control_strategy', 'multicopter_dual_mode_guidance')
        self.update_telemetry_metadata('lateral_guidance_modes', ['yaw_to_target', 'crab_strafe'])
        self.update_telemetry_metadata('forward_velocity_modes', ['constant', 'pn', 'los'])
        self.update_telemetry_metadata('active_lateral_mode', self.active_lateral_mode.value)
        self.update_telemetry_metadata('forward_velocity_mode', self.forward_velocity_mode.value)
        self.update_telemetry_metadata('target_loss_action', self.target_loss_action.value)
        self.update_telemetry_metadata('safety_features', [
            'altitude_monitoring', 'target_loss_hover', 'velocity_saturation_protection',
            'emergency_stop', 'dual_mode_guidance'
        ])

        logger.info(f"MCVelocityFollower initialized with dual-mode offboard velocity control")
        logger.info(f"Lateral guidance mode: {self.active_lateral_mode.value}")
        logger.info(f"Forward velocity mode: {self.forward_velocity_mode.value}")
        logger.info(f"Target loss action: {self.target_loss_action.value}")
        logger.debug(f"Initial target coordinates: {initial_target_coords}")
        logger.debug(f"Max forward velocity: {self.max_forward_velocity:.1f} m/s")

    # ==================== Mode Parsing Methods ====================

    def _parse_lateral_mode(self, mode_str: str) -> LateralGuidanceMode:
        """Parses lateral guidance mode string to enum."""
        mode_map = {
            'yaw_to_target': LateralGuidanceMode.YAW_TO_TARGET,
            'crab_strafe': LateralGuidanceMode.CRAB_STRAFE,
            'strafe': LateralGuidanceMode.CRAB_STRAFE,
            'yaw': LateralGuidanceMode.YAW_TO_TARGET,
        }
        return mode_map.get(mode_str.lower(), LateralGuidanceMode.YAW_TO_TARGET)

    def _parse_forward_mode(self, mode_str: str) -> ForwardVelocityMode:
        """Parses forward velocity mode string to enum."""
        mode_map = {
            'constant': ForwardVelocityMode.CONSTANT,
            'pn': ForwardVelocityMode.PROPORTIONAL_NAVIGATION,
            'proportional_navigation': ForwardVelocityMode.PROPORTIONAL_NAVIGATION,
            'los': ForwardVelocityMode.LINE_OF_SIGHT,
            'line_of_sight': ForwardVelocityMode.LINE_OF_SIGHT,
        }
        return mode_map.get(mode_str.lower(), ForwardVelocityMode.CONSTANT)

    def _parse_target_loss_action(self, action_str: str) -> TargetLossAction:
        """Parses target loss action string to enum."""
        action_map = {
            'hover': TargetLossAction.HOVER,
            'rtl': TargetLossAction.RTL,
            'slow_forward': TargetLossAction.SLOW_FORWARD,
            'continue': TargetLossAction.SLOW_FORWARD,
        }
        return action_map.get(action_str.lower(), TargetLossAction.HOVER)

    # ==================== PID Controller Initialization ====================

    def _initialize_pid_controllers(self) -> None:
        """
        Initializes PID controllers for lateral and vertical tracking.

        Creates PID controllers based on configured guidance mode:
        - YAW_TO_TARGET: Yaw Speed PID for turn-to-track control
        - CRAB_STRAFE: Right Velocity PID for lateral strafing
        - Always: Down Velocity PID for vertical tracking

        Raises:
            RuntimeError: If PID initialization fails.
        """
        try:
            # Use center (0.0, 0.0) as setpoints for center-tracking
            setpoint_x, setpoint_y = 0.0, 0.0

            # Initialize lateral guidance PIDs
            self.pid_yaw_speed = None
            self.pid_right = None

            # YAW_TO_TARGET: Yaw rate control (rad/s internally, converted to deg/s on output)
            self.pid_yaw_speed = CustomPID(
                *self._get_pid_gains('mc_yawspeed_deg_s'),
                setpoint=setpoint_x,
                output_limits=(-self.max_yaw_rate_rad, self.max_yaw_rate_rad)  # rad/s limits
            )
            logger.debug(f"Yaw speed PID initialized with gains {self._get_pid_gains('mc_yawspeed_deg_s')}")

            # CRAB_STRAFE: Lateral velocity control
            max_lateral = Parameters.get_effective_limit('MAX_VELOCITY_LATERAL', 'MC_VELOCITY')
            self.pid_right = CustomPID(
                *self._get_pid_gains('mc_vel_body_right'),
                setpoint=setpoint_x,
                output_limits=(-max_lateral, max_lateral)
            )
            logger.debug(f"Lateral velocity PID initialized with gains {self._get_pid_gains('mc_vel_body_right')}")

            # Down Velocity Controller - Vertical Control
            self.pid_down = None
            if self.enable_altitude_control:
                max_vertical = Parameters.get_effective_limit('MAX_VELOCITY_VERTICAL', 'MC_VELOCITY')
                self.pid_down = CustomPID(
                    *self._get_pid_gains('mc_vel_body_down'),
                    setpoint=setpoint_y,
                    output_limits=(-max_vertical, max_vertical)
                )
                logger.debug(f"Down velocity PID initialized with gains {self._get_pid_gains('mc_vel_body_down')}")
            else:
                logger.debug("Altitude control disabled - no down velocity PID controller created")

            logger.info(f"PID controllers initialized for MCVelocityFollower")

        except Exception as e:
            logger.error(f"Failed to initialize PID controllers: {e}")
            raise RuntimeError(f"PID controller initialization failed: {e}")

    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves PID gains for the specified control axis.

        Args:
            axis (str): Control axis name ('mc_yawspeed_deg_s', 'mc_vel_body_right', 'mc_vel_body_down').

        Returns:
            Tuple[float, float, float]: (P, I, D) gains for the specified axis.
        """
        try:
            gains = Parameters.PID_GAINS[axis]
            return gains['p'], gains['i'], gains['d']
        except KeyError as e:
            # Fall back to generic gains if multicopter-specific not found
            fallback_map = {
                'mc_yawspeed_deg_s': 'yawspeed_deg_s',
                'mc_vel_body_right': 'vel_body_right',
                'mc_vel_body_down': 'vel_body_down',
            }
            fallback = fallback_map.get(axis, axis)
            try:
                gains = Parameters.PID_GAINS[fallback]
                logger.debug(f"Using fallback PID gains '{fallback}' for axis '{axis}'")
                return gains['p'], gains['i'], gains['d']
            except KeyError:
                logger.error(f"PID gains not found for axis '{axis}' or fallback '{fallback}'")
                raise KeyError(f"Invalid PID axis '{axis}'. Check Parameters.PID_GAINS configuration.")

    def _update_pid_gains(self) -> None:
        """Updates all PID controller gains from current parameter configuration."""
        try:
            if self.pid_yaw_speed is not None:
                self.pid_yaw_speed.tunings = self._get_pid_gains('mc_yawspeed_deg_s')

            if self.pid_right is not None:
                self.pid_right.tunings = self._get_pid_gains('mc_vel_body_right')

            if self.pid_down is not None:
                self.pid_down.tunings = self._get_pid_gains('mc_vel_body_down')

            logger.debug(f"PID gains updated for MCVelocityFollower")

        except Exception as e:
            logger.error(f"Failed to update PID gains: {e}")

    # ==================== Lateral Guidance Mode Control ====================

    def _get_active_lateral_mode(self) -> LateralGuidanceMode:
        """
        Determines the active lateral guidance mode based on configuration and state.

        Returns:
            LateralGuidanceMode: Active guidance mode.
        """
        try:
            if self.enable_auto_mode_switching:
                # Auto-switching based on estimated target distance
                # Use LOS rate as proxy for distance (high rate = close target)
                if self.smoothed_los_rate > 0.1:  # High LOS rate indicates close target
                    return LateralGuidanceMode.CRAB_STRAFE
                else:
                    return LateralGuidanceMode.YAW_TO_TARGET

            return self.lateral_guidance_mode

        except Exception as e:
            logger.error(f"Error determining lateral mode: {e}")
            return LateralGuidanceMode.YAW_TO_TARGET

    def _switch_lateral_mode(self, new_mode: LateralGuidanceMode) -> None:
        """
        Switches between lateral guidance modes dynamically.

        Args:
            new_mode (LateralGuidanceMode): New lateral guidance mode.
        """
        try:
            if new_mode == self.active_lateral_mode:
                return

            old_mode = self.active_lateral_mode
            self.active_lateral_mode = new_mode
            self.mode_switch_events += 1

            # Reset the unused PID to prevent integral windup during switch
            if new_mode == LateralGuidanceMode.YAW_TO_TARGET:
                if self.pid_right:
                    self.pid_right.reset()
            else:  # CRAB_STRAFE
                if self.pid_yaw_speed:
                    self.pid_yaw_speed.reset()

            # Update telemetry
            self.update_telemetry_metadata('lateral_mode_switch', {
                'old_mode': old_mode.value,
                'new_mode': new_mode.value,
                'forward_velocity': self.current_forward_velocity,
                'timestamp': datetime.utcnow().isoformat()
            })
            self.update_telemetry_metadata('active_lateral_mode', new_mode.value)

            logger.info(f"Switched lateral guidance mode: {old_mode.value} → {new_mode.value}")

        except Exception as e:
            logger.error(f"Error switching lateral mode to {new_mode}: {e}")

    # ==================== Forward Velocity Control ====================

    def _calculate_forward_velocity(self, target_coords: Tuple[float, float], dt: float) -> float:
        """
        Calculates forward velocity based on the active forward velocity mode.

        Args:
            target_coords: Current target coordinates.
            dt: Time delta since last update.

        Returns:
            float: Calculated forward velocity in m/s.
        """
        try:
            # Determine target velocity based on mode
            if self.forward_velocity_mode == ForwardVelocityMode.CONSTANT:
                target_velocity = self._calculate_constant_velocity()
            elif self.forward_velocity_mode == ForwardVelocityMode.PROPORTIONAL_NAVIGATION:
                target_velocity = self._calculate_pn_velocity(target_coords, dt)
            elif self.forward_velocity_mode == ForwardVelocityMode.LINE_OF_SIGHT:
                target_velocity = self._calculate_los_velocity(target_coords)
            else:
                target_velocity = self._calculate_constant_velocity()

            # Apply ramping to smooth transitions
            velocity_error = target_velocity - self.current_forward_velocity
            if abs(velocity_error) < 0.01:
                self.current_forward_velocity = target_velocity
            else:
                max_change = self.forward_ramp_rate * dt
                velocity_change = np.clip(velocity_error, -max_change, max_change)
                self.current_forward_velocity += velocity_change

            # Apply limits
            self.current_forward_velocity = np.clip(
                self.current_forward_velocity,
                0.0,
                self.max_forward_velocity
            )

            return self.current_forward_velocity

        except Exception as e:
            logger.error(f"Error calculating forward velocity: {e}")
            return 0.0

    def _calculate_constant_velocity(self) -> float:
        """Calculates constant mode target velocity."""
        # Handle target loss
        if self.target_lost and self.ramp_down_on_target_loss:
            if self.target_loss_action == TargetLossAction.HOVER:
                return 0.0
            elif self.target_loss_action == TargetLossAction.SLOW_FORWARD:
                return self.slow_forward_velocity
            else:  # RTL
                return 0.0

        if self.emergency_stop_active:
            return 0.0

        return self.max_forward_velocity

    def _calculate_pn_velocity(self, target_coords: Tuple[float, float], dt: float) -> float:
        """
        Calculates Proportional Navigation velocity.

        PN Law: velocity scales with line-of-sight rate.
        Higher LOS rate = faster target = increase velocity.

        Args:
            target_coords: Current target coordinates.
            dt: Time delta.

        Returns:
            float: PN-based forward velocity.
        """
        try:
            current_time = time.time()

            # Calculate LOS angle from target position
            los_angle = np.arctan2(target_coords[0], 1.0)  # Horizontal angle

            # Calculate LOS rate
            if self.last_los_angle is not None and self.last_los_time is not None:
                los_dt = current_time - self.last_los_time
                if los_dt > 0.001:
                    raw_los_rate = (los_angle - self.last_los_angle) / los_dt

                    # Apply EMA filtering
                    alpha = self.pn_los_smoothing_alpha
                    self.smoothed_los_rate = alpha * raw_los_rate + (1 - alpha) * self.smoothed_los_rate

            # Store for next iteration
            self.last_los_angle = los_angle
            self.last_los_time = current_time
            self.los_angle_history.append((current_time, los_angle))

            # PN velocity calculation
            # V = V_base * (1 + N * |LOS_rate|)
            velocity_scale = 1.0 + self.pn_navigation_constant * abs(self.smoothed_los_rate)
            velocity_scale = min(velocity_scale, self.pn_max_velocity_scale)

            target_velocity = self.pn_base_velocity * velocity_scale

            # Apply target loss handling
            if self.target_lost and self.ramp_down_on_target_loss:
                if self.target_loss_action == TargetLossAction.HOVER:
                    return 0.0
                elif self.target_loss_action == TargetLossAction.SLOW_FORWARD:
                    return self.slow_forward_velocity

            if self.emergency_stop_active:
                return 0.0

            logger.debug(f"PN velocity: LOS_rate={self.smoothed_los_rate:.3f}, scale={velocity_scale:.2f}, "
                        f"velocity={target_velocity:.2f}")

            return target_velocity

        except Exception as e:
            logger.error(f"Error in PN velocity calculation: {e}")
            return self.pn_base_velocity

    def _calculate_los_velocity(self, target_coords: Tuple[float, float]) -> float:
        """
        Calculates Line-of-Sight velocity.

        Velocity proportional to "distance" (derived from target offset).

        Args:
            target_coords: Current target coordinates.

        Returns:
            float: LOS-based forward velocity.
        """
        try:
            # Use target offset magnitude as distance proxy
            # Larger offset = target is off-center = fly faster
            offset_magnitude = np.sqrt(target_coords[0]**2 + target_coords[1]**2)

            # V = K * distance_proxy
            target_velocity = self.los_distance_gain * offset_magnitude * 10.0  # Scale factor
            target_velocity = min(target_velocity, self.los_max_velocity)

            # Minimum velocity when target is centered
            min_velocity = 1.0  # Maintain at least 1 m/s when tracking
            target_velocity = max(target_velocity, min_velocity)

            # Apply target loss handling
            if self.target_lost and self.ramp_down_on_target_loss:
                if self.target_loss_action == TargetLossAction.HOVER:
                    return 0.0
                elif self.target_loss_action == TargetLossAction.SLOW_FORWARD:
                    return self.slow_forward_velocity

            if self.emergency_stop_active:
                return 0.0

            return target_velocity

        except Exception as e:
            logger.error(f"Error in LOS velocity calculation: {e}")
            return 1.0

    # ==================== Tracking Command Calculation ====================

    def _calculate_tracking_commands(self, target_coords: Tuple[float, float]) -> Tuple[float, float, float]:
        """
        Calculates lateral, vertical, and yaw commands based on active guidance mode.

        Args:
            target_coords: Normalized target coordinates from vision system.

        Returns:
            Tuple[float, float, float]: (right_velocity, down_velocity, yaw_speed) commands.
        """
        try:
            # Update PID gains
            self._update_pid_gains()

            # Check for mode switching
            new_mode = self._get_active_lateral_mode()
            if new_mode != self.active_lateral_mode:
                self._switch_lateral_mode(new_mode)

            # Calculate tracking errors
            error_x = -target_coords[0]  # Horizontal error (negative because we want to track toward)
            error_y = -target_coords[1]  # Vertical error

            # Initialize commands
            right_velocity = 0.0
            down_velocity = 0.0
            yaw_speed = 0.0

            # Calculate lateral guidance commands based on active mode
            if self.active_lateral_mode == LateralGuidanceMode.YAW_TO_TARGET:
                # YAW_TO_TARGET: Rotate to face target, no sideslip
                right_velocity = 0.0
                yaw_speed = self.pid_yaw_speed(error_x) if self.pid_yaw_speed else 0.0

            elif self.active_lateral_mode == LateralGuidanceMode.CRAB_STRAFE:
                # CRAB_STRAFE: Strafe laterally, minimal yaw
                right_velocity = self.pid_right(error_x) if self.pid_right else 0.0
                yaw_speed = 0.0

            # Calculate vertical command
            down_velocity = self.pid_down(error_y) if self.pid_down else 0.0

            # Apply velocity smoothing if enabled
            if self.velocity_smoothing_enabled:
                sf = self.smoothing_factor
                self.smoothed_right_velocity = sf * self.smoothed_right_velocity + (1 - sf) * right_velocity
                self.smoothed_down_velocity = sf * self.smoothed_down_velocity + (1 - sf) * down_velocity
                self.smoothed_yaw_speed = sf * self.smoothed_yaw_speed + (1 - sf) * yaw_speed

                right_velocity = self.smoothed_right_velocity
                down_velocity = self.smoothed_down_velocity
                yaw_speed = self.smoothed_yaw_speed

            # Apply tracking error limits
            if abs(error_x) > self.max_tracking_error or abs(error_y) > self.max_tracking_error:
                reduction_factor = 0.5
                right_velocity *= reduction_factor
                down_velocity *= reduction_factor
                yaw_speed *= reduction_factor
                logger.debug(f"Large tracking error detected, reducing commands by {reduction_factor}")

            logger.debug(f"Tracking commands ({self.active_lateral_mode.value}) - "
                        f"Right: {right_velocity:.2f} m/s, Down: {down_velocity:.2f} m/s, "
                        f"Yaw: {yaw_speed:.2f} deg/s, Errors: [{error_x:.2f}, {error_y:.2f}]")

            return right_velocity, down_velocity, yaw_speed

        except Exception as e:
            logger.error(f"Error calculating tracking commands: {e}")
            return 0.0, 0.0, 0.0

    # ==================== Target Loss Handling (HOVER Behavior) ====================

    def _handle_target_loss(self, target_coords: Tuple[float, float]) -> bool:
        """
        Handles target loss detection with HOVER behavior.

        Unlike fixed-wing (which must orbit), multicopters can HOVER in place
        when target is lost, providing a major safety advantage.

        Args:
            target_coords: Current target coordinates.

        Returns:
            bool: True if target is valid, False if target is lost.
        """
        try:
            current_time = time.time()

            # Check if target coordinates indicate a lost target
            threshold = self.target_loss_coord_threshold
            is_valid_target = (
                self.validate_target_coordinates(target_coords) and
                not (np.isnan(target_coords[0]) or np.isnan(target_coords[1])) and
                not (abs(target_coords[0]) > threshold or abs(target_coords[1]) > threshold)
            )

            if is_valid_target:
                # Target is valid
                if self.target_lost:
                    logger.info("Target recovered after loss - resuming tracking")
                    self.target_loss_events += 1
                self.target_lost = False
                self.target_loss_start_time = None
                self.last_valid_target_coords = target_coords
                return True
            else:
                # Target appears to be lost
                if not self.target_lost:
                    self.target_lost = True
                    self.target_loss_start_time = current_time
                    self.target_loss_events += 1
                    logger.warning(f"Target lost at coordinates: {target_coords} - "
                                  f"Action: {self.target_loss_action.value}")
                else:
                    loss_duration = current_time - self.target_loss_start_time
                    if loss_duration > self.target_loss_timeout:
                        logger.debug(f"Target lost for {loss_duration:.1f}s - "
                                    f"executing {self.target_loss_action.value}")

                        # Execute target loss action
                        if self.target_loss_action == TargetLossAction.RTL:
                            self._trigger_rtl("target_loss_timeout")

                return False

        except Exception as e:
            logger.error(f"Error in target loss handling: {e}")
            return False

    # ==================== Velocity Saturation Protection ====================

    def _apply_velocity_saturation_protection(
        self,
        fwd: float,
        right: float,
        down: float
    ) -> Tuple[float, float, float]:
        """
        Applies velocity magnitude limiting to prevent motor saturation.

        Args:
            fwd: Forward velocity.
            right: Right velocity.
            down: Down velocity.

        Returns:
            Tuple[float, float, float]: Saturated velocities.
        """
        if not self.enable_velocity_magnitude_limit:
            return fwd, right, down

        try:
            # Calculate total velocity magnitude
            magnitude = np.sqrt(fwd**2 + right**2 + down**2)

            if magnitude > self.max_velocity_magnitude:
                # Scale down proportionally
                scale = self.max_velocity_magnitude / magnitude
                fwd *= scale
                right *= scale
                down *= scale
                logger.debug(f"Velocity saturation: {magnitude:.2f} m/s > {self.max_velocity_magnitude} m/s, "
                            f"scale={scale:.3f}")

            return fwd, right, down

        except Exception as e:
            logger.error(f"Error in velocity saturation protection: {e}")
            return fwd, right, down

    # ==================== Safety Systems ====================

    def _check_altitude_safety(self) -> bool:
        """
        Monitors altitude safety bounds and triggers RTL if necessary.

        Returns:
            bool: True if altitude is safe, False if violation occurred.
        """
        # Skip safety checks in circuit breaker test mode
        try:
            from classes.circuit_breaker import FollowerCircuitBreaker
            if FollowerCircuitBreaker.should_skip_safety_checks():
                logger.debug("Altitude safety check skipped (circuit breaker test mode)")
                return True
        except ImportError:
            pass  # Circuit breaker not available, continue with normal safety checks

        if not self.enable_altitude_safety:
            return True

        try:
            current_time = time.time()

            if (current_time - self.last_altitude_check_time) < self.altitude_check_interval:
                return True

            self.last_altitude_check_time = current_time

            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)

            altitude_violation = (current_altitude < self.min_altitude_limit or
                                 current_altitude > self.max_altitude_limit)

            if altitude_violation:
                self.altitude_violation_count += 1
                logger.critical(f"ALTITUDE SAFETY VIOLATION! Current: {current_altitude:.1f}m, "
                              f"Limits: [{self.min_altitude_limit}-{self.max_altitude_limit}]m")

                if self.rtl_on_altitude_violation:
                    self._trigger_rtl("altitude_violation")

                self.emergency_stop_active = True
                self.update_telemetry_metadata('safety_violation', 'altitude_bounds')
                return False
            else:
                self.altitude_violation_count = 0

            return True

        except Exception as e:
            logger.error(f"Altitude safety check failed: {e}")
            return True

    def _trigger_rtl(self, reason: str) -> None:
        """Triggers Return to Launch via PX4 controller."""
        try:
            logger.critical(f"Triggering RTL due to: {reason}")

            if self.px4_controller and hasattr(self.px4_controller, 'trigger_return_to_launch'):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.create_task(self.px4_controller.trigger_return_to_launch())
                except RuntimeError:
                    asyncio.run(self.px4_controller.trigger_return_to_launch())
                logger.critical("RTL command issued successfully")
            else:
                logger.error("PX4 controller not available for RTL")

        except Exception as e:
            logger.error(f"Failed to trigger RTL: {e}")

    # ==================== Main Control Methods ====================

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculates and sets body velocity control commands with dual-mode guidance.

        Args:
            tracker_data (TrackerOutput): Structured tracker data with position, confidence, etc.
        """
        try:
            current_time = time.time()
            dt = current_time - self.last_update_time
            self.last_update_time = current_time

            # Extract target coordinates
            target_coords = self.extract_target_coordinates(tracker_data)
            if not target_coords:
                logger.warning("No valid target coordinates found")
                self._handle_tracking_failure()
                return

            # Handle target loss detection
            target_valid = self._handle_target_loss(target_coords)

            # Use last valid coordinates if target is lost
            tracking_coords = target_coords if target_valid else self.last_valid_target_coords

            # Calculate forward velocity
            forward_velocity = self._calculate_forward_velocity(tracking_coords, dt)

            # Calculate tracking commands (lateral + vertical)
            right_velocity, down_velocity, yaw_speed = self._calculate_tracking_commands(tracking_coords)

            # Apply velocity saturation protection
            forward_velocity, right_velocity, down_velocity = self._apply_velocity_saturation_protection(
                forward_velocity, right_velocity, down_velocity
            )

            # Apply emergency stop if active
            if self.emergency_stop_active:
                forward_velocity = 0.0
                right_velocity = 0.0
                down_velocity = 0.0
                yaw_speed = 0.0
                logger.debug("Emergency stop active - all commands set to zero")

            # Target loss hover behavior
            if self.target_lost and self.target_loss_action == TargetLossAction.HOVER:
                forward_velocity = 0.0
                right_velocity = 0.0
                down_velocity = 0.0
                yaw_speed = 0.0
                logger.debug("Target lost - HOVER mode active")

            # Update setpoint handler using schema-aware methods
            self.set_command_field('vel_body_fwd', forward_velocity)
            self.set_command_field('vel_body_right', right_velocity)
            self.set_command_field('vel_body_down', down_velocity)
            self.set_command_field('yawspeed_deg_s', self._degrees(yaw_speed))  # rad/s → deg/s

            self.total_commands_issued += 1

            # Update telemetry metadata
            self.update_telemetry_metadata('last_target_coords', target_coords)
            self.update_telemetry_metadata('target_valid', target_valid)
            self.update_telemetry_metadata('current_forward_velocity', forward_velocity)
            self.update_telemetry_metadata('active_lateral_mode', self.active_lateral_mode.value)
            self.update_telemetry_metadata('emergency_stop_active', self.emergency_stop_active)
            self.update_telemetry_metadata('target_lost', self.target_lost)

            logger.debug(f"MCVelocityFollower commands ({self.active_lateral_mode.value}) - "
                        f"Fwd: {forward_velocity:.2f}, Right: {right_velocity:.2f}, "
                        f"Down: {down_velocity:.2f} m/s, Yaw: {self._degrees(yaw_speed):.2f} deg/s")

        except Exception as e:
            logger.error(f"Error calculating control commands: {e}")
            self._set_safe_commands()

    def _set_safe_commands(self) -> None:
        """Sets safe fallback commands (all zeros)."""
        self.set_command_field('vel_body_fwd', 0.0)
        self.set_command_field('vel_body_right', 0.0)
        self.set_command_field('vel_body_down', 0.0)
        self.set_command_field('yawspeed_deg_s', 0.0)

    def _handle_tracking_failure(self) -> None:
        """Handles complete tracking failure with HOVER behavior."""
        try:
            logger.warning("Complete tracking failure detected - activating HOVER mode")

            # Zero all commands for hover
            self._set_safe_commands()

            # Update telemetry
            self.update_telemetry_metadata('tracking_failure', datetime.utcnow().isoformat())

        except Exception as e:
            logger.error(f"Error handling tracking failure: {e}")
            self.activate_emergency_stop()

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Executes target following with dual-mode multicopter guidance.

        Args:
            tracker_data (TrackerOutput): Structured tracker data with position and metadata.

        Returns:
            bool: True if following executed successfully, False otherwise.
        """
        try:
            # Validate tracker compatibility (errors are logged by base class with rate limiting)
            if not self.validate_tracker_compatibility(tracker_data):
                return False

            # Perform altitude safety check
            if not self._check_altitude_safety():
                logger.error("Altitude safety check failed - activating hover")
                return False

            # Calculate and apply control commands
            self.calculate_control_commands(tracker_data)

            logger.debug(f"MCVelocityFollower executed for tracker: {tracker_data.tracker_id}")
            return True

        except ValueError as e:
            # Validation errors - these indicate bad configuration or state
            logger.error(f"Validation error in {self.__class__.__name__}: {e}")
            raise  # Re-raise validation errors

        except RuntimeError as e:
            # Command execution errors - these indicate system failures
            logger.error(f"Runtime error in {self.__class__.__name__}: {e}")
            self.reset_command_fields()  # Reset to safe state
            return False

        except Exception as e:
            # Unexpected errors - log and fail safe
            logger.error(f"Unexpected error in {self.__class__.__name__}.follow_target(): {e}")
            self.reset_command_fields()
            return False

    # ==================== Status and Telemetry ====================

    def get_follower_status(self) -> Dict[str, Any]:
        """
        Returns comprehensive follower status for telemetry.

        Returns:
            Dict[str, Any]: Detailed status including velocities, modes, and safety state.
        """
        try:
            current_time = time.time()

            return {
                # Velocity State
                'current_forward_velocity': self.current_forward_velocity,
                'max_forward_velocity': self.max_forward_velocity,
                'smoothed_right_velocity': self.smoothed_right_velocity,
                'smoothed_down_velocity': self.smoothed_down_velocity,
                'smoothed_yaw_speed': self.smoothed_yaw_speed,

                # Guidance Mode State
                'active_lateral_mode': self.active_lateral_mode.value,
                'configured_lateral_mode': self.lateral_guidance_mode.value,
                'forward_velocity_mode': self.forward_velocity_mode.value,
                'auto_mode_switching_enabled': self.enable_auto_mode_switching,

                # Target Tracking State
                'target_lost': self.target_lost,
                'target_loss_action': self.target_loss_action.value,
                'target_loss_duration': (
                    (current_time - self.target_loss_start_time)
                    if self.target_loss_start_time else 0.0
                ),
                'last_valid_target_coords': self.last_valid_target_coords,

                # Safety Status
                'emergency_stop_active': self.emergency_stop_active,
                'altitude_violation_count': self.altitude_violation_count,
                'altitude_safety_enabled': self.enable_altitude_safety,

                # PN State (if applicable)
                'smoothed_los_rate': self.smoothed_los_rate,

                # Statistics
                'total_commands_issued': self.total_commands_issued,
                'target_loss_events': self.target_loss_events,
                'mode_switch_events': self.mode_switch_events,

                # Configuration
                'config': {
                    'max_forward_velocity': self.max_forward_velocity,
                    'ramp_rate': self.forward_ramp_rate,
                    'altitude_limits': [self.min_altitude_limit, self.max_altitude_limit],
                    'velocity_magnitude_limit': self.max_velocity_magnitude,
                    'smoothing_factor': self.smoothing_factor,
                }
            }

        except Exception as e:
            logger.error(f"Error generating follower status: {e}")
            return {'error': str(e)}

    def get_status_report(self) -> str:
        """
        Generates a comprehensive human-readable status report.

        Returns:
            str: Formatted status report.
        """
        try:
            status = self.get_follower_status()

            report = f"\n{'='*60}\n"
            report += f"MCVelocityFollower Status Report\n"
            report += f"{'='*60}\n"

            # Velocity Status
            report += f"Forward Velocity: {status.get('current_forward_velocity', 0.0):.2f} m/s "
            report += f"(max: {status.get('max_forward_velocity', 0.0):.2f} m/s)\n"
            report += f"Right Velocity: {status.get('smoothed_right_velocity', 0.0):.2f} m/s\n"
            report += f"Down Velocity: {status.get('smoothed_down_velocity', 0.0):.2f} m/s\n"
            report += f"Yaw Speed: {status.get('smoothed_yaw_speed', 0.0):.2f} deg/s\n"

            # Guidance Mode Status
            report += f"\nGuidance Modes:\n"
            report += f"  Lateral Mode: {status.get('active_lateral_mode', 'unknown').upper()}\n"
            report += f"  Forward Mode: {status.get('forward_velocity_mode', 'unknown').upper()}\n"
            report += f"  Auto-Switching: {'✓' if status.get('auto_mode_switching_enabled', False) else '✗'}\n"

            # Target Status
            report += f"\nTarget Status:\n"
            report += f"  Target Lost: {'✓' if status.get('target_lost', False) else '✗'}\n"
            report += f"  Loss Action: {status.get('target_loss_action', 'hover').upper()}\n"
            if status.get('target_lost', False):
                report += f"  Loss Duration: {status.get('target_loss_duration', 0.0):.1f}s\n"

            # Safety Status
            report += f"\nSafety Status:\n"
            report += f"  Emergency Stop: {'✓' if status.get('emergency_stop_active', False) else '✗'}\n"
            report += f"  Altitude Safety: {'✓' if status.get('altitude_safety_enabled', False) else '✗'}\n"
            report += f"  Altitude Violations: {status.get('altitude_violation_count', 0)}\n"

            # Statistics
            report += f"\nStatistics:\n"
            report += f"  Commands Issued: {status.get('total_commands_issued', 0)}\n"
            report += f"  Target Loss Events: {status.get('target_loss_events', 0)}\n"
            report += f"  Mode Switch Events: {status.get('mode_switch_events', 0)}\n"

            report += f"{'='*60}\n"
            return report

        except Exception as e:
            return f"Error generating status report: {e}"

    # ==================== Control Methods ====================

    def activate_emergency_stop(self) -> None:
        """Activates emergency stop mode - all velocities to zero."""
        try:
            self.emergency_stop_active = True
            self._set_safe_commands()
            self.update_telemetry_metadata('emergency_stop_activated', datetime.utcnow().isoformat())
            logger.critical("Emergency stop activated - all velocities set to zero")

        except Exception as e:
            logger.error(f"Error activating emergency stop: {e}")

    def deactivate_emergency_stop(self) -> None:
        """Deactivates emergency stop mode."""
        try:
            self.emergency_stop_active = False
            self.update_telemetry_metadata('emergency_stop_deactivated', datetime.utcnow().isoformat())
            logger.info("Emergency stop deactivated - normal operation resumed")

        except Exception as e:
            logger.error(f"Error deactivating emergency stop: {e}")

    def reset_follower_state(self) -> None:
        """Resets follower state to initial conditions."""
        try:
            # Reset velocity state
            self.current_forward_velocity = self.initial_forward_velocity
            self.smoothed_right_velocity = 0.0
            self.smoothed_down_velocity = 0.0
            self.smoothed_yaw_speed = 0.0

            # Reset tracking state
            self.target_lost = False
            self.target_loss_start_time = None

            # Reset safety state
            self.emergency_stop_active = False
            self.altitude_violation_count = 0

            # Reset timing
            self.last_update_time = time.time()
            self.last_altitude_check_time = time.time()

            # Reset PN state
            self.los_angle_history.clear()
            self.smoothed_los_rate = 0.0
            self.last_los_angle = None
            self.last_los_time = None

            # Reset lateral mode to configured default
            self.active_lateral_mode = self.lateral_guidance_mode

            # Reset PID integrators
            if self.pid_yaw_speed:
                self.pid_yaw_speed.reset()
            if self.pid_right:
                self.pid_right.reset()
            if self.pid_down:
                self.pid_down.reset()

            self.update_telemetry_metadata('state_reset', datetime.utcnow().isoformat())
            logger.info(f"MCVelocityFollower state reset - Mode: {self.active_lateral_mode.value}")

        except Exception as e:
            logger.error(f"Error resetting follower state: {e}")

    def set_lateral_mode(self, mode: str) -> bool:
        """
        Manually sets the lateral guidance mode.

        Args:
            mode (str): 'yaw_to_target' or 'crab_strafe'.

        Returns:
            bool: True if successful.
        """
        try:
            new_mode = self._parse_lateral_mode(mode)
            self._switch_lateral_mode(new_mode)
            return True
        except Exception as e:
            logger.error(f"Error setting lateral mode: {e}")
            return False

    def set_forward_velocity_mode(self, mode: str) -> bool:
        """
        Manually sets the forward velocity mode.

        Args:
            mode (str): 'constant', 'pn', or 'los'.

        Returns:
            bool: True if successful.
        """
        try:
            self.forward_velocity_mode = self._parse_forward_mode(mode)
            self.update_telemetry_metadata('forward_velocity_mode', self.forward_velocity_mode.value)
            logger.info(f"Forward velocity mode set to: {self.forward_velocity_mode.value}")
            return True
        except Exception as e:
            logger.error(f"Error setting forward velocity mode: {e}")
            return False
