#!/usr/bin/env python3
"""
Production-Ready Drone Pursuit System v5.2 Fixed
================================================

Professional autonomous target tracking system with GPS drift mitigation.
Fixed EKF implementation, visualization, and acceleration handling.

Guidance Modes:
1. local_ned_velocity: Uses PX4 local NED (non-GPS compatible, but may drift)
2. global_ned_velocity: Recalculates NED from geodetic (GPS drift mitigation)  
3. body_velocity: Body frame control (uses global reference)
4. global_position: Direct position commands to PX4

Key Fixes in v5.2:
- Fixed visualization to work properly with tkinter
- Corrected EKF process noise and uncertainty growth
- Fixed acceleration model (excludes gravity)
- Added real-time visualization during all phases
- Added JPEG capture for mission reports

Author: Pursuit Guidance Team
Version: 5.2 Fixed Production
License: MIT
"""

# =============================================================================
# IMPORTS
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

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Circle
import matplotlib.patches as mpatches
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
from collections import deque
import os
from datetime import datetime

warnings.filterwarnings('ignore', category=UserWarning)

# =============================================================================
# FILE: interceptor_params.py
# Centralized configuration management
# =============================================================================

class InterceptionParameters:
    """
    Centralized parameter management for the entire system.
    All configuration in one place for easy access and modification.
    
    Usage:
        params = InterceptionParameters()
        altitude = params.mission_takeoff_altitude
    """
    
    def __init__(self):
        """Initialize all parameters with defaults."""
        
        # ===== Mission Parameters =====
        self.mission_takeoff_altitude = 5.0           # meters AGL
        self.mission_ascent_speed = -2.0             # m/s (negative = up)
        self.mission_descent_speed = 1.0             # m/s (positive = down)  
        self.mission_setpoint_freq = 10.0            # Hz
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
        self.target_initial_position = [30.0, 30.0, -20.0]    # [N, E, D] meters
        self.target_initial_velocity = [1.0, 0.0, 0.0]      # [vN, vE, vD] m/s
        self.target_initial_acceleration = [0.0, 0.0, 0]   # [aN, aE, aD] m/s² (vehicle only, no gravity!)
        
        # ===== Target Maneuvering =====
        self.target_maneuver_amplitudes = [0.0, 0.0, 0.0]    # m/s² per axis
        self.target_maneuver_frequencies = [0.0, 0.0, 0.0] # Hz per axis
        self.target_maneuver_phases = None                   # radians (None = random)
        
        # ===== Camera Configuration =====
        self.camera_mount_roll = 0.0                 # degrees
        self.camera_mount_pitch = 0.0             # degrees (negative = down)
        self.camera_mount_yaw = 0.0                  # degrees
        self.camera_has_gimbal = False               # gimbal support flag
        
        # ===== Guidance Mode Selection =====
        self.guidance_mode = "global_ned_velocity"    
        # Options:
        # - "local_ned_velocity": Uses PX4 local NED (works without GPS but may drift)
        # - "global_ned_velocity": Recalculates from geodetic (avoids GPS drift)
        # - "body_velocity": Body frame control
        # - "global_position": Direct position commands
        
        # ===== Reference Frame Settings =====
        self.reference_use_current_position = False  # True: use current drone pos as ref
                                                    # False: use fixed home as ref
        self.reference_update_rate = 0.0             # How often to update reference (0 = never)
        
        # ===== Control Parameters =====
        self.control_position_deadband = 1.0         # meters
        self.control_yaw_deadband = 5.0              # degrees
        
        # ===== Velocity Limits =====
        self.velocity_max_horizontal = 8.0           # m/s
        self.velocity_max_vertical = 2.0             # m/s
        self.velocity_max_yaw_rate = 45.0            # deg/s (for body commands only)
        
        # ===== Predictive Guidance =====
        self.guidance_position_lead_time = 1.0       # seconds (for position modes)
        self.guidance_velocity_lead_time = 0.5       # seconds (for velocity modes)
        self.guidance_yaw_lead_time = 0.5            # seconds (yaw anticipation)
        
        # ===== PID Gains (unified for velocity control) =====
        self.pid_velocity_gains = {
            'horizontal': [0.8, 0.1, 0.2],  # Increased P for faster response
            'vertical': [1.0, 0.15, 0.3],   # More aggressive vertical control
        }
        self.pid_integral_limit = 2.0  # Maximum integral term contribution

        
        # ===== Adaptive Control =====
        self.adaptive_control_enabled = True         
        self.adaptive_gain_min = 0.3                 # minimum gain scale
        self.adaptive_gain_max = 1.5                 # maximum gain scale
        self.adaptive_distance_threshold = 20.0      # meters
        
        # ===== Extended Kalman Filter =====
        self.ekf_enabled = True
        self.ekf_estimate_acceleration = False  # Use 6-state model by default
        self.ekf_process_noise_position = 0.1      # meters (reduced from 0.01)
        self.ekf_process_noise_velocity = 0.5       # m/s (reduced from 0.1)
        self.ekf_process_noise_acceleration = 2.0    # m/s² (reduced from 0.5)
        self.ekf_measurement_noise = 0.5             # meters
        self.ekf_outlier_threshold_sigma = 3.5       # standard deviations
        self.ekf_max_covariance = 2500.0             # max before reset
        self.ekf_prediction_horizon = 2.0            # seconds
        self.ekf_miss_timeout = 2.0                  # seconds without measurement
        self.ekf_measurement_delay = 0.05  # seconds - typical camera processing delay

        
        # ===== Visualization =====
        self.viz_enabled = True
        self.viz_update_rate = 1.0                   # Hz (reduced for cleaner display)
        self.viz_path_history_length = 200           # points (reduced for clarity)
        self.viz_show_predictions = True
        self.viz_show_uncertainty = True
        self.viz_history_length = 1000               # Maximum history points
        self.save_mission_report = True              # Save mission report and plots
        
        # ===== System Configuration =====
        self.system_connection = "udp://:14540"      # MAVSDK connection
        self.system_log_level = "INFO"               # logging level
        self.system_log_file = "pursuit_mission.log" # log file path
        
        # ===== Target Source Configuration =====
        self.target_source_type = "auto"             # "auto", "simulated", "camera_api"
        self.target_camera_endpoint = "http://camera-server:8080/target"
        self.target_camera_api_key = None            # API key if required
        
        # Derived parameters
        self._update_derived()
    
    def _update_derived(self):
        """Update parameters derived from primary settings."""
        self.ekf_dt = 1.0 / self.mission_setpoint_freq
        self.control_loop_period = 1.0 / self.mission_setpoint_freq
    
    @classmethod
    def from_file(cls, filepath: Path) -> 'InterceptionParameters':
        """Load parameters from YAML or JSON file."""
        instance = cls()
        
        with open(filepath, 'r') as f:
            if filepath.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
            else:
                logging.warning(f"Unknown parameter in config: {key}")
        
        instance._update_derived()
        return instance
    
    def validate(self) -> List[str]:
        """Validate parameter consistency."""
        errors = []
        
        if self.safety_min_altitude >= self.safety_max_altitude:
            errors.append("Min altitude must be less than max altitude")
        
        if self.mission_takeoff_altitude < self.safety_min_altitude:
            errors.append("Takeoff altitude below minimum safety altitude")
        
        valid_modes = ["local_ned_velocity", "global_ned_velocity", 
                      "body_velocity", "global_position"]
        if self.guidance_mode not in valid_modes:
            errors.append(f"Invalid guidance mode: {self.guidance_mode}")
        
        return errors

# =============================================================================
# FILE: frame_utils.py
# Coordinate frame transformations and reference management
# =============================================================================

class ReferenceFrameManager:
    """
    Manages coordinate transformations and reference points.
    Critical for GPS drift mitigation.
    """
    
    def __init__(self, params: InterceptionParameters):
        """Initialize frame manager."""
        self.params = params
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Camera mount rotation matrix
        self._init_camera_transform()
        
        # Reference points
        self.home_position_geo = None  # (lat, lon, alt) - fixed at launch
        self.home_position_ned = np.array([0.0, 0.0, 0.0])  # By definition
        
        # Current reference for relative calculations
        self.current_reference_geo = None
        self.reference_update_time = 0
        
        self.logger.info("Reference frame manager initialized")
    
    def _init_camera_transform(self):
        """Initialize camera to body transformation."""
        roll_rad = math.radians(self.params.camera_mount_roll)
        pitch_rad = math.radians(self.params.camera_mount_pitch)
        yaw_rad = math.radians(self.params.camera_mount_yaw)
        
        self.R_cam2body = Rotation.from_euler('xyz', [roll_rad, pitch_rad, yaw_rad]).as_matrix()
        self.R_body2cam = self.R_cam2body.T
    
    def set_home_reference(self, lat: float, lon: float, alt: float):
        """Set fixed home reference (called once at launch)."""
        self.home_position_geo = (lat, lon, alt)
        self.current_reference_geo = (lat, lon, alt)  # Initialize current ref
        self.reference_update_time = time.time()
        
        self.logger.info(f"Home reference set: {lat:.7f}°, {lon:.7f}°, {alt:.1f}m")
    
    def update_current_reference(self, lat: float, lon: float, alt: float):
        """Update current reference position (for dynamic referencing)."""
        if self.params.reference_use_current_position:
            self.current_reference_geo = (lat, lon, alt)
            self.reference_update_time = time.time()
    
    def get_reference_position(self) -> Tuple[float, float, float]:
        """
        Get reference position for calculations.
        Returns current reference if using dynamic, otherwise home.
        """
        if self.params.reference_use_current_position and self.current_reference_geo:
            return self.current_reference_geo
        else:
            return self.home_position_geo
    
    # ===== Frame Transformations =====
    
    def ned_to_body(self, vector_ned: np.ndarray, yaw_rad: float) -> np.ndarray:
        """Transform from NED to body frame."""
        c, s = np.cos(yaw_rad), np.sin(yaw_rad)
        R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        return R @ vector_ned
    
    def body_to_ned(self, vector_body: np.ndarray, yaw_rad: float) -> np.ndarray:
        """Transform from body to NED frame."""
        c, s = np.cos(yaw_rad), np.sin(yaw_rad)
        R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        return R @ vector_body
    
    def camera_to_body(self, vector_cam: np.ndarray) -> np.ndarray:
        """Transform from camera to body frame."""
        return self.R_cam2body @ vector_cam
    
    def body_to_camera(self, vector_body: np.ndarray) -> np.ndarray:
        """Transform from body to camera frame."""
        return self.R_body2cam @ vector_body
    
    def camera_to_ned(self, vector_cam: np.ndarray, yaw_rad: float) -> np.ndarray:
        """Transform from camera to NED frame."""
        vector_body = self.camera_to_body(vector_cam)
        return self.body_to_ned(vector_body, yaw_rad)
    
    def ned_to_camera(self, vector_ned: np.ndarray, yaw_rad: float) -> np.ndarray:
        """Transform from NED to camera frame."""
        vector_body = self.ned_to_body(vector_ned, yaw_rad)
        return self.body_to_camera(vector_body)
    
    def ned_to_geodetic(self, ned_position: np.ndarray, 
                       reference: Optional[Tuple[float, float, float]] = None) -> Tuple[float, float, float]:
        """
        Convert NED to geodetic.
        
        Args:
            ned_position: Position in NED
            reference: Reference point (uses get_reference_position if None)
        """
        if reference is None:
            reference = self.get_reference_position()
        
        if reference is None:
            raise ValueError("No reference position set")
        
        # Convert NED to ENU for pymap3d
        e, n, u = ned_position[1], ned_position[0], -ned_position[2]
        
        lat, lon, alt = pm.enu2geodetic(
            e, n, u,
            reference[0], reference[1], reference[2],
            deg=True
        )
        
        return lat, lon, alt
    
    def geodetic_to_ned(self, lat: float, lon: float, alt: float,
                       reference: Optional[Tuple[float, float, float]] = None) -> np.ndarray:
        """
        Convert geodetic to NED.
        
        Args:
            lat, lon, alt: Geodetic coordinates
            reference: Reference point (uses get_reference_position if None)
        """
        if reference is None:
            reference = self.get_reference_position()
        
        if reference is None:
            raise ValueError("No reference position set")
        
        # Convert to ENU
        e, n, u = pm.geodetic2enu(
            lat, lon, alt,
            reference[0], reference[1], reference[2],
            deg=True
        )
        
        # Convert ENU to NED
        return np.array([n, e, -u])

