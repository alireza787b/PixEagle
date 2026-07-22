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
    python3 scripts/generate_schema.py

Output:
    configs/config_schema.yaml
"""

import copy
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from ruamel.yaml import YAML as RuamelYAML
from ruamel.yaml.comments import CommentedMap as RuamelCommentedMap


CONFIG_SCHEMA_VERSION = '1.6.0'


# Define categories for sections
SECTION_CATEGORIES = {
    # Video & Input
    'VideoSource': {'category': 'video', 'display_name': 'Video Source', 'icon': 'videocam'},
    'USBCamera': {'category': 'video', 'display_name': 'USB Camera', 'icon': 'usb'},
    'CSICamera': {'category': 'video', 'display_name': 'CSI Camera', 'icon': 'camera'},

    # Recording
    'Recording': {'category': 'video', 'display_name': 'Video Recording', 'icon': 'fiber_manual_record'},

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
    'Follower': {'category': 'follower', 'display_name': 'Follower Config', 'icon': 'flight_takeoff'},
    'MC_VELOCITY_CHASE': {'category': 'follower', 'display_name': 'MC Velocity Chase', 'icon': 'sports_motorsports'},
    'MC_VELOCITY_POSITION': {'category': 'follower', 'display_name': 'MC Velocity Position', 'icon': 'place'},
    'MC_VELOCITY_DISTANCE': {'category': 'follower', 'display_name': 'MC Velocity Distance', 'icon': 'straighten'},
    'MC_VELOCITY_GROUND': {'category': 'follower', 'display_name': 'MC Velocity Ground', 'icon': 'terrain'},
    'MC_ATTITUDE_RATE': {'category': 'follower', 'display_name': 'MC Attitude Rate', 'icon': 'rotate_right'},
    'GM_VELOCITY_CHASE': {'category': 'follower', 'display_name': 'Gimbal Velocity Chase', 'icon': 'control_camera'},
    'GM_VELOCITY_VECTOR': {'category': 'follower', 'display_name': 'Gimbal Velocity Vector', 'icon': 'control_camera'},
    'FW_ATTITUDE_RATE': {'category': 'follower', 'display_name': 'Fixed-Wing Attitude Rate', 'icon': 'flight'},

    # Safety & Control
    'Safety': {'category': 'safety', 'display_name': 'Safety Limits', 'icon': 'shield'},
    'PID': {'category': 'control', 'display_name': 'PID Controller', 'icon': 'tune'},

    # Processing
    'FrameEstimation': {'category': 'processing', 'display_name': 'Frame Display', 'icon': 'picture_in_picture'},
    'Estimator': {'category': 'processing', 'display_name': 'State Estimator', 'icon': 'insights'},
    'FramePreprocessor': {'category': 'processing', 'display_name': 'Frame Preprocessor', 'icon': 'auto_fix_high'},
    'Segmentation': {'category': 'processing', 'display_name': 'Segmentation', 'icon': 'crop'},
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


def load_segmentation_schema_options() -> List[Dict[str, str]]:
    """Build UI options from the canonical implemented-model catalog."""
    catalog_path = (
        Path(__file__).resolve().parents[1]
        / 'configs'
        / 'segmentation_models.yaml'
    )
    loaded = yaml.safe_load(catalog_path.read_text(encoding='utf-8')) or {}
    models = loaded.get('models')
    if not isinstance(models, dict) or 'disabled' not in models:
        raise ValueError('segmentation_models.yaml must define models.disabled')

    options = []
    for value, metadata in models.items():
        if not isinstance(value, str) or not isinstance(metadata, dict):
            raise ValueError('segmentation model entries must be named objects')
        label = metadata.get('label')
        description = metadata.get('description')
        if not isinstance(label, str) or not isinstance(description, str):
            raise ValueError(
                f'segmentation model {value!r} requires label and description'
            )
        options.append({
            'value': value,
            'label': label,
            'description': description,
        })
    return options

# Manual schema overrides for parameters where comment parsing is ambiguous.
# Applied AFTER auto-generation. Keys are "SectionName.PARAM_NAME".
SCHEMA_OVERRIDES = {
    'FOLLOWER_CIRCUIT_BREAKER': {
        'reload_tier': 'immediate',
        'reboot_required': False,
        'description': (
            'PX4 command-dispatch inhibit: true blocks Following startup and '
            'PX4 dispatch; false permits the reviewed command path'
        ),
    },
    'Debugging.ENABLE_MANAGED_SIH': {
        'reload_tier': 'system_restart',
        'reboot_required': True,
        'description': (
            'Allow authenticated administrators to start or stop only the '
            'pinned, PixEagle-owned official PX4 SIH container from the '
            'Validation page; disabled by default'
        ),
    },
    'VideoSource.VIDEO_FILE_PATH': {
        'description': 'Path to the local video replay file',
    },
    'VideoSource.VIDEO_SOURCE_TYPE': {
        'options': [
            {'value': 'VIDEO_FILE', 'label': 'Video file',
             'description': 'Read frames from a local video file'},
            {'value': 'USB_CAMERA', 'label': 'USB camera',
             'description': 'Read frames from a local USB/V4L camera'},
            {'value': 'RTSP_OPENCV', 'label': 'RTSP via OpenCV',
             'description': 'Open an RTSP stream through OpenCV capture'},
            {'value': 'RTSP_STREAM', 'label': 'RTSP stream',
             'description': 'Open an RTSP stream with the configured stream backend'},
            {'value': 'UDP_STREAM', 'label': 'UDP stream',
             'description': 'Read a configured UDP video stream'},
            {'value': 'HTTP_STREAM', 'label': 'HTTP stream',
             'description': 'Read a configured HTTP video stream'},
            {'value': 'CSI_CAMERA', 'label': 'CSI camera',
             'description': 'Read frames from a Raspberry Pi or Jetson CSI camera'},
            {'value': 'CUSTOM_GSTREAMER', 'label': 'Custom GStreamer',
             'description': 'Use the advanced custom GStreamer input pipeline'},
        ],
        'description': 'Primary video input source type',
    },
    'VideoSource.VIDEO_FILE_EOF_POLICY': {
        'options': [
            {'value': 'LOOP', 'label': 'Loop',
             'description': 'Rewind at EOF with an explicit unusable boundary frame'},
            {'value': 'STOP', 'label': 'Stop',
             'description': 'Hold the final cached frame without reconnect attempts'},
        ],
        'description': (
            'End-of-file behavior for VIDEO_FILE; replay media is never command-fresh '
            'for autonomous following'
        ),
    },
    'Detector.DETECTION_ALGORITHM': {
        'options': [
            {
                'value': 'TemplateMatching',
                'label': 'Template matching',
                'description': 'Maintained classic-tracker recovery detector',
            },
        ],
        'description': 'Classic-tracker recovery detector implementation',
    },
    'Detector.TEMPLATE_MATCHING_METHOD': {
        'options': [
            {'value': 'TM_CCOEFF_NORMED', 'label': 'Normalized coefficient'},
            {'value': 'TM_CCORR_NORMED', 'label': 'Normalized correlation'},
            {'value': 'TM_SQDIFF_NORMED', 'label': 'Normalized square difference'},
            {'value': 'TM_CCOEFF', 'label': 'Raw coefficient'},
            {'value': 'TM_CCORR', 'label': 'Raw correlation'},
            {'value': 'TM_SQDIFF', 'label': 'Raw square difference'},
        ],
        'description': 'OpenCV template-matching score method; normalized methods are recommended',
    },
    'Segmentation.DEFAULT_SEGMENTATION_ALGORITHM': {
        'options': load_segmentation_schema_options(),
        'description': (
            'AI segmentation model used for click-assisted target selection; '
            'requires the optional AI runtime and a system restart'
        ),
        'legacy_value_aliases': [
            {
                'value': 'yolov11n.pt',
                'replacement': 'disabled',
                'reason': (
                    'The former default was not connected to an implemented '
                    'segmentation inference path'
                ),
            },
        ],
    },
    'Safety.GlobalLimits': {
        'description': (
            'Complete non-bypassable safety envelope; every canonical field is '
            'required and follower profiles may only tighten it'
        ),
        'required': [
            'MIN_ALTITUDE',
            'MAX_ALTITUDE',
            'ALTITUDE_WARNING_BUFFER',
            'ALTITUDE_SAFETY_ENABLED',
            'MAX_VELOCITY',
            'MAX_VELOCITY_FORWARD',
            'MAX_VELOCITY_LATERAL',
            'MAX_VELOCITY_VERTICAL',
            'MAX_YAW_RATE',
            'MAX_PITCH_RATE',
            'MAX_ROLL_RATE',
            'EMERGENCY_STOP_ENABLED',
            'RTL_ON_VIOLATION',
            'TARGET_LOSS_ACTION',
            'MAX_SAFETY_VIOLATIONS',
        ],
        'additional_properties': False,
    },
    'Safety.GlobalLimits.MIN_ALTITUDE': {
        'min': -10.0,
        'max': 100.0,
        'unit': 'm',
        'description': 'Absolute minimum permitted altitude above the configured reference',
    },
    'Safety.GlobalLimits.MAX_ALTITUDE': {
        'min': 0.000001,
        'max': 500.0,
        'unit': 'm',
        'description': 'Absolute maximum permitted altitude above the configured reference',
    },
    'Safety.GlobalLimits.ALTITUDE_WARNING_BUFFER': {
        'min': 0.0,
        'max': 100.0,
        'unit': 'm',
        'description': 'Warning distance inside the hard altitude envelope',
    },
    'Safety.GlobalLimits.ALTITUDE_SAFETY_ENABLED': {
        'description': 'Enforce the configured altitude envelope',
    },
    'Safety.GlobalLimits.MAX_VELOCITY': {
        'min': 0.000001,
        'max': 30.0,
        'unit': 'm/s',
        'description': 'Maximum overall velocity magnitude',
    },
    'Safety.GlobalLimits.MAX_VELOCITY_FORWARD': {
        'min': 0.000001,
        'max': 30.0,
        'unit': 'm/s',
        'description': 'Maximum forward velocity magnitude',
    },
    'Safety.GlobalLimits.MAX_VELOCITY_LATERAL': {
        'min': 0.000001,
        'max': 30.0,
        'unit': 'm/s',
        'description': 'Maximum lateral velocity magnitude',
    },
    'Safety.GlobalLimits.MAX_VELOCITY_VERTICAL': {
        'min': 0.000001,
        'max': 30.0,
        'unit': 'm/s',
        'description': 'Maximum vertical velocity magnitude',
    },
    'Safety.GlobalLimits.MAX_YAW_RATE': {
        'min': 0.000001,
        'max': 360.0,
        'unit': 'deg/s',
        'description': 'Maximum yaw-rate magnitude',
    },
    'Safety.GlobalLimits.MAX_PITCH_RATE': {
        'min': 0.000001,
        'max': 360.0,
        'unit': 'deg/s',
        'description': 'Maximum pitch-rate magnitude',
    },
    'Safety.GlobalLimits.MAX_ROLL_RATE': {
        'min': 0.000001,
        'max': 360.0,
        'unit': 'deg/s',
        'description': 'Maximum roll-rate magnitude',
    },
    'Safety.GlobalLimits.EMERGENCY_STOP_ENABLED': {
        'description': 'Allow the safety supervisor to request an emergency stop',
    },
    'Safety.GlobalLimits.RTL_ON_VIOLATION': {
        'description': 'Request return-to-launch for configured safety violations',
    },
    'Safety.GlobalLimits.TARGET_LOSS_ACTION': {
        'description': 'Safety action requested when the active target is lost',
        'options': [
            {'value': 'hover', 'label': 'Hover'},
            {'value': 'orbit', 'label': 'Orbit'},
            {'value': 'stop', 'label': 'Stop'},
            {'value': 'rtl', 'label': 'Return to launch'},
            {'value': 'continue', 'label': 'Continue'},
        ],
    },
    'Safety.GlobalLimits.MAX_SAFETY_VIOLATIONS': {
        'min': 1,
        'max': 1000,
        'description': 'Maximum counted safety violations before escalation',
    },
    'Streaming.API_EXPOSURE_MODE': {
        'options': [
            {'value': 'local_only', 'label': 'Local only',
             'description': 'Require an explicit loopback bind and loopback CORS origins'},
            {'value': 'trusted_lan_legacy', 'label': 'Trusted LAN (legacy)',
             'description': (
                 'Temporary LAN compatibility; use bearer tokens for machine clients '
                 'or explicit browser_session auth for browser clients'
             )},
        ],
        'description': 'API exposure boundary; wildcard origins are prohibited in every mode',
    },
    'Streaming.HTTP_STREAM_HOST': {
        'description': 'Backend bind host; local_only requires 127.0.0.1, ::1, or localhost',
    },
    'Streaming.HTTP_STREAM_PORT': {
        'description': 'Backend API and streaming port',
    },
    'Streaming.API_CORS_ALLOWED_ORIGINS': {
        'description': 'Explicit browser origins allowed to call the backend; wildcard origins are prohibited',
    },
    'Streaming.API_ALLOWED_HOSTS': {
        'description': (
            'Exact backend Host authorities for reviewed non-loopback profiles; '
            'an optional port supports reverse proxies; never use wildcards, URLs, or credentials'
        ),
    },
    'Streaming.API_AUTH_MODE': {
        'options': [
            {'value': 'local_compat', 'label': 'Local compatibility',
             'description': (
                 'Allow same-host loopback socket clients without credentials; '
                 'non-loopback clients need bearer tokens'
             )},
            {'value': 'machine_bearer', 'label': 'Machine bearer only',
             'description': (
                 'Require scoped bearer tokens for machine API clients'
             )},
            {'value': 'browser_session', 'label': 'Browser sessions',
             'description': (
                 'Require an external hashed user file and use HttpOnly cookies '
                 'with CSRF for browser/operator API access'
             )},
        ],
        'description': 'Runtime API authorization mode',
    },
    'Streaming.API_SYSTEM_RESTART_POLICY': {
        'options': [
            {'value': 'local_only', 'label': 'Local only',
             'description': 'Allow typed process restart only from a verified loopback transport'},
            {'value': 'lab_admin_browser', 'label': 'Lab admin browser',
             'description': (
                 'Also allow a remote authenticated admin browser session; '
                 'reserved for the beginner LAN demo profile'
             )},
        ],
        'description': (
            'Process-start policy for the typed backend restart action; '
            'changes require a process restart before taking effect'
        ),
    },
    'Streaming.ALLOW_UNAUTHENTICATED_MEDIA_STREAMING': {
        'type': 'boolean',
        'default': False,
        'description': (
            'Unsafe lab-only exception that allows anonymous access only to '
            'GET /video_feed and WS /ws/video_feed; never enables dashboard, '
            'control, config, logs, WebRTC signaling, or media-health APIs'
        ),
    },
    'Streaming.STREAM_FPS': {
        'type': 'integer',
        'default': 20,
        'min': 1,
        'max': 60,
        'unit': 'fps',
        'description': (
            'Browser transport frame-rate ceiling; only fresh publisher frames '
            'are sent, so the actual rate may be lower'
        ),
    },
    'Streaming.TARGET_BANDWIDTH_LOW_KBPS': {
        'description': (
            'Below this estimated KiB/s output rate, bandwidth permits a '
            'quality increase'
        ),
    },
    'Streaming.TARGET_BANDWIDTH_HIGH_KBPS': {
        'description': (
            'Above this estimated KiB/s output rate, reduce JPEG quality'
        ),
    },
    'Streaming.API_BEARER_TOKEN_FILE': {
        'description': 'Optional external JSON file containing hashed, named, revocable machine bearer token records',
    },
    'Streaming.API_SESSION_USER_FILE': {
        'description': 'Optional external JSON file containing hashed browser/operator session user records',
    },
    'Streaming.API_SESSION_TTL_SECONDS': {
        'type': 'integer', 'default': 28800, 'min': 60, 'max': 604800,
        'unit': 's',
        'description': 'Browser session lifetime in seconds for API_AUTH_MODE=browser_session',
    },
    'Streaming.API_SESSION_COOKIE_NAME': {
        'description': 'HttpOnly browser session cookie name for API_AUTH_MODE=browser_session',
    },
    'Streaming.API_SESSION_COOKIE_SECURE': {
        'description': 'Require HTTPS for the browser session cookie; enable when serving PixEagle over TLS',
    },
    'Streaming.API_CSRF_HEADER_NAME': {
        'description': 'Header name carrying the session-bound CSRF token for browser mutations',
    },
    'Streaming.API_SECURITY_AUDIT_ENABLED': {
        'description': 'Write durable JSONL API security audit events for auth, denial, sensitive read, mutation, and security-critical routes',
    },
    'Streaming.API_SECURITY_AUDIT_LOG_PATH': {
        'description': 'Local append-only JSONL path for sanitized API security audit events; do not store credentials here',
    },
    'Streaming.API_SECURITY_AUDIT_MAX_BYTES': {
        'type': 'integer', 'default': 5000000, 'min': 1024, 'max': 100000000,
        'unit': 'bytes',
        'description': 'Maximum security audit JSONL file size before rotation',
    },
    'Streaming.API_SECURITY_AUDIT_BACKUP_COUNT': {
        'type': 'integer', 'default': 5, 'min': 0, 'max': 20,
        'description': 'Number of rotated security audit JSONL files to retain locally',
    },
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
             'description': 'Installed Ultralytics BoT-SORT defaults without native ReID'},
            {'value': 'custom_reid', 'label': 'Custom ReID',
             'description': (
                 "ByteTrack plus PixEagle's local histogram/HOG appearance matching"
             )},
        ],
        'legacy_value_aliases': [
            {
                'value': 'botsort_reid',
                'replacement': 'botsort',
                'reason': (
                    'Native BoT-SORT ReID was advertised but never enabled by '
                    'the runtime backend'
                ),
            },
        ],
        'description': (
            'Supported multi-object tracker and optional PixEagle '
            'appearance-matching mode'
        ),
    },
    'SmartTracker.SMART_TRACKER_ENABLED': {
        'description': (
            'Schema compatibility flag; Smart Mode activation remains an '
            'explicit operator action'
        ),
    },
    'SmartTracker.DETECTION_BACKEND': {
        'options': [
            {
                'value': 'ultralytics',
                'label': 'Ultralytics',
                'description': 'The only currently registered detection backend',
            },
        ],
        'description': 'Detection backend implementation used by SmartTracker',
    },
    'SmartTracker.SMART_TRACKER_GPU_MODEL_PATH': {
        'description': (
            'Trusted direct-child PyTorch model registered in the adjacent '
            'model provenance store'
        ),
    },
    'SmartTracker.SMART_TRACKER_CPU_MODEL_PATH': {
        'description': (
            'Trusted direct-child NCNN export or PyTorch model registered in '
            'the adjacent model provenance store'
        ),
    },
    'SmartTracker.SMART_TRACKER_MODEL_MAX_BYTES': {
        'type': 'integer',
        'default': 268435456,
        'min': 1048576,
        'max': 536870912,
        'unit': 'bytes',
        'description': (
            'Maximum accepted PyTorch checkpoint size for upload and local '
            'registration; multipart overhead and disk headroom are enforced separately'
        ),
    },
    'SmartTracker.SMART_TRACKER_MODEL_TRUST_POLICY': {
        'options': [
            {
                'value': 'operator_ack_or_digest',
                'label': 'Operator acknowledgement or digest',
                'description': (
                    'Lab/development policy requiring explicit checkpoint trust; '
                    'a publisher SHA-256 remains recommended'
                ),
            },
            {
                'value': 'digest_required',
                'label': 'Publisher digest required',
                'description': (
                    'Deployment policy refusing registration without an expected SHA-256'
                ),
            },
        ],
        'description': 'Executable checkpoint admission policy',
    },
    'SmartTracker.SMART_TRACKER_NCNN_EXPORT_TIMEOUT_SECONDS': {
        'type': 'number',
        'default': 900,
        'min': 30,
        'max': 3600,
        'unit': 'seconds',
        'description': (
            'Hard wall-clock limit for the isolated NCNN export worker; '
            'timeout terminates the worker process group and discards staging'
        ),
    },
    'SmartTracker.SMART_TRACKER_SELECTION_TOLERANCE_RATIO': {
        'type': 'number',
        'default': 0.025,
        'min': 0.0,
        'max': 0.25,
        'unit': 'ratio',
        'description': (
            'Frame-relative fallback distance for operator clicks when the '
            'stream frame and detector frame differ slightly'
        ),
    },
    'SmartTracker.SMART_TRACKER_SELECTION_TOLERANCE_MAX_PIXELS': {
        'type': 'number',
        'default': 64,
        'min': 0,
        'max': 512,
        'unit': 'pixels',
        'description': (
            'Upper bound for tolerant SmartTracker click matching; zero uses '
            'the frame-relative ratio without a pixel cap'
        ),
    },
    'SmartTracker.SMART_TRACKER_SELECTION_SNAPSHOT_MAX_AGE_SECONDS': {
        'type': 'number',
        'default': 0.75,
        'min': 0.0,
        'max': 2.0,
        'step': 0.05,
        'unit': 'seconds',
        'description': (
            'Maximum age of the latest non-empty detector snapshot used only '
            'to absorb operator click and stream latency; cached selections '
            'remain tentative until a current measurement confirms them'
        ),
    },
    'SmartTracker.TRACKING_STRATEGY': {
        'options': [
            {'value': 'id_only', 'label': 'ID only'},
            {'value': 'hybrid', 'label': 'Hybrid'},
            {'value': 'spatial_only', 'label': 'Spatial only'},
        ],
        'description': 'Selected-target continuity strategy after initial selection',
    },
    'GimbalTracker.PROVIDER': {
        'options': [
            {'value': 'topotek_sip_udp', 'label': 'Topotek SIP UDP',
             'description': 'Topotek SIP-series UDP frames using GAC, GIC, TRC, and OFT'},
        ],
        'description': 'External gimbal input provider implementation',
    },
    'GimbalTracker.UDP_PORT': {
        'min': 1, 'max': 65535,
        'description': 'Provider UDP command/query port for topotek_sip_udp',
    },
    'GimbalTracker.LISTEN_PORT': {
        'min': 1, 'max': 65535,
        'description': 'Local UDP listen port for gimbal responses/broadcasts',
    },
    'GimbalTracker.CONNECTION_TIMEOUT': {
        'min': 0.1, 'max': 30.0, 'step': 0.1, 'unit': 's',
        'description': 'Freshness timeout for provider data and tracking state',
    },
    'GStreamer.ENABLE_GSTREAMER_STREAM': {
        'description': 'Enable the independent H.264/RTP/UDP output for QGC/GCS receivers',
    },
    'GStreamer.ENABLE_HARDWARE_ENCODING': {
        'description': 'Try supported hardware H.264 encoders before the x264 software fallback',
    },
    'GStreamer.GSTREAMER_HOST': {
        'description': 'Single QGC/GCS UDP destination hostname or IP address; do not include a scheme, port, or path',
    },
    'GStreamer.GSTREAMER_PORT': {
        'min': 1, 'max': 65535,
        'description': 'QGC/GCS H.264/RTP/UDP destination port',
    },
    'GStreamer.GSTREAMER_BITRATE': {
        'min': 100, 'max': 100000, 'unit': 'kbps',
        'description': 'Target H.264 encoder bitrate in kilobits per second',
    },
    'GStreamer.GSTREAMER_WIDTH': {
        'min': 16, 'max': 3840, 'unit': 'px',
        'description': 'Even QGC/GCS output width; frames are aspect-preserving letterboxed to this value',
    },
    'GStreamer.GSTREAMER_HEIGHT': {
        'min': 16, 'max': 2160, 'unit': 'px',
        'description': 'Even QGC/GCS output height; frames are aspect-preserving letterboxed to this value',
    },
    'GStreamer.GSTREAMER_FRAMERATE': {
        'min': 1, 'max': 60, 'unit': 'fps',
        'description': 'QGC/GCS submission cadence and raw-video caps frame rate; the combined pixel rate is runtime-validated',
    },
    'GStreamer.GSTREAMER_BUFFER_SIZE': {
        'min': 65536, 'max': 100000000, 'unit': 'bytes',
        'description': 'UDP socket send-buffer size in bytes',
    },
    'GStreamer.GSTREAMER_INCLUDE_OSD': {
        'description': 'Include processed PixEagle OSD in QGC/GCS output independently of browser stream OSD',
    },
    'GStreamer.GSTREAMER_SPEED_PRESET': {
        'options': [
            {'value': 'ultrafast', 'label': 'Ultra fast'},
            {'value': 'superfast', 'label': 'Super fast'},
            {'value': 'veryfast', 'label': 'Very fast'},
            {'value': 'faster', 'label': 'Faster'},
            {'value': 'fast', 'label': 'Fast'},
        ],
        'description': 'x264 software encoder speed/quality preset',
    },
    'GStreamer.GSTREAMER_KEY_INT_MAX': {
        'min': 1, 'max': 1000, 'unit': 'frames',
        'description': 'Maximum H.264 keyframe interval in frames',
    },
    'GStreamer.GSTREAMER_TUNE': {
        'options': [
            {'value': 'zerolatency', 'label': 'Zero latency'},
            {'value': 'fastdecode', 'label': 'Fast decode'},
            {'value': 'stillimage', 'label': 'Still image'},
        ],
        'description': 'x264 software encoder tuning mode; zero latency is recommended for live video',
    },

    # =========================================================
    # FOLLOWER / SAFETY SCHEMA OVERRIDES
    # These fix auto-generator limitations: wrong type inference,
    # over-restrictive max values, missing units, better descriptions.
    # WORKFLOW: always add fixes here (not directly to config_schema.yaml)
    # then run: python3 scripts/generate_schema.py
    # =========================================================

    # VideoSource — RTSP backoff base is in seconds, not 0-1
    'VideoSource.RTSP_RECOVERY_BACKOFF_BASE': {'max': 30.0, 'unit': 's',
        'description': 'Exponential backoff base interval for RTSP reconnect (seconds)'},

    # Runtime cadence knobs: keep config units explicit and bounded.
    'Follower.FOLLOWER_MODE': {
        'description': (
            'Active follower profile selected from the maintained follower registry'
        ),
    },
    'Follower.FOLLOWER_DATA_REFRESH_RATE': {
        'type': 'float', 'default': 5.0, 'min': 0.1, 'max': 100.0,
        'step': 0.1, 'unit': 'hz',
        'description': 'Telemetry refresh rate in Hz; runtime sleeps 1/rate between polling iterations'},
    'Follower.FOLLOWER_EXECUTION_MODE': {
        'type': 'string', 'default': 'PX4',
        'reload_tier': 'immediate', 'reboot_required': False,
        'options': [
            {'value': 'PX4', 'label': 'PX4 live command path'},
            {'value': 'COMMAND_PREVIEW', 'label': 'Local follower test (no PX4)'},
        ],
        'description': (
            'Follower command boundary: PX4 requires live non-replay input; '
            'COMMAND_PREVIEW records replay-driven intents locally while the '
            'circuit breaker remains active and never sends MAVSDK/PX4 commands. '
            'A change selects the next session and never changes an active session'
        ),
    },
    'MAVLink.MAVLINK_POLLING_INTERVAL': {
        'type': 'float', 'default': 0.5, 'min': 0.1, 'max': 10.0,
        'step': 0.1, 'unit': 's',
        'description': 'MavlinkDataManager polling interval for the MAVLink2REST aggregate endpoint'},
    'MAVLink.MAVLINK_REQUEST_TIMEOUT_S': {
        'type': 'float', 'default': 5.0, 'min': 0.1, 'max': 30.0,
        'step': 0.1, 'unit': 's',
        'description': 'HTTP timeout for each MAVLink2REST request before telemetry is marked degraded'},
    'MAVLink.MAVLINK_REQUEST_RETRIES': {
        'type': 'integer', 'default': 0, 'min': 0, 'max': 5,
        'description': 'Additional retry attempts after the initial MAVLink2REST request fails'},
    'MAVLink.MAVLINK_STALE_TIMEOUT_S': {
        'type': 'float', 'default': 2.0, 'min': 0.1, 'max': 5.0,
        'step': 0.1, 'unit': 's',
        'description': 'Maximum age since the last successful MAVLink2REST request before telemetry is reported stale'},
    'PX4.EXTERNAL_MAVSDK_SERVER': {
        'description': 'Use a gRPC mavsdk_server process instead of the Python client spawning an embedded child process'},
    'PX4.MAVSDK_SERVER_ADDRESS': {
        'type': 'string', 'default': '127.0.0.1',
        'description': 'Host or IP address of the external MAVSDK gRPC server'},
    'PX4.MAVSDK_SERVER_PORT': {
        'type': 'integer', 'default': 50051, 'min': 1, 'max': 65535,
        'description': 'TCP port of the external MAVSDK gRPC server'},
    'PX4.SYSTEM_ADDRESS': {
        'description': 'Vehicle link URI used by an embedded server or passed to the PixEagle-managed external mavsdk_server process'},
    'PX4.MAVSDK_CONNECTION_TIMEOUT_S': {
        'type': 'float', 'default': 15.0, 'min': 0.1, 'max': 120.0,
        'step': 0.5, 'unit': 's',
        'description': 'Deadline for MAVSDK to discover a connected PX4 vehicle after opening the configured link'},
    'PX4.MAVSDK_COMMAND_TIMEOUT_S': {
        'type': 'float', 'default': 3.0, 'min': 0.05, 'max': 30.0,
        'step': 0.05, 'unit': 's',
        'description': 'Deadline for one MAVSDK setpoint, Offboard, or action command RPC'},
    'Setpoint.SETPOINT_PUBLISH_RATE_S': {
        'min': 0.001, 'max': 1.0, 'step': 0.01, 'unit': 's',
        'description': 'SetpointSender monitor loop period in seconds; does not publish MAVSDK Offboard commands'},
    'Setpoint.OFFBOARD_COMMAND_RATE_HZ': {
        'type': 'float', 'default': 20.0, 'min': 5.0, 'max': 100.0,
        'step': 1.0, 'unit': 'hz',
        'description': 'OffboardCommander application-level MAVSDK setter refresh rate in Hz; MAVSDK independently retransmits the latest setpoint'},
    'Setpoint.OFFBOARD_COMMAND_TTL_S': {
        'type': 'float', 'default': 0.5, 'min': 0.1, 'max': 2.0,
        'step': 0.1, 'unit': 's',
        'description': 'Maximum age of the latest follower CommandIntent before OffboardCommander publishes default fail-closed setpoints'},
    'Setpoint.OFFBOARD_COMMAND_FAILURE_THRESHOLD': {
        'type': 'integer', 'default': 3, 'min': 1, 'max': 10,
        'description': 'Consecutive OffboardCommander publish failures before local fail-closed follow stop'},
    'Setpoint.OFFBOARD_PUBLISH_TIMEOUT_S': {
        'type': 'float', 'default': 0.25, 'min': 0.05, 'max': 1.0,
        'step': 0.05, 'unit': 's',
        'description': 'Deadline for one application-level Offboard setpoint publication'},

    # TARGET_LOSS_COORDINATE_THRESHOLD — was mistyped as int=990; correct is float in [0,5]
    'FW_ATTITUDE_RATE.TARGET_LOSS_COORDINATE_THRESHOLD': {
        'type': 'float', 'default': 1.5, 'min': 0.0, 'max': 5.0, 'step': 0.1,
        'description': 'Normalized pixel threshold for target loss detection (0-2 range typical)'},
    'MC_ATTITUDE_RATE.TARGET_LOSS_COORDINATE_THRESHOLD': {
        'type': 'float', 'default': 1.5, 'min': 0.0, 'max': 5.0, 'step': 0.1,
        'description': 'Normalized pixel threshold for target loss detection (0-2 range typical)'},

    # GM_VELOCITY_CHASE — degree/angle params wrongly capped at 1.0
    'GM_VELOCITY_CHASE.NEUTRAL_PITCH_ANGLE': {
        'min': -90.0, 'max': 90.0, 'step': 0.5, 'unit': 'deg',
        'description': 'Neutral pitch angle for HORIZONTAL mount only (degrees)'},

    # GM_VELOCITY_VECTOR — mount offset angles wrongly capped at 1.0
    'GM_VELOCITY_VECTOR.MOUNT_ROLL_OFFSET_DEG':  {'min': -180.0, 'max': 180.0, 'step': 0.5, 'unit': 'deg',
        'description': 'Roll offset to correct physical gimbal mount misalignment (degrees)'},
    'GM_VELOCITY_VECTOR.MOUNT_PITCH_OFFSET_DEG': {'min': -180.0, 'max': 180.0, 'step': 0.5, 'unit': 'deg',
        'description': 'Pitch offset to correct physical gimbal mount misalignment (degrees)'},
    'GM_VELOCITY_VECTOR.MOUNT_YAW_OFFSET_DEG':   {'min': -180.0, 'max': 180.0, 'step': 0.5, 'unit': 'deg',
        'description': 'Yaw offset to correct physical gimbal mount misalignment (degrees)'},

    # GM_VELOCITY_VECTOR — velocity/acceleration params wrongly capped at 1.0
    'GM_VELOCITY_VECTOR.RAMP_ACCELERATION':  {'min': 0.0, 'max': 20.0, 'step': 0.05, 'unit': 'm/s²',
        'description': 'Velocity ramp-up acceleration rate (m/s²)'},
    'GM_VELOCITY_VECTOR.INITIAL_VELOCITY':   {'min': 0.0, 'max': 30.0, 'step': 0.1,  'unit': 'm/s',
        'description': 'Initial forward velocity when target acquired (m/s)'},
    'GM_VELOCITY_VECTOR.ALTITUDE_CHECK_INTERVAL': {'min': 0.01, 'max': 60.0, 'step': 0.1, 'unit': 's',
        'description': 'How often to check altitude safety (seconds)'},

    # MC_VELOCITY_CHASE — velocity/acceleration params wrongly capped at 1.0
    'MC_VELOCITY_CHASE.FORWARD_RAMP_RATE': {'min': 0.0, 'max': 20.0, 'step': 0.05, 'unit': 'm/s²',
        'description': 'Forward velocity ramp-up acceleration rate (m/s²)'},
    'MC_VELOCITY_CHASE.INITIAL_FORWARD_VELOCITY': {'min': 0.0, 'max': 30.0, 'step': 0.1, 'unit': 'm/s',
        'description': 'Initial forward velocity when target acquired (m/s)'},
    'MC_VELOCITY_CHASE.TARGET_LOSS_STOP_VELOCITY': {'min': 0.0, 'max': 30.0, 'step': 0.1, 'unit': 'm/s',
        'description': 'Forward velocity to hold when target is temporarily lost (m/s)'},
    'MC_VELOCITY_CHASE.MIN_FORWARD_VELOCITY_THRESHOLD': {'min': 0.0, 'max': 20.0, 'step': 0.05, 'unit': 'm/s',
        'description': 'Minimum forward velocity to maintain (m/s). Critical for VTOL or fixed-wing configurations.'},

    # FW_ATTITUDE_RATE — orbit/L1 params wrongly capped at 100m
    'FW_ATTITUDE_RATE.ORBIT_RADIUS':    {'min': 10.0, 'max': 2000.0, 'step': 5.0, 'unit': 'm',
        'description': 'Loiter orbit radius on target loss (meters)'},
    'FW_ATTITUDE_RATE.L1_MAX_DISTANCE': {'min': 5.0,  'max': 1000.0, 'step': 5.0, 'unit': 'm',
        'description': 'Maximum L1 lookahead distance at high speed (meters)'},

    # FW_ATTITUDE_RATE — pitch/bank angle limits (float in [0,100] auto-infers max=100, wrong)
    'FW_ATTITUDE_RATE.MAX_PITCH_ANGLE': {'min': 0.0, 'max': 90.0, 'step': 1.0, 'unit': 'deg',
        'description': 'Maximum pitch up angle structural limit (degrees)'},
    'FW_ATTITUDE_RATE.MIN_PITCH_ANGLE': {'min': -90.0, 'max': 0.0, 'step': 1.0, 'unit': 'deg',
        'description': 'Maximum pitch down angle structural limit (degrees)'},
    'FW_ATTITUDE_RATE.MAX_BANK_ANGLE': {'min': 0.0, 'max': 90.0, 'step': 1.0, 'unit': 'deg',
        'description': 'Maximum bank angle for coordinated turns (degrees)'},

    # MC_ATTITUDE_RATE — same issue for pitch/bank/roll angle limits
    'MC_ATTITUDE_RATE.MAX_PITCH_ANGLE': {'min': 0.0, 'max': 90.0, 'step': 1.0, 'unit': 'deg',
        'description': 'Maximum pitch angle limit (degrees)'},
    'MC_ATTITUDE_RATE.MAX_ROLL_ANGLE': {'min': 0.0, 'max': 90.0, 'step': 1.0, 'unit': 'deg',
        'description': 'Maximum roll angle limit (degrees)'},
    'MC_ATTITUDE_RATE.MAX_BANK_ANGLE': {'min': 0.0, 'max': 90.0, 'step': 1.0, 'unit': 'deg',
        'description': 'Maximum bank angle for coordinated turns (degrees)'},

    # FW_ATTITUDE_RATE — keys absent from schema before v6.0.2 audit
    'FW_ATTITUDE_RATE.L1_LATERAL_SCALE': {'type': 'float', 'default': 50.0,
        'min': 0.0, 'max': 500.0, 'step': 1.0, 'unit': 'm',
        'description': 'L1 guidance lateral scale factor (m)'},
    'FW_ATTITUDE_RATE.TECS_ALTITUDE_SCALE': {'type': 'float', 'default': 20.0,
        'min': 0.0, 'max': 200.0, 'step': 1.0, 'unit': 'm',
        'description': 'TECS altitude error scale (m)'},
    'FW_ATTITUDE_RATE.TECS_MAX_INTEGRAL': {'type': 'float', 'default': 50.0,
        'min': 0.0, 'max': 500.0, 'step': 1.0,
        'description': 'TECS maximum integral term'},
    'FW_ATTITUDE_RATE.FALLBACK_ALTITUDE_PITCH_GAIN': {'type': 'float', 'default': 0.5,
        'min': 0.0, 'max': 10.0, 'step': 0.01,
        'description': 'Fallback altitude pitch gain when TECS unavailable'},
}

# Recommended ranges for parameters (soft limits that trigger warnings, not errors).
# Keys are "SectionName.PARAM_NAME".
RECOMMENDED_RANGES = {
    'SmartTracker.SMART_TRACKER_CONFIDENCE_THRESHOLD': {'recommended_min': 0.15, 'recommended_max': 0.7},
    'SmartTracker.SMART_TRACKER_IOU_THRESHOLD': {'recommended_min': 0.2, 'recommended_max': 0.6},
    'SmartTracker.SMART_TRACKER_LABEL_PLATE_OPACITY': {'recommended_min': 0.4, 'recommended_max': 0.9},
    'Streaming.JPEG_QUALITY': {'recommended_min': 50, 'recommended_max': 95},
}

# Reload tier mapping: section-level defaults.
# Tiers: 'immediate', 'follower_restart', 'tracker_restart', 'system_restart'
SECTION_RELOAD_TIERS = {
    # immediate — visual/display settings, read every frame
    'OSD': 'immediate',
    'Debugging': 'immediate',
    'FrameEstimation': 'immediate',

    # follower_restart — follower/control params, need follower reinit
    'PID': 'follower_restart',
    'Follower': 'follower_restart',
    'Safety': 'follower_restart',
    'MC_VELOCITY_CHASE': 'follower_restart',
    'MC_VELOCITY_POSITION': 'follower_restart',
    'MC_VELOCITY_DISTANCE': 'follower_restart',
    'MC_VELOCITY_GROUND': 'follower_restart',
    'MC_ATTITUDE_RATE': 'follower_restart',
    'GM_VELOCITY_CHASE': 'follower_restart',
    'GM_VELOCITY_VECTOR': 'follower_restart',
    'FW_ATTITUDE_RATE': 'follower_restart',

    # tracker_restart — tracker/detection params, need tracker reinit
    'Tracking': 'tracker_restart',
    'TrackerSafety': 'tracker_restart',
    'SmartTracker': 'tracker_restart',
    'ClassicTracker_Common': 'tracker_restart',
    'CSRT_Tracker': 'tracker_restart',
    'KCF_Tracker': 'tracker_restart',
    'DLIB_Tracker': 'tracker_restart',
    'GimbalTracker': 'tracker_restart',
    'GimbalTrackerSettings': 'tracker_restart',
    'Detector': 'tracker_restart',
    'Estimator': 'tracker_restart',
    'FramePreprocessor': 'tracker_restart',
    'Setpoint': 'tracker_restart',

    # system_restart — video/network/hardware, need full restart
    'VideoSource': 'system_restart',
    'USBCamera': 'system_restart',
    'CSICamera': 'system_restart',
    'Recording': 'system_restart',
    'PX4': 'system_restart',
    'MAVLink': 'system_restart',
    'Streaming': 'system_restart',
    'GStreamer': 'system_restart',
    'GStreamerPipelines': 'system_restart',
    'Telemetry': 'system_restart',
    'Segmentation': 'system_restart',
}

# Parameter-level reload tier overrides (highest priority, keyed by "Section.PARAM").
RELOAD_TIER_OVERRIDES = {
    'Setpoint.SETPOINT_PUBLISH_RATE_S': 'follower_restart',
    'Setpoint.OFFBOARD_COMMAND_RATE_HZ': 'follower_restart',
    'Setpoint.OFFBOARD_COMMAND_TTL_S': 'follower_restart',
    'Setpoint.OFFBOARD_COMMAND_FAILURE_THRESHOLD': 'follower_restart',
    'Setpoint.OFFBOARD_PUBLISH_TIMEOUT_S': 'follower_restart',
    # SmartTracker model/GPU params require system restart when edited through
    # the generic settings API. The model-selection API owns its narrower,
    # validated live/standby transition.
    'SmartTracker.SMART_TRACKER_USE_GPU': 'system_restart',
    'SmartTracker.SMART_TRACKER_GPU_MODEL_PATH': 'system_restart',
    'SmartTracker.SMART_TRACKER_CPU_MODEL_PATH': 'system_restart',
    'SmartTracker.SMART_TRACKER_MODEL_MAX_BYTES': 'system_restart',
    'SmartTracker.SMART_TRACKER_MODEL_TRUST_POLICY': 'system_restart',
    'SmartTracker.SMART_TRACKER_NCNN_EXPORT_TIMEOUT_SECONDS': 'system_restart',
    'SmartTracker.SMART_TRACKER_MODEL_TASK_POLICY': 'system_restart',
    # SmartTracker display settings can change immediately
    'SmartTracker.SMART_TRACKER_LABEL_PLATE_OPACITY': 'immediate',
    'GStreamer.GSTREAMER_INCLUDE_OSD': 'immediate',
}


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


def get_reload_tier(full_path: str) -> str:
    """Determine reload tier for a parameter.

    Resolution order:
    1. Parameter-level override (RELOAD_TIER_OVERRIDES)
    2. Section-level default (SECTION_RELOAD_TIERS)
    3. Safe fallback: 'system_restart'
    """
    if full_path in RELOAD_TIER_OVERRIDES:
        return RELOAD_TIER_OVERRIDES[full_path]

    section = full_path.split('.')[0] if '.' in full_path else full_path
    return SECTION_RELOAD_TIERS.get(section, 'system_restart')


def extract_unit(description: str) -> Optional[str]:
    """Extract unit from description if present.

    Pattern 1: trailing parenthetical e.g. (m/s), (degrees) — validated to look like a real unit.
    Pattern 2: well-known unit keywords anywhere in the description.

    False positive guard: parenthetical must be short (≤15 chars), contain no '=' sign,
    and start with a letter/°/%. This prevents extracting phrases like '(lower = less CPU)'.
    """
    unit_map = {
        'pixels': 'px',
        'degrees': 'deg',
        'seconds': 's',
        'sec': 's',
        'milliseconds': 'ms',
    }

    # Pattern 1: trailing parenthetical like (m/s), (degrees), (px)
    trail_match = re.search(r'\(([^)]+)\)\s*$', description, re.IGNORECASE)
    if trail_match:
        candidate = trail_match.group(1).strip()
        # Validate: real units are short, have no '=' sign, and use unit-like chars only
        if (len(candidate) <= 15
                and '=' not in candidate
                and re.match(r'^[a-zA-Z°/%²³][a-zA-Z0-9°/%²³·/\- ]{0,14}$', candidate)):
            unit = candidate.lower()
            return unit_map.get(unit, unit)

    # Pattern 2: well-known unit keyword in description (fallback)
    well_known = r'\b(m/s|m/s²|m|ms|px|pixels|fps|Hz|degrees|deg|deg/s|rad|rad/s|seconds|sec|s|%)\b'
    match = re.search(well_known, description, re.IGNORECASE)
    if match:
        unit = match.group(1).lower()
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
    pipe_value = r'["\']?[A-Za-z0-9_]+["\']?'
    pipe_match = re.search(
        PREFIX + rf':\s*({pipe_value}(?:\s*\|\s*{pipe_value})+)',
        description,
        re.IGNORECASE,
    )
    if pipe_match:
        options_str = pipe_match.group(1).strip()
        for opt in options_str.split('|'):
            opt = opt.strip().strip('"\'')
            if opt and re.match(r'^[a-zA-Z0-9_]+$', opt):
                options.append({'value': opt, 'label': opt})
        if options:
            # Clean the Options:/Allowed: ... part from description
            cleaned = (
                description[:pipe_match.start()]
                + description[pipe_match.end():]
            )
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            cleaned = re.sub(r'^[\s:;,.\-\u2013\u2014]+', '', cleaned).strip()
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


def _extract_comment_text(ca_item) -> str:
    """Extract inline (EOL) comment string from a ruamel.yaml CommentToken list.

    ruamel.yaml stores comment tokens in a list: [pre_comment, key_comment, eol_comment, post_comment].
    Index 2 is the EOL comment — the inline comment on the same line as the value.
    We use only this token to avoid merging block/pre-comments with inline comments.
    """
    if ca_item is None:
        return ''
    if isinstance(ca_item, list) and len(ca_item) > 2:
        token = ca_item[2]
        if token is not None and hasattr(token, 'value'):
            return token.value.strip().lstrip('#').strip()
        return ''
    # Fallback for non-list (single token)
    if hasattr(ca_item, 'value'):
        return ca_item.value.strip().lstrip('#').strip()
    return ''


def _collect_comments(mapping: RuamelCommentedMap, prefix: str, result: Dict[str, str]) -> None:
    """Recursively collect inline comments from a ruamel.yaml CommentedMap.

    Stores comments keyed by their full dotted path (e.g., 'SmartTracker.CONFIDENCE_THRESHOLD').
    This matches the key format expected by process_params() in process_section().
    """
    if not isinstance(mapping, RuamelCommentedMap):
        return
    for key in mapping:
        full_key = f"{prefix}.{key}" if prefix else str(key)
        ca_item = mapping.ca.items.get(key)
        comment_text = _extract_comment_text(ca_item)
        if comment_text:
            result[full_key] = comment_text
        # Recurse into nested mappings
        sub = mapping[key]
        if isinstance(sub, RuamelCommentedMap):
            _collect_comments(sub, full_key, result)


def parse_config_with_comments(config_path: str) -> Tuple[Dict, Dict[str, str]]:
    """Parse config file and extract comments for descriptions.

    Uses ruamel.yaml to preserve comments natively (avoids fragile regex line scanning).
    ruamel.yaml attaches CommentToken objects directly to mapping nodes, so comment
    extraction is a simple recursive traversal — no look-ahead/look-behind needed.

    Returns:
        (config, comments) where:
        - config: plain Python dict (via yaml.safe_load for pure types)
        - comments: dict mapping 'Section.KEY' → comment string
    """
    # Load with ruamel.yaml to get comment-annotated mapping
    ryaml = RuamelYAML()
    ryaml.preserve_quotes = True
    with open(config_path, 'r', encoding='utf-8') as f:
        ruamel_data = ryaml.load(f)

    # Also load with PyYAML for plain Python types (avoids ruamel scalar subclasses)
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # Collect comments recursively from the ruamel-annotated tree
    comments: Dict[str, str] = {}
    _collect_comments(ruamel_data, '', comments)

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

    # Strip comment artifacts from description (e.g., trailing "# === Section ===" blocks)
    if description:
        description = re.split(r'\n\s*#', description)[0].strip()

    # Enum choices are meaningful for selectors, not continuous numeric controls.
    # Restrict prose inference so phrases such as "fixed-wing or VTOL" cannot
    # turn a float's unit/description into an invalid option list.
    if param_type in {'string', 'integer'}:
        options, cleaned_description = extract_options(description)
    else:
        options, cleaned_description = None, description

    lookup_key = full_path or key
    reload_tier = get_reload_tier(lookup_key)

    schema = {
        'type': param_type,
        'default': value,
        'description': cleaned_description or f'{key} parameter',
        'reload_tier': reload_tier,
        'reboot_required': reload_tier == 'system_restart',
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
    unit = extract_unit(cleaned_description) if param_type in {'integer', 'float'} else None
    if unit:
        schema['unit'] = unit

    # Extract [N..M] recommended range from description (soft advisory, not a hard limit)
    # e.g., "JPEG quality [50..95]" → recommended_min=50, recommended_max=95
    range_match = re.search(r'\[(\d+\.?\d*)\s*\.{2,3}\s*(\d+\.?\d*)\]', description)
    if range_match:
        schema['recommended_min'] = float(range_match.group(1))
        schema['recommended_max'] = float(range_match.group(2))

    # Apply recommended ranges from RECOMMENDED_RANGES dict (overrides [N..M] if present)
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
        'parameters': {},
        'additional_properties': False,
    }

    def process_object(key: str, value: Dict[str, Any], full_path: str) -> Dict:
        """Build a complete closed recursive contract for one object value."""
        desc = comments.get(full_path, comments.get(key, ''))
        object_schema = generate_parameter_schema(
            key,
            value,
            desc,
            full_path=full_path,
        )
        properties = {}
        for child_key, child_value in value.items():
            if not isinstance(child_key, str) or not child_key:
                raise ValueError(
                    f'Configuration object {full_path} has a non-string key'
                )
            child_path = f'{full_path}.{child_key}'
            child_desc = comments.get(
                child_path,
                comments.get(child_key, ''),
            )
            if isinstance(child_value, dict):
                properties[child_key] = process_object(
                    child_key,
                    child_value,
                    child_path,
                )
            else:
                properties[child_key] = generate_parameter_schema(
                    child_key,
                    child_value,
                    child_desc,
                    full_path=child_path,
                )

        object_schema['properties'] = properties
        object_schema.setdefault('required', list(value))
        object_schema.setdefault('additional_properties', False)
        return object_schema

    def process_params(data: Dict, prefix: str = '') -> Dict:
        """Recursively process parameters."""
        params = {}
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            desc = comments.get(full_key, comments.get(key, ''))

            if isinstance(value, dict):
                params[key] = process_object(key, value, full_key)
            else:
                params[key] = generate_parameter_schema(key, value, desc,
                                                         full_path=full_key)

        return params

    section_schema['parameters'] = process_params(section_data, section_name)

    return section_schema


def load_canonical_follower_names(repo_root: Path) -> List[str]:
    """Return the exact uppercase catalog of active follower profiles."""
    follower_schema_path = repo_root / 'configs' / 'follower_commands.yaml'
    follower_schema = yaml.safe_load(
        follower_schema_path.read_text(encoding='utf-8')
    ) or {}
    profiles = follower_schema.get('follower_profiles', {})
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError('follower_commands.yaml must define canonical profiles')

    follower_names = []
    for profile_name, profile_contract in profiles.items():
        if (
            not isinstance(profile_name, str)
            or not profile_name.strip()
            or not isinstance(profile_contract, dict)
        ):
            raise ValueError(
                'follower_commands.yaml profiles must be named contract objects'
            )
        follower_names.append(profile_name.upper())
    if len(follower_names) != len(set(follower_names)):
        raise ValueError('Canonical follower profile names collide when uppercased')
    return follower_names


def _make_sparse_override_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Remove defaults and required keys while retaining a typed closed shape."""
    sparse = copy.deepcopy(schema)

    def strip(node: Dict[str, Any]) -> None:
        node.pop('default', None)
        if node.get('type') != 'object':
            return
        node['required'] = []
        node['additional_properties'] = False
        properties = node.get('properties', {})
        if not isinstance(properties, dict):
            raise ValueError('Object schemas must expose a properties mapping')
        for property_schema in properties.values():
            if not isinstance(property_schema, dict):
                raise ValueError('Object property schemas must be mappings')
            strip(property_schema)

    strip(sparse)
    return sparse


