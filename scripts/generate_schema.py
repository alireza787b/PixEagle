#!/usr/bin/env python3
"""
Schema Generation Tool for PixEagle Configuration
==================================================

Parses config_default.yaml and generates config_schema.yaml with:
- Type inference from values
- Description extraction from comments
- Constraint inference (min/max for numbers, options for enums)
- Grouping by category
- reboot_required flag from pattern matching
- Dropdown options from comment patterns (Options:, Allowed:, or-separated, pipe-separated)
- Recommended ranges (soft validation limits) from RECOMMENDED_RANGES dict
- Manual overrides from SCHEMA_OVERRIDES dict (highest priority)

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
    'ClassicTracker_Common': {'category': 'tracking', 'display_name': 'Classic Tracker Common', 'icon': 'tune'},
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

# Manual schema overrides for parameters where comment parsing is ambiguous.
# Applied AFTER auto-generation. Keys are "SectionName.PARAM_NAME".
SCHEMA_OVERRIDES = {
    'VideoSource.FRAME_ROTATION_DEG': {
        'options': [
            {'value': 0, 'label': '0\u00b0'},
            {'value': 90, 'label': '90\u00b0'},
            {'value': 180, 'label': '180\u00b0'},
            {'value': 270, 'label': '270\u00b0'},
        ],
        'min': 0, 'max': 270, 'unit': 'deg',
        'description': 'Frame rotation angle (must match cv2.rotate preset)',
    },
    'VideoSource.FRAME_FLIP_MODE': {
        'options': [
            {'value': 'none', 'label': 'None'},
            {'value': 'horizontal', 'label': 'Horizontal'},
            {'value': 'vertical', 'label': 'Vertical'},
            {'value': 'both', 'label': 'Both'},
        ],
        'description': 'Frame flip mode applied after rotation',
    },
    'SmartTracker.TRACKER_TYPE': {
        'options': [
            {'value': 'bytetrack', 'label': 'ByteTrack',
             'description': 'Fast, no ReID, geometric matching only'},
            {'value': 'botsort', 'label': 'BoT-SORT',
             'description': 'Better persistence, no ReID'},
            {'value': 'botsort_reid', 'label': 'BoT-SORT + ReID',
             'description': 'Ultralytics native ReID (recommended for GPU)'},
            {'value': 'custom_reid', 'label': 'Custom ReID',
             'description': 'Lightweight histogram/HOG ReID (recommended for CPU/offline)'},
        ],
        'description': 'Tracking algorithm selection',
    },
    'SmartTracker.SMART_TRACKER_HUD_STYLE': {
        'options': [
            {'value': 'military', 'label': 'Military',
             'description': 'Modern military-grade HUD style'},
            {'value': 'classic', 'label': 'Classic',
             'description': 'Legacy HUD style'},
        ],
        'description': 'HUD rendering style for Smart Tracker overlay',
    },
}

# Recommended ranges for parameters (soft limits that trigger warnings, not errors).
# Keys are "SectionName.PARAM_NAME".
RECOMMENDED_RANGES = {
    'SmartTracker.SMART_TRACKER_CONFIDENCE_THRESHOLD': {'recommended_min': 0.15, 'recommended_max': 0.7},
    'SmartTracker.SMART_TRACKER_IOU_THRESHOLD': {'recommended_min': 0.2, 'recommended_max': 0.6},
    'SmartTracker.SMART_TRACKER_LABEL_PLATE_OPACITY': {'recommended_min': 0.4, 'recommended_max': 0.9},
    'Streaming.JPEG_QUALITY': {'recommended_min': 50, 'recommended_max': 95},
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
        # Determine reasonable constraints based on default value
        if value >= 0:
            constraints['min'] = 0
        # Smarter max inference: avoid blanket max=100 for small defaults
        if value <= 1:
            # Default 0 or 1 — we can't infer intent, use generous range
            constraints['max'] = 10000
        elif value <= 10:
            constraints['max'] = max(value * 20, 100)
        elif value <= 100:
            constraints['max'] = max(value * 5, 1000)
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


def extract_options(description: str) -> Tuple[Optional[List[Dict]], str]:
    """Extract options from various patterns in description.

    Supported patterns:
    - "Options: val1, val2, val3" - comma separated
    - "Options: val1 | val2 | val3" - pipe separated
    - "Allowed: val1, val2, val3" - "Allowed:" prefix (same as Options:)
    - "Options: val1 (description), val2 (fast)" - with parenthetical descriptions
    - "val1 or val2 or val3" - or-separated values
    - '"val1" (desc) or "val2" (desc)' - quoted with or-separator
    - "val1, val2, val3" - trailing comma-separated values (implicit options)
    - '"val1", "val2"' - quoted values

    Returns:
        Tuple of (options_list, cleaned_description)
        options_list: List of {'value': str, 'label': str} or None
        cleaned_description: Description with Options line removed
    """
    if not description:
        return None, description

    options = []
    cleaned = description

    # Unified prefix pattern: recognize both "Options:" and "Allowed:" identically
    PREFIX = r'(?:Options|Allowed)'

    # Pattern 1: "Options:/Allowed: ..." with pipe separator
    pipe_match = re.search(PREFIX + r':\s*([^#\n]+\|[^#\n]+)', description, re.IGNORECASE)
    if pipe_match:
        options_str = pipe_match.group(1).strip()
        for opt in options_str.split('|'):
            opt = opt.strip().strip('"\'')
            if opt and re.match(r'^[a-zA-Z0-9_]+$', opt):
                options.append({'value': opt, 'label': opt})
        if options:
            # Clean the Options:/Allowed: ... part from description
            cleaned = re.sub(r'\s*(?:Options|Allowed):\s*[^#\n]+\|[^#\n]+', '', description, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if not cleaned or cleaned in [':', '.', '-']:
                cleaned = ''
            return options, cleaned

    # Pattern 1b: Bare pipe-separated options without "Options:" prefix
    # e.g., "sideslip | coordinated_turn"
    bare_pipe_match = re.fullmatch(
        r'["\']?[A-Za-z0-9_]+["\']?(?:\s*\|\s*["\']?[A-Za-z0-9_]+["\']?)+',
        description.strip()
    )
    if bare_pipe_match:
        options_str = bare_pipe_match.group(0).strip()
        for opt in options_str.split('|'):
            opt = opt.strip().strip('"\'')
            if opt and re.match(r'^[a-zA-Z0-9_]+$', opt):
                options.append({'value': opt, 'label': opt})
        if options:
            return options, ''

    # Pattern 2: "Options:/Allowed: val1 (desc), val2 (desc), ..." with parenthetical descriptions
    # Capture everything after prefix that may include parens
    paren_match = re.search(PREFIX + r':\s*([A-Za-z0-9_]+\s*\([^)]+\)(?:\s*,\s*[A-Za-z0-9_]+(?:\s*\([^)]*\))?)+)', description, re.IGNORECASE)
    if paren_match:
        options_str = paren_match.group(1).strip()
        # Extract option names and optional parenthetical descriptions.
        for opt_match in re.finditer(r'([A-Za-z0-9_]+)(?:\s*\(([^)]*)\))?', options_str):
            opt = opt_match.group(1).strip()
            opt_desc = opt_match.group(2).strip() if opt_match.group(2) else None
            if opt:
                opt_entry = {'value': opt, 'label': opt}
                if opt_desc:
                    opt_entry['description'] = opt_desc
                options.append(opt_entry)
        if options:
            cleaned = re.sub(r'\s*(?:Options|Allowed):\s*[A-Za-z0-9_]+\s*\([^)]+\)(?:\s*,\s*[A-Za-z0-9_]+(?:\s*\([^)]*\))?)+', '', description, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if not cleaned or cleaned in [':', '.', '-']:
                cleaned = ''
            return options, cleaned

    # Pattern 3: "Options:/Allowed: val1, val2, val3" simple comma separated
    # Also handle quoted values like "HORIZONTAL", "VERTICAL" and numeric values like 0, 90, 180
    simple_match = re.search(PREFIX + r':\s*(["\']?[A-Za-z0-9_]+["\']?(?:\s*,\s*["\']?[A-Za-z0-9_]+["\']?)+)', description, re.IGNORECASE)
    if simple_match:
        options_str = simple_match.group(1).strip()
        for opt in options_str.split(','):
            opt = opt.strip().strip('"\'')
            if opt and re.match(r'^[a-zA-Z0-9_]+$', opt):
                options.append({'value': opt, 'label': opt})
        if options:
            cleaned = re.sub(r'\s*(?:Options|Allowed):\s*["\']?[A-Za-z0-9_]+["\']?(?:\s*,\s*["\']?[A-Za-z0-9_]+["\']?)+', '', description, flags=re.IGNORECASE)
            # Also clean up Deprecated patterns
            cleaned = re.sub(r'\s*Deprecated\s*\([^)]*\)\s*:\s*[a-zA-Z0-9_,\s]+', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if not cleaned or cleaned in [':', '.', '-']:
                cleaned = ''
            return options, cleaned

    # Pattern 3b: "or"-separated values (e.g., "MANUAL or AUTO", "center or top or bottom")
    # Also handles: "val1" (desc) or "val2" (desc)
    or_match = re.findall(r'["\']?([A-Za-z0-9_]+)["\']?(?:\s*\([^)]*\))?\s+or\s+', description, re.IGNORECASE)
    if or_match:
        # Get all values including the last one after the final "or"
        # Re-parse to get all values correctly
        or_parts = re.split(r'\s+or\s+', description.strip(), flags=re.IGNORECASE)
        or_options = []
        for part in or_parts:
            # Extract the value: strip quotes and parenthetical descriptions
            val_match = re.match(r'["\']?([A-Za-z0-9_]+)["\']?', part.strip())
            if val_match:
                opt = val_match.group(1)
                if opt and re.match(r'^[a-zA-Z0-9_]+$', opt):
                    or_options.append({'value': opt, 'label': opt})
        if len(or_options) >= 2:
            return or_options, ''

    # Pattern 4: Trailing comma-separated uppercase values (implicit options, no "Options:" prefix)
    # e.g., "# DEBUG, INFO, WARNING, ERROR" at end of description
    trailing_match = re.search(r'([A-Z][A-Z0-9_]*(?:\s*,\s*[A-Z][A-Z0-9_]*){2,})\s*$', description)
    if trailing_match:
        options_str = trailing_match.group(1).strip()
        for opt in options_str.split(','):
            opt = opt.strip()
            if opt and re.match(r'^[A-Z][A-Z0-9_]*$', opt):
                options.append({'value': opt, 'label': opt})
        if options:
            cleaned = description[:trailing_match.start()].strip()
            if not cleaned or cleaned in [':', '.', '-']:
                cleaned = ''
            return options, cleaned

    # Pattern 5: Quoted values followed by dash-descriptions
    # e.g., "fast" - description "balanced" - description "quality" - description
    # Common in performance mode configs
    quoted_matches = re.findall(r'"([a-zA-Z0-9_]+)"\s*-\s*', description)
    if len(quoted_matches) >= 2:  # At least 2 options to be considered a valid option set
        for opt in quoted_matches:
            if opt and re.match(r'^[a-zA-Z0-9_]+$', opt):
                options.append({'value': opt, 'label': opt})
        if options:
            # Keep description but note options are extracted
            return options, description

    return None, description


def parse_config_with_comments(config_path: str) -> Tuple[Dict, Dict[str, str]]:
    """Parse config file and extract comments for descriptions.

    Extracts comments from:
    - Inline comments (same line as key)
    - Previous lines (up to 5 lines before)
    - Following lines (up to 3 lines after, for Options: patterns)
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse YAML
    config = yaml.safe_load(content)

    # Extract comments keyed by full YAML path (e.g., "MC_VELOCITY.LATERAL_GUIDANCE_MODE")
    # to avoid collisions when repeated key names appear in different sections.
    comments = {}
    lines = content.split('\n')
    path_stack: List[Tuple[int, str]] = []

    for i, line in enumerate(lines):
        # Find key definitions
        key_match = re.match(r'^(\s*)(\w+):\s*(.*)$', line)
        if key_match:
            indent, key, value_part = key_match.groups()
            indent_len = len(indent)

            # Maintain parent key stack based on indentation level
            while path_stack and path_stack[-1][0] >= indent_len:
                path_stack.pop()

            full_path = '.'.join([k for _, k in path_stack] + [key])

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

            # Look for Options: on following lines (up to 8 lines)
            # Extended range to capture TRACKER_TYPE's "Options:" which is 5+ lines after the key
            following_options = ''
            for j in range(i + 1, min(len(lines), i + 9)):
                follow_line = lines[j].strip()
                # Stop if we hit another key definition or non-comment line
                if re.match(r'^(\s*)\w+:\s*', lines[j]):
                    break
                if follow_line.startswith('#'):
                    follow_comment = follow_line.lstrip('#').strip()
                    # Look for Options: pattern
                    if 'Options:' in follow_comment or 'options:' in follow_comment:
                        following_options = follow_comment
                        break
                elif follow_line and not follow_line.startswith('#'):
                    break

            # Combine comments: inline + following options, or prev_comments
            if inline_comment:
                description = inline_comment
                if following_options:
                    description += ' ' + following_options
            else:
                description = ' '.join(prev_comments)
                if following_options:
                    description += ' ' + following_options

            if description:
                comments[full_path] = description

            # Track current key as a potential parent for nested keys
            path_stack.append((indent_len, key))

    return config, comments


