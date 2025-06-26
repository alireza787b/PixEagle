#!/usr/bin/env python3
"""
Production-Ready Drone Pursuit System v5.0 Final
================================================

Professional autonomous target tracking system with modular architecture.

Navigation Modes:
- Body Frame: Aircraft-relative navigation
- Local NED: Local tangent plane navigation  
- Global: WGS84 geodetic navigation

Command Modes:
- Body Velocity: VelocityBodyYawspeed commands
- NED Velocity: VelocityNedYaw commands
- Global Position: PositionGlobalYaw commands

File Structure (for future separation):
- interceptor_params.py: Configuration parameters
- frame_utils.py: Coordinate transformations
- telemetry_manager.py: Telemetry handling
- target_tracker.py: EKF and target tracking
- guidance_strategies.py: Control strategies
- mission_executor.py: Main mission logic
- visualization.py: 3D display

Author: Pursuit Guidance Team
Version: 5.0 Final
License: MIT
"""

# =============================================================================
# IMPORTS (will be organized per module in production)
# =============================================================================

import asyncio
import json
import logging
import math
import time
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from pathlib import Path
from typing import Dict, Optional, Tuple, Type, Any, List, Union, Callable

import matplotlib.pyplot as plt
import numpy as np
import pymap3d as pm
import yaml
from filterpy.kalman import ExtendedKalmanFilter
from filterpy.common import Q_discrete_white_noise
from simple_pid import PID
from mavsdk import System
from mavsdk.offboard import (
    OffboardError,
    PositionGlobalYaw,
    PositionNedYaw,
    VelocityNedYaw,
    VelocityBodyYawspeed,
)
from scipy import stats
from scipy.linalg import block_diag
from scipy.spatial.transform import Rotation

warnings.filterwarnings('ignore', category=UserWarning)

# =============================================================================
# FILE: interceptor_params.py
# Centralized configuration management
# =============================================================================

