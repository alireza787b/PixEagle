# src/classes/followers/fixed_wing_follower.py
"""
Fixed-Wing Follower Module
==========================

Professional fixed-wing target following with L1 navigation and TECS energy management.
This module implements government-demo-quality guidance for fixed-wing aircraft using
proven aerospace navigation methods.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- L1 Navigation: Lateral guidance using cross-track error to yaw rate conversion
- TECS (Total Energy Control System): Coordinated pitch and throttle for altitude/speed
- Coordinated Turn Dynamics: Bank angle calculation with load factor limiting
- Stall Protection: Airspeed monitoring with automatic recovery
- Altitude Safety: Envelope protection with RTL capability
- Target Loss Handling: Orbit behavior for safe loitering

CRITICAL: PX4 fixed-wing IGNORES velocity body commands in offboard mode.
This follower uses attitude_rate control (the ONLY supported method).

Control Architecture:
====================
    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
    │   L1 LATERAL │    │    TECS      │    │   COORDINATED│
    │   GUIDANCE   │    │   ENERGY     │    │   TURN CALC  │
    │              │    │   CONTROL    │    │              │
    │ cross_track  │    │ altitude_err │    │ bank = f(ω,v)│
    │ → yaw_rate   │    │ speed_err    │    │ → roll_rate  │
    │              │    │ → pitch_rate │    │              │
    │              │    │ → thrust     │    │              │
    └──────────────┘    └──────────────┘    └──────────────┘
           │                  │                   │
           ▼                  ▼                   ▼
    ┌──────────────────────────────────────────────────────┐
    │              PX4 ATTITUDE RATE COMMANDS               │
    │  rollspeed_deg_s, pitchspeed_deg_s, yawspeed_deg_s   │
    │                      thrust                           │
    └──────────────────────────────────────────────────────┘
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
import numpy as np
import math
import time
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class TargetLossAction(Enum):
    """Actions to take when target is lost."""
    ORBIT = "orbit"
    RTL = "rtl"
    CONTINUE_LAST = "continue_last"


class FWAttitudeRateFollower(BaseFollower):
    """
    Professional fixed-wing target following with L1 navigation and TECS.

    This follower implements aerospace-standard guidance laws for fixed-wing aircraft:
    - L1 Navigation for lateral guidance (cross-track error to yaw rate)
    - TECS for longitudinal control (coordinated pitch/throttle)
    - Coordinated turns with load factor limiting
    - Stall protection with automatic recovery

    Uses attitude rate commands (the ONLY offboard control type supported by PX4
    for fixed-wing aircraft).

    Key Differences from AttitudeRateFollower (quadcopter-focused):
    - L1 navigation law instead of direct PID
    - TECS energy coordination instead of independent axes
    - Airspeed-based calculations instead of ground speed
    - Stall protection (critical for fixed-wing)
    - Orbit behavior on target loss instead of hover

    Safety Features:
    - Stall speed protection with automatic recovery
    - Load factor limiting (structural protection)
    - Altitude envelope enforcement with RTL
    - Target loss handling (orbit or RTL)
    - Thrust slew rate limiting

    References:
    - Park, S., Deyst, J., & How, J. P. (2004). A New Nonlinear Guidance Logic
      for Trajectory Tracking. AIAA Guidance, Navigation, and Control Conference.
    - Lambregts, A. A. (1983). Vertical Flight Path and Speed Control Autopilot
      Design Using Total Energy Principles. AIAA Paper 83-2239.
    """

    # Class-level constants
    GRAVITY = 9.81  # m/s^2

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the FWAttitudeRateFollower with L1 navigation and TECS.

        Args:
            px4_controller: Instance of PX4Controller to control the drone.
            initial_target_coords (Tuple[float, float]): Initial target coordinates.

        Raises:
            ValueError: If initial coordinates are invalid or configuration fails.
        """
        # Initialize with fixed_wing profile for attitude rate control
        super().__init__(px4_controller, "fixed_wing")

        # Validate and store initial target coordinates
        if not self.validate_target_coordinates(initial_target_coords):
            raise ValueError(f"Invalid initial target coordinates: {initial_target_coords}")

        self.initial_target_coords = initial_target_coords

        # Get configuration section
        config = getattr(Parameters, 'FW_ATTITUDE_RATE', {})

        # === Flight Envelope ===
        self.min_airspeed = config.get('MIN_AIRSPEED', 12.0)
        self.cruise_airspeed = config.get('CRUISE_AIRSPEED', 18.0)
        self.max_airspeed = config.get('MAX_AIRSPEED', 30.0)
        self.stall_margin_buffer = config.get('STALL_MARGIN_BUFFER', 3.0)

        # === Structural Limits ===
        self.max_bank_angle = config.get('MAX_BANK_ANGLE', 35.0)
        self.max_load_factor = config.get('MAX_LOAD_FACTOR', 2.5)
        self.max_pitch_angle = config.get('MAX_PITCH_ANGLE', 25.0)
        self.min_pitch_angle = config.get('MIN_PITCH_ANGLE', -20.0)

        # === Rate Limits (deg/s) ===
        self.max_roll_rate = config.get('MAX_ROLL_RATE', 45.0)
        self.max_pitch_rate = config.get('MAX_PITCH_RATE', 20.0)
        self.max_yaw_rate = config.get('MAX_YAW_RATE', 25.0)

        # === L1 Navigation Parameters ===
        self.l1_distance = config.get('L1_DISTANCE', 50.0)
        self.l1_damping = config.get('L1_DAMPING', 0.75)
        self.enable_l1_adaptive = config.get('ENABLE_L1_ADAPTIVE', False)
        self.l1_min_distance = config.get('L1_MIN_DISTANCE', 20.0)
        self.l1_max_distance = config.get('L1_MAX_DISTANCE', 100.0)

        # === TECS Parameters ===
        self.enable_tecs = config.get('ENABLE_TECS', True)
        self.tecs_time_const = config.get('TECS_TIME_CONST', 5.0)
        self.tecs_pitch_damping = config.get('TECS_PITCH_DAMPING', 1.0)
        self.tecs_throttle_damping = config.get('TECS_THROTTLE_DAMPING', 0.5)
        self.tecs_spe_weight = config.get('TECS_SPE_WEIGHT', 1.0)

        # === Thrust Control ===
        self.min_thrust = config.get('MIN_THRUST', 0.2)
        self.max_thrust = config.get('MAX_THRUST', 1.0)
        self.cruise_thrust = config.get('CRUISE_THRUST', 0.6)
        self.thrust_slew_rate = config.get('THRUST_SLEW_RATE', 0.5)

        # === Coordinated Turn ===
        self.enable_coordinated_turn = config.get('ENABLE_COORDINATED_TURN', True)
        self.turn_coordination_gain = config.get('TURN_COORDINATION_GAIN', 1.0)
        self.slip_angle_limit = config.get('SLIP_ANGLE_LIMIT', 5.0)

        # === Altitude Safety ===
        self.altitude_safety_enabled = config.get('ENABLE_ALTITUDE_SAFETY', True)
        self.min_altitude_limit = Parameters.get_effective_limit('MIN_ALTITUDE', 'FW_ATTITUDE_RATE')
        self.max_altitude_limit = Parameters.get_effective_limit('MAX_ALTITUDE', 'FW_ATTITUDE_RATE')
        self.altitude_check_interval = config.get('ALTITUDE_CHECK_INTERVAL', 0.1)
        self.rtl_on_altitude_violation = config.get('RTL_ON_ALTITUDE_VIOLATION', True)

        # === Stall Protection ===
        self.stall_protection_enabled = config.get('ENABLE_STALL_PROTECTION', True)
        self.stall_recovery_pitch = config.get('STALL_RECOVERY_PITCH', -5.0)
        self.stall_recovery_throttle = config.get('STALL_RECOVERY_THROTTLE', 1.0)

        # === Target Loss Handling ===
        self.target_loss_timeout = config.get('TARGET_LOSS_TIMEOUT', 3.0)
        target_loss_action_str = config.get('TARGET_LOSS_ACTION', 'orbit')
        self.target_loss_action = TargetLossAction(target_loss_action_str)
        self.orbit_radius = config.get('ORBIT_RADIUS', 100.0)
        self.target_loss_coord_threshold = config.get('TARGET_LOSS_COORDINATE_THRESHOLD', 990)

        # === Performance Tuning ===
        self.control_update_rate = config.get('CONTROL_UPDATE_RATE', 20.0)
        self.enable_command_smoothing = config.get('ENABLE_COMMAND_SMOOTHING', True)
        self.smoothing_factor = config.get('SMOOTHING_FACTOR', 0.85)

        # === State Variables ===
        self._init_state_variables()

        # === Initialize PID Controllers ===
        self._initialize_pid_controllers()

        # === Initialize TECS State ===
        self._init_tecs_state()

        # Update telemetry metadata
        self.update_telemetry_metadata('controller_type', 'fixed_wing_l1_tecs')
        self.update_telemetry_metadata('guidance_law', 'L1_navigation')
        self.update_telemetry_metadata('energy_control', 'TECS')
        self.update_telemetry_metadata('safety_features', [
            'stall_protection', 'load_factor_limiting', 'altitude_safety',
            'target_loss_orbit', 'thrust_slew_limiting'
        ])

        logger.info(f"FWAttitudeRateFollower initialized with L1 navigation and TECS")
        logger.info(f"Flight envelope - Airspeed: [{self.min_airspeed}-{self.max_airspeed}] m/s, "
                   f"Bank: {self.max_bank_angle}°, Load factor: {self.max_load_factor}g")
        logger.info(f"L1 params - Distance: {self.l1_distance}m, Damping: {self.l1_damping}")
        logger.debug(f"Initial target coordinates: {initial_target_coords}")

    def _init_state_variables(self) -> None:
        """Initialize all state variables for fixed-wing following."""
        # Target tracking state
        self.target_lost = False
        self.target_loss_start_time = None
        self.last_valid_target_coords = None
        self.orbit_mode_active = False
        self.orbit_start_time = None

        # Stall protection state
        self.stall_warning_active = False
        self.stall_recovery_active = False

        # Altitude monitoring state
        self.last_altitude_check_time = 0.0
        self.altitude_violation_count = 0
        self.rtl_triggered = False

        # Command smoothing state
        self.smoothed_roll_rate = 0.0
        self.smoothed_pitch_rate = 0.0
        self.smoothed_yaw_rate = 0.0
        self.last_thrust_command = self.cruise_thrust
        self.last_command_time = time.time()

        # L1 navigation state
        self.last_cross_track_error = 0.0
        self.cross_track_rate = 0.0
        self.effective_l1_distance = self.l1_distance

        # Bank angle state
        self.target_bank_angle = 0.0
        self.current_bank_angle = 0.0

    def _init_tecs_state(self) -> None:
        """Initialize TECS energy management state variables."""
        # Energy state
        self.specific_potential_energy = 0.0  # altitude (m)
        self.specific_kinetic_energy = 0.0    # v^2 / (2*g)
        self.specific_total_energy = 0.0      # SPE + SKE

        # Energy errors
        self.spe_error = 0.0          # Altitude error (m)
        self.ske_error = 0.0          # Speed error (energy equivalent)
        self.ste_error = 0.0          # Total energy error
        self.seb_error = 0.0          # Energy balance error

        # Integrated errors for PI control
        self.ste_error_integral = 0.0
        self.seb_error_integral = 0.0

        # Target energy state
        self.target_altitude = None   # Will be set from current on first run
        self.target_airspeed = self.cruise_airspeed

    def _initialize_pid_controllers(self) -> None:
        """
        Initialize PID controllers for fixed-wing control.

        Controllers:
        - Bank Angle: Achieves target bank angle for coordinated turns
        - Roll Rate: Inner loop for roll control
        - Pitch Rate: TECS-driven pitch control
        - Yaw Rate: L1-driven lateral guidance
        """
        try:
            setpoint_x, setpoint_y = self.initial_target_coords

            # Bank Angle Controller - Outer loop for coordinated turns
            self.pid_bank_angle = CustomPID(
                *self._get_pid_gains('fw_bank_angle'),
                setpoint=0.0,  # Updated dynamically based on L1 guidance
                output_limits=(-self.max_roll_rate, self.max_roll_rate)
            )

            # Roll Rate Controller - Inner loop (feeds from bank angle error)
            self.pid_roll_rate = CustomPID(
                *self._get_pid_gains('fw_roll_rate'),
                setpoint=0.0,
                output_limits=(-self.max_roll_rate, self.max_roll_rate)
            )

            # Pitch Rate Controller - TECS-driven
            self.pid_pitch_rate = CustomPID(
                *self._get_pid_gains('fw_pitch_rate'),
                setpoint=0.0,  # Updated by TECS
                output_limits=(-self.max_pitch_rate, self.max_pitch_rate)
            )

            # Yaw Rate Controller - L1 navigation lateral guidance
            self.pid_yaw_rate = CustomPID(
                *self._get_pid_gains('fw_yaw_rate'),
                setpoint=setpoint_x,
                output_limits=(-self.max_yaw_rate, self.max_yaw_rate)
            )

            # Throttle Controller - TECS energy control
            self.pid_throttle = CustomPID(
                *self._get_pid_gains('fw_throttle'),
                setpoint=0.0,  # Updated by TECS
                output_limits=(self.min_thrust, self.max_thrust)
            )

            logger.info("All PID controllers initialized for FWAttitudeRateFollower")
            logger.debug(f"Rate limits - Roll: {self.max_roll_rate}°/s, "
                        f"Pitch: {self.max_pitch_rate}°/s, Yaw: {self.max_yaw_rate}°/s")

        except Exception as e:
            logger.error(f"Failed to initialize PID controllers: {e}")
            raise ValueError(f"PID controller initialization failed: {e}")

    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves PID gains for the specified control axis.

        Args:
            axis (str): Control axis name (fw_roll_rate, fw_pitch_rate, etc.).

        Returns:
            Tuple[float, float, float]: (P, I, D) gains.
        """
        try:
            gains = Parameters.PID_GAINS[axis]
            return gains['p'], gains['i'], gains['d']
        except KeyError:
            # Fallback to reasonable defaults if not configured
            defaults = {
                'fw_roll_rate': (0.8, 0.1, 0.05),
                'fw_pitch_rate': (0.6, 0.15, 0.03),
                'fw_yaw_rate': (0.5, 0.05, 0.02),
                'fw_throttle': (0.4, 0.2, 0.1),
                'fw_bank_angle': (2.0, 0.3, 0.2)
            }
            if axis in defaults:
                logger.warning(f"Using default PID gains for {axis}")
                return defaults[axis]
            raise KeyError(f"Invalid PID axis '{axis}'. Check Parameters.PID_GAINS configuration.")

    # ==================== L1 Navigation ====================

    def _calculate_l1_guidance(self, cross_track_error: float, airspeed: float) -> float:
        """
        Calculate lateral guidance using L1 navigation law.

        The L1 guidance law provides robust lateral tracking by computing
        a lateral acceleration command based on cross-track error and
        a lookahead distance.

        Reference: Park, S., Deyst, J., & How, J. P. (2004)

        Args:
            cross_track_error (float): Lateral error from target (normalized).
            airspeed (float): Current airspeed in m/s.

        Returns:
            float: Commanded yaw rate in deg/s.
        """
        # Adapt L1 distance to airspeed if enabled
        if self.enable_l1_adaptive:
            self.effective_l1_distance = self._adapt_l1_distance(airspeed)
        else:
            self.effective_l1_distance = self.l1_distance

        # Calculate cross-track rate (derivative for damping)
        current_time = time.time()
        dt = current_time - self.last_command_time
        if dt > 0.001:
            self.cross_track_rate = (cross_track_error - self.last_cross_track_error) / dt
        self.last_cross_track_error = cross_track_error

        # Ensure minimum airspeed for calculation stability
        safe_airspeed = max(airspeed, self.min_airspeed)

        # L1 guidance law: lateral acceleration
        # a_lat = 2 * (V^2 / L1) * sin(eta)
        # For small angles: sin(eta) ≈ cross_track_error / L1
        eta = 2 * self.l1_damping ** 2  # Damping factor

        # Simplified L1 for visual tracking (cross_track_error is normalized)
        # Scale cross_track_error to approximate lateral offset
        # In visual tracking, cross_track_error is typically [-1, 1] normalized
        lateral_scale = 50.0  # Scale factor: 1.0 normalized ≈ 50m offset

        # L1 lateral acceleration command
        a_lat_cmd = eta * (safe_airspeed ** 2 / self.effective_l1_distance) * \
                    (cross_track_error * lateral_scale / self.effective_l1_distance)

        # Add damping term
        a_lat_cmd += self.l1_damping * self.cross_track_rate * lateral_scale

        # Convert lateral acceleration to yaw rate
        # For coordinated flight: yaw_rate = a_lat / V
        yaw_rate_rad = a_lat_cmd / safe_airspeed

        # Convert to deg/s and apply limits
        yaw_rate_deg = math.degrees(yaw_rate_rad)
        yaw_rate_deg = np.clip(yaw_rate_deg, -self.max_yaw_rate, self.max_yaw_rate)

        logger.debug(f"L1 guidance - Cross-track: {cross_track_error:.3f}, "
                    f"L1: {self.effective_l1_distance:.1f}m, "
                    f"Yaw rate: {yaw_rate_deg:.2f}°/s")

        return yaw_rate_deg

    def _adapt_l1_distance(self, airspeed: float) -> float:
        """
        Adapt L1 lookahead distance based on current airspeed.

        Larger L1 at higher speeds for stability, smaller at low speeds
        for responsiveness.

        Args:
            airspeed (float): Current airspeed in m/s.

        Returns:
            float: Adapted L1 distance in meters.
        """
        # Linear interpolation between min and max L1
        speed_ratio = (airspeed - self.min_airspeed) / (self.max_airspeed - self.min_airspeed)
        speed_ratio = np.clip(speed_ratio, 0.0, 1.0)

        adapted_l1 = self.l1_min_distance + speed_ratio * (self.l1_max_distance - self.l1_min_distance)

        logger.debug(f"Adaptive L1: {adapted_l1:.1f}m at {airspeed:.1f} m/s")
        return adapted_l1

    # ==================== TECS Energy Control ====================

    def _calculate_tecs_commands(self, altitude_error: float, airspeed: float) -> Tuple[float, float]:
        """
        Calculate pitch rate and throttle commands using TECS.

        Total Energy Control System (TECS) coordinates pitch and throttle
        to manage the aircraft's energy state, providing:
        - Throttle: Controls total energy (altitude + speed)
        - Pitch: Controls energy distribution (altitude vs speed trade-off)

        Reference: Lambregts, A. A. (1983)

        Args:
            altitude_error (float): Altitude error in meters (positive = need to climb).
            airspeed (float): Current airspeed in m/s.

        Returns:
            Tuple[float, float]: (pitch_rate_deg_s, thrust_command)
        """
        if not self.enable_tecs:
            # Fallback to simple PID if TECS disabled
            return self._simple_altitude_pitch_control(altitude_error)

        # Initialize target altitude on first run
        if self.target_altitude is None:
            current_altitude = getattr(self.px4_controller, 'current_altitude', 50.0)
            self.target_altitude = current_altitude
            logger.info(f"TECS initialized with target altitude: {self.target_altitude:.1f}m")

        # Calculate specific energies
        self.specific_potential_energy = altitude_error  # Already error (target - current)
        self.specific_kinetic_energy = (self.target_airspeed ** 2 - airspeed ** 2) / (2 * self.GRAVITY)

        # Calculate energy errors
        # SPE weight determines altitude vs speed priority
        self.spe_error = self.tecs_spe_weight * self.specific_potential_energy
        self.ske_error = self.specific_kinetic_energy
        self.ste_error = self.spe_error + self.ske_error  # Total energy error
        self.seb_error = self.spe_error - self.ske_error  # Energy balance error

        # Integrate errors for PI control
        dt = 1.0 / self.control_update_rate
        self.ste_error_integral += self.ste_error * dt
        self.seb_error_integral += self.seb_error * dt

        # Anti-windup: limit integral terms
        max_integral = 50.0
        self.ste_error_integral = np.clip(self.ste_error_integral, -max_integral, max_integral)
        self.seb_error_integral = np.clip(self.seb_error_integral, -max_integral, max_integral)

        # Throttle command from total energy error
        # Throttle increases total energy
        kp_throttle = 1.0 / self.tecs_time_const
        ki_throttle = kp_throttle * self.tecs_throttle_damping

        throttle_cmd = self.cruise_thrust + \
                      kp_throttle * self.ste_error + \
                      ki_throttle * self.ste_error_integral

        # Pitch command from energy balance error
        # Pitch trades energy between altitude and speed
        kp_pitch = 1.0 / self.tecs_time_const
        kd_pitch = self.tecs_pitch_damping

        # Energy balance derivative (approximated)
        seb_rate = self.seb_error / dt if dt > 0 else 0.0

        pitch_rate_cmd = kp_pitch * self.seb_error + kd_pitch * seb_rate

        # Convert to deg/s and apply limits
        pitch_rate_deg = pitch_rate_cmd * 10.0  # Scale factor for deg/s
        pitch_rate_deg = np.clip(pitch_rate_deg, -self.max_pitch_rate, self.max_pitch_rate)

        # Apply thrust limits with slew rate limiting
        throttle_cmd = self._apply_thrust_slew_limiting(throttle_cmd)
        throttle_cmd = np.clip(throttle_cmd, self.min_thrust, self.max_thrust)

        logger.debug(f"TECS - SPE_err: {self.spe_error:.2f}, SKE_err: {self.ske_error:.2f}, "
                    f"STE_err: {self.ste_error:.2f}, SEB_err: {self.seb_error:.2f}")
        logger.debug(f"TECS output - Pitch: {pitch_rate_deg:.2f}°/s, Throttle: {throttle_cmd:.3f}")

        return pitch_rate_deg, throttle_cmd

    def _simple_altitude_pitch_control(self, altitude_error: float) -> Tuple[float, float]:
        """
        Simple pitch control as fallback when TECS is disabled.

        Args:
            altitude_error (float): Altitude error in meters.

        Returns:
            Tuple[float, float]: (pitch_rate_deg_s, thrust_command)
        """
        # Simple proportional pitch control
        pitch_rate_deg = 0.5 * altitude_error  # 0.5 deg/s per meter error
        pitch_rate_deg = np.clip(pitch_rate_deg, -self.max_pitch_rate, self.max_pitch_rate)

        return pitch_rate_deg, self.cruise_thrust

    def _apply_thrust_slew_limiting(self, target_thrust: float) -> float:
        """
        Apply thrust slew rate limiting for smooth throttle response.

        Args:
            target_thrust (float): Target thrust command.

        Returns:
            float: Rate-limited thrust command.
        """
        current_time = time.time()
        dt = current_time - self.last_command_time

        if dt > 0:
            max_change = self.thrust_slew_rate * dt
            thrust_change = target_thrust - self.last_thrust_command
            thrust_change = np.clip(thrust_change, -max_change, max_change)
            limited_thrust = self.last_thrust_command + thrust_change
        else:
            limited_thrust = target_thrust

        return limited_thrust

    # ==================== Coordinated Turn ====================

    def _calculate_coordinated_bank_angle(self, yaw_rate_deg: float, airspeed: float) -> float:
        """
        Calculate bank angle required for coordinated turn.

        Standard coordinated turn equation:
        bank_angle = arctan((yaw_rate * airspeed) / g)

        Args:
            yaw_rate_deg (float): Commanded yaw rate in deg/s.
            airspeed (float): Current airspeed in m/s.

        Returns:
            float: Required bank angle in degrees.
        """
        if not self.enable_coordinated_turn:
            return 0.0

        # Convert yaw rate to rad/s
        yaw_rate_rad = math.radians(yaw_rate_deg)

        # Ensure minimum airspeed
        safe_airspeed = max(airspeed, self.min_airspeed)

        # Standard coordinated turn equation
        bank_rad = math.atan2(yaw_rate_rad * safe_airspeed, self.GRAVITY)

        # Convert to degrees
        bank_deg = math.degrees(bank_rad)

        # Apply turn coordination gain
        bank_deg *= self.turn_coordination_gain

        # Apply load factor limiting
        bank_deg = self._limit_load_factor(bank_deg)

        # Apply structural limits
        bank_deg = np.clip(bank_deg, -self.max_bank_angle, self.max_bank_angle)

        logger.debug(f"Coordinated turn - Yaw: {yaw_rate_deg:.2f}°/s, "
                    f"Airspeed: {safe_airspeed:.1f} m/s, Bank: {bank_deg:.1f}°")

        return bank_deg

    def _limit_load_factor(self, bank_angle_deg: float) -> float:
        """
        Limit bank angle based on load factor constraints.

        Load factor n = 1 / cos(bank_angle)
        Maximum bank = arccos(1 / n_max)

        Args:
            bank_angle_deg (float): Requested bank angle in degrees.

        Returns:
            float: Load-factor-limited bank angle in degrees.
        """
        # Calculate maximum bank angle for load factor limit
        # n = 1/cos(bank) => bank = arccos(1/n)
        if self.max_load_factor > 1.0:
            max_bank_for_load = math.degrees(math.acos(1.0 / self.max_load_factor))
        else:
            max_bank_for_load = 0.0

        # Apply the more restrictive limit
        max_bank = min(max_bank_for_load, self.max_bank_angle)

        return np.clip(bank_angle_deg, -max_bank, max_bank)

    def _calculate_roll_rate(self, target_bank: float, current_bank: float) -> float:
        """
        Calculate roll rate to achieve target bank angle.

        Args:
            target_bank (float): Target bank angle in degrees.
            current_bank (float): Current bank angle in degrees.

        Returns:
            float: Roll rate command in deg/s.
        """
        bank_error = target_bank - current_bank
        roll_rate = self.pid_bank_angle(bank_error)

        return np.clip(roll_rate, -self.max_roll_rate, self.max_roll_rate)

    # ==================== Safety Systems ====================

    def _check_stall_protection(self) -> bool:
        """
        Check airspeed and apply stall protection if necessary.

        Returns:
            bool: True if airspeed is safe, False if stall protection active.
        """
        if not self.stall_protection_enabled:
            return True

        current_airspeed = self._get_current_airspeed()
        stall_warning_speed = self.min_airspeed + self.stall_margin_buffer

        if current_airspeed < stall_warning_speed:
            if not self.stall_warning_active:
                logger.warning(f"STALL WARNING: Airspeed {current_airspeed:.1f} m/s < "
                             f"{stall_warning_speed:.1f} m/s")
                self.stall_warning_active = True

            if current_airspeed < self.min_airspeed:
                logger.critical(f"STALL PROTECTION ACTIVE: Airspeed {current_airspeed:.1f} m/s")
                self._apply_stall_recovery()
                return False
        else:
            if self.stall_warning_active:
                logger.info("Stall warning cleared - airspeed recovered")
            self.stall_warning_active = False
            self.stall_recovery_active = False

        return True

    def _apply_stall_recovery(self) -> None:
        """
        Apply stall recovery: nose down, full throttle.
        """
        self.stall_recovery_active = True

        # Command nose down to regain airspeed
        self.set_command_field('pitchspeed_deg_s', self.stall_recovery_pitch)

        # Full throttle for energy recovery
        self.set_command_field('thrust', self.stall_recovery_throttle)

        # Level wings during recovery
        self.set_command_field('rollspeed_deg_s', 0.0)

        # Maintain current yaw
        self.set_command_field('yawspeed_deg_s', 0.0)

        self.log_follower_event('stall_recovery',
                               airspeed=self._get_current_airspeed(),
                               pitch_cmd=self.stall_recovery_pitch,
                               thrust_cmd=self.stall_recovery_throttle)

    def _check_altitude_safety(self) -> bool:
        """
        Check altitude bounds and trigger RTL if necessary.

        Returns:
            bool: True if altitude is safe, False if RTL triggered.
        """
        if not self.altitude_safety_enabled:
            return True

        current_time = time.time()
        if current_time - self.last_altitude_check_time < self.altitude_check_interval:
            return True
        self.last_altitude_check_time = current_time

        current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)

        if current_altitude < self.min_altitude_limit or current_altitude > self.max_altitude_limit:
            self.altitude_violation_count += 1
            logger.critical(f"ALTITUDE VIOLATION: {current_altitude:.1f}m "
                          f"(limits: [{self.min_altitude_limit}-{self.max_altitude_limit}]m)")

            if self.rtl_on_altitude_violation and not self.rtl_triggered:
                self._trigger_rtl("altitude_violation")
                return False

        return True

    def _trigger_rtl(self, reason: str) -> None:
        """
        Trigger Return to Launch mode.

        Args:
            reason (str): Reason for RTL trigger.
        """
        if self.rtl_triggered:
            return

        self.rtl_triggered = True
        logger.critical(f"TRIGGERING RTL - Reason: {reason}")

        try:
            if self.px4_controller and hasattr(self.px4_controller, 'trigger_return_to_launch'):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.create_task(self.px4_controller.trigger_return_to_launch())
                except RuntimeError:
                    asyncio.run(self.px4_controller.trigger_return_to_launch())
                logger.critical("RTL command issued successfully")
        except Exception as e:
            logger.error(f"Failed to trigger RTL: {e}")

        self.log_follower_event('rtl_triggered', reason=reason)

    # ==================== Target Loss Handling ====================

    def _handle_target_loss(self, target_coords: Tuple[float, float]) -> bool:
        """
        Handle target loss detection and execute appropriate action.

        Args:
            target_coords (Tuple[float, float]): Current target coordinates.

        Returns:
            bool: True if target is valid, False if lost.
        """
        current_time = time.time()

        # Check if target is valid
        threshold = self.target_loss_coord_threshold
        is_valid = (
            self.validate_target_coordinates(target_coords) and
            not (np.isnan(target_coords[0]) or np.isnan(target_coords[1])) and
            not (abs(target_coords[0]) > threshold or abs(target_coords[1]) > threshold)
        )

        if is_valid:
            if self.target_lost:
                logger.info("Target reacquired after loss")
                self.orbit_mode_active = False
            self.target_lost = False
            self.target_loss_start_time = None
            self.last_valid_target_coords = target_coords
            return True

        # Target is lost
        if not self.target_lost:
            self.target_lost = True
            self.target_loss_start_time = current_time
            logger.warning(f"Target lost at coordinates: {target_coords}")

        loss_duration = current_time - self.target_loss_start_time

        if loss_duration > self.target_loss_timeout:
            logger.warning(f"Target loss timeout ({loss_duration:.1f}s) - executing {self.target_loss_action.value}")
            self._execute_target_loss_action()

        return False

    def _execute_target_loss_action(self) -> None:
        """Execute the configured target loss action."""
        if self.target_loss_action == TargetLossAction.ORBIT:
            self._execute_orbit()
        elif self.target_loss_action == TargetLossAction.RTL:
            self._trigger_rtl("target_loss_timeout")
        elif self.target_loss_action == TargetLossAction.CONTINUE_LAST:
            # Continue with last valid target (do nothing special)
            logger.info("Continuing with last valid target position")

    def _execute_orbit(self) -> None:
        """
        Execute orbit/loiter behavior on target loss.

        Commands a constant-rate turn to maintain position.
        """
        if not self.orbit_mode_active:
            self.orbit_mode_active = True
            self.orbit_start_time = time.time()
            logger.info(f"Entering orbit mode with radius {self.orbit_radius}m")

        # Calculate orbit turn rate
        airspeed = self._get_current_airspeed()
        safe_airspeed = max(airspeed, self.min_airspeed)

        # Turn rate for given radius: omega = V / R
        orbit_yaw_rate = math.degrees(safe_airspeed / self.orbit_radius)
        orbit_yaw_rate = min(orbit_yaw_rate, self.max_yaw_rate)

        # Calculate coordinated bank for orbit
        orbit_bank = self._calculate_coordinated_bank_angle(orbit_yaw_rate, safe_airspeed)
        roll_rate = self._calculate_roll_rate(orbit_bank, self._get_current_roll())

        # Set orbit commands
        self.set_command_field('yawspeed_deg_s', orbit_yaw_rate)
        self.set_command_field('rollspeed_deg_s', roll_rate)
        self.set_command_field('pitchspeed_deg_s', 0.0)  # Maintain altitude
        self.set_command_field('thrust', self.cruise_thrust)

        self.log_follower_event('orbit_mode',
                               yaw_rate=orbit_yaw_rate,
                               bank_angle=orbit_bank,
                               duration=time.time() - self.orbit_start_time)

    # ==================== Helper Methods ====================

    def _get_current_airspeed(self) -> float:
        """Get current airspeed from PX4 controller."""
        return getattr(self.px4_controller, 'current_airspeed',
                      getattr(self.px4_controller, 'current_ground_speed', self.cruise_airspeed))

    def _get_current_altitude(self) -> float:
        """Get current altitude from PX4 controller."""
        return getattr(self.px4_controller, 'current_altitude', 50.0)

    def _get_current_roll(self) -> float:
        """Get current roll angle from PX4 controller."""
        return getattr(self.px4_controller, 'current_roll', 0.0)

    def _get_current_pitch(self) -> float:
        """Get current pitch angle from PX4 controller."""
        return getattr(self.px4_controller, 'current_pitch', 0.0)

    def _apply_command_smoothing(self, roll_rate: float, pitch_rate: float,
                                 yaw_rate: float) -> Tuple[float, float, float]:
        """
        Apply exponential moving average smoothing to rate commands.

        Args:
            roll_rate, pitch_rate, yaw_rate: Raw rate commands.

        Returns:
            Tuple of smoothed (roll, pitch, yaw) rates.
        """
        if not self.enable_command_smoothing:
            return roll_rate, pitch_rate, yaw_rate

        alpha = self.smoothing_factor
        self.smoothed_roll_rate = alpha * self.smoothed_roll_rate + (1 - alpha) * roll_rate
        self.smoothed_pitch_rate = alpha * self.smoothed_pitch_rate + (1 - alpha) * pitch_rate
        self.smoothed_yaw_rate = alpha * self.smoothed_yaw_rate + (1 - alpha) * yaw_rate

        return self.smoothed_roll_rate, self.smoothed_pitch_rate, self.smoothed_yaw_rate

    # ==================== Core Control Methods ====================

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculate control commands using L1 navigation and TECS.

        This method implements the core fixed-wing following logic:
        1. Extract target coordinates from tracker data
        2. Calculate L1 lateral guidance (yaw rate)
        3. Calculate coordinated turn dynamics (bank angle, roll rate)
        4. Calculate TECS longitudinal control (pitch rate, throttle)
        5. Apply safety checks and command smoothing
        6. Update setpoint handler

        Args:
            tracker_data (TrackerOutput): Structured tracker data.
        """
        # Extract target coordinates
        target_coords = self.extract_target_coordinates(tracker_data)
        if not target_coords:
            logger.warning("No valid target coordinates, skipping control update")
            return

        # Get current flight state
        airspeed = self._get_current_airspeed()
        altitude = self._get_current_altitude()
        current_roll = self._get_current_roll()

        # === L1 Lateral Guidance ===
        # Cross-track error from target x coordinate (normalized)
        cross_track_error = target_coords[0]  # Positive = target right of center
        yaw_rate = self._calculate_l1_guidance(cross_track_error, airspeed)

        # === Coordinated Turn ===
        target_bank = self._calculate_coordinated_bank_angle(yaw_rate, airspeed)
        roll_rate = self._calculate_roll_rate(target_bank, current_roll)

        # === TECS Longitudinal Control ===
        # Altitude error from target y coordinate (normalized to altitude)
        # In visual tracking, y > 0 means target is above center (need to climb)
        altitude_scale = 20.0  # Scale: 1.0 normalized ≈ 20m altitude adjustment
        altitude_error = target_coords[1] * altitude_scale  # Positive = need to climb

        pitch_rate, thrust = self._calculate_tecs_commands(altitude_error, airspeed)

        # === Apply Command Smoothing ===
        roll_rate, pitch_rate, yaw_rate = self._apply_command_smoothing(
            roll_rate, pitch_rate, yaw_rate
        )

        # === Update Commands ===
        self.set_command_field('rollspeed_deg_s', roll_rate)
        self.set_command_field('pitchspeed_deg_s', pitch_rate)
        self.set_command_field('yawspeed_deg_s', yaw_rate)
        self.set_command_field('thrust', thrust)

        # Store state for telemetry
        self.target_bank_angle = target_bank
        self.last_thrust_command = thrust
        self.last_command_time = time.time()

        logger.debug(f"FW control - Roll: {roll_rate:.2f}°/s, Pitch: {pitch_rate:.2f}°/s, "
                    f"Yaw: {yaw_rate:.2f}°/s, Thrust: {thrust:.3f}")

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Execute fixed-wing target following with L1 navigation and TECS.

        Main entry point for fixed-wing following behavior. Performs:
        1. Tracker compatibility validation
        2. Target loss detection
        3. Safety checks (stall, altitude)
        4. Control command calculation

        Args:
            tracker_data (TrackerOutput): Structured tracker data.

        Returns:
            bool: True if following executed successfully, False otherwise.
        """
        try:
            # Validate tracker compatibility
            if not self.validate_tracker_compatibility(tracker_data):
                logger.error("Tracker data incompatible with FWAttitudeRateFollower")
                return False

            # Extract target coordinates
            target_coords = self.extract_target_coordinates(tracker_data)
            if not target_coords:
                logger.warning("No valid target coordinates in tracker data")
                return False

            # Handle target loss
            if not self._handle_target_loss(target_coords):
                # Target lost - orbit or other action already being executed
                return False

            # Check stall protection
            if not self._check_stall_protection():
                # Stall recovery active - skip normal control
                return False

            # Check altitude safety
            if not self._check_altitude_safety():
                # RTL triggered - skip normal control
                return False

            # Calculate and apply control commands
            self.calculate_control_commands(tracker_data)

            # Update telemetry
            self.update_telemetry_metadata('last_target_coords', target_coords)
            self.update_telemetry_metadata('orbit_mode_active', self.orbit_mode_active)
            self.update_telemetry_metadata('stall_warning', self.stall_warning_active)
            self.update_telemetry_metadata('target_lost', self.target_lost)

            logger.debug(f"Fixed-wing following executed for target: {target_coords}")
            return True

        except Exception as e:
            logger.error(f"Fixed-wing following failed: {e}")
            return False

    # ==================== Telemetry and Status ====================

    def get_fixed_wing_status(self) -> Dict[str, Any]:
        """
        Returns comprehensive fixed-wing follower status.

        Returns:
            Dict[str, Any]: Detailed status information.
        """
        try:
            return {
                # Flight State
                'current_airspeed': self._get_current_airspeed(),
                'current_altitude': self._get_current_altitude(),
                'current_roll': self._get_current_roll(),
                'current_pitch': self._get_current_pitch(),

                # L1 Navigation State
                'l1_distance': self.effective_l1_distance,
                'cross_track_error': self.last_cross_track_error,
                'cross_track_rate': self.cross_track_rate,

                # TECS State
                'spe_error': self.spe_error,
                'ske_error': self.ske_error,
                'ste_error': self.ste_error,
                'seb_error': self.seb_error,
                'target_altitude': self.target_altitude,
                'target_airspeed': self.target_airspeed,

                # Turn State
                'target_bank_angle': self.target_bank_angle,
                'last_thrust_command': self.last_thrust_command,

                # Safety State
                'stall_warning_active': self.stall_warning_active,
                'stall_recovery_active': self.stall_recovery_active,
                'altitude_violation_count': self.altitude_violation_count,
                'rtl_triggered': self.rtl_triggered,

                # Target State
                'target_lost': self.target_lost,
                'orbit_mode_active': self.orbit_mode_active,
                'target_loss_duration': (time.time() - self.target_loss_start_time)
                                        if self.target_loss_start_time else 0.0,

                # Configuration
                'configuration': {
                    'min_airspeed': self.min_airspeed,
                    'max_airspeed': self.max_airspeed,
                    'max_bank_angle': self.max_bank_angle,
                    'max_load_factor': self.max_load_factor,
                    'l1_distance': self.l1_distance,
                    'l1_damping': self.l1_damping,
                    'tecs_enabled': self.enable_tecs,
                    'stall_protection': self.stall_protection_enabled,
                }
            }
        except Exception as e:
            logger.error(f"Error generating fixed-wing status: {e}")
            return {'error': str(e)}

    def get_status_report(self) -> str:
        """
        Generate human-readable status report.

        Returns:
            str: Formatted status report.
        """
        try:
            status = self.get_fixed_wing_status()

            report = f"\n{'='*60}\n"
            report += "Fixed-Wing Follower Status Report\n"
            report += f"{'='*60}\n"

            report += f"\nFlight State:\n"
            report += f"  Airspeed: {status.get('current_airspeed', 0):.1f} m/s\n"
            report += f"  Altitude: {status.get('current_altitude', 0):.1f} m\n"
            report += f"  Roll: {status.get('current_roll', 0):.1f}°\n"
            report += f"  Pitch: {status.get('current_pitch', 0):.1f}°\n"

            report += f"\nL1 Navigation:\n"
            report += f"  L1 Distance: {status.get('l1_distance', 0):.1f} m\n"
            report += f"  Cross-track Error: {status.get('cross_track_error', 0):.3f}\n"

            report += f"\nTECS Energy:\n"
            report += f"  SPE Error: {status.get('spe_error', 0):.2f}\n"
            report += f"  SKE Error: {status.get('ske_error', 0):.2f}\n"
            report += f"  STE Error: {status.get('ste_error', 0):.2f}\n"

            report += f"\nSafety Status:\n"
            report += f"  Stall Warning: {'ACTIVE' if status.get('stall_warning_active') else 'Clear'}\n"
            report += f"  Stall Recovery: {'ACTIVE' if status.get('stall_recovery_active') else 'Inactive'}\n"
            report += f"  RTL Triggered: {'YES' if status.get('rtl_triggered') else 'No'}\n"

            report += f"\nTarget Status:\n"
            report += f"  Target Lost: {'YES' if status.get('target_lost') else 'No'}\n"
            report += f"  Orbit Mode: {'ACTIVE' if status.get('orbit_mode_active') else 'Inactive'}\n"

            report += f"{'='*60}\n"
            return report

        except Exception as e:
            return f"Error generating status report: {e}"

    def reset_state(self) -> None:
        """Reset all state variables to initial conditions."""
        try:
            self._init_state_variables()
            self._init_tecs_state()

            # Reset PID controllers
            self.pid_bank_angle.reset()
            self.pid_roll_rate.reset()
            self.pid_pitch_rate.reset()
            self.pid_yaw_rate.reset()
            self.pid_throttle.reset()

            self.update_telemetry_metadata('state_reset', datetime.utcnow().isoformat())
            logger.info("FWAttitudeRateFollower state reset to initial conditions")

        except Exception as e:
            logger.error(f"Error resetting state: {e}")