def apply_operational_follower_override_contract(
    schema: Dict[str, Any],
    config: Dict[str, Any],
    repo_root: Path,
) -> None:
    """Generate sparse operational overrides for every active profile."""
    follower_names = load_canonical_follower_names(repo_root)
    follower_parameters = schema['sections']['Follower']['parameters']
    general_schema = follower_parameters.get('General')
    if not isinstance(general_schema, dict):
        raise ValueError('Follower.General must expose a schema object')
    general_properties = general_schema.get('properties')
    if not isinstance(general_properties, dict) or not general_properties:
        raise ValueError('Follower.General must expose recursive property schemas')

    configured_overrides = config.get('Follower', {}).get(
        'FollowerOverrides',
        {},
    )
    if not isinstance(configured_overrides, dict):
        raise ValueError('Follower.FollowerOverrides defaults must be an object')
    unknown_defaults = sorted(set(configured_overrides) - set(follower_names))
    if unknown_defaults:
        raise ValueError(
            'Follower.FollowerOverrides contains unknown follower defaults: '
            + ', '.join(unknown_defaults)
        )

    sparse_properties = {
        name: _make_sparse_override_schema(property_schema)
        for name, property_schema in general_properties.items()
    }
    follower_properties = {}
    for follower_name in follower_names:
        follower_properties[follower_name] = {
            'type': 'object',
            'default': copy.deepcopy(
                configured_overrides.get(follower_name, {})
            ),
            'description': (
                f'Sparse operational overrides for {follower_name}; omitted '
                'values inherit the complete Follower.General contract'
            ),
            'reload_tier': 'follower_restart',
            'reboot_required': False,
            'properties': copy.deepcopy(sparse_properties),
            'required': [],
            'additional_properties': False,
        }

    follower_parameters['FollowerOverrides'] = {
        'type': 'object',
        'default': copy.deepcopy(configured_overrides),
        'description': (
            'Sparse operational overrides keyed by canonical uppercase '
            'follower profile name'
        ),
        'reload_tier': 'follower_restart',
        'reboot_required': False,
        'properties': follower_properties,
        'required': [],
        'additional_properties': False,
    }