class InterceptionParameters:
    """
    Centralized parameter management for the entire interception system.
    Single source of truth for all configuration.
    
    Usage:
        params = InterceptionParameters()
        altitude = params.mission_takeoff_altitude
        
    Can be imported by any module:
        from interceptor_params import InterceptionParameters
    """
    
    def __init__(self):
        """Initialize all parameters with defaults."""
        
        # ===== Mission Parameters =====
        self.mission_takeoff_altitude = 5.0           # meters AGL
        self.mission_ascent_speed = -2.0             # m/s (negative = up)
        self.mission_descent_speed = 1.0             # m/s (positive = down)  
        self.mission_setpoint_freq = 20.0            # Hz
        self.mission_max_time = 300.0                # seconds
        self.mission_target_threshold = 3.0          # meters
        self.mission_hold_time = 3.0                 # seconds after reaching target
        
        # ===== Safety Limits =====
        self.safety_min_altitude = 2.0               # meters AGL
        self.safety_max_altitude = 100.0             # meters AGL
        self.safety_max_distance = 500.0             # meters from home
        self.safety_geofence_action = "RTL"          # RTL or LOITER
        self.safety_battery_min_voltage = 14.0       # volts
        self.safety_battery_critical_voltage = 13.5  # volts
        self.safety_telemetry_timeout = 5.0          # seconds
        
        # ===== Target Definition (NED relative to launch) =====
        self.target_initial_position = [30.0, 0.0, -10.0]    # [N, E, D] meters
        self.target_initial_velocity = [-1.0, 2.0, 0.0]      # [vN, vE, vD] m/s
        self.target_initial_acceleration = [0.0, 0.0, 0.0]   # [aN, aE, aD] m/s²
        
        # ===== Target Maneuvering =====
        self.target_maneuver_amplitudes = [2.0, 2.0, 0.5]    # m/s² per axis
        self.target_maneuver_frequencies = [0.1, 0.15, 0.05] # Hz per axis
        self.target_maneuver_phases = None                   # radians (None = random)
        
        # ===== Camera Configuration =====
        self.camera_mount_roll = 0.0                 # degrees
        self.camera_mount_pitch = -45.0              # degrees (negative = down)
        self.camera_mount_yaw = 0.0                  # degrees
        self.camera_has_gimbal = False               # gimbal support flag
        
        # ===== Navigation & Control =====
        self.nav_mode = "body_velocity"              # Navigation strategy mode
        # Options: "body_velocity", "ned_velocity", "global_position"
        # Future: "proportional_navigation", "augmented_pn", "optimal_guidance"
        
        self.control_position_deadband = 0.5         # meters
        self.control_yaw_deadband = 5.0              # degrees
        
        # ===== Velocity Limits =====
        self.velocity_max_horizontal = 5.0           # m/s
        self.velocity_max_vertical = 2.0             # m/s
        self.velocity_max_yaw_rate = 45.0            # deg/s (for body commands only)
        
        # ===== Predictive Guidance =====
        self.guidance_position_lead_time = 2.0       # seconds (for position modes)
        self.guidance_velocity_lead_time = 0.5       # seconds (for velocity modes)
        self.guidance_yaw_lead_time = 1.0            # seconds (yaw anticipation)
        
        # ===== PID Gains (unified for velocity control) =====
        # Used by both body and NED velocity modes
        self.pid_velocity_gains = {
            'horizontal': [0.5, 0.05, 0.1],          # [Kp, Ki, Kd]
            'vertical': [0.5, 0.02, 0.1],            # [Kp, Ki, Kd]
        }
        
        # ===== Adaptive Control =====
        self.adaptive_control_enabled = True         
        self.adaptive_gain_min = 0.3                 # minimum gain scale
        self.adaptive_gain_max = 1.5                 # maximum gain scale
        self.adaptive_distance_threshold = 20.0      # meters
        
        # ===== Extended Kalman Filter =====
        self.ekf_enabled = True
        self.ekf_process_noise_position = 0.1        # meters
        self.ekf_process_noise_velocity = 0.05       # m/s
        self.ekf_process_noise_acceleration = 0.01   # m/s²
        self.ekf_measurement_noise = 0.5             # meters
        self.ekf_outlier_threshold_sigma = 3.0       # standard deviations
        self.ekf_max_covariance = 100.0              # max before reset
        self.ekf_prediction_horizon = 5.0            # seconds
        self.ekf_miss_timeout = 5.0                  # seconds without measurement
        
        # ===== Visualization =====
        self.viz_enabled = True
        self.viz_update_rate = 10.0                  # Hz
        self.viz_path_history_length = 500           # points
        self.viz_show_predictions = True
        self.viz_show_uncertainty = True
        
        # ===== System Configuration =====
        self.system_connection = "udp://:14540"      # MAVSDK connection
        self.system_log_level = "INFO"               # logging level
        self.system_log_file = "pursuit_mission.log" # log file path
        
        # ===== Target Source Configuration =====
        self.target_source_type = "auto"             # "auto", "simulated", "camera_api"
        self.target_camera_endpoint = "http://camera-server:8080/target"
        self.target_camera_api_key = None            # API key if required
        
        # ===== GPS Reference Management =====
        self.gps_use_fixed_reference = True          # Use fixed home for conversions
        self.gps_reference_update_interval = 0.0     # seconds (0 = never update)
        
        # Derived parameters (computed from above)
        self._update_derived()
    
    def _update_derived(self):
        """Update parameters derived from primary settings."""
        self.ekf_dt = 1.0 / self.mission_setpoint_freq
        self.control_loop_period = 1.0 / self.mission_setpoint_freq
    
    @classmethod
    def from_file(cls, filepath: Path) -> 'InterceptionParameters':
        """
        Load parameters from YAML or JSON file.
        
        Example YAML format:
            mission_takeoff_altitude: 10.0
            safety_max_altitude: 150.0
            nav_mode: "ned_velocity"
        """
        instance = cls()
        
        with open(filepath, 'r') as f:
            if filepath.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        
        # Update parameters from file
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
            else:
                logging.warning(f"Unknown parameter in config: {key}")
        
        instance._update_derived()
        return instance
    
    def to_dict(self) -> Dict[str, Any]:
        """Export parameters to dictionary."""
        # Get all public attributes (not starting with _)
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
    
    def validate(self) -> List[str]:
        """
        Validate parameter consistency.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if self.safety_min_altitude >= self.safety_max_altitude:
            errors.append("Min altitude must be less than max altitude")
        
        if self.mission_takeoff_altitude < self.safety_min_altitude:
            errors.append("Takeoff altitude below minimum safety altitude")
        
        if self.nav_mode not in ["body_velocity", "ned_velocity", "global_position"]:
            errors.append(f"Invalid navigation mode: {self.nav_mode}")
        
        return errors

# =============================================================================
# FILE: frame_utils.py
# Coordinate frame transformations and reference management
# =============================================================================

class ReferenceFrameManager:
    """
    Manages coordinate transformations and reference points.
    Handles GPS drift mitigation by maintaining fixed references.
    
    Key features:
    - Fixed home reference to avoid GPS drift
    - Efficient transformation caching
    - Support for multiple reference frames
    """
    
    def __init__(self, params: InterceptionParameters):
        """Initialize frame manager."""
        self.params = params
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Camera mount rotation matrix (computed once)
        self._init_camera_transform()
        
        # Reference points
        self.home_position_geo = None  # (lat, lon, alt) - fixed reference
        self.home_position_ned = None  # (north, east, down) - always (0, 0, 0)
        self.launch_time = None
        
        # GPS drift mitigation
        self.reference_positions = {}  # Store multiple reference points if needed
        
    def _init_camera_transform(self):
        """Initialize camera to body transformation."""
        roll_rad = math.radians(self.params.camera_mount_roll)
        pitch_rad = math.radians(self.params.camera_mount_pitch)
        yaw_rad = math.radians(self.params.camera_mount_yaw)
        
        # Using scipy Rotation for robustness
        self.R_cam2body = Rotation.from_euler('xyz', [roll_rad, pitch_rad, yaw_rad]).as_matrix()
        self.R_body2cam = self.R_cam2body.T
        
        self.logger.info(f"Camera mount configured: R={roll_rad:.2f}, P={pitch_rad:.2f}, Y={yaw_rad:.2f}")
    
    def set_home_reference(self, lat: float, lon: float, alt: float):
        """
        Set fixed home reference for all conversions.
        This prevents GPS drift affecting position calculations.
        """
        self.home_position_geo = (lat, lon, alt)
        self.home_position_ned = np.array([0.0, 0.0, 0.0])
        self.launch_time = time.time()
        
        self.logger.info(f"Home reference set: {lat:.7f}°, {lon:.7f}°, {alt:.1f}m")
        
        # Store as primary reference
        self.reference_positions['home'] = {
            'geo': self.home_position_geo,
            'ned': self.home_position_ned,
            'timestamp': self.launch_time
        }
    
    def add_reference_point(self, name: str, lat: float, lon: float, alt: float):
        """Add additional reference point for future use."""
        ned = self.geodetic_to_ned(lat, lon, alt)
        self.reference_positions[name] = {
            'geo': (lat, lon, alt),
            'ned': ned,
            'timestamp': time.time()
        }
    
    # ===== NED <-> Body Transformations =====
    
    def ned_to_body(self, vector_ned: np.ndarray, yaw_rad: float) -> np.ndarray:
        """Transform vector from NED to body frame."""
        c, s = np.cos(yaw_rad), np.sin(yaw_rad)
        R = np.array([[c, s, 0],
                      [-s, c, 0],
                      [0, 0, 1]])
        return R @ vector_ned
    
    def body_to_ned(self, vector_body: np.ndarray, yaw_rad: float) -> np.ndarray:
        """Transform vector from body to NED frame."""
        c, s = np.cos(yaw_rad), np.sin(yaw_rad)
        R = np.array([[c, -s, 0],
                      [s, c, 0],
                      [0, 0, 1]])
        return R @ vector_body
    
    # ===== Camera <-> Body Transformations =====
    
    def camera_to_body(self, vector_cam: np.ndarray) -> np.ndarray:
        """Transform from camera to body frame."""
        return self.R_cam2body @ vector_cam
    
    def body_to_camera(self, vector_body: np.ndarray) -> np.ndarray:
        """Transform from body to camera frame."""
        return self.R_body2cam @ vector_body
    
    # ===== Camera <-> NED Transformations =====
    
    def camera_to_ned(self, vector_cam: np.ndarray, yaw_rad: float) -> np.ndarray:
        """Transform from camera to NED frame (two-step)."""
        vector_body = self.camera_to_body(vector_cam)
        return self.body_to_ned(vector_body, yaw_rad)
    
    def ned_to_camera(self, vector_ned: np.ndarray, yaw_rad: float) -> np.ndarray:
        """Transform from NED to camera frame (two-step)."""
        vector_body = self.ned_to_body(vector_ned, yaw_rad)
        return self.body_to_camera(vector_body)
    
    # ===== Geodetic <-> NED Transformations =====
    
    def ned_to_geodetic(self, ned_position: np.ndarray) -> Tuple[float, float, float]:
        """
        Convert NED to geodetic using fixed home reference.
        This avoids GPS drift by always using the initial home position.
        """
        if self.home_position_geo is None:
            raise ValueError("Home reference not set. Call set_home_reference first.")
        
        # Convert NED to ENU for pymap3d
        e, n, u = ned_position[1], ned_position[0], -ned_position[2]
        
        # Use fixed home reference
        lat, lon, alt = pm.enu2geodetic(
            e, n, u,
            self.home_position_geo[0],
            self.home_position_geo[1], 
            self.home_position_geo[2],
            deg=True
        )
        
        return lat, lon, alt
    
    def geodetic_to_ned(self, lat: float, lon: float, alt: float) -> np.ndarray:
        """Convert geodetic to NED using fixed home reference."""
        if self.home_position_geo is None:
            raise ValueError("Home reference not set.")
        
        # Convert to ENU
        e, n, u = pm.geodetic2enu(
            lat, lon, alt,
            self.home_position_geo[0],
            self.home_position_geo[1],
            self.home_position_geo[2],
            deg=True
        )
        
        # Convert ENU to NED
        return np.array([n, e, -u])

def normalize_angle(angle_deg: float) -> float:
    """Normalize angle to [-180, 180] degrees."""
    return ((angle_deg + 180) % 360) - 180

# =============================================================================
# FILE: telemetry_manager.py
# Robust telemetry management
# =============================================================================

@dataclass
class TelemetryData:
    """
    Comprehensive telemetry data structure.
    Provides convenient access methods for common operations.
    """
    # Geodetic position
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    altitude_amsl_m: float = 0.0
    altitude_agl_m: float = 0.0
    
    # Local position (NED from arming point - may drift)
    north_m: float = 0.0
    east_m: float = 0.0  
    down_m: float = 0.0
    
    # Velocity (NED)
    vn_m_s: float = 0.0
    ve_m_s: float = 0.0
    vd_m_s: float = 0.0
    
    # Attitude
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    yaw_rad: float = 0.0
    
    # System status
    armed: bool = False
    battery_voltage: float = 16.0
    battery_percent: float = 100.0
    gps_satellites: int = 0
    gps_fix_type: int = 0
    
    # Timestamp
    last_update: float = 0.0
    
    def is_valid(self, timeout: float = 5.0) -> bool:
        """Check if telemetry is recent and valid."""
        return (time.time() - self.last_update) < timeout
    
    def get_position_ned(self) -> np.ndarray:
        """Get position as NED array."""
        return np.array([self.north_m, self.east_m, self.down_m])
    
    def get_velocity_ned(self) -> np.ndarray:
        """Get velocity as NED array."""
        return np.array([self.vn_m_s, self.ve_m_s, self.vd_m_s])
    
    def get_ground_speed(self) -> float:
        """Get horizontal ground speed."""
        return np.hypot(self.vn_m_s, self.ve_m_s)
    
    def get_climb_rate(self) -> float:
        """Get climb rate (positive = up)."""
        return -self.vd_m_s

class TelemetryManager:
    """
    Manages telemetry subscriptions with robust error handling.
    Provides easy access to telemetry data throughout the system.
    """
    
    def __init__(self, drone: System, params: InterceptionParameters):
        """Initialize telemetry manager."""
        self.drone = drone
        self.params = params
        self.data = TelemetryData()
        self.lock = asyncio.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.running = False
        self._tasks = []
    
    async def start(self):
        """Start all telemetry subscriptions."""
        self.running = True
        self._tasks = [
            asyncio.create_task(self._position_subscription()),
            asyncio.create_task(self._velocity_subscription()),
            asyncio.create_task(self._attitude_subscription()),
            asyncio.create_task(self._battery_subscription()),
            asyncio.create_task(self._gps_subscription()),
        ]
        self.logger.info("Telemetry subscriptions started")
    
    async def stop(self):
        """Stop all subscriptions gracefully."""
        self.running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.logger.info("Telemetry subscriptions stopped")
    
    async def get_telemetry(self) -> TelemetryData:
        """Get current telemetry with validation."""
        async with self.lock:
            if not self.data.is_valid(self.params.safety_telemetry_timeout):
                raise TimeoutError("Telemetry data timeout")
            # Return copy to prevent external modification
            return TelemetryData(**self.data.__dict__)
    
    def check_safety_limits(self, home_ned: Optional[np.ndarray] = None) -> Tuple[bool, str]:
        """Check if current state is within safety limits."""
        # Altitude check
        if self.data.altitude_agl_m < self.params.safety_min_altitude:
            return False, f"Below minimum altitude: {self.data.altitude_agl_m:.1f}m"
        
        if self.data.altitude_agl_m > self.params.safety_max_altitude:
            return False, f"Above maximum altitude: {self.data.altitude_agl_m:.1f}m"
        
        # Distance check
        if home_ned is not None:
            current = self.data.get_position_ned()
            distance = np.linalg.norm(current[:2] - home_ned[:2])
            if distance > self.params.safety_max_distance:
                return False, f"Beyond geofence: {distance:.1f}m"
        
        # Battery check
        if self.data.battery_voltage < self.params.safety_battery_critical_voltage:
            return False, f"Critical battery: {self.data.battery_voltage:.1f}V"
        
        # GPS check
        if self.data.gps_satellites < 6:
            return False, f"Poor GPS: {self.data.gps_satellites} satellites"
        
        return True, "All safety checks passed"
    
    # Subscription implementations...
    async def _position_subscription(self):
        """Position updates."""
        try:
            async for position in self.drone.telemetry.position():
                if not self.running:
                    break
                async with self.lock:
                    self.data.latitude_deg = position.latitude_deg
                    self.data.longitude_deg = position.longitude_deg
                    self.data.altitude_amsl_m = position.absolute_altitude_m
                    self.data.altitude_agl_m = position.relative_altitude_m
        except Exception as e:
            self.logger.error(f"Position subscription error: {e}")
    
    async def _velocity_subscription(self):
        """Velocity and NED position updates."""
        try:
            async for pv_ned in self.drone.telemetry.position_velocity_ned():
                if not self.running:
                    break
                async with self.lock:
                    # Note: This NED position is from PX4 origin, may drift
                    self.data.north_m = pv_ned.position.north_m
                    self.data.east_m = pv_ned.position.east_m
                    self.data.down_m = pv_ned.position.down_m
                    self.data.vn_m_s = pv_ned.velocity.north_m_s
                    self.data.ve_m_s = pv_ned.velocity.east_m_s
                    self.data.vd_m_s = pv_ned.velocity.down_m_s
                    self.data.last_update = time.time()
        except Exception as e:
            self.logger.error(f"Velocity subscription error: {e}")
    
    async def _attitude_subscription(self):
        """Attitude updates."""
        try:
            async for attitude in self.drone.telemetry.attitude_euler():
                if not self.running:
                    break
                async with self.lock:
                    self.data.roll_deg = attitude.roll_deg
                    self.data.pitch_deg = attitude.pitch_deg
                    self.data.yaw_deg = attitude.yaw_deg
                    self.data.yaw_rad = math.radians(attitude.yaw_deg)
        except Exception as e:
            self.logger.error(f"Attitude subscription error: {e}")
    
    async def _battery_subscription(self):
        """Battery updates."""
        try:
            async for battery in self.drone.telemetry.battery():
                if not self.running:
                    break
                async with self.lock:
                    self.data.battery_voltage = battery.voltage_v
                    self.data.battery_percent = battery.remaining_percent * 100
        except Exception as e:
            self.logger.error(f"Battery subscription error: {e}")
    
    async def _gps_subscription(self):
        """GPS info updates."""
        try:
            async for gps_info in self.drone.telemetry.gps_info():
                if not self.running:
                    break
                async with self.lock:
                    self.data.gps_satellites = gps_info.num_satellites
                    self.data.gps_fix_type = gps_info.fix_type
        except Exception as e:
            self.logger.error(f"GPS subscription error: {e}")

# =============================================================================
# FILE: target_tracker.py
# Target tracking with EKF and target source interface
# =============================================================================

class TargetTrackingEKF:
    """
    Extended Kalman Filter for target state estimation.
    Provides easy access to predictions for any guidance strategy.
    """
    
    def __init__(self, params: InterceptionParameters):
        """Initialize EKF with parameters."""
        self.params = params
        self.dt = params.ekf_dt
        
        # 9-state EKF: [x, y, z, vx, vy, vz, ax, ay, az]
        self.ekf = ExtendedKalmanFilter(dim_x=9, dim_z=3)
        
        # Initialize matrices
        self._setup_ekf()
        
        # State tracking
        self.is_initialized = False
        self.last_measurement_time = None
        self.measurement_count = 0
        self.outlier_count = 0
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def _setup_ekf(self):
        """Setup EKF matrices."""
        # State transition (constant acceleration model)
        self.ekf.F = self._get_F(self.dt)
        
        # Measurement function (position only)
        self.ekf.h = lambda x: x[0:3]
        self.ekf.H = lambda x: np.hstack([np.eye(3), np.zeros((3, 6))])
        
        # Process noise
        self.ekf.Q = self._get_Q(self.dt)
        
        # Measurement noise
        self.ekf.R = np.eye(3) * (self.params.ekf_measurement_noise ** 2)
        
        # Initial covariance
        self.ekf.P = np.diag([10, 10, 10, 5, 5, 5, 1, 1, 1])
    
    def _get_F(self, dt: float) -> np.ndarray:
        """Get state transition matrix."""
        F = np.eye(9)
        dt2 = dt * dt / 2
        
        # Kinematic relationships
        F[0:3, 3:6] = np.eye(3) * dt      # position <- velocity
        F[0:3, 6:9] = np.eye(3) * dt2     # position <- acceleration
        F[3:6, 6:9] = np.eye(3) * dt      # velocity <- acceleration
        
        return F
    
    def _get_Q(self, dt: float) -> np.ndarray:
        """Get process noise matrix."""
        q_p = self.params.ekf_process_noise_position
        q_v = self.params.ekf_process_noise_velocity
        q_a = self.params.ekf_process_noise_acceleration
        
        # Build Q for constant acceleration model
        Q = np.zeros((9, 9))
        
        # Position block
        Q[0:3, 0:3] = np.eye(3) * q_p * dt**4 / 4
        Q[0:3, 3:6] = np.eye(3) * q_p * dt**3 / 2
        Q[3:6, 0:3] = Q[0:3, 3:6].T
        
        # Velocity block
        Q[3:6, 3:6] = np.eye(3) * q_v * dt**2
        
        # Acceleration block
        Q[6:9, 6:9] = np.eye(3) * q_a
        
        return Q
    
    def initialize(self, position: np.ndarray, 
                   velocity: Optional[np.ndarray] = None,
                   acceleration: Optional[np.ndarray] = None):
        """Initialize filter with known state."""
        self.ekf.x[0:3] = position
        if velocity is not None:
            self.ekf.x[3:6] = velocity
        if acceleration is not None:
            self.ekf.x[6:9] = acceleration
        
        self.is_initialized = True
        self.last_measurement_time = time.time()
        self.logger.info("EKF initialized with target state")
    
    def predict(self, dt: Optional[float] = None):
        """Predict next state."""
        if not self.is_initialized:
            return
        
        # Update matrices if dt changed
        if dt and dt != self.dt:
            self.ekf.F = self._get_F(dt)
            self.ekf.Q = self._get_Q(dt)
        
        self.ekf.predict()
        
        # Covariance health check
        if np.trace(self.ekf.P) > self.params.ekf_max_covariance:
            self.logger.warning("EKF covariance reset")
            self.ekf.P *= 0.1
    
    def update(self, measurement: np.ndarray) -> bool:
        """
        Update with measurement after outlier check.
        
        Args:
            measurement: Position measurement in NED
            
        Returns:
            True if measurement accepted
        """
        if not self.is_initialized:
            self.initialize(measurement)
            return True
        
        # Calculate innovation
        y = measurement - self.ekf.h(self.ekf.x)
        S = self.ekf.H(self.ekf.x) @ self.ekf.P @ self.ekf.H(self.ekf.x).T + self.ekf.R
        
        # Outlier detection (chi-squared test)
        try:
            nis = float(y.T @ np.linalg.inv(S) @ y)
            chi2_threshold = stats.chi2.ppf(
                1 - 10**(-self.params.ekf_outlier_threshold_sigma), df=3
            )
            
            if nis > chi2_threshold:
                self.outlier_count += 1
                self.logger.debug(f"Measurement rejected: NIS={nis:.1f}")
                return False
                
        except np.linalg.LinAlgError:
            self.logger.warning("Singular innovation covariance")
            return False
        
        # Accept measurement
        self.ekf.update(measurement, self.ekf.R, self.ekf.H(self.ekf.x))
        self.last_measurement_time = time.time()
        self.measurement_count += 1
        
        return True
    
    def get_state(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Get current state estimate: (position, velocity, acceleration)."""
        return (
            self.ekf.x[0:3].copy(),
            self.ekf.x[3:6].copy(),
            self.ekf.x[6:9].copy()
        )
    
    def predict_future_position(self, time_ahead: float) -> np.ndarray:
        """Predict position at future time using current state."""
        if not self.is_initialized:
            return np.zeros(3)
        
        # Kinematic prediction: p = p0 + v0*t + 0.5*a0*t²
        pos = self.ekf.x[0:3] + \
              self.ekf.x[3:6] * time_ahead + \
              0.5 * self.ekf.x[6:9] * time_ahead**2
        
        return pos.copy()
    
    def predict_trajectory(self, time_horizon: float, dt: float = 0.1) -> List[np.ndarray]:
        """Predict future trajectory."""
        if not self.is_initialized:
            return []
        
        predictions = []
        steps = int(time_horizon / dt)
        
        # Save current state
        x_saved = self.ekf.x.copy()
        P_saved = self.ekf.P.copy()
        
        # Generate predictions
        for _ in range(steps):
            self.predict(dt)
            predictions.append(self.ekf.x[0:3].copy())
        
        # Restore state
        self.ekf.x = x_saved
        self.ekf.P = P_saved
        
        return predictions
    
    def time_since_measurement(self) -> float:
        """Time elapsed since last measurement."""
        if self.last_measurement_time is None:
            return float('inf')
        return time.time() - self.last_measurement_time
    
    def get_uncertainty(self) -> Tuple[np.ndarray, float]:
        """Get position uncertainty (covariance and scalar metric)."""
        pos_cov = self.ekf.P[0:3, 0:3]
        uncertainty = np.sqrt(np.trace(pos_cov))
        return pos_cov, uncertainty

