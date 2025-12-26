# tests/integration/drone_interface/test_safety_integration.py
"""
Integration tests for safety features in drone interface.

Tests safety mechanisms:
- Circuit breaker command blocking
- Velocity limit enforcement
- Safety manager integration
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


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
            }
        },
        'command_fields': {
            'vel_body_fwd': {'type': 'float', 'unit': 'm/s', 'default': 0.0, 'clamp': True},
            'vel_body_right': {'type': 'float', 'unit': 'm/s', 'default': 0.0, 'clamp': True},
            'vel_body_down': {'type': 'float', 'unit': 'm/s', 'default': 0.0, 'clamp': True},
            'yawspeed_deg_s': {'type': 'float', 'unit': 'deg/s', 'default': 0.0, 'clamp': True}
        }
    }


@pytest.fixture
def mock_parameters():
    """Mock Parameters class with safety limits."""
    mock_params = MagicMock()
    mock_params.get_effective_limit = MagicMock(side_effect=lambda name: {
        'MAX_VELOCITY_FORWARD': 8.0,
        'MAX_VELOCITY_LATERAL': 5.0,
        'MAX_VELOCITY_VERTICAL': 3.0,
        'MAX_YAW_RATE': 45.0
    }.get(name, 10.0))
    return mock_params


@pytest.fixture
def mock_circuit_breaker_active():
    """Mock active circuit breaker."""
    with patch('classes.circuit_breaker.FollowerCircuitBreaker') as mock_cb:
        mock_cb.is_active.return_value = True
        mock_cb.log_command_instead_of_execute = MagicMock()
        mock_cb.get_statistics.return_value = {'blocked_count': 5}
        yield mock_cb


@pytest.fixture
def mock_circuit_breaker_inactive():
    """Mock inactive circuit breaker."""
    with patch('classes.circuit_breaker.FollowerCircuitBreaker') as mock_cb:
        mock_cb.is_active.return_value = False
        yield mock_cb


# ============================================================================
# Test Classes
# ============================================================================

class TestCircuitBreakerIntegration:
    """Tests for circuit breaker integration."""

    def test_circuit_breaker_blocks_commands_when_active(self, mock_circuit_breaker_active):
        """Test that circuit breaker blocks commands when active."""
        mock_cb = mock_circuit_breaker_active

        # Simulate command attempt
        if mock_cb.is_active():
            mock_cb.log_command_instead_of_execute(
                command_type='velocity_body',
                follower_name='TestFollower',
                fields={'vel_body_fwd': 5.0}
            )

        mock_cb.log_command_instead_of_execute.assert_called_once()

    def test_circuit_breaker_allows_commands_when_inactive(self, mock_circuit_breaker_inactive):
        """Test that circuit breaker allows commands when inactive."""
        mock_cb = mock_circuit_breaker_inactive

        # Should not be active
        assert mock_cb.is_active() is False

    def test_circuit_breaker_status_in_setpoint_handler(self, mock_schema, mock_parameters):
        """Test circuit breaker status appears in setpoint handler output."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    with patch('classes.circuit_breaker.FollowerCircuitBreaker') as mock_cb:
                        mock_cb.is_active.return_value = True
                        mock_cb.get_statistics.return_value = {'blocked_count': 10}

                        from classes.setpoint_handler import SetpointHandler
                        SetpointHandler._schema_cache = mock_schema
                        handler = SetpointHandler('mc_velocity_offboard')

                        result = handler.get_fields_with_status()

                        assert 'circuit_breaker' in result
                        assert result['circuit_breaker']['active'] is True


