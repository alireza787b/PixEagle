# PixEagle Tracker and Follower Schema System Developer Guide

## Overview

This comprehensive guide documents the **PixEagle Schema-Aware Tracker and Follower System** — a robust, extensible architecture that enables developers to create custom tracker implementations and follower modes with dynamic validation, type safety, and unified command processing.

The system provides a **unified interface** for all tracking and following operations while maintaining **complete flexibility** for implementing new tracker types with custom data sources, output schemas, and follower integrations.

---

## 🚀 What's New in PixEagle 3.0

### ✨ Schema-Driven Architecture
- **YAML-based configuration** for all tracker data types and validation rules
- **Dynamic validation system** supporting complex data structures
- **Extensible without code changes** — add new tracker types via configuration
- **Type-safe data structures** with automatic validation and error reporting

### 🎯 Unified Command Processing  
- **Schema-aware follower factory** supporting multiple follower implementations
- **Dynamic mode switching** between tracker and follower combinations
- **Consistent telemetry and debugging** across all system components
- **Production-ready logging** with clean, informative status updates

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [Schema Configuration System](#schema-configuration-system)
4. [Creating Custom Trackers](#creating-custom-trackers)
5. [Creating Custom Followers](#creating-custom-followers)
6. [Integration Examples](#integration-examples)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)
9. [API Reference](#api-reference)

---

## 🏗️ Architecture Overview

The PixEagle schema system consists of three main architectural layers:

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
├─────────────────────────────────────────────────────────────┤
│  AppController  │  FastAPIHandler  │  TelemetryHandler      │
└─────────────────┴──────────────────┴─────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                      SCHEMA LAYER                           │
├─────────────────────────────────────────────────────────────┤
│  SchemaManager  │  TrackerOutput   │  SetpointHandler       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │            YAML Configuration Files                 │    │
│  │  • tracker_schemas.yaml                             │    │
│  │  • follower_commands.yaml                           │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                   IMPLEMENTATION LAYER                      │
├─────────────────────────────────────────────────────────────┤
│  TrackerFactory │  FollowerFactory │  Smart/Classic Trackers│
│  Custom Trackers│  Custom Followers│  MAVLink Integration   │
└─────────────────┴──────────────────┴─────────────────────────┘
```

### Key Design Principles

- **Separation of Concerns**: Schema definitions are separate from implementation
- **Extensibility**: New trackers and followers can be added without modifying core code
- **Type Safety**: All data is validated against schema definitions
- **Backwards Compatibility**: Existing implementations continue to work unchanged
- **Production Ready**: Comprehensive logging, error handling, and monitoring

---

## 🔧 Core Components

### 1. SchemaManager (`src/classes/schema_manager.py`)

The central component that loads and manages YAML-based schema definitions.

```python
from classes.schema_manager import validate_tracker_data, SCHEMA_MANAGER_AVAILABLE

# Validate tracker output against schema
is_valid, errors = validate_tracker_data(
    'POSITION_2D', 
    {'position_2d': (0.5, 0.3)}, 
    tracking_active=True
)
```

### 2. TrackerOutput (`src/classes/tracker_output.py`)

Type-safe data structure for all tracker implementations.

```python
from classes.tracker_output import TrackerOutput, TrackerDataType

# Create validated tracker output
output = TrackerOutput(
    data_type=TrackerDataType.POSITION_2D,
    position_2d=(0.5, 0.3),
    confidence=0.87,
    tracking_active=True
)
```

### 3. SetpointHandler (`src/classes/setpoint_handler.py`)

Schema-aware configuration manager for follower command profiles.

```python
from classes.setpoint_handler import SetpointHandler

# Create handler for specific follower profile
handler = SetpointHandler('chase_follower')
handler.set_field('forward_speed', 2.5)
handler.set_field('height_offset', -1.0)
```

### 4. Factory Systems

- **TrackerFactory**: Dynamic tracker instantiation
- **FollowerFactory**: Schema-aware follower creation and management

---

## ⚙️ Schema Configuration System

### Tracker Schema (`configs/tracker_schemas.yaml`)

Defines all available tracker data types and their validation rules:

```yaml
schema_version: "1.0"
description: "PixEagle Tracker Data Type Schema Definitions"

tracker_data_types:
  POSITION_2D:
    name: "2D Position Tracking"
    description: "Basic 2D position tracking with normalized coordinates"
    required_fields: [position_2d]
    optional_fields: [confidence, timestamp]
    validation:
      position_2d:
        type: "tuple"
        length: 2
        range: [-2.0, 2.0]  # Extended range for off-screen tracking
      confidence:
        type: "float" 
        range: [0.0, 1.0]

  MULTI_TARGET:
    name: "Multi-Target Detection"
    description: "Multiple object detection with individual tracking"
    required_fields: [detections]
    optional_fields: [primary_target, detection_count]
    validation:
      detections:
        type: "list"
        max_length: 50
      primary_target:
        type: "int"
        range: [0, 49]
```

### Follower Command Schema (`configs/follower_commands.yaml`)

Defines follower profiles and their command structures:

```yaml
schema_version: "1.0"
follower_profiles:
  chase_follower:
    display_name: "Chase Follower"
    description: "Direct pursuit of target with configurable parameters"
    control_type: "velocity_body"
    required_fields: [forward_speed, lateral_speed, vertical_speed]
    optional_fields: [height_offset, safety_distance]

command_fields:
  forward_speed:
    type: "float"
    limits: {min: -5.0, max: 10.0}
    default: 2.0
    units: "m/s"
    description: "Forward velocity component"
    clamp: true
```

---

## 🔨 Creating Custom Trackers

### Step 1: Define Data Schema

Add your new tracker data type to `configs/tracker_schemas.yaml`:

```yaml
tracker_data_types:
  DEPTH_TRACKING:
    name: "3D Depth Tracking" 
    description: "Tracking with depth estimation and 3D positioning"
    required_fields: [position_3d, depth_estimate]
    optional_fields: [confidence, depth_confidence]
    validation:
      position_3d:
        type: "tuple"
        length: 3
        range: [-2.0, 2.0]
      depth_estimate:
        type: "float"
        range: [0.1, 100.0]
      depth_confidence:
        type: "float"
        range: [0.0, 1.0]
```

### Step 2: Create Tracker Implementation

Create your tracker class in `src/classes/trackers/`:

```python
# src/classes/trackers/depth_tracker.py
import cv2
import numpy as np
from typing import Optional, Tuple
from .base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType

class DepthTracker(BaseTracker):
    """Custom depth-aware tracking implementation"""

    def __init__(self, video_handler, detector=None, app_controller=None):
        super().__init__(video_handler, detector, app_controller)
        self.depth_estimator = None  # Initialize your depth estimation model
        self.trackerName = "DepthTracker"

    def _create_tracker(self):
        """
        Creates and returns a new tracker instance.

        This polymorphic method is called by BaseTracker during __init__() and reset().
        Override this to return your specific tracker type (OpenCV, dlib, custom, etc.).

        Returns:
            Your tracker instance (e.g., cv2 tracker, dlib tracker, custom object)
        """
        return YourCustomTrackerClass()  # Replace with your tracker initialization

    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[TrackerOutput]]:
        """Main tracking update method"""
        if not self.tracking_started:
            return False, None
            
        # Your tracking logic here
        success, bbox = self._perform_tracking(frame)
        
        if success:
            # Calculate 3D position with depth
            position_2d = self._bbox_to_normalized_center(bbox)
            depth = self._estimate_depth(frame, bbox)
            position_3d = (*position_2d, depth)
            
            # Create validated output
            return True, TrackerOutput(
                data_type=TrackerDataType.DEPTH_TRACKING,
                position_3d=position_3d,
                depth_estimate=depth,
                confidence=self.get_confidence(),
                tracking_active=True
            )
        
        return False, TrackerOutput(
            data_type=TrackerDataType.DEPTH_TRACKING,
            tracking_active=False
        )
    
    def _estimate_depth(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> float:
        """Implement your depth estimation logic"""
        # Your custom depth estimation implementation
        return 5.0  # Placeholder
```

### Step 3: Register with Factory

Add your tracker to the tracker factory in `src/classes/trackers/tracker_factory.py`:

```python
def create_tracker(tracker_type: str, video_handler, detector=None, app_controller=None):
    """Factory function to create tracker instances"""
    
    trackers = {
        'csrt': CSRTTracker,
        'kcf': KCFTracker,
        'depth': DepthTracker,  # Add your tracker here
        # ... other trackers
    }
    
    if tracker_type.lower() in trackers:
        return trackers[tracker_type.lower()](video_handler, detector, app_controller)
    else:
        raise ValueError(f"Unknown tracker type: {tracker_type}")
```

### Step 4: Update TrackerDataType Enum

Add your data type to `src/classes/tracker_output.py`:

```python
from enum import Enum

class TrackerDataType(Enum):
    POSITION_2D = "position_2d"
    MULTI_TARGET = "multi_target" 
    DEPTH_TRACKING = "depth_tracking"  # Add your new type
```

---

## 🎯 Creating Custom Followers

### Step 1: Define Follower Profile

Add your follower configuration to `configs/follower_commands.yaml`:

```yaml
follower_profiles:
  formation_follower:
    display_name: "Formation Follower"
    description: "Maintains formation with multiple targets"
    control_type: "velocity_body"
    required_fields: [formation_offset_x, formation_offset_y, formation_offset_z]
    optional_fields: [formation_stiffness, leader_prediction]

command_fields:
  formation_offset_x:
    type: "float"
    limits: {min: -20.0, max: 20.0}
    default: -5.0
    units: "m"
    description: "X offset in formation"
    clamp: true
  formation_stiffness:
    type: "float"
    limits: {min: 0.1, max: 2.0}
    default: 1.0
    description: "Formation maintenance stiffness"
    clamp: true
```

### Step 2: Implement Follower Class

Create your follower in `src/classes/followers/`:

```python
# src/classes/followers/formation_follower.py
import math
import logging
from typing import Tuple, Dict, Any, List
from .base_follower import BaseFollower
from classes.setpoint_handler import SetpointHandler

logger = logging.getLogger(__name__)

class FormationFollower(BaseFollower):
    """Formation flying follower implementation"""
    
    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        # Initialize with schema profile
        self.setpoint_handler = SetpointHandler('formation_follower')
        super().__init__(px4_controller, initial_target_coords)
        
        self.leader_positions = []  # Track leader position history
        logger.info("Formation Follower initialized")
    
    def follow_target(self, target_coords: Tuple[float, float]) -> bool:
        """Execute formation following logic"""
        try:
            # Get current setpoints
            fields = self.setpoint_handler.get_fields()
            
            # Track leader positions for prediction
            self.leader_positions.append(target_coords)
            if len(self.leader_positions) > 10:
                self.leader_positions.pop(0)
            
            # Calculate formation position
            formation_x = target_coords[0] + fields['formation_offset_x']
            formation_y = target_coords[1] + fields['formation_offset_y']
            formation_z = fields['formation_offset_z']
            
            # Apply formation stiffness for smooth following
            stiffness = fields.get('formation_stiffness', 1.0)
            
            # Calculate control commands
            commands = self.calculate_formation_commands(
                (formation_x, formation_y, formation_z), 
                stiffness
            )
            
            # Send commands to PX4
            return self.send_velocity_command(
                commands['vx'], commands['vy'], commands['vz'], commands['yaw_rate']
            )
            
        except Exception as e:
            logger.error(f"Formation following error: {e}")
            return False
    
    def calculate_formation_commands(self, target_position: Tuple[float, float, float], 
                                   stiffness: float) -> Dict[str, float]:
        """Calculate formation-specific control commands"""
        # Your custom formation logic here
        return {
            'vx': target_position[0] * stiffness,
            'vy': target_position[1] * stiffness, 
            'vz': target_position[2] * stiffness,
            'yaw_rate': 0.0
        }
    
    def get_available_fields(self) -> List[str]:
        """Return available command fields"""
        return list(self.setpoint_handler.get_fields().keys())
    
    def get_display_name(self) -> str:
        return self.setpoint_handler.get_display_name()
    
    def get_description(self) -> str:
        return self.setpoint_handler.get_description()
    
    def get_control_type(self) -> str:
        return self.setpoint_handler.get_control_type()
```

### Step 3: Register with FollowerFactory

Add your follower to `src/classes/follower.py`:

```python
class FollowerFactory:
    @classmethod
    def _initialize_registry(cls):
        """Initialize follower registry with available implementations"""
        if cls._registry_initialized:
            return
            
        try:
            # Import all follower implementations
            from classes.followers.ground_target_follower import GroundTargetFollower
            from classes.followers.formation_follower import FormationFollower  # Add import
            # ... other imports
            
            # Register followers with their schema profile names
            cls._follower_registry = {
                'ground_view': GroundTargetFollower,
                'formation_follower': FormationFollower,  # Add registration
                # ... other registrations
            }
```

---

## 🔗 Integration Examples

### Example 1: Custom AI-Powered Tracker

```python
# src/classes/trackers/ai_tracker.py
import torch
import numpy as np
from typing import Optional, Tuple, List
from .base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType

class AITracker(BaseTracker):
    """AI-powered multi-target tracking with object classification"""
    
    def __init__(self, video_handler, detector=None, app_controller=None):
        super().__init__(video_handler, detector, app_controller)
        self.ai_model = self._load_ai_model()
        self.tracked_objects = []
        
    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[TrackerOutput]]:
        """AI-powered tracking update"""
        # Run AI inference
        detections = self._run_inference(frame)
        
        if detections:
            # Process multiple targets
            processed_detections = []
            for det in detections:
                processed_detections.append({
                    'bbox': det['bbox'],
                    'class': det['class'], 
                    'confidence': det['confidence'],
                    'position_2d': self._bbox_to_normalized_center(det['bbox'])
                })
            
            return True, TrackerOutput(
                data_type=TrackerDataType.MULTI_TARGET,
                detections=processed_detections,
                primary_target=0,  # First detection as primary
                detection_count=len(processed_detections),
                tracking_active=True
            )
        
        return False, TrackerOutput(
            data_type=TrackerDataType.MULTI_TARGET,
            tracking_active=False
        )
```

### Example 2: Precision Landing Follower

```python
# src/classes/followers/precision_landing_follower.py
from .base_follower import BaseFollower
from classes.setpoint_handler import SetpointHandler

class PrecisionLandingFollower(BaseFollower):
    """Precision landing with target alignment"""
    
    def __init__(self, px4_controller, initial_target_coords):
        self.setpoint_handler = SetpointHandler('precision_landing')
        super().__init__(px4_controller, initial_target_coords)
        
    def follow_target(self, target_coords: Tuple[float, float]) -> bool:
        """Execute precision landing approach"""
        fields = self.setpoint_handler.get_fields()
        
        # Calculate approach vector
        approach_speed = fields['approach_speed']
        alignment_threshold = fields['alignment_threshold']
        
        # Check alignment
        distance_to_target = math.sqrt(
            target_coords[0]**2 + target_coords[1]**2
        )
        
        if distance_to_target < alignment_threshold:
            # Execute landing
            return self.send_velocity_command(0, 0, approach_speed, 0)
        else:
            # Align with target
            return self.send_velocity_command(
                target_coords[0] * 2.0,  # Proportional control
                target_coords[1] * 2.0,
                0,  # Maintain altitude until aligned
                0
            )
```

### Example 3: Sensor Fusion Tracker

```python
# Schema definition for sensor fusion
tracker_data_types:
  SENSOR_FUSION:
    name: "Sensor Fusion Tracking"
    description: "Multi-sensor tracking with GPS, IMU, and vision"
    required_fields: [position_2d, sensor_data]
    optional_fields: [gps_coords, imu_data, confidence_matrix]
    validation:
      sensor_data:
        type: "dict"
        required_keys: [gps_available, imu_available, vision_available]
      gps_coords:
        type: "tuple"
        length: 2
      confidence_matrix:
        type: "list"
        max_length: 9

# Tracker implementation
class SensorFusionTracker(BaseTracker):
    """Multi-sensor fusion for robust tracking"""
    
    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[TrackerOutput]]:
        # Fuse vision, GPS, and IMU data
        vision_data = self._process_vision(frame)
        gps_data = self._get_gps_data()
        imu_data = self._get_imu_data()
        
        # Kalman filter or similar fusion algorithm
        fused_position = self._sensor_fusion(vision_data, gps_data, imu_data)
        
        return True, TrackerOutput(
            data_type=TrackerDataType.SENSOR_FUSION,
            position_2d=fused_position[:2],
            sensor_data={
                'gps_available': gps_data is not None,
                'imu_available': imu_data is not None,
                'vision_available': vision_data is not None
            },
            gps_coords=gps_data,
            imu_data=imu_data,
            confidence_matrix=self._calculate_confidence_matrix(),
            tracking_active=True
        )
```

### Example 4: dlib Correlation Filter Tracker

The dlib tracker is a production-ready, high-performance correlation filter tracker with PSR (Peak-to-Sidelobe Ratio) confidence scoring, designed specifically for aerial drone tracking scenarios.

#### Key Features

- **Three Performance Modes**: Fast (25-30 FPS), Balanced (18-25 FPS), Robust (12-18 FPS)
- **PSR-Based Confidence Scoring**: Converts PSR values to normalized 0.0-1.0 confidence scores
- **Adaptive Template Learning**: Configurable appearance adaptation for changing targets
- **Robust Failure Handling**: Consecutive failure threshold with graceful degradation
- **Full Schema Compliance**: Supports POSITION_2D, BBOX_CONFIDENCE, and VELOCITY_AWARE schemas

#### Configuration Example

```yaml
# In configs/config_default.yaml
DEFAULT_TRACKING_ALGORITHM: "dlib"

DLIB_Tracker:
  # Performance mode selection (fast, balanced, or robust)
  performance_mode: "balanced"

  # PSR-based confidence system
  psr_confidence_threshold: 7.0    # Min PSR for reliable tracking (5-7 marginal)
  psr_high_confidence: 20.0        # PSR above this = excellent tracking
  psr_low_confidence: 5.0          # PSR below this = poor tracking

  # Failure tolerance
  failure_threshold: 5             # Consecutive failures before declaring lost
  confidence_smoothing_alpha: 0.7  # EMA smoothing factor

  # Validation & robustness
  validation_start_frame: 10       # Grace period before validation
  max_scale_change_per_frame: 0.5  # Max size change per frame
  max_motion_per_frame: 0.6        # Max motion as fraction of diagonal

  # Appearance adaptation
  appearance_learning_rate: 0.08   # Template update learning rate

  # Integration features
  enable_validation: true          # Enable robustness validation
  enable_estimator_integration: false  # Kalman integration (robust mode)
  enable_template_matching: true   # Re-detection on failure
```

#### Schema Definition

```yaml
# In configs/tracker_schemas.yaml
tracker_types:
  DlibTracker:
    name: "dlib Correlation Tracker"
    description: "Fast correlation filter tracker with PSR confidence scoring (Danelljan et al. 2014 DSST)"
    supported_schemas:
      - POSITION_2D
      - BBOX_CONFIDENCE
      - VELOCITY_AWARE  # When estimator is enabled
    capabilities:
      - fast_correlation_filter
      - psr_confidence_scoring
      - scale_adaptation
      - appearance_learning
      - occlusion_handling
      - performance_modes
    performance:
      accuracy: "high"
      speed: "very_fast"
      latency: "minimal"
      cpu_usage: "low"
      recommended_for: "aerial_drone_tracking_fast_scenarios"
```

#### Implementation Highlights

```python
# src/classes/trackers/dlib_tracker.py
import dlib
import cv2
import numpy as np
from typing import Tuple, Optional
from .base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType

class DlibTracker(BaseTracker):
    """
    dlib correlation filter tracker with PSR confidence scoring.

    Based on Danelljan et al. 2014 DSST algorithm, providing excellent
    performance for aerial drone tracking with minimal CPU usage.
    """

    def __init__(self, video_handler, detector=None, app_controller=None):
        super().__init__(video_handler, detector, app_controller)

        # Initialize dlib correlation tracker
        self.tracker = dlib.correlation_tracker()

        # Load performance mode configuration
        self._configure_performance_mode()

        # PSR confidence system
        self.psr_confidence_threshold = config.get('psr_confidence_threshold', 7.0)
        self.psr_high_confidence = config.get('psr_high_confidence', 20.0)
        self.psr_low_confidence = config.get('psr_low_confidence', 5.0)

    def _psr_to_confidence(self, psr: float) -> float:
        """
        Convert PSR (Peak-to-Sidelobe Ratio) to normalized confidence.

        PSR Ranges (based on Bolme et al. 2010 MOSSE):
        - < 5.0: Poor tracking (confidence 0.0 - 0.25)
        - 5.0 - 7.0: Marginal (confidence 0.25 - 0.50)
        - 7.0 - 20.0: Good tracking (confidence 0.50 - 0.90)
        - > 20.0: Excellent tracking (confidence 0.90 - 1.00)
        """
        psr_clamped = max(0.0, min(psr, 30.0))

        if psr_clamped < self.psr_low_confidence:
            confidence = psr_clamped / (self.psr_low_confidence * 2.0)
        elif psr_clamped < self.psr_confidence_threshold:
            confidence = 0.25 + (psr_clamped - self.psr_low_confidence) / \
                        (self.psr_confidence_threshold - self.psr_low_confidence) * 0.25
        elif psr_clamped < self.psr_high_confidence:
            confidence = 0.5 + (psr_clamped - self.psr_confidence_threshold) / \
                        (self.psr_high_confidence - self.psr_confidence_threshold) * 0.4
        else:
            confidence = 0.9 + min(0.1, (psr_clamped - self.psr_high_confidence) / 20.0)

        return max(0.0, min(1.0, confidence))

    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[Tuple[int, int, int, int]]]:
        """Update tracker with current frame"""
        if not self.tracking_started:
            return False, self.bbox

        # Run dlib tracker update
        psr = self.tracker.update(frame)

        # Get updated position
        pos = self.tracker.get_position()
        detected_bbox = (int(pos.left()), int(pos.top()),
                        int(pos.width()), int(pos.height()))

        # Convert PSR to normalized confidence
        raw_confidence = self._psr_to_confidence(psr)

        # Apply confidence smoothing
        self.smoothed_confidence = (
            self.confidence_smoothing_alpha * raw_confidence +
            (1.0 - self.confidence_smoothing_alpha) * self.smoothed_confidence
        )

        # Handle tracking failures
        if self.smoothed_confidence < self.min_confidence:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.failure_threshold:
                self.tracking_started = False
                self.logger.warning("dlib tracker lost target")
                return False, self.bbox
        else:
            self.consecutive_failures = 0
            self.bbox = detected_bbox

        return True, self.bbox

    def get_output(self) -> TrackerOutput:
        """Return schema-compliant tracker output"""
        if not self.tracking_started:
            return TrackerOutput(
                data_type=TrackerDataType.POSITION_2D,
                tracking_active=False
            )

        # Calculate normalized position
        position_2d = self._bbox_to_normalized_center(self.bbox)
        normalized_bbox = self._bbox_to_normalized_bbox(self.bbox)

        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            position_2d=position_2d,
            confidence=self.smoothed_confidence,
            bbox=self.bbox,
            normalized_bbox=normalized_bbox,
            tracking_active=True,
            timestamp=time.time()
        )
```

#### Usage Example

To use the dlib tracker in your PixEagle application:

1. **Install dlib** (if not already installed):
   ```bash
   pip install dlib
   # Or using conda (faster on Windows):
   # conda install -c conda-forge dlib
   ```

2. **Update configuration**:
   ```yaml
   # In configs/config_default.yaml
   DEFAULT_TRACKING_ALGORITHM: "dlib"
   ```

3. **Run PixEagle**:
   ```bash
   python main.py
   ```

4. **Test different performance modes**:
   ```yaml
   # Fast mode - maximum FPS (25-30 FPS)
   DLIB_Tracker:
     performance_mode: "fast"

   # Balanced mode - default (18-25 FPS)
   DLIB_Tracker:
     performance_mode: "balanced"

   # Robust mode - maximum accuracy (12-18 FPS)
   DLIB_Tracker:
     performance_mode: "robust"
     enable_estimator_integration: true
   ```

#### Tuning Scenarios

**Scenario 1: High-Speed Chase**
```yaml
DLIB_Tracker:
  performance_mode: "fast"
  max_motion_per_frame: 0.8        # Allow rapid motion
  appearance_learning_rate: 0.12   # Faster adaptation
  failure_threshold: 3             # Quicker recovery
```

**Scenario 2: Rotating/Tumbling Target**
```yaml
DLIB_Tracker:
  performance_mode: "balanced"
  appearance_learning_rate: 0.15   # Aggressive learning
  max_scale_change_per_frame: 0.7  # Allow rotation/scale
  psr_confidence_threshold: 6.0    # More tolerant
```

**Scenario 3: Resource-Constrained Platform**
```yaml
DLIB_Tracker:
  performance_mode: "fast"
  enable_validation: false         # Skip validation overhead
  enable_template_matching: false  # Disable re-detection
```

**Scenario 4: Critical Mission (Maximum Reliability)**
```yaml
DLIB_Tracker:
  performance_mode: "robust"
  enable_estimator_integration: true
  enable_template_matching: true
  failure_threshold: 10            # Very tolerant
  validation_start_frame: 20       # Longer grace period
```

**Scenario 5: Occlusion-Prone Environment**
```yaml
DLIB_Tracker:
  performance_mode: "balanced"
  enable_template_matching: true   # Re-detection enabled
  failure_threshold: 8             # Tolerate occlusions
  appearance_learning_rate: 0.05   # Conservative updates
  psr_low_confidence: 4.0          # Lower threshold
```

#### Performance Comparison

| Mode      | FPS Range | Accuracy | CPU Usage | Best For                          |
|-----------|-----------|----------|-----------|-----------------------------------|
| Fast      | 25-30     | High     | Low       | High-speed tracking, real-time    |
| Balanced  | 18-25     | High     | Medium    | General aerial tracking (default) |
| Robust    | 12-18     | Very High| Medium    | Critical missions, validation     |

#### Integration with PixEagle Ecosystem

The dlib tracker seamlessly integrates with all PixEagle subsystems:

- **Detector Integration**: Supports template matching re-detection on failure
- **Estimator Integration**: Works with Kalman filter in robust mode
- **Follower Compatibility**: Compatible with all follower modes (chase, ground_view, etc.)
- **Smart Override**: Automatically switches to SmartTracker when enabled
- **Schema Compliance**: Full POSITION_2D, BBOX_CONFIDENCE, VELOCITY_AWARE support

#### Testing

Use the provided test script to validate dlib integration:

```bash
# Test all performance modes
python tools/test_dlib_tracker.py

# Test specific mode with video
python tools/test_dlib_tracker.py --mode balanced --video test_footage.mp4

# Test PSR confidence mapping
python tools/test_dlib_tracker.py --test-psr
```

---

## ✅ Best Practices

### 1. Schema Design Guidelines

- **Keep schemas versioned** for backward compatibility
- **Use descriptive names** for all fields and data types
- **Define appropriate validation ranges** to prevent invalid data
- **Include comprehensive descriptions** for all schema elements
- **Use consistent units** and document them clearly

### 2. Tracker Implementation Best Practices

- **Always validate input parameters** before processing
- **Handle edge cases gracefully** (off-screen targets, occlusion, etc.)
- **Implement proper error handling** with informative logging
- **Use appropriate log levels** (DEBUG for detailed info, INFO for status)
- **Maintain thread safety** if your tracker uses multi-threading

### 3. Follower Implementation Best Practices

- **Validate target coordinates** before processing commands
- **Implement safety limits** for all movement commands
- **Use smooth control transitions** to avoid abrupt movements
- **Provide comprehensive telemetry** for debugging and monitoring
- **Handle connection failures** gracefully

### 4. Performance Optimization

```python
# Good: Efficient data validation
def validate_efficiently(self, data):
    """Optimized validation with early returns"""
    if not self.tracking_active:
        return True, []  # Skip validation when inactive
    
    # Fast path for common cases
    if self.data_type == TrackerDataType.POSITION_2D:
        return self._validate_position_2d(data)
    
    # Full validation for complex types
    return self._validate_full_schema(data)

# Good: Batch operations
def update_multiple_targets(self, targets):
    """Process multiple targets efficiently"""
    results = []
    for target in targets:
        result = self._process_single_target(target)
        results.append(result)
    return results
```

### 5. Error Handling Patterns

```python
# Good: Comprehensive error handling
def follow_target(self, target_coords: Tuple[float, float]) -> bool:
    """Robust follower implementation"""
    try:
        # Validate inputs
        if not self.validate_target_coordinates(target_coords):
            logger.warning(f"Invalid target coordinates: {target_coords}")
            return False
        
        # Execute following logic
        commands = self.calculate_control_commands(target_coords)
        
        # Send commands with retry logic
        for attempt in range(3):
            if self.send_commands(commands):
                return True
            logger.warning(f"Command send failed, attempt {attempt + 1}")
            
        return False
        
    except Exception as e:
        logger.error(f"Follow target error: {e}")
        # Implement safe fallback behavior
        self.execute_safe_stop()
        return False
```

---

## 🔍 Troubleshooting

### Common Issues and Solutions

#### 1. Schema Validation Failures

**Problem**: `ValidationError: Field 'position_2d' validation failed`

**Solutions**:
- Check that coordinate values are within the defined range [-2.0, 2.0]
- Ensure position_2d is a tuple with exactly 2 elements
- Verify data types match schema requirements

```python
# Debug schema validation
is_valid, errors = validate_tracker_data('POSITION_2D', data, tracking_active=True)
if not is_valid:
    logger.error(f"Validation errors: {errors}")
```

#### 2. Tracker Registration Issues

**Problem**: `ValueError: Unknown tracker type: my_custom_tracker`

**Solutions**:
- Ensure your tracker is imported in `tracker_factory.py`
- Add your tracker to the factory dictionary
- Check that class names match exactly

#### 3. Follower Profile Not Found

**Problem**: `ValueError: Profile 'my_profile' not found`

**Solutions**:
- Verify profile name in `follower_commands.yaml`
- Check for typos in profile name
- Ensure YAML file is valid and loadable

#### 4. Off-Screen Coordinate Issues

**Problem**: Tracking fails when target moves outside camera view

**Solutions**:
- Use extended coordinate range [-2.0, 2.0] in schema
- Implement predictive tracking for off-screen objects
- Add boundary detection logic

```python
def handle_off_screen_target(self, position):
    """Handle targets that move off-screen"""
    if any(abs(coord) > 1.0 for coord in position):
        # Target is off-screen, use prediction
        return self.predict_target_position()
    return position
```

#### 5. Performance Issues

**Problem**: System runs slowly with new tracker implementation

**Solutions**:
- Profile your tracker code to identify bottlenecks
- Use efficient data structures and algorithms
- Implement frame skipping for expensive operations
- Consider GPU acceleration for AI-based trackers

```python
# Performance monitoring
import time

def update_with_timing(self, frame):
    """Tracker update with performance monitoring"""
    start_time = time.time()
    result = self.update(frame)
    elapsed = time.time() - start_time
    
    if elapsed > 0.1:  # Log slow operations
        logger.warning(f"Slow tracker update: {elapsed:.3f}s")
    
    return result
```

### Debugging Tools

#### 1. Schema Validation Testing

```python
# Test schema validation independently
from classes.schema_manager import validate_tracker_data

def test_schema_validation():
    """Test custom tracker data validation"""
    test_data = {
        'position_2d': (0.5, 0.3),
        'confidence': 0.87
    }
    
    is_valid, errors = validate_tracker_data('POSITION_2D', test_data, True)
    print(f"Valid: {is_valid}, Errors: {errors}")
```

#### 2. Follower Command Testing

```python
# Test follower commands
from classes.setpoint_handler import SetpointHandler

def test_follower_commands():
    """Test follower command validation"""
    handler = SetpointHandler('chase_follower')
    
    try:
        handler.set_field('forward_speed', 15.0)  # Should be clamped
        print(f"Forward speed: {handler.get_fields()['forward_speed']}")
    except ValueError as e:
        print(f"Validation error: {e}")
```

#### 3. System Status Monitoring

The system provides comprehensive status monitoring:

```
SYSTEM: Tracking: CUSTOM (MyTracker) | Following: Active | MAVLink: Connected | PX4: Connected
TEMPLATE: Updated (Conf: 0.87, Frame: 120)
MAVLINK: Connected | Armed: Armed | Alt: 15.2m | GPS: -33.856159,151.215256
```

---

## 📚 API Reference

### SchemaManager

```python
def validate_tracker_data(data_type: str, data: Dict[str, Any], 
                         tracking_active: bool = True) -> Tuple[bool, List[str]]:
    """
    Validates tracker data against schema definitions.
    
    Args:
        data_type: The tracker data type (e.g., 'POSITION_2D')
        data: Dictionary of data fields to validate
        tracking_active: Whether tracking is currently active
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
```

### TrackerOutput

```python
class TrackerOutput:
    """Type-safe tracker output with schema validation"""
    
    def __init__(self, data_type: TrackerDataType, tracking_active: bool = False, **kwargs):
        """
        Initialize tracker output with validation.
        
        Args:
            data_type: The type of tracking data
            tracking_active: Whether tracking is currently active
            **kwargs: Additional data fields based on schema
        """
```

### SetpointHandler

```python
class SetpointHandler:
    """Schema-aware configuration manager for follower commands"""
    
    def __init__(self, profile_name: str):
        """Initialize with specific follower profile"""
        
    def set_field(self, field_name: str, value: float):
        """Set field value with validation and clamping"""
        
    def get_fields(self) -> Dict[str, float]:
        """Get all current field values"""
        
    def get_control_type(self) -> str:
        """Get control type for this profile"""
```

### FollowerFactory

```python
class FollowerFactory:
    """Schema-aware factory for follower creation and management"""
    
    @classmethod
    def create_follower(cls, profile_name: str, px4_controller, 
                       initial_target_coords: Tuple[float, float]):
        """Create follower instance for specified profile"""
        
    @classmethod
    def get_available_modes(cls) -> List[str]:
        """Get list of all available follower modes"""
        
    @classmethod
    def register_follower(cls, profile_name: str, follower_class: Type) -> bool:
        """Register new follower implementation"""
```

---

## 🎯 Advanced Topics

### 1. Custom Validation Rules

You can extend the schema system with custom validation logic:

```yaml
# In tracker_schemas.yaml
validation_rules:
  custom_range_check:
    description: "Custom validation for specific use cases"
    fields: [position_2d, velocity_2d]
    validation_function: "validate_movement_consistency"
```

### 2. Dynamic Schema Loading

For advanced use cases, schemas can be loaded dynamically:

```python
from classes.schema_manager import SchemaManager

# Load custom schema from different location
schema_manager = SchemaManager(schema_path="custom/path/configs/tracker_schemas.yaml")
```

### 3. Multi-Stage Validation

Implement complex validation pipelines:

```python
def validate_complex_tracker_data(self, data):
    """Multi-stage validation for complex trackers"""
    # Stage 1: Schema validation
    is_valid, errors = validate_tracker_data(self.data_type, data)
    if not is_valid:
        return False, errors
    
    # Stage 2: Business logic validation
    if not self.validate_business_rules(data):
        return False, ["Business rule validation failed"]
    
    # Stage 3: Performance validation
    if not self.validate_performance_metrics(data):
        return False, ["Performance validation failed"]
    
    return True, []
```

---

## 🔄 Version History

### v3.0 (Current)
- ✅ YAML-based schema configuration system
- ✅ Dynamic validation with extended coordinate ranges
- ✅ Schema-aware follower factory system
- ✅ Production-ready logging and monitoring
- ✅ Comprehensive developer documentation

### v2.0
- Basic tracker and follower implementations
- Hardcoded data validation
- Limited extensibility

### v1.0
- Initial tracker implementation
- Basic following modes

---

## 🤝 Contributing

### Adding New Features

1. **Define the schema** in appropriate YAML file
2. **Implement the functionality** following established patterns
3. **Add comprehensive tests** for validation and integration
4. **Update documentation** with examples and API reference
5. **Test with existing system** to ensure compatibility

### Pull Request Guidelines

- Include schema changes in separate commits
- Provide comprehensive test coverage
- Update relevant documentation
- Follow existing code style and patterns
- Include performance impact analysis

---

## 📞 Support

### Documentation
- **Schema Files**: `configs/tracker_schemas.yaml`, `configs/follower_commands.yaml`
- **Core Classes**: `src/classes/schema_manager.py`, `src/classes/tracker_output.py`
- **Examples**: See `src/classes/trackers/` and `src/classes/followers/` directories

### Troubleshooting
- Enable DEBUG logging for detailed validation information
- Use the provided testing utilities for schema validation
- Check system status logs for integration issues

### Community
- GitHub Issues for bug reports and feature requests
- Discussions for implementation questions and design feedback

---

*This guide is part of the PixEagle project. For the latest updates and additional documentation, visit the project repository.*

**Last Updated**: September 2025  
**Version**: 3.0  
**Authors**: PixEagle Development Team