def apply_safety_follower_override_contract(
    schema: Dict[str, Any],
    config: Dict[str, Any],
    repo_root: Path,
) -> None:
    """Generate strict sparse safety overrides from canonical follower profiles."""
    follower_names = load_canonical_follower_names(repo_root)

    safety_parameters = schema['sections']['Safety']['parameters']
    global_schema = safety_parameters['GlobalLimits']
    global_properties = global_schema.get('properties', {})
    if not isinstance(global_properties, dict) or not global_properties:
        raise ValueError('Safety.GlobalLimits must expose strict property schemas')

    configured_overrides = config.get('Safety', {}).get('FollowerOverrides', {})
    if not isinstance(configured_overrides, dict):
        raise ValueError('Safety.FollowerOverrides defaults must be an object')
    unknown_defaults = sorted(set(configured_overrides) - set(follower_names))
    if unknown_defaults:
        raise ValueError(
            'Safety.FollowerOverrides contains unknown follower defaults: '
            + ', '.join(unknown_defaults)
        )

    follower_properties = {}
    for follower_name in follower_names:
        override_properties = copy.deepcopy(global_properties)
        for property_schema in override_properties.values():
            if isinstance(property_schema, dict):
                property_schema.pop('default', None)
        follower_properties[follower_name] = {
            'type': 'object',
            'default': copy.deepcopy(configured_overrides.get(follower_name, {})),
            'description': (
                f'Sparse tightening safety limits for {follower_name}; omitted '
                'limits inherit the hard Safety.GlobalLimits envelope'
            ),
            'reload_tier': 'follower_restart',
            'reboot_required': False,
            'properties': override_properties,
            'required': [],
            'additional_properties': False,
        }

    safety_parameters['FollowerOverrides'] = {
        'type': 'object',
        'default': copy.deepcopy(configured_overrides),
        'description': (
            'Sparse per-follower limits that may only tighten the hard global '
            'envelope, keyed by canonical uppercase follower profile name'
        ),
        'reload_tier': 'follower_restart',
        'reboot_required': False,
        'properties': follower_properties,
        'required': [],
        'additional_properties': False,
    }


