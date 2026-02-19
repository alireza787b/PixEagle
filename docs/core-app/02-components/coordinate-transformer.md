# CoordinateTransformer

Coordinate transformation utilities for gimbal-based tracking systems.

## Overview

`CoordinateTransformer` (`src/classes/coordinate_transformer.py`) provides:

- Gimbal angle to body vector conversion
- Body frame to NED frame transformations
- Vector to normalized coordinate projection
- Camera parameter management
- Transformation matrix caching

## Coordinate Frames

### Frame Types

```python
class FrameType(Enum):
    GIMBAL_BODY = "gimbal_body"       # Relative to gimbal mount
    AIRCRAFT_BODY = "aircraft_body"   # Relative to aircraft body
    NED = "ned"                       # North-East-Down frame
    NORMALIZED = "normalized"         # PixEagle normalized coordinates
```

### Frame Conventions

```
Aircraft Body Frame:
  X = Forward
  Y = Right
  Z = Down

NED Frame:
  X = North
  Y = East
  Z = Down

Normalized Coordinates:
  X = [-1, 1] (left to right)
  Y = [-1, 1] (down to up)
```

## Class Definition

```python
class CoordinateTransformer:
    """
    Comprehensive coordinate transformation utility for gimbal-based tracking.
    """
```

## Camera Parameters

```python
@dataclass
class CameraParameters:
    """Camera calibration and mounting parameters."""
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
```

## Key Transformations

### Gimbal Angles to Body Vector

```python
def gimbal_angles_to_body_vector(
    self,
    yaw: float,
    pitch: float,
    roll: float,
    include_mount_offset: bool = True
) -> np.ndarray:
    """
    Convert gimbal angles to unit vector in aircraft body frame.

    Args:
        yaw: Gimbal yaw angle in degrees (+ = right)
        pitch: Gimbal pitch angle in degrees (+ = up)
        roll: Gimbal roll angle in degrees (+ = clockwise)
        include_mount_offset: Apply camera mount offset corrections

    Returns:
        Unit vector [x, y, z] in aircraft body frame
        (x=forward, y=right, z=down)
    """
    # Apply mount offsets
    if include_mount_offset:
        total_yaw = yaw + self.camera_params.mount_offset_yaw
        total_pitch = pitch + self.camera_params.mount_offset_pitch
    else:
        total_yaw = yaw
        total_pitch = pitch

    # Convert to radians
    yaw_rad = math.radians(total_yaw)
    pitch_rad = math.radians(total_pitch)

    # Create unit vector in body frame
    x = math.cos(pitch_rad) * math.cos(yaw_rad)  # Forward
    y = math.cos(pitch_rad) * math.sin(yaw_rad)  # Right
    z = -math.sin(pitch_rad)                      # Down (neg = up)

    target_vector = np.array([x, y, z])
    return target_vector / np.linalg.norm(target_vector)
```

### Body to NED Transformation

```python
def body_to_ned_vector(
    self,
    body_vector: np.ndarray,
    aircraft_yaw_rad: float
) -> np.ndarray:
    """
    Transform body frame vector to NED frame.

    Args:
        body_vector: Vector in body frame [x, y, z]
        aircraft_yaw_rad: Aircraft yaw angle in radians

    Returns:
        Vector in NED frame [north, east, down]
    """
    cos_yaw = math.cos(aircraft_yaw_rad)
    sin_yaw = math.sin(aircraft_yaw_rad)

    # Rotation matrix for yaw (around Z-axis)
    R_body_to_ned = np.array([
        [cos_yaw, -sin_yaw, 0],
        [sin_yaw,  cos_yaw, 0],
        [0,        0,       1]
    ])

    return R_body_to_ned @ body_vector
```

### NED to Body Transformation

```python
def ned_to_body_vector(
    self,
    ned_vector: np.ndarray,
    aircraft_yaw_rad: float
) -> np.ndarray:
    """
    Transform NED frame vector to body frame.
    """
    cos_yaw = math.cos(aircraft_yaw_rad)
    sin_yaw = math.sin(aircraft_yaw_rad)

    R_ned_to_body = np.array([
        [cos_yaw,  sin_yaw, 0],
        [-sin_yaw, cos_yaw, 0],
        [0,        0,       1]
    ])

    return R_ned_to_body @ ned_vector
```

### Vector to Normalized Coordinates

```python
def vector_to_normalized_coords(
    self,
    target_vector: np.ndarray,
    frame_type: FrameType = FrameType.AIRCRAFT_BODY
) -> Tuple[float, float]:
    """
    Convert 3D target vector to normalized 2D coordinates.

    Projects the 3D target vector onto a 2D plane using
    camera projection models.

    Args:
        target_vector: 3D target vector
        frame_type: Source coordinate frame

    Returns:
        Normalized coordinates (x, y) in range [-1, 1]
    """
    # Normalize vector
    unit_vector = target_vector / np.linalg.norm(target_vector)

    # Extract components
    forward = unit_vector[0]
    right = unit_vector[1]
    down = unit_vector[2]

    # Convert to angular coordinates
    if forward > 0:  # Target is in front
        horizontal_angle = math.atan2(right, forward)
        horizontal_magnitude = math.sqrt(forward**2 + right**2)
        vertical_angle = math.atan2(-down, horizontal_magnitude)
    else:
        # Target is behind
        horizontal_angle = math.atan2(right, abs(forward))
        vertical_angle = 0.0

    # Normalize based on camera FOV
    fov_h_rad = math.radians(self.camera_params.fov_horizontal / 2)
    fov_v_rad = math.radians(self.camera_params.fov_vertical / 2)

    norm_x = horizontal_angle / fov_h_rad
    norm_y = vertical_angle / fov_v_rad

    # Clamp to reasonable range
    norm_x = max(-2.0, min(2.0, norm_x))
    norm_y = max(-2.0, min(2.0, norm_y))

    return (norm_x, norm_y)
```

