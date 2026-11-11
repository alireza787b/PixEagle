# tests/unit/drone_interface/test_setpoint_handler.py
"""
Unit tests for SetpointHandler.

Tests schema-driven command field management:
- Schema loading and caching
- Profile initialization
- Field get/set operations
- Type validation and range clamping
- Control type extraction
- Profile switching
"""

import pytest
import math
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import yaml
import os


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_schema():
    """Create a mock schema for testing."""
    return {
        'schema_version': '2.5.0',
        'follower_profiles': {
            'mc_velocity_chase': {
                'control_type': 'velocity_body_offboard',
                'airframe_phase': 'multicopter',
                'live_qualified_phases': ['multicopter'],
                'display_name': 'MC Velocity Chase',
                'description': 'Body-frame velocity control',
                'required_fields': ['vel_body_fwd', 'vel_body_right', 'vel_body_down', 'yawspeed_deg_s']
            },
            'fw_attitude_rate': {
                'control_type': 'attitude_rate',
                'airframe_phase': 'fixed_wing',
                'live_qualified_phases': [],
                'display_name': 'FW Attitude Rate',
                'description': 'Angular rate control',
                'required_fields': ['rollspeed_deg_s', 'pitchspeed_deg_s', 'yawspeed_deg_s', 'thrust']
            },
            'mc_velocity_position': {
                'airframe_phase': 'multicopter',
                'live_qualified_phases': ['multicopter'],
                'control_type': 'velocity_body_offboard',
                'display_name': 'MC Velocity Position',
                'description': 'Position-based velocity control',
                'required_fields': ['vel_body_fwd', 'vel_body_right', 'vel_body_down', 'yawspeed_deg_s']
            }
        },
        'command_fields': {
            'vel_body_fwd': {
                'type': 'float',
                'unit': 'm/s',
                'description': 'Forward velocity',
                'default': 0.0,
                'clamp': True
            },
            'vel_body_right': {
                'type': 'float',
                'unit': 'm/s',
                'description': 'Right velocity',
                'default': 0.0,
                'clamp': True
            },
            'vel_body_down': {
                'type': 'float',
                'unit': 'm/s',
                'description': 'Down velocity',
                'default': 0.0,
                'clamp': True
            },
            'yawspeed_deg_s': {
                'type': 'float',
                'unit': 'deg/s',
                'description': 'Yaw rate',
                'default': 0.0,
                'clamp': True
            },
            'rollspeed_deg_s': {
                'type': 'float',
                'unit': 'deg/s',
                'description': 'Roll rate',
                'default': 0.0,
                'clamp': True
            },
            'pitchspeed_deg_s': {
                'type': 'float',
                'unit': 'deg/s',
                'description': 'Pitch rate',
                'default': 0.0,
                'clamp': True
            },
            'thrust': {
                'type': 'float',
                'unit': 'normalized',
                'description': 'Thrust 0-1',
                'default': 0.5,
                'clamp': True,
                'limits': {'min': 0.0, 'max': 1.0}
            }
        },
        'control_types': {
            'velocity_body_offboard': {
                'transport': 'mavsdk',
                'mavsdk_method': 'set_velocity_body',
            },
            'attitude_rate': {
                'transport': 'mavsdk',
                'mavsdk_method': 'set_attitude_rate',
            },
        },
        'validation_rules': {
            'attitude_rate_exclusive': {
                'fields': ['rollspeed_deg_s', 'pitchspeed_deg_s', 'thrust'],
                'allowed_control_types': ['attitude_rate'],
                'description': 'Attitude rate fields only with attitude_rate control type'
            }
        }
    }


@pytest.fixture
def mock_parameters():
    """Mock Parameters class for testing."""
    mock_params = MagicMock()
    mock_params.get_effective_limit = MagicMock(side_effect=lambda name, follower_name=None: {
        'MAX_VELOCITY_FORWARD': 8.0,
        'MAX_VELOCITY_LATERAL': 5.0,
        'MAX_VELOCITY_VERTICAL': 3.0,
        'MAX_YAW_RATE': 45.0,
        'MAX_PITCH_RATE': 30.0,
        'MAX_ROLL_RATE': 20.0,
    }.get(name, 10.0))
    return mock_params


@pytest.fixture
def setpoint_handler(mock_schema, mock_parameters):
    """Create a SetpointHandler instance for testing.

    Uses yield instead of return to keep patch contexts active during test execution.
    This ensures mock_parameters is used when set_field() calls Parameters.get_effective_limit().
    """
    with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
        with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
            with patch('classes.parameters.Parameters', mock_parameters):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('mc_velocity_chase')
                yield handler  # Keep patches active during test


# ============================================================================
# Test Classes
# ============================================================================

