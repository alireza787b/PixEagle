#!/usr/bin/env python3
"""
Production-Ready Drone Pursuit System v6.0 - Multi-Source Target Framework
==========================================================================

Professional autonomous target tracking system with multi-source target input support.
Supports camera frame, external tracker NED, GPS coordinates, and simulated targets.

Target Input Modes:
1. Camera API - Target detection in camera frame coordinates
2. External Tracker - NED coordinates from external tracking system
3. GPS Feed - Direct lat/lon/alt target positions
4. Simulated - Built-in target simulation for testing

Guidance Modes:
1. local_ned_velocity: Uses PX4 local NED (non-GPS compatible, but may drift)
2. global_ned_velocity: Recalculates NED from geodetic (GPS drift mitigation)  
3. body_velocity: Body frame control (uses global reference)
4. global_position: Direct position commands to PX4

Key Features in v6.0:
- Multi-source target framework with fusion
- Flexible coordinate frame support
- Quality-aware measurement fusion
- Async target source management
- Backward compatible with v5.2


Changes in v6.1:
- Fixed velocity oscillation in fallback state with exponential smoothing
- Added coordinated flight mode where drone faces velocity vector
- Improved velocity estimation with sanity checks
- Added runtime yaw mode switching capability

Key Features:
- Smooth velocity display without flickering
- Multiple yaw control modes (target tracking, coordinated, fixed, manual)
- Configurable yaw smoothing and rate limiting
- Backward compatible with existing configurations

Author: Alireza Ghaderi (@alireza787b)
Version: 6.1 Multi-Source
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
from collections import deque

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
import os
from datetime import datetime


# For HTTP/WebSocket sources (optional dependencies)
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

warnings.filterwarnings('ignore', category=UserWarning)

class YawControlMode(Enum):
    """Yaw control modes for different flight behaviors."""
    TARGET_TRACKING = "target_tracking"  # Always face target (default)
    COORDINATED = "coordinated"          # Face velocity vector
    FIXED = "fixed"                      # Maintain fixed heading
    MANUAL = "manual"                    # User-controlled yaw

# =============================================================================
# FILE: interceptor_params.py
# PATH: /interceptor_params.py
# Centralized configuration management with multi-source support
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
        self.mission_target_threshold = 5.0          # meters
        self.mission_hold_time = 3.0                 # seconds after reaching target
        
        # ===== Safety Limits =====
        self.safety_min_altitude = 2.0               # meters AGL
        self.safety_max_altitude = 100.0             # meters AGL
        self.safety_max_distance = 500.0             # meters from home
        self.safety_geofence_action = "RTL"          # RTL or LOITER
        self.safety_battery_min_voltage = 14.0       # volts
        self.safety_battery_critical_voltage = 13.5  # volts
        self.safety_telemetry_timeout = 5.0          # seconds
        
        # ===== Legacy Target Definition (for backward compatibility) =====
        self.target_initial_position = [-150.0, 300.0, -50.0]    # [N, E, D] meters
        self.target_initial_velocity = [8.0, -2.0, -0.2]      # [vN, vE, vD] m/s
        self.target_initial_acceleration = [0.0, 0.0, 0]   # [aN, aE, aD] m/s² (vehicle only, no gravity!)
        
        # ===== Target Maneuvering =====
        self.target_maneuver_amplitudes = [0.0, 0.0, 0.0]    # m/s² per axis
        self.target_maneuver_frequencies = [0.0, 0.0, 0.0] # Hz per axis
        self.target_maneuver_phases = None                   # radians (None = random)
        
        # ===== Multi-Source Target Configuration =====
        # Camera source
        self.target_camera_enabled = False           # Enable camera target source
        self.target_camera_endpoint = "http://camera-server:8080/api/v1/target"
        self.target_camera_api_key = None            # API key if required
        self.target_camera_timeout = 1.0             # seconds
        self.target_camera_fps = 30.0                # expected FPS
        
        # External tracker source
        self.target_tracker_enabled = False          # Enable external tracker
        self.target_tracker_url = "ws://tracker-server:9090/targets"
        self.target_tracker_origin_lat = 0.0         # Tracker origin latitude
        self.target_tracker_origin_lon = 0.0         # Tracker origin longitude  
        self.target_tracker_origin_alt = 0.0         # Tracker origin altitude
        self.target_tracker_rate = 50.0              # Hz
        
        # GPS target feed
        self.target_gps_enabled = False              # Enable GPS target feed
        self.target_gps_endpoint = "https://target-provider.com/api/position"
        self.target_gps_rate = 1.0                   # Hz
        
        # Simulation source (always available as fallback)
        self.target_simulation_enabled = True        # Enable simulation
        
        # Fusion configuration
        self.target_fusion_strategy = "priority"     # priority, weighted, kalman
        
        # Legacy compatibility
        self.target_source_type = "auto"             # "auto", "simulated", "camera_api"
        self.target_camera_endpoint_legacy = self.target_camera_endpoint
        self.target_camera_api_key_legacy = self.target_camera_api_key
        
        self.control_yaw_mode = "coordinated"      # Default mode target_tracking, coordinated
        self.control_coordinated_min_speed = 2.0       # Min speed for coordinated mode (m/s)
        self.control_coordinated_yaw_rate = 45.0       # Max yaw rate in coordinated mode (deg/s)
        self.control_fixed_yaw_angle = 0.0             # Fixed yaw angle (degrees)
        self.control_manual_yaw_angle = 0.0            # Manual yaw setpoint (degrees)
        self.control_yaw_smoothing = 0.8               # Yaw command smoothing (0-1)
        
        # ===== Camera Configuration =====
        self.camera_mount_roll = 0.0                 # degrees
        self.camera_mount_pitch = 0.0             # degrees (negative = down)
        self.camera_mount_yaw = 0.0                  # degrees
        self.camera_has_gimbal = False               # gimbal support flag
        
        # ===== Guidance Mode Selection =====
        self.guidance_mode = "global_position"    
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
        self.guidance_position_lead_time = 1       # seconds (for position modes)
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


        # Adaptive measurement noise
        self.ekf_timeout_threshold = 2.0          # Time threshold for target loss (seconds)
        self.ekf_high_trust_noise = 0.01          # Low noise for established tracking
        self.ekf_normal_trust_noise = self.ekf_measurement_noise  # Default noise
        self.ekf_reacquisition_noise = 0.1        # Medium noise for reacquisition

        # Initial state uncertainty
        self.ekf_initial_velocity_uncertainty = 10.0    # m/s - high if velocity unknown
        self.ekf_initial_position_uncertainty = 5.0     # m - moderate position uncertainty
        self.ekf_initial_acceleration_uncertainty = 5.0 # m/s² - high if acceleration unknown

        # Mahalanobis gating
        self.ekf_innovation_threshold = 0.5       # Innovation magnitude threshold
        self.ekf_chi2_confidence = 0.997          # 99.7% confidence for gating
        self.ekf_gate_scale_factor = 1.2          # P inflation factor on rejection
        self.ekf_innovation_norm_threshold = 5.0  # meters - for adaptive noise

        # Dynamic process noise
        self.ekf_process_noise_scale = 2.0        # Maximum Q scale factor
        self.ekf_process_noise_decay = 0.95      # Decay rate for Q scale
        
        
        # ===== EKF Warm-up and Health Parameters =====
        # Enable/disable control
        self.ekf_auto_enable = True              # Auto-enable after warm-up
        self.ekf_warm_up_time = 3.0              # Warm-up period (seconds)
        self.ekf_warm_up_measurements = 10       # Min measurements for warm-up

        # Velocity initialization
        self.ekf_velocity_init_method = 'finite_difference'  # 'zero', 'finite_difference'
        self.ekf_velocity_init_samples = 3       # Samples for velocity estimation

        # Health monitoring thresholds
        self.ekf_max_innovation_norm = 20.0      # Max acceptable innovation (meters)
        self.ekf_max_state_jump = 50.0          # Max position jump (meters)
        self.ekf_max_velocity = 50.0            # Max velocity (m/s)
        self.ekf_max_acceleration = 20.0        # Max acceleration (m/s²)
        self.ekf_divergence_threshold = 100.0   # Max uncertainty before reset (meters)

        # Recovery parameters
        self.ekf_recovery_measurements = 5       # Good measurements to recover
        self.ekf_reset_cooldown = 2.0           # Cooldown between resets (seconds)
        
        # ===== Visualization =====
        self.viz_enabled = True
        self.viz_update_rate = 10.0                   # Hz (reduced for cleaner display)
        self.viz_path_history_length = 200           # points (reduced for clarity)
        self.viz_show_predictions = True
        self.viz_show_uncertainty = True
        self.viz_history_length = 1000               # Maximum history points
        self.save_mission_report = True              # Save mission report and plots
        
        # ===== System Configuration =====
        self.system_connection = "udp://:14540"      # MAVSDK connection
        self.system_log_level = "INFO"               # logging level
        self.system_log_file = "pursuit_mission.log" # log file path
        
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
        
        valid_fusion = ["priority", "weighted", "kalman"]
        if self.target_fusion_strategy not in valid_fusion:
            errors.append(f"Invalid fusion strategy: {self.target_fusion_strategy}")
        
        return errors

# =============================================================================
# FILE: target_framework/core.py
# PATH: /target_framework/core.py
# Core interfaces and data structures for multi-source target framework
# =============================================================================

class ReferenceFrame(Enum):
    """Supported reference frames for target measurements"""
    CAMERA = auto()          # Camera body frame
    BODY = auto()            # Drone body frame
    LOCAL_NED = auto()       # Local NED (arbitrary origin)
    GLOBAL_NED = auto()      # NED from home position
    GEODETIC = auto()        # Lat/Long/Alt (WGS84)
    ECEF = auto()           # Earth-Centered Earth-Fixed
    TRACKER_LOCAL = auto()   # External tracker frame

@dataclass
class TargetMeasurement:
    """
    Unified target measurement structure.
    
    This dataclass represents a target measurement from any source,
    including position, optional velocity/acceleration, confidence scores,
    and metadata. All measurements are timestamped and include their
    reference frame information.
    """
    position: np.ndarray               # 3D position in specified frame
    velocity: Optional[np.ndarray]     # 3D velocity (if available)
    acceleration: Optional[np.ndarray] # 3D acceleration (if available)
    timestamp: float                   # Unix timestamp
    frame: ReferenceFrame             # Reference frame
    frame_origin: Optional[Dict[str, float]] = None  # For local frames
    confidence: float = 1.0           # 0-1 confidence score
    covariance: Optional[np.ndarray] = None  # 3x3 or 6x6 or 9x9
    metadata: Dict[str, Any] = field(default_factory=dict)   # Source-specific data
    
    def has_velocity(self) -> bool:
        """Check if velocity data is available"""
        return self.velocity is not None
    
    def has_acceleration(self) -> bool:
        """Check if acceleration data is available"""
        return self.acceleration is not None
    
    def get_age(self) -> float:
        """Get measurement age in seconds"""
        return time.time() - self.timestamp

class TargetSource(ABC):
    """
    Abstract interface for target data sources.
    
    All target sources must implement this interface to provide
    measurements in their native coordinate frame. The framework
    handles all necessary transformations.
    """
    
    def __init__(self, source_id: str, params: Dict[str, Any]):
        self.source_id = source_id
        self.params = params
        self.is_active = False
        self.last_measurement = None
        self.measurement_count = 0
        self.error_count = 0
        self.logger = logging.getLogger(f"{self.__class__.__name__}[{source_id}]")
        
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the source"""
        pass
    
    @abstractmethod
    async def get_measurement(self) -> Optional[TargetMeasurement]:
        """Get latest measurement in source's native frame"""
        pass
    
    @abstractmethod
    def get_required_frames(self) -> List[ReferenceFrame]:
        """Return list of reference frames this source can work with"""
        pass
    
    @abstractmethod
    def get_update_rate(self) -> float:
        """Expected update rate in Hz"""
        pass
    
    async def shutdown(self) -> None:
        """Cleanup resources"""
        self.is_active = False
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get source health metrics"""
        return {
            'source_id': self.source_id,
            'is_active': self.is_active,
            'measurement_count': self.measurement_count,
            'error_count': self.error_count,
            'last_measurement_age': self.last_measurement.get_age() if self.last_measurement else float('inf'),
            'error_rate': self.error_count / max(1, self.measurement_count)
        }

# =============================================================================
# FILE: frame_utils.py
# PATH: /frame_utils.py
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
# FILE: target_framework/transformations.py
# PATH: /target_framework/transformations.py
# Coordinate transformation pipeline for multi-source framework
# =============================================================================

class CoordinateTransformer:
    """
    Handles all coordinate transformations with caching and validation.
    
    This class provides a unified interface for transforming measurements
    between different coordinate frames, with support for all frame types
    used in the system.
    """
    
    def __init__(self, frame_manager: ReferenceFrameManager):
        self.frame_manager = frame_manager
        self.transform_cache = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
    def transform_measurement(self, 
                            measurement: TargetMeasurement,
                            to_frame: ReferenceFrame,
                            drone_state: Optional['TelemetryData'] = None) -> TargetMeasurement:
        """
        Transform measurement to desired frame.
        
        Args:
            measurement: Target measurement to transform
            to_frame: Desired output frame
            drone_state: Current drone telemetry (required for some transforms)
            
        Returns:
            Transformed measurement in the requested frame
        """
        
        if measurement.frame == to_frame:
            return measurement
        
        # Get transformation path
        path = self._get_transform_path(measurement.frame, to_frame)
        
        # Apply transformations
        result = measurement
        for from_frame, to_frame_step in path:
            result = self._apply_single_transform(result, from_frame, to_frame_step, drone_state)
        
        return result
    
    def _apply_single_transform(self,
                               measurement: TargetMeasurement,
                               from_frame: ReferenceFrame,
                               to_frame: ReferenceFrame,
                               drone_state: Optional['TelemetryData']) -> TargetMeasurement:
        """Apply single transformation step"""
        
        # Camera to Body
        if from_frame == ReferenceFrame.CAMERA and to_frame == ReferenceFrame.BODY:
            pos = self.frame_manager.camera_to_body(measurement.position)
            vel = self.frame_manager.camera_to_body(measurement.velocity) if measurement.has_velocity() else None
            
        # Body to Global NED
        elif from_frame == ReferenceFrame.BODY and to_frame == ReferenceFrame.GLOBAL_NED:
            if drone_state is None:
                raise ValueError("Drone state required for body to NED transformation")
            pos = self.frame_manager.body_to_ned(measurement.position, drone_state.yaw_rad)
            # Add drone position to get absolute position
            drone_ned = self.frame_manager.geodetic_to_ned(
                drone_state.latitude_deg,
                drone_state.longitude_deg, 
                drone_state.altitude_amsl_m
            )
            pos += drone_ned
            vel = self.frame_manager.body_to_ned(measurement.velocity, drone_state.yaw_rad) if measurement.has_velocity() else None
            
        # Camera to Global NED (direct path)
        elif from_frame == ReferenceFrame.CAMERA and to_frame == ReferenceFrame.GLOBAL_NED:
            if drone_state is None:
                raise ValueError("Drone state required for camera to NED transformation")
            # Transform to NED relative
            pos_ned_rel = self.frame_manager.camera_to_ned(measurement.position, drone_state.yaw_rad)
            # Add drone position
            drone_ned = self.frame_manager.geodetic_to_ned(
                drone_state.latitude_deg,
                drone_state.longitude_deg, 
                drone_state.altitude_amsl_m
            )
            pos = pos_ned_rel + drone_ned
            vel = self.frame_manager.camera_to_ned(measurement.velocity, drone_state.yaw_rad) if measurement.has_velocity() else None
            
        # Local NED to Global NED
        elif from_frame == ReferenceFrame.LOCAL_NED and to_frame == ReferenceFrame.GLOBAL_NED:
            if measurement.frame_origin is None:
                raise ValueError("Frame origin required for local NED transformation")
            
            # Transform from local origin to global
            local_origin_ned = self.frame_manager.geodetic_to_ned(
                measurement.frame_origin['lat'],
                measurement.frame_origin['lon'],
                measurement.frame_origin['alt']
            )
            pos = measurement.position + local_origin_ned
            vel = measurement.velocity  # Velocity unchanged
            
        # Geodetic to Global NED
        elif from_frame == ReferenceFrame.GEODETIC and to_frame == ReferenceFrame.GLOBAL_NED:
            pos = self.frame_manager.geodetic_to_ned(
                measurement.position[0],  # lat
                measurement.position[1],  # lon
                measurement.position[2]   # alt
            )
            # TODO: Handle velocity transformation if needed
            vel = None
            
        else:
            raise NotImplementedError(f"Transform from {from_frame} to {to_frame} not implemented")
        
        # Create transformed measurement
        return TargetMeasurement(
            position=pos,
            velocity=vel,
            acceleration=measurement.acceleration,  # TODO: Transform acceleration
            timestamp=measurement.timestamp,
            frame=to_frame,
            frame_origin=None,  # Clear origin after transformation
            confidence=measurement.confidence,
            covariance=self._transform_covariance(measurement.covariance, from_frame, to_frame),
            metadata=measurement.metadata
        )
    
    def _get_transform_path(self, from_frame: ReferenceFrame, to_frame: ReferenceFrame) -> List[Tuple]:
        """Get transformation path between frames"""
        # Define transformation graph
        # This is simplified - you'd want a proper graph search
        
        # All paths go through GLOBAL_NED as the common frame
        if to_frame == ReferenceFrame.GLOBAL_NED:
            if from_frame == ReferenceFrame.CAMERA:
                return [(ReferenceFrame.CAMERA, ReferenceFrame.GLOBAL_NED)]
            elif from_frame == ReferenceFrame.BODY:
                return [(ReferenceFrame.BODY, ReferenceFrame.GLOBAL_NED)]
            elif from_frame == ReferenceFrame.LOCAL_NED:
                return [(ReferenceFrame.LOCAL_NED, ReferenceFrame.GLOBAL_NED)]
            elif from_frame == ReferenceFrame.GEODETIC:
                return [(ReferenceFrame.GEODETIC, ReferenceFrame.GLOBAL_NED)]
        
        # For now, all transformations go through GLOBAL_NED
        if from_frame != ReferenceFrame.GLOBAL_NED and to_frame != ReferenceFrame.GLOBAL_NED:
            return self._get_transform_path(from_frame, ReferenceFrame.GLOBAL_NED) + \
                   self._get_transform_path(ReferenceFrame.GLOBAL_NED, to_frame)
        
        raise NotImplementedError(f"No path from {from_frame} to {to_frame}")
    
    def _transform_covariance(self, covariance: Optional[np.ndarray], 
                             from_frame: ReferenceFrame, 
                             to_frame: ReferenceFrame) -> Optional[np.ndarray]:
        """Transform covariance matrix between frames"""
        # TODO: Implement proper covariance transformation
        # For now, return unchanged
        return covariance

# =============================================================================
# FILE: telemetry_manager.py
# PATH: /telemetry_manager.py
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
# FILE: target_tracker.py
# PATH: /target_tracker.py
# Enhanced Extended Kalman Filter with warm-up and auto-recovery
# =============================================================================

class EKFHealthMonitor:
    """
    Monitors EKF health and determines when to trust/reset the filter.
    """
    
    def __init__(self, params: InterceptionParameters):
        self.params = params
        
        # Health thresholds
        self.max_innovation_norm = getattr(params, 'ekf_max_innovation_norm', 20.0)  # meters
        self.max_state_jump = getattr(params, 'ekf_max_state_jump', 50.0)  # meters
        self.max_velocity = getattr(params, 'ekf_max_velocity', 50.0)  # m/s
        self.max_acceleration = getattr(params, 'ekf_max_acceleration', 20.0)  # m/s²
        self.divergence_threshold = getattr(params, 'ekf_divergence_threshold', 100.0)  # meters
        
        # Recovery parameters
        self.consecutive_good_measurements = getattr(params, 'ekf_recovery_measurements', 5)
        self.reset_cooldown = getattr(params, 'ekf_reset_cooldown', 2.0)  # seconds
        
        # State tracking
        self.innovation_history = deque(maxlen=10)
        self.position_history = deque(maxlen=5)
        self.good_measurement_count = 0
        self.last_reset_time = 0
        self.is_healthy = True
        self.health_score = 1.0
        
    def check_innovation(self, innovation: np.ndarray) -> bool:
        """Check if innovation is reasonable."""
        norm = np.linalg.norm(innovation)
        self.innovation_history.append(norm)
        
        if norm > self.max_innovation_norm:
            self.good_measurement_count = 0
            return False
        
        self.good_measurement_count += 1
        return True
    
    def check_state_jump(self, new_pos: np.ndarray) -> bool:
        """Check for unreasonable state jumps."""
        if len(self.position_history) > 0:
            last_pos = self.position_history[-1]
            jump = np.linalg.norm(new_pos - last_pos)
            
            if jump > self.max_state_jump:
                return False
        
        self.position_history.append(new_pos.copy())
        return True
    
    def check_velocity(self, velocity: np.ndarray) -> bool:
        """Check if velocity is reasonable."""
        vel_norm = np.linalg.norm(velocity)
        return vel_norm <= self.max_velocity
    
    def check_divergence(self, uncertainty: float) -> bool:
        """Check if filter has diverged based on uncertainty."""
        return uncertainty <= self.divergence_threshold
    
    def update_health_score(self, innovation_ok: bool, state_ok: bool, 
                           velocity_ok: bool, divergence_ok: bool):
        """Update overall health score."""
        # Weight different factors
        weights = {
            'innovation': 0.3,
            'state': 0.3,
            'velocity': 0.2,
            'divergence': 0.2
        }
        
        score = (weights['innovation'] * float(innovation_ok) +
                weights['state'] * float(state_ok) +
                weights['velocity'] * float(velocity_ok) +
                weights['divergence'] * float(divergence_ok))
        
        # Smooth health score
        self.health_score = 0.7 * self.health_score + 0.3 * score
        
        # Determine if healthy
        self.is_healthy = self.health_score > 0.5
    
    def should_reset(self) -> bool:
        """Determine if EKF should be reset."""
        current_time = time.time()
        
        # Check cooldown
        if current_time - self.last_reset_time < self.reset_cooldown:
            return False
        
        # Reset if unhealthy for too long
        if not self.is_healthy and self.good_measurement_count == 0:
            self.last_reset_time = current_time
            return True
        
        return False
    
    def has_recovered(self) -> bool:
        """Check if filter has recovered after being unhealthy."""
        return self.good_measurement_count >= self.consecutive_good_measurements


class TargetTrackingEKF:
    """
    Extended Kalman Filter with warm-up period and auto-recovery.
    
    Features:
    - Warm-up period for initial learning
    - Automatic health monitoring
    - Fallback to raw measurements
    - Auto-reset on divergence
    - Configurable enable/disable
    """
    
    def __init__(self, params: InterceptionParameters):
        """Initialize EKF with enhanced robustness parameters."""
        self.params = params
        self.dt = params.ekf_dt
        
        # EKF enable/disable control
        self.ekf_enabled = params.ekf_enabled
        self.ekf_auto_enable = getattr(params, 'ekf_auto_enable', True)
        self.ekf_warm_up_time = getattr(params, 'ekf_warm_up_time', 3.0)  # seconds
        self.ekf_warm_up_measurements = getattr(params, 'ekf_warm_up_measurements', 10)
        
        # State model selection
        self.use_acceleration = params.ekf_estimate_acceleration if hasattr(params, 'ekf_estimate_acceleration') else False
        
        if self.use_acceleration:
            self.ekf = ExtendedKalmanFilter(dim_x=9, dim_z=3)
        else:
            self.ekf = ExtendedKalmanFilter(dim_x=6, dim_z=3)
        
        # Health monitor
        self.health_monitor = EKFHealthMonitor(params)
        
        # Enhanced initialization parameters
        self.velocity_init_method = getattr(params, 'ekf_velocity_init_method', 'finite_difference')  # 'zero', 'finite_difference', 'from_measurement'
        self.velocity_init_samples = getattr(params, 'ekf_velocity_init_samples', 3)
        
        # State tracking
        self.is_initialized = False
        self.is_warmed_up = False
        self.warm_up_start_time = None
        self.warm_up_measurements = 0
        self.measurement_buffer = deque(maxlen=self.velocity_init_samples)
        
        # Fallback state (raw measurements)
        self.fallback_position = None
        self.fallback_velocity = None
        self.fallback_measurement_times = deque(maxlen=5)
        self.fallback_positions = deque(maxlen=5)
        
        # All other robustness parameters from previous implementation
        self.timeout_threshold = getattr(params, 'ekf_timeout_threshold', 2.0)
        self.high_trust_noise = getattr(params, 'ekf_high_trust_noise', 0.01)
        self.normal_trust_noise = getattr(params, 'ekf_normal_trust_noise', params.ekf_measurement_noise)
        self.reacquisition_noise = getattr(params, 'ekf_reacquisition_noise', 0.1)
        
        self.initial_velocity_uncertainty = getattr(params, 'ekf_initial_velocity_uncertainty', 10.0)
        self.initial_position_uncertainty = getattr(params, 'ekf_initial_position_uncertainty', 5.0)
        self.initial_acceleration_uncertainty = getattr(params, 'ekf_initial_acceleration_uncertainty', 5.0)
        
        self.innovation_threshold = getattr(params, 'ekf_innovation_threshold', 0.5)
        self.chi2_confidence = getattr(params, 'ekf_chi2_confidence', 0.997)
        self.gate_scale_factor = getattr(params, 'ekf_gate_scale_factor', 1.2)
        
        self.process_noise_scale = getattr(params, 'ekf_process_noise_scale', 2.0)
        self.innovation_norm_threshold = getattr(params, 'ekf_innovation_norm_threshold', 5.0)
        self.process_noise_decay = getattr(params, 'ekf_process_noise_decay', 0.95)
        
        # Runtime state
        self.last_reset_time = 0.0
        self.init_time = time.time()
        self.last_measurement_time = None
        self.measurement_count = 0
        self.outlier_count = 0
        self.consecutive_outliers = 0
        self.reacquisition_mode = False
        self.dynamic_q_scale = 1.0
        
        # Initialize matrices
        self._setup_ekf()
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"EKF initialized - enabled: {self.ekf_enabled}, "
                        f"auto_enable: {self.ekf_auto_enable}, "
                        f"warm_up_time: {self.ekf_warm_up_time}s")
    
    def _setup_ekf(self):
        """Setup EKF matrices with enhanced initial uncertainties."""
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
            self.ekf.R = np.eye(3) * (self.normal_trust_noise ** 2)
            
            pos_var = self.initial_position_uncertainty ** 2
            vel_var = self.initial_velocity_uncertainty ** 2
            acc_var = self.initial_acceleration_uncertainty ** 2
            self.ekf.P = np.diag([pos_var, pos_var, pos_var, 
                                 vel_var, vel_var, vel_var,
                                 acc_var, acc_var, acc_var])
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
            self.ekf.R = np.eye(3) * (self.normal_trust_noise ** 2)
            
            pos_var = self.initial_position_uncertainty ** 2
            vel_var = self.initial_velocity_uncertainty ** 2
            self.ekf.P = np.diag([pos_var, pos_var, pos_var,
                                 vel_var, vel_var, vel_var])
    
    def _estimate_initial_velocity(self, measurements: List[Tuple[np.ndarray, float]]) -> Optional[np.ndarray]:
        """Estimate initial velocity from measurement history."""
        if len(measurements) < 2:
            return None
        
        if self.velocity_init_method == 'finite_difference':
            # Use finite difference on recent measurements
            positions = np.array([m[0] for m in measurements])
            times = np.array([m[1] for m in measurements])
            
            # Simple finite difference
            if len(measurements) == 2:
                dt = times[1] - times[0]
                if dt > 0:
                    velocity = (positions[1] - positions[0]) / dt
                    return velocity
            else:
                # Use least squares for multiple points
                velocities = []
                for i in range(1, len(measurements)):
                    dt = times[i] - times[i-1]
                    if dt > 0:
                        vel = (positions[i] - positions[i-1]) / dt
                        velocities.append(vel)
                
                if velocities:
                    return np.mean(velocities, axis=0)
        
        return None
    
    def _update_fallback_state(self, measurement: np.ndarray):
        """Update fallback state with raw measurements and velocity smoothing."""
        current_time = time.time()
        
        self.fallback_position = measurement.copy()
        self.fallback_positions.append(measurement.copy())
        self.fallback_measurement_times.append(current_time)
        
        # Calculate velocity with smoothing
        if len(self.fallback_positions) >= 2:
            # Calculate instantaneous velocity
            dt = self.fallback_measurement_times[-1] - self.fallback_measurement_times[-2]
            if dt > 0 and dt < 1.0:  # Sanity check on time delta
                instant_velocity = (self.fallback_positions[-1] - self.fallback_positions[-2]) / dt
                
                # Apply exponential smoothing to velocity
                if self.fallback_velocity is not None:
                    # Smooth with previous velocity (alpha = 0.3 for smoothing)
                    alpha = 0.3
                    self.fallback_velocity = alpha * instant_velocity + (1 - alpha) * self.fallback_velocity
                else:
                    self.fallback_velocity = instant_velocity
            else:
                # Keep previous velocity if dt is invalid
                if self.fallback_velocity is None:
                    self.fallback_velocity = np.zeros(3)
        else:
            # Not enough measurements yet
            if self.fallback_velocity is None:
                self.fallback_velocity = np.zeros(3)
    
    def initialize(self, position: np.ndarray, 
                   velocity: Optional[np.ndarray] = None,
                   acceleration: Optional[np.ndarray] = None):
        """Initialize filter with warm-up period."""
        # Always update fallback state
        self._update_fallback_state(position)
        
        # Store measurement for velocity estimation
        self.measurement_buffer.append((position.copy(), time.time()))
        
        if not self.ekf_enabled:
            self.logger.info("EKF disabled - using fallback state only")
            return
        
        # Start warm-up period
        if not self.is_initialized:
            self.warm_up_start_time = time.time()
            self.warm_up_measurements = 0
            self.is_warmed_up = False
            self.logger.info("Starting EKF warm-up period")
        
        # Initialize EKF state
        self.ekf.x[0:3] = position
        
        # Smart velocity initialization
        if velocity is not None:
            self.ekf.x[3:6] = velocity
            # Reduce uncertainty if velocity is provided
            for i in [3, 4, 5]:
                self.ekf.P[i, i] = (self.initial_velocity_uncertainty * 0.3) ** 2
        else:
            # Try to estimate velocity from measurements
            estimated_vel = self._estimate_initial_velocity(list(self.measurement_buffer))
            if estimated_vel is not None:
                self.ekf.x[3:6] = estimated_vel
                # Moderate uncertainty for estimated velocity
                for i in [3, 4, 5]:
                    self.ekf.P[i, i] = (self.initial_velocity_uncertainty * 0.5) ** 2
                self.logger.info(f"Initialized with estimated velocity: {estimated_vel}")
            else:
                # No velocity - use zero with high uncertainty
                self.ekf.x[3:6] = np.zeros(3)
                for i in [3, 4, 5]:
                    self.ekf.P[i, i] = self.initial_velocity_uncertainty ** 2
        
        # Handle acceleration
        if self.use_acceleration:
            if acceleration is not None:
                self.ekf.x[6:9] = acceleration
            else:
                self.ekf.x[6:9] = np.zeros(3)
        
        self.is_initialized = True
        self.last_measurement_time = time.time()
        self.reacquisition_mode = False
        self.consecutive_outliers = 0
        self.dynamic_q_scale = 1.0
        
    def _check_warm_up_complete(self) -> bool:
        """Check if warm-up period is complete."""
        if self.is_warmed_up:
            return True
        
        current_time = time.time()
        time_elapsed = current_time - self.warm_up_start_time
        
        # Check both time and measurement count
        if (time_elapsed >= self.ekf_warm_up_time and 
            self.warm_up_measurements >= self.ekf_warm_up_measurements):
            self.is_warmed_up = True
            self.logger.info(f"EKF warm-up complete after {time_elapsed:.1f}s and "
                           f"{self.warm_up_measurements} measurements")
            return True
        
        return False
    
    def predict(self, dt: Optional[float] = None):
        """Predict with warm-up awareness."""
        if not self.is_initialized or not self.ekf_enabled:
            return
        
        # Always run predict to maintain filter state
        if dt and abs(dt - self.dt) > 0.001:
            self.ekf.F = self._get_F(dt)
            self.ekf.Q = self._get_Q(dt)
        else:
            self.ekf.Q = self._get_Q(self.dt)
        
        # Decay dynamic Q scale
        self.dynamic_q_scale = 1.0 + (self.dynamic_q_scale - 1.0) * self.process_noise_decay
        
        # Check for target loss
        current_time = time.time()
        if self.last_measurement_time and (current_time - self.last_measurement_time) > self.timeout_threshold:
            if not self.reacquisition_mode:
                self.reacquisition_mode = True
                self.logger.info("Target lost - entering reacquisition mode")
                self.dynamic_q_scale *= 1.5
        
        self.ekf.predict()
        self._limit_covariance()
    
    def update(self, measurement: np.ndarray) -> bool:
        """Update with warm-up period and health monitoring."""
        # Always update fallback state
        self._update_fallback_state(measurement)
        
        if not self.ekf_enabled:
            return True  # Fallback state updated successfully
        
        if not self.is_initialized:
            self.initialize(measurement)
            return True
        
        # Store measurement for velocity estimation
        self.measurement_buffer.append((measurement.copy(), time.time()))
        
        # Increment warm-up counter
        if not self.is_warmed_up:
            self.warm_up_measurements += 1
        
        # Always run EKF update to learn during warm-up
        z = measurement.flatten()
        
        # Calculate innovation
        y = z - self.ekf.hx(self.ekf.x)
        H = self.ekf.HJacobian(self.ekf.x)
        
        # Health checks
        pos, vel, _ = self.get_state()
        innovation_ok = self.health_monitor.check_innovation(y)
        state_ok = self.health_monitor.check_state_jump(pos)
        velocity_ok = self.health_monitor.check_velocity(vel)
        _, uncertainty = self.get_uncertainty()
        divergence_ok = self.health_monitor.check_divergence(uncertainty)
        
        # Update health score
        self.health_monitor.update_health_score(
            innovation_ok, state_ok, velocity_ok, divergence_ok
        )
        
        # Check if we should reset
        if self.health_monitor.should_reset():
            self.logger.warning("EKF unhealthy - resetting filter")
            self.reset_filter()
            return False
        
        # Continue with normal update process...
        current_time = time.time()
        time_since_last = current_time - self.last_measurement_time if self.last_measurement_time else 0
        
        # Adaptive measurement noise
        if self.reacquisition_mode and time_since_last > self.timeout_threshold:
            R_adaptive = np.eye(3) * (self.reacquisition_noise ** 2)
            self.reacquisition_mode = False
        elif self.consecutive_outliers > 3:
            R_adaptive = np.eye(3) * ((self.normal_trust_noise * 2) ** 2)
        elif self.measurement_count < 10 or not self.is_warmed_up:
            R_adaptive = np.eye(3) * (self.normal_trust_noise ** 2)
        else:
            R_adaptive = np.eye(3) * (self.high_trust_noise ** 2)
        
        # Innovation-based noise scaling
        innovation_norm = np.linalg.norm(y)
        if innovation_norm > self.innovation_norm_threshold:
            noise_scale = 1 + (innovation_norm / self.innovation_norm_threshold)
            R_adaptive *= noise_scale
        
        # Compute innovation covariance
        S = H @ self.ekf.P @ H.T + R_adaptive
        
        # Mahalanobis gating
        try:
            S_inv = np.linalg.inv(S)
            mahalanobis_dist = float(y.T @ S_inv @ y)
            
            chi2_threshold = stats.chi2.ppf(self.chi2_confidence, df=3)
            
            # More permissive during warm-up
            if not self.is_warmed_up:
                chi2_threshold *= 2.0
            elif self.reacquisition_mode:
                chi2_threshold *= 1.5
            
            if mahalanobis_dist > chi2_threshold:
                self.outlier_count += 1
                self.consecutive_outliers += 1
                
                self.ekf.P *= self.gate_scale_factor
                self.dynamic_q_scale *= 1.2
                
                if self.consecutive_outliers > 5:
                    self.dynamic_q_scale = self.process_noise_scale
                
                return False
                
        except np.linalg.LinAlgError:
            self.logger.warning("Singular innovation covariance")
            return False
        
        # Measurement passed gating
        self.consecutive_outliers = 0
        
        # Dynamic process noise
        if innovation_norm > self.innovation_threshold:
            scale_factor = min(innovation_norm / self.innovation_threshold, self.process_noise_scale)
            self.dynamic_q_scale = scale_factor
        
        # Apply update
        self.ekf.R = R_adaptive
        self.ekf.update(z, self.ekf.HJacobian, self.ekf.hx)
        self.ekf.R = np.eye(3) * (self.normal_trust_noise ** 2)
        
        self.last_measurement_time = current_time
        self.measurement_count += 1
        
        # Check warm-up completion
        self._check_warm_up_complete()
        
        return True
    
    def reset_filter(self):
        """Reset the filter to initial state."""
        self.logger.info("Resetting EKF")
        
        # Keep position but reset velocity and covariance
        if self.fallback_position is not None:
            position = self.fallback_position
        else:
            position = self.ekf.x[0:3].copy()
        
        # Re-initialize
        self._setup_ekf()
        self.is_initialized = False
        self.is_warmed_up = False
        self.warm_up_measurements = 0
        self.measurement_count = 0
        self.outlier_count = 0
        self.consecutive_outliers = 0
        self.dynamic_q_scale = 1.0
        
        # Re-initialize with position
        self.initialize(position)
    
    def enable_filter(self):
        """Enable the EKF."""
        if not self.ekf_enabled:
            self.ekf_enabled = True
            self.logger.info("EKF enabled")
            if self.fallback_position is not None:
                self.initialize(self.fallback_position)
    
    def disable_filter(self):
        """Disable the EKF."""
        self.ekf_enabled = False
        self.is_warmed_up = False
        self.logger.info("EKF disabled - using fallback state")
    
    def get_state(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Get current state estimate with fallback and smoothing."""
        # If EKF is disabled or not ready, use fallback
        if not self.ekf_enabled or not self.is_warmed_up or not self.health_monitor.is_healthy:
            if self.fallback_position is not None:
                # Always return non-None velocity
                velocity = self.fallback_velocity if self.fallback_velocity is not None else np.zeros(3)
                return (
                    self.fallback_position.copy(),
                    velocity.copy(),
                    np.zeros(3)  # No acceleration in fallback
                )
            else:
                return np.zeros(3), np.zeros(3), np.zeros(3)
        
        # Use EKF state
        if self.use_acceleration:
            pos = self.ekf.x[0:3].copy()
            vel = self.ekf.x[3:6].copy()
            acc = self.ekf.x[6:9].copy()
        else:
            pos = self.ekf.x[0:3].copy()
            vel = self.ekf.x[3:6].copy()
            acc = np.zeros(3)
        
        # Apply sanity check on velocity
        vel_norm = np.linalg.norm(vel)
        if vel_norm > self.health_monitor.max_velocity:
            # Clip velocity to maximum
            vel = vel * (self.health_monitor.max_velocity / vel_norm)
        
        return pos, vel, acc


        
        # Use EKF state
        if self.use_acceleration:
            pos = self.ekf.x[0:3].copy()
            vel = self.ekf.x[3:6].copy()
            acc = self.ekf.x[6:9].copy()
        else:
            pos = self.ekf.x[0:3].copy()
            vel = self.ekf.x[3:6].copy()
            acc = np.zeros(3)
            
        return pos, vel, acc
    
    def is_ready(self) -> bool:
        """Check if filter is ready to provide estimates."""
        if not self.ekf_enabled:
            return self.fallback_position is not None
        
        return (self.is_initialized and 
                self.is_warmed_up and 
                self.health_monitor.is_healthy)
    
    def get_health_status(self) -> Dict[str, Any]:
        """Enhanced health metrics."""
        if not self.is_initialized:
            return {
                'healthy': False, 
                'reason': 'Not initialized',
                'ekf_enabled': self.ekf_enabled,
                'using_fallback': True
            }
        
        # Basic health checks
        time_since_meas = self.time_since_measurement()
        _, uncertainty = self.get_uncertainty()
        
        health_info = {
            'healthy': self.health_monitor.is_healthy,
            'health_score': self.health_monitor.health_score,
            'ekf_enabled': self.ekf_enabled,
            'is_warmed_up': self.is_warmed_up,
            'using_fallback': not self.ekf_enabled or not self.is_warmed_up or not self.health_monitor.is_healthy,
            'warm_up_progress': f"{self.warm_up_measurements}/{self.ekf_warm_up_measurements}",
            'time_since_measurement': time_since_meas,
            'position_uncertainty': uncertainty,
            'measurement_count': self.measurement_count,
            'outlier_ratio': self.outlier_count / max(1, self.measurement_count),
            'consecutive_outliers': self.consecutive_outliers,
            'dynamic_q_scale': self.dynamic_q_scale,
        }
        
        # Add specific reason if unhealthy
        if not self.health_monitor.is_healthy:
            if uncertainty > self.health_monitor.divergence_threshold:
                health_info['reason'] = f'High uncertainty: {uncertainty:.1f}m'
            elif self.consecutive_outliers > 5:
                health_info['reason'] = 'Multiple consecutive outliers'
            elif time_since_meas > self.timeout_threshold:
                health_info['reason'] = f'No measurements for {time_since_meas:.1f}s'
            else:
                health_info['reason'] = 'Low health score'
        
        return health_info
    
    def update_with_delay(self, measurement: np.ndarray, measurement_time: float) -> bool:
        """Update with delayed measurement - enhanced for robustness."""
        current_time = time.time()
        delay = current_time - measurement_time
        
        if delay > 0.5:  # Reject very old measurements
            self.logger.warning(f"Measurement too old: {delay:.3f}s")
            return False
        
        if delay > 0.01:  # Compensate for delay
            # Save current state
            x_current = self.ekf.x.copy()
            P_current = self.ekf.P.copy()
            Q_scale_current = self.dynamic_q_scale
            
            # Retrodict to measurement time
            F_back = self._get_F(-delay)
            self.ekf.x = F_back @ self.ekf.x
            
            # Increase uncertainty when retrodicting
            Q_back = self._get_Q(abs(delay)) * 2  # Double process noise for retrodiction
            self.ekf.P = F_back @ self.ekf.P @ F_back.T + Q_back
            
            # Update at measurement time
            success = self.update(measurement)
            
            if success:
                # Predict forward to current time
                self.predict(delay)
            else:
                # Restore state if update failed
                self.ekf.x = x_current
                self.ekf.P = P_current
                self.dynamic_q_scale = Q_scale_current
            
            return success
        else:
            return self.update(measurement)

    
    
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
    def _get_F(self, dt: float) -> np.ndarray:
        """Get state transition matrix."""
        if self.use_acceleration:
            F = np.eye(9)
            dt2 = dt * dt / 2
            F[0:3, 3:6] = np.eye(3) * dt
            F[0:3, 6:9] = np.eye(3) * dt2
            F[3:6, 6:9] = np.eye(3) * dt
        else:
            F = np.eye(6)
            F[0:3, 3:6] = np.eye(3) * dt
        return F
    
    def _get_Q(self, dt: float) -> np.ndarray:
        """Get process noise matrix with dynamic scaling."""
        Q_base = self._get_base_Q(dt)
        return Q_base * self.dynamic_q_scale
    
    def _get_base_Q(self, dt: float) -> np.ndarray:
        """Get base process noise matrix."""
        if self.use_acceleration:
            q_acc = 2.0
            Q_single = self._get_Q_single_axis(dt, q_acc)
            Q = block_diag(Q_single, Q_single, Q_single)
            return Q
        else:
            q_pos = 0.1
            q_vel = 0.5
            Q = np.zeros((6, 6))
            Q[0:3, 0:3] = np.eye(3) * q_pos * dt
            Q[3:6, 3:6] = np.eye(3) * q_vel * dt
            return Q
    
    def _get_Q_single_axis(self, dt: float, q: float) -> np.ndarray:
        """Get process noise for single axis."""
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt3 * dt
        dt5 = dt4 * dt
        
        return q * np.array([
            [dt5/20, dt4/8,  dt3/6],
            [dt4/8,  dt3/3,  dt2/2],
            [dt3/6,  dt2/2,  dt]
        ])
    
    def _limit_covariance(self):
        """Limit covariance growth."""
        if self.use_acceleration:
            identity = np.eye(9)
        else:
            identity = np.eye(6)
        
        # Get max allowed variances
        max_pos_var = 900.0  # 30m std
        max_vel_var = 225.0  # 15m/s std
        
        # Limit diagonal elements
        for i in range(3):
            if self.ekf.P[i, i] > max_pos_var:
                self.ekf.P[i, i] = max_pos_var * 0.9
            if self.ekf.P[i+3, i+3] > max_vel_var:
                self.ekf.P[i+3, i+3] = max_vel_var * 0.9
        
        # Ensure positive definite
        self.ekf.P = 0.5 * (self.ekf.P + self.ekf.P.T)
        self.ekf.P += identity * 1e-6
    
    def time_since_measurement(self) -> float:
        """Time since last measurement."""
        if self.last_measurement_time is None:
            return float('inf')
        return time.time() - self.last_measurement_time
    
    def get_uncertainty(self) -> Tuple[np.ndarray, float]:
        """Get position uncertainty."""
        if not self.ekf_enabled or not self.is_initialized:
            # Return high uncertainty when using fallback
            return np.eye(3) * 100, 100.0
            
        pos_cov = self.ekf.P[0:3, 0:3]
        uncertainty = np.sqrt(np.trace(pos_cov) / 3)
        return pos_cov, uncertainty