def apply_smart_tracker_overlay_contract(schema: Dict[str, Any]) -> None:
    """Constrain SmartTracker BGR colors to exactly three numeric channels."""
    parameters = schema['sections']['SmartTracker']['parameters']
    parameters['SMART_TRACKER_SHOW_FPS']['description'] = (
        'Show SmartTracker processing FPS in the video overlay'
    )
    descriptions = {
        'SMART_TRACKER_ACTIVE_COLOR': 'Three-channel BGR active target color',
        'SMART_TRACKER_PASSIVE_COLOR': (
            'Three-channel BGR unselected detection color'
        ),
    }
    for name, description in descriptions.items():
        color_schema = parameters[name]
        color_schema.update({
            'description': description,
            'item_type': 'number',
            'min_items': 3,
            'max_items': 3,
        })


def generate_schema(config_path: str, output_path: str):
    """Generate schema file from config."""
    print(f"Reading config from: {config_path}")

    config, comments = parse_config_with_comments(config_path)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        generated_from = str(Path(config_path).resolve().relative_to(repo_root))
    except ValueError:
        generated_from = str(Path(config_path))

    schema = {
        'schema_version': CONFIG_SCHEMA_VERSION,
        'meta': {
            'project': 'PixEagle',
            'generated_from': generated_from,
            'generated_at': None,
            'description': 'Auto-generated schema for PixEagle configuration',
            'extension_sections': {},
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

    apply_operational_follower_override_contract(schema, config, repo_root)
    apply_safety_follower_override_contract(schema, config, repo_root)
    apply_smart_tracker_overlay_contract(schema)

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