class TestSetpointHandlerInitialization:
    """Tests for SetpointHandler initialization."""

    def test_init_with_valid_profile(self, mock_schema, mock_parameters):
        """Test initialization with valid profile name."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('mc_velocity_chase')

                assert handler.profile_name == 'mc_velocity_chase'
                assert 'vel_body_fwd' in handler.fields
                assert 'yawspeed_deg_s' in handler.fields

    def test_init_with_normalized_profile_name(self, mock_schema, mock_parameters):
        """Test that profile names are normalized correctly."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema

                # Test with spaces and mixed case
                handler = SetpointHandler('MC Velocity Chase')
                assert handler.profile_name == 'mc_velocity_chase'

    def test_init_with_invalid_profile_raises_error(self, mock_schema, mock_parameters):
        """Test that invalid profile raises ValueError."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema

                with pytest.raises(ValueError, match="not found"):
                    SetpointHandler('nonexistent_profile')

    def test_fields_initialized_with_defaults(self, setpoint_handler):
        """Test that fields are initialized with default values."""
        assert setpoint_handler.fields['vel_body_fwd'] == 0.0
        assert setpoint_handler.fields['vel_body_right'] == 0.0
        assert setpoint_handler.fields['vel_body_down'] == 0.0
        assert setpoint_handler.fields['yawspeed_deg_s'] == 0.0


class TestSetpointHandlerProfileNormalization:
    """Tests for profile name normalization."""

    def test_normalize_lowercase(self):
        """Test lowercase conversion."""
        from classes.setpoint_handler import SetpointHandler
        assert SetpointHandler.normalize_profile_name('MC_VELOCITY_CHASE') == 'mc_velocity_chase'

    def test_normalize_spaces_to_underscores(self):
        """Test space to underscore conversion."""
        from classes.setpoint_handler import SetpointHandler
        assert SetpointHandler.normalize_profile_name('MC Velocity Chase') == 'mc_velocity_chase'

    def test_normalize_already_normalized(self):
        """Test that already normalized names pass through."""
        from classes.setpoint_handler import SetpointHandler
        assert SetpointHandler.normalize_profile_name('mc_velocity_chase') == 'mc_velocity_chase'


class TestSetpointHandlerFieldOperations:
    """Tests for field get/set operations."""

    def test_set_field_valid(self, setpoint_handler, mock_parameters):
        """Test setting a valid field value."""
        setpoint_handler.set_field('vel_body_fwd', 2.5)
        assert setpoint_handler.fields['vel_body_fwd'] == 2.5

    def test_set_field_invalid_name_raises_error(self, setpoint_handler):
        """Test that setting invalid field name raises ValueError."""
        with pytest.raises(ValueError, match="not valid for profile"):
            setpoint_handler.set_field('nonexistent_field', 1.0)

    def test_set_field_non_numeric_raises_error(self, setpoint_handler):
        """Test that non-numeric value raises ValueError."""
        with pytest.raises(ValueError, match="Python int or float"):
            setpoint_handler.set_field('vel_body_fwd', 'not_a_number')

    def test_set_field_converts_int_to_float(self, setpoint_handler, mock_parameters):
        """Test that integer values are converted to float."""
        setpoint_handler.set_field('vel_body_fwd', 3)
        assert setpoint_handler.fields['vel_body_fwd'] == 3.0
        assert isinstance(setpoint_handler.fields['vel_body_fwd'], float)

    def test_get_fields_returns_copy(self, setpoint_handler):
        """Test that get_fields returns a copy, not the original."""
        fields = setpoint_handler.get_fields()
        fields['vel_body_fwd'] = 999.0
        assert setpoint_handler.fields['vel_body_fwd'] != 999.0

    def test_get_fields_contains_all_profile_fields(self, setpoint_handler):
        """Test that all profile fields are returned."""
        fields = setpoint_handler.get_fields()
        assert 'vel_body_fwd' in fields
        assert 'vel_body_right' in fields
        assert 'vel_body_down' in fields
        assert 'yawspeed_deg_s' in fields


class TestSetpointHandlerAtomicFields:
    """Tests for atomic command-intent field updates."""

    def test_set_fields_commits_only_after_all_fields_validate(self, setpoint_handler):
        """An invalid field in a command intent must leave old setpoints intact."""
        setpoint_handler.set_fields(
            {
                'vel_body_fwd': 1.0,
                'vel_body_right': 2.0,
                'vel_body_down': -0.5,
                'yawspeed_deg_s': 10.0,
            },
            source='test',
            reason='baseline',
        )
        before = setpoint_handler.get_fields()

        with pytest.raises(ValueError, match="must be finite"):
            setpoint_handler.set_fields(
                {
                    'vel_body_fwd': 3.0,
                    'vel_body_right': float('nan'),
                    'vel_body_down': 0.0,
                    'yawspeed_deg_s': 0.0,
                },
                source='test',
                reason='invalid_nan',
            )

        assert setpoint_handler.get_fields() == before

    def test_set_fields_requires_complete_profile_by_default(self, setpoint_handler):
        """Missing fields are rejected so old command fields cannot carry over."""
        before = setpoint_handler.get_fields()

        with pytest.raises(ValueError, match="missing fields"):
            setpoint_handler.set_fields(
                {
                    'vel_body_fwd': 1.0,
                    'vel_body_right': 0.0,
                    'vel_body_down': 0.0,
                },
                source='test',
                reason='missing_yaw',
            )

        assert setpoint_handler.get_fields() == before

    def test_set_fields_returns_command_intent_metadata(self, setpoint_handler):
        """Accepted atomic commands expose a typed command intent for telemetry."""
        intent = setpoint_handler.set_fields(
            {
                'vel_body_fwd': 1.0,
                'vel_body_right': 0.5,
                'vel_body_down': -0.25,
                'yawspeed_deg_s': 5.0,
            },
            source='unit_test',
            reason='metadata',
        )

        assert intent.profile_name == 'mc_velocity_chase'
        assert intent.control_type == 'velocity_body_offboard'
        assert intent.source == 'unit_test'
        assert intent.reason == 'metadata'
        assert intent.fields == setpoint_handler.get_fields()
        assert setpoint_handler.get_last_command_intent() == intent


class TestSetpointHandlerClamping:
    """Tests for value clamping and limit enforcement."""

    def test_velocity_clamped_to_max(self, setpoint_handler, mock_parameters):
        """Test that velocity is clamped to maximum limit."""
        # MAX_VELOCITY_FORWARD is 8.0
        setpoint_handler.set_field('vel_body_fwd', 15.0)
        assert setpoint_handler.fields['vel_body_fwd'] == 8.0

    def test_velocity_clamped_to_min(self, setpoint_handler, mock_parameters):
        """Test that velocity is clamped to minimum limit (negative max)."""
        # MAX_VELOCITY_FORWARD is 8.0, so min is -8.0
        setpoint_handler.set_field('vel_body_fwd', -15.0)
        assert setpoint_handler.fields['vel_body_fwd'] == -8.0

    def test_yaw_rate_clamped(self, setpoint_handler, mock_parameters):
        """Test that yaw rate is clamped."""
        # MAX_YAW_RATE is 45.0
        setpoint_handler.set_field('yawspeed_deg_s', 100.0)
        assert setpoint_handler.fields['yawspeed_deg_s'] == 45.0

    def test_pitch_and_roll_use_distinct_rate_limits(self, mock_schema, mock_parameters):
        """Pitch/roll limits must not silently reuse MAX_YAW_RATE."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    from classes.setpoint_handler import SetpointHandler

                    SetpointHandler._schema_cache = mock_schema
                    handler = SetpointHandler('fw_attitude_rate')

                    handler.set_field('yawspeed_deg_s', 100.0)
                    handler.set_field('pitchspeed_deg_s', 100.0)
                    handler.set_field('rollspeed_deg_s', 100.0)

                    assert handler.fields['yawspeed_deg_s'] == 45.0
                    assert handler.fields['pitchspeed_deg_s'] == 30.0
                    assert handler.fields['rollspeed_deg_s'] == 20.0

    def test_runtime_mapping_matches_safety_types(self):
        """SetpointHandler must use the shared safety field mapping."""
        from classes.safety_types import FIELD_LIMIT_MAPPING
        from classes.setpoint_handler import SetpointHandler

        for field_name in [
            'vel_body_fwd',
            'vel_body_right',
            'vel_body_down',
            'yawspeed_deg_s',
            'pitchspeed_deg_s',
            'rollspeed_deg_s',
        ]:
            assert SetpointHandler._FIELD_TO_LIMIT_NAME[field_name] == FIELD_LIMIT_MAPPING[field_name]

        for retired_field in ('vel_x', 'vel_y', 'vel_z', 'yaw_rate', 'yaw_speed_deg_s'):
            assert retired_field not in SetpointHandler._FIELD_TO_LIMIT_NAME

    def test_non_finite_values_are_rejected(self, setpoint_handler):
        """SetpointHandler must not store NaN/Inf command values."""
        with pytest.raises(ValueError, match="finite"):
            setpoint_handler.set_field('vel_body_fwd', float('nan'))

    @pytest.mark.parametrize('value', [True, False, '0.25'])
    def test_declared_float_rejects_bool_and_numeric_strings(
        self,
        setpoint_handler,
        value,
    ):
        """Command fields accept Python numbers, never coercible lookalikes."""
        with pytest.raises(ValueError, match="Python int or float"):
            setpoint_handler.set_field('vel_body_fwd', value)

    def test_lateral_velocity_uses_lateral_limit(self, setpoint_handler, mock_parameters):
        """Test that lateral velocity uses its own limit."""
        # MAX_VELOCITY_LATERAL is 5.0
        setpoint_handler.set_field('vel_body_right', 10.0)
        assert setpoint_handler.fields['vel_body_right'] == 5.0

    def test_vertical_velocity_uses_vertical_limit(self, setpoint_handler, mock_parameters):
        """Test that vertical velocity uses its own limit."""
        # MAX_VELOCITY_VERTICAL is 3.0
        setpoint_handler.set_field('vel_body_down', 6.0)
        assert setpoint_handler.fields['vel_body_down'] == 3.0

    def test_value_within_limits_not_clamped(self, setpoint_handler, mock_parameters):
        """Test that values within limits are not modified."""
        setpoint_handler.set_field('vel_body_fwd', 2.5)
        assert setpoint_handler.fields['vel_body_fwd'] == 2.5


