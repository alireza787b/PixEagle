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
from unittest.mock import patch, MagicMock
import yaml
import os


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_schema():
    """Create a mock schema for testing."""
    return {
        'schema_version': '2.0',
        'follower_profiles': {
            'mc_velocity_offboard': {
                'control_type': 'velocity_body_offboard',
                'display_name': 'MC Velocity Offboard',
                'description': 'Body-frame velocity control',
                'required_fields': ['vel_body_fwd', 'vel_body_right', 'vel_body_down', 'yawspeed_deg_s'],
                'optional_fields': []
            },
            'fw_attitude_rate': {
                'control_type': 'attitude_rate',
                'display_name': 'FW Attitude Rate',
                'description': 'Angular rate control',
                'required_fields': ['rollspeed_deg_s', 'pitchspeed_deg_s', 'yawspeed_deg_s', 'thrust'],
                'optional_fields': []
            },
            'mc_velocity_position': {
                'control_type': 'velocity_body_offboard',
                'display_name': 'MC Velocity Position',
                'description': 'Position-based velocity control',
                'required_fields': ['vel_body_fwd', 'vel_body_right', 'vel_body_down', 'yawspeed_deg_s'],
                'optional_fields': []
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
    mock_params.get_effective_limit = MagicMock(side_effect=lambda name: {
        'MAX_VELOCITY_FORWARD': 8.0,
        'MAX_VELOCITY_LATERAL': 5.0,
        'MAX_VELOCITY_VERTICAL': 3.0,
        'MAX_YAW_RATE': 45.0
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
                handler = SetpointHandler('mc_velocity_offboard')
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
                handler = SetpointHandler('mc_velocity_offboard')

                assert handler.profile_name == 'mc_velocity_offboard'
                assert 'vel_body_fwd' in handler.fields
                assert 'yawspeed_deg_s' in handler.fields

    def test_init_with_normalized_profile_name(self, mock_schema, mock_parameters):
        """Test that profile names are normalized correctly."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler
                SetpointHandler._schema_cache = mock_schema

                # Test with spaces and mixed case
                handler = SetpointHandler('MC Velocity Offboard')
                assert handler.profile_name == 'mc_velocity_offboard'

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
        assert SetpointHandler.normalize_profile_name('MC_VELOCITY') == 'mc_velocity'

    def test_normalize_spaces_to_underscores(self):
        """Test space to underscore conversion."""
        from classes.setpoint_handler import SetpointHandler
        assert SetpointHandler.normalize_profile_name('MC Velocity Offboard') == 'mc_velocity_offboard'

    def test_normalize_already_normalized(self):
        """Test that already normalized names pass through."""
        from classes.setpoint_handler import SetpointHandler
        assert SetpointHandler.normalize_profile_name('mc_velocity_offboard') == 'mc_velocity_offboard'


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
        with pytest.raises(ValueError, match="must be a numeric type"):
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
        assert setpoint_handler.get_display_name() == 'MC Velocity Offboard'

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

            assert 'mc_velocity_offboard' in profiles
            assert 'fw_attitude_rate' in profiles
            assert 'mc_velocity_position' in profiles


class TestSetpointHandlerReport:
    """Tests for report generation."""

    def test_report_contains_profile_info(self, setpoint_handler):
        """Test that report contains profile information."""
        report = setpoint_handler.report()

        assert 'MC Velocity Offboard' in report
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

                velocity_handler = SetpointHandler('mc_velocity_offboard')
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
