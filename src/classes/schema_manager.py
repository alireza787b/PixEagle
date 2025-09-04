# src/classes/schema_manager.py

"""
Schema Manager Module
====================

This module provides centralized schema management for the PixEagle tracker system.
It loads schema configurations from YAML files and provides validation,
compatibility checking, and extensibility support.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- YAML-based schema configuration
- Dynamic schema loading and validation
- Compatibility matrix for trackers and followers
- Extensible design for future tracker types
"""

import yaml
import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple
from pathlib import Path
import os

logger = logging.getLogger(__name__)

class TrackerDataType(Enum):
    """
    Dynamically generated enum from YAML configuration.
    This replaces the hardcoded enum in tracker_output.py
    """
    pass

class SchemaManager:
    """
    Manages tracker schemas loaded from YAML configuration files.
    Provides validation, compatibility checking, and extensibility support.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the schema manager.
        
        Args:
            config_path (Optional[str]): Path to schema configuration file
        """
        self.config_path = config_path or self._get_default_config_path()
        self.schemas: Dict[str, Any] = {}
        self.tracker_types: Dict[str, Any] = {}
        self.compatibility: Dict[str, Any] = {}
        self._loaded = False
        
        # Load schemas on initialization
        self.load_schemas()
    
    def _get_default_config_path(self) -> str:
        """Get the default path to the schema configuration file."""
        # Get the project root directory
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent  # Go up to PixEagle root
        config_path = project_root / "configs" / "tracker_schemas.yaml"
        return str(config_path)
    
    def load_schemas(self) -> bool:
        """
        Load schemas from YAML configuration file.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not os.path.exists(self.config_path):
                logger.error(f"Schema configuration file not found: {self.config_path}")
                return False
            
            with open(self.config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
            
            # Load schema sections
            self.schemas = config.get('tracker_data_types', {})
            self.tracker_types = config.get('tracker_types', {})
            self.compatibility = config.get('compatibility', {})
            
            # Generate dynamic enum values
            self._generate_enum()
            
            self._loaded = True
            logger.info(f"Loaded {len(self.schemas)} tracker schemas from {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load schemas from {self.config_path}: {e}")
            return False
    
    def _generate_enum(self):
        """Log loaded schema types for system verification."""
        # System is now fully YAML-driven - enum values are created dynamically from YAML
        logger.info(f"Loaded schema types: {list(self.schemas.keys())}")
        
        # Validate schema completeness
        if len(self.schemas) == 0:
            logger.warning("No tracker schemas loaded - check YAML configuration")
        else:
            logger.debug(f"Successfully loaded {len(self.schemas)} tracker data type schemas")
    
    def get_schema(self, schema_type: str) -> Optional[Dict[str, Any]]:
        """
        Get schema configuration for a specific data type.
        
        Args:
            schema_type (str): The schema type name
            
        Returns:
            Optional[Dict[str, Any]]: Schema configuration or None
        """
        return self.schemas.get(schema_type)
    
    def get_tracker_info(self, tracker_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific tracker type.
        
        Args:
            tracker_name (str): Name of the tracker
            
        Returns:
            Optional[Dict[str, Any]]: Tracker information or None
        """
        return self.tracker_types.get(tracker_name)
    
    def validate_tracker_output(self, data_type: str, data: Dict[str, Any], 
                              tracking_active: bool = True) -> Tuple[bool, List[str]]:
        """
        Validate tracker output against schema requirements.
        
        Args:
            data_type (str): The data type being validated
            data (Dict[str, Any]): The data to validate
            tracking_active (bool): Whether tracking is currently active
            
        Returns:
            Tuple[bool, List[str]]: (is_valid, list_of_errors)
        """
        schema = self.get_schema(data_type)
        if not schema:
            return False, [f"Unknown schema type: {data_type}"]
        
        errors = []
        
        # Only validate required fields when tracking is active
        if tracking_active:
            required_fields = schema.get('required_fields', [])
            for field in required_fields:
                if field == 'bbox_or_normalized_bbox':
                    # Special case: at least one bbox field must exist
                    if not (data.get('bbox') or data.get('normalized_bbox')):
                        errors.append("Either 'bbox' or 'normalized_bbox' is required")
                elif field not in data or data[field] is None:
                    errors.append(f"Required field '{field}' is missing")
        
        # Validate field types and constraints
        validation_rules = schema.get('validation', {})
        for field_name, rules in validation_rules.items():
            if field_name in data and data[field_name] is not None:
                field_errors = self._validate_field(field_name, data[field_name], rules)
                errors.extend(field_errors)
        
        # Special validation for POSITION_3D: ensure 2D projection consistency
        if data_type == 'POSITION_3D' and tracking_active:
            pos_2d = data.get('position_2d')
            pos_3d = data.get('position_3d')
            if pos_2d and pos_3d and len(pos_2d) == 2 and len(pos_3d) >= 2:
                # Check if 2D position matches first two components of 3D position
                tolerance = 1e-6
                if (abs(pos_2d[0] - pos_3d[0]) > tolerance or 
                    abs(pos_2d[1] - pos_3d[1]) > tolerance):
                    errors.append("position_2d must match x,y components of position_3d")
        
        return len(errors) == 0, errors
    
    def _validate_field(self, field_name: str, value: Any, rules: Dict[str, Any]) -> List[str]:
        """Validate a single field against its rules."""
        errors = []
        
        # Type validation
        expected_type = rules.get('type')
        if expected_type == 'tuple' and not isinstance(value, (tuple, list)):
            errors.append(f"Field '{field_name}' must be a tuple/list")
            return errors
        elif expected_type == 'dict' and not isinstance(value, dict):
            errors.append(f"Field '{field_name}' must be a dictionary")
            return errors
        elif expected_type == 'list' and not isinstance(value, list):
            errors.append(f"Field '{field_name}' must be a list")
            return errors
        
        # Length validation
        if 'length' in rules and hasattr(value, '__len__'):
            expected_length = rules['length']
            if len(value) != expected_length:
                errors.append(f"Field '{field_name}' must have length {expected_length}")
        
        if 'min_length' in rules and hasattr(value, '__len__'):
            min_length = rules['min_length']
            if len(value) < min_length:
                errors.append(f"Field '{field_name}' must have at least {min_length} elements")
        
        # Range validation
        if 'range' in rules and isinstance(value, (tuple, list)):
            min_val, max_val = rules['range']
            for i, item in enumerate(value):
                if isinstance(item, (int, float)):
                    if item < min_val or item > max_val:
                        errors.append(f"Field '{field_name}[{i}]' value {item} not in range [{min_val}, {max_val}]")
        
        return errors
    
    def check_tracker_compatibility(self, tracker_name: str, schema_type: str) -> bool:
        """
        Check if a tracker supports a specific schema type.
        
        Args:
            tracker_name (str): Name of the tracker
            schema_type (str): Schema type to check
            
        Returns:
            bool: True if compatible, False otherwise
        """
        tracker_info = self.get_tracker_info(tracker_name)
        if not tracker_info:
            return False
        
        supported_schemas = tracker_info.get('supported_schemas', [])
        return schema_type in supported_schemas
    
    def check_follower_compatibility(self, follower_name: str, schema_type: str) -> str:
        """
        Check follower compatibility with a schema type.
        
        Args:
            follower_name (str): Name of the follower
            schema_type (str): Schema type to check
            
        Returns:
            str: 'required', 'preferred', 'optional', or 'incompatible'
        """
        compatibility_info = self.compatibility.get('followers', {}).get(follower_name, {})
        
        if schema_type in compatibility_info.get('required_schemas', []):
            return 'required'
        elif schema_type in compatibility_info.get('preferred_schemas', []):
            return 'preferred'
        elif schema_type in compatibility_info.get('optional_schemas', []):
            return 'optional'
        else:
            return 'incompatible'
    
    def get_available_schemas(self) -> List[str]:
        """Get list of all available schema types."""
        return list(self.schemas.keys())
    
    def get_available_trackers(self) -> List[str]:
        """Get list of all available tracker types."""
        return list(self.tracker_types.keys())
    
    def get_schema_summary(self) -> Dict[str, Any]:
        """Get a summary of all loaded schemas and configurations."""
        return {
            'schemas': len(self.schemas),
            'tracker_types': len(self.tracker_types),
            'loaded': self._loaded,
            'config_path': self.config_path,
            'available_schemas': self.get_available_schemas(),
            'available_trackers': self.get_available_trackers()
        }