class TestSetpointHandlerThrustLimits:
    """Tests for thrust field with schema-based limits."""

    def test_thrust_clamped_to_max(self, mock_schema, mock_parameters):
        """Test that thrust is clamped to 1.0."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('fw_attitude_rate')

                handler.set_field('thrust', 1.5)
                assert handler.fields['thrust'] == 1.0

    def test_thrust_clamped_to_min(self, mock_schema, mock_parameters):
        """Test that thrust is clamped to 0.0."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('fw_attitude_rate')

                handler.set_field('thrust', -0.5)
                assert handler.fields['thrust'] == 0.0

    def test_thrust_default_value(self, mock_schema, mock_parameters):
        """Test that thrust has correct default value."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('fw_attitude_rate')

                assert handler.fields['thrust'] == 0.5


class TestSetpointHandlerControlType:
    """Tests for control type retrieval."""

    def test_get_control_type_velocity_body_offboard(self, setpoint_handler):
        """Test control type for velocity offboard profile."""
        assert setpoint_handler.get_control_type() == 'velocity_body_offboard'

    def test_get_control_type_attitude_rate(self, mock_schema, mock_parameters):
        """Test control type for attitude rate profile."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('fw_attitude_rate')

                assert handler.get_control_type() == 'attitude_rate'


class TestSetpointHandlerDisplayName:
    """Tests for display name retrieval."""

    def test_get_display_name(self, setpoint_handler):
        """Test display name retrieval."""
        assert setpoint_handler.get_display_name() == 'MC Velocity Chase'

    def test_get_display_name_attitude_rate(self, mock_schema, mock_parameters):
        """Test display name for attitude rate profile."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('fw_attitude_rate')

                assert handler.get_display_name() == 'FW Attitude Rate'


class TestSetpointHandlerReset:
    """Tests for resetting setpoints."""

    def test_reset_setpoints_restores_defaults(self, setpoint_handler, mock_parameters):
        """Test that reset restores default values."""
        # Set some values
        setpoint_handler.set_field('vel_body_fwd', 5.0)
        setpoint_handler.set_field('yawspeed_deg_s', 30.0)

        # Reset
        setpoint_handler.reset_setpoints()

        # Check defaults restored
        assert setpoint_handler.fields['vel_body_fwd'] == 0.0
        assert setpoint_handler.fields['yawspeed_deg_s'] == 0.0

    def test_configured_fallback_defaults_replace_schema_default(self, setpoint_handler):
        """Runtime config may provide a validated per-profile fallback value."""
        configured = setpoint_handler.configure_fallback_defaults(
            {'vel_body_fwd': 1.25},
            source='TEST_PROFILE.HOLD_SPEED',
        )
        setpoint_handler.set_field('vel_body_fwd', 3.0)

        setpoint_handler.reset_setpoints()

        assert configured['vel_body_fwd'] == 1.25
        assert setpoint_handler.fields['vel_body_fwd'] == 1.25
        assert setpoint_handler.get_fallback_default_sources()['vel_body_fwd'] == (
            'TEST_PROFILE.HOLD_SPEED'
        )

    def test_configured_fallback_defaults_are_atomic(self, setpoint_handler):
        """An invalid field must not partially replace existing fallback values."""
        before = setpoint_handler.get_fallback_defaults()

        with pytest.raises(ValueError):
            setpoint_handler.configure_fallback_defaults(
                {'vel_body_fwd': 1.0, 'not_a_command_field': 2.0},
                source='test',
            )

        assert setpoint_handler.get_fallback_defaults() == before

    def test_reset_invalidates_last_command_intent(self, setpoint_handler):
        setpoint_handler.set_fields(
            {
                'vel_body_fwd': 1.0,
                'vel_body_right': 0.0,
                'vel_body_down': 0.0,
                'yawspeed_deg_s': 0.0,
            },
            source='test',
        )

        setpoint_handler.reset_setpoints()

        assert setpoint_handler.get_last_command_intent() is None


class TestFollowerCommandSchemaContract:
    """Adversarial checks for the one runtime/evidence command contract."""

    @staticmethod
    def _canonical_schema():
        path = Path(__file__).resolve().parents[3] / 'configs' / 'follower_commands.yaml'
        return yaml.safe_load(path.read_text(encoding='utf-8'))

    def test_canonical_schema_loads_and_exposes_dispatch_metadata(self):
        from classes.setpoint_handler import SetpointHandler

        path = Path(__file__).resolve().parents[3] / 'configs' / 'follower_commands.yaml'
        contract = SetpointHandler.load_and_validate_schema(path)

        assert contract['schema_version'] == '2.5.0'
        assert contract['removed_profile_aliases']['mc_velocity'] == 'mc_velocity_chase'
        assert contract['control_types']['velocity_body_offboard']['mavsdk_method'] == (
            'set_velocity_body'
        )

    @pytest.mark.parametrize(
        'mutate,match',
        [
            (
                lambda schema: schema['follower_profiles']['mc_velocity_chase'].__setitem__('family', []),
                'family is invalid',
            ),
            (
                lambda schema: schema['follower_profiles']['mc_velocity_chase'].__setitem__('visibility', 'always'),
                'visibility is invalid',
            ),
            (
                lambda schema: schema.__setitem__('schema_version', '3.0.0'),
                'unsupported follower command schema_version',
            ),
            (
                lambda schema: schema.__setitem__('schema_version', '2.3.0'),
                'unsupported follower command schema_version',
            ),
            (
                lambda schema: schema['command_fields']['thrust'].__setitem__(
                    'default', float('nan')
                ),
                'must be finite',
            ),
            (
                lambda schema: schema['follower_profiles']['mc_velocity_chase'].__setitem__(
                    'required_tracker_data', ['NOT_A_TRACKER_TYPE']
                ),
                'unknown TrackerDataType',
            ),
            (
                lambda schema: schema['follower_profiles']['mc_velocity_chase'].__setitem__(
                    'optional_fields', ['vel_body_right']
                ),
                'optional_fields is unsupported',
            ),
            (
                lambda schema: schema['control_types']['attitude_rate'].pop('mavsdk_method'),
                'mavsdk_method must be a non-empty string',
            ),
            (
                lambda schema: schema['command_fields']['vel_body_fwd'].__setitem__(
                    'limit_name', 'MAX_VELOCITY_FORWARD'
                ),
                'unsupported metadata',
            ),
            *[(lambda schema, bad=bad: schema['follower_profiles']['gm_velocity_vector'].__setitem__(
                'native_phase_contracts', bad), 'native_phase_contracts is invalid')
              for bad in ('fixed_wing', ['fixed_wing', 'fixed_wing'], ['unknown'], [{}], [True])],
            (
                lambda schema: schema.__setitem__('schema_version', '2.4.0'),
                'unsupported follower command schema_version',
            ),
            (
                lambda schema: schema['follower_profiles']['mc_velocity_chase'].pop('live_qualified_phases'),
                'live_qualified_phases',
            ),
            *[(lambda schema, bad=bad: schema['follower_profiles']['mc_velocity_chase'].__setitem__(
                'live_qualified_phases', bad), 'live_qualified_phases')
              for bad in (None, 'multicopter', ['multicopter', 'multicopter'], ['fixed_wing'], ['unknown'], [True], [{}])],
        ],
    )
    def test_complete_schema_validation_fails_closed(self, mutate, match):
        from classes.setpoint_handler import validate_follower_command_schema

        schema = deepcopy(self._canonical_schema())
        mutate(schema)

        with pytest.raises(ValueError, match=match):
            validate_follower_command_schema(schema)

    @pytest.mark.parametrize('bad_value', [True, '0.25'])
    def test_shared_intent_contract_rejects_coercible_values(self, bad_value):
        from classes.setpoint_handler import command_intent_contract_errors

        contract = self._canonical_schema()
        intent = {
            'profile_name': 'mc_velocity_chase',
            'control_type': 'velocity_body_offboard',
            'fields': {
                'vel_body_fwd': bad_value,
                'vel_body_right': 0.0,
                'vel_body_down': 0.0,
                'yawspeed_deg_s': 0.0,
            },
        }

        errors = command_intent_contract_errors(intent, contract)

        assert any('Python int or float' in error for error in errors)


@pytest.fixture
def native_schema():
    """Native-only fixture; the shipped catalog retains its eight profiles."""
    from classes.setpoint_handler import validate_follower_command_schema

    schema = TestFollowerCommandSchemaContract._canonical_schema()
    profile = deepcopy(schema['follower_profiles']['fw_attitude_rate'])
    profile.update(
        control_type='fixed_wing_external',
        required_fields=[],
        display_name='Fixture Native FW',
    )
    schema['follower_profiles']['fixture_native_fw'] = profile
    schema['ui_config']['profile_display_order'].append('fixture_native_fw')
    return validate_follower_command_schema(schema)


@pytest.fixture
def native_handler(native_schema):
    from classes.setpoint_handler import SetpointHandler

    with patch.object(SetpointHandler, '_schema_cache', native_schema):
        yield SetpointHandler('fixture_native_fw')


def native_intent(**changes):
    from classes.aircraft_state import AircraftBinding, GuidanceSessionIdentity
    from classes.command_intent import CommandIntent

    values = {
        'profile_name': 'fixture_native_fw',
        'control_type': 'fixed_wing_external',
        'fields': {'course_rad': 0.25, 'equivalent_airspeed_m_s': 18.0, 'height_rate_m_s': -1.0},
        'source': 'native_contract_test',
        'guidance_identity': GuidanceSessionIdentity('follow-a', AircraftBinding('aircraft-a', 'connection-a', 1), 1),
    }
    values.update(changes)
    return CommandIntent(**values)


class TestNativeFollowerCommandSchema:
    def test_canonical_native_contract_is_dormant_and_has_no_scalar_defaults(self):
        from classes.fixed_wing_vector_guidance import FixedWingCommand

        schema = TestFollowerCommandSchemaContract._canonical_schema()
        native = schema['control_types']['fixed_wing_external']
        assert native['transport'] == 'px4_native'
        assert 'mavsdk_method' not in native
        assert {name: frozenset(fields) for name, fields in native['field_variants'].items()} == (
            FixedWingCommand.field_variants()
        )
        assert not set().union(*FixedWingCommand.field_variants().values()) & set(schema['command_fields'])
        assert len(schema['follower_profiles']) == 8
        assert all(profile['required_fields'] for profile in schema['follower_profiles'].values())
        assert all(profile['control_type'] != 'fixed_wing_external' for profile in schema['follower_profiles'].values())

    @pytest.mark.parametrize('mutate,match', [
        (lambda schema: schema['control_types']['fixed_wing_external'].__setitem__('mavsdk_method', 'set_velocity_body'),
         'cannot declare a MAVSDK method'),
        (lambda schema: schema['control_types']['fixed_wing_external'].__setitem__('transport', 'unknown'),
         'transport must be mavsdk or px4_native'),
        (lambda schema: schema['control_types']['velocity_body_offboard'].pop('transport'),
         'transport must be mavsdk or px4_native'),
        (lambda schema: schema['control_types']['velocity_body_offboard'].__setitem__('field_variants', {}),
         'field_variants requires px4_native'),
        (lambda schema: schema['control_types']['fixed_wing_external'].pop('field_variants'),
         'field_variants must match FixedWingCommand'),
        (lambda schema: schema['control_types']['fixed_wing_external']['field_variants'].__setitem__('extra', []),
         'field_variants must match FixedWingCommand'),
        (lambda schema: schema['control_types']['fixed_wing_external']['field_variants'].__setitem__('height_rate', ['course_rad']),
         'must match FixedWingCommand'),
        (lambda schema: schema['control_types']['fixed_wing_external']['field_variants'].__setitem__('height_rate', ['course_rad'] * 3),
         'must not contain duplicates'),
        (lambda schema: schema['control_types']['fixed_wing_external']['field_variants'].__setitem__('height_rate', [' course_rad', 'equivalent_airspeed_m_s', 'height_rate_m_s']),
         'must match FixedWingCommand'),
        (lambda schema: schema['follower_profiles']['fixture_native_fw'].__setitem__('required_fields', ['vel_body_fwd']),
         'native FW profiles require empty required_fields'),
        (lambda schema: schema['follower_profiles']['fixture_native_fw'].__setitem__('airframe_phase', 'multicopter'),
         'fixed_wing airframe_phase'),
        (lambda schema: schema['follower_profiles']['mc_velocity_chase'].__setitem__('required_fields', []),
         'required_fields must not be empty'),
        (lambda schema: schema['command_fields'].__setitem__('course_rad', deepcopy(schema['command_fields']['vel_body_fwd'])),
         'native command fields must not declare scalar defaults'),
    ])
    def test_native_metadata_fails_closed(self, native_schema, mutate, match):
        from classes.setpoint_handler import validate_follower_command_schema

        mutate(native_schema)
        with pytest.raises(ValueError, match=match):
            validate_follower_command_schema(native_schema)

    def test_native_evidence_contract_uses_supplied_session_identity(self, native_schema):
        from dataclasses import asdict
        from classes.setpoint_handler import command_intent_contract_errors

        intent = asdict(native_intent())
        assert command_intent_contract_errors(intent, native_schema) == []
        intent['fields']['height_rate_m_s'] = math.nan
        assert any('height_rate_invalid' in error for error in command_intent_contract_errors(intent, native_schema))
        intent['fields']['height_rate_m_s'] = 0
        intent.pop('guidance_identity')
        assert any('GuidanceSessionIdentity' in error for error in command_intent_contract_errors(intent, native_schema))

    @pytest.mark.parametrize('identity', [None, {}, {'binding': None}, {'binding': {}, 'unexpected': 1}])
    def test_native_evidence_identity_fails_closed(self, native_schema, identity):
        from dataclasses import asdict
        from classes.setpoint_handler import command_intent_contract_errors

        intent = asdict(native_intent())
        intent['guidance_identity'] = identity
        assert command_intent_contract_errors(intent, native_schema)


class TestNativeSetpointHandler:
    def test_initial_state_has_no_command_or_fallback(self, native_handler):
        from classes.fixed_wing_vector_guidance import FixedWingCommand

        assert native_handler.get_fields() == {}
        assert native_handler.get_last_command_intent() is None
        assert native_handler.get_transport() == 'px4_native'
        assert native_handler.get_allowed_field_variants() == FixedWingCommand.field_variants()
        assert native_handler.validate_profile_consistency()

    @pytest.mark.parametrize('method,args,kwargs', [
        ('set_field', ('course_rad', 1.0), {}),
        ('set_fields', ({},), {}),
        ('configure_fallback_defaults', ({'course_rad': 1.0},), {'source': 'test'}),
        ('get_fallback_defaults', (), {}),
        ('get_fallback_default_sources', (), {}),
        ('get_mavsdk_dispatch_method', (), {}),
    ])
    def test_scalar_fallback_and_mavsdk_apis_refuse_native(self, native_handler, method, args, kwargs):
        with pytest.raises(ValueError, match='native profiles require|does not use MAVSDK'):
            getattr(native_handler, method)(*args, **kwargs)
        assert native_handler.get_fields() == {}
        assert native_handler.get_last_command_intent() is None

    def test_variants_replace_current_fields_and_reset_clears_them(self, native_handler):
        first = native_intent()
        accepted = native_handler.set_native_intent(first)
        assert accepted == first
        assert accepted.guidance_identity is first.guidance_identity
        assert native_handler.get_fields() == first.fields

        altitude = native_intent(fields={'course_rad': -.5, 'equivalent_airspeed_m_s': 21.0, 'altitude_amsl_m': 550.0})
        native_handler.set_native_intent(altitude)
        assert native_handler.get_fields() == altitude.fields
        assert 'height_rate_m_s' not in native_handler.get_fields()
        native_handler.reset_setpoints()
        assert native_handler.get_fields() == {}
        assert native_handler.get_last_command_intent() is None
        assert set(native_handler.get_allowed_field_variants()) == {'height_rate', 'altitude'}

    def test_caller_mutation_does_not_change_accepted_snapshot(self, native_handler):
        intent = native_intent()
        accepted = native_handler.set_native_intent(intent)
        intent.fields['course_rad'] = math.nan
        assert accepted.fields['course_rad'] == .25
        assert native_handler.get_fields()['course_rad'] == .25
        metadata = native_handler.get_control_type_metadata('fixed_wing_external')
        metadata['field_variants']['height_rate'].clear()
        assert len(native_handler.get_allowed_field_variants()['height_rate']) == 3

    def test_unavailable_fallback_read_does_not_invalidate_native_intent(self, native_handler):
        accepted = native_handler.set_native_intent(native_intent())
        with pytest.raises(ValueError):
            native_handler.get_fallback_defaults()
        assert native_handler.get_last_command_intent() == accepted

    @pytest.mark.parametrize('changes', [
        {'profile_name': 'gm_velocity_vector'},
        {'control_type': 'velocity_body_offboard'},
        {'guidance_identity': None},
        {'guidance_identity': {'follow_session_id': 'follow-a'}},
        {'fields': {}},
        {'fields': None},
        {'fields': {'course_rad': 0, 'equivalent_airspeed_m_s': 20}},
        {'fields': {'course_rad': 0, 'equivalent_airspeed_m_s': 20, 'height_rate_m_s': 0, 'altitude_amsl_m': 550}},
        {'fields': {'course_rad': 0, 'equivalent_airspeed_m_s': 20, 'height_rate_m_s': 0, 'vel_body_fwd': 1}},
        *[{'fields': {'course_rad': value, 'equivalent_airspeed_m_s': 20, 'height_rate_m_s': 0}}
          for value in (math.nan, math.inf, True, '0.25')],
        *[{'fields': {'course_rad': 0, 'equivalent_airspeed_m_s': value, 'height_rate_m_s': 0}}
          for value in (0, -1, math.nan, True, '20')],
        {'fields': {'course_rad': 0, 'equivalent_airspeed_m_s': 20, 'height_rate_m_s': math.nan}},
        {'fields': {'course_rad': 0, 'equivalent_airspeed_m_s': 20, 'altitude_amsl_m': math.inf}},
    ])
    def test_rejected_native_command_is_atomic_and_invalidates_previous_intent(self, native_handler, changes):
        native_handler.set_native_intent(native_intent())
        before = native_handler.get_fields()
        with pytest.raises(ValueError):
            native_handler.set_native_intent(native_intent(**changes))
        assert native_handler.get_fields() == before
        assert native_handler.get_last_command_intent() is None

    def test_untyped_native_intent_is_rejected(self, native_handler):
        with pytest.raises(ValueError, match='must be a CommandIntent'):
            native_handler.set_native_intent({})

    def test_mavsdk_profile_cannot_accept_native_intent(self, setpoint_handler):
        with pytest.raises(ValueError, match='requires px4_native transport'):
            setpoint_handler.set_native_intent(native_intent())

    @pytest.mark.parametrize('populate', [False, True])
    def test_ordinary_commander_cannot_admit_native_profile(self, native_handler, populate):
        from classes.offboard_commander import OffboardCommander

        intent = native_intent()
        if populate:
            native_handler.set_native_intent(intent)
        commander = OffboardCommander(MagicMock(), native_handler)
        assert commander.submit_intent(intent) is False
        assert commander._last_intent is None
        assert commander.rejected_intents == 1

    @pytest.mark.asyncio
    async def test_mavsdk_dispatch_never_sends_native_profile(self, native_handler):
        from classes.px4_interface_manager import PX4InterfaceManager

        native_handler.set_native_intent(native_intent())
        manager = PX4InterfaceManager.__new__(PX4InterfaceManager)
        manager.setpoint_handler = native_handler
        manager._validation_mavsdk_disconnect_error = MagicMock(return_value=None)
        manager.send_attitude_rate_commands = AsyncMock()
        manager.send_velocity_body_offboard_commands = AsyncMock()

        assert await manager.send_commands_unified() is False
        manager.send_attitude_rate_commands.assert_not_awaited()
        manager.send_velocity_body_offboard_commands.assert_not_awaited()


class TestSetpointHandlerValidation:
    """Tests for profile validation."""

    def test_validate_profile_consistency_valid(self, setpoint_handler):
        """Test validation passes for consistent profile."""
        assert setpoint_handler.validate_profile_consistency() is True


class TestSetpointHandlerAvailableProfiles:
    """Tests for listing available profiles."""

    def test_get_available_profiles(self, mock_schema):
        """Test listing available profiles."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            from classes.setpoint_handler import SetpointHandler

            profiles = SetpointHandler.get_available_profiles()

            assert 'mc_velocity_chase' in profiles
            assert 'fw_attitude_rate' in profiles
            assert 'mc_velocity_position' in profiles


