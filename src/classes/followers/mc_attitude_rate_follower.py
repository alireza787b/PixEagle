# src/classes/followers/multicopter_attitude_rate_follower.py
"""
Multicopter Attitude Rate Follower Module
==========================================

This module implements the MCAttitudeRateFollower class for aggressive
multicopter target following using pure attitude rate control. It provides a more
responsive alternative to velocity-based control with explicit thrust management.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- Pure attitude rate control (rollspeed, pitchspeed, yawspeed, thrust)
- Explicit thrust management with altitude PID and pitch compensation
- Optional Proportional Navigation (PNG) guidance mode
- Coordinated turn dynamics with bank angle calculations
- Yaw error gating safety (don't dive until aligned)
- Target loss handling with HOVER behavior
- Altitude safety monitoring with RTL capability
- GPS-independent operation (inertial only)

When to Use This Follower:
=========================
- Target interception requiring aggressive response
- GPS-denied operations
- High-bandwidth maneuvers
- Vision-based servoing (IBVS)
- When velocity cascade latency is unacceptable

Key Differences from MulticopterFollower (velocity-based):
=========================================================
- Control Type: attitude_rate (not velocity_body_offboard)
- Altitude Control: Explicit thrust management (not automatic)
- Response: More aggressive and responsive
- GPS: Not required (inertial only)
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
import numpy as np
import time
from enum import Enum
from typing import Tuple, Optional, Dict, Any, Deque
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class GuidanceMode(Enum):
    """Guidance mode enumeration for attitude rate control."""
    DIRECT_RATE = "direct_rate"           # Direct PID-based rate control
    PROPORTIONAL_NAVIGATION = "png"        # Military-standard PNG guidance


class TargetLossAction(Enum):
    """Action to take when target is lost."""
    HOVER = "hover"                        # Hover in place (rates=0, hover thrust)
    RTL = "rtl"                            # Return to launch


class MCAttitudeRateFollower(BaseFollower):
    """
    Professional multicopter attitude rate follower for aggressive target tracking.

    This follower uses direct attitude rate commands (roll, pitch, yaw rates + thrust)
    to achieve fast, responsive target tracking. Unlike velocity-based control, it
    bypasses the velocity control loop for lower latency and more aggressive response.

    Control Strategy:
    ================
    - **Pitch Rate Control**: Vertical target tracking (nose up/down)
    - **Yaw Rate Control**: Horizontal target tracking (turn to face)
    - **Roll Rate Control**: Coordinated turns based on bank angle
    - **Thrust Control**: Explicit altitude management with pitch compensation

    Thrust Management (Critical):
    ===========================
    Unlike velocity control, attitude rate requires explicit thrust management:
    1. Hover thrust baseline (typically 0.5)
    2. Altitude PID correction for height hold
    3. Pitch angle compensation (vertical thrust = T * cos(pitch))

    Safety Features:
    ===============
    - Yaw error gating (don't dive until aligned with target)
    - Attitude angle limits (prevent flip)
    - Target loss → HOVER (rates=0, hover thrust)
    - Altitude safety monitoring with RTL
    - Emergency stop capability
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the MCAttitudeRateFollower with schema-aware attitude rate control.

        Args:
            px4_controller: Instance of PX4Controller to control the drone.
            initial_target_coords (Tuple[float, float]): Initial target coordinates.

        Raises:
            ValueError: If initial coordinates are invalid or initialization fails.
            RuntimeError: If PID controller initialization fails.
        """
        # Initialize with attitude_rate profile
        super().__init__(px4_controller, "multicopter_attitude_rate")

        # Validate and store initial target coordinates
        if not self.validate_target_coordinates(initial_target_coords):
            raise ValueError(f"Invalid initial target coordinates: {initial_target_coords}")

        self.initial_target_coords = initial_target_coords

        # Get configuration section
        config = getattr(Parameters, 'MC_ATTITUDE_RATE', {})

        # === GUIDANCE MODE ===
        guidance_mode_str = config.get('GUIDANCE_MODE', 'direct_rate')
        self.guidance_mode = self._parse_guidance_mode(guidance_mode_str)

        # === RATE LIMITS (deg/s) ===
        self.max_pitch_rate = config.get('MAX_PITCH_RATE', 45.0)
        self.max_roll_rate = config.get('MAX_ROLL_RATE', 45.0)
        self.max_yaw_rate = config.get('MAX_YAW_RATE', 60.0)

        # === ANGLE LIMITS (safety) ===
        self.max_pitch_angle = config.get('MAX_PITCH_ANGLE', 35.0)
        self.max_roll_angle = config.get('MAX_ROLL_ANGLE', 35.0)
        self.max_bank_angle = config.get('MAX_BANK_ANGLE', 30.0)

        # === THRUST MANAGEMENT (Critical) ===
        self.hover_thrust = config.get('HOVER_THRUST', 0.5)
        self.min_thrust = config.get('MIN_THRUST', 0.1)
        self.max_thrust = config.get('MAX_THRUST', 0.9)
        self.enable_pitch_thrust_compensation = config.get('ENABLE_PITCH_THRUST_COMPENSATION', True)
        self.pitch_compensation_gain = config.get('PITCH_COMPENSATION_GAIN', 0.5)

        # === ALTITUDE CONTROL ===
        self.enable_altitude_hold = config.get('ENABLE_ALTITUDE_HOLD', True)
        self.target_altitude_offset = config.get('TARGET_ALTITUDE_OFFSET', 0.0)
        self.initial_altitude = None  # Set on first update

        # === PROPORTIONAL NAVIGATION PARAMETERS ===
        self.pn_navigation_constant = config.get('PN_NAVIGATION_CONSTANT', 4.0)
        self.pn_los_smoothing_alpha = config.get('PN_LOS_SMOOTHING_ALPHA', 0.3)
        self.pn_closing_velocity = config.get('PN_CLOSING_VELOCITY', 5.0)

        # === YAW ERROR GATING (safety) ===
        self.enable_yaw_error_gating = config.get('ENABLE_YAW_ERROR_GATING', True)
        self.yaw_error_threshold = config.get('YAW_ERROR_THRESHOLD', 0.3)

        # === COORDINATED TURNS ===
        self.enable_coordinated_turns = config.get('ENABLE_COORDINATED_TURNS', True)
        self.turn_coordination_gain = config.get('TURN_COORDINATION_GAIN', 1.0)

        # === TARGET LOSS HANDLING ===
        self.target_loss_timeout = config.get('TARGET_LOSS_TIMEOUT', 2.0)
        target_loss_action_str = config.get('TARGET_LOSS_ACTION', 'hover')
        self.target_loss_action = self._parse_target_loss_action(target_loss_action_str)
        self.target_loss_coord_threshold = config.get('TARGET_LOSS_COORDINATE_THRESHOLD', 990)

        # === ALTITUDE SAFETY ===
        self.enable_altitude_safety = config.get('ENABLE_ALTITUDE_SAFETY', True)
        self.min_altitude_limit = Parameters.get_effective_limit('MIN_ALTITUDE', 'MC_ATTITUDE_RATE')
        self.max_altitude_limit = Parameters.get_effective_limit('MAX_ALTITUDE', 'MC_ATTITUDE_RATE')
        self.altitude_check_interval = config.get('ALTITUDE_CHECK_INTERVAL', 0.1)
        self.rtl_on_altitude_violation = config.get('RTL_ON_ALTITUDE_VIOLATION', True)

        # === COMMAND SMOOTHING ===
        self.rate_smoothing_enabled = config.get('RATE_SMOOTHING_ENABLED', True)
        self.smoothing_factor = config.get('SMOOTHING_FACTOR', 0.85)

        # === SAFETY ===
        self.emergency_stop_enabled = config.get('EMERGENCY_STOP_ENABLED', True)

        # === PERFORMANCE ===
        self.control_update_rate = config.get('CONTROL_UPDATE_RATE', 50.0)

        # === RUNTIME STATE ===

        # Control state
        self.dive_started = False
        self.last_bank_angle = 0.0
        self.last_thrust_command = self.hover_thrust

        # Target tracking state
        self.target_lost = False
        self.target_loss_start_time = None
        self.last_valid_target_coords = initial_target_coords

        # Safety state
        self.emergency_stop_active = False
        self.last_altitude_check_time = time.time()
        self.altitude_violation_count = 0

        # Smoothed commands
        self.smoothed_pitch_rate = 0.0
        self.smoothed_yaw_rate = 0.0
        self.smoothed_roll_rate = 0.0

        # PNG state
        self.los_angle_history: Deque[Tuple[float, float]] = deque(maxlen=10)
        self.smoothed_los_rate = 0.0
        self.last_los_angle = None
        self.last_los_time = None

        # Telemetry
        self.total_commands_issued = 0
        self.target_loss_events = 0

        # Initialize PID controllers
        self._initialize_pid_controllers()

        # Update telemetry metadata
        self.update_telemetry_metadata('controller_type', 'attitude_rate')
        self.update_telemetry_metadata('control_strategy', 'multicopter_attitude_rate')
        self.update_telemetry_metadata('guidance_mode', self.guidance_mode.value)
        self.update_telemetry_metadata('target_loss_action', self.target_loss_action.value)
        self.update_telemetry_metadata('safety_features', [
            'yaw_error_gating', 'altitude_safety', 'target_loss_hover',
            'pitch_thrust_compensation', 'emergency_stop'
        ])

        logger.info(f"MCAttitudeRateFollower initialized with attitude rate control")
        logger.info(f"Guidance mode: {self.guidance_mode.value}")
        logger.info(f"Target loss action: {self.target_loss_action.value}")
        logger.debug(f"Rate limits - Pitch: {self.max_pitch_rate}°/s, Yaw: {self.max_yaw_rate}°/s, "
                    f"Roll: {self.max_roll_rate}°/s")
        logger.debug(f"Thrust management - Hover: {self.hover_thrust}, Range: [{self.min_thrust}, {self.max_thrust}]")

    # ==================== Mode Parsing ====================

    def _parse_guidance_mode(self, mode_str: str) -> GuidanceMode:
        """Parses guidance mode string to enum."""
        mode_map = {
            'direct_rate': GuidanceMode.DIRECT_RATE,
            'direct': GuidanceMode.DIRECT_RATE,
            'png': GuidanceMode.PROPORTIONAL_NAVIGATION,
            'proportional_navigation': GuidanceMode.PROPORTIONAL_NAVIGATION,
        }
        return mode_map.get(mode_str.lower(), GuidanceMode.DIRECT_RATE)

    def _parse_target_loss_action(self, action_str: str) -> TargetLossAction:
        """Parses target loss action string to enum."""
        action_map = {
            'hover': TargetLossAction.HOVER,
            'rtl': TargetLossAction.RTL,
        }
        return action_map.get(action_str.lower(), TargetLossAction.HOVER)

    # ==================== PID Initialization ====================

    def _initialize_pid_controllers(self) -> None:
        """
        Initializes all PID controllers for attitude rate control.

        Creates PIDs for:
        - Pitch rate (vertical tracking)
        - Yaw rate (horizontal tracking)
        - Roll rate (coordinated turns)
        - Thrust (speed management - optional)
        - Altitude (height hold)

        Raises:
            RuntimeError: If PID initialization fails.
        """
        try:
            setpoint_x, setpoint_y = self.initial_target_coords

            # Pitch Rate Controller - Vertical Tracking (deg/s)
            self.pid_pitch_rate = CustomPID(
                *self._get_pid_gains('mcar_pitchspeed_deg_s'),
                setpoint=setpoint_y,
                output_limits=(-self.max_pitch_rate, self.max_pitch_rate)
            )
            logger.debug(f"Pitch rate PID initialized with gains {self._get_pid_gains('mcar_pitchspeed_deg_s')}")

            # Yaw Rate Controller - Horizontal Tracking (deg/s)
            self.pid_yaw_rate = CustomPID(
                *self._get_pid_gains('mcar_yawspeed_deg_s'),
                setpoint=setpoint_x,
                output_limits=(-self.max_yaw_rate, self.max_yaw_rate)
            )
            logger.debug(f"Yaw rate PID initialized with gains {self._get_pid_gains('mcar_yawspeed_deg_s')}")

            # Roll Rate Controller - Coordinated Turns (deg/s)
            self.pid_roll_rate = CustomPID(
                *self._get_pid_gains('mcar_rollspeed_deg_s'),
                setpoint=0.0,  # Updated dynamically based on bank angle
                output_limits=(-self.max_roll_rate, self.max_roll_rate)
            )
            logger.debug(f"Roll rate PID initialized with gains {self._get_pid_gains('mcar_rollspeed_deg_s')}")

            # Altitude Controller - Height Hold (thrust output)
            self.pid_altitude = None
            if self.enable_altitude_hold:
                self.pid_altitude = CustomPID(
                    *self._get_pid_gains('mcar_altitude'),
                    setpoint=0.0,  # Set when initial altitude is captured
                    output_limits=(-0.3, 0.3)  # Altitude correction bounds
                )
                logger.debug(f"Altitude PID initialized with gains {self._get_pid_gains('mcar_altitude')}")

            logger.info("All PID controllers initialized for MCAttitudeRateFollower")

        except Exception as e:
            logger.error(f"Failed to initialize PID controllers: {e}")
            raise RuntimeError(f"PID controller initialization failed: {e}")

    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves PID gains for the specified control axis.

        Args:
            axis (str): Control axis name with mcar_ prefix.

        Returns:
            Tuple[float, float, float]: (P, I, D) gains.
        """
        try:
            gains = Parameters.PID_GAINS[axis]
            return gains['p'], gains['i'], gains['d']
        except KeyError:
            # Fallback to generic attitude rate gains
            fallback_map = {
                'mcar_pitchspeed_deg_s': 'pitchspeed_deg_s',
                'mcar_yawspeed_deg_s': 'yawspeed_deg_s',
                'mcar_rollspeed_deg_s': 'rollspeed_deg_s',
                'mcar_thrust': 'thrust',
                'mcar_altitude': 'z',
            }
            fallback = fallback_map.get(axis, axis)
            try:
                gains = Parameters.PID_GAINS[fallback]
                logger.debug(f"Using fallback PID gains '{fallback}' for axis '{axis}'")
                return gains['p'], gains['i'], gains['d']
            except KeyError:
                logger.error(f"PID gains not found for axis '{axis}' or fallback")
                # Return safe defaults
                return (1.0, 0.1, 0.1)

    def _update_pid_gains(self) -> None:
        """Updates all PID gains from current configuration."""
        try:
            self.pid_pitch_rate.tunings = self._get_pid_gains('mcar_pitchspeed_deg_s')
            self.pid_yaw_rate.tunings = self._get_pid_gains('mcar_yawspeed_deg_s')
            self.pid_roll_rate.tunings = self._get_pid_gains('mcar_rollspeed_deg_s')
            if self.pid_altitude:
                self.pid_altitude.tunings = self._get_pid_gains('mcar_altitude')
            logger.debug("PID gains updated for MCAttitudeRateFollower")
        except Exception as e:
            logger.error(f"Failed to update PID gains: {e}")

    # ==================== Thrust Management (Critical) ====================

    def _calculate_thrust_command(self, current_altitude: float, current_pitch: float) -> float:
        """
        Calculates thrust command with altitude hold and pitch compensation.

        Unlike velocity control, attitude rate requires explicit thrust management:
        1. Hover thrust baseline
        2. Altitude PID correction
        3. Pitch angle compensation (vertical thrust = T * cos(pitch))

        Args:
            current_altitude (float): Current altitude in meters.
            current_pitch (float): Current pitch angle in degrees.

        Returns:
            float: Thrust command (0.0-1.0).
        """
        try:
            # Start with hover thrust baseline
            thrust = self.hover_thrust

            # Apply altitude hold correction
            if self.enable_altitude_hold and self.pid_altitude:
                # Set initial altitude on first call
                if self.initial_altitude is None:
                    self.initial_altitude = current_altitude
                    target_altitude = current_altitude + self.target_altitude_offset
                    self.pid_altitude.setpoint = target_altitude
                    logger.info(f"Initial altitude captured: {current_altitude:.1f}m, "
                               f"target: {target_altitude:.1f}m")

                # Calculate altitude error and correction
                altitude_error = self.pid_altitude.setpoint - current_altitude
                altitude_correction = self.pid_altitude(altitude_error)
                thrust += altitude_correction

                logger.debug(f"Altitude control - Target: {self.pid_altitude.setpoint:.1f}m, "
                            f"Current: {current_altitude:.1f}m, Correction: {altitude_correction:.3f}")

            # Apply pitch angle compensation
            # As pitch increases, vertical thrust component decreases: Tv = T * cos(pitch)
            # To maintain altitude, we need to increase total thrust: T = T_hover / cos(pitch)
            if self.enable_pitch_thrust_compensation:
                pitch_rad = np.deg2rad(abs(current_pitch))
                cos_pitch = np.cos(pitch_rad)

                # Avoid division by zero and limit compensation
                if cos_pitch > 0.5:  # Only compensate up to ~60° pitch
                    compensation_factor = (1.0 / cos_pitch) - 1.0
                    thrust_adjustment = compensation_factor * self.pitch_compensation_gain * self.hover_thrust
                    thrust += thrust_adjustment

                    logger.debug(f"Pitch compensation - Pitch: {current_pitch:.1f}°, "
                                f"cos: {cos_pitch:.3f}, adjustment: {thrust_adjustment:.3f}")

            # Clamp to valid range
            thrust = np.clip(thrust, self.min_thrust, self.max_thrust)

            self.last_thrust_command = thrust
            return thrust

        except Exception as e:
            logger.error(f"Error calculating thrust: {e}")
            return self.hover_thrust

    # ==================== Rate Control ====================

    def _calculate_tracking_rates(self, target_coords: Tuple[float, float]) -> Tuple[float, float]:
        """
        Calculates pitch and yaw rates based on guidance mode.

        Args:
            target_coords: Normalized target coordinates.

        Returns:
            Tuple[float, float]: (pitch_rate, yaw_rate) in deg/s.
        """
        if self.guidance_mode == GuidanceMode.DIRECT_RATE:
            return self._calculate_direct_rates(target_coords)
        elif self.guidance_mode == GuidanceMode.PROPORTIONAL_NAVIGATION:
            return self._calculate_png_rates(target_coords)
        else:
            return self._calculate_direct_rates(target_coords)

    def _calculate_direct_rates(self, target_coords: Tuple[float, float]) -> Tuple[float, float]:
        """
        Calculates rates using direct PID control.

        Args:
            target_coords: Normalized target coordinates.

        Returns:
            Tuple[float, float]: (pitch_rate, yaw_rate) in deg/s.
        """
        # Calculate tracking errors (invert for correct direction)
        error_y = (self.pid_pitch_rate.setpoint - target_coords[1]) * (-1)  # Vertical
        error_x = (self.pid_yaw_rate.setpoint - target_coords[0]) * (+1)   # Horizontal

        # Generate rate commands
        pitch_rate = self.pid_pitch_rate(error_y)
        yaw_rate = self.pid_yaw_rate(error_x)

        return pitch_rate, yaw_rate

    def _calculate_png_rates(self, target_coords: Tuple[float, float]) -> Tuple[float, float]:
        """
        Calculates rates using Proportional Navigation guidance.

        PNG Law: a_cmd = N * V_c * LOS_rate
        Where N is navigation constant (3-5 typical)

        Args:
            target_coords: Normalized target coordinates.

        Returns:
            Tuple[float, float]: (pitch_rate, yaw_rate) in deg/s.
        """
        try:
            current_time = time.time()

            # Calculate LOS angles
            los_angle_h = np.arctan2(target_coords[0], 1.0)  # Horizontal
            los_angle_v = np.arctan2(target_coords[1], 1.0)  # Vertical

            # Calculate LOS rates
            if self.last_los_angle is not None and self.last_los_time is not None:
                dt = current_time - self.last_los_time
                if dt > 0.001:
                    los_rate_h = (los_angle_h - self.last_los_angle[0]) / dt
                    los_rate_v = (los_angle_v - self.last_los_angle[1]) / dt

                    # Apply EMA filtering
                    alpha = self.pn_los_smoothing_alpha
                    self.smoothed_los_rate = alpha * np.sqrt(los_rate_h**2 + los_rate_v**2) + \
                                            (1 - alpha) * self.smoothed_los_rate

                    # PNG acceleration command
                    # a_cmd = N * V_c * LOS_rate
                    N = self.pn_navigation_constant
                    V_c = self.pn_closing_velocity

                    # Convert acceleration to rate commands
                    # For multicopter: pitch_rate ~ vertical acceleration, yaw_rate ~ lateral acceleration
                    yaw_rate = N * V_c * los_rate_h * np.rad2deg(1.0)  # Convert to deg/s
                    pitch_rate = N * V_c * los_rate_v * np.rad2deg(1.0)

                    # Clamp to limits
                    pitch_rate = np.clip(pitch_rate, -self.max_pitch_rate, self.max_pitch_rate)
                    yaw_rate = np.clip(yaw_rate, -self.max_yaw_rate, self.max_yaw_rate)

                    # Store for next iteration
                    self.last_los_angle = (los_angle_h, los_angle_v)
                    self.last_los_time = current_time
                    self.los_angle_history.append((current_time, (los_angle_h, los_angle_v)))

                    logger.debug(f"PNG rates - LOS_rate: {self.smoothed_los_rate:.4f}, "
                                f"Pitch: {pitch_rate:.2f}, Yaw: {yaw_rate:.2f}")

                    return pitch_rate, yaw_rate

            # First iteration - store values and use direct control
            self.last_los_angle = (los_angle_h, los_angle_v)
            self.last_los_time = current_time
            return self._calculate_direct_rates(target_coords)

        except Exception as e:
            logger.error(f"PNG calculation error: {e}")
            return self._calculate_direct_rates(target_coords)

    # ==================== Coordinated Turn ====================

    def _calculate_coordinated_roll_rate(self, yaw_rate: float, ground_speed: float,
                                          current_roll: float) -> float:
        """
        Calculates roll rate for coordinated turns.

        Bank Angle = arctan((yaw_rate * speed) / g)

        Args:
            yaw_rate: Commanded yaw rate in deg/s.
            ground_speed: Current ground speed in m/s.
            current_roll: Current roll angle in degrees.

        Returns:
            float: Commanded roll rate in deg/s.
        """
        if not self.enable_coordinated_turns:
            return 0.0

        try:
            # Calculate target bank angle
            target_bank = self._calculate_target_bank_angle(yaw_rate, ground_speed)

            # Calculate bank angle error
            bank_error = -1.0 * (target_bank - current_roll) * self.turn_coordination_gain

            # Generate roll rate command
            roll_rate = self.pid_roll_rate(bank_error)

            self.last_bank_angle = target_bank

            logger.debug(f"Coordinated turn - Target bank: {target_bank:.1f}°, "
                        f"Current: {current_roll:.1f}°, Roll rate: {roll_rate:.2f}°/s")

            return roll_rate

        except Exception as e:
            logger.error(f"Coordinated turn calculation error: {e}")
            return 0.0

    def _calculate_target_bank_angle(self, yaw_rate: float, ground_speed: float) -> float:
        """Calculates target bank angle for coordinated turn."""
        safe_speed = max(ground_speed, 1.0)
        yaw_rate_rad = np.deg2rad(yaw_rate)
        g = 9.81

        target_bank_rad = np.arctan((yaw_rate_rad * safe_speed) / g)
        target_bank = np.rad2deg(target_bank_rad)
        target_bank = np.clip(target_bank, -self.max_bank_angle, self.max_bank_angle)

        return target_bank

    # ==================== Safety Systems ====================

    def _apply_yaw_error_gating(self, yaw_error: float, pitch_rate: float,
                                 thrust: float) -> Tuple[float, float]:
        """
        Applies yaw error gating - don't dive until aligned.

        Args:
            yaw_error: Current yaw tracking error (normalized).
            pitch_rate: Calculated pitch rate.
            thrust: Calculated thrust.

        Returns:
            Tuple[float, float]: (gated_pitch_rate, gated_thrust).
        """
        if not self.enable_yaw_error_gating:
            self.dive_started = True
            return pitch_rate, thrust

        # Check if aligned enough to start diving
        if self.dive_started or abs(yaw_error) < self.yaw_error_threshold:
            if not self.dive_started:
                self.dive_started = True
                logger.info(f"Dive mode activated - yaw error {abs(yaw_error):.3f} < {self.yaw_error_threshold}")
            return pitch_rate, thrust
        else:
            # Hold level until aligned
            logger.debug(f"Yaw error gating active - error: {abs(yaw_error):.3f} > {self.yaw_error_threshold}")
            return 0.0, self.hover_thrust

    def _handle_target_loss(self, target_coords: Tuple[float, float]) -> bool:
        """
        Handles target loss detection with HOVER behavior.

        Args:
            target_coords: Current target coordinates.

        Returns:
            bool: True if target is valid, False if lost.
        """
        try:
            current_time = time.time()
            threshold = self.target_loss_coord_threshold

            is_valid = (
                self.validate_target_coordinates(target_coords) and
                not (np.isnan(target_coords[0]) or np.isnan(target_coords[1])) and
                not (abs(target_coords[0]) > threshold or abs(target_coords[1]) > threshold)
            )

            if is_valid:
                if self.target_lost:
                    logger.info("Target recovered after loss")
                    self.target_loss_events += 1
                self.target_lost = False
                self.target_loss_start_time = None
                self.last_valid_target_coords = target_coords
                return True
            else:
                if not self.target_lost:
                    self.target_lost = True
                    self.target_loss_start_time = current_time
                    self.target_loss_events += 1
                    logger.warning(f"Target lost at coordinates: {target_coords}")
                else:
                    loss_duration = current_time - self.target_loss_start_time
                    if loss_duration > self.target_loss_timeout:
                        logger.debug(f"Target lost for {loss_duration:.1f}s")
                        if self.target_loss_action == TargetLossAction.RTL:
                            self._trigger_rtl("target_loss_timeout")

                return False

        except Exception as e:
            logger.error(f"Target loss handling error: {e}")
            return False

    def _check_altitude_safety(self) -> bool:
        """Monitors altitude bounds and triggers RTL if violated."""
        if not self.enable_altitude_safety:
            return True

        try:
            current_time = time.time()
            if (current_time - self.last_altitude_check_time) < self.altitude_check_interval:
                return True
            self.last_altitude_check_time = current_time

            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)

            if current_altitude < self.min_altitude_limit or current_altitude > self.max_altitude_limit:
                self.altitude_violation_count += 1
                logger.critical(f"ALTITUDE VIOLATION! {current_altitude:.1f}m, "
                              f"Limits: [{self.min_altitude_limit}-{self.max_altitude_limit}]m")

                if self.rtl_on_altitude_violation:
                    self._trigger_rtl("altitude_violation")

                self.emergency_stop_active = True
                return False

            return True

        except Exception as e:
            logger.error(f"Altitude safety check error: {e}")
            return True

    def _trigger_rtl(self, reason: str) -> None:
        """Triggers Return to Launch."""
        try:
            logger.critical(f"Triggering RTL: {reason}")
            if self.px4_controller and hasattr(self.px4_controller, 'trigger_return_to_launch'):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.create_task(self.px4_controller.trigger_return_to_launch())
                except RuntimeError:
                    asyncio.run(self.px4_controller.trigger_return_to_launch())
        except Exception as e:
            logger.error(f"RTL trigger failed: {e}")

    # ==================== Main Control Methods ====================

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculates and sets attitude rate control commands.

        Args:
            tracker_data: Structured tracker data with position.
        """
        try:
            # Extract target coordinates
            target_coords = self.extract_target_coordinates(tracker_data)
            if not target_coords:
                logger.warning("No valid target coordinates")
                self._set_hover_commands()
                return

            # Update PID gains
            self._update_pid_gains()

            # Handle target loss
            if not self._handle_target_loss(target_coords):
                self._set_hover_commands()
                return

            # Get current flight state
            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)
            current_pitch = getattr(self.px4_controller, 'current_pitch', 0.0)
            current_roll = getattr(self.px4_controller, 'current_roll', 0.0)
            current_speed = getattr(self.px4_controller, 'current_ground_speed', 1.0)

            # Calculate tracking rates
            pitch_rate, yaw_rate = self._calculate_tracking_rates(target_coords)

            # Calculate thrust with altitude hold and pitch compensation
            thrust = self._calculate_thrust_command(current_altitude, current_pitch)

            # Apply yaw error gating
            yaw_error = target_coords[0]  # Horizontal error
            pitch_rate, thrust = self._apply_yaw_error_gating(yaw_error, pitch_rate, thrust)

            # Calculate coordinated turn roll rate
            roll_rate = self._calculate_coordinated_roll_rate(yaw_rate, current_speed, current_roll)

            # Apply smoothing
            if self.rate_smoothing_enabled:
                sf = self.smoothing_factor
                self.smoothed_pitch_rate = sf * self.smoothed_pitch_rate + (1 - sf) * pitch_rate
                self.smoothed_yaw_rate = sf * self.smoothed_yaw_rate + (1 - sf) * yaw_rate
                self.smoothed_roll_rate = sf * self.smoothed_roll_rate + (1 - sf) * roll_rate
                pitch_rate = self.smoothed_pitch_rate
                yaw_rate = self.smoothed_yaw_rate
                roll_rate = self.smoothed_roll_rate

            # Apply emergency stop
            if self.emergency_stop_active:
                pitch_rate = 0.0
                yaw_rate = 0.0
                roll_rate = 0.0
                thrust = self.hover_thrust

            # Set commands via schema
            self.set_command_field('pitchspeed_deg_s', pitch_rate)
            self.set_command_field('yawspeed_deg_s', yaw_rate)
            self.set_command_field('rollspeed_deg_s', roll_rate)
            self.set_command_field('thrust', thrust)

            self.total_commands_issued += 1

            # Update telemetry
            self.update_telemetry_metadata('last_target_coords', target_coords)
            self.update_telemetry_metadata('dive_started', self.dive_started)
            self.update_telemetry_metadata('last_thrust', thrust)

            logger.debug(f"Attitude rate commands - Pitch: {pitch_rate:.2f}, Yaw: {yaw_rate:.2f}, "
                        f"Roll: {roll_rate:.2f} deg/s, Thrust: {thrust:.3f}")

        except Exception as e:
            logger.error(f"Control command calculation error: {e}")
            self._set_hover_commands()

    def _set_hover_commands(self) -> None:
        """Sets hover commands (all rates zero, hover thrust)."""
        self.set_command_field('pitchspeed_deg_s', 0.0)
        self.set_command_field('yawspeed_deg_s', 0.0)
        self.set_command_field('rollspeed_deg_s', 0.0)
        self.set_command_field('thrust', self.hover_thrust)

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Executes target following with attitude rate control.

        Args:
            tracker_data: Structured tracker data.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            if self.emergency_stop_active:
                logger.debug("Emergency stop active")
                return False

            if not self.validate_tracker_compatibility(tracker_data):
                logger.error("Tracker incompatible")
                return False

            if not self._check_altitude_safety():
                logger.error("Altitude safety failed")
                return False

            self.calculate_control_commands(tracker_data)
            return True

        except Exception as e:
            logger.error(f"Follow target failed: {e}")
            return False

    # ==================== Status and Telemetry ====================

    def get_follower_status(self) -> Dict[str, Any]:
        """Returns comprehensive follower status."""
        try:
            return {
                'guidance_mode': self.guidance_mode.value,
                'dive_started': self.dive_started,
                'last_bank_angle': self.last_bank_angle,
                'last_thrust_command': self.last_thrust_command,
                'target_lost': self.target_lost,
                'target_loss_action': self.target_loss_action.value,
                'emergency_stop_active': self.emergency_stop_active,
                'altitude_violation_count': self.altitude_violation_count,
                'smoothed_los_rate': self.smoothed_los_rate,
                'total_commands_issued': self.total_commands_issued,
                'target_loss_events': self.target_loss_events,
                'initial_altitude': self.initial_altitude,
                'config': {
                    'max_rates': [self.max_pitch_rate, self.max_yaw_rate, self.max_roll_rate],
                    'hover_thrust': self.hover_thrust,
                    'altitude_hold_enabled': self.enable_altitude_hold,
                    'yaw_error_gating_enabled': self.enable_yaw_error_gating,
                }
            }
        except Exception as e:
            return {'error': str(e)}

    def get_status_report(self) -> str:
        """Generates human-readable status report."""
        try:
            status = self.get_follower_status()

            report = f"\n{'='*60}\n"
            report += f"MCAttitudeRateFollower Status Report\n"
            report += f"{'='*60}\n"
            report += f"Guidance Mode: {status.get('guidance_mode', 'unknown').upper()}\n"
            report += f"Dive Started: {'YES' if status.get('dive_started', False) else 'NO'}\n"
            report += f"Last Thrust: {status.get('last_thrust_command', 0.0):.3f}\n"
            report += f"Bank Angle: {status.get('last_bank_angle', 0.0):.1f}°\n"
            report += f"\nTarget Status:\n"
            report += f"  Lost: {'YES' if status.get('target_lost', False) else 'NO'}\n"
            report += f"  Loss Action: {status.get('target_loss_action', 'hover').upper()}\n"
            report += f"\nSafety Status:\n"
            report += f"  Emergency Stop: {'ACTIVE' if status.get('emergency_stop_active', False) else 'Inactive'}\n"
            report += f"  Altitude Violations: {status.get('altitude_violation_count', 0)}\n"
            report += f"\nStatistics:\n"
            report += f"  Commands Issued: {status.get('total_commands_issued', 0)}\n"
            report += f"  Target Loss Events: {status.get('target_loss_events', 0)}\n"
            report += f"{'='*60}\n"

            return report

        except Exception as e:
            return f"Error generating status report: {e}"

    # ==================== Control Methods ====================

    def activate_emergency_stop(self) -> None:
        """Activates emergency stop - all rates to zero, hover thrust."""
        self.emergency_stop_active = True
        self._set_hover_commands()
        logger.critical("EMERGENCY STOP ACTIVATED")

    def deactivate_emergency_stop(self) -> None:
        """Deactivates emergency stop."""
        self.emergency_stop_active = False
        self.altitude_violation_count = 0
        logger.info("Emergency stop deactivated")

    def reset_follower_state(self) -> None:
        """Resets follower state to initial conditions."""
        self.dive_started = False
        self.target_lost = False
        self.target_loss_start_time = None
        self.emergency_stop_active = False
        self.altitude_violation_count = 0
        self.smoothed_pitch_rate = 0.0
        self.smoothed_yaw_rate = 0.0
        self.smoothed_roll_rate = 0.0
        self.last_los_angle = None
        self.last_los_time = None
        self.smoothed_los_rate = 0.0

        if self.pid_pitch_rate:
            self.pid_pitch_rate.reset()
        if self.pid_yaw_rate:
            self.pid_yaw_rate.reset()
        if self.pid_roll_rate:
            self.pid_roll_rate.reset()
        if self.pid_altitude:
            self.pid_altitude.reset()

        logger.info("MCAttitudeRateFollower state reset")

    def set_guidance_mode(self, mode: str) -> bool:
        """Sets guidance mode dynamically."""
        try:
            self.guidance_mode = self._parse_guidance_mode(mode)
            self.update_telemetry_metadata('guidance_mode', self.guidance_mode.value)
            logger.info(f"Guidance mode set to: {self.guidance_mode.value}")
            return True
        except Exception as e:
            logger.error(f"Error setting guidance mode: {e}")
            return False
