"""
Tests for schema generation: option extraction, unit extraction, comment parsing,
Pydantic config validation, and end-to-end schema correctness.
"""

import os
import sys
from pathlib import Path

import pytest
import yaml

# Add project root to import scripts module
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, PROJECT_ROOT)
CONFIGS_DIR = Path(PROJECT_ROOT) / "configs"

from scripts.generate_schema import (  # noqa: E402
    extract_options,
    extract_unit,
    infer_type,
    generate_parameter_schema,
    parse_config_with_comments,
    SCHEMA_OVERRIDES,
    RECOMMENDED_RANGES,
)


def test_extract_options_with_parenthetical_descriptions_and_prefix_text():
    description = (
        "Fixed-camera lateral guidance strategy. "
        "Options: coordinated_turn (recommended fixed camera), "
        "sideslip (advanced, may lose target)"
    )

    options, cleaned = extract_options(description)

    assert cleaned == "Fixed-camera lateral guidance strategy."
    assert options == [
        {
            "value": "coordinated_turn",
            "label": "coordinated_turn",
            "description": "recommended fixed camera",
        },
        {
            "value": "sideslip",
            "label": "sideslip",
            "description": "advanced, may lose target",
        },
    ]


# ---- New tests for Allowed: prefix ----

def test_extract_options_allowed_prefix_comma():
    """Allowed: prefix should be recognized like Options: prefix."""
    options, cleaned = extract_options("Allowed: 0, 90, 180, 270")
    assert options is not None
    assert len(options) == 4
    values = [o['value'] for o in options]
    assert values == ['0', '90', '180', '270']
    assert cleaned == ''


def test_extract_options_allowed_prefix_strings():
    """Allowed: with string values."""
    options, cleaned = extract_options("Allowed: none, horizontal, vertical, both")
    assert options is not None
    assert len(options) == 4
    values = [o['value'] for o in options]
    assert values == ['none', 'horizontal', 'vertical', 'both']


def test_extract_options_allowed_prefix_pipe():
    """Allowed: with pipe separator."""
    options, cleaned = extract_options("Allowed: fast | balanced | quality")
    assert options is not None
    assert len(options) == 3
    values = [o['value'] for o in options]
    assert values == ['fast', 'balanced', 'quality']


# ---- New tests for "or"-separated values ----

def test_extract_options_or_separated():
    """Simple 'or'-separated values should generate options."""
    options, cleaned = extract_options("MANUAL or AUTO")
    assert options is not None
    assert len(options) == 2
    values = [o['value'] for o in options]
    assert values == ['MANUAL', 'AUTO']


def test_extract_options_or_separated_three_values():
    """Three 'or'-separated values."""
    options, cleaned = extract_options("center or top or bottom")
    assert options is not None
    assert len(options) == 3
    values = [o['value'] for o in options]
    assert values == ['center', 'top', 'bottom']


def test_float_prose_with_or_does_not_generate_enum_options():
    schema = generate_parameter_schema(
        'MIN_FORWARD_VELOCITY_THRESHOLD',
        0.2,
        'm/s - minimum velocity (important for fixed-wing or VTOL)',
        'MC_VELOCITY_CHASE.MIN_FORWARD_VELOCITY_THRESHOLD',
    )

    assert schema['type'] == 'float'
    assert schema['default'] == 0.2
    assert 'options' not in schema


# ---- Integer range inference ----

def test_infer_type_zero_integer():
    """Integer 0 should not be capped at max=100."""
    param_type, constraints = infer_type(0)
    assert param_type == 'integer'
    assert constraints['min'] == 0
    assert constraints['max'] == 10000  # wide range for 0/1 defaults


def test_infer_type_small_integer():
    """Small integer like 5 should get a reasonable range."""
    param_type, constraints = infer_type(5)
    assert param_type == 'integer'
    assert constraints['min'] == 0
    assert constraints['max'] == 100  # max(5*20, 100)


def test_infer_type_medium_integer():
    """Medium integer like 20 should get max = value * 5."""
    param_type, constraints = infer_type(20)
    assert param_type == 'integer'
    assert constraints['max'] == 1000  # max(20*5, 1000)


# ---- SCHEMA_OVERRIDES ----