class TestSetpointHandlerReport:
    """Tests for report generation."""

    def test_report_contains_profile_info(self, setpoint_handler):
        """Test that report contains profile information."""
        report = setpoint_handler.report()

        assert 'MC Velocity Chase' in report
        assert 'velocity_body_offboard' in report
        assert 'vel_body_fwd' in report


class TestSetpointHandlerTelemetry:
    """Tests for telemetry data export."""

    def test_get_telemetry_data_contains_fields(self, setpoint_handler, mock_parameters):
        """Test telemetry data contains field values."""
        setpoint_handler.set_field('vel_body_fwd', 2.0)

        telemetry = setpoint_handler.get_telemetry_data()

        assert 'fields' in telemetry
        assert telemetry['fields']['vel_body_fwd'] == 2.0

    def test_get_telemetry_data_contains_metadata(self, setpoint_handler):
        """Test telemetry data contains metadata."""
        telemetry = setpoint_handler.get_telemetry_data()

        assert 'profile_name' in telemetry
        assert 'control_type' in telemetry
        assert 'timestamp' in telemetry


class TestSetpointHandlerCircuitBreakerIntegration:
    """Tests for circuit breaker integration."""

    def test_get_fields_with_status_contains_cb_info(self, setpoint_handler):
        """Test that get_fields_with_status includes circuit breaker info."""
        with patch('classes.circuit_breaker.FollowerCircuitBreaker') as mock_cb:
            mock_cb.is_active.return_value = True
            mock_cb.get_statistics.return_value = {'blocked_count': 5}

            result = setpoint_handler.get_fields_with_status()

            assert 'circuit_breaker' in result
            assert 'setpoints' in result