# =============================================================================
# Target Source Interface
# =============================================================================

class TargetSource(ABC):
    """
    Abstract interface for target data sources.
    All sources must provide position in camera frame.
    """
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize target source."""
        pass
    
    @abstractmethod
    async def get_measurement(self) -> Optional[Dict[str, Any]]:
        """
        Get target measurement in camera frame.
        
        Returns:
            {
                'position': np.ndarray([x, y, z]),  # Camera frame
                'timestamp': float,
                'confidence': float (0-1),
                'frame': 'camera'
            }
            or None if no target
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup target source."""
        pass

class SimulatedTargetSource(TargetSource):
    """
    Simulated target for SITL testing.
    Generates realistic target motion with measurements in camera frame.
    """
    
    def __init__(self, params: InterceptionParameters, 
                 frame_manager: ReferenceFrameManager):
        """Initialize simulated target."""
        self.params = params
        self.frame_manager = frame_manager
        
        # Target model
        self.position = np.array(params.target_initial_position)
        self.velocity = np.array(params.target_initial_velocity)
        self.acceleration = np.array(params.target_initial_acceleration)
        
        # Maneuvering
        self.amp = np.array(params.target_maneuver_amplitudes)
        self.freq = np.array(params.target_maneuver_frequencies)
        self.phase = np.array(params.target_maneuver_phases) if params.target_maneuver_phases \
                     else np.random.random(3) * 2 * np.pi
        
        # Simulation state
        self.start_time = time.time()
        self.drone_position = np.zeros(3)
        self.drone_yaw = 0.0
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def initialize(self) -> bool:
        """Initialize simulation."""
        self.logger.info("Simulated target source ready")
        return True
    
    async def get_measurement(self) -> Optional[Dict[str, Any]]:
        """Generate simulated measurement in camera frame."""
        # Update target state
        t = time.time() - self.start_time
        
        # Linear motion
        pos = self.position + self.velocity * t + 0.5 * self.acceleration * t**2
        
        # Add maneuvering
        for i in range(3):
            if self.amp[i] > 0 and self.freq[i] > 0:
                omega = 2 * np.pi * self.freq[i]
                pos[i] += -(self.amp[i] / (omega**2)) * np.sin(omega * t + self.phase[i])
        
        # Get relative position in NED
        relative_ned = pos - self.drone_position
        
        # Transform to camera frame
        pos_camera = self.frame_manager.ned_to_camera(relative_ned, self.drone_yaw)
        
        # Add measurement noise
        noise = np.random.normal(0, self.params.ekf_measurement_noise, 3)
        pos_camera += noise
        
        # Simulate confidence based on distance
        distance = np.linalg.norm(pos_camera)
        confidence = np.clip(1.0 - distance / 100.0, 0.1, 1.0)
        
        return {
            'position': pos_camera,
            'timestamp': time.time(),
            'confidence': confidence,
            'frame': 'camera'
        }
    
    def update_drone_state(self, position: np.ndarray, yaw: float):
        """Update drone state for simulation."""
        self.drone_position = position
        self.drone_yaw = yaw
    
    async def shutdown(self) -> None:
        """No cleanup needed."""
        pass

class CameraAPITargetSource(TargetSource):
    """
    Real camera API integration.
    
    To use your camera system:
    1. Implement the get_measurement method to call your API
    2. Ensure it returns position in camera frame coordinates
    3. Update endpoint and authentication as needed
    """
    
    def __init__(self, params: InterceptionParameters):
        """Initialize camera API source."""
        self.params = params
        self.endpoint = params.target_camera_endpoint
        self.api_key = params.target_camera_api_key
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def initialize(self) -> bool:
        """Initialize camera connection."""
        # TODO: Initialize your camera API connection here
        # Example:
        # self.session = aiohttp.ClientSession()
        # await self.authenticate()
        
        self.logger.info(f"Camera API target source initialized: {self.endpoint}")
        return True
    
    async def get_measurement(self) -> Optional[Dict[str, Any]]:
        """
        Get target position from camera API.
        
        Expected API response format:
        {
            "detected": true,
            "position": {"x": 10.0, "y": 5.0, "z": -3.0},  // Camera frame
            "confidence": 0.95,
            "timestamp": 1234567890.123
        }
        """
        try:
            # TODO: Implement your camera API call here
            # Example:
            # headers = {"Authorization": f"Bearer {self.api_key}"}
            # async with self.session.get(self.endpoint, headers=headers) as resp:
            #     data = await resp.json()
            
            # Placeholder for demonstration
            # Replace with actual API call
            data = {
                "detected": False,
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "confidence": 0.0
            }
            
            if not data.get("detected", False):
                return None
            
            return {
                'position': np.array([
                    data["position"]["x"],
                    data["position"]["y"],
                    data["position"]["z"]
                ]),
                'timestamp': data.get("timestamp", time.time()),
                'confidence': data.get("confidence", 1.0),
                'frame': 'camera'
            }
            
        except Exception as e:
            self.logger.error(f"Camera API error: {e}")
            return None
    
    async def shutdown(self) -> None:
        """Close camera connection."""
        # TODO: Cleanup your camera API connection
        # if hasattr(self, 'session'):
        #     await self.session.close()
        pass

def create_target_source(params: InterceptionParameters,
                        frame_manager: ReferenceFrameManager) -> TargetSource:
    """
    Factory function to create appropriate target source.
    
    Auto-detection logic:
    - If SITL connection -> SimulatedTargetSource
    - Otherwise -> CameraAPITargetSource
    """
    if params.target_source_type == "simulated":
        return SimulatedTargetSource(params, frame_manager)
    elif params.target_source_type == "camera_api":
        return CameraAPITargetSource(params)
    else:
        # Auto-detect based on connection
        if params.system_connection.startswith("udp"):
            # SITL mode
            return SimulatedTargetSource(params, frame_manager)
        else:
            # Real drone mode
            return CameraAPITargetSource(params)

# =============================================================================
# FILE: guidance_strategies.py
# Modular guidance strategies with clear naming
# =============================================================================

class GuidanceStrategy(ABC):
    """
    Base class for all guidance strategies.
    Provides common functionality and ensures consistent interface.
    """
    
    def __init__(self, params: InterceptionParameters,
                 ekf: TargetTrackingEKF,
                 frame_manager: ReferenceFrameManager):
        """Initialize guidance strategy."""
        self.params = params
        self.ekf = ekf
        self.frame_manager = frame_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        
    @abstractmethod
    async def compute_command(self,
                            drone: System,
                            telemetry: TelemetryData,
                            target_ned: np.ndarray,
                            target_velocity: Optional[np.ndarray] = None,
                            dt: float = 0.05) -> bool:
        """
        Compute and send guidance command.
        
        Args:
            drone: MAVSDK drone object
            telemetry: Current telemetry
            target_ned: Target position in NED
            target_velocity: Target velocity in NED
            dt: Time step
            
        Returns:
            True if command sent successfully
        """
        pass
    
    def get_future_target_position(self, lead_time: float) -> np.ndarray:
        """
        Get predicted target position using EKF.
        Available to all guidance strategies.
        """
        return self.ekf.predict_future_position(lead_time)
    
    def compute_desired_yaw(self, error_ned: np.ndarray,
                          target_velocity: Optional[np.ndarray] = None) -> float:
        """Compute desired yaw angle with optional lead compensation."""
        # Apply yaw lead time if velocity available
        if target_velocity is not None and self.params.guidance_yaw_lead_time > 0:
            future_error = error_ned + target_velocity * self.params.guidance_yaw_lead_time
            bearing = math.degrees(math.atan2(future_error[1], future_error[0]))
        else:
            bearing = math.degrees(math.atan2(error_ned[1], error_ned[0]))
        
        # Account for camera mount offset
        return normalize_angle(bearing - self.params.camera_mount_yaw)

class BodyVelocityGuidance(GuidanceStrategy):
    """
    Body-frame velocity guidance using VelocityBodyYawSpeed commands.
    Best for: Close-range tracking, camera-centric control, non-GPS scenarios
    
    Navigation: Body frame relative to aircraft
    Commands: VelocityBodyYawSpeed (body frame velocities with yaw rate)
    """
    
    def __init__(self, params: InterceptionParameters,
                 ekf: TargetTrackingEKF,
                 frame_manager: ReferenceFrameManager):
        """Initialize body velocity guidance."""
        super().__init__(params, ekf, frame_manager)
        
        # PID controllers for camera frame
        h_gains = params.pid_velocity_gains['horizontal']
        v_gains = params.pid_velocity_gains['vertical']
        
        self.pid_x = self._create_pid(h_gains, params.velocity_max_horizontal)
        self.pid_y = self._create_pid(h_gains, params.velocity_max_horizontal)
        self.pid_z = self._create_pid(v_gains, params.velocity_max_vertical)
        
        self.logger.info("Body velocity guidance initialized")
    
    def _create_pid(self, gains: List[float], limit: float) -> PID:
        """Create PID controller with gains and limits."""
        pid = PID(
            Kp=gains[0], Ki=gains[1], Kd=gains[2],
            setpoint=0,
            output_limits=(-limit, limit)
        )
        return pid
    
    async def compute_command(self, drone, telemetry, target_ned, target_velocity=None, dt=0.05):
        """Compute body velocity command."""
        # Get current position (use fixed reference for accuracy)
        current_ned = self.frame_manager.geodetic_to_ned(
            telemetry.latitude_deg,
            telemetry.longitude_deg,
            telemetry.altitude_amsl_m
        )
        
        # Compute error
        error_ned = target_ned - current_ned
        distance = np.linalg.norm(error_ned)
        
        # Check deadband
        if distance < self.params.control_position_deadband:
            await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
            return True
        
        # Transform error to camera frame
        error_camera = self.frame_manager.ned_to_camera(error_ned, telemetry.yaw_rad)
        
        # Adaptive gain scheduling
        if self.params.adaptive_control_enabled:
            scale = np.clip(distance / self.params.adaptive_distance_threshold,
                          self.params.adaptive_gain_min,
                          self.params.adaptive_gain_max)
            self._update_gains(scale)
        
        # PID control in camera frame
        vx_cam = self.pid_x(-error_camera[0])  # Negative because PID expects measurement
        vy_cam = self.pid_y(-error_camera[1])
        vz_cam = self.pid_z(-error_camera[2])
        
        # Transform to body frame
        vel_camera = np.array([vx_cam, vy_cam, vz_cam])
        vel_body = self.frame_manager.camera_to_body(vel_camera)
        
        # Compute yaw with rate limiting
        desired_yaw = self.compute_desired_yaw(error_ned, target_velocity)
        yaw_error = normalize_angle(desired_yaw - telemetry.yaw_deg)
        
        # Apply yaw rate limit for body commands
        if abs(yaw_error) > self.params.velocity_max_yaw_rate * dt:
            yaw_error = np.sign(yaw_error) * self.params.velocity_max_yaw_rate * dt
        
        # Convert to rate
        yaw_rate = 0 if abs(yaw_error) < self.params.control_yaw_deadband else yaw_error / dt
        
        # Send command
        try:
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(
                    float(vel_body[0]),
                    float(vel_body[1]),
                    float(vel_body[2]),
                    float(yaw_rate)
                )
            )
            return True
        except OffboardError as e:
            self.logger.error(f"Body velocity command failed: {e}")
            return False
    
    def _update_gains(self, scale: float):
        """Update PID gains with scale factor."""
        base_h = self.params.pid_velocity_gains['horizontal']
        base_v = self.params.pid_velocity_gains['vertical']
        
        self.pid_x.Kp = base_h[0] * scale
        self.pid_x.Ki = base_h[1] * scale
        self.pid_x.Kd = base_h[2] * scale
        
        self.pid_y.Kp = base_h[0] * scale
        self.pid_y.Ki = base_h[1] * scale
        self.pid_y.Kd = base_h[2] * scale
        
        self.pid_z.Kp = base_v[0] * scale
        self.pid_z.Ki = base_v[1] * scale
        self.pid_z.Kd = base_v[2] * scale

class NEDVelocityGuidance(GuidanceStrategy):
    """
    NED-frame velocity guidance using VelocityNedYaw commands.
    Best for: Medium-range tracking, geographic navigation
    
    Navigation: NED frame (North-East-Down)
    Commands: VelocityNedYaw (NED velocities with yaw angle)
    """
    
    def __init__(self, params: InterceptionParameters,
                 ekf: TargetTrackingEKF,
                 frame_manager: ReferenceFrameManager):
        """Initialize NED velocity guidance."""
        super().__init__(params, ekf, frame_manager)
        
        # PID controllers for NED frame
        h_gains = params.pid_velocity_gains['horizontal']
        v_gains = params.pid_velocity_gains['vertical']
        
        self.pid_n = self._create_pid(h_gains, params.velocity_max_horizontal)
        self.pid_e = self._create_pid(h_gains, params.velocity_max_horizontal)
        self.pid_d = self._create_pid(v_gains, params.velocity_max_vertical)
        
        self.logger.info("NED velocity guidance initialized")
    
    def _create_pid(self, gains: List[float], limit: float) -> PID:
        """Create PID controller."""
        return PID(
            Kp=gains[0], Ki=gains[1], Kd=gains[2],
            setpoint=0,
            output_limits=(-limit, limit)
        )
    
    async def compute_command(self, drone, telemetry, target_ned, target_velocity=None, dt=0.05):
        """Compute NED velocity command."""
        # Use fixed reference to avoid GPS drift
        current_ned = self.frame_manager.geodetic_to_ned(
            telemetry.latitude_deg,
            telemetry.longitude_deg,
            telemetry.altitude_amsl_m
        )
        
        # Compute error
        error_ned = target_ned - current_ned
        distance = np.linalg.norm(error_ned)
        
        # Check deadband
        if distance < self.params.control_position_deadband:
            await drone.offboard.set_velocity_ned(
                VelocityNedYaw(0, 0, 0, telemetry.yaw_deg)
            )
            return True
        
        # Adaptive gains
        if self.params.adaptive_control_enabled:
            scale = np.clip(distance / self.params.adaptive_distance_threshold,
                          self.params.adaptive_gain_min,
                          self.params.adaptive_gain_max)
            self._update_gains(scale)
        
        # PID control
        vn = self.pid_n(-error_ned[0])
        ve = self.pid_e(-error_ned[1])
        vd = self.pid_d(-error_ned[2])
        
        # Add velocity feed-forward
        if target_velocity is not None:
            ff_scale = self.params.guidance_velocity_lead_time
            vn += target_velocity[0] * ff_scale
            ve += target_velocity[1] * ff_scale
            vd += target_velocity[2] * ff_scale
        
        # Desired yaw (no rate limiting for NED commands)
        desired_yaw = self.compute_desired_yaw(error_ned, target_velocity)
        
        # Send command
        try:
            await drone.offboard.set_velocity_ned(
                VelocityNedYaw(float(vn), float(ve), float(vd), float(desired_yaw))
            )
            return True
        except OffboardError as e:
            self.logger.error(f"NED velocity command failed: {e}")
            return False
    
    def _update_gains(self, scale: float):
        """Update PID gains."""
        base_h = self.params.pid_velocity_gains['horizontal']
        base_v = self.params.pid_velocity_gains['vertical']
        
        self.pid_n.Kp = base_h[0] * scale
        self.pid_n.Ki = base_h[1] * scale
        self.pid_n.Kd = base_h[2] * scale
        
        self.pid_e.Kp = base_h[0] * scale
        self.pid_e.Ki = base_h[1] * scale
        self.pid_e.Kd = base_h[2] * scale
        
        self.pid_d.Kp = base_v[0] * scale
        self.pid_d.Ki = base_v[1] * scale
        self.pid_d.Kd = base_v[2] * scale

class GlobalPositionGuidance(GuidanceStrategy):
    """
    Global position guidance using PositionGlobalYaw commands.
    Best for: Long-range navigation, waypoint following
    
    Navigation: WGS84 geodetic coordinates
    Commands: PositionGlobalYaw (lat/lon/alt with yaw angle)
    """
    
    async def compute_command(self, drone, telemetry, target_ned, target_velocity=None, dt=0.05):
        """Compute global position command."""
        # Get predicted target position
        if self.params.guidance_position_lead_time > 0:
            predicted_ned = self.get_future_target_position(
                self.params.guidance_position_lead_time
            )
        else:
            predicted_ned = target_ned
        
        # Convert to geodetic using fixed reference
        target_lat, target_lon, target_alt = self.frame_manager.ned_to_geodetic(predicted_ned)
        
        # Compute desired yaw
        current_ned = self.frame_manager.geodetic_to_ned(
            telemetry.latitude_deg,
            telemetry.longitude_deg,
            telemetry.altitude_amsl_m
        )
        error_ned = target_ned - current_ned
        desired_yaw = self.compute_desired_yaw(error_ned, target_velocity)
        
        # Send command
        try:
            await drone.offboard.set_position_global(
                PositionGlobalYaw(
                    target_lat,
                    target_lon,
                    target_alt,
                    desired_yaw,
                    PositionGlobalYaw.AltitudeType.AMSL
                )
            )
            return True
        except OffboardError as e:
            self.logger.error(f"Global position command failed: {e}")
            return False

# Future guidance strategies can be added here
# Example template:
"""
class ProportionalNavigationGuidance(GuidanceStrategy):
    '''
    Proportional Navigation (PN) guidance law.
    Future implementation for missile-like intercept trajectories.
    '''
    
    def __init__(self, params, ekf, frame_manager):
        super().__init__(params, ekf, frame_manager)
        self.navigation_constant = 3.0  # N'
        
    async def compute_command(self, drone, telemetry, target_ned, target_velocity=None, dt=0.05):
        # Implement PN guidance law
        # 1. Compute line-of-sight rate
        # 2. Apply PN law: a_cmd = N' * V_c * omega_los
        # 3. Convert to velocity commands
        pass