def test_schema_overrides_applied():
    """SCHEMA_OVERRIDES should override auto-generated values."""
    schema = generate_parameter_schema(
        'FRAME_ROTATION_DEG', 0,
        description='Options: 0, 90, 180, 270',
        full_path='VideoSource.FRAME_ROTATION_DEG'
    )
    # Override should set min/max/options from SCHEMA_OVERRIDES
    assert schema['min'] == 0
    assert schema['max'] == 270
    assert schema['unit'] == 'deg'
    assert len(schema['options']) == 4
    opt_values = [o['value'] for o in schema['options']]
    assert opt_values == [0, 90, 180, 270]


def test_schema_overrides_tracker_type():
    """TRACKER_TYPE override should provide rich descriptions."""
    schema = generate_parameter_schema(
        'TRACKER_TYPE', 'botsort_reid',
        description='',
        full_path='SmartTracker.TRACKER_TYPE'
    )
    assert schema['options'] is not None
    assert len(schema['options']) == 4
    assert schema['options'][0]['value'] == 'bytetrack'
    assert 'description' in schema['options'][0]


def test_video_source_type_override_directly_defines_dashboard_options():
    """VIDEO_SOURCE_TYPE options should come from generator overrides, not hand-edited schema."""
    schema = generate_parameter_schema(
        'VIDEO_SOURCE_TYPE',
        'VIDEO_FILE',
        description='stale parsed comment',
        full_path='VideoSource.VIDEO_SOURCE_TYPE',
    )

    assert schema['description'] == 'Primary video input source type'
    values = [option['value'] for option in schema['options']]
    assert values == [
        'VIDEO_FILE',
        'USB_CAMERA',
        'RTSP_OPENCV',
        'RTSP_STREAM',
        'UDP_STREAM',
        'HTTP_STREAM',
        'CSI_CAMERA',
        'CUSTOM_GSTREAMER',
    ]


def test_video_file_eof_policy_schema_defines_explicit_options():
    """The dashboard selector and defaults must share the EOF policy contract."""
    schema = generate_parameter_schema(
        'VIDEO_FILE_EOF_POLICY',
        'LOOP',
        description='stale parsed comment',
        full_path='VideoSource.VIDEO_FILE_EOF_POLICY',
    )
    config_default = yaml.safe_load(
        (CONFIGS_DIR / "config_default.yaml").read_text(encoding="utf-8")
    )

    assert schema['default'] == 'LOOP'
    assert [option['value'] for option in schema['options']] == ['LOOP', 'STOP']
    assert config_default['VideoSource']['VIDEO_FILE_EOF_POLICY'] == 'LOOP'

    path_schema = generate_parameter_schema(
        'VIDEO_FILE_PATH',
        'resources/test4.mp4',
        description='misassociated neighboring comment',
        full_path='VideoSource.VIDEO_FILE_PATH',
    )
    assert path_schema['description'] == 'Path to the local video replay file'


def test_runtime_rate_schema_overrides_define_units_and_bounds():
    """Runtime cadence parameters should keep explicit units and safe bounds."""
    follower_schema = generate_parameter_schema(
        'FOLLOWER_DATA_REFRESH_RATE', 5.0,
        description='Telemetry refresh rate (Hz)',
        full_path='Follower.FOLLOWER_DATA_REFRESH_RATE'
    )
    setpoint_schema = generate_parameter_schema(
        'SETPOINT_PUBLISH_RATE_S', 0.1,
        description='SetpointSender monitor loop period (seconds)',
        full_path='Setpoint.SETPOINT_PUBLISH_RATE_S'
    )
    failure_threshold_schema = generate_parameter_schema(
        'OFFBOARD_COMMAND_FAILURE_THRESHOLD', 3,
        description='Consecutive publish failures before local fail-closed follow stop',
        full_path='Setpoint.OFFBOARD_COMMAND_FAILURE_THRESHOLD'
    )
    mavlink_retry_schema = generate_parameter_schema(
        'MAVLINK_REQUEST_RETRIES', 0,
        description='Additional retries after the first request attempt',
        full_path='MAVLink.MAVLINK_REQUEST_RETRIES'
    )

    assert follower_schema['type'] == 'float'
    assert follower_schema['default'] == 5.0
    assert follower_schema['unit'] == 'hz'
    assert follower_schema['min'] == 0.1
    assert setpoint_schema['unit'] == 's'
    assert setpoint_schema['min'] == 0.001
    assert 'monitor loop period' in setpoint_schema['description']
    assert failure_threshold_schema['type'] == 'integer'
    assert failure_threshold_schema['min'] == 1
    assert failure_threshold_schema['max'] == 100
    assert mavlink_retry_schema['type'] == 'integer'
    assert mavlink_retry_schema['max'] == 5