class TestSetpointHandlerMultipleProfiles:
    """Tests for switching between profiles."""

    def test_different_profiles_have_different_fields(self, mock_schema, mock_parameters):
        """Test that different profiles have different field sets."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema

                velocity_handler = SetpointHandler('mc_velocity_chase')
                attitude_handler = SetpointHandler('fw_attitude_rate')

                # Velocity handler should not have thrust
                assert 'vel_body_fwd' in velocity_handler.fields
                assert 'thrust' not in velocity_handler.fields

                # Attitude handler should have thrust
                assert 'thrust' in attitude_handler.fields
                assert 'rollspeed_deg_s' in attitude_handler.fields


class TestSetpointHandlerEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_set_field_with_zero_value(self, setpoint_handler, mock_parameters):
        """Test setting field to zero."""
        setpoint_handler.set_field('vel_body_fwd', 5.0)
        setpoint_handler.set_field('vel_body_fwd', 0.0)
        assert setpoint_handler.fields['vel_body_fwd'] == 0.0

    def test_set_field_with_negative_value(self, setpoint_handler, mock_parameters):
        """Test setting negative field value."""
        setpoint_handler.set_field('vel_body_fwd', -3.0)
        assert setpoint_handler.fields['vel_body_fwd'] == -3.0

    def test_set_field_with_float_precision(self, setpoint_handler, mock_parameters):
        """Test that float precision is maintained."""
        setpoint_handler.set_field('vel_body_fwd', 2.123456789)
        assert abs(setpoint_handler.fields['vel_body_fwd'] - 2.123456789) < 1e-9

    def test_set_field_at_exact_limit(self, setpoint_handler, mock_parameters):
        """Test setting field at exactly the limit."""
        setpoint_handler.set_field('vel_body_fwd', 8.0)  # MAX_VELOCITY_FORWARD
        assert setpoint_handler.fields['vel_body_fwd'] == 8.0
