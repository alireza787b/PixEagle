# src/classes/coordinate_transformer.py

"""
CoordinateTransformer Module
============================

This module provides coordinate transformation utilities for gimbal-based tracking systems.
It handles conversions between different coordinate systems used in aerial tracking scenarios.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The CoordinateTransformer class handles transformations between:
- Gimbal coordinate systems (GIMBAL_BODY and SPATIAL_FIXED)
- Aircraft body frame coordinates
- NED (North-East-Down) frame coordinates
- Normalized screen coordinates for PixEagle compatibility

Key Features:
-------------
- Real-time coordinate transformations
- Support for camera mount offsets
- Gimbal angle to target vector conversion
- Body frame to NED frame transformations
- Mathematical utilities for rotation matrices

Usage:
------
```python
transformer = CoordinateTransformer()

# Convert gimbal angles to target vector in body frame
target_vector = transformer.gimbal_angles_to_body_vector(yaw, pitch, roll)

# Transform body vector to NED frame
ned_vector = transformer.body_to_ned_vector(target_vector, aircraft_yaw)

# Convert to normalized coordinates for PixEagle
norm_coords = transformer.vector_to_normalized_coords(target_vector)
```

Integration:
-----------
This module is used by both GimbalTracker and GimbalFollower to handle
coordinate transformations throughout the tracking and control pipeline.
"""

import math
import time
import numpy as np
import logging
from typing import Tuple, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class FrameType(Enum):
    """Coordinate frame types"""
    GIMBAL_BODY = "gimbal_body"       # Relative to gimbal mount
    AIRCRAFT_BODY = "aircraft_body"   # Relative to aircraft body
    NED = "ned"                       # North-East-Down frame
    NORMALIZED = "normalized"         # PixEagle normalized coordinates

@dataclass
class TransformationMatrix:
    """Container for 3x3 transformation matrix with metadata"""
    matrix: np.ndarray
    source_frame: FrameType
    target_frame: FrameType
    timestamp: float

@dataclass
class CameraParameters:
    """Camera calibration and mounting parameters"""
    # Camera mount offsets relative to aircraft body frame
    mount_offset_roll: float = 0.0    # degrees
    mount_offset_pitch: float = 0.0   # degrees
    mount_offset_yaw: float = 0.0     # degrees

    # Camera field of view parameters
    fov_horizontal: float = 60.0      # degrees
    fov_vertical: float = 45.0        # degrees

    # Projection parameters
    focal_length_x: float = 1.0       # normalized focal length
    focal_length_y: float = 1.0       # normalized focal length

