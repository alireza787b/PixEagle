# SchemaManager

YAML-driven tracker schema management with validation and compatibility checking.

## Overview

`SchemaManager` (`src/classes/schema_manager.py`) provides:

- Loading tracker schemas from YAML
- Tracker output validation
- Compatibility checking between trackers and followers
- UI metadata for tracker selection

## Class Definition

```python
class SchemaManager:
    """
    Manages tracker schemas loaded from YAML configuration files.
    Provides validation, compatibility checking, and extensibility support.
    """
```

## Schema Configuration

### File Location

```
configs/tracker_schemas.yaml
```

### Schema Structure

```yaml
# configs/tracker_schemas.yaml

tracker_data_types:
  POSITION_2D:
    description: "Basic 2D position tracking"
    required_fields:
      - position_2d
      - confidence
    optional_fields:
      - bbox
      - normalized_bbox
    validation:
      position_2d:
        type: tuple
        length: 2
        range: [0.0, 1.0]
      confidence:
        type: float
        range: [0.0, 1.0]

  POSITION_3D:
    description: "3D position with depth estimation"
    required_fields:
      - position_2d
      - position_3d
      - confidence
    validation:
      position_3d:
        type: tuple
        length: 3

  GIMBAL_ANGLES:
    description: "Gimbal angle output"
    required_fields:
      - gimbal_angles
    validation:
      gimbal_angles:
        type: tuple
        length: 3

tracker_types:
  csrt_tracker:
    name: "CSRT Tracker"
    description: "OpenCV CSRT tracker for visual tracking"
    supported_schemas:
      - POSITION_2D
      - BBOX
    capabilities:
      - real_time
      - gpu_optional
    ui_metadata:
      factory_key: "csrt"
      display_name: "CSRT (Discriminative)"
      icon: "target"
      exclude_from_ui: false

  smart_tracker:
    name: "Smart Tracker"
    description: "YOLO-based intelligent tracking"
    supported_schemas:
      - POSITION_2D
      - BBOX
      - CLASSIFICATION
    ui_metadata:
      factory_key: null
      exclude_from_ui: true
      note: "Automatically used when smart mode enabled"

compatibility:
  followers:
    mc_velocity_follower:
      required_schemas:
        - POSITION_2D
      preferred_schemas:
        - POSITION_3D
      compatible_schemas:
        - BBOX
```

## Key Methods

### Loading Schemas

```python
def load_schemas(self) -> bool:
    """Load schemas from YAML configuration file."""
    with open(self.config_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)

    self.schemas = config.get('tracker_data_types', {})
    self.tracker_types = config.get('tracker_types', {})
    self.compatibility = config.get('compatibility', {})

    return True
```

### Schema Retrieval

```python
def get_schema(self, schema_type: str) -> Optional[Dict[str, Any]]:
    """Get schema configuration for a specific data type."""
    return self.schemas.get(schema_type)

def get_available_schemas(self) -> List[str]:
    """Get list of all available schema types."""
    return list(self.schemas.keys())
```

### Tracker Information

```python
def get_tracker_info(self, tracker_name: str) -> Optional[Dict[str, Any]]:
    """Get information about a specific tracker type."""
    return self.tracker_types.get(tracker_name)

def get_available_trackers(self) -> List[str]:
    """Get list of all available tracker types."""
    return list(self.tracker_types.keys())

def get_available_classic_trackers(self) -> Dict[str, Any]:
    """Get UI-selectable classic trackers (excludes SmartTracker)."""
    classic_trackers = {}

    for tracker_name, tracker_info in self.tracker_types.items():
        ui_metadata = tracker_info.get('ui_metadata', {})

        if not ui_metadata.get('exclude_from_ui', False):
            if ui_metadata.get('factory_key'):
                classic_trackers[tracker_name] = {
                    'name': tracker_info.get('name'),
                    'description': tracker_info.get('description'),
                    'ui_metadata': ui_metadata,
                    'supported_schemas': tracker_info.get('supported_schemas', [])
                }

    return classic_trackers
```

### Validation

