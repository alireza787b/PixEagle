#!/usr/bin/env python3
"""
Schema Generation Tool for PixEagle Configuration
==================================================

Parses config_default.yaml and generates config_schema.yaml with:
- Type inference from values
- Description extraction from comments
- Constraint inference (min/max for numbers, options for enums)
- Grouping by category
- reboot_required flag placeholder

Usage:
    python scripts/generate_schema.py

Output:
    configs/config_schema.yaml
"""

import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime


# Define categories for sections
SECTION_CATEGORIES = {
    # Video & Input
    'VideoSource': {'category': 'video', 'display_name': 'Video Source', 'icon': 'videocam'},
    'USBCamera': {'category': 'video', 'display_name': 'USB Camera', 'icon': 'usb'},
    'CSICamera': {'category': 'video', 'display_name': 'CSI Camera', 'icon': 'camera'},

    # Network
    'PX4': {'category': 'network', 'display_name': 'PX4 Connection', 'icon': 'flight'},
    'MAVLink': {'category': 'network', 'display_name': 'MAVLink Telemetry', 'icon': 'router'},
    'Streaming': {'category': 'network', 'display_name': 'Video Streaming', 'icon': 'stream'},
    'GStreamer': {'category': 'network', 'display_name': 'GStreamer Output', 'icon': 'play_circle'},
    'GStreamerPipelines': {'category': 'network', 'display_name': 'GStreamer Pipelines', 'icon': 'code'},
    'Telemetry': {'category': 'network', 'display_name': 'Telemetry', 'icon': 'analytics'},

    # Tracking
    'Tracking': {'category': 'tracking', 'display_name': 'Tracking Settings', 'icon': 'gps_fixed'},
    'TrackerSafety': {'category': 'tracking', 'display_name': 'Tracker Safety', 'icon': 'security'},
    'CSRT_Tracker': {'category': 'tracking', 'display_name': 'CSRT Tracker', 'icon': 'track_changes'},
    'KCF_Tracker': {'category': 'tracking', 'display_name': 'KCF Tracker', 'icon': 'track_changes'},
    'DLIB_Tracker': {'category': 'tracking', 'display_name': 'dlib Tracker', 'icon': 'track_changes'},
    'SmartTracker': {'category': 'tracking', 'display_name': 'Smart Tracker (YOLO)', 'icon': 'smart_toy'},
    'GimbalTracker': {'category': 'tracking', 'display_name': 'Gimbal Tracker', 'icon': 'control_camera'},
    'GimbalTrackerSettings': {'category': 'tracking', 'display_name': 'Gimbal Tracker Settings', 'icon': 'settings'},

    # Detection
    'Detector': {'category': 'detection', 'display_name': 'Object Detector', 'icon': 'search'},

    # Followers
    'Follower': {'category': 'follower', 'display_name': 'Follower Settings', 'icon': 'navigation'},
    'MC_VELOCITY_CHASE': {'category': 'follower', 'display_name': 'MC Velocity Chase', 'icon': 'sports_motorsports'},
    'MC_VELOCITY_POSITION': {'category': 'follower', 'display_name': 'MC Velocity Position', 'icon': 'place'},
    'MC_VELOCITY_DISTANCE': {'category': 'follower', 'display_name': 'MC Velocity Distance', 'icon': 'straighten'},
    'MC_VELOCITY_GROUND': {'category': 'follower', 'display_name': 'MC Velocity Ground', 'icon': 'terrain'},
    'MC_VELOCITY': {'category': 'follower', 'display_name': 'MC Velocity', 'icon': 'speed'},
    'MC_ATTITUDE_RATE': {'category': 'follower', 'display_name': 'MC Attitude Rate', 'icon': 'rotate_right'},
    'GM_PID_PURSUIT': {'category': 'follower', 'display_name': 'Gimbal PID Pursuit', 'icon': 'control_camera'},
    'GM_VELOCITY_VECTOR': {'category': 'follower', 'display_name': 'Gimbal Velocity Vector', 'icon': 'control_camera'},
    'FW_ATTITUDE_RATE': {'category': 'follower', 'display_name': 'Fixed-Wing Attitude Rate', 'icon': 'flight'},

    # Safety & Control
    'Safety': {'category': 'safety', 'display_name': 'Safety Limits', 'icon': 'shield'},
    'PID': {'category': 'control', 'display_name': 'PID Controller', 'icon': 'tune'},
    'GainScheduling': {'category': 'control', 'display_name': 'Gain Scheduling', 'icon': 'timeline'},
    'ChaseFollower': {'category': 'control', 'display_name': 'Chase Follower Limits', 'icon': 'speed'},
    'YawControl': {'category': 'control', 'display_name': 'Yaw Control', 'icon': 'rotate_right'},
    'AdaptiveControl': {'category': 'control', 'display_name': 'Adaptive Control', 'icon': 'auto_fix_high'},
    'Gimbal': {'category': 'control', 'display_name': 'Gimbal Control', 'icon': 'control_camera'},

    # Processing
    'FrameEstimation': {'category': 'processing', 'display_name': 'Frame Display', 'icon': 'picture_in_picture'},
    'Estimator': {'category': 'processing', 'display_name': 'State Estimator', 'icon': 'insights'},
    'FramePreprocessor': {'category': 'processing', 'display_name': 'Frame Preprocessor', 'icon': 'auto_fix_high'},
    'Segmentation': {'category': 'processing', 'display_name': 'Segmentation', 'icon': 'crop'},
    'VerticalErrorRecalculation': {'category': 'processing', 'display_name': 'Vertical Error', 'icon': 'height'},
    'Setpoint': {'category': 'processing', 'display_name': 'Setpoint Config', 'icon': 'my_location'},

    # Display
    'OSD': {'category': 'display', 'display_name': 'On-Screen Display', 'icon': 'tv'},
    'Debugging': {'category': 'display', 'display_name': 'Debugging', 'icon': 'bug_report'},
}