def normalize_angle(angle_deg: float) -> float:
    """Normalize angle to [-180, 180] degrees."""
    return ((angle_deg + 180) % 360) - 180

# =============================================================================
# FILE: telemetry_manager.py
# Telemetry management with easy access
# =============================================================================

@dataclass
class TelemetryData:
    """Comprehensive telemetry data structure."""
    # Geodetic position
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    altitude_amsl_m: float = 0.0
    altitude_agl_m: float = 0.0
    
    # Local position (NED from PX4 origin - may drift!)
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
        """Get PX4 local position (may drift!)."""
        return np.array([self.north_m, self.east_m, self.down_m])
    
    def get_velocity_ned(self) -> np.ndarray:
        """Get velocity as NED array."""
        return np.array([self.vn_m_s, self.ve_m_s, self.vd_m_s])
    
    def get_ground_speed(self) -> float:
        """Get horizontal ground speed."""
        return np.hypot(self.vn_m_s, self.ve_m_s)

class TelemetryManager:
    """Manages telemetry subscriptions with robust error handling."""
    
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
            return TelemetryData(**self.data.__dict__)
    
    def check_safety_limits(self, home_ned: Optional[np.ndarray] = None) -> Tuple[bool, str]:
        """Check if current state is within safety limits."""
        # Altitude check
        if self.data.altitude_agl_m < self.params.safety_min_altitude:
            return False, f"Below minimum altitude: {self.data.altitude_agl_m:.1f}m"
        
        if self.data.altitude_agl_m > self.params.safety_max_altitude:
            return False, f"Above maximum altitude: {self.data.altitude_agl_m:.1f}m"
        
        # Distance check (using PX4 local position)
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
    
    # Subscription methods...
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
                    # WARNING: This NED position is from PX4 origin and may drift!
                    self.data.north_m = pv_ned.position.north_m
                    self.data.east_m = pv_ned.position.east_m
                    self.data.down_m = pv_ned.position.down_m
                    self.data.vn_m_s = pv_ned.velocity.north_m_s
                    self.data.ve_m_s = pv_ned.velocity.east_m_s
                    self.data.vd_m_s = pv_ned.velocity.down_m_s
                    self.data.last_update = time.time()
                    if hasattr(self, 'visualizer') and self.visualizer:
                        self.visualizer.telemetry_times.append(time.time())
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
                    # Fix: remaining_percent is already 0-1, multiply by 100
                    self.data.battery_percent = battery.remaining_percent * 100.0
                    # Clamp to reasonable values
                    self.data.battery_percent = np.clip(self.data.battery_percent, 0, 100)
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
# FILE: target_tracker.py - FIXED EKF IMPLEMENTATION
# =============================================================================