# Global schema manager instance
_schema_manager: Optional[SchemaManager] = None

def get_schema_manager() -> SchemaManager:
    """Get or create the global schema manager instance."""
    global _schema_manager
    if _schema_manager is None:
        _schema_manager = SchemaManager()
    return _schema_manager

def validate_tracker_data(data_type: str, data: Dict[str, Any], 
                         tracking_active: bool = True) -> Tuple[bool, List[str]]:
    """
    Convenience function to validate tracker data using the global schema manager.
    
    Args:
        data_type (str): The data type being validated
        data (Dict[str, Any]): The data to validate
        tracking_active (bool): Whether tracking is currently active
        
    Returns:
        Tuple[bool, List[str]]: (is_valid, list_of_errors)
    """
    manager = get_schema_manager()
    return manager.validate_tracker_output(data_type, data, tracking_active)

if __name__ == "__main__":
    # Test the schema manager
    manager = SchemaManager()
    print("Schema Manager Test")
    print("=" * 50)
    print(f"Summary: {manager.get_schema_summary()}")
    print(f"Available schemas: {manager.get_available_schemas()}")
    print(f"Available trackers: {manager.get_available_trackers()}")
    
    # Test validation
    test_data = {
        'position_2d': (0.5, 0.3),
        'confidence': 0.8
    }
    is_valid, errors = manager.validate_tracker_output('POSITION_2D', test_data, True)
    print(f"Validation test: {is_valid}, Errors: {errors}")