# =============================================================================
# FILE: target_framework/sources/simulated_source.py
# PATH: /target_framework/sources/simulated_source.py
# Enhanced simulated target source for testing
# =============================================================================

class SimulatedTargetSourceV2(TargetSource):
    """
    Enhanced simulated target for testing with multi-source framework.
    
    This source simulates a target with configurable motion patterns,
    including linear motion, sinusoidal maneuvering, and noise.
    Outputs measurements in camera frame.
    """
    
    def __init__(self, source_id: str, params: Dict[str, Any], frame_manager: ReferenceFrameManager):
        """Initialize simulated target."""
        super().__init__(source_id, params)
        self.frame_manager = frame_manager
        
        # Target model - absolute position in NED
        self.position = np.array(params.get('initial_position', [30.0, 30.0, -20.0]), dtype=float)
        self.velocity = np.array(params.get('initial_velocity', [1.0, 0.0, 0.0]), dtype=float)
        self.acceleration = np.array(params.get('initial_acceleration', [0.0, 0.0, 0.0]), dtype=float)
        
        # Maneuvering parameters
        self.amp   = np.array(params.get('maneuver_amplitudes', [0.0, 0.0, 0.0]))
        self.freq  = np.array(params.get('maneuver_frequencies', [0.0, 0.0, 0.0]))
        # If no explicit phases provided, generate random ones; otherwise use the array
        raw_phase = params.get('maneuver_phases')
        if raw_phase is None:
            self.phase = np.random.random(3) * 2 * np.pi
        else:
            self.phase = np.array(raw_phase)
        
        # Noise parameters
        self.position_noise_std = params.get('position_noise_std', 0.2)  # meters
        self.measurement_rate = params.get('measurement_rate', 30.0)  # Hz
        
        # Simulation state
        self.start_time = None
        self.drone_position = np.zeros(3)
        self.drone_yaw = 0.0
    
    async def initialize(self) -> bool:
        """Initialize simulation."""
        self.start_time = time.time()
        self.is_active = True
        self.logger.info(f"Simulated target initialized at NED position: {self.position}")
        return True
    
    async def get_measurement(self) -> Optional[TargetMeasurement]:
        """Generate simulated measurement in camera frame."""
        if not self.is_active or self.start_time is None:
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
        noise = np.random.normal(0, self.position_noise_std, 3)
        pos_camera += noise
        
        # Simulate confidence based on distance
        distance = np.linalg.norm(relative_ned)
        confidence = np.clip(1.0 - distance / 200.0, 0.3, 1.0)
        
        # Create measurement
        measurement = TargetMeasurement(
            position=pos_camera,
            velocity=None,  # Camera typically doesn't provide velocity
            acceleration=None,
            timestamp=time.time(),
            frame=ReferenceFrame.CAMERA,
            confidence=confidence,
            metadata={
                'source': 'simulated',
                'true_ned_position': current_pos.tolist(),
                'true_ned_velocity': current_vel.tolist(),
                'distance': distance
            }
        )
        
        self.last_measurement = measurement
        self.measurement_count += 1
        
        return measurement
    
    def update_drone_state(self, position: np.ndarray, yaw: float):
        """Update drone state for simulation."""
        self.drone_position = position.copy()
        self.drone_yaw = yaw
    
    def get_required_frames(self) -> List[ReferenceFrame]:
        """Simulated source outputs in camera frame"""
        return [ReferenceFrame.CAMERA]
    
    def get_update_rate(self) -> float:
        """Expected measurement rate"""
        return self.measurement_rate