### Normalized Coordinates to Angles

```python
def normalized_coords_to_angles(
    self,
    norm_x: float,
    norm_y: float
) -> Tuple[float, float]:
    """
    Convert normalized coordinates back to gimbal angles.

    Args:
        norm_x: Normalized X coordinate [-1, 1]
        norm_y: Normalized Y coordinate [-1, 1]

    Returns:
        (yaw, pitch) angles in degrees
    """
    fov_h_rad = math.radians(self.camera_params.fov_horizontal / 2)
    fov_v_rad = math.radians(self.camera_params.fov_vertical / 2)

    yaw_rad = norm_x * fov_h_rad
    pitch_rad = norm_y * fov_v_rad

    return (math.degrees(yaw_rad), math.degrees(pitch_rad))
```

## Transformation Matrices

### Get Transformation Matrix

```python
def get_transformation_matrix(
    self,
    source: FrameType,
    target: FrameType,
    aircraft_yaw_rad: float = 0.0
) -> np.ndarray:
    """
    Get transformation matrix between coordinate frames.
    Uses caching for frequently used transforms.
    """
    # Check cache
    cache_key = f"{source.value}_{target.value}_{aircraft_yaw_rad:.3f}"
    if cache_key in self._transform_cache:
        cached = self._transform_cache[cache_key]
        if time.time() - cached.timestamp < self._cache_timeout:
            return cached.matrix

    # Create matrix
    if source == target:
        matrix = np.eye(3)
    elif source == FrameType.AIRCRAFT_BODY and target == FrameType.NED:
        # Body to NED rotation
        cos_yaw = math.cos(aircraft_yaw_rad)
        sin_yaw = math.sin(aircraft_yaw_rad)
        matrix = np.array([
            [cos_yaw, -sin_yaw, 0],
            [sin_yaw,  cos_yaw, 0],
            [0,        0,       1]
        ])
    # ... more cases

    # Cache result
    self._transform_cache[cache_key] = TransformationMatrix(
        matrix=matrix,
        source_frame=source,
        target_frame=target,
        timestamp=time.time()
    )

    return matrix
```

## Velocity Calculation

```python
def calculate_velocity_from_vector(
    self,
    target_vector: np.ndarray,
    velocity_magnitude: float = 1.0,
    frame_type: FrameType = FrameType.AIRCRAFT_BODY
) -> np.ndarray:
    """
    Calculate velocity vector from target direction.

    Args:
        target_vector: Target direction vector
        velocity_magnitude: Desired velocity (m/s)
        frame_type: Coordinate frame for output

    Returns:
        Velocity vector [vx, vy, vz]
    """
    unit_vector = target_vector / np.linalg.norm(target_vector)
    return unit_vector * velocity_magnitude
```

## Parameter Management

```python
def update_camera_parameters(self, **kwargs) -> None:
    """Update camera parameters."""
    for key, value in kwargs.items():
        if hasattr(self.camera_params, key):
            setattr(self.camera_params, key, value)

    # Clear cache when parameters change
    self._transform_cache.clear()

def get_camera_parameters(self) -> CameraParameters:
    """Get current camera parameters."""
    return self.camera_params
```

## Usage Example

```python
from classes.coordinate_transformer import CoordinateTransformer, CameraParameters

# Create with custom camera params
params = CameraParameters(
    fov_horizontal=82.0,
    fov_vertical=52.0,
    mount_offset_pitch=-10.0  # Camera tilted down
)
transformer = CoordinateTransformer(params)

# Convert gimbal angles to body vector
gimbal_yaw = 15.0    # degrees right
gimbal_pitch = -5.0  # degrees down
body_vector = transformer.gimbal_angles_to_body_vector(gimbal_yaw, gimbal_pitch, 0)

# Transform to NED
aircraft_yaw = math.radians(45)  # Aircraft heading 45° from North
ned_vector = transformer.body_to_ned_vector(body_vector, aircraft_yaw)

# Get normalized coordinates for tracker
norm_x, norm_y = transformer.vector_to_normalized_coords(body_vector)
print(f"Normalized: ({norm_x:.3f}, {norm_y:.3f})")

# Calculate velocity toward target
velocity = transformer.calculate_velocity_from_vector(body_vector, 5.0)
print(f"Velocity: {velocity}")
```

## Related Components

- [GimbalTracker](../../trackers/02-components/gimbal-tracker.md) - Uses coordinate transforms
- [GimbalFollower](../../followers/02-components/gm-velocity-chase-follower.md) - Velocity calculations
