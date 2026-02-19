# src/classes/followers/mc_velocity_chase_follower.py
"""
MC Velocity Chase Follower Module - Fixed Camera Body Velocity Tracking
=========================================================================

This module implements the MCVelocityChaseFollower class for quadcopter target following
using offboard body velocity control with a FIXED CAMERA (no gimbal).

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- Body velocity offboard control (forward, right, down, yaw speed)
- Supports both lateral guidance modes:
  - coordinated_turn (recommended for fixed camera)
  - sideslip (advanced mode; may lose target in fixed-camera setups)
- Forward velocity ramping with configurable acceleration
- PID-controlled vertical tracking
- Enterprise-grade YawRateSmoother (deadzone, rate limiting, EMA)
- Altitude safety monitoring with RTL capability
- Target loss handling with automatic ramp-down
- Emergency stop functionality
- Comprehensive telemetry and status reporting

FIXED CAMERA ADVISORY:
=================================
With a fixed camera (no gimbal), the drone MUST yaw to keep the target centered.
Sideslip mode (lateral velocity without yaw) can cause target drift and loss.
PixEagle now allows sideslip when explicitly selected, but coordinated_turn
remains the default and recommended mode for fixed-camera tracking.

Unit Conventions:
=================
- Target coordinates: Normalized [-1, 1], center at (0, 0)
- Target loss threshold: Normalized (default 1.5 = edge of frame)
- PID input: Normalized error [-1, 1]
- PID output (yaw): rad/s (internal), converted to deg/s for MAVSDK
- Velocity commands: m/s (body frame)
- Yaw rate command: deg/s (MAVSDK convention)

Control Flow (v5.7.0):
======================
1. 2D Target Coords (x, y) ∈ [-1, 1] from tracker
2. error_x = 0 - target_x (horizontal), error_y = 0 - target_y (vertical)
3. PID controllers compute raw commands
4. YawRateSmoother applies deadzone, rate limiting, EMA, speed scaling
5. Commands sent to MAVSDK:
   - coordinated_turn: vel_body_fwd, vel_body_right=0, vel_body_down, yawspeed_deg_s
   - sideslip: vel_body_fwd, vel_body_right, vel_body_down, yawspeed_deg_s=0

v5.7.0+ Enterprise Hardening:
============================
- Fixed TARGET_LOSS_COORDINATE_THRESHOLD (was 990, now 1.5 normalized)
- Added explicit fixed-camera advisory for sideslip mode
- Added YawRateSmoother for smooth yaw commands
- Made VIDEO_HEIGHT_PIXELS configurable (was hardcoded 480)
- Made FORWARD_VELOCITY_DEADZONE configurable (was hardcoded 0.01)

Configuration:
=============
- LATERAL_GUIDANCE_MODE: coordinated_turn (recommended) or sideslip (advanced)
- TARGET_LOSS_COORDINATE_THRESHOLD: Normalized coords (default 1.5)
- YAW_SMOOTHING: Nested config for enterprise-grade yaw smoothing
- VIDEO_HEIGHT_PIXELS: Camera resolution for rate calculations
- FORWARD_VELOCITY_DEADZONE: Velocity ramping deadzone
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.followers.yaw_rate_smoother import YawRateSmoother  # WP9: canonical import
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
import numpy as np
import time
import asyncio
from math import degrees
from typing import Tuple, Optional, Dict, Any, List, Deque
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)

class MCVelocityChaseFollower(BaseFollower):
    """
    Body velocity chase follower for FIXED CAMERA target tracking (v5.7.1).

    This follower uses offboard body velocity commands (forward, right, down, yaw speed)
    for target tracking with 2D bounding box coordinates from a body-fixed camera.

    FIXED CAMERA ADVISORY:
    =================================
    Since the camera is body-fixed (no gimbal), the drone MUST yaw to keep the target
    centered in frame. Sideslip mode (lateral velocity without yaw) is incompatible
    in many scenarios because the target may drift out of frame.
    This follower allows sideslip when explicitly configured, but coordinated_turn
    remains the recommended default.

    Control Strategy:
    ================
    - **Forward Velocity**: Ramped acceleration from 0 to max velocity
    - **Yaw Control**: PID-controlled yaw rate in coordinated_turn mode
    - **Vertical Control**: PID-controlled down velocity for altitude/vertical tracking
    - **Lateral Velocity**: PID-controlled in sideslip mode

    Features (v5.7.1):
    ==================
    - Forward velocity ramping with configurable acceleration rate
    - YawRateSmoother integration (deadzone, rate limiting, EMA, speed scaling)
    - PID-controlled yaw and vertical tracking
    - Target loss detection with normalized coordinate threshold (default 1.5)
    - Altitude safety monitoring with RTL capability
    - Emergency stop functionality for critical situations
    - Velocity smoothing for stable control commands
    - Comprehensive telemetry and status reporting

    Safety Features:
    ===============
    - Altitude bounds checking with automatic RTL
    - Target loss handling with configurable timeout
    - Emergency velocity zeroing capability
    - Velocity command smoothing and limiting
    - Comprehensive error handling and recovery
    """
    
    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the MCVelocityChaseFollower with schema-aware dual-mode offboard control.

        Args:
            px4_controller: Instance of PX4Controller to control the drone.
            initial_target_coords (Tuple[float, float]): Initial target coordinates for setpoint initialization.
            
        Raises:
            ValueError: If initial coordinates are invalid or schema initialization fails.
            RuntimeError: If PID controller initialization fails.
        """
        # Initialize with mc_velocity_chase profile for offboard control
        super().__init__(px4_controller, "mc_velocity_chase")
        
        # Validate and store initial target coordinates
        if not self.validate_target_coordinates(initial_target_coords):
            raise ValueError(f"Invalid initial target coordinates: {initial_target_coords}")
        
        self.initial_target_coords = initial_target_coords

        # Get configuration section
        config = getattr(Parameters, 'MC_VELOCITY_CHASE', {})

        # Load body velocity chase specific parameters from config
        self.initial_forward_velocity = config.get('INITIAL_FORWARD_VELOCITY', 0.0)
        # v5.0.0: Use SafetyManager for velocity limits (single source of truth)
        self.max_forward_velocity = self.velocity_limits.forward
        self.forward_ramp_rate = config.get('FORWARD_RAMP_RATE', 0.5)
        self.ramp_down_on_target_loss = config.get('RAMP_DOWN_ON_TARGET_LOSS', True)
        self.target_loss_timeout = config.get('TARGET_LOSS_TIMEOUT', 2.0)
        self.enable_altitude_control = config.get('ENABLE_ALTITUDE_CONTROL', False)
        self.lateral_guidance_mode = config.get('LATERAL_GUIDANCE_MODE', 'coordinated_turn')
        self.guidance_mode_switch_velocity = config.get('GUIDANCE_MODE_SWITCH_VELOCITY', 3.0)
        self.enable_auto_mode_switching = config.get('ENABLE_AUTO_MODE_SWITCHING', False)
        self.mode_switch_hysteresis = config.get('MODE_SWITCH_HYSTERESIS', 0.5)
        self.min_mode_switch_interval = config.get('MIN_MODE_SWITCH_INTERVAL', 2.0)
        self.last_mode_switch_time = 0.0
        # v5.x: altitude_safety_enabled, rtl_on_altitude_violation, emergency_stop_enabled
        # are now delegated to SafetyManager (via base class). Use:
        #   self.is_altitude_safety_enabled()
        #   self.safety_manager.get_safety_behavior(self._follower_config_name).rtl_on_violation
        #   self.safety_manager.get_safety_behavior(self._follower_config_name).emergency_stop_enabled
        # Use base class cached altitude limits (via SafetyManager)
        self.min_altitude_limit = self.altitude_limits.min_altitude
        self.max_altitude_limit = self.altitude_limits.max_altitude
        self.altitude_check_interval = config.get('ALTITUDE_CHECK_INTERVAL', 0.1)  # 100ms for safety
        self.altitude_warning_buffer = self.altitude_limits.warning_buffer
        self.max_tracking_error = config.get('MAX_TRACKING_ERROR', 1.5)
        self.velocity_smoothing_enabled = config.get('COMMAND_SMOOTHING_ENABLED', True)
        self.smoothing_factor = config.get('SMOOTHING_FACTOR', 0.8)
        self.min_forward_velocity_threshold = config.get('MIN_FORWARD_VELOCITY_THRESHOLD', 0.2)
        # Target loss stop velocity: velocity to ramp to when target is lost (0.0 = full stop)
        self.target_loss_stop_velocity = config.get('TARGET_LOSS_STOP_VELOCITY', 0.0)
        # Coordinate threshold for detecting lost target (abs value > this = lost)
        # v5.7.1: Fallback 1.5 matches normalized coords [-1,1] - target at edge = near loss
        self.target_loss_coord_threshold = config.get('TARGET_LOSS_COORDINATE_THRESHOLD', 1.5)
        self.ramp_update_rate = config.get('RAMP_UPDATE_RATE', 10.0)
        self.pid_update_rate = config.get('PID_UPDATE_RATE', 20.0)

        # Max yaw rate in radians for PID limit (from base class cached limits)
        self.max_yaw_rate_rad = self.rate_limits.yaw  # Already in rad/s from SafetyManager

        # Load adaptive dive/climb parameters
        self.adaptive_mode_enabled = config.get('ENABLE_ADAPTIVE_DIVE_CLIMB', False)
        self.adaptive_smoothing_alpha = config.get('ADAPTIVE_SMOOTHING_ALPHA', 0.2)
        self.adaptive_warmup_frames = config.get('ADAPTIVE_WARMUP_FRAMES', 10)
        self.adaptive_rate_threshold = config.get('ADAPTIVE_RATE_THRESHOLD', 5.0)
        self.adaptive_max_correction = config.get('ADAPTIVE_MAX_CORRECTION', 1.0)
        self.adaptive_correction_gain = config.get('ADAPTIVE_CORRECTION_GAIN', 0.3)
        self.adaptive_min_confidence = config.get('ADAPTIVE_MIN_CONFIDENCE', 0.6)
        self.adaptive_fwd_coupling_enabled = config.get('ADAPTIVE_FWD_COUPLING_ENABLED', False)
        self.adaptive_fwd_coupling_gain = config.get('ADAPTIVE_FWD_COUPLING_GAIN', 0.1)
        self.pixel_to_rate_calibration = config.get('PIXEL_TO_RATE_CALIBRATION', 0.05)
        self.adaptive_oscillation_detection = config.get('ADAPTIVE_OSCILLATION_DETECTION', True)
        self.adaptive_max_sign_changes = config.get('ADAPTIVE_MAX_SIGN_CHANGES', 3)
        self.adaptive_divergence_timeout = config.get('ADAPTIVE_DIVERGENCE_TIMEOUT', 5.0)

        # === v5.7.0: Configurable parameters (removed hardcodes) ===
        # Video resolution for adaptive rate calculations (was hardcoded 480)
        self.video_height_pixels = config.get('VIDEO_HEIGHT_PIXELS', 480.0)
        # Velocity deadzone for ramping logic (was hardcoded 0.01 m/s)
        self.forward_velocity_deadzone = config.get('FORWARD_VELOCITY_DEADZONE', 0.01)
        # v5.7.1: Target validation thresholds (were hardcoded)
        self.target_confidence_threshold = config.get('TARGET_CONFIDENCE_THRESHOLD', 0.5)
        self.max_reasonable_target_velocity = config.get('MAX_REASONABLE_TARGET_VELOCITY', 50.0)

        # === v5.7.0: YawRateSmoother configuration ===
        yaw_smoothing_config = config.get('YAW_SMOOTHING', {})
        self.yaw_smoother = YawRateSmoother.from_config(yaw_smoothing_config)
        logger.debug(f"YawRateSmoother initialized: enabled={self.yaw_smoother.enabled}, "
                    f"deadzone={self.yaw_smoother.deadzone_deg_s}°/s")

        # Initialize forward velocity ramping state
        self.current_forward_velocity = self.initial_forward_velocity
        self.target_forward_velocity = self.max_forward_velocity
        self.last_ramp_update_time = time.time()
        
        # Initialize target tracking state
        self.target_lost = False
        self.target_loss_start_time = None
        self.last_valid_target_coords = initial_target_coords
        
        # Initialize safety monitoring state
        self.emergency_stop_active = False
        self.last_altitude_check_time = time.time()
        self.altitude_violation_count = 0
        
        # Initialize velocity smoothing for all axes
        self.smoothed_right_velocity = 0.0
        self.smoothed_down_velocity = 0.0
        self.smoothed_yaw_speed = 0.0
        
        # Initialize lateral guidance mode tracking
        self.active_lateral_mode = None  # Will be set by PID initialization
        self._sideslip_advisory_logged = False

        # Initialize adaptive dive/climb control state
        self.adaptive_active = False  # Whether adaptive mode is currently active
        self.target_vertical_history: Deque[Tuple[float, float]] = deque(maxlen=30)  # (timestamp, y_coord) history
        self.smoothed_vertical_rate = 0.0  # Filtered vertical rate (pixels/sec)
        self.expected_vertical_rate = 0.0  # Expected rate based on commanded velocities
        self.vertical_rate_error = 0.0  # Difference between observed and expected
        self.adaptive_warmup_counter = 0  # Frame counter for warmup period
        self.last_target_y_coord = None  # Last valid Y coordinate
        self.last_target_timestamp = None  # Last valid timestamp
        self.adaptive_correction_down = 0.0  # Current down velocity correction
        self.adaptive_correction_fwd = 0.0  # Current forward velocity correction

        # Oscillation detection state
        self.rate_error_sign_history: Deque[Tuple[float, int]] = deque(maxlen=50)  # (timestamp, sign) history
        self.adaptive_disabled_reason = None  # Reason if adaptive mode was disabled
        self.adaptive_divergence_start_time = None  # When divergence was first detected

        # === PITCH COMPENSATION CONFIGURATION ===
        # Load pitch compensation parameters from config
        self.pitch_compensation_enabled = config.get('ENABLE_PITCH_COMPENSATION', False)
        self.pitch_compensation_model = config.get('PITCH_COMPENSATION_MODEL', 'linear_velocity')
        self.pitch_compensation_gain = config.get('PITCH_COMPENSATION_GAIN', 0.05)
        self.pitch_smoothing_alpha = config.get('PITCH_DATA_SMOOTHING_ALPHA', 0.7)
        self.pitch_data_max_age = config.get('PITCH_DATA_MAX_AGE', 0.5)
        self.pitch_min_velocity = config.get('PITCH_COMPENSATION_MIN_VELOCITY', 1.0)
        self.pitch_deadband = config.get('PITCH_COMPENSATION_DEADBAND', 2.0)
        self.pitch_max_angle = config.get('PITCH_COMPENSATION_MAX_ANGLE', 45.0)
        self.pitch_max_correction = config.get('PITCH_COMPENSATION_MAX_CORRECTION', 0.3)
        self.pitch_adaptive_gain = config.get('PITCH_COMPENSATION_ADAPTIVE_GAIN', False)

        # Initialize pitch compensation runtime state
        self.current_pitch_angle = 0.0  # Current pitch angle in degrees
        self.smoothed_pitch_angle = 0.0  # Filtered pitch angle with EMA
        self.last_pitch_timestamp = None  # Timestamp of last pitch data
        self.pitch_compensation_active = False  # Whether compensation is currently applied
        self.pitch_compensation_value = 0.0  # Current compensation value (normalized coordinates)
        self.pitch_data_valid = False  # Whether pitch data is fresh and valid
        self.pitch_compensation_history: Deque[Tuple[float, float]] = deque(maxlen=20)  # (timestamp, compensation) history

        # Initialize PID controllers (includes mode determination)
        self._initialize_pid_controllers()
        
        # Update telemetry metadata
        self.update_telemetry_metadata('controller_type', 'velocity_body_offboard')
        self.update_telemetry_metadata('control_strategy', 'mc_velocity_chase_fixed_camera')
        self.update_telemetry_metadata('lateral_guidance_mode', self.lateral_guidance_mode)
        self.update_telemetry_metadata('active_lateral_mode', self.active_lateral_mode)
        self.update_telemetry_metadata(
            'lateral_mode_advisory',
            'Fixed camera: coordinated_turn recommended; sideslip may lose target.'
        )
        self.update_telemetry_metadata('safety_features', [
            'altitude_monitoring', 'target_loss_handling', 'velocity_ramping', 'emergency_stop',
            'yaw_rate_smoothing',  # v5.7.0: YawRateSmoother integration
            'adaptive_dive_climb' if self.adaptive_mode_enabled else None,
            'pitch_compensation' if self.pitch_compensation_enabled else None
        ])
        self.update_telemetry_metadata('forward_ramping_enabled', True)
        self.update_telemetry_metadata('altitude_safety_enabled', self.is_altitude_safety_enabled())
        self.update_telemetry_metadata('adaptive_dive_climb_enabled', self.adaptive_mode_enabled)
        self.update_telemetry_metadata('pitch_compensation_enabled', self.pitch_compensation_enabled)
        
        logger.info(f"MCVelocityChaseFollower initialized with dual-mode offboard velocity control")
        logger.info(f"Active lateral guidance mode: {self.active_lateral_mode}")
        logger.debug(f"Initial target coordinates: {initial_target_coords}")
        logger.debug(f"Max forward velocity: {self.target_forward_velocity:.1f} m/s")

    def _initialize_pid_controllers(self) -> None:
        """
        Initializes PID controllers for lateral and vertical tracking with dual-mode support.
        
        Creates PID controllers based on configured guidance mode:
        - Sideslip Mode: Right Velocity PID for direct lateral control
        - Coordinated Turn Mode: Yaw Speed PID for turn-to-track control
        - Always: Down Velocity PID for vertical tracking (if enabled)
        
        Note: Forward velocity is controlled by ramping logic, not PID.
        
        Raises:
            RuntimeError: If PID initialization fails.
        """
        try:
            # Use center (0.0, 0.0) as setpoints for proper center-tracking behavior
            # This ensures target is tracked to the center of the frame
            # regardless of where initial_target_coords was set
            setpoint_x, setpoint_y = 0.0, 0.0

            # Initialize lateral guidance PIDs based on mode
            self.pid_right = None
            self.pid_yaw_speed = None
            
            # Determine active lateral guidance mode
            self.active_lateral_mode = self._get_active_lateral_mode()
            
            if self.active_lateral_mode == 'sideslip':
                # Sideslip Mode: Direct lateral velocity control (use base class cached limits)
                self.pid_right = CustomPID(
                    *self._get_pid_gains('mc_vel_body_right'),
                    setpoint=setpoint_x,
                    output_limits=(-self.velocity_limits.lateral, self.velocity_limits.lateral)
                )
                logger.debug(f"Sideslip mode PID initialized with gains {self._get_pid_gains('mc_vel_body_right')}")

            elif self.active_lateral_mode == 'coordinated_turn':
                # Coordinated Turn Mode: Yaw rate control (rad/s internally, converted to deg/s on output)
                self.pid_yaw_speed = CustomPID(
                    *self._get_pid_gains('mc_yawspeed_deg_s'),
                    setpoint=setpoint_x,
                    output_limits=(-self.max_yaw_rate_rad, self.max_yaw_rate_rad)  # rad/s limits
                )
                logger.debug(f"Coordinated turn mode PID initialized with gains {self._get_pid_gains('mc_yawspeed_deg_s')}")

            # Down Velocity Controller - Vertical Control (if enabled, use base class cached limits)
            self.pid_down = None
            if self.enable_altitude_control:
                self.pid_down = CustomPID(
                    *self._get_pid_gains('mc_vel_body_down'),
                    setpoint=setpoint_y,
                    output_limits=(-self.velocity_limits.vertical, self.velocity_limits.vertical)
                )
                logger.debug(f"Down velocity PID initialized with gains {self._get_pid_gains('mc_vel_body_down')}")
            else:
                logger.debug("Altitude control disabled - no down velocity PID controller created")
            
            logger.info(f"PID controllers initialized for MCVelocityChaseFollower - Mode: {self.active_lateral_mode}")
            logger.debug(f"PID setpoints - Lateral: {setpoint_x}, Down: {setpoint_y if self.pid_down else 'N/A'}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PID controllers: {e}")
            raise RuntimeError(f"PID controller initialization failed: {e}")

    def _get_active_lateral_mode(self) -> str:
        """
        Determine the active lateral guidance mode based on configuration and flight state.

        Behavior:
        - If auto-switching is disabled, uses configured mode directly.
        - If auto-switching is enabled, switches based on forward velocity threshold
          with hysteresis and minimum switch interval.
        - Logs an advisory when sideslip is selected for fixed-camera operation.

        Returns:
            str: 'sideslip' or 'coordinated_turn'
        """
        try:
            configured_mode = str(self.lateral_guidance_mode).strip().lower()
            if configured_mode not in ('sideslip', 'coordinated_turn'):
                logger.warning(
                    f"Invalid LATERAL_GUIDANCE_MODE '{self.lateral_guidance_mode}' for MC_VELOCITY_CHASE. "
                    "Falling back to coordinated_turn."
                )
                configured_mode = 'coordinated_turn'

            if configured_mode == 'sideslip' and not self._sideslip_advisory_logged:
                logger.warning(
                    "MC_VELOCITY_CHASE running in sideslip mode on fixed camera. "
                    "This is advanced and may increase target-loss risk. "
                    "Use coordinated_turn for more robust framing."
                )
                self._sideslip_advisory_logged = True

            if not self.enable_auto_mode_switching:
                return configured_mode

            current_time = time.time()
            switch_velocity = self.guidance_mode_switch_velocity
            hysteresis = self.mode_switch_hysteresis

            # Prevent mode flapping near threshold.
            if current_time - self.last_mode_switch_time < self.min_mode_switch_interval:
                return self.active_lateral_mode or configured_mode

            active_mode = self.active_lateral_mode or configured_mode

            if active_mode == 'sideslip':
                if self.current_forward_velocity >= switch_velocity + hysteresis:
                    self.last_mode_switch_time = current_time
                    logger.info(
                        f"Mode switch: sideslip -> coordinated_turn (v={self.current_forward_velocity:.2f} m/s)"
                    )
                    return 'coordinated_turn'
            else:
                if self.current_forward_velocity <= switch_velocity - hysteresis:
                    self.last_mode_switch_time = current_time
                    logger.info(
                        f"Mode switch: coordinated_turn -> sideslip (v={self.current_forward_velocity:.2f} m/s)"
                    )
                    return 'sideslip'

            return active_mode

        except Exception as e:
            logger.error(f"Error determining lateral mode: {e}")
            return 'coordinated_turn'

    def _switch_lateral_mode(self, new_mode: str) -> None:
        """
        Switches between lateral guidance modes dynamically.
        
        Args:
            new_mode (str): New lateral guidance mode ('sideslip' or 'coordinated_turn')
        """
        try:
            if new_mode == self.active_lateral_mode:
                return  # No change needed
            
            logger.info(f"Switching lateral guidance mode: {self.active_lateral_mode} → {new_mode}")
            
            old_mode = self.active_lateral_mode
            self.active_lateral_mode = new_mode

            # Use 0.0 as setpoint (consistent with init: center-tracking behavior)
            setpoint_x = 0.0
            
            if new_mode == 'sideslip' and self.pid_right is None:
                # Initialize sideslip PID controller (use base class cached limits)
                self.pid_right = CustomPID(
                    *self._get_pid_gains('mc_vel_body_right'),
                    setpoint=setpoint_x,
                    output_limits=(-self.velocity_limits.lateral, self.velocity_limits.lateral)
                )
                logger.debug("Sideslip PID controller initialized during mode switch")

            elif new_mode == 'coordinated_turn' and self.pid_yaw_speed is None:
                # Initialize coordinated turn PID controller (rad/s internally, converted to deg/s on output)
                self.pid_yaw_speed = CustomPID(
                    *self._get_pid_gains('mc_yawspeed_deg_s'),
                    setpoint=setpoint_x,
                    output_limits=(-self.max_yaw_rate_rad, self.max_yaw_rate_rad)  # rad/s limits
                )
                logger.debug("Coordinated turn PID controller initialized during mode switch")
            
            # Update telemetry
            self.update_telemetry_metadata('lateral_mode_switch', {
                'old_mode': old_mode,
                'new_mode': new_mode,
                'forward_velocity': self.current_forward_velocity,
                'timestamp': datetime.utcnow().isoformat()
            })
            self.update_telemetry_metadata('active_lateral_mode', new_mode)
            
        except Exception as e:
            logger.error(f"Error switching lateral mode to {new_mode}: {e}")

    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves PID gains for the specified control axis.

        Args:
            axis (str): Control axis name ('vel_body_right', 'vel_body_down', 'yawspeed_deg_s').

        Returns:
            Tuple[float, float, float]: (P, I, D) gains for the specified axis.
            
        Raises:
            KeyError: If the specified axis is not configured.
        """
        try:
            gains = Parameters.PID_GAINS[axis]
            return gains['p'], gains['i'], gains['d']
        except KeyError as e:
            logger.error(f"PID gains not found for axis '{axis}': {e}")
            raise KeyError(f"Invalid PID axis '{axis}'. Check Parameters.PID_GAINS configuration.")

    def _update_pid_gains(self) -> None:
        """
        Updates all PID controller gains from current parameter configuration.

        Uses base class _update_pid_gains_from_config() method to eliminate code duplication.
        Handles both lateral guidance modes dynamically.
        """
        try:
            # Use base class method for consistent PID gain updates
            if self.pid_right is not None:
                self._update_pid_gains_from_config(self.pid_right, 'mc_vel_body_right', 'MC Velocity Chase')

            if self.pid_yaw_speed is not None:
                self._update_pid_gains_from_config(self.pid_yaw_speed, 'mc_yawspeed_deg_s', 'MC Velocity Chase')

            if self.pid_down is not None:
                self._update_pid_gains_from_config(self.pid_down, 'mc_vel_body_down', 'MC Velocity Chase')

            logger.debug(f"PID gains updated for MCVelocityChaseFollower - Mode: {self.active_lateral_mode}")

        except Exception as e:
            logger.error(f"Failed to update PID gains: {e}")

    def _update_forward_velocity(self, dt: float) -> float:
        """
        Updates forward velocity using ramping logic with configurable acceleration.
        
        Args:
            dt (float): Time delta since last update in seconds.
            
        Returns:
            float: Updated forward velocity in m/s.
        """
        try:
            # Determine target velocity based on system state
            if self.emergency_stop_active:
                target_velocity = 0.0
            elif self.target_lost and self.ramp_down_on_target_loss:
                # Use configurable stop velocity (default 0.0 = full stop on target loss)
                target_velocity = self.target_loss_stop_velocity
            else:
                target_velocity = self.max_forward_velocity

            # Calculate velocity change
            ramp_rate = self.forward_ramp_rate
            velocity_error = target_velocity - self.current_forward_velocity

            # v5.7.0: Use configurable deadzone (was hardcoded 0.01 m/s)
            if abs(velocity_error) < self.forward_velocity_deadzone:  # Close enough to target
                self.current_forward_velocity = target_velocity
            else:
                # Apply ramping with acceleration limit
                max_change = ramp_rate * dt
                velocity_change = np.clip(velocity_error, -max_change, max_change)
                self.current_forward_velocity += velocity_change
            
            # Apply absolute velocity limits
            self.current_forward_velocity = np.clip(
                self.current_forward_velocity,
                0.0,  # Never go backward
                self.max_forward_velocity
            )
            
            logger.debug(f"Forward velocity updated: {self.current_forward_velocity:.2f} m/s "
                        f"(target: {target_velocity:.2f} m/s, dt: {dt:.3f}s)")
            
            return self.current_forward_velocity
            
        except Exception as e:
            logger.error(f"Error updating forward velocity: {e}")
            return 0.0  # Safe fallback

    def _calculate_tracking_commands(self, target_coords: Tuple[float, float]) -> Tuple[float, float, float]:
        """
        Calculates lateral, vertical, and yaw commands based on active guidance mode.
        
        Args:
            target_coords (Tuple[float, float]): Normalized target coordinates from vision system.
            
        Returns:
            Tuple[float, float, float]: (right_velocity, down_velocity, yaw_speed) commands.
        """
        try:
            # Update PID gains and check for mode changes
            self._update_pid_gains()
            
            # Check if mode switching is needed
            new_mode = self._get_active_lateral_mode()
            if new_mode != self.active_lateral_mode:
                self._switch_lateral_mode(new_mode)
            
            # Calculate tracking errors
            error_x = (self.pid_right.setpoint if self.pid_right else
                      self.pid_yaw_speed.setpoint) - target_coords[0]  # Horizontal error
            error_y = (self.pid_down.setpoint - target_coords[1]) if self.pid_down else 0.0  # Vertical error

            # === PITCH COMPENSATION ===
            # Apply pitch angle compensation to vertical error BEFORE PID processing
            # This removes geometric image shifts caused by forward pitch angles
            if self.pitch_compensation_enabled:
                try:
                    # Get current pitch angle from MAVLink telemetry
                    pitch_angle, pitch_valid = self._get_current_pitch_angle()

                    if pitch_valid:
                        # Calculate compensation based on pitch angle and forward velocity
                        pitch_compensation = self._calculate_pitch_compensation(
                            pitch_angle,
                            self.current_forward_velocity
                        )

                        # Apply compensation to error_y BEFORE PID
                        # This cancels out the geometric shift, preventing false altitude corrections
                        error_y += pitch_compensation

                        logger.debug(f"Pitch compensation applied: {pitch_compensation:+.4f} to error_y")
                    else:
                        logger.debug("Pitch compensation: Data not valid, skipping")

                except Exception as e:
                    logger.error(f"Pitch compensation failed: {e}")
                    # Continue without pitch compensation on error

            # Initialize commands
            right_velocity = 0.0
            down_velocity = 0.0
            yaw_speed = 0.0
            
            # Calculate lateral guidance commands based on active mode
            if self.active_lateral_mode == 'sideslip':
                # Sideslip Mode: Direct lateral velocity, no yaw
                right_velocity = self.pid_right(error_x) if self.pid_right else 0.0
                yaw_speed = 0.0
                
            elif self.active_lateral_mode == 'coordinated_turn':
                # Coordinated Turn Mode: Yaw to track, no sideslip
                right_velocity = 0.0
                yaw_speed = self.pid_yaw_speed(error_x) if self.pid_yaw_speed else 0.0
            
            
            # === APPLY COMMANDS USING SCHEMA-AWARE METHODS ===
            # Schema now uses velocity_body_offboard with yawspeed_deg_s and vel_body_down
            # NOTE: PID output (yaw_speed) is in RAD/S - converted to deg/s via _degrees() below
            # Calculate vertical command (same for both modes)
            down_velocity = self.pid_down(error_y) if self.pid_down else 0.0

            # Apply emergency limits BEFORE smoothing (prevents smoothed state divergence)
            max_error = self.max_tracking_error
            if abs(error_x) > max_error or abs(error_y) > max_error:
                reduction_factor = 0.5
                right_velocity *= reduction_factor
                down_velocity *= reduction_factor
                yaw_speed *= reduction_factor
                logger.debug(f"Large tracking error detected, reducing commands by {reduction_factor}")

            # Apply velocity smoothing if enabled (yaw is handled by YawRateSmoother)
            if self.velocity_smoothing_enabled:
                smoothing_factor = self.smoothing_factor

                # Smooth right velocity (sideslip mode)
                self.smoothed_right_velocity = (smoothing_factor * self.smoothed_right_velocity +
                                               (1 - smoothing_factor) * right_velocity)

                # Smooth down velocity
                self.smoothed_down_velocity = (smoothing_factor * self.smoothed_down_velocity +
                                              (1 - smoothing_factor) * down_velocity)

                # Apply smoothed values (yaw_speed not smoothed here — YawRateSmoother handles it)
                right_velocity = self.smoothed_right_velocity
                down_velocity = self.smoothed_down_velocity
            
            logger.debug(f"Tracking commands ({self.active_lateral_mode}) - "
                        f"Right: {right_velocity:.2f} m/s, Down: {down_velocity:.2f} m/s, "
                        f"Yaw: {yaw_speed:.2f} deg/s, Errors: [{error_x:.2f}, {error_y:.2f}]")
            
            return right_velocity, down_velocity, yaw_speed
            
        except Exception as e:
            logger.error(f"Error calculating tracking commands: {e}")
            return 0.0, 0.0, 0.0  # Safe fallback

    def _handle_target_loss(self, target_coords: Tuple[float, float]) -> bool:
        """
        Handles target loss detection and recovery logic.
        
        Args:
            target_coords (Tuple[float, float]): Current target coordinates.
            
        Returns:
            bool: True if target is valid, False if target is lost.
        """
        try:
            current_time = time.time()
            
            # Check if target coordinates indicate a lost target
            # (This depends on your vision system's lost target indication)
            # Assuming invalid coordinates like (-999, -999) or (nan, nan) indicate lost target
            threshold = self.target_loss_coord_threshold
            is_valid_target = (
                self.validate_target_coordinates(target_coords) and
                not (np.isnan(target_coords[0]) or np.isnan(target_coords[1])) and
                not (abs(target_coords[0]) > threshold or abs(target_coords[1]) > threshold)
            )
            
            if is_valid_target:
                # Target is valid - reset loss tracking
                if self.target_lost:
                    logger.info("Target recovered after loss")
                self.target_lost = False
                self.target_loss_start_time = None
                self.last_valid_target_coords = target_coords
                return True
            else:
                # Target appears to be lost
                if not self.target_lost:
                    # Just lost the target
                    self.target_lost = True
                    self.target_loss_start_time = current_time
                    logger.warning(f"Target lost at coordinates: {target_coords}")
                else:
                    # Target has been lost for some time
                    loss_duration = current_time - self.target_loss_start_time
                    timeout = self.target_loss_timeout
                    
                    if loss_duration > timeout:
                        logger.debug(f"Target lost for {loss_duration:.1f}s (timeout: {timeout}s)")
                
                return False
                
        except Exception as e:
            logger.error(f"Error in target loss handling: {e}")
            return False

    def _calculate_target_vertical_rate(self, target_coords: Tuple[float, float], tracker_data: TrackerOutput) -> Tuple[float, float, float]:
        """
        Calculates target vertical rate with filtering and compares to expected rate.

        This is Phase 1 of adaptive dive/climb control. It:
        1. Records target Y coordinates over time
        2. Calculates instantaneous vertical rate (pixels/sec)
        3. Applies exponential moving average (EMA) filtering
        4. Computes expected vertical rate from commanded velocities
        5. Returns rate error for use in adaptive corrections

        Args:
            target_coords (Tuple[float, float]): Current normalized target coordinates (x, y)
            tracker_data (TrackerOutput): Tracker data with confidence and timestamps

        Returns:
            Tuple[float, float, float]: (smoothed_rate, expected_rate, rate_error) all in pixels/sec

        Note:
            - Returns (0.0, 0.0, 0.0) if adaptive mode disabled or during warmup
            - Returns (0.0, 0.0, 0.0) if insufficient data or low confidence
        """
        try:
            # Check if adaptive mode is enabled
            if not self.adaptive_mode_enabled:
                return 0.0, 0.0, 0.0

            # Check minimum confidence threshold
            if tracker_data.confidence is not None and tracker_data.confidence < self.adaptive_min_confidence:
                logger.debug(f"Adaptive mode: Confidence too low ({tracker_data.confidence:.2f} < {self.adaptive_min_confidence})")
                self.adaptive_active = False
                return 0.0, 0.0, 0.0

            current_time = time.time()
            target_y = target_coords[1]  # Vertical coordinate (normalized)

            # Store current measurement in history
            self.target_vertical_history.append((current_time, target_y))

            # Warmup period - accumulate data but don't compute rates yet
            self.adaptive_warmup_counter += 1
            if self.adaptive_warmup_counter < self.adaptive_warmup_frames:
                logger.debug(f"Adaptive mode: Warming up ({self.adaptive_warmup_counter}/{self.adaptive_warmup_frames})")
                return 0.0, 0.0, 0.0

            # Need at least 2 samples to compute rate
            if len(self.target_vertical_history) < 2:
                return 0.0, 0.0, 0.0

            # Calculate instantaneous vertical rate using recent samples
            # Use last N samples for more robust rate estimation
            sample_window = min(5, len(self.target_vertical_history))
            recent_samples = list(self.target_vertical_history)[-sample_window:]

            # Linear regression or simple difference for rate estimation
            if len(recent_samples) >= 2:
                # Use first and last sample for rate (more noise-resistant than frame-to-frame)
                t1, y1 = recent_samples[0]
                t2, y2 = recent_samples[-1]
                dt = t2 - t1

                if dt > 0.001:  # Avoid division by zero
                    # Raw vertical rate in normalized coords per second
                    raw_rate = (y2 - y1) / dt

                    # Convert to pixels/sec using configurable video height
                    # v5.7.0: Use self.video_height_pixels (was hardcoded 480.0)
                    instantaneous_rate = raw_rate * self.video_height_pixels  # Scale to pixel-equivalent rate

                    # Apply exponential moving average (EMA) filtering
                    alpha = self.adaptive_smoothing_alpha
                    self.smoothed_vertical_rate = (alpha * instantaneous_rate +
                                                  (1 - alpha) * self.smoothed_vertical_rate)
                else:
                    instantaneous_rate = 0.0
            else:
                instantaneous_rate = 0.0

            # Calculate expected vertical rate based on commanded velocities
            # This requires mapping vel_body_down to expected pixel rate
            # Expected rate depends on: altitude, FOV, forward velocity (perspective)
            # For initial implementation, use simplified model:
            # expected_pixel_rate ≈ vel_body_down * calibration_factor / (altitude_estimate)

            # Since we don't have distance/altitude directly, use calibration factor
            # that user can tune based on their specific scenario
            # v5.7.0: Use self.video_height_pixels (was hardcoded 480.0)
            expected_rate = self.smoothed_down_velocity * self.pixel_to_rate_calibration * self.video_height_pixels

            # Note: This is a simplified model. For better accuracy:
            # - Account for forward velocity (perspective scaling)
            # - Use altitude from telemetry if available
            # - Calibrate pixel_to_rate_calibration factor in field

            # Compute rate error
            rate_error = self.smoothed_vertical_rate - expected_rate

            # Update state
            self.expected_vertical_rate = expected_rate
            self.vertical_rate_error = rate_error
            self.adaptive_active = True

            logger.debug(f"Adaptive rates - Observed: {self.smoothed_vertical_rate:.2f}, "
                        f"Expected: {expected_rate:.2f}, Error: {rate_error:.2f} px/s")

            return self.smoothed_vertical_rate, expected_rate, rate_error

        except Exception as e:
            logger.error(f"Error calculating target vertical rate: {e}")
            self.adaptive_active = False
            return 0.0, 0.0, 0.0

    def _adapt_dive_climb_velocities(self, rate_error: float, current_v_fwd: float, current_v_down: float) -> Tuple[float, float]:
        """
        Adapts forward and down velocities based on vertical rate error.

        This is Phase 2 of adaptive dive/climb control. It:
        1. Checks if rate error exceeds threshold (dead-zone)
        2. Computes correction based on proportional gain
        3. Applies mode-aware authority limits (sideslip vs coordinated turn)
        4. Clamps corrections to safety limits
        5. Returns corrected velocities

        Logic:
        - Positive rate_error: Target descending faster than expected → increase v_down, decrease v_fwd
        - Negative rate_error: Target ascending relative to expected → decrease v_down, increase v_fwd

        Args:
            rate_error (float): Vertical rate error in pixels/sec (observed - expected)
            current_v_fwd (float): Current forward velocity command (m/s)
            current_v_down (float): Current down velocity command (m/s)

        Returns:
            Tuple[float, float]: (adjusted_v_fwd, adjusted_v_down) in m/s

        Note:
            - Returns unchanged velocities if adaptive mode inactive
            - Respects PX4 velocity limits from SafetyLimits configuration
            - Mode-specific authority: sideslip mode gets 50% reduced correction
        """
        try:
            # Check if corrections should be applied
            if not self.adaptive_active or not self.adaptive_mode_enabled:
                return current_v_fwd, current_v_down

            # Dead-zone: ignore small errors to prevent over-reaction
            threshold = self.adaptive_rate_threshold
            if abs(rate_error) < threshold:
                # Error within dead-zone, no correction needed
                self.adaptive_correction_down = 0.0
                self.adaptive_correction_fwd = 0.0
                return current_v_fwd, current_v_down

            # Compute correction magnitude (proportional to error beyond threshold)
            error_magnitude = rate_error - np.sign(rate_error) * threshold  # Remove dead-zone
            base_correction = error_magnitude * self.adaptive_correction_gain

            # Clamp to maximum correction authority
            base_correction = np.clip(base_correction, -self.adaptive_max_correction, self.adaptive_max_correction)

            # Mode-specific authority adjustment
            # Sideslip mode: reduce correction authority for precision operations
            if self.active_lateral_mode == 'sideslip':
                authority_factor = 0.5  # 50% authority in sideslip mode
                logger.debug("Adaptive mode: Reducing correction authority (sideslip mode)")
            else:
                authority_factor = 1.0  # Full authority in coordinated turn mode

            base_correction *= authority_factor

            # Apply corrections to velocities
            # Positive rate_error (target descending too fast): increase v_down, decrease v_fwd
            # Negative rate_error (target not descending enough): decrease v_down, increase v_fwd

            # Down velocity correction (primary control axis)
            v_down_correction = base_correction * 0.01  # Scale from pixels/s error to m/s correction

            # Forward velocity correction (optional, controlled by coupling flag)
            if self.adaptive_fwd_coupling_enabled:
                # Inverse relationship: if target descending too fast, slow down approach
                v_fwd_correction = -base_correction * self.adaptive_fwd_coupling_gain * 0.01
            else:
                v_fwd_correction = 0.0

            # Store corrections for telemetry
            self.adaptive_correction_down = v_down_correction
            self.adaptive_correction_fwd = v_fwd_correction

            # Apply corrections (additive to PID output)
            adjusted_v_down = current_v_down + v_down_correction
            adjusted_v_fwd = current_v_fwd + v_fwd_correction

            # Apply absolute velocity limits from base class cached limits
            adjusted_v_fwd = np.clip(adjusted_v_fwd, 0.0, self.velocity_limits.forward)  # Never go backward
            adjusted_v_down = np.clip(adjusted_v_down, -self.velocity_limits.vertical, self.velocity_limits.vertical)

            # Ensure forward velocity doesn't drop below minimum threshold
            if adjusted_v_fwd < self.min_forward_velocity_threshold:
                adjusted_v_fwd = self.min_forward_velocity_threshold

            logger.debug(f"Adaptive corrections - v_down: {v_down_correction:+.2f} m/s, "
                        f"v_fwd: {v_fwd_correction:+.2f} m/s, "
                        f"Final: fwd={adjusted_v_fwd:.2f}, down={adjusted_v_down:.2f}")

            return adjusted_v_fwd, adjusted_v_down

        except Exception as e:
            logger.error(f"Error adapting dive/climb velocities: {e}")
            # Safe fallback: return original velocities
            return current_v_fwd, current_v_down

    def _check_adaptive_oscillation(self) -> bool:
        """
        Detects oscillations in rate error by monitoring sign changes.

        Oscillation indicates the adaptive system is fighting with PID or over-correcting
        due to noise. If detected, adaptive mode is automatically disabled for safety.

        Returns:
            bool: True if oscillation detected, False otherwise
        """
        try:
            if not self.adaptive_oscillation_detection:
                return False

            # Record current error sign in history
            current_time = time.time()
            if abs(self.vertical_rate_error) > 0.1:  # Ignore near-zero errors
                error_sign = int(np.sign(self.vertical_rate_error))
                self.rate_error_sign_history.append((current_time, error_sign))

            # Need sufficient history to detect oscillation
            if len(self.rate_error_sign_history) < 4:
                return False

            # Count sign changes in recent history (last 2 seconds)
            recent_window = 2.0  # seconds
            cutoff_time = current_time - recent_window
            recent_signs = [(t, sign) for t, sign in self.rate_error_sign_history if t >= cutoff_time]

            if len(recent_signs) < 2:
                return False

            # Count sign changes
            sign_changes = 0
            for i in range(1, len(recent_signs)):
                if recent_signs[i][1] != recent_signs[i-1][1]:
                    sign_changes += 1

            # Check if sign changes exceed threshold
            if sign_changes >= self.adaptive_max_sign_changes:
                logger.warning(f"Adaptive mode: Oscillation detected! "
                             f"{sign_changes} sign changes in {recent_window}s - DISABLING")
                self.adaptive_disabled_reason = "oscillation_detected"
                self.adaptive_mode_enabled = False
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking adaptive oscillation: {e}")
            return False

    def _check_adaptive_divergence(self) -> bool:
        """
        Detects divergence: rate error growing despite corrections.

        If error magnitude consistently increases over timeout period,
        it indicates corrections are ineffective or counter-productive.

        Returns:
            bool: True if divergence detected, False otherwise
        """
        try:
            current_time = time.time()
            error_magnitude = abs(self.vertical_rate_error)

            # Track when large error first appeared
            if error_magnitude > self.adaptive_rate_threshold * 2.0:  # 2x threshold
                if self.adaptive_divergence_start_time is None:
                    self.adaptive_divergence_start_time = current_time
                    logger.debug("Adaptive mode: Large error detected, monitoring for divergence...")
                else:
                    # Check if error has persisted beyond timeout
                    divergence_duration = current_time - self.adaptive_divergence_start_time
                    if divergence_duration > self.adaptive_divergence_timeout:
                        logger.warning(f"Adaptive mode: Divergence detected! "
                                     f"Error {error_magnitude:.1f} px/s persisted for {divergence_duration:.1f}s - DISABLING")
                        self.adaptive_disabled_reason = "divergence_detected"
                        self.adaptive_mode_enabled = False
                        return True
            else:
                # Error returned to reasonable levels, reset divergence tracker
                self.adaptive_divergence_start_time = None

            return False

        except Exception as e:
            logger.error(f"Error checking adaptive divergence: {e}")
            return False

    def _get_current_pitch_angle(self) -> Tuple[float, bool]:
        """
        Retrieves current pitch angle from MAVLink telemetry with filtering and validation.

        This method:
        1. Retrieves pitch angle from px4_controller attitude data
        2. Validates data freshness (age < pitch_data_max_age)
        3. Applies exponential moving average (EMA) filtering
        4. Clamps pitch angle to configured maximum
        5. Updates state variables for pitch compensation

        Returns:
            Tuple[float, bool]: (pitch_angle_deg, data_valid)
                - pitch_angle_deg: Smoothed pitch angle in degrees (positive = nose up)
                - data_valid: True if data is fresh and valid, False otherwise

        Note:
            - Returns (0.0, False) if pitch compensation disabled
            - Returns (0.0, False) if MAVLink data unavailable or stale
            - Pitch angle convention: positive = nose up, negative = nose down
        """
        try:
            # Check if pitch compensation is enabled
            if not self.pitch_compensation_enabled:
                return 0.0, False

            current_time = time.time()

            # Retrieve pitch angle from PX4 controller telemetry
            # The px4_controller should have attitude data from MAVLink
            # Typical attribute: px4_controller.attitude or px4_controller.current_pitch
            pitch_rad = getattr(self.px4_controller, 'current_pitch', None)

            if pitch_rad is None:
                # Try alternate attribute names
                attitude = getattr(self.px4_controller, 'attitude', None)
                if attitude is not None and hasattr(attitude, 'pitch'):
                    pitch_rad = attitude.pitch
                else:
                    logger.debug("Pitch compensation: No pitch data available from MAVLink")
                    self.pitch_data_valid = False
                    self.pitch_compensation_active = False
                    return 0.0, False

            # Convert radians to degrees
            pitch_deg = np.degrees(pitch_rad)

            # Check data freshness (timestamp validation)
            # If px4_controller provides timestamp, validate it
            pitch_timestamp = getattr(self.px4_controller, 'attitude_timestamp', current_time)
            data_age = current_time - pitch_timestamp

            if data_age > self.pitch_data_max_age:
                logger.debug(f"Pitch compensation: Data too old ({data_age:.2f}s > {self.pitch_data_max_age}s)")
                self.pitch_data_valid = False
                self.pitch_compensation_active = False
                return 0.0, False

            # Update timestamp
            self.last_pitch_timestamp = pitch_timestamp

            # Apply maximum angle clamping for safety
            if abs(pitch_deg) > self.pitch_max_angle:
                logger.warning(f"Pitch compensation: Angle {pitch_deg:.1f}° exceeds max {self.pitch_max_angle}°, clamping")
                pitch_deg = np.clip(pitch_deg, -self.pitch_max_angle, self.pitch_max_angle)

            # Apply exponential moving average (EMA) filtering
            # First update: initialize smoothed value
            if self.smoothed_pitch_angle == 0.0 and self.current_pitch_angle == 0.0:
                self.smoothed_pitch_angle = pitch_deg  # Initialize without filtering
            else:
                alpha = self.pitch_smoothing_alpha
                self.smoothed_pitch_angle = (alpha * pitch_deg +
                                            (1 - alpha) * self.smoothed_pitch_angle)

            # Update current pitch angle
            self.current_pitch_angle = pitch_deg

            # Mark data as valid
            self.pitch_data_valid = True

            logger.debug(f"Pitch compensation: Raw={pitch_deg:.2f}°, Smoothed={self.smoothed_pitch_angle:.2f}°, Age={data_age:.3f}s")

            return self.smoothed_pitch_angle, True

        except Exception as e:
            logger.error(f"Error retrieving pitch angle: {e}")
            self.pitch_data_valid = False
            self.pitch_compensation_active = False
            return 0.0, False

    def _calculate_pitch_compensation(self, pitch_angle: float, forward_velocity: float) -> float:
        """
        Calculates vertical coordinate compensation based on pitch angle and velocity.

        This method implements the core pitch compensation algorithm to remove geometric
        image shifts caused by forward pitch during acceleration/deceleration.

        Physical Principle:
        -------------------
        When drone pitches forward (θ > 0):
        - Camera optical axis rotates downward by angle θ
        - Target appears to shift DOWN in image (positive Δy in normalized coords)
        - Without compensation, PID interprets this as "target below center"
        - PID commands v_down (descent), causing unwanted altitude loss

        Solution:
        - Add compensation_value to error_y BEFORE PID processing
        - This cancels the geometric shift, preventing false altitude corrections

        Compensation Models:
        --------------------
        1. linear_velocity: Δy = K * θ * v_fwd
           - Compensation scales with both pitch angle and forward velocity
           - Best for dynamic flight with varying speeds
           - Recommended default model

        2. linear_angle: Δy = K * θ
           - Compensation depends only on pitch angle
           - Simpler model for constant-speed scenarios
           - Good for aggressive tuning without velocity coupling

        3. quadratic: Δy = K * θ² * sign(θ)
           - Non-linear model for extreme pitch angles (>20°)
           - Accounts for increased geometric distortion at high angles
           - Use when linear models under-compensate

        Args:
            pitch_angle (float): Smoothed pitch angle in degrees (positive = nose up)
            forward_velocity (float): Current forward velocity in m/s

        Returns:
            float: Compensation value in normalized coordinates [-pitch_max_correction, +pitch_max_correction]
                   - Positive compensation: counteracts downward image shift (nose-up pitch)
                   - Negative compensation: counteracts upward image shift (nose-down pitch)

        Note:
            - Returns 0.0 if pitch angle within deadband
            - Returns 0.0 if forward velocity below minimum threshold
            - Compensation is additive to error_y in PID calculation
            - Stored in self.pitch_compensation_value for telemetry
        """
        try:
            # Apply deadband: ignore small pitch angles to prevent over-reaction
            if abs(pitch_angle) < self.pitch_deadband:
                self.pitch_compensation_value = 0.0
                self.pitch_compensation_active = False
                return 0.0

            # Check minimum forward velocity threshold
            # Pitch compensation is most critical during forward flight
            if forward_velocity < self.pitch_min_velocity:
                logger.debug(f"Pitch compensation: Forward velocity {forward_velocity:.2f} m/s below threshold {self.pitch_min_velocity} m/s")
                self.pitch_compensation_value = 0.0
                self.pitch_compensation_active = False
                return 0.0

            # Select compensation model
            model = self.pitch_compensation_model
            gain = self.pitch_compensation_gain

            # Adaptive gain adjustment (optional)
            if self.pitch_adaptive_gain:
                # Increase gain at higher forward velocities
                # Rationale: Higher speed = more pronounced pitch angles = stronger geometric effect
                velocity_factor = min(forward_velocity / 10.0, 2.0)  # Cap at 2x gain
                gain *= velocity_factor
                logger.debug(f"Pitch compensation: Adaptive gain {gain:.4f} (velocity_factor={velocity_factor:.2f})")

            # Calculate base compensation based on selected model
            if model == "linear_velocity":
                # Compensation = K * θ * v_fwd
                # This model captures the fact that geometric shift increases with both pitch and speed
                compensation = gain * pitch_angle * forward_velocity

            elif model == "linear_angle":
                # Compensation = K * θ
                # Simpler model ignoring velocity, useful for constant-speed operations
                compensation = gain * pitch_angle * 10.0  # Scale factor for normalization

            elif model == "quadratic":
                # Compensation = K * θ² * sign(θ)
                # Non-linear model for extreme angles where distortion is non-linear
                compensation = gain * (pitch_angle ** 2) * np.sign(pitch_angle) * forward_velocity * 0.1

            else:
                logger.warning(f"Pitch compensation: Unknown model '{model}', using linear_velocity")
                compensation = gain * pitch_angle * forward_velocity

            # Clamp compensation to maximum authority for safety
            max_correction = self.pitch_max_correction
            compensation = np.clip(compensation, -max_correction, max_correction)

            # Store compensation value for telemetry and debugging
            self.pitch_compensation_value = compensation
            self.pitch_compensation_active = True

            # Record in history for analysis
            current_time = time.time()
            self.pitch_compensation_history.append((current_time, compensation))

            logger.debug(f"Pitch compensation: Model={model}, Angle={pitch_angle:.2f}°, "
                        f"v_fwd={forward_velocity:.2f} m/s, Compensation={compensation:+.4f}")

            return compensation

        except Exception as e:
            logger.error(f"Error calculating pitch compensation: {e}")
            self.pitch_compensation_value = 0.0
            self.pitch_compensation_active = False
            return 0.0

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

        # Skip if disabled via SafetyManager
        if not self.is_altitude_safety_enabled():
            return True

        try:
            # Cache safety behavior for this method (avoids repeated lookups)
            safety = self.safety_manager.get_safety_behavior(self._follower_config_name)

            current_time = time.time()
            check_interval = self.altitude_check_interval

            # Only check at specified intervals to avoid excessive processing
            if (current_time - self.last_altitude_check_time) < check_interval:
                return True

            self.last_altitude_check_time = current_time

            # Get current altitude from PX4 controller
            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)
            min_altitude = self.min_altitude_limit
            max_altitude = self.max_altitude_limit
            warning_buffer = self.altitude_warning_buffer

            # Check for violations
            altitude_violation = (current_altitude < min_altitude or current_altitude > max_altitude)
            altitude_warning = (
                current_altitude < (min_altitude + warning_buffer) or
                current_altitude > (max_altitude - warning_buffer)
            )

            if altitude_violation:
                self.altitude_violation_count += 1
                logger.critical(f"ALTITUDE SAFETY VIOLATION! Current: {current_altitude:.1f}m, "
                              f"Limits: [{min_altitude}-{max_altitude}]m, "
                              f"Violation count: {self.altitude_violation_count}")

                # Trigger RTL if enabled via SafetyManager
                if safety.rtl_on_violation:
                    logger.critical("Triggering Return to Launch due to altitude violation")
                    try:
                        # Actually trigger RTL via PX4 controller
                        if self.px4_controller and hasattr(self.px4_controller, 'trigger_return_to_launch'):
                            try:
                                loop = asyncio.get_running_loop()
                                asyncio.create_task(self.px4_controller.trigger_return_to_launch())
                            except RuntimeError:
                                # No running loop - create new one
                                asyncio.run(self.px4_controller.trigger_return_to_launch())
                            logger.critical("RTL command issued successfully")
                        else:
                            logger.error("PX4 controller not available for RTL - emergency stop only")
                    except Exception as rtl_error:
                        logger.error(f"Failed to trigger RTL: {rtl_error}")
                
                # Activate emergency stop
                self.emergency_stop_active = True
                self.update_telemetry_metadata('safety_violation', 'altitude_bounds')
                return False
                
            elif altitude_warning and self.altitude_violation_count == 0:
                logger.warning(f"Altitude warning: {current_altitude:.1f}m approaching limits "
                             f"[{min_altitude}-{max_altitude}]m")
            else:
                # Reset violation count if altitude is safe
                self.altitude_violation_count = 0
            
            return True
            
        except Exception as e:
            logger.error(f"Altitude safety check failed: {e}")
            return True  # Fail safe - allow operation if check fails

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculates and sets body velocity control commands with dual-mode lateral guidance.

        This method implements the core body velocity chase logic with support for both
        sideslip and coordinated turn lateral guidance modes:
        1. Extracts target coordinates from structured tracker data
        2. Handles target loss detection and recovery with confidence analysis
        3. Updates forward velocity using ramping logic
        4. Calculates lateral and vertical tracking commands with mode switching
        5. Applies safety checks and emergency stops
        6. Updates setpoint handler with commands

        Altitude Sign Convention (NED/Body Frame):
        - vel_body_down > 0 = DESCENDING (moving down)
        - vel_body_down < 0 = ASCENDING (moving up)
        - PID output is directly in NED convention (positive=down, negative=up)
        - No sign reversal needed when setting vel_body_down

        Test Values for Verification:
        - Target above drone (top of image): error > 0 → vel_body_down > 0 (descend to reach target)
        - Target below drone (bottom of image): error < 0 → vel_body_down < 0 (climb to reach target)

        Args:
            tracker_data (TrackerOutput): Structured tracker data with position, confidence, etc.

        Note:
            This method updates the setpoint handler directly and does not return values.
            Control commands are applied via the schema-aware setpoint management system.
        """
        try:
            current_time = time.time()
            dt = current_time - self.last_ramp_update_time
            self.last_ramp_update_time = current_time
            
            # Extract target coordinates from structured data
            target_coords = self.extract_target_coordinates(tracker_data)
            if not target_coords:
                logger.warning("No valid target coordinates found in tracker data")
                self._handle_tracking_failure()
                return
            
            # Handle target loss detection (enhanced with confidence analysis)
            target_valid = self._handle_target_loss_enhanced(target_coords, tracker_data)
            
            # Use last valid coordinates if target is lost
            tracking_coords = target_coords if target_valid else self.last_valid_target_coords
            
            # Update forward velocity using ramping logic
            forward_velocity = self._update_forward_velocity(dt)

            # Calculate tracking commands (includes mode switching logic)
            right_velocity, down_velocity, yaw_speed = self._calculate_tracking_commands(tracking_coords)

            # === ADAPTIVE DIVE/CLIMB CONTROL ===
            # Calculate vertical rate and apply adaptive corrections if enabled
            if self.adaptive_mode_enabled and target_valid:
                try:
                    # Phase 1: Calculate vertical rate error
                    smoothed_rate, expected_rate, rate_error = self._calculate_target_vertical_rate(
                        tracking_coords, tracker_data
                    )

                    # Phase 2: Apply adaptive corrections to velocities
                    forward_velocity, down_velocity = self._adapt_dive_climb_velocities(
                        rate_error, forward_velocity, down_velocity
                    )

                    # Phase 3: Safety monitoring - check for oscillations and divergence
                    oscillation_detected = self._check_adaptive_oscillation()
                    divergence_detected = self._check_adaptive_divergence()

                    if oscillation_detected or divergence_detected:
                        logger.warning(f"Adaptive mode disabled due to: {self.adaptive_disabled_reason}")

                    logger.debug(f"Adaptive dive/climb active - Rate error: {rate_error:.2f} px/s")

                except Exception as e:
                    logger.error(f"Adaptive dive/climb failed: {e}")
                    # Continue with non-adaptive velocities on error

            # Apply emergency stop if active
            if self.emergency_stop_active:
                forward_velocity = 0.0
                right_velocity = 0.0
                down_velocity = 0.0
                yaw_speed = 0.0
                logger.debug("Emergency stop active - all commands set to zero")
            
            # Update setpoint handler using schema-aware methods
            self.set_command_field('vel_body_fwd', forward_velocity)
            self.set_command_field('vel_body_right', right_velocity)
            self.set_command_field('vel_body_down', down_velocity)

            # v5.7.0: Apply enterprise-grade yaw rate smoothing (deadzone, rate limiting, EMA)
            raw_yaw_rate_deg_s = degrees(yaw_speed)  # rad/s → deg/s
            smoothed_yaw_rate = self.yaw_smoother.apply(raw_yaw_rate_deg_s, dt, forward_velocity)
            self.set_command_field('yawspeed_deg_s', smoothed_yaw_rate)
            
            # Update telemetry metadata
            self.update_telemetry_metadata('last_target_coords', target_coords)
            self.update_telemetry_metadata('target_valid', target_valid)
            self.update_telemetry_metadata('current_forward_velocity', forward_velocity)
            self.update_telemetry_metadata('active_lateral_mode', self.active_lateral_mode)
            self.update_telemetry_metadata('emergency_stop_active', self.emergency_stop_active)

            # Adaptive mode telemetry
            if self.adaptive_mode_enabled:
                self.update_telemetry_metadata('adaptive_active', self.adaptive_active)
                self.update_telemetry_metadata('adaptive_rate_error', self.vertical_rate_error)
                self.update_telemetry_metadata('adaptive_correction_down', self.adaptive_correction_down)
                self.update_telemetry_metadata('adaptive_correction_fwd', self.adaptive_correction_fwd)
                if self.adaptive_disabled_reason:
                    self.update_telemetry_metadata('adaptive_disabled_reason', self.adaptive_disabled_reason)
            
            logger.debug(f"Body velocity commands ({self.active_lateral_mode}) - "
                        f"Fwd: {forward_velocity:.2f}, Right: {right_velocity:.2f}, "
                        f"Down: {down_velocity:.2f} m/s, Yaw: {smoothed_yaw_rate:.2f} deg/s (raw: {raw_yaw_rate_deg_s:.2f})")
            
        except Exception as e:
            logger.error(f"Error calculating control commands: {e}")
            # Set safe fallback commands
            self.set_command_field('vel_body_fwd', 0.0)
            self.set_command_field('vel_body_right', 0.0)
            self.set_command_field('vel_body_down', 0.0)
            self.set_command_field('yawspeed_deg_s', 0.0)

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Executes target following with dual-mode body velocity chase control logic.
        
        This is the main entry point for body velocity chase following behavior. It performs
        compatibility validation, safety checks, and calculates control commands.
        
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
                logger.error("Altitude safety check failed - aborting body velocity following")
                return False

            # Calculate and apply control commands using structured data
            self.calculate_control_commands(tracker_data)

            logger.debug(f"Body velocity following executed for tracker: {tracker_data.tracker_id}")
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

    # ==================== Enhanced Telemetry and Status ====================
    
    def get_chase_status(self) -> Dict[str, Any]:
        """
        Returns comprehensive body velocity chase follower status with dual-mode information.
        
        Returns:
            Dict[str, Any]: Detailed status including velocities, modes, safety status, and control state.
        """
        try:
            current_time = time.time()
            
            return {
                # Velocity State
                'current_forward_velocity': self.current_forward_velocity,
                'target_forward_velocity': self.target_forward_velocity,
                'smoothed_right_velocity': self.smoothed_right_velocity,
                'smoothed_down_velocity': self.smoothed_down_velocity,
                'smoothed_yaw_speed': self.smoothed_yaw_speed,
                
                # Lateral Guidance Mode State
                'active_lateral_mode': self.active_lateral_mode,
                'configured_lateral_mode': self.lateral_guidance_mode,
                'auto_mode_switching_enabled': self.enable_auto_mode_switching,
                'mode_switch_velocity': self.guidance_mode_switch_velocity,
                
                # Target Tracking State
                'target_lost': self.target_lost,
                'target_loss_duration': (
                    (current_time - self.target_loss_start_time) 
                    if self.target_loss_start_time else 0.0
                ),
                'last_valid_target_coords': self.last_valid_target_coords,
                
                # Safety Status
                'emergency_stop_active': self.emergency_stop_active,
                'altitude_violation_count': self.altitude_violation_count,
                'altitude_safety_enabled': self.is_altitude_safety_enabled(),
                
                # PID States
                'pid_states': {
                    'right_setpoint': self.pid_right.setpoint if self.pid_right else None,
                    'down_setpoint': self.pid_down.setpoint if self.pid_down else None,
                    'yaw_speed_setpoint': self.pid_yaw_speed.setpoint if hasattr(self, 'pid_yaw_speed') and self.pid_yaw_speed else None,
                },
                
                # Configuration Status
                'config': {
                    'max_forward_velocity': self.max_forward_velocity,
                    'ramp_rate': self.forward_ramp_rate,
                    'altitude_control_enabled': self.enable_altitude_control,
                    'min_altitude_limit': self.min_altitude_limit,
                    'max_altitude_limit': self.max_altitude_limit,
                    'velocity_smoothing_enabled': self.velocity_smoothing_enabled,
                    'smoothing_factor': self.smoothing_factor,
                    'max_tracking_error': self.max_tracking_error
                },

                # Adaptive Dive/Climb Status
                'adaptive_mode': {
                    'enabled': self.adaptive_mode_enabled,
                    'active': self.adaptive_active,
                    'warmup_counter': self.adaptive_warmup_counter,
                    'smoothed_vertical_rate': self.smoothed_vertical_rate,
                    'expected_vertical_rate': self.expected_vertical_rate,
                    'vertical_rate_error': self.vertical_rate_error,
                    'correction_down': self.adaptive_correction_down,
                    'correction_fwd': self.adaptive_correction_fwd,
                    'disabled_reason': self.adaptive_disabled_reason,
                    'fwd_coupling_enabled': self.adaptive_fwd_coupling_enabled
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating chase status: {e}")
            return {'error': str(e)}

    def get_status_report(self) -> str:
        """
        Generates a comprehensive human-readable status report with dual-mode information.
        
        Returns:
            str: Formatted status report including all chase-specific and mode information.
        """
        try:
            # Get base status from parent class (if available)
            try:
                base_report = super().get_status_report()
            except AttributeError:
                base_report = ""
            
            # Add chase-specific status
            chase_status = self.get_chase_status()
            
            chase_report = f"\n{'='*60}\n"
            chase_report += f"Body Velocity Chase Follower Status (Dual-Mode)\n"
            chase_report += f"{'='*60}\n"
            
            # Velocity Status
            chase_report += f"Forward Velocity: {chase_status.get('current_forward_velocity', 0.0):.2f} m/s "
            chase_report += f"(target: {chase_status.get('target_forward_velocity', 0.0):.2f} m/s)\n"
            chase_report += f"Right Velocity: {chase_status.get('smoothed_right_velocity', 0.0):.2f} m/s\n"
            chase_report += f"Down Velocity: {chase_status.get('smoothed_down_velocity', 0.0):.2f} m/s\n"
            chase_report += f"Yaw Speed: {chase_status.get('smoothed_yaw_speed', 0.0):.2f} deg/s\n"
            
            # Lateral Guidance Mode Status
            chase_report += f"\nLateral Guidance Mode:\n"
            chase_report += f"  Active Mode: {chase_status.get('active_lateral_mode', 'unknown').title()}\n"
            chase_report += f"  Configured Mode: {chase_status.get('configured_lateral_mode', 'unknown').title()}\n"
            chase_report += f"  Auto-Switching: {'✓' if chase_status.get('auto_mode_switching_enabled', False) else '✗'}\n"
            if chase_status.get('auto_mode_switching_enabled', False):
                chase_report += f"  Switch Velocity: {chase_status.get('mode_switch_velocity', 0.0):.1f} m/s\n"
            
            # Target status
            chase_report += f"\nTarget Status:\n"
            chase_report += f"  Target Lost: {'✓' if chase_status.get('target_lost', False) else '✗'}\n"
            if chase_status.get('target_lost', False):
                chase_report += f"  Loss Duration: {chase_status.get('target_loss_duration', 0.0):.1f}s\n"
            
            # Safety status
            chase_report += f"\nSafety Status:\n"
            chase_report += f"  Emergency Stop: {'✓' if chase_status.get('emergency_stop_active', False) else '✗'}\n"
            chase_report += f"  Altitude Safety: {'✓' if chase_status.get('altitude_safety_enabled', False) else '✗'}\n"
            chase_report += f"  Altitude Violations: {chase_status.get('altitude_violation_count', 0)}\n"
            
            # Configuration
            config = chase_status.get('config', {})
            chase_report += f"\nConfiguration:\n"
            chase_report += f"  Max Forward Speed: {config.get('max_forward_velocity', 0.0):.1f} m/s\n"
            chase_report += f"  Ramp Rate: {config.get('ramp_rate', 0.0):.1f} m/s²\n"
            chase_report += f"  Altitude Control: {'✓' if config.get('altitude_control_enabled', False) else '✗'}\n"
            chase_report += f"  Altitude Limits: {config.get('min_altitude_limit', 0.0):.0f}-{config.get('max_altitude_limit', 0.0):.0f}m\n"
            
            return base_report + chase_report
            
        except Exception as e:
            return f"Error generating body velocity chase status report: {e}"

    def reset_chase_state(self) -> None:
        """
        Resets chase-specific state variables to initial conditions including mode state.
        
        Useful for reinitializing after mode switches or error recovery.
        """
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
            self.last_ramp_update_time = time.time()
            self.last_altitude_check_time = time.time()
            
            # Reset lateral guidance mode to configured default
            self.active_lateral_mode = self._get_active_lateral_mode()

            # Reset adaptive dive/climb state
            self.adaptive_active = False
            self.target_vertical_history.clear()
            self.smoothed_vertical_rate = 0.0
            self.expected_vertical_rate = 0.0
            self.vertical_rate_error = 0.0
            self.adaptive_warmup_counter = 0
            self.last_target_y_coord = None
            self.last_target_timestamp = None
            self.adaptive_correction_down = 0.0
            self.adaptive_correction_fwd = 0.0
            self.rate_error_sign_history.clear()
            self.adaptive_divergence_start_time = None
            # Note: adaptive_disabled_reason and adaptive_mode_enabled are NOT reset
            # User must manually re-enable if it was auto-disabled

            # Reset PID integrators to prevent windup
            if self.pid_right:
                self.pid_right.reset()
            if self.pid_down:
                self.pid_down.reset()
            if hasattr(self, 'pid_yaw_speed') and self.pid_yaw_speed:
                self.pid_yaw_speed.reset()

            # Update telemetry
            self.update_telemetry_metadata('chase_state_reset', datetime.utcnow().isoformat())
            self.update_telemetry_metadata('lateral_mode_reset', self.active_lateral_mode)
            self.update_telemetry_metadata('active_lateral_mode', self.active_lateral_mode)
            
            logger.info(f"Body velocity chase follower state reset - Mode: {self.active_lateral_mode}")
            
        except Exception as e:
            logger.error(f"Error resetting chase state: {e}")

    def activate_emergency_stop(self) -> None:
        """
        Activates emergency stop mode, setting all velocities to zero.
        """
        try:
            self.emergency_stop_active = True
            
            # Immediately set all velocities to zero
            self.set_command_field('vel_body_fwd', 0.0)
            self.set_command_field('vel_body_right', 0.0)
            self.set_command_field('vel_body_down', 0.0)
            self.set_command_field('yawspeed_deg_s', 0.0)
            
            # Update telemetry
            self.update_telemetry_metadata('emergency_stop_activated', datetime.utcnow().isoformat())
            
            logger.critical("Emergency stop activated - all velocities set to zero")
            
        except Exception as e:
            logger.error(f"Error activating emergency stop: {e}")

    def deactivate_emergency_stop(self) -> None:
        """
        Deactivates emergency stop mode, allowing normal operation to resume.
        """
        try:
            self.emergency_stop_active = False
            
            # Update telemetry
            self.update_telemetry_metadata('emergency_stop_deactivated', datetime.utcnow().isoformat())
            
            logger.info("Emergency stop deactivated - normal operation resumed")
            
        except Exception as e:
            logger.error(f"Error deactivating emergency stop: {e}")

    # ==================== Mode-Specific Utility Methods ====================
    
    def get_lateral_mode_description(self, mode: str = None) -> str:
        """
        Returns a description of the specified lateral guidance mode.
        
        Args:
            mode (str, optional): Mode to describe. If None, uses active mode.
            
        Returns:
            str: Human-readable description of the mode.
        """
        mode = mode or self.active_lateral_mode
        
        descriptions = {
            'sideslip': "Direct lateral velocity control (v_right ≠ 0, yaw_rate = 0). "
                       "Best for precision hovering, close proximity operations, confined spaces.",
            'coordinated_turn': "Turn-to-track control (v_right = 0, yaw_rate ≠ 0). "
                               "Best for forward flight efficiency, natural behavior, wind resistance."
        }
        
        return descriptions.get(mode, f"Unknown mode: {mode}")

    def force_lateral_mode(self, mode: str) -> bool:
        """
        Forces a specific lateral guidance mode, overriding auto-switching.
        
        Args:
            mode (str): Desired mode ('sideslip' or 'coordinated_turn').
            
        Returns:
            bool: True if mode switch successful, False otherwise.
        """
        try:
            if mode not in ['sideslip', 'coordinated_turn']:
                logger.error(f"Invalid lateral mode: {mode}")
                return False
            
            logger.info(f"Force switching to lateral mode: {mode}")
            self._switch_lateral_mode(mode)
            
            # Update telemetry to indicate forced mode
            self.update_telemetry_metadata('forced_lateral_mode', mode)
            self.update_telemetry_metadata('mode_force_timestamp', datetime.utcnow().isoformat())
            
            return True
            
        except Exception as e:
            logger.error(f"Error forcing lateral mode to {mode}: {e}")
            return False

    # ==================== Enhanced Tracker Data Methods ====================
    
    def _handle_target_loss_enhanced(self, target_coords: Tuple[float, float], tracker_data: TrackerOutput) -> bool:
        """
        Enhanced target loss detection with confidence analysis.
        
        Args:
            target_coords (Tuple[float, float]): Target coordinates
            tracker_data (TrackerOutput): Structured tracker data with confidence
            
        Returns:
            bool: True if target is valid, False if lost
        """
        try:
            # Use existing target loss logic first
            basic_validity = self._handle_target_loss(target_coords)

            # Enhance with confidence analysis if available (v5.7.1: configurable threshold)
            if tracker_data.confidence is not None:
                confidence_valid = tracker_data.confidence >= self.target_confidence_threshold

                if not confidence_valid:
                    logger.debug(f"Target confidence too low: {tracker_data.confidence:.2f} < {self.target_confidence_threshold}")
                    return False

            # Consider velocity information if available (v5.7.1: configurable threshold)
            if tracker_data.velocity is not None:
                # Validate that velocity is reasonable
                vx, vy = tracker_data.velocity
                velocity_magnitude = np.sqrt(vx**2 + vy**2)

                if velocity_magnitude > self.max_reasonable_target_velocity:
                    logger.debug(f"Target velocity too high: {velocity_magnitude:.2f} > {self.max_reasonable_target_velocity}")
                    return False

            return basic_validity
            
        except Exception as e:
            logger.error(f"Error in enhanced target loss detection: {e}")
            return basic_validity if 'basic_validity' in locals() else False
    
    def _handle_tracking_failure(self) -> None:
        """
        Handles complete tracking failure by applying safe fallback behavior.
        """
        try:
            logger.warning("Complete tracking failure detected - applying safe fallback")
            
            # Reduce forward velocity
            self.current_forward_velocity *= 0.5
            
            # Zero lateral commands
            self.set_command_field('vel_body_right', 0.0)
            self.set_command_field('vel_body_down', 0.0)
            self.set_command_field('yawspeed_deg_s', 0.0)
            
            # Continue with reduced forward velocity
            self.set_command_field('vel_body_fwd', self.current_forward_velocity)
            
            # Update telemetry
            self.update_telemetry_metadata('tracking_failure', datetime.utcnow().isoformat())
            
        except Exception as e:
            logger.error(f"Error handling tracking failure: {e}")
            self.activate_emergency_stop()

    # ==================== Schema-Driven Data Requirements ====================
    # 
    # NOTE: Tracker data requirements are now read from schema (follower_commands.yaml)
    # instead of being hardcoded here. This enables dynamic extensibility without
    # modifying individual follower classes.
    #
    # Schema location: configs/follower_commands.yaml -> body_velocity_chase -> required_tracker_data
    # The base class automatically loads these requirements from the profile configuration.
    #
    # No override methods needed - base class handles schema-driven data requirements ✅