# =============================================================================
# FILE: target_framework/sources/camera_source.py
# PATH: /target_framework/sources/camera_source.py
# Camera-based target detection source
# =============================================================================

class CameraTargetSource(TargetSource):
    """
    Camera-based target detection source.
    
    Connects to a camera API endpoint to receive target detections
    in camera frame coordinates. Supports both polling and streaming.
    """
    
    def __init__(self, source_id: str, params: Dict[str, Any]):
        super().__init__(source_id, params)
        self.camera_api_url = params.get('api_url', 'http://localhost:8080/target')
        self.api_key = params.get('api_key', None)
        self.timeout = params.get('timeout', 1.0)
        self.fps = params.get('fps', 30.0)
        self.session = None
        
    async def initialize(self) -> bool:
        """Initialize HTTP session"""
        if not AIOHTTP_AVAILABLE:
            self.logger.error("aiohttp not available. Install with: pip install aiohttp")
            return False
            
        try:
            import aiohttp
            self.session = aiohttp.ClientSession()
            self.is_active = True
            self.logger.info(f"Camera source initialized: {self.camera_api_url}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize camera source: {e}")
            return False
    
    async def get_measurement(self) -> Optional[TargetMeasurement]:
        """Get target from camera API"""
        if not self.is_active or not self.session:
            return None
            
        try:
            headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
            
            async with self.session.get(self.camera_api_url, 
                                       headers=headers,
                                       timeout=self.timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse camera detection
                    # Expected format: {"x": float, "y": float, "z": float, "confidence": float, "timestamp": float}
                    position = np.array([
                        data['x'],  # Camera X (typically right)
                        data['y'],  # Camera Y (typically down)  
                        data['z']   # Camera Z (typically forward)
                    ])
                    
                    # Optional velocity if provided
                    velocity = None
                    if 'vx' in data and 'vy' in data and 'vz' in data:
                        velocity = np.array([data['vx'], data['vy'], data['vz']])
                    
                    # Create measurement
                    measurement = TargetMeasurement(
                        position=position,
                        velocity=velocity,
                        acceleration=None,
                        timestamp=data.get('timestamp', time.time()),
                        frame=ReferenceFrame.CAMERA,
                        confidence=data.get('confidence', 0.8),
                        metadata={
                            'detection_id': data.get('id'),
                            'detection_class': data.get('class', 'target'),
                            'bounding_box': data.get('bbox')
                        }
                    )
                    
                    self.last_measurement = measurement
                    self.measurement_count += 1
                    return measurement
                    
                elif response.status == 404:
                    # No target detected
                    return None
                else:
                    self.logger.warning(f"Camera API returned status {response.status}")
                    self.error_count += 1
                    
        except asyncio.TimeoutError:
            self.logger.debug("Camera API timeout")
            self.error_count += 1
        except Exception as e:
            self.logger.error(f"Camera API error: {e}")
            self.error_count += 1
            
        return None
    
    def get_required_frames(self) -> List[ReferenceFrame]:
        return [ReferenceFrame.CAMERA]
    
    def get_update_rate(self) -> float:
        return self.fps
    
    async def shutdown(self) -> None:
        await super().shutdown()
        if self.session:
            await self.session.close()

# =============================================================================
# FILE: target_framework/sources/tracker_source.py
# PATH: /target_framework/sources/tracker_source.py
# External tracking system source
# =============================================================================

class ExternalTrackerSource(TargetSource):
    """
    External tracking system providing NED coordinates.
    
    Connects to an external tracking system via WebSocket to receive
    target positions in a local NED frame. The tracker origin must be
    configured to transform to global coordinates.
    """
    
    def __init__(self, source_id: str, params: Dict[str, Any]):
        super().__init__(source_id, params)
        self.tracker_url = params.get('tracker_url', 'ws://localhost:9090/targets')
        self.tracker_origin = params.get('origin', {
            'lat': 0.0,
            'lon': 0.0,
            'alt': 0.0
        })
        self.rate = params.get('rate', 50.0)
        self.websocket = None
        self.data_queue = asyncio.Queue(maxsize=10)
        self._listener_task = None
        
    async def initialize(self) -> bool:
        """Connect to tracker WebSocket"""
        if not WEBSOCKETS_AVAILABLE:
            self.logger.error("websockets not available. Install with: pip install websockets")
            return False
            
        try:
            import websockets
            self.websocket = await websockets.connect(self.tracker_url)
            self.is_active = True
            # Start listener task
            self._listener_task = asyncio.create_task(self._listen_for_data())
            self.logger.info(f"Connected to tracker: {self.tracker_url}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to tracker: {e}")
            return False
    
    async def _listen_for_data(self):
        """Background task to receive tracker data"""
        while self.is_active and self.websocket:
            try:
                data = await self.websocket.recv()
                parsed = json.loads(data)
                
                # Put in queue, drop old data if full
                if self.data_queue.full():
                    try:
                        self.data_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                await self.data_queue.put(parsed)
                
            except Exception as e:
                self.logger.error(f"Tracker listener error: {e}")
                break
        
        self.is_active = False
    
    async def get_measurement(self) -> Optional[TargetMeasurement]:
        """Get latest tracker measurement"""
        if not self.is_active:
            return None
            
        try:
            # Get latest data with timeout
            data = await asyncio.wait_for(self.data_queue.get(), timeout=0.1)
            
            # Parse tracker data
            # Expected format: {"north": float, "east": float, "down": float, 
            #                   "velocity": {"north": float, "east": float, "down": float},
            #                   "timestamp": float, "target_id": str, "quality": float}
            position = np.array([
                data['north'],
                data['east'],
                data['down']
            ])
            
            velocity = None
            if 'velocity' in data:
                velocity = np.array([
                    data['velocity']['north'],
                    data['velocity']['east'],
                    data['velocity']['down']
                ])
            
            measurement = TargetMeasurement(
                position=position,
                velocity=velocity,
                acceleration=None,
                timestamp=data.get('timestamp', time.time()),
                frame=ReferenceFrame.LOCAL_NED,
                frame_origin=self.tracker_origin,
                confidence=data.get('quality', 1.0),
                metadata={
                    'tracker_id': data.get('target_id'),
                    'tracker_name': data.get('tracker_name', 'external')
                }
            )
            
            self.last_measurement = measurement
            self.measurement_count += 1
            return measurement
            
        except asyncio.TimeoutError:
            # No new data available
            return None
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"Tracker data error: {e}")
            return None
    
    def get_required_frames(self) -> List[ReferenceFrame]:
        return [ReferenceFrame.LOCAL_NED, ReferenceFrame.GLOBAL_NED]
    
    def get_update_rate(self) -> float:
        return self.rate
    
    async def shutdown(self) -> None:
        await super().shutdown()
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self.websocket:
            await self.websocket.close()