"""

def create_guidance_strategy(params: InterceptionParameters,
                           ekf: TargetTrackingEKF,
                           frame_manager: ReferenceFrameManager) -> GuidanceStrategy:
    """
    Factory function to create guidance strategies.
    
    Current strategies:
    - body_velocity: Body-frame velocity control
    - ned_velocity: NED-frame velocity control  
    - global_position: Global position control
    
    Future strategies:
    - proportional_navigation: PN guidance
    - augmented_pn: Augmented PN
    - optimal_guidance: Optimal control
    """
    strategies = {
        'body_velocity': BodyVelocityGuidance,
        'ned_velocity': NEDVelocityGuidance,
        'global_position': GlobalPositionGuidance,
    }
    
    if params.nav_mode not in strategies:
        raise ValueError(f"Unknown navigation mode: {params.nav_mode}")
    
    return strategies[params.nav_mode](params, ekf, frame_manager)

# =============================================================================
# FILE: mission_executor.py
# Main mission execution logic
# =============================================================================

class MissionState(Enum):
    """Mission execution states."""
    INIT = auto()
    PREFLIGHT = auto()
    ARMING = auto()
    TAKEOFF = auto()
    PURSUIT = auto()
    HOLDING = auto()
    LANDING = auto()
    LANDED = auto()
    EMERGENCY = auto()
    FAILED = auto()

class MissionStateMachine:
    """Manages mission state transitions."""
    
    def __init__(self):
        self.state = MissionState.INIT
        self.state_start_time = time.time()
        self.state_history = []
        self.emergency_reason = None
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Valid transitions
        self.transitions = {
            MissionState.INIT: [MissionState.PREFLIGHT, MissionState.FAILED],
            MissionState.PREFLIGHT: [MissionState.ARMING, MissionState.FAILED],
            MissionState.ARMING: [MissionState.TAKEOFF, MissionState.EMERGENCY, MissionState.FAILED],
            MissionState.TAKEOFF: [MissionState.PURSUIT, MissionState.EMERGENCY, MissionState.LANDING],
            MissionState.PURSUIT: [MissionState.HOLDING, MissionState.EMERGENCY, MissionState.LANDING],
            MissionState.HOLDING: [MissionState.LANDING, MissionState.PURSUIT, MissionState.EMERGENCY],
            MissionState.LANDING: [MissionState.LANDED, MissionState.EMERGENCY],
            MissionState.LANDED: [MissionState.INIT],
            MissionState.EMERGENCY: [MissionState.LANDING, MissionState.FAILED],
            MissionState.FAILED: [MissionState.INIT]
        }
    
    def transition_to(self, new_state: MissionState, reason: str = "") -> bool:
        """Execute state transition."""
        if new_state not in self.transitions.get(self.state, []):
            self.logger.error(f"Invalid transition: {self.state} -> {new_state}")
            return False
        
        # Record history
        duration = time.time() - self.state_start_time
        self.state_history.append({
            'state': self.state.name,
            'duration': duration,
            'reason': reason
        })
        
        self.logger.info(f"State: {self.state.name} -> {new_state.name} ({reason})")
        self.state = new_state
        self.state_start_time = time.time()
        
        if new_state == MissionState.EMERGENCY:
            self.emergency_reason = reason
        
        return True

# =============================================================================
# FILE: visualization.py  
# 3D visualization for mission monitoring
# =============================================================================

class MissionVisualizer:
    """Professional 3D visualization (implementation omitted for brevity)."""
    
    def __init__(self, params: InterceptionParameters):
        self.params = params
        self.enabled = params.viz_enabled
        # Full implementation in separate file
        
    def update(self, telemetry, target_state, predictions=None, metrics=None):
        """Update visualization."""
        if not self.enabled:
            return
        # Implementation details...

# =============================================================================
# MAIN MISSION EXECUTOR
# =============================================================================

class MissionExecutor:
    """
    Main mission orchestrator.
    Coordinates all subsystems for autonomous pursuit missions.
    """
    
    def __init__(self, params: Optional[InterceptionParameters] = None):
        """Initialize mission executor."""
        # Use provided params or create defaults
        self.params = params or InterceptionParameters()
        
        # Validate parameters
        errors = self.params.validate()
        if errors:
            raise ValueError(f"Invalid parameters: {errors}")
        
        # Setup logging
        self._setup_logging()
        
        # Core components
        self.drone = None
        self.state_machine = MissionStateMachine()
        self.telemetry_manager = None
        self.frame_manager = None
        self.ekf = None
        self.guidance_strategy = None
        self.target_source = None
        self.visualizer = None
        
        # Mission data
        self.home_position_ned = None
        self.mission_start_time = None
        self.mission_stats = {}
        
        self.logger.info("Mission executor initialized")
        self.logger.info(f"Navigation mode: {self.params.nav_mode}")
    
    def _setup_logging(self):
        """Configure logging system."""
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Console handler
        console = logging.StreamHandler()
        console.setLevel(getattr(logging, self.params.system_log_level))
        
        # File handler
        handlers = [console]
        if self.params.system_log_file:
            file_handler = logging.FileHandler(self.params.system_log_file)
            file_handler.setLevel(getattr(logging, self.params.system_log_level))
            handlers.append(file_handler)
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        for handler in handlers:
            handler.setFormatter(formatter)
        
        # Configure root logger
        logging.basicConfig(level=getattr(logging, self.params.system_log_level), handlers=handlers)
    
    async def initialize_systems(self):
        """Initialize all subsystems."""
        self.logger.info("Initializing subsystems...")
        
        # Connect to drone
        self.drone = System()
        await self.drone.connect(system_address=self.params.system_connection)
        
        # Wait for connection
        async for state in self.drone.core.connection_state():
            if state.is_connected:
                self.logger.info("Drone connected")
                break
        
        # Initialize managers
        self.telemetry_manager = TelemetryManager(self.drone, self.params)
        await self.telemetry_manager.start()
        
        self.frame_manager = ReferenceFrameManager(self.params)
        
        # Initialize EKF
        if self.params.ekf_enabled:
            self.ekf = TargetTrackingEKF(self.params)
        
        # Create target source
        self.target_source = create_target_source(self.params, self.frame_manager)
        await self.target_source.initialize()
        
        # Create guidance strategy
        self.guidance_strategy = create_guidance_strategy(
            self.params, self.ekf, self.frame_manager
        )
        
        # Initialize visualization
        if self.params.viz_enabled:
            self.visualizer = MissionVisualizer(self.params)
        
        self.logger.info("All systems initialized successfully")
    
    async def run_mission(self):
        """Execute the complete mission."""
        try:
            print("\n" + "="*70)
            print("DRONE PURSUIT SYSTEM v5.0".center(70))
            print("Production Ready - Professional Autonomous Tracking".center(70))
            print("="*70 + "\n")
            
            await self.initialize_systems()
            await self._wait_for_ready()
            await self._execute_preflight()
            await self._execute_arming()
            await self._execute_takeoff()
            await self._execute_pursuit()
            await self._execute_landing()
            
        except Exception as e:
            self.logger.error(f"Mission failed: {e}", exc_info=True)
            self.state_machine.transition_to(MissionState.EMERGENCY, str(e))
            await self._handle_emergency()
        finally:
            await self._cleanup()
            self._print_mission_report()
    
    async def _wait_for_ready(self):
        """Wait for vehicle ready."""
        self.logger.info("Waiting for vehicle ready...")
        
        async for health in self.drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                self.logger.info("Vehicle is ready for flight")
                break
            await asyncio.sleep(0.5)
    
    async def _execute_preflight(self):
        """Execute preflight checks."""
        self.state_machine.transition_to(MissionState.PREFLIGHT, "Preflight checks")
        
        # Get telemetry
        telemetry = await self.telemetry_manager.get_telemetry()
        
        # Safety checks
        is_safe, reason = self.telemetry_manager.check_safety_limits()
        if not is_safe:
            raise RuntimeError(f"Preflight failed: {reason}")
        
        # Set home reference
        self.frame_manager.set_home_reference(
            telemetry.latitude_deg,
            telemetry.longitude_deg,
            telemetry.altitude_amsl_m
        )
        
        # Store home position
        self.home_position_ned = np.array([0.0, 0.0, 0.0])  # By definition
        
        # Initialize EKF with target
        if self.ekf and hasattr(self.target_source, 'position'):
            # For simulated target
            self.ekf.initialize(
                self.target_source.position,
                self.target_source.velocity,
                self.target_source.acceleration
            )
        
        self.logger.info("Preflight checks complete")
    
    async def _execute_arming(self):
        """Arm and start offboard mode."""
        self.state_machine.transition_to(MissionState.ARMING, "Arming vehicle")
        
        await self.drone.action.arm()
        
        # Start offboard
        try:
            await self.drone.offboard.set_velocity_ned(VelocityNedYaw(0, 0, 0, 0))
            await self.drone.offboard.start()
            self.logger.info("Offboard mode active")
        except OffboardError as e:
            raise RuntimeError(f"Failed to start offboard: {e}")
    
    async def _execute_takeoff(self):
        """Takeoff to target altitude."""
        self.state_machine.transition_to(MissionState.TAKEOFF, "Taking off")
        
        self.logger.info(f"Taking off to {self.params.mission_takeoff_altitude}m...")
        
        while True:
            telemetry = await self.telemetry_manager.get_telemetry()
            
            if telemetry.altitude_agl_m >= self.params.mission_takeoff_altitude:
                self.logger.info(f"Reached altitude: {telemetry.altitude_agl_m:.1f}m")
                break
            
            await self.drone.offboard.set_velocity_ned(
                VelocityNedYaw(0, 0, self.params.mission_ascent_speed, 0)
            )
            
            await asyncio.sleep(self.params.control_loop_period)
        
        # Hold position
        await self.drone.offboard.set_velocity_ned(VelocityNedYaw(0, 0, 0, 0))
        await asyncio.sleep(2.0)
    
    async def _execute_pursuit(self):
        """Main pursuit phase."""
        self.state_machine.transition_to(MissionState.PURSUIT, "Starting pursuit")
        
        self.logger.info("Pursuit phase active")
        self.mission_start_time = time.time()
        
        # Initialize stats
        self.mission_stats = {
            'max_error': 0,
            'measurements_accepted': 0,
            'measurements_rejected': 0,
            'min_battery': 100,
            'max_altitude': 0,
            'pursuit_duration': 0
        }
        
        print("\n" + "="*60)
        print("PURSUIT ACTIVE".center(60))
        print("="*60)
        
        last_time = time.time()
        
        while self.state_machine.state == MissionState.PURSUIT:
            loop_start = time.time()
            dt = loop_start - last_time
            last_time = loop_start
            
            try:
                # Get telemetry
                telemetry = await self.telemetry_manager.get_telemetry()
                
                # Update simulated target
                if isinstance(self.target_source, SimulatedTargetSource):
                    current_ned = self.frame_manager.geodetic_to_ned(
                        telemetry.latitude_deg,
                        telemetry.longitude_deg,
                        telemetry.altitude_amsl_m
                    )
                    self.target_source.update_drone_state(current_ned, telemetry.yaw_rad)
                
                # Get target measurement
                measurement = await self.target_source.get_measurement()
                
                if measurement is None:
                    self.logger.warning("No target measurement")
                    continue
                
                # Process measurement
                target_cam = measurement['position']
                target_ned_relative = self.frame_manager.camera_to_ned(
                    target_cam, telemetry.yaw_rad
                )
                
                # Get absolute target position
                current_ned = self.frame_manager.geodetic_to_ned(
                    telemetry.latitude_deg,
                    telemetry.longitude_deg,
                    telemetry.altitude_amsl_m
                )
                target_ned = current_ned + target_ned_relative
                
                # Apply EKF
                if self.ekf:
                    self.ekf.predict(dt)
                    
                    if self.ekf.update(target_ned):
                        self.mission_stats['measurements_accepted'] += 1
                    else:
                        self.mission_stats['measurements_rejected'] += 1
                    
                    # Get filtered state
                    target_pos, target_vel, _ = self.ekf.get_state()
                else:
                    target_pos = target_ned
                    target_vel = np.zeros(3)
                
                # Check constraints
                elapsed = time.time() - self.mission_start_time
                if elapsed > self.params.mission_max_time:
                    self.logger.info("Mission time limit reached")
                    break
                
                # Safety check
                is_safe, reason = self.telemetry_manager.check_safety_limits(
                    self.home_position_ned
                )
                if not is_safe:
                    self.logger.warning(f"Safety limit: {reason}")
                    if "battery" in reason.lower():
                        break
                
                # Calculate error
                error = np.linalg.norm(target_pos - current_ned)
                self.mission_stats['max_error'] = max(self.mission_stats['max_error'], error)
                
                # Check if target reached
                if error <= self.params.mission_target_threshold:
                    self.logger.info(f"Target reached! Distance: {error:.2f}m")
                    self.state_machine.transition_to(MissionState.HOLDING, "Target acquired")
                    break
                
                # Send guidance command
                success = await self.guidance_strategy.compute_command(
                    self.drone, telemetry, target_pos, target_vel, dt
                )
                
                if not success:
                    self.logger.warning("Guidance command failed")
                
                # Update stats
                self.mission_stats['min_battery'] = min(
                    self.mission_stats['min_battery'],
                    telemetry.battery_percent
                )
                self.mission_stats['max_altitude'] = max(
                    self.mission_stats['max_altitude'],
                    telemetry.altitude_agl_m
                )
                
                # Terminal display
                speed = telemetry.get_ground_speed()
                closing_rate = -np.dot(
                    (target_pos - current_ned)[:2] / error,
                    telemetry.get_velocity_ned()[:2]
                ) if error > 0 else 0
                
                eta = error / closing_rate if closing_rate > 0.1 else float('inf')
                
                print(f"\r{'Time:':<6} {elapsed:>6.1f}s | "
                      f"{'Dist:':<5} {error:>5.1f}m | "
                      f"{'Speed:':<6} {speed:>4.1f}m/s | "
                      f"{'Close:':<6} {closing_rate:>4.1f}m/s | "
                      f"{'ETA:':<4} {eta:>5.1f}s | "
                      f"{'Bat:':<4} {telemetry.battery_percent:>3.0f}%",
                      end='', flush=True)
                
            except Exception as e:
                self.logger.error(f"Pursuit error: {e}")
                raise
            
            # Maintain loop rate
            loop_duration = time.time() - loop_start
            if loop_duration < self.params.control_loop_period:
                await asyncio.sleep(self.params.control_loop_period - loop_duration)
        
        self.mission_stats['pursuit_duration'] = time.time() - self.mission_start_time
        print("\n" + "="*60)
    
    async def _execute_landing(self):
        """Execute landing sequence."""
        # Hold if target reached
        if self.state_machine.state == MissionState.HOLDING:
            self.logger.info(f"Holding for {self.params.mission_hold_time}s...")
            await self.drone.offboard.set_velocity_ned(VelocityNedYaw(0, 0, 0, 0))
            await asyncio.sleep(self.params.mission_hold_time)
        
        self.state_machine.transition_to(MissionState.LANDING, "Landing")
        
        if self.params.safety_geofence_action == "RTL":
            await self.drone.offboard.stop()
            await self.drone.action.return_to_launch()
            self.logger.info("Return to launch initiated")
        else:
            # Controlled descent
            while True:
                telemetry = await self.telemetry_manager.get_telemetry()
                if telemetry.altitude_agl_m < 0.5:
                    break
                
                await self.drone.offboard.set_velocity_ned(
                    VelocityNedYaw(0, 0, self.params.mission_descent_speed, 0)
                )
                await asyncio.sleep(self.params.control_loop_period)
            
            await self.drone.offboard.stop()
            await self.drone.action.land()
        
        self.state_machine.transition_to(MissionState.LANDED, "Landed safely")
    
    async def _handle_emergency(self):
        """Handle emergency situations."""
        self.logger.error(f"EMERGENCY: {self.state_machine.emergency_reason}")
        
        try:
            await self.drone.offboard.stop()
            await self.drone.action.return_to_launch()
            self.logger.info("Emergency RTL executed")
        except:
            try:
                await self.drone.action.land()
            except:
                pass
    
    async def _cleanup(self):
        """Clean up resources."""
        self.logger.info("Cleaning up...")
        
        if self.telemetry_manager:
            await self.telemetry_manager.stop()
        
        if self.target_source:
            await self.target_source.shutdown()
        
        if self.visualizer and self.visualizer.enabled:
            plt.ioff()
            plt.show()
    
    def _print_mission_report(self):
        """Print comprehensive mission report."""
        print("\n" + "="*70)
        print("MISSION REPORT".center(70))
        print("="*70)
        
        # State summary
        total_time = sum(s['duration'] for s in self.state_machine.state_history)
        print(f"\n{'Mission Duration:':<30} {total_time:>10.1f} seconds")
        print(f"{'Final State:':<30} {self.state_machine.state.name:>10}")
        print(f"{'Navigation Mode:':<30} {self.params.nav_mode:>10}")
        
        # Performance metrics
        if self.mission_stats:
            print(f"\n{'Performance Metrics':^70}")
            print("-"*70)
            print(f"{'Maximum Position Error:':<30} {self.mission_stats.get('max_error', 0):>10.2f} meters")
            print(f"{'Pursuit Duration:':<30} {self.mission_stats.get('pursuit_duration', 0):>10.1f} seconds")
            print(f"{'Minimum Battery:':<30} {self.mission_stats.get('min_battery', 0):>10.0f} %")
            
            # EKF performance
            if self.ekf and self.mission_stats.get('measurements_accepted', 0) > 0:
                total_meas = (self.mission_stats['measurements_accepted'] + 
                            self.mission_stats['measurements_rejected'])
                accept_rate = 100 * self.mission_stats['measurements_accepted'] / total_meas
                print(f"\n{'EKF Measurement Accept Rate:':<30} {accept_rate:>10.1f} %")
        
        # Result
        print("\n" + "="*70)
        if self.state_machine.state == MissionState.LANDED:
            if self.mission_stats.get('max_error', float('inf')) <= self.params.mission_target_threshold:
                print("MISSION SUCCESS - Target Intercepted".center(70))
            else:
                print("MISSION COMPLETE".center(70))
        else:
            print(f"MISSION INCOMPLETE - {self.state_machine.state.name}".center(70))
        print("="*70 + "\n")

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def main():
    """Main entry point."""
    # Create parameters (can load from file in future)
    params = InterceptionParameters()
    
    # Create and run mission
    executor = MissionExecutor(params)
    await executor.run_mission()

if __name__ == "__main__":
    asyncio.run(main())
