# src/classes/tracker_output.py

"""
TrackerOutput Module - Flexible Tracker Data Schema
===================================================

This module defines the unified data schema for all tracker types, providing
a flexible and extensible structure that supports various tracking modalities
while maintaining backwards compatibility.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle  
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- Flexible schema supporting multiple tracker types
- Type-safe data structures with validation
- Backwards compatibility with existing trackers
- Extensible design for future tracker types
- Clean separation between tracker internals and outputs
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Tuple, Dict, Any, List
import time
import logging

logger = logging.getLogger(__name__)

# Import schema manager for dynamic schema handling
try:
    from classes.schema_manager import get_schema_manager, validate_tracker_data
    SCHEMA_MANAGER_AVAILABLE = True
except ImportError:
    logger.warning("Schema manager not available, falling back to hardcoded schemas")
    SCHEMA_MANAGER_AVAILABLE = False

class TrackerDataType(Enum):
    """
    Enumeration of different data types that trackers can provide.
    
    This enum defines the various modalities of tracking data, allowing
    followers to understand what type of information is available.
    
    Note: When schema manager is available, these values are loaded from YAML configuration.
    """
    POSITION_2D = "POSITION_2D"           # Standard 2D position tracking
    POSITION_3D = "POSITION_3D"           # 3D position with depth
    ANGULAR = "ANGULAR"                   # Bearing/elevation angles
    GIMBAL_ANGLES = "GIMBAL_ANGLES"       # Gimbal yaw, pitch, roll angles
    BBOX_CONFIDENCE = "BBOX_CONFIDENCE"   # Bounding box with confidence
    VELOCITY_AWARE = "VELOCITY_AWARE"     # Position + velocity estimates
    EXTERNAL = "EXTERNAL"                 # External data source (e.g., radar)
    MULTI_TARGET = "MULTI_TARGET"         # Multiple target tracking

# Initialize schema manager if available
if SCHEMA_MANAGER_AVAILABLE:
    try:
        _schema_manager = get_schema_manager()
        logger.info("Schema manager initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize schema manager: {e}")
        SCHEMA_MANAGER_AVAILABLE = False

@dataclass
class TrackerOutput:
    """
    Unified tracker output schema supporting multiple tracking modalities.
    
    This dataclass provides a flexible structure that can accommodate
    different types of tracking data while maintaining type safety and
    providing backwards compatibility.
    
    Attributes:
        data_type (TrackerDataType): Type of tracking data provided
        timestamp (float): Unix timestamp when data was generated
        tracking_active (bool): Whether tracking is currently active
        tracker_id (str): Unique identifier for the tracker instance
        
        # Position Data (various formats)
        position_2d (Optional[Tuple[float, float]]): Normalized 2D position
        position_3d (Optional[Tuple[float, float, float]]): 3D position with depth
        angular (Optional[Tuple[float, ...]]): Angular data - 2D for bearing/elevation, 3D for gimbal (yaw, pitch, roll)
        
        # Bounding Box Data
        bbox (Optional[Tuple[int, int, int, int]]): Pixel coordinates (x, y, w, h)
        normalized_bbox (Optional[Tuple[float, float, float, float]]): Normalized bbox
        
        # Quality/Confidence Metrics
        confidence (Optional[float]): Tracking confidence [0.0, 1.0]
        quality_metrics (Dict[str, float]): Additional quality indicators
        
        # Motion Data
        velocity (Optional[Tuple[float, float]]): Velocity estimates (vx, vy)
        acceleration (Optional[Tuple[float, float]]): Acceleration estimates
        
        # Multi-target Support
        target_id (Optional[int]): Target ID for multi-target scenarios
        targets (Optional[List[Dict[str, Any]]]): Multiple target data
        
        # Raw/Custom Data
        raw_data (Dict[str, Any]): Tracker-specific raw data
        metadata (Dict[str, Any]): Additional metadata
    """
    
    # Required fields
    data_type: TrackerDataType
    timestamp: float
    tracking_active: bool
    tracker_id: str = "default"
    
    # Position data (mutually exclusive based on data_type)
    position_2d: Optional[Tuple[float, float]] = None
    position_3d: Optional[Tuple[float, float, float]] = None  
    angular: Optional[Tuple[float, ...]] = None  # Flexible tuple for 2D angles or 3D gimbal angles
    
    # Bounding box data
    bbox: Optional[Tuple[int, int, int, int]] = None
    normalized_bbox: Optional[Tuple[float, float, float, float]] = None
    geometry_type: Optional[str] = None  # aabb | obb | polygon
    oriented_bbox: Optional[Tuple[float, float, float, float, float]] = None
    polygon: Optional[List[Tuple[float, float]]] = None
    normalized_polygon: Optional[List[Tuple[float, float]]] = None
    
    # Quality metrics
    confidence: Optional[float] = None
    quality_metrics: Dict[str, float] = field(default_factory=dict)
    
    # Motion data
    velocity: Optional[Tuple[float, float]] = None
    acceleration: Optional[Tuple[float, float]] = None
    
    # Multi-target support
    target_id: Optional[int] = None
    targets: Optional[List[Dict[str, Any]]] = None
    
    # Raw/custom data
    raw_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Schema-specific fields (handled as optional kwargs)
    gimbal_metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate the tracker output after initialization."""
        self.validate()
    
    def validate(self) -> bool:
        """
        Validates the tracker output for consistency and completeness.
        Uses schema manager for validation when available, falls back to hardcoded validation.
        
        Returns:
            bool: True if valid, raises ValueError if invalid
        """
        # Basic validation
        if self.timestamp <= 0:
            raise ValueError("Timestamp must be positive")
        
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        
        # Use schema manager validation if available
        if SCHEMA_MANAGER_AVAILABLE:
            try:
                data_dict = {
                    'position_2d': self.position_2d,
                    'position_3d': self.position_3d,
                    'angular': self.angular,
                    'bbox': self.bbox,
                    'normalized_bbox': self.normalized_bbox,
                    'geometry_type': self.geometry_type,
                    'oriented_bbox': self.oriented_bbox,
                    'polygon': self.polygon,
                    'normalized_polygon': self.normalized_polygon,
                    'targets': self.targets,
                    'confidence': self.confidence,
                    'velocity': self.velocity
                }
                
                is_valid, errors = validate_tracker_data(
                    self.data_type.value.upper(), 
                    data_dict, 
                    self.tracking_active
                )
                
                if not is_valid:
                    raise ValueError(f"Schema validation failed: {'; '.join(errors)}")
                
                return True
                
            except Exception as e:
                logger.error(f"Schema validation failed: {e}")
                raise ValueError(f"Schema validation is required but failed: {e}")
        else:
            logger.warning("Schema manager not available - validation may be incomplete")
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the TrackerOutput to a dictionary for JSON serialization.
        
        Returns:
            Dict[str, Any]: Dictionary representation
        """
        data = asdict(self)
        data['data_type'] = self.data_type.value  # Convert enum to string
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrackerOutput':
        """
        Creates a TrackerOutput instance from a dictionary.
        
        Args:
            data (Dict[str, Any]): Dictionary containing tracker data
            
        Returns:
            TrackerOutput: New instance
        """
        # Convert string back to enum
        if 'data_type' in data and isinstance(data['data_type'], str):
            data['data_type'] = TrackerDataType(data['data_type'])
        
        return cls(**data)
    
    def has_position_data(self) -> bool:
        """Returns True if any position data is available."""
        return (self.position_2d is not None or 
                self.position_3d is not None or 
                self.angular is not None)
    
    def get_primary_position(self) -> Optional[Tuple[float, float]]:
        """
        Returns the primary 2D position regardless of data type.
        
        Returns:
            Optional[Tuple[float, float]]: 2D position or None
        """
        if self.position_2d:
            return self.position_2d
        elif self.position_3d:
            return self.position_3d[:2]  # Extract x, y from 3D
        else:
            return None
    
    def get_confidence_or_default(self, default: float = 1.0) -> float:
        """
        Returns confidence value or default if not available.
        
        Args:
            default (float): Default confidence value
            
        Returns:
            float: Confidence value
        """
        return self.confidence if self.confidence is not None else default
    
    def is_high_confidence(self, threshold: float = 0.7) -> bool:
        """
        Checks if tracking confidence is above threshold.
        
        Args:
            threshold (float): Confidence threshold
            
        Returns:
            bool: True if high confidence
        """
        return self.get_confidence_or_default() >= threshold

def create_legacy_tracker_output(
    center: Optional[Tuple[int, int]] = None,
    normalized_center: Optional[Tuple[float, float]] = None,
    bbox: Optional[Tuple[int, int, int, int]] = None,
    normalized_bbox: Optional[Tuple[float, float, float, float]] = None,
    confidence: Optional[float] = None,
    tracking_active: bool = False
) -> TrackerOutput:
    """
    Creates a TrackerOutput from legacy tracker data for backwards compatibility.
    
    Args:
        center: Pixel center coordinates
        normalized_center: Normalized center coordinates  
        bbox: Pixel bounding box
        normalized_bbox: Normalized bounding box
        confidence: Tracking confidence
        tracking_active: Whether tracking is active
        
    Returns:
        TrackerOutput: Compatible output structure
    """
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=tracking_active,
        tracker_id="legacy",
        position_2d=normalized_center,
        bbox=bbox,
        normalized_bbox=normalized_bbox,
        confidence=confidence,
        metadata={"legacy_format": True}
    )

# Backwards compatibility aliases
LegacyTrackerData = TrackerOutput  # For migration ease

if __name__ == "__main__":
    # Example usage and testing
    
    # Create a 2D position tracker output
    output_2d = TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        position_2d=(0.1, -0.2),
        confidence=0.8
    )
    
    print("2D Position Output:", output_2d.to_dict())
    
    # Create a 3D position tracker output
    output_3d = TrackerOutput(
        data_type=TrackerDataType.POSITION_3D,
        timestamp=time.time(),
        tracking_active=True,
        position_3d=(0.1, -0.2, 5.3),
        position_2d=(0.1, -0.2),  # Required: 2D projection of 3D position
        confidence=0.9
    )
    
    print("3D Position Output:", output_3d.to_dict())
    
    # Create an angular tracker output
    output_angular = TrackerOutput(
        data_type=TrackerDataType.ANGULAR,
        timestamp=time.time(),
        tracking_active=True,
        angular=(45.0, -10.0),
        confidence=0.85
    )
    
    print("Angular Output:", output_angular.to_dict())