# =============================================================================
# FILE: target_framework/sources/gps_source.py
# PATH: /target_framework/sources/gps_source.py
# GPS-based target position source
# =============================================================================

class GPSTargetSource(TargetSource):
    """
    Direct GPS coordinates input source.
    
    Polls an HTTP endpoint to receive target GPS coordinates.
    Can calculate velocity from consecutive positions if not provided.
    """
    
    def __init__(self, source_id: str, params: Dict[str, Any]):
        super().__init__(source_id, params)
        self.api_endpoint = params.get('api_endpoint', 'http://localhost:8080/gps')
        self.api_key = params.get('api_key', None)
        self.rate = params.get('rate', 1.0)
        self.update_interval = 1.0 / self.rate
        self.session = None
        self.last_fetch = 0
        self.position_history = deque(maxlen=5)  # For velocity estimation
        
    async def initialize(self) -> bool:
        """Initialize HTTP session"""
        if not AIOHTTP_AVAILABLE:
            self.logger.error("aiohttp not available. Install with: pip install aiohttp")
            return False
            
        try:
            import aiohttp
            self.session = aiohttp.ClientSession()
            self.is_active = True
            self.logger.info(f"GPS source initialized: {self.api_endpoint}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize GPS source: {e}")
            return False
    
    async def get_measurement(self) -> Optional[TargetMeasurement]:
        """Fetch GPS coordinates"""
        if not self.is_active or not self.session:
            return None
            
        now = time.time()
        if now - self.last_fetch < self.update_interval:
            return None  # Rate limiting
            
        try:
            headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
            
            async with self.session.get(self.api_endpoint, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse GPS data
                    # Expected format: {"latitude": float, "longitude": float, "altitude": float,
                    #                   "timestamp": float, "hdop": float, "satellites": int}
                    position = np.array([
                        data['latitude'],
                        data['longitude'],
                        data['altitude']
                    ])
                    
                    # Store in history for velocity calculation
                    self.position_history.append({
                        'position': position,
                        'timestamp': data.get('timestamp', now)
                    })
                    
                    # Calculate velocity from consecutive positions
                    velocity = None
                    if len(self.position_history) >= 2:
                        velocity = self._estimate_velocity()
                    
                    # Convert HDOP to confidence (lower HDOP = higher confidence)
                    hdop = data.get('hdop', 10.0)
                    confidence = np.clip(1.0 - (hdop - 1.0) / 9.0, 0.1, 1.0)
                    
                    measurement = TargetMeasurement(
                        position=position,
                        velocity=velocity,
                        acceleration=None,
                        timestamp=data.get('timestamp', now),
                        frame=ReferenceFrame.GEODETIC,
                        confidence=confidence,
                        metadata={
                            'satellites': data.get('satellites', 0),
                            'hdop': hdop,
                            'vdop': data.get('vdop'),
                            'fix_type': data.get('fix_type', 'unknown')
                        }
                    )
                    
                    self.last_measurement = measurement
                    self.last_fetch = now
                    self.measurement_count += 1
                    return measurement
                    
                else:
                    self.logger.warning(f"GPS API returned status {response.status}")
                    self.error_count += 1
                    
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"GPS API error: {e}")
            
        return None
    
    def _estimate_velocity(self) -> Optional[np.ndarray]:
        """Estimate velocity from position history"""
        if len(self.position_history) < 2:
            return None
            
        # Use the two most recent positions
        latest = self.position_history[-1]
        previous = self.position_history[-2]
        
        dt = latest['timestamp'] - previous['timestamp']
        if dt <= 0 or dt > 5.0:  # Sanity check
            return None
        
        # Simple velocity approximation
        # TODO: This is simplified - proper implementation would account for Earth curvature
        dlat = latest['position'][0] - previous['position'][0]
        dlon = latest['position'][1] - previous['position'][1]
        dalt = latest['position'][2] - previous['position'][2]
        
        # Convert to approximate m/s (rough approximation)
        lat_avg = (latest['position'][0] + previous['position'][0]) / 2
        velocity = np.array([
            dlat * 111111.0 / dt,  # degrees to meters (latitude)
            dlon * 111111.0 * np.cos(np.radians(lat_avg)) / dt,  # longitude with latitude correction
            dalt / dt  # altitude already in meters
        ])
        
        return velocity
    
    def get_required_frames(self) -> List[ReferenceFrame]:
        return [ReferenceFrame.GEODETIC, ReferenceFrame.GLOBAL_NED]
    
    def get_update_rate(self) -> float:
        return self.rate
    
    async def shutdown(self) -> None:
        await super().shutdown()
        if self.session:
            await self.session.close()