# Category definitions
CATEGORIES = {
    'video': {'display_name': 'Video Input', 'icon': 'videocam', 'order': 1},
    'network': {'display_name': 'Network & Streaming', 'icon': 'router', 'order': 2},
    'tracking': {'display_name': 'Tracking', 'icon': 'gps_fixed', 'order': 3},
    'detection': {'display_name': 'Detection', 'icon': 'search', 'order': 4},
    'follower': {'display_name': 'Followers', 'icon': 'navigation', 'order': 5},
    'safety': {'display_name': 'Safety', 'icon': 'shield', 'order': 6},
    'control': {'display_name': 'Control', 'icon': 'tune', 'order': 7},
    'processing': {'display_name': 'Processing', 'icon': 'auto_fix_high', 'order': 8},
    'display': {'display_name': 'Display & Debug', 'icon': 'tv', 'order': 9},
}

# Parameters that require app restart
REBOOT_REQUIRED_PATTERNS = [
    r'^VIDEO_SOURCE',
    r'^CAPTURE_',
    r'^RTSP_',
    r'^UDP_',
    r'^HTTP_',
    r'^CSI_',
    r'^CAMERA_',
    r'^USE_GSTREAMER',
    r'^SYSTEM_ADDRESS',
    r'^MAVLINK_HOST',
    r'^MAVLINK_PORT',
    r'^HTTP_STREAM_HOST',
    r'^HTTP_STREAM_PORT',
    r'^SMART_TRACKER_.*MODEL',
    r'^SMART_TRACKER_USE_GPU',
]


def infer_type(value: Any) -> Tuple[str, Dict]:
    """Infer parameter type and constraints from value."""
    constraints = {}

    if isinstance(value, bool):
        return 'boolean', constraints
    elif isinstance(value, int):
        # Determine reasonable constraints
        if value >= 0:
            constraints['min'] = 0
        if value <= 100 and value >= 0:
            constraints['max'] = 100
        elif value <= 1000:
            constraints['max'] = 10000
        else:
            constraints['max'] = 1000000
        return 'integer', constraints
    elif isinstance(value, float):
        if 0 <= value <= 1:
            constraints['min'] = 0.0
            constraints['max'] = 1.0
            constraints['step'] = 0.01
        elif 0 <= value <= 100:
            constraints['min'] = 0.0
            constraints['max'] = 100.0
            constraints['step'] = 0.1
        else:
            constraints['min'] = -10000.0
            constraints['max'] = 10000.0
            constraints['step'] = 0.1
        return 'float', constraints
    elif isinstance(value, str):
        return 'string', constraints
    elif isinstance(value, list):
        if value and all(isinstance(x, (int, float)) for x in value):
            constraints['item_type'] = 'number'
            constraints['min_items'] = 0
            constraints['max_items'] = 20
        elif value and all(isinstance(x, str) for x in value):
            constraints['item_type'] = 'string'
        return 'array', constraints
    elif isinstance(value, dict):
        return 'object', constraints
    elif value is None:
        return 'string', {'nullable': True}

    return 'any', constraints


def is_reboot_required(param_name: str) -> bool:
    """Check if parameter requires app restart to take effect."""
    for pattern in REBOOT_REQUIRED_PATTERNS:
        if re.match(pattern, param_name, re.IGNORECASE):
            return True
    return False


def extract_unit(description: str) -> Optional[str]:
    """Extract unit from description if present."""
    unit_patterns = [
        (r'\(([^)]+)\)\s*$', 1),  # (m/s) at end
        (r'\b(m/s|m|ms|px|pixels|fps|Hz|degrees|deg|deg/s|rad|rad/s|seconds|sec|s|%)\b', 1),
    ]

    for pattern, group in unit_patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            unit = match.group(group).lower()
            # Normalize units
            unit_map = {
                'pixels': 'px',
                'degrees': 'deg',
                'seconds': 's',
                'sec': 's',
                'milliseconds': 'ms',
            }
            return unit_map.get(unit, unit)
    return None