def test_checked_in_runtime_rate_schema_matches_defaults():
    """Checked-in defaults and generated schema must agree on PXE-0030 timing units."""
    config_default = yaml.safe_load((CONFIGS_DIR / "config_default.yaml").read_text(encoding="utf-8"))
    config_schema = yaml.safe_load((CONFIGS_DIR / "config_schema.yaml").read_text(encoding="utf-8"))

    follower_default = config_default["Follower"]["FOLLOWER_DATA_REFRESH_RATE"]
    follower_schema = config_schema["sections"]["Follower"]["parameters"]["FOLLOWER_DATA_REFRESH_RATE"]
    control_schema = config_schema["sections"]["Follower"]["parameters"]["General"]["properties"]["CONTROL_UPDATE_RATE"]
    setpoint_default = config_default["Setpoint"]["SETPOINT_PUBLISH_RATE_S"]
    setpoint_schema = config_schema["sections"]["Setpoint"]["parameters"]["SETPOINT_PUBLISH_RATE_S"]
    failure_threshold_default = config_default["Setpoint"]["OFFBOARD_COMMAND_FAILURE_THRESHOLD"]
    failure_threshold_schema = config_schema["sections"]["Setpoint"]["parameters"]["OFFBOARD_COMMAND_FAILURE_THRESHOLD"]
    mavlink_retry_schema = config_schema["sections"]["MAVLink"]["parameters"]["MAVLINK_REQUEST_RETRIES"]

    assert follower_default == 5.0
    assert follower_schema["type"] == "float"
    assert follower_schema["default"] == follower_default
    assert follower_schema["unit"] == "hz"
    assert follower_schema["min"] > 0.0
    assert follower_schema["max"] == 100.0
    assert "not MAVSDK Offboard publish cadence" in control_schema["description"]

    assert setpoint_default == 0.1
    assert setpoint_schema["default"] == setpoint_default
    assert setpoint_schema["unit"] == "s"
    assert setpoint_schema["min"] > 0.0
    assert setpoint_schema["max"] == 1.0
    assert setpoint_schema["reload_tier"] == "follower_restart"
    assert "monitor loop period" in setpoint_schema["description"]
    assert failure_threshold_default == 3
    assert failure_threshold_schema["type"] == "integer"
    assert failure_threshold_schema["default"] == failure_threshold_default
    assert failure_threshold_schema["min"] == 1
    assert failure_threshold_schema["max"] == 100
    assert failure_threshold_schema["reload_tier"] == "follower_restart"
    assert mavlink_retry_schema["type"] == "integer"
    assert mavlink_retry_schema["max"] == 5


# ---- Recommended ranges ----

def test_recommended_range_in_schema():
    """Recommended ranges should be applied from RECOMMENDED_RANGES dict."""
    schema = generate_parameter_schema(
        'SMART_TRACKER_CONFIDENCE_THRESHOLD', 0.3,
        description='Min detection confidence (0.0-1.0)',
        full_path='SmartTracker.SMART_TRACKER_CONFIDENCE_THRESHOLD'
    )
    assert schema.get('recommended_min') == 0.15
    assert schema.get('recommended_max') == 0.7


def test_recommended_range_from_bracket_notation():
    """[N..M] notation in comment should be extracted as recommended_min/max."""
    schema = generate_parameter_schema(
        'JPEG_QUALITY', 80,
        description='JPEG compression quality [50..95]',
        full_path='Streaming.JPEG_QUALITY'
    )
    assert schema.get('recommended_min') == 50.0
    assert schema.get('recommended_max') == 95.0


def test_recommended_range_bracket_three_dots():
    """[N...M] with three dots should also be parsed."""
    schema = generate_parameter_schema(
        'SOME_PARAM', 30,
        description='Frame rate target [15...60]',
        full_path='VideoSource.SOME_PARAM'
    )
    assert schema.get('recommended_min') == 15.0
    assert schema.get('recommended_max') == 60.0