# =============================================================================
# FILE: target_framework/manager.py
# PATH: /target_framework/manager.py
# Multi-source target manager with fusion
# =============================================================================

class TargetManager:
    """
    Manages multiple target sources with fusion and fallback.
    
    This is the main interface for the multi-source target framework.
    It coordinates multiple sources, handles transformations, applies
    fusion strategies, and provides a unified target state output.
    """
    
    def __init__(self, params: InterceptionParameters, 
                 frame_manager: ReferenceFrameManager,
                 ekf: Optional[TargetTrackingEKF] = None):
        self.params = params
        self.frame_manager = frame_manager
        self.ekf = ekf
        self.transformer = CoordinateTransformer(frame_manager)
        
        self.sources: Dict[str, TargetSource] = {}
        self.source_priorities = []  # Ordered list of (priority, source_id)
        self.fusion_strategy = params.target_fusion_strategy  # 'priority', 'weighted', 'kalman'
        
        self.measurement_history = deque(maxlen=100)
        self.current_target_state = None
        self.logger = logging.getLogger(self.__class__.__name__)
        
    def register_source(self, source: TargetSource, priority: int = 0):
        """
        Register a target source with priority.
        
        Args:
            source: Target source instance
            priority: Priority level (lower = higher priority)
        """
        self.sources[source.source_id] = source
        self.source_priorities.append((priority, source.source_id))
        self.source_priorities.sort(key=lambda x: x[0])
        self.logger.info(f"Registered source: {source.source_id} with priority {priority}")
    
    async def initialize_all(self) -> bool:
        """Initialize all registered sources"""
        results = []
        for _, source_id in self.source_priorities:
            source = self.sources[source_id]
            try:
                result = await source.initialize()
                results.append(result)
                if result:
                    self.logger.info(f"Source {source_id} initialized successfully")
                else:
                    self.logger.warning(f"Source {source_id} initialization failed")
            except Exception as e:
                self.logger.error(f"Error initializing {source_id}: {e}")
                results.append(False)
        
        return any(results)  # At least one source must initialize
    
    async def get_target_state(self, drone_state: TelemetryData) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """
        Get fused target state in Global NED frame.
        
        Args:
            drone_state: Current drone telemetry
            
        Returns:
            Tuple of (position, velocity, acceleration) in Global NED frame,
            or None if no valid target data available
        """
        
        measurements = await self._collect_measurements()
        
        if not measurements:
            # No measurements - use prediction if available
            if self.ekf and self.ekf.is_initialized:
                if self.ekf.time_since_measurement() < self.params.ekf_miss_timeout:
                    self.ekf.predict()
                    return self.ekf.get_state()
            return None
        
        # Transform all measurements to Global NED
        transformed = []
        for meas in measurements:
            try:
                ned_meas = self.transformer.transform_measurement(
                    meas, 
                    ReferenceFrame.GLOBAL_NED,
                    drone_state
                )
                transformed.append(ned_meas)
            except Exception as e:
                self.logger.error(f"Transform error for {meas.metadata.get('source', 'unknown')}: {e}")
        
        if not transformed:
            return None
        
        # Store in history
        self.measurement_history.extend(transformed)
        
        # Apply fusion strategy
        if self.fusion_strategy == 'priority':
            fused = self._priority_fusion(transformed)
        elif self.fusion_strategy == 'weighted':
            fused = self._weighted_fusion(transformed)
        else:  # kalman
            fused = self._kalman_fusion(transformed)
        
        if fused and self.ekf:
            # Update EKF
            self.ekf.predict()
            if self.ekf.update(fused.position):
                return self.ekf.get_state()
        
        # Return raw measurement if no EKF
        if fused:
            return (fused.position, 
                    fused.velocity if fused.has_velocity() else np.zeros(3),
                    fused.acceleration if fused.has_acceleration() else np.zeros(3))
        
        return None
    
    async def _collect_measurements(self) -> List[TargetMeasurement]:
        """Collect measurements from all active sources"""
        measurements = []
        
        for _, source_id in self.source_priorities:
            source = self.sources[source_id]
            if not source.is_active:
                continue
                
            try:
                meas = await source.get_measurement()
                if meas and meas.get_age() < 1.0:  # Fresh measurement
                    # Add source info to metadata
                    meas.metadata['source'] = source_id
                    measurements.append(meas)
            except Exception as e:
                self.logger.error(f"Error getting measurement from {source_id}: {e}")
        
        return measurements
    
    def _priority_fusion(self, measurements: List[TargetMeasurement]) -> Optional[TargetMeasurement]:
        """
        Priority-based fusion strategy.
        
        Uses the highest priority measurement that meets confidence threshold.
        Falls back to lower priority sources if needed.
        """
        confidence_threshold = 0.5
        
        # Measurements are already sorted by source priority
        for meas in measurements:
            if meas.confidence >= confidence_threshold:
                self.logger.debug(f"Priority fusion selected source: {meas.metadata.get('source')}")
                return meas
        
        # If no high-confidence measurement, use best available
        if measurements:
            best = max(measurements, key=lambda m: m.confidence)
            self.logger.debug(f"Priority fusion fallback to source: {best.metadata.get('source')}")
            return best
            
        return None
    
    def _weighted_fusion(self, measurements: List[TargetMeasurement]) -> Optional[TargetMeasurement]:
        """
        Weighted average fusion based on confidence scores.
        
        Combines all measurements weighted by their confidence values.
        """
        if not measurements:
            return None
        
        # Calculate weights
        weights = np.array([m.confidence for m in measurements])
        weights = weights / weights.sum()
        
        # Weighted position
        position = np.zeros(3)
        for i, meas in enumerate(measurements):
            position += weights[i] * meas.position
        
        # Weighted velocity (if available)
        velocity = None
        vel_measurements = [m for m in measurements if m.has_velocity()]
        if vel_measurements:
            vel_weights = np.array([m.confidence for m in vel_measurements])
            vel_weights = vel_weights / vel_weights.sum()
            velocity = np.zeros(3)
            for i, meas in enumerate(vel_measurements):
                velocity += vel_weights[i] * meas.velocity
        
        # Use timestamp of most recent measurement
        latest = max(measurements, key=lambda m: m.timestamp)
        
        # Combined confidence
        combined_confidence = np.average([m.confidence for m in measurements], weights=weights)
        
        self.logger.debug(f"Weighted fusion from {len(measurements)} sources, confidence: {combined_confidence:.2f}")
        
        return TargetMeasurement(
            position=position,
            velocity=velocity,
            acceleration=None,
            timestamp=latest.timestamp,
            frame=ReferenceFrame.GLOBAL_NED,
            confidence=combined_confidence,
            metadata={
                'fusion_method': 'weighted',
                'source_count': len(measurements),
                'sources': [m.metadata.get('source', 'unknown') for m in measurements]
            }
        )
    
    def _kalman_fusion(self, measurements: List[TargetMeasurement]) -> Optional[TargetMeasurement]:
        """
        Kalman filter fusion (uses the configured EKF).
        
        This is effectively the same as priority fusion but ensures
        the measurement goes through the EKF for optimal estimation.
        """
        # For now, use priority selection and let the EKF handle the fusion
        return self._priority_fusion(measurements)
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """Get comprehensive diagnostics for all sources and fusion"""
        diagnostics = {
            'sources': {},
            'active_sources': 0,
            'total_sources': len(self.sources),
            'total_measurements': sum(s.measurement_count for s in self.sources.values()),
            'fusion_strategy': self.fusion_strategy,
            'ekf_health': self.ekf.get_health_status() if self.ekf else None,
            'measurement_history_size': len(self.measurement_history)
        }
        
        # Per-source diagnostics
        for source_id, source in self.sources.items():
            health = source.get_health_status()
            diagnostics['sources'][source_id] = health
            if health['is_active']:
                diagnostics['active_sources'] += 1
        
        return diagnostics
    
    async def shutdown_all(self):
        """Shutdown all sources gracefully"""
        for source in self.sources.values():
            try:
                await source.shutdown()
            except Exception as e:
                self.logger.error(f"Error shutting down {source.source_id}: {e}")