def parse_config_with_comments(config_path: str) -> Tuple[Dict, Dict[str, str]]:
    """Parse config file and extract comments for descriptions."""
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse YAML
    config = yaml.safe_load(content)

    # Extract comments (line before each key)
    comments = {}
    lines = content.split('\n')

    for i, line in enumerate(lines):
        # Find key definitions
        key_match = re.match(r'^(\s*)(\w+):\s*(.*)$', line)
        if key_match:
            indent, key, value_part = key_match.groups()

            # Look for comment on same line
            inline_comment = ''
            if '#' in value_part:
                _, inline_comment = value_part.split('#', 1)
                inline_comment = inline_comment.strip()

            # Look for comment on previous lines
            prev_comments = []
            for j in range(i - 1, max(0, i - 5), -1):
                prev_line = lines[j].strip()
                if prev_line.startswith('#') and not prev_line.startswith('# ==='):
                    comment = prev_line.lstrip('#').strip()
                    if comment and not comment.startswith('='):
                        prev_comments.insert(0, comment)
                elif prev_line:
                    break

            # Combine comments
            description = inline_comment if inline_comment else ' '.join(prev_comments)
            if description:
                comments[key] = description

    return config, comments


def generate_parameter_schema(key: str, value: Any, description: str = '') -> Dict:
    """Generate schema entry for a parameter."""
    param_type, constraints = infer_type(value)

    schema = {
        'type': param_type,
        'default': value,
        'description': description or f'{key} parameter',
        'reboot_required': is_reboot_required(key),
    }

    # Add constraints
    schema.update(constraints)

    # Extract unit from description
    unit = extract_unit(description)
    if unit:
        schema['unit'] = unit

    return schema


def process_section(section_name: str, section_data: Any, comments: Dict[str, str]) -> Dict:
    """Process a config section into schema format."""
    if not isinstance(section_data, dict):
        # Simple value at section level
        return generate_parameter_schema(section_name, section_data, comments.get(section_name, ''))

    # Get section metadata
    section_meta = SECTION_CATEGORIES.get(section_name, {
        'category': 'other',
        'display_name': section_name.replace('_', ' ').title(),
        'icon': 'settings'
    })

    section_schema = {
        'display_name': section_meta['display_name'],
        'category': section_meta['category'],
        'icon': section_meta.get('icon', 'settings'),
        'parameters': {}
    }

    def process_params(data: Dict, prefix: str = '') -> Dict:
        """Recursively process parameters."""
        params = {}
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            desc = comments.get(key, '')

            if isinstance(value, dict) and not any(isinstance(v, dict) for v in value.values()):
                # Simple nested dict (like PID_GAINS entries)
                params[key] = generate_parameter_schema(key, value, desc)
            elif isinstance(value, dict):
                # Complex nested structure - keep as object
                params[key] = {
                    'type': 'object',
                    'description': desc or f'{key} settings',
                    'reboot_required': False,
                    'properties': process_params(value, full_key)
                }
            else:
                params[key] = generate_parameter_schema(key, value, desc)

        return params

    section_schema['parameters'] = process_params(section_data)

    return section_schema


def generate_schema(config_path: str, output_path: str):
    """Generate schema file from config."""
    print(f"Reading config from: {config_path}")

    config, comments = parse_config_with_comments(config_path)

    schema = {
        'schema_version': '1.0.0',
        'meta': {
            'project': 'PixEagle',
            'generated_from': str(config_path),
            'generated_at': datetime.now().isoformat(),
            'description': 'Auto-generated schema for PixEagle configuration'
        },
        'categories': CATEGORIES,
        'sections': {}
    }

    # Process each section
    for section_name, section_data in config.items():
        if section_data is None:
            continue

        print(f"  Processing section: {section_name}")
        schema['sections'][section_name] = process_section(section_name, section_data, comments)

    # Write schema
    print(f"\nWriting schema to: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(schema, f, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)

    # Count stats
    total_params = 0
    for section in schema['sections'].values():
        if 'parameters' in section:
            total_params += len(section['parameters'])

    print(f"\n✅ Schema generated successfully!")
    print(f"   Sections: {len(schema['sections'])}")
    print(f"   Parameters: {total_params}")
    print(f"   Categories: {len(CATEGORIES)}")


if __name__ == '__main__':
    import sys

    # Determine paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    config_path = project_root / 'configs' / 'config_default.yaml'
    output_path = project_root / 'configs' / 'config_schema.yaml'

    # Allow overriding paths via arguments
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_path = Path(sys.argv[2])

    generate_schema(str(config_path), str(output_path))