# ---- Frame rotation end-to-end ----

def test_frame_rotation_schema_end_to_end():
    """FRAME_ROTATION_DEG should get strict preset options 0/90/180/270."""
    import yaml
    import pytest
    schema_path = os.path.join(PROJECT_ROOT, 'configs', 'config_schema.yaml')
    if not os.path.exists(schema_path):
        pytest.skip("config_schema.yaml not generated yet")

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = yaml.safe_load(f)

    param = schema['sections']['VideoSource']['parameters']['FRAME_ROTATION_DEG']
    assert param['type'] == 'integer'
    assert param['min'] == 0
    assert param['max'] == 270
    assert len(param['options']) == 4
    opt_values = [o['value'] for o in param['options']]
    assert opt_values == [0, 90, 180, 270]


def test_video_source_type_options_in_schema():
    """VIDEO_SOURCE_TYPE should expose source choices to the dashboard."""
    import yaml
    import pytest
    schema_path = os.path.join(PROJECT_ROOT, 'configs', 'config_schema.yaml')
    if not os.path.exists(schema_path):
        pytest.skip("config_schema.yaml not generated yet")

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = yaml.safe_load(f)

    param = schema['sections']['VideoSource']['parameters']['VIDEO_SOURCE_TYPE']
    assert param['type'] == 'string'
    assert param['description'] == 'Primary video input source type'
    values = [o['value'] for o in param['options']]
    assert values == [
        'VIDEO_FILE',
        'USB_CAMERA',
        'RTSP_OPENCV',
        'RTSP_STREAM',
        'UDP_STREAM',
        'HTTP_STREAM',
        'CSI_CAMERA',
        'CUSTOM_GSTREAMER',
    ]


def test_tracker_type_options_in_schema():
    """TRACKER_TYPE should have 4 options in generated schema."""
    import yaml
    import pytest
    schema_path = os.path.join(PROJECT_ROOT, 'configs', 'config_schema.yaml')
    if not os.path.exists(schema_path):
        pytest.skip("config_schema.yaml not generated yet")

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = yaml.safe_load(f)

    param = schema['sections']['SmartTracker']['parameters']['TRACKER_TYPE']
    assert param['options'] is not None
    assert len(param['options']) == 4
    values = [o['value'] for o in param['options']]
    assert 'bytetrack' in values
    assert 'botsort_reid' in values


# ---- extract_unit() tests ----

def test_extract_unit_false_positive_prevented():
    """Parenthetical with '=' should NOT be extracted as a unit."""
    assert extract_unit('Width in pixels (lower = less CPU)') == 'px'
    # ↑ 'px' comes from well-known keyword 'pixels', NOT from the parenthetical ✓
    # The parenthetical '(lower = less CPU)' is rejected by the = guard
    assert extract_unit('Some value (0 = disabled)') is None
    assert extract_unit('A flag (0 = off, 1 = on)') is None


def test_extract_unit_valid_parenthetical():
    """Short, unit-like parenthetical should be extracted."""
    assert extract_unit('Speed limit (m/s)') == 'm/s'
    assert extract_unit('Maximum bank angle (degrees)') == 'deg'  # normalised
    assert extract_unit('Frame rate (fps)') == 'fps'


def test_extract_unit_well_known_keywords():
    """Well-known unit keywords should be extracted from description body."""
    assert extract_unit('Distance threshold in m') == 'm'
    assert extract_unit('Interval in seconds') == 's'  # normalised from 'seconds'
    assert extract_unit('Width in pixels') == 'px'     # normalised from 'pixels'


def test_extract_unit_none_for_plain_description():
    """Plain description without unit keywords should return None."""
    assert extract_unit('Enable altitude hold mode') is None
    assert extract_unit('Number of consecutive frames') is None


# ---- parse_config_with_comments() end-to-end ----

def test_parse_config_reads_comments():
    """parse_config_with_comments should extract inline comments from config_default.yaml."""
    import pytest
    config_path = os.path.join(PROJECT_ROOT, 'configs', 'config_default.yaml')
    if not os.path.exists(config_path):
        pytest.skip("config_default.yaml not present")

    config, comments = parse_config_with_comments(config_path)

    # Config should have sections
    assert isinstance(config, dict)
    assert 'VideoSource' in config
    assert 'Safety' in config

    # Comments should be non-empty
    assert len(comments) > 0

    # At least some comments should be present for common keys
    # (not asserting specific text — comment content may change)
    video_comments = {k: v for k, v in comments.items() if k.startswith('VideoSource.')}
    assert len(video_comments) > 0, "Expected at least one VideoSource comment"