```python
def validate_tracker_output(
    self,
    data_type: str,
    data: Dict[str, Any],
    tracking_active: bool = True
) -> Tuple[bool, List[str]]:
    """
    Validate tracker output against schema requirements.

    Args:
        data_type: The data type being validated
        data: The data to validate
        tracking_active: Whether tracking is currently active

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    schema = self.get_schema(data_type)
    if not schema:
        return False, [f"Unknown schema type: {data_type}"]

    errors = []

    # Validate required fields when tracking
    if tracking_active:
        required_fields = schema.get('required_fields', [])
        for field in required_fields:
            if field not in data or data[field] is None:
                errors.append(f"Required field '{field}' is missing")

    # Validate field types and constraints
    validation_rules = schema.get('validation', {})
    for field_name, rules in validation_rules.items():
        if field_name in data and data[field_name] is not None:
            field_errors = self._validate_field(field_name, data[field_name], rules)
            errors.extend(field_errors)

    return len(errors) == 0, errors

def _validate_field(
    self,
    field_name: str,
    value: Any,
    rules: Dict[str, Any]
) -> List[str]:
    """Validate a single field against its rules."""
    errors = []

    # Type validation
    expected_type = rules.get('type')
    if expected_type == 'tuple' and not isinstance(value, (tuple, list)):
        errors.append(f"Field '{field_name}' must be a tuple/list")

    # Length validation
    if 'length' in rules and hasattr(value, '__len__'):
        if len(value) != rules['length']:
            errors.append(f"Field '{field_name}' must have length {rules['length']}")

    # Range validation
    if 'range' in rules and isinstance(value, (tuple, list)):
        min_val, max_val = rules['range']
        for i, item in enumerate(value):
            if isinstance(item, (int, float)):
                if item < min_val or item > max_val:
                    errors.append(
                        f"Field '{field_name}[{i}]' value {item} "
                        f"not in range [{min_val}, {max_val}]"
                    )

    return errors
```

### Compatibility Checking

```python
def check_tracker_compatibility(
    self,
    tracker_name: str,
    schema_type: str
) -> bool:
    """Check if a tracker supports a specific schema type."""
    tracker_info = self.get_tracker_info(tracker_name)
    if not tracker_info:
        return False

    supported_schemas = tracker_info.get('supported_schemas', [])
    return schema_type in supported_schemas

def check_follower_compatibility(
    self,
    follower_name: str,
    schema_type: str
) -> str:
    """
    Check follower compatibility with a schema type.

    Returns:
        'required', 'preferred', 'optional', 'compatible', or 'incompatible'
    """
    compatibility_info = self.compatibility.get('followers', {}).get(follower_name, {})

    if schema_type in compatibility_info.get('required_schemas', []):
        return 'required'
    elif schema_type in compatibility_info.get('preferred_schemas', []):
        return 'preferred'
    elif schema_type in compatibility_info.get('compatible_schemas', []):
        return 'compatible'
    elif schema_type in compatibility_info.get('optional_schemas', []):
        return 'optional'
    else:
        return 'incompatible'
```

### UI Validation

```python
def validate_tracker_for_ui(
    self,
    tracker_name: str
) -> Tuple[bool, str]:
    """
    Validate if a tracker can be used via UI selection.

    Returns:
        Tuple of (is_valid, error_message)
    """
    tracker_info = self.get_tracker_info(tracker_name)

    if not tracker_info:
        return False, f"Unknown tracker: {tracker_name}"

    ui_metadata = tracker_info.get('ui_metadata', {})

    if ui_metadata.get('exclude_from_ui', False):
        return False, ui_metadata.get('note', 'Not selectable via UI')

    if not ui_metadata.get('factory_key'):
        return False, "Tracker has no factory key"

    return True, ""
```

## Global Instance

```python
_schema_manager: Optional[SchemaManager] = None

def get_schema_manager() -> SchemaManager:
    """Get or create the global schema manager instance."""
    global _schema_manager
    if _schema_manager is None:
        _schema_manager = SchemaManager()
    return _schema_manager
```

## Convenience Function

```python
def validate_tracker_data(
    data_type: str,
    data: Dict[str, Any],
    tracking_active: bool = True
) -> Tuple[bool, List[str]]:
    """Validate tracker data using the global schema manager."""
    manager = get_schema_manager()
    return manager.validate_tracker_output(data_type, data, tracking_active)
```

## Usage Example

```python
from classes.schema_manager import get_schema_manager, validate_tracker_data

# Get manager
manager = get_schema_manager()

# Get available trackers for UI
trackers = manager.get_available_classic_trackers()
for name, info in trackers.items():
    print(f"{info['ui_metadata']['display_name']}: {info['description']}")

# Validate tracker output
data = {
    'position_2d': (0.5, 0.3),
    'confidence': 0.85
}
is_valid, errors = validate_tracker_data('POSITION_2D', data)

# Check compatibility
compat = manager.check_follower_compatibility(
    'mc_velocity_follower',
    'POSITION_2D'
)
print(f"Compatibility: {compat}")  # 'required'
```

## Related Components

- [TrackerOutput](../../trackers/02-components/tracker-output.md) - Uses schema validation
- [TrackerFactory](../../trackers/02-components/tracker-factory.md) - Uses factory keys
- [FastAPIHandler](fastapi-handler.md) - Exposes schema endpoints
