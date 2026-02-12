"""
Tests for schema generation option extraction behavior.
"""

import os
import sys

# Add project root to import scripts module
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, PROJECT_ROOT)

from scripts.generate_schema import (  # noqa: E402
    extract_options,
    infer_type,
    generate_parameter_schema,
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


# ---- Frame rotation end-to-end ----

def test_frame_rotation_schema_end_to_end():
    """FRAME_ROTATION_DEG should get strict preset options 0/90/180/270."""
    import yaml
    schema_path = os.path.join(PROJECT_ROOT, 'configs', 'config_schema.yaml')
    if not os.path.exists(schema_path):
        return  # Skip if schema not generated yet

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
    schema_path = os.path.join(PROJECT_ROOT, 'configs', 'config_schema.yaml')
    if not os.path.exists(schema_path):
        return  # Skip if schema not generated yet

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = yaml.safe_load(f)

    param = schema['sections']['SmartTracker']['parameters']['TRACKER_TYPE']
    assert param['options'] is not None
    assert len(param['options']) == 4
    values = [o['value'] for o in param['options']]
    assert 'bytetrack' in values
    assert 'botsort_reid' in values