def test_parse_config_options_comment_extracted():
    """Comments with Options: pattern should be captured for later parsing."""
    import pytest
    config_path = os.path.join(PROJECT_ROOT, 'configs', 'config_default.yaml')
    if not os.path.exists(config_path):
        pytest.skip("config_default.yaml not present")

    config, comments = parse_config_with_comments(config_path)

    # TARGET_LOSS_ACTION should have an Options: comment
    # (present in multiple follower sections)
    options_comments = {
        k: v for k, v in comments.items()
        if 'Options:' in v and 'TARGET_LOSS_ACTION' in k
    }
    assert len(options_comments) > 0, "Expected Options: comment on TARGET_LOSS_ACTION"


# ---- config_validator.py tests ----

def _valid_safety_config():
    """Return the canonical complete safety fixture from checked-in defaults."""
    import yaml

    config_path = os.path.join(PROJECT_ROOT, 'configs', 'config_default.yaml')
    with open(config_path, 'r', encoding='utf-8') as config_file:
        config = yaml.safe_load(config_file)
    return {
        'Safety': config['Safety'],
        'VideoSource': config['VideoSource'],
    }


def test_validate_safety_config_passes_valid():
    """validate_safety_config should return True for a valid config."""
    from classes.config_validator import validate_safety_config

    config = _valid_safety_config()
    result = validate_safety_config(config)
    assert result is True


def test_validate_safety_config_fails_high_velocity():
    """MAX_VELOCITY > 30 m/s should fail validation."""
    from classes.config_validator import validate_safety_config

    config = _valid_safety_config()
    config['Safety']['GlobalLimits']['MAX_VELOCITY'] = 50.0
    result = validate_safety_config(config)
    assert result is False


def test_validate_safety_config_fails_invalid_altitude():
    """MIN_ALTITUDE > 100 should fail validation."""
    from classes.config_validator import validate_safety_config

    config = _valid_safety_config()
    config['Safety']['GlobalLimits']['MIN_ALTITUDE'] = 200.0
    result = validate_safety_config(config)
    assert result is False


@pytest.mark.parametrize('invalid_value', [None, '0.5', True, float('nan'), float('inf')])
def test_normalize_safety_config_rejects_null_coercive_and_nonfinite_limits(
    invalid_value,
):
    from classes.config_validator import normalize_safety_config

    config = _valid_safety_config()
    config['Safety']['GlobalLimits']['MAX_VELOCITY_FORWARD'] = invalid_value

    with pytest.raises((TypeError, ValueError)):
        normalize_safety_config(config, require_safety=True)


def test_normalize_safety_config_rejects_invalid_sparse_override_envelope():
    from classes.config_validator import normalize_safety_config

    config = _valid_safety_config()
    config['Safety']['FollowerOverrides']['MC_VELOCITY_CHASE'] = {
        'MIN_ALTITUDE': 50.0,
        'MAX_ALTITUDE': 40.0,
    }

    with pytest.raises(ValueError, match='invalid effective limits'):
        normalize_safety_config(config, require_safety=True)


def test_validate_safety_config_skips_missing_sections():
    """Missing Safety/VideoSource sections should not cause errors (returns True)."""
    from classes.config_validator import validate_safety_config

    # No Safety or VideoSource sections → nothing to validate → passes
    result = validate_safety_config({})
    assert result is True

    # Only unrelated sections → still passes
    result = validate_safety_config({'Tracking': {'SOME_KEY': True}})
    assert result is True


def test_validate_safety_config_passes_real_config():
    """Validation should pass against the actual config_default.yaml."""
    import yaml
    import pytest
    from classes.config_validator import validate_safety_config

    config_path = os.path.join(PROJECT_ROOT, 'configs', 'config_default.yaml')
    if not os.path.exists(config_path):
        pytest.skip("config_default.yaml not present")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    result = validate_safety_config(config)
    assert result is True, "config_default.yaml should pass safety validation"