class CoordinateTransformer:
    """
    Comprehensive coordinate transformation utility for gimbal-based tracking.

    This class provides all coordinate transformations needed for converting
    gimbal angles to target vectors and velocity commands in various reference frames.
    """

    def __init__(self, camera_params: Optional[CameraParameters] = None):
        """
        Initialize coordinate transformer.

        Args:
            camera_params (Optional[CameraParameters]): Camera calibration parameters
        """
        self.camera_params = camera_params or CameraParameters()

        # Cache for frequently used transformation matrices
        self._transform_cache: Dict[str, TransformationMatrix] = {}
        self._cache_timeout = 1.0  # Cache timeout in seconds

        logger.debug("CoordinateTransformer initialized")

    def gimbal_angles_to_body_vector(self, yaw: float, pitch: float, roll: float,
                                   include_mount_offset: bool = True) -> np.ndarray:
        """
        Convert gimbal angles to unit vector in aircraft body frame.

        This is the core transformation that converts gimbal pointing angles
        to a 3D vector indicating target direction relative to the aircraft.

        Args:
            yaw (float): Gimbal yaw angle in degrees (+ = right)
            pitch (float): Gimbal pitch angle in degrees (+ = up)
            roll (float): Gimbal roll angle in degrees (+ = clockwise)
            include_mount_offset (bool): Apply camera mount offset corrections

        Returns:
            np.ndarray: Unit vector [x, y, z] in aircraft body frame
                       (x=forward, y=right, z=down)
        """
        try:
            # Apply camera mount offsets if requested
            if include_mount_offset:
                total_yaw = yaw + self.camera_params.mount_offset_yaw
                total_pitch = pitch + self.camera_params.mount_offset_pitch
                total_roll = roll + self.camera_params.mount_offset_roll
            else:
                total_yaw = yaw
                total_pitch = pitch
                total_roll = roll

            # Convert to radians
            yaw_rad = math.radians(total_yaw)
            pitch_rad = math.radians(total_pitch)
            # Note: Roll typically doesn't affect target vector direction for tracking

            # Create unit vector pointing to target in body frame
            # Body frame convention: X=forward, Y=right, Z=down
            x = math.cos(pitch_rad) * math.cos(yaw_rad)  # Forward component
            y = math.cos(pitch_rad) * math.sin(yaw_rad)  # Right component
            z = -math.sin(pitch_rad)                     # Down component (negative = up)

            target_vector = np.array([x, y, z])

            # Normalize to ensure unit vector
            magnitude = np.linalg.norm(target_vector)
            if magnitude > 0:
                target_vector = target_vector / magnitude

            logger.debug(f"Gimbal angles ({yaw:.1f}°, {pitch:.1f}°, {roll:.1f}°) → "
                        f"Body vector ({x:.3f}, {y:.3f}, {z:.3f})")

            return target_vector

        except Exception as e:
            logger.error(f"Error converting gimbal angles to body vector: {e}")
            # Return forward-pointing vector as safe fallback
            return np.array([1.0, 0.0, 0.0])

    def body_to_ned_vector(self, body_vector: np.ndarray, aircraft_yaw_rad: float) -> np.ndarray:
        """
        Transform body frame vector to NED (North-East-Down) frame.

        Args:
            body_vector (np.ndarray): Vector in body frame [x, y, z]
            aircraft_yaw_rad (float): Aircraft yaw angle in radians

        Returns:
            np.ndarray: Vector in NED frame [north, east, down]
        """
        try:
            # Create rotation matrix from body to NED frame
            # This accounts for aircraft orientation relative to North
            cos_yaw = math.cos(aircraft_yaw_rad)
            sin_yaw = math.sin(aircraft_yaw_rad)

            # Rotation matrix for yaw rotation (around Z-axis)
            R_body_to_ned = np.array([
                [cos_yaw, -sin_yaw, 0],
                [sin_yaw,  cos_yaw, 0],
                [0,        0,       1]
            ])

            ned_vector = R_body_to_ned @ body_vector

            logger.debug(f"Body vector {body_vector} → NED vector {ned_vector} "
                        f"(aircraft yaw: {math.degrees(aircraft_yaw_rad):.1f}°)")

            return ned_vector

        except Exception as e:
            logger.error(f"Error converting body to NED vector: {e}")
            return body_vector  # Return original as fallback

    def ned_to_body_vector(self, ned_vector: np.ndarray, aircraft_yaw_rad: float) -> np.ndarray:
        """
        Transform NED frame vector to body frame.

        Args:
            ned_vector (np.ndarray): Vector in NED frame [north, east, down]
            aircraft_yaw_rad (float): Aircraft yaw angle in radians

        Returns:
            np.ndarray: Vector in body frame [x, y, z]
        """
        try:
            # Create rotation matrix from NED to body frame (inverse of body_to_ned)
            cos_yaw = math.cos(aircraft_yaw_rad)
            sin_yaw = math.sin(aircraft_yaw_rad)

            R_ned_to_body = np.array([
                [cos_yaw,  sin_yaw, 0],
                [-sin_yaw, cos_yaw, 0],
                [0,        0,       1]
            ])

            body_vector = R_ned_to_body @ ned_vector

            logger.debug(f"NED vector {ned_vector} → Body vector {body_vector} "
                        f"(aircraft yaw: {math.degrees(aircraft_yaw_rad):.1f}°)")

            return body_vector

        except Exception as e:
            logger.error(f"Error converting NED to body vector: {e}")
            return ned_vector  # Return original as fallback

    def vector_to_normalized_coords(self, target_vector: np.ndarray,
                                  frame_type: FrameType = FrameType.AIRCRAFT_BODY) -> Tuple[float, float]:
        """
        Convert 3D target vector to normalized 2D coordinates for PixEagle.

        This conversion projects the 3D target vector onto a 2D plane using
        camera projection models, resulting in normalized coordinates that
        PixEagle can use for tracking and control.

        Args:
            target_vector (np.ndarray): 3D target vector
            frame_type (FrameType): Source coordinate frame

        Returns:
            Tuple[float, float]: Normalized coordinates (x, y) in range [-1, 1]
        """
        try:
            # Ensure we have a unit vector
            magnitude = np.linalg.norm(target_vector)
            if magnitude == 0:
                return (0.0, 0.0)

            unit_vector = target_vector / magnitude

            # Extract direction components
            if frame_type == FrameType.AIRCRAFT_BODY:
                forward = unit_vector[0]
                right = unit_vector[1]
                down = unit_vector[2]
            elif frame_type == FrameType.NED:
                # For NED frame, we need to determine which component corresponds to "forward"
                # This depends on aircraft orientation, but for simplicity, assume:
                north = unit_vector[0]
                east = unit_vector[1]
                down = unit_vector[2]
                # Map to screen coordinates (this is application-specific)
                forward = north  # Simplified mapping
                right = east
            else:
                # Default to body frame interpretation
                forward = unit_vector[0]
                right = unit_vector[1]
                down = unit_vector[2]

            # Convert to angular coordinates
            if forward > 0:  # Target is in front
                # Calculate horizontal angle (yaw equivalent)
                horizontal_angle = math.atan2(right, forward)

                # Calculate vertical angle (pitch equivalent)
                horizontal_magnitude = math.sqrt(forward**2 + right**2)
                vertical_angle = math.atan2(-down, horizontal_magnitude)  # Negative for "up is positive"
            else:
                # Target is behind - handle this case carefully
                horizontal_angle = math.atan2(right, abs(forward))
                vertical_angle = 0.0  # Assume level when target is behind

            # Convert angles to normalized coordinates based on camera FOV
            fov_h_rad = math.radians(self.camera_params.fov_horizontal / 2)
            fov_v_rad = math.radians(self.camera_params.fov_vertical / 2)

            # Normalize to [-1, 1] range
            norm_x = horizontal_angle / fov_h_rad
            norm_y = vertical_angle / fov_v_rad

            # Clamp to reasonable range (allow for off-screen tracking)
            norm_x = max(-2.0, min(2.0, norm_x))
            norm_y = max(-2.0, min(2.0, norm_y))

            logger.debug(f"Vector {target_vector} → Normalized coords ({norm_x:.3f}, {norm_y:.3f})")

            return (norm_x, norm_y)

        except Exception as e:
            logger.error(f"Error converting vector to normalized coords: {e}")
            return (0.0, 0.0)

    def normalized_coords_to_angles(self, norm_x: float, norm_y: float) -> Tuple[float, float]:
        """
        Convert normalized coordinates back to gimbal angles.

        Args:
            norm_x (float): Normalized X coordinate [-1, 1]
            norm_y (float): Normalized Y coordinate [-1, 1]

        Returns:
            Tuple[float, float]: (yaw, pitch) angles in degrees
        """
        try:
            # Convert normalized coordinates to angles based on camera FOV
            fov_h_rad = math.radians(self.camera_params.fov_horizontal / 2)
            fov_v_rad = math.radians(self.camera_params.fov_vertical / 2)

            yaw_rad = norm_x * fov_h_rad
            pitch_rad = norm_y * fov_v_rad

            yaw_deg = math.degrees(yaw_rad)
            pitch_deg = math.degrees(pitch_rad)

            return (yaw_deg, pitch_deg)

        except Exception as e:
            logger.error(f"Error converting normalized coords to angles: {e}")
            return (0.0, 0.0)

    def calculate_velocity_from_vector(self, target_vector: np.ndarray,
                                     velocity_magnitude: float = 1.0,
                                     frame_type: FrameType = FrameType.AIRCRAFT_BODY) -> np.ndarray:
        """
        Calculate velocity vector from target direction vector.

        Args:
            target_vector (np.ndarray): Target direction vector
            velocity_magnitude (float): Desired velocity magnitude (m/s)
            frame_type (FrameType): Coordinate frame for output

        Returns:
            np.ndarray: Velocity vector [vx, vy, vz]
        """
        try:
            # Normalize target vector
            magnitude = np.linalg.norm(target_vector)
            if magnitude == 0:
                return np.array([0.0, 0.0, 0.0])

            unit_vector = target_vector / magnitude

            # Scale by desired velocity magnitude
            velocity_vector = unit_vector * velocity_magnitude

            logger.debug(f"Target vector {target_vector} → Velocity {velocity_vector} "
                        f"(magnitude: {velocity_magnitude:.2f} m/s)")

            return velocity_vector

        except Exception as e:
            logger.error(f"Error calculating velocity from vector: {e}")
            return np.array([0.0, 0.0, 0.0])

    def get_transformation_matrix(self, source: FrameType, target: FrameType,
                                aircraft_yaw_rad: float = 0.0) -> np.ndarray:
        """
        Get transformation matrix between coordinate frames.

        Args:
            source (FrameType): Source coordinate frame
            target (FrameType): Target coordinate frame
            aircraft_yaw_rad (float): Aircraft yaw for body/NED transforms

        Returns:
            np.ndarray: 3x3 transformation matrix
        """
        try:
            # Generate cache key
            cache_key = f"{source.value}_{target.value}_{aircraft_yaw_rad:.3f}"

            # Check cache
            if cache_key in self._transform_cache:
                cached = self._transform_cache[cache_key]
                if (time.time() - cached.timestamp) < self._cache_timeout:
                    return cached.matrix

            # Create transformation matrix based on frame types
            if source == target:
                matrix = np.eye(3)
            elif source == FrameType.AIRCRAFT_BODY and target == FrameType.NED:
                cos_yaw = math.cos(aircraft_yaw_rad)
                sin_yaw = math.sin(aircraft_yaw_rad)
                matrix = np.array([
                    [cos_yaw, -sin_yaw, 0],
                    [sin_yaw,  cos_yaw, 0],
                    [0,        0,       1]
                ])
            elif source == FrameType.NED and target == FrameType.AIRCRAFT_BODY:
                cos_yaw = math.cos(aircraft_yaw_rad)
                sin_yaw = math.sin(aircraft_yaw_rad)
                matrix = np.array([
                    [cos_yaw,  sin_yaw, 0],
                    [-sin_yaw, cos_yaw, 0],
                    [0,        0,       1]
                ])
            else:
                # Default to identity matrix for unknown transformations
                matrix = np.eye(3)
                logger.warning(f"Unknown transformation: {source.value} → {target.value}")

            # Cache the result
            self._transform_cache[cache_key] = TransformationMatrix(
                matrix=matrix,
                source_frame=source,
                target_frame=target,
                timestamp=time.time()
            )

            return matrix

        except Exception as e:
            logger.error(f"Error creating transformation matrix: {e}")
            return np.eye(3)

    def update_camera_parameters(self, **kwargs) -> None:
        """
        Update camera parameters.

        Args:
            **kwargs: Camera parameter updates (mount_offset_yaw, fov_horizontal, etc.)
        """
        try:
            for key, value in kwargs.items():
                if hasattr(self.camera_params, key):
                    setattr(self.camera_params, key, value)
                    logger.debug(f"Updated camera parameter {key} = {value}")
                else:
                    logger.warning(f"Unknown camera parameter: {key}")

            # Clear cache when parameters change
            self._transform_cache.clear()

        except Exception as e:
            logger.error(f"Error updating camera parameters: {e}")

    def get_camera_parameters(self) -> CameraParameters:
        """
        Get current camera parameters.

        Returns:
            CameraParameters: Current camera configuration
        """
        return self.camera_params

    def clear_cache(self) -> None:
        """Clear transformation matrix cache."""
        self._transform_cache.clear()
        logger.debug("Transformation cache cleared")

    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict[str, Any]: Cache information
        """
        current_time = time.time()
        valid_entries = sum(
            1 for cached in self._transform_cache.values()
            if (current_time - cached.timestamp) < self._cache_timeout
        )

        return {
            'total_entries': len(self._transform_cache),
            'valid_entries': valid_entries,
            'cache_timeout': self._cache_timeout
        }