# =============================================================================
# FILE: legacy_target_source.py
# PATH: /legacy_target_source.py
# Legacy target source interface for backward compatibility
# =============================================================================

# Keep the original abstract interface for compatibility
class TargetSource_Legacy(ABC):
    """Legacy abstract interface for target data sources."""
    
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

class SimulatedTargetSource(TargetSource_Legacy):
    """Legacy simulated target for backward compatibility."""
    
    def __init__(self, params: InterceptionParameters, 
                 frame_manager: ReferenceFrameManager):
        """Initialize simulated target."""
        self.params = params
        self.frame_manager = frame_manager
        
        # Create the new simulated source
        self._new_source = SimulatedTargetSourceV2(
            'legacy_sim',
            {
                'initial_position': params.target_initial_position,
                'initial_velocity': params.target_initial_velocity,
                'initial_acceleration': params.target_initial_acceleration,
                'maneuver_amplitudes': params.target_maneuver_amplitudes,
                'maneuver_frequencies': params.target_maneuver_frequencies,
                'maneuver_phases': params.target_maneuver_phases,
            },
            frame_manager
        )
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def initialize(self) -> bool:
        """Initialize simulation."""
        return await self._new_source.initialize()
    
    async def get_measurement(self) -> Optional[Dict[str, Any]]:
        """Get measurement in legacy format."""
        measurement = await self._new_source.get_measurement()
        if measurement is None:
            return None
            
        # Convert to legacy format
        return {
            'position': measurement.position,
            'timestamp': measurement.timestamp,
            'confidence': measurement.confidence,
            'frame': 'camera',
            'true_ned_position': measurement.metadata.get('true_ned_position'),
            'true_ned_velocity': measurement.metadata.get('true_ned_velocity')
        }
    
    def update_drone_state(self, position: np.ndarray, yaw: float):
        """Update drone state for simulation."""
        self._new_source.update_drone_state(position, yaw)
    
    async def shutdown(self) -> None:
        """No cleanup needed."""
        await self._new_source.shutdown()

    # Add these properties for backward compatibility
    @property
    def position(self):
        return self._new_source.position
    
    @property
    def velocity(self):
        return self._new_source.velocity
    
    @property
    def acceleration(self):
        return self._new_source.acceleration

class CameraAPITargetSource(TargetSource_Legacy):
    """Legacy camera API integration for backward compatibility."""
    
    def __init__(self, params: InterceptionParameters):
        """Initialize camera API source."""
        self.params = params
        self.endpoint = params.target_camera_endpoint
        self.api_key = params.target_camera_api_key
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Create new camera source
        self._new_source = CameraTargetSource(
            'legacy_camera',
            {
                'api_url': params.target_camera_endpoint,
                'api_key': params.target_camera_api_key,
                'timeout': 1.0,
                'fps': 30.0
            }
        )
    
    async def initialize(self) -> bool:
        """Initialize camera connection."""
        return await self._new_source.initialize()
    
    async def get_measurement(self) -> Optional[Dict[str, Any]]:
        """Get measurement in legacy format."""
        measurement = await self._new_source.get_measurement()
        if measurement is None:
            return None
            
        # Convert to legacy format
        return {
            'position': measurement.position,
            'timestamp': measurement.timestamp,
            'confidence': measurement.confidence,
            'frame': 'camera'
        }
    
    async def shutdown(self) -> None:
        """Close camera connection."""
        await self._new_source.shutdown()

def create_target_source(params: InterceptionParameters,
                        frame_manager: ReferenceFrameManager) -> TargetSource_Legacy:
    """Legacy factory function for backward compatibility."""
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
# FILE: guidance_strategies.py
# PATH: /guidance_strategies.py
# Guidance control strategies
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
        
        # Yaw control state
        self.last_commanded_yaw = None
        self.yaw_mode = YawControlMode(params.control_yaw_mode)
        
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
                          target_velocity: Optional[np.ndarray] = None,
                          drone_velocity_ned: Optional[np.ndarray] = None,
                          current_yaw: float = 0.0) -> float:
        """
        Compute desired yaw angle based on selected mode.
        
        Args:
            error_ned: Position error vector in NED
            target_velocity: Target velocity in NED (for target tracking)
            drone_velocity_ned: Drone velocity in NED (for coordinated mode)
            current_yaw: Current yaw angle in degrees
            
        Returns:
            Desired yaw angle in degrees
        """
        
        if self.yaw_mode == YawControlMode.TARGET_TRACKING:
            # Original behavior - face the target
            if target_velocity is not None and self.params.guidance_yaw_lead_time > 0:
                future_error = error_ned + target_velocity * self.params.guidance_yaw_lead_time
                bearing = math.degrees(math.atan2(future_error[1], future_error[0]))
            else:
                bearing = math.degrees(math.atan2(error_ned[1], error_ned[0]))
            desired_yaw = normalize_angle(bearing)
            
        elif self.yaw_mode == YawControlMode.COORDINATED:
            # Face velocity vector
            if drone_velocity_ned is not None:
                speed = np.linalg.norm(drone_velocity_ned[:2])  # Horizontal speed
                
                if speed >= self.params.control_coordinated_min_speed:
                    # Calculate heading from velocity
                    heading = math.degrees(math.atan2(drone_velocity_ned[1], drone_velocity_ned[0]))
                    desired_yaw = normalize_angle(heading)
                else:
                    # Below minimum speed - maintain current yaw or face target
                    if self.last_commanded_yaw is not None:
                        desired_yaw = self.last_commanded_yaw
                    else:
                        # Fall back to target tracking at low speed
                        bearing = math.degrees(math.atan2(error_ned[1], error_ned[0]))
                        desired_yaw = normalize_angle(bearing)
            else:
                # No velocity info - maintain current
                desired_yaw = current_yaw
                
        elif self.yaw_mode == YawControlMode.FIXED:
            # Fixed heading
            desired_yaw = normalize_angle(self.params.control_fixed_yaw_angle)
            
        elif self.yaw_mode == YawControlMode.MANUAL:
            # Manual control
            desired_yaw = normalize_angle(self.params.control_manual_yaw_angle)
            
        else:
            # Default to target tracking
            bearing = math.degrees(math.atan2(error_ned[1], error_ned[0]))
            desired_yaw = normalize_angle(bearing)
        
        # Apply smoothing if enabled
        if self.params.control_yaw_smoothing > 0 and self.last_commanded_yaw is not None:
            # Smooth yaw changes
            yaw_diff = normalize_angle(desired_yaw - self.last_commanded_yaw)
            max_yaw_change = self.params.control_coordinated_yaw_rate * 0.1  # Assume 10Hz update
            
            if abs(yaw_diff) > max_yaw_change:
                # Limit yaw rate
                yaw_diff = np.clip(yaw_diff, -max_yaw_change, max_yaw_change)
            
            # Apply smoothing
            alpha = self.params.control_yaw_smoothing
            smoothed_yaw = self.last_commanded_yaw + yaw_diff * (1 - alpha)
            desired_yaw = normalize_angle(smoothed_yaw)
        
        self.last_commanded_yaw = desired_yaw
        return desired_yaw


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
        drone_velocity_ned = telemetry.get_velocity_ned()
        desired_yaw = self.compute_desired_yaw(
            error_ned, 
            target_velocity,
            drone_velocity_ned,
            telemetry.yaw_deg
        )
        
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
        drone_velocity_ned = telemetry.get_velocity_ned()
        desired_yaw = self.compute_desired_yaw(
            error_ned, 
            target_velocity,
            drone_velocity_ned,
            telemetry.yaw_deg
        )
        
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
        drone_velocity_ned = telemetry.get_velocity_ned()
        desired_yaw = self.compute_desired_yaw(
            error_ned, 
            target_velocity,
            drone_velocity_ned,
            telemetry.yaw_deg
        )
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
        if self.params.guidance_position_lead_time > 0 and self.params.ekf_enabled and self.ekf.is_ready():
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
        drone_velocity_ned = telemetry.get_velocity_ned()
        desired_yaw = self.compute_desired_yaw(
            error_ned, 
            target_velocity,
            drone_velocity_ned,
            telemetry.yaw_deg
        )
        
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
# FILE: visualization.py
# PATH: /visualization.py
# Mission visualization
# =============================================================================