def generate_parameter_schema(key: str, value: Any, description: str = '',
                               full_path: str = '') -> Dict:
    """Generate schema entry for a parameter.

    Args:
        key: Parameter name (e.g., 'FRAME_ROTATION_DEG')
        value: Default value from config
        description: Extracted description from comments
        full_path: Full dotted path (e.g., 'VideoSource.FRAME_ROTATION_DEG') for override lookup
    """
    param_type, constraints = infer_type(value)

    # Extract options from description (e.g., "Options: val1, val2, val3")
    options, cleaned_description = extract_options(description)

    schema = {
        'type': param_type,
        'default': value,
        'description': cleaned_description or f'{key} parameter',
        'reboot_required': is_reboot_required(key),
    }

    # Add constraints
    schema.update(constraints)

    # Add options if found (for dropdown display)
    if options:
        schema['options'] = options
        # For integer options, derive min/max from option values
        if param_type == 'integer' and all(
            isinstance(o.get('value'), (int, str)) and str(o['value']).isdigit()
            for o in options
        ):
            int_vals = [int(o['value']) for o in options]
            schema['min'] = min(int_vals)
            schema['max'] = max(int_vals)

    # Extract unit from description
    unit = extract_unit(cleaned_description)
    if unit:
        schema['unit'] = unit

    # Apply recommended ranges if defined
    lookup_key = full_path or key
    if lookup_key in RECOMMENDED_RANGES:
        schema.update(RECOMMENDED_RANGES[lookup_key])

    # Apply manual overrides (highest priority — overwrites auto-generated values)
    if lookup_key in SCHEMA_OVERRIDES:
        schema.update(SCHEMA_OVERRIDES[lookup_key])

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
            desc = comments.get(full_key, comments.get(key, ''))

            if isinstance(value, dict) and not any(isinstance(v, dict) for v in value.values()):
                # Simple nested dict (like PID_GAINS entries)
                params[key] = generate_parameter_schema(key, value, desc,
                                                         full_path=full_key)
            elif isinstance(value, dict):
                # Complex nested structure - keep as object
                params[key] = {
                    'type': 'object',
                    'description': desc or f'{key} settings',
                    'reboot_required': False,
                    'properties': process_params(value, full_key)
                }
            else:
                params[key] = generate_parameter_schema(key, value, desc,
                                                         full_path=full_key)

        return params

    section_schema['parameters'] = process_params(section_data, section_name)

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

    print(f"\nSchema generated successfully!")
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
