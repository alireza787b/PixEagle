"""
Tests for schema generation: option extraction, unit extraction, comment parsing,
Pydantic config validation, and end-to-end schema correctness.
"""

import os
import sys

# Add project root to import scripts module
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, PROJECT_ROOT)

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

def test_validate_safety_config_passes_valid():
    """validate_safety_config should return True for a valid config."""
    from classes.config_validator import validate_safety_config

    # Field names match actual config_default.yaml Safety.GlobalLimits
    config = {
        'Safety': {
            'GlobalLimits': {
                'MAX_VELOCITY': 10.0,
                'MAX_VELOCITY_FORWARD': 5.0,
                'MAX_VELOCITY_LATERAL': 5.0,
                'MAX_YAW_RATE': 45.0,
                'MAX_ALTITUDE': 120.0,
                'MIN_ALTITUDE': 0.5,
            },
            'FollowerOverrides': {},
        },
        'VideoSource': {
            'VIDEO_SOURCE_TYPE': 'USB',
            'CAPTURE_FPS': 30.0,
            'CAPTURE_WIDTH': 1280,
            'CAPTURE_HEIGHT': 720,
        },
    }
    result = validate_safety_config(config)
    assert result is True


def test_validate_safety_config_fails_high_velocity():
    """MAX_VELOCITY > 30 m/s should fail validation."""
    from classes.config_validator import validate_safety_config

    config = {
        'Safety': {
            'GlobalLimits': {
                'MAX_VELOCITY': 50.0,  # Exceeds 30.0 m/s hard limit
                'MAX_YAW_RATE': 45.0,
                'MAX_ALTITUDE': 120.0,
                'MIN_ALTITUDE': 0.5,
            },
        },
    }
    result = validate_safety_config(config)
    assert result is False


def test_validate_safety_config_fails_invalid_altitude():
    """MIN_ALTITUDE > 100 should fail validation."""
    from classes.config_validator import validate_safety_config

    config = {
        'Safety': {
            'GlobalLimits': {
                'MAX_VELOCITY': 10.0,
                'MAX_YAW_RATE': 45.0,
                'MAX_ALTITUDE': 120.0,
                'MIN_ALTITUDE': 200.0,   # Exceeds 100.0 ceiling
            },
        },
    }
    result = validate_safety_config(config)
    assert result is False


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