class MissionVisualizer:
    """
    Clean, organized 3D visualization for mission monitoring.
    Fixed to work properly with tkinter and headless mode.
    """
    
    def __init__(self, params, ekf: Optional[Any] = None):
        self.params = params
        self.logger = logging.getLogger(self.__class__.__name__)
        self.rate_window = 5.0
        self.control_loop_times = deque(maxlen=200)
        self.telemetry_times = deque(maxlen=200)
        self.ekf = ekf
        self.ekf_update_times = deque(maxlen=200)
        self.target_meas_times = deque(maxlen=200)

        if not params.viz_enabled:
            self.enabled = False
            return

        display_available = True
        if os.environ.get('DISPLAY') is None and os.name != 'nt':
            display_available = False
            self.logger.warning("No display detected, running in headless mode")

        if display_available:
            try:
                matplotlib.use('TkAgg')
            except ImportError:
                matplotlib.use('Agg')
                display_available = False

        if not display_available:
            self.enabled = False
            self.logger.info("Visualization disabled due to headless environment")
            return

        self.enabled = True
        plt.ion()
        self.fig = plt.figure(figsize=(16, 9))
        self.fig.canvas.manager.set_window_title('Mission Visualizer')

        # Subplots
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

        # History
        self.history = {
            'drone': deque(maxlen=self.params.viz_history_length),
            'target': deque(maxlen=self.params.viz_history_length),
            'predictions': deque(maxlen=self.params.viz_history_length)
        }

        self.update_count = 0
        self.last_update_time = time.time()
        self.start_time = time.time()
        self.last_telemetry = None

        self.drone_path = []
        self.target_path = []
        self.drone_altitudes = []
        self.target_altitudes = []
        self.distances = []
        self.times = []

        # Setup
        self._setup_3d_plot()
        self._setup_topdown_plot()
        self._setup_status_plot()
        self._setup_altitude_plot()

        self.fig.tight_layout()
        plt.show(block=False)
        self.logger.info("Visualization initialized successfully")

    def _setup_3d_plot(self):
        self.ax_3d.set_title('3D Pursuit View', fontsize=14, pad=10)
        self.ax_3d.set_xlabel('North (m)', labelpad=5)
        self.ax_3d.set_ylabel('East (m)', labelpad=5)
        self.ax_3d.set_zlabel('Altitude (m)', labelpad=5)
        self.ax_3d.grid(True, alpha=0.3)
        self.ax_3d.view_init(elev=25, azim=45)

    def _setup_topdown_plot(self):
        self.ax_topdown.set_title('Top-Down View', fontsize=12, pad=10)
        self.ax_topdown.set_xlabel('East (m)')
        self.ax_topdown.set_ylabel('North (m)')
        self.ax_topdown.set_aspect('equal')
        self.ax_topdown.grid(True, alpha=0.3)

        # Trails
        self.topdown_drone_trail, = self.ax_topdown.plot([], [], color=self.colors['drone'], linewidth=1, alpha=0.3)
        self.topdown_target_trail, = self.ax_topdown.plot([], [], color=self.colors['target'], linewidth=1, alpha=0.3, linestyle='--')

        # Heading arrow
        self.topdown_drone_arrow = self.ax_topdown.quiver(
            0, 0, 0, 0,
            color=self.colors['drone'],
            angles='xy', scale_units='xy', scale=1, width=0.005
        )

        # Target marker
        self.topdown_target, = self.ax_topdown.plot([], [], color=self.colors['target'], marker='*', markersize=12)

        # Range rings
        self.range_rings = []
        for r in [10, 25, 50]:
            ring = Circle((0, 0), r, fill=False, linestyle=':', alpha=0.3, color='gray')
            self.ax_topdown.add_patch(ring)
            self.range_rings.append(ring)

        # Uncertainty
        self.uncertainty_ellipse = Ellipse((0, 0), 0, 0, angle=0,
                                          fill=False, edgecolor=self.colors['target'],
                                          alpha=0.5, linestyle='--', linewidth=1)
        self.ax_topdown.add_patch(self.uncertainty_ellipse)
        self.uncertainty_ellipse.set_visible(False)

    def _setup_altitude_plot(self):
        self.ax_altitude.set_title('Altitude Profile', fontsize=12, pad=10)
        self.ax_altitude.set_xlabel('Time (s)')
        self.ax_altitude.set_ylabel('Altitude AGL (m)')
        self.ax_altitude.grid(True, alpha=0.3)
        self.altitude_drone_line, = self.ax_altitude.plot([], [], color=self.colors['drone'], linewidth=2, label='Drone')
        self.altitude_target_line, = self.ax_altitude.plot([], [], color=self.colors['target'], linewidth=2, linestyle='--', label='Target')
        self.ax_altitude.legend(loc='upper right')
        self.ax_altitude.set_ylim(0, 50)

    def _setup_status_plot(self):
        self.ax_status.set_title('Mission Status', fontsize=12, pad=10)
        self.ax_status.axis('off')
        self.status_text = self.ax_status.text(0.05, 0.95, '', transform=self.ax_status.transAxes,
                                              fontsize=11, verticalalignment='top', fontfamily='monospace')

    def _compute_rate(self, times):
        now = time.time()
        recent = [t for t in times if now - t < self.rate_window]
        if len(recent) < 2:
            return 0.0
        return (len(recent)-1) / (recent[-1] - recent[0])

    def update(self, telemetry, target_state: Tuple[np.ndarray, np.ndarray, np.ndarray],
               predictions: Optional[List[np.ndarray]] = None,
               uncertainty: Optional[Tuple[np.ndarray, float]] = None,
               mission_state: str = "UNKNOWN",
               target_sources: Optional[Dict[str, Any]] = None):
        if not self.enabled:
            return
        now = time.time()
        if now - self.last_update_time < 1.0 / self.params.viz_update_rate:
            return
        self.last_update_time = now
        self.update_count += 1

        drone_pos = np.array([telemetry.north_m, telemetry.east_m, -telemetry.altitude_agl_m])
        target_pos = target_state[0].copy()

        self.history['drone'].append(drone_pos.copy())
        self.history['target'].append(target_pos.copy())
        if predictions:
            self.history['predictions'].append(predictions[:20])

        elapsed = now - self.start_time
        self.times.append(elapsed)
        self.drone_path.append(drone_pos)
        self.target_path.append(target_pos)
        self.drone_altitudes.append(telemetry.altitude_agl_m)
        self.target_altitudes.append(-target_pos[2])

        error_horizontal = np.linalg.norm(drone_pos[:2] - target_pos[:2])
        error_3d = np.linalg.norm(drone_pos - target_pos)
        self.distances.append(error_horizontal)

        max_pts = self.params.viz_path_history_length
        if len(self.drone_path) > max_pts:
            self.drone_path = self.drone_path[-max_pts:]
            self.target_path = self.target_path[-max_pts:]
            self.times = self.times[-max_pts:]
            self.distances = self.distances[-max_pts:]
            self.drone_altitudes = self.drone_altitudes[-max_pts:]
            self.target_altitudes = self.target_altitudes[-max_pts:]

        self._update_3d(drone_pos, target_pos, predictions, error_3d, telemetry.yaw_rad)
        self._update_topdown(drone_pos, target_pos, telemetry, uncertainty, error_horizontal)
        self._update_altitude()
        self._update_status_display(telemetry, target_state, error_horizontal, elapsed, mission_state, uncertainty, target_sources)

        plt.draw()
        plt.pause(0.001)

    def _update_3d(self, drone_pos, target_pos, predictions, error_3d, yaw):
        self.ax_3d.clear()
        self._setup_3d_plot()

        # Trails
        if len(self.drone_path) > 1:
            da = np.array(self.drone_path); ta = np.array(self.target_path)
            da[:,2] = -da[:,2]; ta[:,2] = -ta[:,2]
            self.ax_3d.plot(da[:,0], da[:,1], da[:,2], color=self.colors['drone'], linewidth=2, alpha=0.3)
            self.ax_3d.plot(ta[:,0], ta[:,1], ta[:,2], color=self.colors['target'], linewidth=2, alpha=0.3, linestyle='--')

        # Drone body
        drone_size = 2.0
        shape = np.array([[1.5,0,0],[-0.75,0.75,0],[-0.75,-0.75,0],[1.5,0,0]]) * drone_size
        R = np.array([[np.cos(yaw), -np.sin(yaw),0],[np.sin(yaw),np.cos(yaw),0],[0,0,1]])
        pts = shape @ R.T
        pts += [drone_pos[0], drone_pos[1], -drone_pos[2]]
        self.ax_3d.plot(pts[:,0], pts[:,1], pts[:,2], '-', color=self.colors['drone'], linewidth=3)

        # Heading arrow
        arrow_len = 10.0
        dx = arrow_len * np.cos(yaw)
        dy = arrow_len * np.sin(yaw)
        dz = 0.0
        self.ax_3d.quiver(
            drone_pos[0], drone_pos[1], -drone_pos[2],
            dx, dy, dz,
            color=self.colors['drone'], length=arrow_len,
            normalize=True, arrow_length_ratio=0.3, linewidth=2
        )

        # Camera FOV
        fov_l, fov_a = 10.0, np.radians(30)
        for off in (-fov_a, fov_a):
            ang = yaw + off
            fe = drone_pos[:2] + fov_l * np.array([np.cos(ang), np.sin(ang)])
            self.ax_3d.plot([drone_pos[0], fe[0]], [drone_pos[1], fe[1]], [-drone_pos[2]]*2, color='yellow', linewidth=1, alpha=0.5)

        # Target
        self.ax_3d.scatter([target_pos[0]], [target_pos[1]], [-target_pos[2]],
                           c=self.colors['target'], s=150, marker='*',
                           edgecolors='darkred', linewidth=2)

        # Predictions
        if predictions and error_3d<50:
            pa = np.array(predictions[:20])
            self.ax_3d.plot(pa[:,0], pa[:,1], -pa[:,2], color=self.colors['prediction'], linestyle=':', linewidth=2, alpha=0.6)

        # Autoscale
        all_x = [p[0] for p in self.drone_path+self.target_path]
        all_y = [p[1] for p in self.drone_path+self.target_path]
        all_z = [-p[2] for p in self.drone_path+self.target_path]
        m=15
        self.ax_3d.set_xlim(min(all_x)-m, max(all_x)+m)
        self.ax_3d.set_ylim(min(all_y)-m, max(all_y)+m)
        self.ax_3d.set_zlim(0, max(max(all_z)+m,20))

    def _update_topdown(self, drone_pos, target_pos, telemetry, uncertainty, error):
        x, y = drone_pos[1], drone_pos[0]
        yaw = telemetry.yaw_rad
        l=5.0
        u = l * np.sin(yaw)
        v = l * np.cos(yaw)
        self.topdown_drone_arrow.set_offsets([[x,y]])
        self.topdown_drone_arrow.set_UVC([u],[v])

        self.topdown_target.set_data([target_pos[1]],[target_pos[0]])
        if len(self.drone_path)>1:
            dt = np.array(self.drone_path[-50:]); tt = np.array(self.target_path[-50:])
            self.topdown_drone_trail.set_data(dt[:,1], dt[:,0])
            self.topdown_target_trail.set_data(tt[:,1], tt[:,0])

        for ring in self.range_rings:
            ring.center = (x,y)

        if uncertainty and uncertainty[1]>2.0:
            cov=uncertainty[0][:2,:2]
            vals, vecs = np.linalg.eigh(cov)
            ang = np.degrees(np.arctan2(vecs[1,0], vecs[0,0]))
            w=2*np.sqrt(5.991*vals[0]); h=2*np.sqrt(5.991*vals[1])
            self.uncertainty_ellipse.set_center((target_pos[1], target_pos[0]))
            self.uncertainty_ellipse.width, self.uncertainty_ellipse.height = w, h
            self.uncertainty_ellipse.angle = ang
            self.uncertainty_ellipse.set_visible(True)
        else:
            self.uncertainty_ellipse.set_visible(False)

        vr=75
        self.ax_topdown.set_xlim(x-vr, x+vr)
        self.ax_topdown.set_ylim(y-vr, y+vr)

    def _update_altitude(self):
        if len(self.times)>1:
            self.altitude_drone_line.set_data(self.times, self.drone_altitudes)
            self.altitude_target_line.set_data(self.times, self.target_altitudes)
            self.ax_altitude.set_xlim(0, max(self.times[-1],10))
            ma = max(max(self.drone_altitudes+self.target_altitudes, default=10),10)
            self.ax_altitude.set_ylim(0, ma*1.2)

    def _update_status_display(self, telemetry, target_state, error, elapsed, 
                              mission_state, uncertainty, target_sources):
        """Update status panel with target source info."""
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

        # Add target source info if available
        if target_sources:
            status_lines.extend([
                f"",
                f"TARGET SOURCES",
            ])
            for source_id, info in target_sources.items():
                if info.get('is_active'):
                    status_lines.append(f"{source_id:>12}: {'ACTIVE':>8}")

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
        if self.enabled:
            self.fig.savefig(filename, dpi=150, bbox_inches='tight')
            self.logger.info(f"Plot saved to {filename}")