class TargetTrackingEKF:
    """
    Extended Kalman Filter for robust target tracking.
    Fixed implementation with proper process noise and acceleration model.
    """
    
    def __init__(self, params: InterceptionParameters):
        """Initialize EKF."""
        self.params = params
        self.dt = params.ekf_dt
        
        # Add option for reduced state model
        self.use_acceleration = params.ekf_estimate_acceleration if hasattr(params, 'ekf_estimate_acceleration') else False
        
        if self.use_acceleration:
            # 9-state EKF: [x, y, z, vx, vy, vz, ax, ay, az]
            self.ekf = ExtendedKalmanFilter(dim_x=9, dim_z=3)
        else:
            # 6-state EKF: [x, y, z, vx, vy, vz] - more stable
            self.ekf = ExtendedKalmanFilter(dim_x=6, dim_z=3)

        self.last_reset_time = 0.0  # Track last reset warning time
        self.init_time = time.time()  # Track filter initialization time
        
        
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
        if self.use_acceleration:
            self.ekf.x = np.zeros(9)
            self.ekf.F = self._get_F(self.dt)
            def h_func(x):
                return x[0:3]
            def h_jacobian(x):
                H = np.zeros((3, 9))
                H[0:3, 0:3] = np.eye(3)
                return H
            self.ekf.hx = h_func
            self.ekf.HJacobian = h_jacobian
            self.ekf.Q = self._get_Q(self.dt)
            self.ekf.R = np.eye(3) * (self.params.ekf_measurement_noise ** 2)
            self.ekf.P = np.diag([1.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.1, 0.1, 0.1])
        else:
            self.ekf.x = np.zeros(6)
            self.ekf.F = self._get_F(self.dt)
            def h_func(x):
                return x[0:3]
            def h_jacobian(x):
                H = np.zeros((3, 6))
                H[0:3, 0:3] = np.eye(3)
                return H
            self.ekf.hx = h_func
            self.ekf.HJacobian = h_jacobian
            self.ekf.Q = self._get_Q(self.dt)
            self.ekf.R = np.eye(3) * (self.params.ekf_measurement_noise ** 2)
            self.ekf.P = np.diag([1.0, 1.0, 1.0, 0.5, 0.5, 0.5])
    
    def _get_F(self, dt: float) -> np.ndarray:
        """Get state transition matrix."""
        if self.use_acceleration:
            # Original 9-state model
            F = np.eye(9)
            dt2 = dt * dt / 2
            F[0:3, 3:6] = np.eye(3) * dt
            F[0:3, 6:9] = np.eye(3) * dt2
            F[3:6, 6:9] = np.eye(3) * dt
        else:
            # 6-state constant velocity model
            F = np.eye(6)
            F[0:3, 3:6] = np.eye(3) * dt
        
        return F
    
    def _get_Q(self, dt: float) -> np.ndarray:
        """Get process noise matrix for EKF (6 or 9 state)."""
        if self.use_acceleration:
            # 9-state: [x, y, z, vx, vy, vz, ax, ay, az]
            q_acc_horizontal = self.params.ekf_process_noise_acceleration if hasattr(self.params, 'ekf_process_noise_acceleration') else 2.0
            q_acc_vertical = self.params.ekf_process_noise_acceleration if hasattr(self.params, 'ekf_process_noise_acceleration') else 0.5

            Q_single_axis_h = self._get_Q_single_axis(dt, q_acc_horizontal)
            Q_single_axis_v = self._get_Q_single_axis(dt, q_acc_vertical)

            # Compose block-diagonal for x/y/z
            Q = np.zeros((9, 9))
            # X axis (horizontal)
            Q[0:3, 0:3] = Q_single_axis_h
            # Y axis (horizontal)
            Q[3:6, 3:6] = Q_single_axis_h
            # Z axis (vertical)
            Q[6:9, 6:9] = Q_single_axis_v
            return Q
        else:
            # 6-state: [x, y, z, vx, vy, vz]
            q_pos = self.params.ekf_process_noise_position if hasattr(self.params, 'ekf_process_noise_position') else 0.1
            q_vel = self.params.ekf_process_noise_velocity if hasattr(self.params, 'ekf_process_noise_velocity') else 0.5
            Q = np.zeros((6, 6))
            Q[0:3, 0:3] = np.eye(3) * q_pos * dt
            Q[3:6, 3:6] = np.eye(3) * q_vel * dt
            return Q

    def _get_Q_single_axis(self, dt: float, q: float) -> np.ndarray:
        """Get process noise for single axis using exact discretization."""
        # For constant acceleration model with white noise jerk
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt3 * dt
        dt5 = dt4 * dt
        
        return q * np.array([
            [dt5/20, dt4/8,  dt3/6],
            [dt4/8,  dt3/3,  dt2/2],
            [dt3/6,  dt2/2,  dt]
        ])
    
    def initialize(self, position: np.ndarray, 
                   velocity: Optional[np.ndarray] = None,
                   acceleration: Optional[np.ndarray] = None):
        """Initialize filter with known state."""
        self.ekf.x[0:3] = position
        if velocity is not None:
            self.ekf.x[3:6] = velocity
        if self.use_acceleration and acceleration is not None:
            self.ekf.x[6:9] = acceleration
        self.is_initialized = True
        self.last_measurement_time = time.time()
        self.logger.info(f"EKF initialized at position: {position}")
    
    def predict(self, dt: Optional[float] = None):
        """Predict next state with improved covariance management."""
        if not self.is_initialized:
            return
        
        if dt and abs(dt - self.dt) > 0.001:
            self.ekf.F = self._get_F(dt)
            self.ekf.Q = self._get_Q(dt)
        
        self.ekf.predict()
        
        # Much more conservative covariance limiting
        filter_age = time.time() - self.init_time
        if self.use_acceleration:
            pos_indices = [0, 1, 2]
            vel_indices = [3, 4, 5]
            acc_indices = [6, 7, 8]
            identity = np.eye(9)
        else:
            pos_indices = [0, 1, 2]
            vel_indices = [3, 4, 5]
            identity = np.eye(6)
        
        # Gradually increase allowed uncertainty
        if filter_age < 10.0:
            max_pos_variance = 100.0   # 10m standard deviation
            max_vel_variance = 25.0    # 5m/s standard deviation
        elif filter_age < 60.0:
            max_pos_variance = 400.0   # 20m standard deviation
            max_vel_variance = 100.0   # 10m/s standard deviation
        else:
            max_pos_variance = 900.0   # 30m standard deviation
            max_vel_variance = 225.0   # 15m/s standard deviation
        
        # Check individual axes
        pos_variances = np.diag(self.ekf.P)[0:3]
        vel_variances = np.diag(self.ekf.P)[3:6]
        
        needs_reset = False
        
        # Soft limit - reduce variance gradually
        for i in range(3):
            if pos_variances[i] > max_pos_variance:
                # Gradually reduce instead of hard reset
                self.ekf.P[i, i] = max_pos_variance * 0.9
                needs_reset = True
            if vel_variances[i] > max_vel_variance:
                self.ekf.P[i+3, i+3] = max_vel_variance * 0.9
                needs_reset = True
        
        if needs_reset:
            # Only log once per 5 seconds to reduce spam
            current_time = time.time()
            if current_time - self.last_reset_time > 5.0:
                self.logger.debug(
                    f"EKF covariance limited: max_pos_std={np.sqrt(np.max(pos_variances)):.1f}m, "
                    f"max_vel_std={np.sqrt(np.max(vel_variances)):.1f}m/s"
                )
                self.last_reset_time = current_time
            
            # Ensure covariance remains symmetric and positive definite
            self.ekf.P = 0.5 * (self.ekf.P + self.ekf.P.T)
            self.ekf.P += identity * 1e-6
    
    
    def update(self, measurement: np.ndarray) -> bool:
        """Update with measurement after outlier check."""
        if not self.is_initialized:
            self.initialize(measurement)
            return True
        
        # Ensure measurement is 1D array
        z = measurement.flatten()
        
        # Calculate innovation
        y = z - self.ekf.hx(self.ekf.x)
        H = self.ekf.HJacobian(self.ekf.x)
        
        # Adaptive measurement noise based on innovation
        innovation_norm = np.linalg.norm(y)
        if innovation_norm > 5.0:  # Large innovation suggests higher noise
            R_adaptive = self.ekf.R * (1 + innovation_norm / 10.0)
        else:
            R_adaptive = self.ekf.R
        
        S = H @ self.ekf.P @ H.T + R_adaptive
        
        # More robust outlier detection
        try:
            nis = float(y.T @ np.linalg.inv(S) @ y)
            
            # Adaptive threshold based on filter convergence
            if self.measurement_count < 10:
                chi2_threshold = stats.chi2.ppf(0.999, df=3)  # More permissive initially
            else:
                chi2_threshold = stats.chi2.ppf(0.997, df=3)
            
            if nis > chi2_threshold:
                self.outlier_count += 1
                # Increase process noise after outlier to help filter adapt
                self.ekf.Q = self.ekf.Q * 1.5
                self.logger.debug(f"Measurement rejected - NIS: {nis:.2f}")
                return False
                
        except np.linalg.LinAlgError:
            self.logger.warning("Singular innovation covariance")
            return False
        
        # Update with adaptive R
        self.ekf.R = R_adaptive
        self.ekf.update(z, self.ekf.HJacobian, self.ekf.hx)
        self.ekf.R = self.ekf.R  # Reset to original
        
        self.last_measurement_time = time.time()
        self.measurement_count += 1
        
        # Reduce process noise after successful update
        if self.measurement_count > 5:
            self.ekf.Q = self._get_Q(self.dt)  # Reset to nominal
        
        return True
    
    def update_with_delay(self, measurement: np.ndarray, measurement_time: float) -> bool:
        """Update with delayed measurement."""
        current_time = time.time()
        delay = current_time - measurement_time
        
        if delay > 0.5:  # Reject very old measurements
            self.logger.warning(f"Measurement too old: {delay:.3f}s")
            return False
        
        if delay > 0.01:  # Compensate for delay
            # Save current state
            x_current = self.ekf.x.copy()
            P_current = self.ekf.P.copy()
            
            # Retrodict to measurement time
            F_back = self._get_F(-delay)
            self.ekf.x = F_back @ self.ekf.x
            self.ekf.P = F_back @ self.ekf.P @ F_back.T
            
            # Update at measurement time
            success = self.update(measurement)
            
            if success:
                # Predict forward to current time
                self.predict(delay)
            else:
                # Restore state if update failed
                self.ekf.x = x_current
                self.ekf.P = P_current
            
            return success
        else:
            return self.update(measurement)
    
    def get_state(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self.use_acceleration:
            pos = self.ekf.x[0:3].copy()
            vel = self.ekf.x[3:6].copy()
            acc = self.ekf.x[6:9].copy()
        else:
            pos = self.ekf.x[0:3].copy()
            vel = self.ekf.x[3:6].copy()
            acc = np.zeros(3)
        return pos, vel, acc
    
    def predict_future_position(self, time_ahead: float) -> np.ndarray:
        if not self.is_initialized:
            return np.zeros(3)
        if self.use_acceleration:
            pos = self.ekf.x[0:3] + self.ekf.x[3:6] * time_ahead + 0.5 * self.ekf.x[6:9] * time_ahead**2
        else:
            pos = self.ekf.x[0:3] + self.ekf.x[3:6] * time_ahead
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
    

    def get_health_status(self) -> Dict[str, Any]:
        """Get EKF health metrics."""
        if not self.is_initialized:
            return {'healthy': False, 'reason': 'Not initialized'}
        
        # Check measurement staleness
        time_since_meas = self.time_since_measurement()
        if time_since_meas > 2.0:
            return {'healthy': False, 'reason': f'No measurements for {time_since_meas:.1f}s'}
        
        # Check covariance health
        pos_variance = np.diag(self.ekf.P)[0:3]
        max_std = np.sqrt(np.max(pos_variance))
        if max_std > 50.0:  # 50m standard deviation is too high
            return {'healthy': False, 'reason': f'High uncertainty: {max_std:.1f}m'}
        
        # Check outlier ratio
        if self.measurement_count > 20:
            outlier_ratio = self.outlier_count / self.measurement_count
            if outlier_ratio > 0.3:
                return {'healthy': False, 'reason': f'High outlier ratio: {outlier_ratio:.1%}'}
        
        return {
            'healthy': True,
            'max_std': max_std,
            'time_since_meas': time_since_meas,
            'outlier_ratio': self.outlier_count / max(1, self.measurement_count)
        }
    
    def time_since_measurement(self) -> float:
        """Time elapsed since last measurement."""
        if self.last_measurement_time is None:
            return float('inf')
        return time.time() - self.last_measurement_time
    
    def get_uncertainty(self) -> Tuple[np.ndarray, float]:
        """Get position uncertainty."""
        pos_cov = self.ekf.P[0:3, 0:3]
        uncertainty = np.sqrt(np.trace(pos_cov) / 3)  # Average uncertainty
        return pos_cov, uncertainty

# Target Source Interface
class TargetSource(ABC):
    """Abstract interface for target data sources."""
    
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
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup target source."""
        pass

class SimulatedTargetSource(TargetSource):
    """Simulated target for SITL testing - Fixed implementation."""
    
    def __init__(self, params: InterceptionParameters, 
                 frame_manager: ReferenceFrameManager):
        """Initialize simulated target."""
        self.params = params
        self.frame_manager = frame_manager
        
        # Target model - absolute position in NED
        self.position = np.array(params.target_initial_position, dtype=float)
        self.velocity = np.array(params.target_initial_velocity, dtype=float)
        self.acceleration = np.array(params.target_initial_acceleration, dtype=float)
        
        # Maneuvering parameters
        self.amp = np.array(params.target_maneuver_amplitudes)
        self.freq = np.array(params.target_maneuver_frequencies)
        self.phase = np.array(params.target_maneuver_phases) if params.target_maneuver_phases \
                     else np.random.random(3) * 2 * np.pi
        
        # Simulation state
        self.start_time = None
        self.drone_position = np.zeros(3)
        self.drone_yaw = 0.0
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def initialize(self) -> bool:
        """Initialize simulation."""
        self.start_time = time.time()
        self.logger.info(f"Simulated target initialized at NED position: {self.position}")
        return True
    
    async def get_measurement(self) -> Optional[Dict[str, Any]]:
        """Generate simulated measurement in camera frame."""
        if self.start_time is None:
            return None
            
        # Update target state
        t = time.time() - self.start_time
        
        # Target motion model (no gravity included in acceleration!)
        current_pos = self.position.copy()
        current_vel = self.velocity.copy()
        
        # Linear motion
        current_pos += self.velocity * t + 0.5 * self.acceleration * t**2
        current_vel += self.acceleration * t
        
        # Add sinusoidal maneuvering
        for i in range(3):
            if self.amp[i] > 0 and self.freq[i] > 0:
                omega = 2 * np.pi * self.freq[i]
                # Position offset
                current_pos[i] += (self.amp[i] / (omega**2)) * (1 - np.cos(omega * t + self.phase[i]))
                # Velocity component
                current_vel[i] += (self.amp[i] / omega) * np.sin(omega * t + self.phase[i])
        
        # Store true position for debugging
        self.current_position = current_pos
        self.current_velocity = current_vel
        
        # Get relative position in NED
        relative_ned = current_pos - self.drone_position
        
        # Transform to camera frame
        pos_camera = self.frame_manager.ned_to_camera(relative_ned, self.drone_yaw)
        
        # Add realistic measurement noise
        noise = np.random.normal(0, 0.2, 3)  # 20cm standard deviation
        pos_camera += noise
        
        # Simulate confidence based on distance
        distance = np.linalg.norm(relative_ned)
        confidence = np.clip(1.0 - distance / 200.0, 0.3, 1.0)
        
        return {
            'position': pos_camera,
            'timestamp': time.time(),
            'confidence': confidence,
            'frame': 'camera',
            'true_ned_position': current_pos,
            'true_ned_velocity': current_vel
        }
    
    def update_drone_state(self, position: np.ndarray, yaw: float):
        """Update drone state for simulation."""
        self.drone_position = position.copy()
        self.drone_yaw = yaw
    
    async def shutdown(self) -> None:
        """No cleanup needed."""
        pass

class CameraAPITargetSource(TargetSource):
    """
    Real camera API integration template.
    Implement get_measurement() for your camera system.
    """
    
    def __init__(self, params: InterceptionParameters):
        """Initialize camera API source."""
        self.params = params
        self.endpoint = params.target_camera_endpoint
        self.api_key = params.target_camera_api_key
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def initialize(self) -> bool:
        """Initialize camera connection."""
        # TODO: Initialize your camera API connection
        self.logger.info(f"Camera API target source initialized: {self.endpoint}")
        return True
    
    async def get_measurement(self) -> Optional[Dict[str, Any]]:
        """
        Get target position from camera API.
        
        TODO: Implement your camera API call here.
        Expected response should contain target position in camera frame.
        """
        try:
            # Example implementation:
            # response = await your_api_call(self.endpoint)
            # if response.target_detected:
            #     return {
            #         'position': np.array([response.x, response.y, response.z]),
            #         'timestamp': response.timestamp,
            #         'confidence': response.confidence,
            #         'frame': 'camera'
            #     }
            
            # Placeholder - replace with actual implementation
            return None
            
        except Exception as e:
            self.logger.error(f"Camera API error: {e}")
            return None
    
    async def shutdown(self) -> None:
        """Close camera connection."""
        # TODO: Cleanup your camera API connection
        pass

def create_target_source(params: InterceptionParameters,
                        frame_manager: ReferenceFrameManager) -> TargetSource:
    """Factory function to create appropriate target source."""
    if params.target_source_type == "simulated":
        return SimulatedTargetSource(params, frame_manager)
    elif params.target_source_type == "camera_api":
        return CameraAPITargetSource(params)
    else:
        # Auto-detect based on connection
        if params.system_connection.startswith("udp"):
            return SimulatedTargetSource(params, frame_manager)
        else:
            return CameraAPITargetSource(params)

# =============================================================================
# FILE: guidance_strategies.py - Fixed implementations
# =============================================================================

class GuidanceStrategy(ABC):
    """Base class for all guidance strategies."""
    
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
        """Compute and send guidance command."""
        pass
    
    def get_future_target_position(self, lead_time: float) -> np.ndarray:
        """Get predicted target position using EKF."""
        return self.ekf.predict_future_position(lead_time)
    
    def compute_desired_yaw(self, error_ned: np.ndarray,
                          target_velocity: Optional[np.ndarray] = None) -> float:
        """Compute desired yaw angle with optional lead compensation."""
        if target_velocity is not None and self.params.guidance_yaw_lead_time > 0:
            future_error = error_ned + target_velocity * self.params.guidance_yaw_lead_time
            bearing = math.degrees(math.atan2(future_error[1], future_error[0]))
        else:
            bearing = math.degrees(math.atan2(error_ned[1], error_ned[0]))
        
        return normalize_angle(bearing)

class LocalNEDVelocityGuidance(GuidanceStrategy):
    """
    Local NED velocity guidance using PX4's local position.
    
    Characteristics:
    - Uses PX4's local NED position (position_velocity_ned)
    - Works without GPS (optical flow, VIO, etc.)
    - May experience drift over time due to PX4's reference
    - Commands: VelocityNedYaw
    
    Best for: Non-GPS scenarios, indoor flight, short missions
    """
    
    def __init__(self, params: InterceptionParameters,
                 ekf: TargetTrackingEKF,
                 frame_manager: ReferenceFrameManager):
        """Initialize local NED velocity guidance."""
        super().__init__(params, ekf, frame_manager)
        
        # PID controllers
        h_gains = params.pid_velocity_gains['horizontal']
        v_gains = params.pid_velocity_gains['vertical']
        
        self.pid_n = self._create_pid(h_gains, params.velocity_max_horizontal)
        self.pid_e = self._create_pid(h_gains, params.velocity_max_horizontal)
        self.pid_d = self._create_pid(v_gains, params.velocity_max_vertical)
        
        self.logger.info("Local NED velocity guidance initialized (may drift with GPS)")
    
    def _create_pid(self, gains: List[float], limit: float) -> PID:
        """Create PID controller with anti-windup."""
        pid = PID(
            Kp=gains[0], Ki=gains[1], Kd=gains[2],
            setpoint=0,
            output_limits=(-limit, limit),
            sample_time=self.params.control_loop_period  # Specify sample time
        )
        # Add integral windup limit
        pid.set_auto_mode(True, last_output=0)
        if hasattr(pid, '_integral'):
            pid._integral_limits = (-self.params.pid_integral_limit, 
                                self.params.pid_integral_limit)
        return pid
    
    async def compute_command(self, drone, telemetry, target_ned, target_velocity=None, dt=0.05):
        """Compute NED velocity using PX4 local position."""
        # Use PX4's local NED position (may drift!)
        current_ned = telemetry.get_position_ned()
        
        # Compute error
        error_ned = target_ned - current_ned
        distance = np.linalg.norm(error_ned[:2])  # Horizontal distance
        
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
        
        # Ensure velocities are within limits
        horizontal_vel = np.hypot(vn, ve)
        if horizontal_vel > self.params.velocity_max_horizontal:
            scale = self.params.velocity_max_horizontal / horizontal_vel
            vn *= scale
            ve *= scale
        
        vd = np.clip(vd, -self.params.velocity_max_vertical, self.params.velocity_max_vertical)
        
        # Desired yaw
        desired_yaw = self.compute_desired_yaw(error_ned, target_velocity)
        
        # Send command
        try:
            await drone.offboard.set_velocity_ned(
                VelocityNedYaw(float(vn), float(ve), float(vd), float(desired_yaw))
            )
            return True
        except OffboardError as e:
            self.logger.error(f"Local NED velocity command failed: {e}")
            return False
    
    def _update_gains(self, scale: float):
        """Update PID gains."""
        base_h = self.params.pid_velocity_gains['horizontal']
        base_v = self.params.pid_velocity_gains['vertical']
        
        for pid, base in [(self.pid_n, base_h), (self.pid_e, base_h), (self.pid_d, base_v)]:
            pid.Kp = base[0] * scale
            pid.Ki = base[1] * scale
            pid.Kd = base[2] * scale

class GlobalNEDVelocityGuidance(GuidanceStrategy):
    """
    Global-referenced NED velocity guidance with GPS drift mitigation.
    
    Characteristics:
    - Recalculates positions from geodetic coordinates
    - Avoids PX4's local position drift
    - Uses either fixed home or current position as reference
    - Commands: VelocityNedYaw
    
    Best for: GPS-based missions requiring precise positioning
    """
    
    def __init__(self, params: InterceptionParameters,
                 ekf: TargetTrackingEKF,
                 frame_manager: ReferenceFrameManager):
        """Initialize global NED velocity guidance."""
        super().__init__(params, ekf, frame_manager)
        
        # PID controllers
        h_gains = params.pid_velocity_gains['horizontal']
        v_gains = params.pid_velocity_gains['vertical']
        
        self.pid_n = self._create_pid(h_gains, params.velocity_max_horizontal)
        self.pid_e = self._create_pid(h_gains, params.velocity_max_horizontal)
        self.pid_d = self._create_pid(v_gains, params.velocity_max_vertical)
        
        ref_mode = "current position" if params.reference_use_current_position else "fixed home"
        self.logger.info(f"Global NED velocity guidance initialized (using {ref_mode} reference)")
    
    def _create_pid(self, gains: List[float], limit: float) -> PID:
        """Create PID controller."""
        return PID(
            Kp=gains[0], Ki=gains[1], Kd=gains[2],
            setpoint=0,
            output_limits=(-limit, limit)
        )
    
    async def compute_command(self, drone, telemetry, target_ned, target_velocity=None, dt=0.05):
        """Compute NED velocity using global position reference."""
        # Update reference if using current position mode
        if self.params.reference_use_current_position:
            self.frame_manager.update_current_reference(
                telemetry.latitude_deg,
                telemetry.longitude_deg,
                telemetry.altitude_amsl_m
            )
        
        # Calculate current NED from geodetic (avoids drift)
        current_ned = self.frame_manager.geodetic_to_ned(
            telemetry.latitude_deg,
            telemetry.longitude_deg,
            telemetry.altitude_amsl_m
        )
        
        # Compute error
        error_ned = target_ned - current_ned
        distance = np.linalg.norm(error_ned[:2])  # Horizontal distance
        
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
        
        # Ensure velocities are within limits
        horizontal_vel = np.hypot(vn, ve)
        if horizontal_vel > self.params.velocity_max_horizontal:
            scale = self.params.velocity_max_horizontal / horizontal_vel
            vn *= scale
            ve *= scale
        
        vd = np.clip(vd, -self.params.velocity_max_vertical, self.params.velocity_max_vertical)
        
        # Desired yaw
        desired_yaw = self.compute_desired_yaw(error_ned, target_velocity)
        
        # Send command
        try:
            await drone.offboard.set_velocity_ned(
                VelocityNedYaw(float(vn), float(ve), float(vd), float(desired_yaw))
            )
            return True
        except OffboardError as e:
            self.logger.error(f"Global NED velocity command failed: {e}")
            return False
    
    def _update_gains(self, scale: float):
        """Update PID gains."""
        base_h = self.params.pid_velocity_gains['horizontal']
        base_v = self.params.pid_velocity_gains['vertical']
        
        for pid, base in [(self.pid_n, base_h), (self.pid_e, base_h), (self.pid_d, base_v)]:
            pid.Kp = base[0] * scale
            pid.Ki = base[1] * scale
            pid.Kd = base[2] * scale

class BodyVelocityGuidance(GuidanceStrategy):
    """
    Body-frame velocity guidance.
    
    Characteristics:
    - Controls in aircraft body frame
    - Camera-centric control
    - Uses global position reference to avoid drift
    - Commands: VelocityBodyYawspeed
    
    Best for: Camera tracking, close-range operations
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
        """Create PID controller."""
        return PID(
            Kp=gains[0], Ki=gains[1], Kd=gains[2],
            setpoint=0,
            output_limits=(-limit, limit)
        )
    
    async def compute_command(self, drone, telemetry, target_ned, target_velocity=None, dt=0.05):
        """Compute body velocity command."""
        # Get current position (use global reference to avoid drift)
        if self.params.reference_use_current_position:
            self.frame_manager.update_current_reference(
                telemetry.latitude_deg,
                telemetry.longitude_deg,
                telemetry.altitude_amsl_m
            )
        
        current_ned = self.frame_manager.geodetic_to_ned(
            telemetry.latitude_deg,
            telemetry.longitude_deg,
            telemetry.altitude_amsl_m
        )
        
        # Compute error
        error_ned = target_ned - current_ned
        distance = np.linalg.norm(error_ned[:2])
        
        # Check deadband
        if distance < self.params.control_position_deadband:
            await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
            return True
        
        # Transform to camera frame
        error_camera = self.frame_manager.ned_to_camera(error_ned, telemetry.yaw_rad)
        
        # Adaptive gain scheduling
        if self.params.adaptive_control_enabled:
            scale = np.clip(distance / self.params.adaptive_distance_threshold,
                          self.params.adaptive_gain_min,
                          self.params.adaptive_gain_max)
            self._update_gains(scale)
        
        # PID control in camera frame
        vx_cam = self.pid_x(-error_camera[0])
        vy_cam = self.pid_y(-error_camera[1])
        vz_cam = self.pid_z(-error_camera[2])
        
        # Transform to body frame
        vel_camera = np.array([vx_cam, vy_cam, vz_cam])
        vel_body = self.frame_manager.camera_to_body(vel_camera)
        
        # Ensure velocities are within limits
        horizontal_vel = np.hypot(vel_body[0], vel_body[1])
        if horizontal_vel > self.params.velocity_max_horizontal:
            scale = self.params.velocity_max_horizontal / horizontal_vel
            vel_body[0] *= scale
            vel_body[1] *= scale
        
        vel_body[2] = np.clip(vel_body[2], -self.params.velocity_max_vertical, 
                              self.params.velocity_max_vertical)
        
        # Compute yaw rate
        desired_yaw = self.compute_desired_yaw(error_ned, target_velocity)
        yaw_error = normalize_angle(desired_yaw - telemetry.yaw_deg)
        
        # Convert to rate with deadband
        if abs(yaw_error) < self.params.control_yaw_deadband:
            yaw_rate = 0
        else:
            yaw_rate = np.clip(yaw_error * 2.0, -self.params.velocity_max_yaw_rate, 
                              self.params.velocity_max_yaw_rate)
        
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
        """Update PID gains."""
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

class GlobalPositionGuidance(GuidanceStrategy):
    """
    Global position guidance using direct position commands.
    
    Characteristics:
    - Sends target position directly to PX4
    - PX4 handles all control and path planning
    - Uses predictive positioning
    - Commands: PositionGlobalYaw
    
    Best for: Long-range navigation, waypoint missions
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
        
        # Convert to geodetic
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

def create_guidance_strategy(params: InterceptionParameters,
                           ekf: TargetTrackingEKF,
                           frame_manager: ReferenceFrameManager) -> GuidanceStrategy:
    """
    Factory function to create guidance strategies.
    
    Available strategies:
    - local_ned_velocity: PX4 local NED (may drift)
    - global_ned_velocity: Global-referenced NED (drift mitigation)
    - body_velocity: Body frame control
    - global_position: Direct position commands
    """
    strategies = {
        'local_ned_velocity': LocalNEDVelocityGuidance,
        'global_ned_velocity': GlobalNEDVelocityGuidance,
        'body_velocity': BodyVelocityGuidance,
        'global_position': GlobalPositionGuidance,
    }
    
    if params.guidance_mode not in strategies:
        raise ValueError(f"Unknown guidance mode: {params.guidance_mode}")
    
    return strategies[params.guidance_mode](params, ekf, frame_manager)

# =============================================================================
# FILE: visualization.py - FIXED IMPLEMENTATION
# =============================================================================

class MissionVisualizer:
    """
    Clean, organized 3D visualization for mission monitoring.
    Fixed to work properly with tkinter and headless mode.
    """
    
    def __init__(self, params: InterceptionParameters, ekf: Optional[TargetTrackingEKF] = None):
        """Initialize visualizer with headless mode detection."""
        self.params = params
        self.logger = logging.getLogger(self.__class__.__name__)
        self.rate_window = 5.0  # seconds for moving average
        self.control_loop_times = deque(maxlen=200)
        self.telemetry_times = deque(maxlen=200)
        self.ekf = ekf
        self.ekf_update_times = deque(maxlen=200)
        self.target_meas_times = deque(maxlen=200)

        if not params.viz_enabled:
            self.enabled = False
            return
        
        # Detect headless mode
        display_available = True
        if os.environ.get('DISPLAY') is None and os.name != 'nt':
            display_available = False
            self.logger.warning("No display detected, running in headless mode")
        
        # Try to set backend
        if display_available:
            try:
                matplotlib.use('TkAgg')
            except ImportError:
                try:
                    matplotlib.use('Qt5Agg')
                except ImportError:
                    try:
                        matplotlib.use('GTKAgg')
                    except ImportError:
                        self.logger.warning("No interactive backend available")
                        display_available = False
        
        if not display_available:
            # Use non-interactive backend
            matplotlib.use('Agg')
            self.enabled = False
            self.logger.info("Visualization disabled due to headless environment")
            return
        
        self.enabled = True
        
        # Setup figure
        try:
            plt.ion()  # Interactive mode
            self.fig = plt.figure(figsize=(16, 9))
            self.fig.canvas.manager.set_window_title('Mission Visualizer')
            
            # Create subplots
            self.ax_3d = self.fig.add_subplot(221, projection='3d')
            self.ax_topdown = self.fig.add_subplot(222)
            self.ax_status = self.fig.add_subplot(223)
            self.ax_altitude = self.fig.add_subplot(224)
            
            # Colors
            self.colors = {
                'drone': '#0066CC',
                'target': '#CC0000',
                'prediction': '#00CC66',
                'good': '#00CC00',
                'warning': '#FFAA00',
                'danger': '#FF0000'
            }
            
            # Initialize data storage
            self.history = {
                'drone': deque(maxlen=self.params.viz_history_length),
                'target': deque(maxlen=self.params.viz_history_length),
                'predictions': deque(maxlen=self.params.viz_history_length)
            }
            
            # State tracking
            self.update_count = 0
            self.last_update_time = time.time()
            self.start_time = time.time()
            self.last_telemetry = None
            
            # Data for plots
            self.drone_path = []
            self.target_path = []
            self.drone_altitudes = []
            self.target_altitudes = []
            self.distances = []
            self.times = []
            
            # Setup plots
            self._setup_3d_plot()
            self._setup_topdown_plot()
            self._setup_status_plot()
            self._setup_altitude_plot()
            
            self.fig.tight_layout()
            plt.show(block=False)
            
            self.logger.info("Visualization initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize visualization: {e}")
            self.enabled = False

    def _compute_rate(self, times):
        now = time.time()
        times = [t for t in times if now - t < self.rate_window]
        if len(times) < 2:
            return 0.0
        return (len(times) - 1) / (times[-1] - times[0])
    
    def _setup_3d_plot(self):
        """Setup clean 3D trajectory plot."""
        self.ax_3d.set_title('3D Pursuit View', fontsize=14, pad=10)
        self.ax_3d.set_xlabel('North (m)', labelpad=5)
        self.ax_3d.set_ylabel('East (m)', labelpad=5)
        self.ax_3d.set_zlabel('Altitude (m)', labelpad=5)
        self.ax_3d.grid(True, alpha=0.3)
        self.ax_3d.view_init(elev=25, azim=45)
    
    def _setup_topdown_plot(self):
        """Setup clean top-down view."""
        self.ax_topdown.set_title('Top-Down View', fontsize=12, pad=10)
        self.ax_topdown.set_xlabel('East (m)')
        self.ax_topdown.set_ylabel('North (m)')
        self.ax_topdown.set_aspect('equal')
        self.ax_topdown.grid(True, alpha=0.3)
        
        # Initialize elements
        self.topdown_drone_trail, = self.ax_topdown.plot([], [], 
                                                         color=self.colors['drone'], 
                                                         linewidth=1, alpha=0.3)
        self.topdown_target_trail, = self.ax_topdown.plot([], [], 
                                                          color=self.colors['target'], 
                                                          linewidth=1, alpha=0.3, 
                                                          linestyle='--')
        
        self.topdown_drone, = self.ax_topdown.plot([], [], 
                                                   color=self.colors['drone'], 
                                                   marker='o', markersize=10)
        self.topdown_target, = self.ax_topdown.plot([], [], 
                                                    color=self.colors['target'], 
                                                    marker='*', markersize=12)
        
        # Range rings
        self.range_rings = []
        for r in [10, 25, 50]:
            circle = Circle((0, 0), r, fill=False, linestyle=':', 
                          alpha=0.3, color='gray')
            self.ax_topdown.add_patch(circle)
            self.range_rings.append(circle)
        
        # Uncertainty ellipse
        self.uncertainty_ellipse = Ellipse((0, 0), 0, 0, angle=0, 
                                         fill=False, edgecolor=self.colors['target'], 
                                         alpha=0.5, linestyle='--', linewidth=1)
        self.ax_topdown.add_patch(self.uncertainty_ellipse)
        self.uncertainty_ellipse.set_visible(False)
    
    def _setup_altitude_plot(self):
        """Setup altitude vs time plot."""
        self.ax_altitude.set_title('Altitude Profile', fontsize=12, pad=10)
        self.ax_altitude.set_xlabel('Time (s)')
        self.ax_altitude.set_ylabel('Altitude AGL (m)')
        self.ax_altitude.grid(True, alpha=0.3)
        
        # Initialize plot lines
        self.altitude_drone_line, = self.ax_altitude.plot([], [], 
                                                         color=self.colors['drone'],
                                                         linewidth=2, label='Drone')
        self.altitude_target_line, = self.ax_altitude.plot([], [], 
                                                          color=self.colors['target'],
                                                          linewidth=2, linestyle='--',
                                                          label='Target')
        
        self.ax_altitude.legend(loc='upper right')
        self.ax_altitude.set_ylim(0, 50)
    
    def _setup_status_plot(self):
        """Setup clean status display."""
        self.ax_status.set_title('Mission Status', fontsize=12, pad=10)
        self.ax_status.axis('off')
        
        # Create text element
        self.status_text = self.ax_status.text(0.05, 0.95, '', 
                                              transform=self.ax_status.transAxes,
                                              fontsize=11, verticalalignment='top',
                                              fontfamily='monospace')
    
    def update(self, telemetry: TelemetryData,
    target_state: Tuple[np.ndarray, np.ndarray, np.ndarray],
    predictions: Optional[List[np.ndarray]] = None,
    uncertainty: Optional[Tuple[np.ndarray, float]] = None,
    mission_state: str = "UNKNOWN"):
        """Update visualization with all components."""
        if not self.enabled:
            return

        # Store telemetry
        self.last_telemetry = telemetry

        # Rate limiting
        now = time.time()
        if now - self.last_update_time < 1.0 / self.params.viz_update_rate:
            return

        self.last_update_time = now
        self.update_count += 1

        # Get positions
        drone_pos = np.array([telemetry.north_m, telemetry.east_m, -telemetry.altitude_agl_m])
        target_pos = target_state[0].copy()
        target_vel = target_state[1].copy()

        # Store history
        self.history['drone'].append(drone_pos.copy())
        self.history['target'].append(target_pos.copy())
        if predictions:
            self.history['predictions'].append(predictions[:20])

        # Store data for plots
        elapsed = now - self.start_time
        self.times.append(elapsed)
        self.drone_path.append(drone_pos)
        self.target_path.append(target_pos)
        self.drone_altitudes.append(telemetry.altitude_agl_m)
        self.target_altitudes.append(-target_pos[2])

        # Calculate metrics
        error_horizontal = np.linalg.norm(drone_pos[:2] - target_pos[:2])
        error_3d = np.linalg.norm(drone_pos - target_pos)
        self.distances.append(error_horizontal)

        # Limit history
        max_points = self.params.viz_path_history_length
        if len(self.drone_path) > max_points:
            self.drone_path = self.drone_path[-max_points:]
            self.target_path = self.target_path[-max_points:]
            self.times = self.times[-max_points:]
            self.distances = self.distances[-max_points:]
            self.drone_altitudes = self.drone_altitudes[-max_points:]
            self.target_altitudes = self.target_altitudes[-max_points:]

        # Update all plots
        self._update_3d(drone_pos, target_pos, predictions, error_3d, telemetry.yaw_rad)
        self._update_topdown(drone_pos, target_pos, telemetry, uncertainty, error_horizontal)
        self._update_altitude()
        self._update_status_display(telemetry, target_state, error_horizontal,
                                elapsed, mission_state, uncertainty)

        # Refresh display
        plt.draw()
        plt.pause(0.001)
    
    def _update_3d(self, drone_pos, target_pos, predictions, error_3d, yaw):
        """Update 3D plot with drone orientation."""
        # Clear and redraw
        self.ax_3d.clear()
        
        # Re-setup
        self.ax_3d.set_title('3D Pursuit View', fontsize=14, pad=10)
        self.ax_3d.set_xlabel('North (m)', labelpad=5)
        self.ax_3d.set_ylabel('East (m)', labelpad=5)
        self.ax_3d.set_zlabel('Altitude (m)', labelpad=5)
        self.ax_3d.grid(True, alpha=0.3)
        
        # Plot trails
        if len(self.drone_path) > 1:
            drone_array = np.array(self.drone_path)
            target_array = np.array(self.target_path)
            drone_array[:, 2] = -drone_array[:, 2]
            target_array[:, 2] = -target_array[:, 2]
            
            self.ax_3d.plot(drone_array[:, 0], drone_array[:, 1], drone_array[:, 2],
                           color=self.colors['drone'], linewidth=2, alpha=0.3)
            self.ax_3d.plot(target_array[:, 0], target_array[:, 1], target_array[:, 2],
                           color=self.colors['target'], linewidth=2, alpha=0.3, linestyle='--')
        
        # Draw drone with orientation
        drone_size = 2.0
        
        # Drone shape (triangle pointing forward)
        drone_shape = np.array([
            [1.5, 0, 0],      # Nose
            [-0.75, 0.75, 0], # Left wing
            [-0.75, -0.75, 0], # Right wing
            [1.5, 0, 0]       # Close shape
        ]) * drone_size
        
        # Rotate by yaw
        rotation = np.array([
            [np.cos(yaw), -np.sin(yaw), 0],
            [np.sin(yaw), np.cos(yaw), 0],
            [0, 0, 1]
        ])
        
        drone_rotated = drone_shape @ rotation.T
        drone_rotated[:, 0] += drone_pos[0]
        drone_rotated[:, 1] += drone_pos[1]
        drone_rotated[:, 2] -= drone_pos[2]
        
        # Plot drone body
        self.ax_3d.plot(drone_rotated[:, 0], drone_rotated[:, 1], drone_rotated[:, 2],
                       'b-', linewidth=3, label='Drone')
        
        # Add drone marker
        self.ax_3d.scatter([drone_pos[0]], [drone_pos[1]], [-drone_pos[2]],
                          c=self.colors['drone'], s=100, marker='o', 
                          edgecolors='darkblue', linewidth=2)
        
        # Draw heading arrow
        arrow_length = 5.0
        arrow_end = drone_pos[:2] + arrow_length * np.array([np.cos(yaw), np.sin(yaw)])
        self.ax_3d.plot([drone_pos[0], arrow_end[0]], 
                       [drone_pos[1], arrow_end[1]], 
                       [-drone_pos[2], -drone_pos[2]],
                       'b--', linewidth=2, alpha=0.5)
        
        # Draw simple camera FOV
        fov_length = 10.0
        fov_angle = np.radians(30)
        
        for angle_offset in [-fov_angle, fov_angle]:
            fov_dir = yaw + angle_offset
            fov_end = drone_pos[:2] + fov_length * np.array([np.cos(fov_dir), np.sin(fov_dir)])
            self.ax_3d.plot([drone_pos[0], fov_end[0]], 
                           [drone_pos[1], fov_end[1]], 
                           [-drone_pos[2], -drone_pos[2]],
                           color='yellow', linewidth=1, alpha=0.5)
        
        # Add yaw text
        self.ax_3d.text(drone_pos[0], drone_pos[1], -drone_pos[2] + 3,
                       f'Yaw: {np.degrees(yaw):.0f}°',
                       fontsize=9, ha='center')
        
        # Plot target
        self.ax_3d.scatter([target_pos[0]], [target_pos[1]], [-target_pos[2]],
                          c=self.colors['target'], s=150, marker='*',
                          edgecolors='darkred', linewidth=2, label='Target')
        
        # Plot prediction
        if predictions and error_3d < 50 and len(predictions) > 0:
            pred_array = np.array(predictions[:20])
            self.ax_3d.plot(pred_array[:, 0], pred_array[:, 1], -pred_array[:, 2],
                           color=self.colors['prediction'], linestyle=':',
                           linewidth=2, alpha=0.6, label='Prediction')
        
        # Auto-scale
        if len(self.drone_path) > 0:
            all_x = [p[0] for p in self.drone_path + self.target_path]
            all_y = [p[1] for p in self.drone_path + self.target_path]
            all_z = [-p[2] for p in self.drone_path + self.target_path]
            
            margin = 15
            self.ax_3d.set_xlim(min(all_x) - margin, max(all_x) + margin)
            self.ax_3d.set_ylim(min(all_y) - margin, max(all_y) + margin)
            self.ax_3d.set_zlim(0, max(max(all_z) + margin, 20))
        
        self.ax_3d.legend(loc='upper right', framealpha=0.9)
        self.ax_3d.view_init(elev=25, azim=45)
    
    def _update_topdown(self, drone_pos, target_pos, telemetry, uncertainty, error):
        """Update top-down view."""
        # Update positions
        self.topdown_drone.set_data([drone_pos[1]], [drone_pos[0]])
        self.topdown_target.set_data([target_pos[1]], [target_pos[0]])
        
        # Update trails
        if len(self.drone_path) > 1:
            drone_trail = np.array(self.drone_path[-50:])
            target_trail = np.array(self.target_path[-50:])
            self.topdown_drone_trail.set_data(drone_trail[:, 1], drone_trail[:, 0])
            self.topdown_target_trail.set_data(target_trail[:, 1], target_trail[:, 0])
        
        # Update range rings
        for ring in self.range_rings:
            ring.center = (drone_pos[1], drone_pos[0])
        
        # Update uncertainty ellipse
        if uncertainty and uncertainty[1] > 2.0:
            try:
                cov_2d = uncertainty[0][:2, :2]
                eigenvalues, eigenvectors = np.linalg.eigh(cov_2d)
                angle = np.degrees(np.arctan2(eigenvectors[1, 0], eigenvectors[0, 0]))
                width = 2 * np.sqrt(5.991 * eigenvalues[0])
                height = 2 * np.sqrt(5.991 * eigenvalues[1])
                
                self.uncertainty_ellipse.set_center((target_pos[1], target_pos[0]))
                self.uncertainty_ellipse.width = width
                self.uncertainty_ellipse.height = height
                self.uncertainty_ellipse.angle = angle
                self.uncertainty_ellipse.set_visible(True)
            except:
                self.uncertainty_ellipse.set_visible(False)
        else:
            self.uncertainty_ellipse.set_visible(False)
        
        # Auto-scale
        view_range = 75
        self.ax_topdown.set_xlim(drone_pos[1] - view_range, drone_pos[1] + view_range)
        self.ax_topdown.set_ylim(drone_pos[0] - view_range, drone_pos[0] + view_range)
    
    def _update_altitude(self):
        """Update altitude plot."""
        if len(self.times) > 1:
            self.altitude_drone_line.set_data(self.times, self.drone_altitudes)
            self.altitude_target_line.set_data(self.times, self.target_altitudes)
            
            # Auto-scale
            self.ax_altitude.set_xlim(0, max(self.times[-1], 10))
            max_alt = max(max(self.drone_altitudes + self.target_altitudes, default=10), 10)
            self.ax_altitude.set_ylim(0, max_alt * 1.2)
    
    def _update_status_display(self, telemetry, target_state, error, elapsed, 
                              mission_state, uncertainty):
        """Update status panel."""
        # Determine status color
        if error < self.params.mission_target_threshold:
            error_status = "ON TARGET"
        elif error < self.params.mission_target_threshold * 3:
            error_status = "CLOSING"
        else:
            error_status = "TRACKING"
        
        # Format time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        # Build status text
        status_lines = [
            f"{'='*35}",
            f"Mission State: {mission_state:>18}",
            f"Time Elapsed:  {minutes:02d}:{seconds:02d}",
            f"{'='*35}",
            f"",
            f"TRACKING STATUS",
            f"Distance:      {error:>6.1f} m [{error_status}]",
            f"Target Speed:  {np.linalg.norm(target_state[1]):>6.1f} m/s",
            f"Drone Speed:   {telemetry.get_ground_speed():>6.1f} m/s",
        ]
        
        if uncertainty and uncertainty[1] is not None:
            status_lines.append(f"EKF Uncert.:   {uncertainty[1]:>6.1f} m")
        
        status_lines.extend([
            f"",
            f"DRONE STATUS",
            f"Altitude:      {telemetry.altitude_agl_m:>6.1f} m",
            f"Battery:       {telemetry.battery_percent:>6.0f} %",
            f"GPS Sats:      {telemetry.gps_satellites:>6d}",
        ])

        # Add rates
        control_rate = self._compute_rate(self.control_loop_times)
        telemetry_rate = self._compute_rate(self.telemetry_times)
        ekf_rate = self._compute_rate(self.ekf_update_times)
        target_rate = self._compute_rate(self.target_meas_times)
        status_lines.append("")
        status_lines.append(f"RATES [Hz]:")
        status_lines.append(f"Control: {control_rate:5.1f} | Telemetry: {telemetry_rate:5.1f} | EKF: {ekf_rate:5.1f} | Target: {target_rate:5.1f}")
        
        full_text = '\n'.join(status_lines)
        self.status_text.set_text(full_text)
    
    def save_plot(self, filename: str):
        """Save current plot to file."""
        if self.enabled:
            self.fig.savefig(filename, dpi=150, bbox_inches='tight')
            self.logger.info(f"Plot saved to {filename}")

# =============================================================================
# FILE: mission_executor.py - Main mission execution
# =============================================================================

class MissionState(Enum):
    """Mission execution states."""
    INIT = auto()
    PREFLIGHT = auto()
    ARMING = auto()
    TAKEOFF = auto()
    PURSUIT = auto()
    PROXIMITY = auto()
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
            MissionState.PROXIMITY: [MissionState.HOLDING, MissionState.LANDING, MissionState.EMERGENCY],
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
        self.logger.info(f"Guidance mode: {self.params.guidance_mode}")
    
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
            self.visualizer = MissionVisualizer(self.params, self.ekf)
        
        self.logger.info("All systems initialized successfully")
    
    async def run_mission(self):
        """Execute the complete mission."""
        try:
            print("\n" + "="*70)
            print("DRONE PURSUIT SYSTEM v5.2 FIXED".center(70))
            print("Professional Autonomous Target Tracking".center(70))
            print(f"Mode: {self.params.guidance_mode}".center(70))
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
        
        # Set home reference
        self.frame_manager.set_home_reference(
            telemetry.latitude_deg,
            telemetry.longitude_deg,
            telemetry.altitude_amsl_m
        )
        
        # Store home position
        self.home_position_ned = np.array([0.0, 0.0, 0.0])
        
        # Initialize EKF with target
        if self.ekf and hasattr(self.target_source, 'position'):
            initial_target_pos = np.array(self.target_source.position)
            initial_target_vel = np.array(self.target_source.velocity) if hasattr(self.target_source, 'velocity') else np.zeros(3)
            initial_target_acc = np.array(self.target_source.acceleration) if hasattr(self.target_source, 'acceleration') else np.zeros(3)
            self.ekf.initialize(initial_target_pos, initial_target_vel, initial_target_acc)
        
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
            
            if telemetry.altitude_agl_m >= self.params.mission_takeoff_altitude - 0.5:
                self.logger.info(f"Reached altitude: {telemetry.altitude_agl_m:.1f}m")
                break
            
            await self.drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(0, 0, self.params.mission_ascent_speed, 0)
            )
            
            # Update visualization during takeoff
            if self.visualizer and self.ekf:
                target_pos, target_vel, target_acc = self.ekf.get_state()
                self.visualizer.update(
                    telemetry,
                    (target_pos, target_vel, target_acc),
                    mission_state=self.state_machine.state.name
                )
            
            await asyncio.sleep(self.params.control_loop_period)
        
        # Hold position briefly
        await self.drone.offboard.set_velocity_ned(VelocityNedYaw(0, 0, 0, 0))
        await asyncio.sleep(2.0)
    
    async def _execute_pursuit(self):
        """Main pursuit phase - Fixed implementation."""
        self.state_machine.transition_to(MissionState.PURSUIT, "Starting pursuit")
        
        self.logger.info("Pursuit phase active")
        self.mission_start_time = time.time()
        
        # Initialize stats
        self.mission_stats = {
            'max_error': 0,
            'min_error': float('inf'),
            'measurements_accepted': 0,
            'measurements_rejected': 0,
            'min_battery': 100,
            'max_altitude': 0,
            'pursuit_duration': 0,
            'average_error': 0,
            'error_samples': 0,
            'target_acquired': False
        }
        
        print("\n" + "="*60)
        print("PURSUIT ACTIVE".center(60))
        print("="*60 + "\n")
        
        last_time = time.time()
        consecutive_target_acquisitions = 0
        
        while self.state_machine.state == MissionState.PURSUIT:
            loop_start = time.time()
            dt = loop_start - last_time
            last_time = loop_start
            
            try:
                # Get telemetry
                telemetry = await self.telemetry_manager.get_telemetry()
                
                # Get current drone position (avoid drift by using geodetic)
                current_ned = self.frame_manager.geodetic_to_ned(
                    telemetry.latitude_deg,
                    telemetry.longitude_deg,
                    telemetry.altitude_amsl_m
                )
                
                # Update simulated target
                if isinstance(self.target_source, SimulatedTargetSource):
                    self.target_source.update_drone_state(current_ned, telemetry.yaw_rad)
                
                # Get target measurement
                measurement = await self.target_source.get_measurement()
                
                # Process measurement or use prediction
                if measurement is None:
                    self.logger.warning("No target measurement")
                    # Continue with EKF prediction if available
                    if self.ekf and self.ekf.is_initialized and \
                       self.ekf.time_since_measurement() < self.params.ekf_miss_timeout:
                        self.ekf.predict(dt)
                        target_pos, target_vel, target_acc = self.ekf.get_state()
                    else:
                        self.logger.warning("No valid target data available")
                        continue
                else:
                    # Transform measurement to NED
                    if self.visualizer:
                        self.visualizer.target_meas_times.append(time.time())
                    target_cam = measurement['position']
                    target_ned_relative = self.frame_manager.camera_to_ned(
                        target_cam, telemetry.yaw_rad
                    )
                    
                    # Get absolute target position
                    target_ned = current_ned + target_ned_relative
                    
                    # Apply EKF
                    if self.ekf:
                        self.ekf.predict(dt)
                        
                        if self.ekf.update(target_ned):
                            self.mission_stats['measurements_accepted'] += 1
                            if self.visualizer:
                                self.visualizer.ekf_update_times.append(time.time())
                        else:
                            self.mission_stats['measurements_rejected'] += 1
                        
                        # Get filtered state
                        target_pos, target_vel, target_acc = self.ekf.get_state()
                    else:
                        # No EKF, use raw measurement
                        target_pos = target_ned
                        target_vel = np.zeros(3)
                        target_acc = np.zeros(3)
                
                # Check mission constraints
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
                    if "battery" in reason.lower() or "altitude" in reason.lower():
                        break
                
                # Calculate error
                error_3d = np.linalg.norm(target_pos - current_ned)
                error_horizontal = np.linalg.norm((target_pos - current_ned)[:2])
                
                # Update statistics
                self.mission_stats['max_error'] = max(self.mission_stats['max_error'], error_3d)
                self.mission_stats['min_error'] = min(self.mission_stats['min_error'], error_3d)
                self.mission_stats['average_error'] = (
                    (self.mission_stats['average_error'] * self.mission_stats['error_samples'] + error_3d) /
                    (self.mission_stats['error_samples'] + 1)
                )
                self.mission_stats['error_samples'] += 1
                
                # Check if target reached
                if error_3d <= self.params.mission_target_threshold:
                    consecutive_target_acquisitions += 1
                    if consecutive_target_acquisitions >= 3:  # Require stable acquisition
                        self.logger.info(f"Target acquired! Distance: {error_3d:.2f}m")
                        self.mission_stats['target_acquired'] = True
                        self.state_machine.transition_to(MissionState.PROXIMITY, "Target acquired")  # <-- update
                        break
                else:
                    consecutive_target_acquisitions = 0
                
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
                
                # Update visualization
                if self.visualizer:
                    predictions = None
                    uncertainty = None

                    self.visualizer.control_loop_times.append(time.time())
                    
                    if self.ekf:
                        if self.params.viz_show_predictions:
                            predictions = self.ekf.predict_trajectory(
                                self.params.ekf_prediction_horizon
                            )
                        if self.params.viz_show_uncertainty:
                            uncertainty = self.ekf.get_uncertainty()
                    
                    self.visualizer.update(
                        telemetry,
                        (target_pos, target_vel, target_acc),
                        predictions,
                        uncertainty,
                        self.state_machine.state.name,
                    )
                
                # Terminal display (clean and informative)
                speed = telemetry.get_ground_speed()
                target_speed = np.linalg.norm(target_vel[:2])
                
                # Calculate closing rate (positive when approaching)
                if error_horizontal > 0.1:  # Avoid division by zero
                    error_direction = (target_pos - current_ned)[:2] / error_horizontal
                    drone_velocity_horizontal = telemetry.get_velocity_ned()[:2]
                    # Positive when approaching target
                    closing_rate = np.dot(error_direction, drone_velocity_horizontal)
                else:
                    closing_rate = 0
                
                eta = error_horizontal / closing_rate if closing_rate > 0.1 else float('inf')
                
                # Clean terminal output
                print(f"\r{'Time:':<6} {elapsed:>6.1f}s | "
                      f"{'Dist:':<5} {error_3d:>5.1f}m | "
                      f"{'H-Dist:':<7} {error_horizontal:>5.1f}m | "
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

                
        
        # After the pursuit loop:
        self.mission_stats['pursuit_duration'] = time.time() - self.mission_start_time
        print("\n" + "="*60 + "\n")  # Clean line after pursuit

        # If target was acquired, run proximity behavior
        if self.state_machine.state == MissionState.PROXIMITY:
            await self._execute_proximity_behavior()


    async def _execute_proximity_behavior(self):
        """
        Modular behavior after reaching target proximity.
        Continues current trajectory for mission_hold_time seconds.
        """
        self.logger.info(f"Proximity behavior: continue current trajectory for {self.params.mission_hold_time}s")
        hold_start = time.time()
        while time.time() - hold_start < self.params.mission_hold_time:
            # Get current velocity and yaw from telemetry
            telemetry = await self.telemetry_manager.get_telemetry()
            vn, ve, vd = telemetry.vn_m_s, telemetry.ve_m_s, telemetry.vd_m_s
            yaw = telemetry.yaw_deg

            # Command the current velocity and yaw
            await self.drone.offboard.set_velocity_ned(
                VelocityNedYaw(vn, ve, vd, yaw)
            )

            # Optionally update visualization
            if self.visualizer and self.ekf:
                target_pos, target_vel, target_acc = self.ekf.get_state()
                self.visualizer.update(
                    telemetry,
                    (target_pos, target_vel, target_acc),
                    mission_state="PROXIMITY"
                )

            await asyncio.sleep(self.params.control_loop_period)
        self.state_machine.transition_to(MissionState.LANDING, "Proximity hold complete")
    
    async def _execute_landing(self):
        """Execute landing sequence."""
        
        self.state_machine.transition_to(MissionState.LANDING, "Landing")
        
        if self.params.safety_geofence_action == "RTL":
            await self.drone.offboard.stop()
            await self.drone.action.return_to_launch()
            self.logger.info("Return to launch initiated")
            
            # Wait for landing
            while True:
                telemetry = await self.telemetry_manager.get_telemetry()
                if telemetry.altitude_agl_m < 0.5:
                    break
                    
                # Update visualization during RTL
                if self.visualizer and self.ekf:
                    target_pos, target_vel, target_acc = self.ekf.get_state()
                    self.visualizer.update(
                        telemetry,
                        (target_pos, target_vel, target_acc),
                        mission_state="RTL"
                    )
                    
                await asyncio.sleep(1.0)
        else:
            # Controlled descent
            while True:
                telemetry = await self.telemetry_manager.get_telemetry()
                if telemetry.altitude_agl_m < 0.5:
                    break
                
                await self.drone.offboard.set_velocity_ned(
                    VelocityNedYaw(0, 0, self.params.mission_descent_speed, 0)
                )
                
                # Update visualization during landing
                if self.visualizer and self.ekf:
                    target_pos, target_vel, target_acc = self.ekf.get_state()
                    self.visualizer.update(
                        telemetry,
                        (target_pos, target_vel, target_acc),
                        mission_state=self.state_machine.state.name
                    )
                
                await asyncio.sleep(self.params.control_loop_period)
            
            await self.drone.offboard.stop()
            await self.drone.action.land()
        
        # Wait for disarm
        await asyncio.sleep(5.0)
        
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
                self.logger.info("Emergency landing executed")
            except:
                self.logger.error("Failed to execute emergency procedures")
    
    async def _cleanup(self):
        """Clean up resources."""
        self.logger.info("Cleaning up...")
        
        if self.telemetry_manager:
            await self.telemetry_manager.stop()
        
        if self.target_source:
            await self.target_source.shutdown()
        
        # Save plot if enabled
        if self.visualizer and self.visualizer.enabled and self.params.save_mission_report:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("reports", exist_ok=True)
            plot_filename = f"reports/mission_plot_{timestamp}.png"
            self.visualizer.save_plot(plot_filename)
        
        if self.visualizer and self.visualizer.enabled:
            plt.ioff()
            plt.show()
    
    def _print_mission_report(self):
        """Print comprehensive mission report and optionally save to CSV."""
        import csv
        
        # Prepare report data
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
        
        # Calculate summary statistics
        total_time = sum(s['duration'] for s in self.state_machine.state_history)
        
        # Build report sections
        report_lines = []
        report_lines.append("\n" + "="*70)
        report_lines.append("MISSION REPORT".center(70))
        report_lines.append("="*70)
        
        # Summary Section
        report_lines.append(f"\n{'MISSION SUMMARY':^70}")
        report_lines.append("-"*70)
        report_lines.append(f"{'Total Mission Duration:':<35} {total_time:>10.1f} seconds")
        report_lines.append(f"{'Final Mission State:':<35} {self.state_machine.state.name:>10}")
        report_lines.append(f"{'Guidance Mode:':<35} {self.params.guidance_mode:>10}")
        
        # Mission Success Status
        if self.mission_stats.get('target_acquired', False):
            report_lines.append(f"{'Target Acquisition:':<35} {'SUCCESS':>10}")
        else:
            report_lines.append(f"{'Target Acquisition:':<35} {'NOT ACHIEVED':>10}")
        
        # GPS Mode Info
        if "ned_velocity" in self.params.guidance_mode:
            if "local" in self.params.guidance_mode:
                ref_info = "PX4 Local (may drift)"
            else:
                ref_mode = "Current Position" if self.params.reference_use_current_position else "Fixed Home"
                ref_info = f"Global ({ref_mode})"
            report_lines.append(f"{'Reference System:':<35} {ref_info:>10}")
        
        # State Timeline
        report_lines.append(f"\n{'STATE TIMELINE':^70}")
        report_lines.append("-"*70)
        report_lines.append(f"{'State':<20} {'Duration (s)':<15} {'Reason':<35}")
        report_lines.append("-"*70)
        for state in self.state_machine.state_history:
            report_lines.append(f"{state['state']:<20} {state['duration']:>10.1f}     {state['reason']:<35}")
        
        # Performance Metrics
        if self.mission_stats:
            report_lines.append(f"\n{'PERFORMANCE METRICS':^70}")
            report_lines.append("-"*70)
            report_lines.append(f"{'Maximum Position Error:':<35} {self.mission_stats.get('max_error', 0):>10.2f} meters")
            report_lines.append(f"{'Minimum Position Error:':<35} {self.mission_stats.get('min_error', 0):>10.2f} meters")
            report_lines.append(f"{'Average Position Error:':<35} {self.mission_stats.get('average_error', 0):>10.2f} meters")
            report_lines.append(f"{'Pursuit Phase Duration:':<35} {self.mission_stats.get('pursuit_duration', 0):>10.1f} seconds")
            report_lines.append(f"{'Maximum Altitude AGL:':<35} {self.mission_stats.get('max_altitude', 0):>10.1f} meters")
            report_lines.append(f"{'Minimum Battery Level:':<35} {self.mission_stats.get('min_battery', 0):>10.0f} %")
            
            # EKF Performance
            if self.ekf and self.mission_stats.get('measurements_accepted', 0) > 0:
                report_lines.append(f"\n{'TARGET TRACKING PERFORMANCE':^70}")
                report_lines.append("-"*70)
                total_meas = (self.mission_stats['measurements_accepted'] + 
                            self.mission_stats['measurements_rejected'])
                accept_rate = 100 * self.mission_stats['measurements_accepted'] / total_meas if total_meas > 0 else 0
                report_lines.append(f"{'Measurement Accept Rate:':<35} {accept_rate:>10.1f} %")
                report_lines.append(f"{'Total Measurements Processed:':<35} {total_meas:>10.0f}")
                report_lines.append(f"{'Measurements Accepted:':<35} {self.mission_stats['measurements_accepted']:>10.0f}")
                report_lines.append(f"{'Measurements Rejected (Outliers):':<35} {self.mission_stats['measurements_rejected']:>10.0f}")
                
                if self.ekf.is_initialized:
                    _, uncertainty = self.ekf.get_uncertainty()
                    report_lines.append(f"{'Final Position Uncertainty:':<35} {uncertainty:>10.2f} meters")
                    report_lines.append(f"{'Time Since Last Measurement:':<35} {self.ekf.time_since_measurement():>10.1f} seconds")
        
        # Mission Result
        report_lines.append("\n" + "="*70)
        if self.state_machine.state == MissionState.LANDED:
            if self.mission_stats.get('target_acquired', False):
                report_lines.append("MISSION SUCCESS - TARGET INTERCEPTED".center(70))
                report_lines.append(f"Target successfully tracked and intercepted within {self.params.mission_target_threshold}m threshold".center(70))
            elif self.mission_stats.get('min_error', float('inf')) < self.params.mission_target_threshold * 2:
                report_lines.append("MISSION COMPLETE - CLOSE APPROACH".center(70))
                report_lines.append(f"Minimum distance to target: {self.mission_stats.get('min_error', 0):.2f}m".center(70))
            else:
                report_lines.append("MISSION COMPLETE - TARGET TRACKED".center(70))
                report_lines.append(f"Minimum distance to target: {self.mission_stats.get('min_error', 0):.2f}m".center(70))
        else:
            report_lines.append(f"MISSION INCOMPLETE - ENDED IN {self.state_machine.state.name}".center(70))
            if self.state_machine.emergency_reason:
                report_lines.append(f"Reason: {self.state_machine.emergency_reason}".center(70))
        report_lines.append("="*70 + "\n")
        
        # Print to console
        report_content = '\n'.join(report_lines)
        print(report_content)
        
        # Save to CSV if enabled
        if hasattr(self.params, 'save_mission_report') and self.params.save_mission_report:
            # Create reports directory
            os.makedirs("reports", exist_ok=True)
            
            # Save text report
            text_filename = f"reports/mission_report_{timestamp_str}.txt"
            with open(text_filename, 'w') as f:
                f.write(report_content)
            
            # Prepare CSV data
            csv_filename = f"reports/mission_report_{timestamp_str}.csv"
            
            with open(csv_filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                
                # Header information
                writer.writerow(['Mission Report', timestamp.strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow([])
                
                # Mission Summary
                writer.writerow(['MISSION SUMMARY'])
                writer.writerow(['Metric', 'Value'])
                writer.writerow(['Total Duration (s)', f'{total_time:.1f}'])
                writer.writerow(['Final State', self.state_machine.state.name])
                writer.writerow(['Guidance Mode', self.params.guidance_mode])
                writer.writerow(['Target Acquired', 'Yes' if self.mission_stats.get('target_acquired', False) else 'No'])
                writer.writerow([])
                
                # State Timeline
                writer.writerow(['STATE TIMELINE'])
                writer.writerow(['State', 'Duration (s)', 'Start Time', 'Reason'])
                cumulative_time = 0
                for state in self.state_machine.state_history:
                    writer.writerow([
                        state['state'],
                        f"{state['duration']:.1f}",
                        f"{cumulative_time:.1f}",
                        state['reason']
                    ])
                    cumulative_time += state['duration']
                writer.writerow([])
                
                # Performance Metrics
                if self.mission_stats:
                    writer.writerow(['PERFORMANCE METRICS'])
                    writer.writerow(['Metric', 'Value', 'Unit'])
                    writer.writerow(['Max Position Error', f"{self.mission_stats.get('max_error', 0):.2f}", 'meters'])
                    writer.writerow(['Min Position Error', f"{self.mission_stats.get('min_error', 0):.2f}", 'meters'])
                    writer.writerow(['Average Position Error', f"{self.mission_stats.get('average_error', 0):.2f}", 'meters'])
                    writer.writerow(['Pursuit Duration', f"{self.mission_stats.get('pursuit_duration', 0):.1f}", 'seconds'])
                    writer.writerow(['Max Altitude AGL', f"{self.mission_stats.get('max_altitude', 0):.1f}", 'meters'])
                    writer.writerow(['Min Battery Level', f"{self.mission_stats.get('min_battery', 0):.0f}", '%'])
                    writer.writerow([])
                    
                    # EKF Performance
                    if self.ekf and self.mission_stats.get('measurements_accepted', 0) > 0:
                        writer.writerow(['EKF PERFORMANCE'])
                        writer.writerow(['Metric', 'Value', 'Unit'])
                        total_meas = (self.mission_stats['measurements_accepted'] + 
                                    self.mission_stats['measurements_rejected'])
                        accept_rate = 100 * self.mission_stats['measurements_accepted'] / total_meas if total_meas > 0 else 0
                        writer.writerow(['Measurement Accept Rate', f"{accept_rate:.1f}", '%'])
                        writer.writerow(['Total Measurements', total_meas, 'count'])
                        writer.writerow(['Accepted Measurements', self.mission_stats['measurements_accepted'], 'count'])
                        writer.writerow(['Rejected Measurements', self.mission_stats['measurements_rejected'], 'count'])
                        
                        if self.ekf.is_initialized:
                            _, uncertainty = self.ekf.get_uncertainty()
                            writer.writerow(['Final Position Uncertainty', f"{uncertainty:.2f}", 'meters'])
                            writer.writerow(['Time Since Last Measurement', f"{self.ekf.time_since_measurement():.1f}", 'seconds'])
                
                writer.writerow([])
                writer.writerow(['Mission Result', 'SUCCESS' if self.mission_stats.get('target_acquired', False) else 'COMPLETE'])
            
            print(f"\nReports saved to:")
            print(f"  - {text_filename}")
            print(f"  - {csv_filename}")
            if os.path.exists(f"reports/mission_plot_{timestamp_str}.png"):
                print(f"  - reports/mission_plot_{timestamp_str}.png")

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def main():
    """Main entry point with configuration options."""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Drone Pursuit System v5.2 - Professional Target Tracking"
    )
    parser.add_argument('--config', type=Path, help='Configuration file (YAML or JSON)')
    parser.add_argument('--mode', choices=['local_ned_velocity', 'global_ned_velocity', 
                                          'body_velocity', 'global_position'],
                       help='Override guidance mode')
    parser.add_argument('--connection', type=str, help='Override connection string')
    parser.add_argument('--no-viz', action='store_true', help='Disable visualization')
    parser.add_argument('--no-save', action='store_true', help='Do not save mission report')
    
    args = parser.parse_args()
    
    # Create parameters
    if args.config and args.config.exists():
        params = InterceptionParameters.from_file(args.config)
        print(f"Loaded configuration from: {args.config}")
    else:
        params = InterceptionParameters()
    
    # Apply command line overrides
    if args.mode:
        params.guidance_mode = args.mode
        print(f"Guidance mode override: {args.mode}")
    
    if args.connection:
        params.system_connection = args.connection
        print(f"Connection override: {args.connection}")
    
    if args.no_viz:
        params.viz_enabled = False
        print("Visualization disabled")
    
    if args.no_save:
        params.save_mission_report = False
        print("Report saving disabled")
    
    # Create and run mission
    executor = MissionExecutor(params)
    await executor.run_mission()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nMission aborted by user")
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()