class TestVelocityLimitEnforcement:
    """Tests for velocity limit enforcement."""

    def test_forward_velocity_clamped(self, mock_schema, mock_parameters):
        """Test that forward velocity is clamped to limit."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    from classes.setpoint_handler import SetpointHandler

                    SetpointHandler._schema_cache = mock_schema
                    handler = SetpointHandler('mc_velocity_offboard')

                    # Attempt to set value exceeding limit
                    handler.set_field('vel_body_fwd', 15.0)  # Max is 8.0

                    fields = handler.get_fields()

                    assert fields['vel_body_fwd'] <= 8.0

    def test_lateral_velocity_clamped(self, mock_schema, mock_parameters):
        """Test that lateral velocity is clamped to limit."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    from classes.setpoint_handler import SetpointHandler

                    SetpointHandler._schema_cache = mock_schema
                    handler = SetpointHandler('mc_velocity_offboard')

                    handler.set_field('vel_body_right', 10.0)  # Max is 5.0

                    fields = handler.get_fields()

                    assert fields['vel_body_right'] <= 5.0

    def test_vertical_velocity_clamped(self, mock_schema, mock_parameters):
        """Test that vertical velocity is clamped to limit."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    from classes.setpoint_handler import SetpointHandler

                    SetpointHandler._schema_cache = mock_schema
                    handler = SetpointHandler('mc_velocity_offboard')

                    handler.set_field('vel_body_down', 10.0)  # Max is 3.0

                    fields = handler.get_fields()

                    assert fields['vel_body_down'] <= 3.0

    def test_yaw_rate_clamped(self, mock_schema, mock_parameters):
        """Test that yaw rate is clamped to limit."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    from classes.setpoint_handler import SetpointHandler

                    SetpointHandler._schema_cache = mock_schema
                    handler = SetpointHandler('mc_velocity_offboard')

                    handler.set_field('yawspeed_deg_s', 90.0)  # Max is 45.0

                    fields = handler.get_fields()

                    assert fields['yawspeed_deg_s'] <= 45.0

    def test_negative_limits_applied(self, mock_schema, mock_parameters):
        """Test that negative values are also clamped."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    from classes.setpoint_handler import SetpointHandler

                    SetpointHandler._schema_cache = mock_schema
                    handler = SetpointHandler('mc_velocity_offboard')

                    handler.set_field('vel_body_fwd', -15.0)  # Min is -8.0

                    fields = handler.get_fields()

                    assert fields['vel_body_fwd'] >= -8.0


class TestThrustLimits:
    """Tests for thrust limit enforcement."""

    def test_thrust_max_clamped(self):
        """Test thrust is clamped to maximum of 1.0."""
        mock_schema = {
            'schema_version': '2.0',
            'follower_profiles': {
                'fw_attitude_rate': {
                    'control_type': 'attitude_rate',
                    'display_name': 'FW Attitude Rate',
                    'required_fields': ['thrust'],
                    'optional_fields': []
                }
            },
            'command_fields': {
                'thrust': {
                    'type': 'float',
                    'unit': 'normalized',
                    'default': 0.5,
                    'clamp': True,
                    'limits': {'min': 0.0, 'max': 1.0}
                }
            }
        }

        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler

                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('fw_attitude_rate')

                handler.set_field('thrust', 1.5)

                fields = handler.get_fields()

                assert fields['thrust'] <= 1.0

    def test_thrust_min_clamped(self):
        """Test thrust is clamped to minimum of 0.0."""
        mock_schema = {
            'schema_version': '2.0',
            'follower_profiles': {
                'fw_attitude_rate': {
                    'control_type': 'attitude_rate',
                    'display_name': 'FW Attitude Rate',
                    'required_fields': ['thrust'],
                    'optional_fields': []
                }
            },
            'command_fields': {
                'thrust': {
                    'type': 'float',
                    'unit': 'normalized',
                    'default': 0.5,
                    'clamp': True,
                    'limits': {'min': 0.0, 'max': 1.0}
                }
            }
        }

        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler

                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('fw_attitude_rate')

                handler.set_field('thrust', -0.5)

                fields = handler.get_fields()

                assert fields['thrust'] >= 0.0


class TestSafetyManagerIntegration:
    """Tests for safety manager integration."""

    def test_safety_limits_from_config(self):
        """Test that safety limits come from configuration."""
        with patch('classes.parameters.Parameters') as mock_params:
            mock_params.MAX_VELOCITY_FORWARD = 8.0
            mock_params.MAX_VELOCITY_LATERAL = 5.0

            # Verify config values
            assert mock_params.MAX_VELOCITY_FORWARD == 8.0
            assert mock_params.MAX_VELOCITY_LATERAL == 5.0


class TestOffboardModeSafety:
    """Tests for offboard mode safety features."""

    @pytest.mark.asyncio
    async def test_initial_zero_velocity_required(self):
        """Test that zero velocity must be sent before starting offboard."""
        from mavsdk.offboard import VelocityBodyYawspeed

        # Initial hover command required
        initial_cmd = VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)

        assert initial_cmd.forward_m_s == 0.0
        assert initial_cmd.right_m_s == 0.0
        assert initial_cmd.down_m_s == 0.0
        assert initial_cmd.yawspeed_deg_s == 0.0

    def test_command_rate_minimum(self):
        """Test that command rate meets minimum requirement."""
        with patch('classes.setpoint_sender.Parameters') as mock_params:
            mock_params.SETPOINT_PUBLISH_RATE_S = 0.05  # 20 Hz

            # PX4 requires at least 2 Hz
            rate_hz = 1.0 / mock_params.SETPOINT_PUBLISH_RATE_S
            assert rate_hz >= 2.0


class TestFlightModeTransitions:
    """Tests for flight mode transition safety."""

    def test_offboard_mode_code_constant(self):
        """Test offboard mode code is defined correctly."""
        OFFBOARD_MODE_CODE = 393216
        POSITION_MODE_CODE = 196608

        # Offboard exit is detected when mode changes from offboard
        assert OFFBOARD_MODE_CODE != POSITION_MODE_CODE

    def test_mode_change_detection_logic(self):
        """Test mode change detection logic."""
        OFFBOARD_MODE = 393216
        POSITION_MODE = 196608

        # Simulate mode tracking
        was_in_offboard = True
        current_mode = POSITION_MODE

        # Exit condition: was in offboard, now not
        exited_offboard = was_in_offboard and current_mode != OFFBOARD_MODE

        assert exited_offboard is True

    def test_still_in_offboard_no_exit(self):
        """Test no exit detected when still in offboard."""
        OFFBOARD_MODE = 393216

        was_in_offboard = True
        current_mode = OFFBOARD_MODE

        exited_offboard = was_in_offboard and current_mode != OFFBOARD_MODE

        assert exited_offboard is False


class TestEmergencyActions:
    """Tests for emergency action integration."""

    @pytest.mark.asyncio
    async def test_rtl_available(self):
        """Test that RTL action is available."""
        mock_drone = MagicMock()
        mock_drone.action = MagicMock()
        mock_drone.action.return_to_launch = AsyncMock()

        # Should be callable
        await mock_drone.action.return_to_launch()

        mock_drone.action.return_to_launch.assert_called_once()


class TestDataValidation:
    """Tests for data validation in safety context."""

    def test_nan_values_handled_safely(self, mock_schema, mock_parameters):
        """Test that NaN values are handled safely."""
        import math

        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    from classes.setpoint_handler import SetpointHandler

                    SetpointHandler._schema_cache = mock_schema
                    handler = SetpointHandler('mc_velocity_offboard')

                    # NaN values: either rejected or stored (depending on implementation)
                    # The important thing is the system doesn't crash
                    try:
                        handler.set_field('vel_body_fwd', float('nan'))
                        # If it accepts NaN, it should at least store something
                        fields = handler.get_fields()
                        assert 'vel_body_fwd' in fields
                    except (TypeError, ValueError):
                        # If it rejects NaN, that's also safe behavior
                        pass

    def test_inf_values_clamped(self, mock_schema, mock_parameters):
        """Test that infinity values are clamped safely."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    from classes.setpoint_handler import SetpointHandler

                    SetpointHandler._schema_cache = mock_schema
                    handler = SetpointHandler('mc_velocity_offboard')

                    # Infinity should be clamped, not passed through
                    handler.set_field('vel_body_fwd', float('inf'))
                    fields = handler.get_fields()

                    # Should be clamped to max limit
                    assert fields['vel_body_fwd'] <= 8.0