# =============================================================================
# FILE: mission_executor.py
# PATH: /mission_executor.py
# Main mission execution with multi-source integration
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
            MissionState.PURSUIT: [MissionState.PROXIMITY, MissionState.HOLDING, MissionState.EMERGENCY, MissionState.LANDING],
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
    Main mission orchestrator with multi-source target support.
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
        self.target_manager = None  # New multi-source manager
        self.target_source = None   # Legacy compatibility
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
        """Initialize all subsystems with multi-source support."""
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
        
        # Initialize target manager
        self.target_manager = TargetManager(self.params, self.frame_manager, self.ekf)
        
        # Configure target sources based on parameters
        await self._configure_target_sources()
        
        # Initialize all sources
        if not await self.target_manager.initialize_all():
            # Fall back to legacy mode if no sources available
            self.logger.warning("No target sources available, falling back to legacy mode")
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
        
    def set_yaw_mode(self, mode: str):
        """Change yaw control mode at runtime."""
        try:
            new_mode = YawControlMode(mode)
            if self.guidance_strategy:
                self.guidance_strategy.yaw_mode = new_mode
                self.logger.info(f"Yaw mode changed to: {mode}")
                
                # Update parameters for consistency
                self.params.control_yaw_mode = mode
            return True
        except ValueError:
            self.logger.error(f"Invalid yaw mode: {mode}")
            return False
    
    async def _configure_target_sources(self):
        """Configure target sources based on parameters."""
        
        # Camera source
        if self.params.target_camera_enabled:
            camera_source = CameraTargetSource('camera', {
                'api_url': self.params.target_camera_endpoint,
                'api_key': self.params.target_camera_api_key,
                'timeout': self.params.target_camera_timeout,
                'fps': self.params.target_camera_fps
            })
            self.target_manager.register_source(camera_source, priority=0)
        
        # External tracker
        if self.params.target_tracker_enabled:
            tracker_source = ExternalTrackerSource('tracker', {
                'tracker_url': self.params.target_tracker_url,
                'origin': {
                    'lat': self.params.target_tracker_origin_lat,
                    'lon': self.params.target_tracker_origin_lon,
                    'alt': self.params.target_tracker_origin_alt
                },
                'rate': self.params.target_tracker_rate
            })
            self.target_manager.register_source(tracker_source, priority=1)
        
        # GPS source
        if self.params.target_gps_enabled:
            gps_source = GPSTargetSource('gps', {
                'api_endpoint': self.params.target_gps_endpoint,
                'api_key': None,  # Add if needed
                'rate': self.params.target_gps_rate
            })
            self.target_manager.register_source(gps_source, priority=2)
        
        # Simulated source (always available as fallback)
        if self.params.target_simulation_enabled:
            sim_source = SimulatedTargetSourceV2('simulation', {
                'initial_position': self.params.target_initial_position,
                'initial_velocity': self.params.target_initial_velocity,
                'initial_acceleration': self.params.target_initial_acceleration,
                'maneuver_amplitudes': self.params.target_maneuver_amplitudes,
                'maneuver_frequencies': self.params.target_maneuver_frequencies,
                'maneuver_phases': self.params.target_maneuver_phases,
                'position_noise_std': 0.2,
                'measurement_rate': 30.0
            }, self.frame_manager)
            self.target_manager.register_source(sim_source, priority=99)
    
    async def run_mission(self):
        """Execute the complete mission."""
        try:
            print("\n" + "="*70)
            print("DRONE PURSUIT SYSTEM v6.0 - Multi-Source".center(70))
            print("Professional Autonomous Target Tracking".center(70))
            print(f"Mode: {self.params.guidance_mode} | Fusion: {self.params.target_fusion_strategy}".center(70))
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
        
        # Initialize EKF with target if using legacy mode
        if self.target_source and hasattr(self.target_source, 'position'):
            initial_target_pos = np.array(self.target_source.position)
            initial_target_vel = np.array(self.target_source.velocity) if hasattr(self.target_source, 'velocity') else np.zeros(3)
            initial_target_acc = np.array(self.target_source.acceleration) if hasattr(self.target_source, 'acceleration') else np.zeros(3)
            if self.ekf:
                self.ekf.initialize(initial_target_pos, initial_target_vel, initial_target_acc)
        elif self.target_manager and self.params.target_simulation_enabled:
            # Initialize with simulated target position
            initial_target_pos = np.array(self.params.target_initial_position)
            initial_target_vel = np.array(self.params.target_initial_velocity)
            initial_target_acc = np.array(self.params.target_initial_acceleration)
            if self.ekf:
                self.ekf.initialize(initial_target_pos, initial_target_vel, initial_target_acc)
        
        self.logger.info("Preflight checks complete")
    
    async def _execute_arming(self):
        """Arm and start offboard mode."""
        self.state_machine.transition_to(MissionState.ARMING, "Arming vehicle")
        
        await self.drone.action.hold()
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
        """Main pursuit phase with multi-source support."""
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
            'target_acquired': False,
            'active_sources': set()  # Track which sources provided data
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
                
                # Get target state (multi-source or legacy)
                target_state = None
                
                if self.target_manager:
                    # Multi-source mode
                    # Update simulated sources with drone state
                    for source in self.target_manager.sources.values():
                        if isinstance(source, SimulatedTargetSourceV2):
                            source.update_drone_state(current_ned, telemetry.yaw_rad)
                    
                    # Get fused target state
                    target_state = await self.target_manager.get_target_state(telemetry)
                    
                    # Track active sources
                    for source_id, source in self.target_manager.sources.items():
                        if source.is_active and source.measurement_count > 0:
                            self.mission_stats['active_sources'].add(source_id)
                
                else:
                    # Legacy mode
                    if isinstance(self.target_source, SimulatedTargetSource):
                        self.target_source.update_drone_state(current_ned, telemetry.yaw_rad)
                    
                    measurement = await self.target_source.get_measurement()
                    
                    if measurement:
                        if self.visualizer:
                            self.visualizer.target_meas_times.append(time.time())
                        
                        target_cam = measurement['position']
                        target_ned_relative = self.frame_manager.camera_to_ned(
                            target_cam, telemetry.yaw_rad
                        )
                        target_ned = current_ned + target_ned_relative
                        
                        if self.ekf:
                            self.ekf.predict(dt)
                            
                            if self.ekf.update(target_ned):
                                self.mission_stats['measurements_accepted'] += 1
                                if self.visualizer:
                                    self.visualizer.ekf_update_times.append(time.time())
                            else:
                                self.mission_stats['measurements_rejected'] += 1
                            
                            target_state = self.ekf.get_state()
                        else:
                            target_state = (target_ned, np.zeros(3), np.zeros(3))
                
                # Check if we have valid target data
                if target_state is None:
                    self.logger.warning("No valid target data available")
                    continue
                
                target_pos, target_vel, target_acc = target_state
                
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
                        self.state_machine.transition_to(MissionState.PROXIMITY, "Target acquired")
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
                    target_sources = None

                    self.visualizer.control_loop_times.append(time.time())
                    
                    if self.ekf:
                        if self.params.viz_show_predictions and self.ekf.is_ready():
                            predictions = self.ekf.predict_trajectory(
                                self.params.ekf_prediction_horizon
                            )
                        if self.params.viz_show_uncertainty:
                            uncertainty = self.ekf.get_uncertainty()
                    
                    # Get target source diagnostics
                    if self.target_manager:
                        diagnostics = self.target_manager.get_diagnostics()
                        target_sources = diagnostics.get('sources', {})
                    
                    self.visualizer.update(
                        telemetry,
                        (target_pos, target_vel, target_acc),
                        predictions,
                        uncertainty,
                        self.state_machine.state.name,
                        target_sources
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
                
                # Add source info to display
                source_info = ""
                if self.target_manager:
                    active_sources = [s for s, info in self.target_manager.sources.items() 
                                     if info.is_active and info.measurement_count > 0]
                    if active_sources:
                        source_info = f" | Src: {','.join(active_sources[:2])}"
                
                # Clean terminal output
                print(f"\r{'Time:':<6} {elapsed:>6.1f}s | "
                      f"{'Dist:':<5} {error_3d:>5.1f}m | "
                      f"{'H-Dist:':<7} {error_horizontal:>5.1f}m | "
                      f"{'Close:':<6} {closing_rate:>4.1f}m/s | "
                      f"{'ETA:':<4} {eta:>5.1f}s | "
                      f"{'Bat:':<4} {telemetry.battery_percent:>3.0f}%"
                      f"{source_info}",
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
                
                # Get source diagnostics
                target_sources = None
                if self.target_manager:
                    diagnostics = self.target_manager.get_diagnostics()
                    target_sources = diagnostics.get('sources', {})
                
                self.visualizer.update(
                    telemetry,
                    (target_pos, target_vel, target_acc),
                    mission_state="PROXIMITY",
                    target_sources=target_sources
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
        
        if self.target_manager:
            await self.target_manager.shutdown_all()
        elif self.target_source:
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
        """Print comprehensive mission report with multi-source info."""
        import csv
        
        # Prepare report data
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
        
        # Calculate summary statistics
        total_time = sum(s['duration'] for s in self.state_machine.state_history)
        
        # Build report sections
        report_lines = []
        report_lines.append("\n" + "="*70)
        report_lines.append("MISSION REPORT - v6.0 Multi-Source".center(70))
        report_lines.append("="*70)
        
        # Summary Section
        report_lines.append(f"\n{'MISSION SUMMARY':^70}")
        report_lines.append("-"*70)
        report_lines.append(f"{'Total Mission Duration:':<35} {total_time:>10.1f} seconds")
        report_lines.append(f"{'Final Mission State:':<35} {self.state_machine.state.name:>10}")
        report_lines.append(f"{'Guidance Mode:':<35} {self.params.guidance_mode:>10}")
        report_lines.append(f"{'Fusion Strategy:':<35} {self.params.target_fusion_strategy:>10}")
        
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
        
        # Target Sources Info
        if self.mission_stats.get('active_sources'):
            report_lines.append(f"\n{'TARGET SOURCES':^70}")
            report_lines.append("-"*70)
            report_lines.append(f"{'Active Sources:':<35} {', '.join(self.mission_stats['active_sources']):>10}")
            
            if self.target_manager:
                for source_id, source in self.target_manager.sources.items():
                    health = source.get_health_status()
                    if health['measurement_count'] > 0:
                        report_lines.append(f"{source_id + ' Measurements:':<35} {health['measurement_count']:>10}")
                        report_lines.append(f"{source_id + ' Error Rate:':<35} {health['error_rate']*100:>9.1f}%")
        
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
                writer.writerow(['Mission Report v6.0', timestamp.strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow([])
                
                # Mission Summary
                writer.writerow(['MISSION SUMMARY'])
                writer.writerow(['Metric', 'Value'])
                writer.writerow(['Total Duration (s)', f'{total_time:.1f}'])
                writer.writerow(['Final State', self.state_machine.state.name])
                writer.writerow(['Guidance Mode', self.params.guidance_mode])
                writer.writerow(['Fusion Strategy', self.params.target_fusion_strategy])
                writer.writerow(['Target Acquired', 'Yes' if self.mission_stats.get('target_acquired', False) else 'No'])
                writer.writerow([])
                
                # Target Sources
                if self.mission_stats.get('active_sources'):
                    writer.writerow(['TARGET SOURCES'])
                    writer.writerow(['Source ID', 'Measurements', 'Error Rate'])
                    if self.target_manager:
                        for source_id, source in self.target_manager.sources.items():
                            health = source.get_health_status()
                            if health['measurement_count'] > 0:
                                writer.writerow([
                                    source_id,
                                    health['measurement_count'],
                                    f"{health['error_rate']*100:.1f}%"
                                ])
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
        description="Drone Pursuit System v6.0 - Multi-Source Target Framework"
    )
    parser.add_argument('--config', type=Path, help='Configuration file (YAML or JSON)')
    parser.add_argument('--mode', choices=['local_ned_velocity', 'global_ned_velocity', 
                                          'body_velocity', 'global_position'],
                       help='Override guidance mode')
    parser.add_argument('--fusion', choices=['priority', 'weighted', 'kalman'],
                       help='Override fusion strategy')
    parser.add_argument('--connection', type=str, help='Override connection string')
    parser.add_argument('--no-viz', action='store_true', help='Disable visualization')
    parser.add_argument('--no-save', action='store_true', help='Do not save mission report')
    
    # Target source overrides
    parser.add_argument('--enable-camera', action='store_true', help='Enable camera source')
    parser.add_argument('--enable-tracker', action='store_true', help='Enable tracker source')
    parser.add_argument('--enable-gps', action='store_true', help='Enable GPS source')
    parser.add_argument('--disable-sim', action='store_true', help='Disable simulation source')
    
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
    
    if args.fusion:
        params.target_fusion_strategy = args.fusion
        print(f"Fusion strategy override: {args.fusion}")
    
    if args.connection:
        params.system_connection = args.connection
        print(f"Connection override: {args.connection}")
    
    if args.no_viz:
        params.viz_enabled = False
        print("Visualization disabled")
    
    if args.no_save:
        params.save_mission_report = False
        print("Report saving disabled")
    
    # Target source overrides
    if args.enable_camera:
        params.target_camera_enabled = True
        print("Camera source enabled")
    
    if args.enable_tracker:
        params.target_tracker_enabled = True
        print("Tracker source enabled")
    
    if args.enable_gps:
        params.target_gps_enabled = True
        print("GPS source enabled")
    
    if args.disable_sim:
        params.target_simulation_enabled = False
        print("Simulation source disabled")
    
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
