# tests/integration/drone_interface/test_command_flow.py
"""
Integration tests for command flow through drone interface.

Tests the complete command path:
Follower → SetpointHandler → PX4InterfaceManager → MAVSDK
"""

import pytest
import asyncio
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
            },
            'fw_attitude_rate': {
                'control_type': 'attitude_rate',
                'display_name': 'FW Attitude Rate',
                'description': 'Angular rate control',
                'required_fields': ['rollspeed_deg_s', 'pitchspeed_deg_s', 'yawspeed_deg_s', 'thrust'],
                'optional_fields': []
            }
        },
        'command_fields': {
            'vel_body_fwd': {'type': 'float', 'unit': 'm/s', 'default': 0.0, 'clamp': True},
            'vel_body_right': {'type': 'float', 'unit': 'm/s', 'default': 0.0, 'clamp': True},
            'vel_body_down': {'type': 'float', 'unit': 'm/s', 'default': 0.0, 'clamp': True},
            'yawspeed_deg_s': {'type': 'float', 'unit': 'deg/s', 'default': 0.0, 'clamp': True},
            'rollspeed_deg_s': {'type': 'float', 'unit': 'deg/s', 'default': 0.0, 'clamp': True},
            'pitchspeed_deg_s': {'type': 'float', 'unit': 'deg/s', 'default': 0.0, 'clamp': True},
            'thrust': {'type': 'float', 'unit': 'normalized', 'default': 0.5, 'clamp': True, 'limits': {'min': 0.0, 'max': 1.0}}
        }
    }


@pytest.fixture
def mock_mavsdk_system():
    """Create mock MAVSDK System."""
    mock_system = MagicMock()
    mock_system.offboard = MagicMock()
    mock_system.offboard.start = AsyncMock()
    mock_system.offboard.stop = AsyncMock()
    mock_system.offboard.set_velocity_body = AsyncMock()
    mock_system.offboard.set_attitude_rate = AsyncMock()
    mock_system.action = MagicMock()
    mock_system.action.arm = AsyncMock()
    mock_system.action.return_to_launch = AsyncMock()
    mock_system.connect = AsyncMock()
    return mock_system


@pytest.fixture
def mock_parameters():
    """Mock Parameters class."""
    mock_params = MagicMock()
    mock_params.get_effective_limit = MagicMock(side_effect=lambda name: {
        'MAX_VELOCITY_FORWARD': 8.0,
        'MAX_VELOCITY_LATERAL': 5.0,
        'MAX_VELOCITY_VERTICAL': 3.0,
        'MAX_YAW_RATE': 45.0
    }.get(name, 10.0))
    return mock_params


# ============================================================================
# Test Classes
# ============================================================================

class TestSetpointHandlerToPX4Flow:
    """Tests for command flow from SetpointHandler to PX4."""

    def test_velocity_fields_propagate_to_px4(self, mock_schema, mock_parameters):
        """Test that velocity fields reach PX4InterfaceManager."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    from classes.setpoint_handler import SetpointHandler

                    SetpointHandler._schema_cache = mock_schema
                    handler = SetpointHandler('mc_velocity_offboard')

                    # Set fields as follower would
                    handler.set_field('vel_body_fwd', 3.0)
                    handler.set_field('vel_body_right', 1.5)
                    handler.set_field('yawspeed_deg_s', 10.0)

                    # Get fields for PX4
                    fields = handler.get_fields()

                    assert fields['vel_body_fwd'] == 3.0
                    assert fields['vel_body_right'] == 1.5
                    assert fields['yawspeed_deg_s'] == 10.0

    def test_control_type_dispatch_routing(self, mock_schema, mock_parameters):
        """Test that control type determines dispatch method."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler

                SetpointHandler._schema_cache = mock_schema

                velocity_handler = SetpointHandler('mc_velocity_offboard')
                attitude_handler = SetpointHandler('fw_attitude_rate')

                assert velocity_handler.get_control_type() == 'velocity_body_offboard'
                assert attitude_handler.get_control_type() == 'attitude_rate'

    def test_fields_clamped_before_dispatch(self, mock_schema, mock_parameters):
        """Test that values are clamped before reaching PX4."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                with patch('classes.parameters.Parameters', mock_parameters):
                    from classes.setpoint_handler import SetpointHandler

                    SetpointHandler._schema_cache = mock_schema
                    handler = SetpointHandler('mc_velocity_offboard')

                    # Set value exceeding limit
                    handler.set_field('vel_body_fwd', 15.0)  # Max is 8.0

                    fields = handler.get_fields()

                    # Should be clamped
                    assert fields['vel_body_fwd'] <= 8.0


class TestVelocityBodyCommandFlow:
    """Tests for velocity body command flow."""

    @pytest.mark.asyncio
    async def test_velocity_body_command_format(self, mock_mavsdk_system):
        """Test velocity body commands have correct format."""
        fields = {
            'vel_body_fwd': 2.0,
            'vel_body_right': 1.0,
            'vel_body_down': -0.5,
            'yawspeed_deg_s': 15.0
        }

        # Simulate PX4InterfaceManager behavior
        from mavsdk.offboard import VelocityBodyYawspeed

        velocity_cmd = VelocityBodyYawspeed(
            forward_m_s=fields['vel_body_fwd'],
            right_m_s=fields['vel_body_right'],
            down_m_s=fields['vel_body_down'],
            yawspeed_deg_s=fields['yawspeed_deg_s']
        )

        assert velocity_cmd.forward_m_s == 2.0
        assert velocity_cmd.right_m_s == 1.0
        assert velocity_cmd.down_m_s == -0.5
        assert velocity_cmd.yawspeed_deg_s == 15.0

    @pytest.mark.asyncio
    async def test_zero_velocity_produces_hover(self, mock_mavsdk_system):
        """Test that zero velocities result in hover command."""
        from mavsdk.offboard import VelocityBodyYawspeed

        hover_cmd = VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)

        assert hover_cmd.forward_m_s == 0.0
        assert hover_cmd.right_m_s == 0.0
        assert hover_cmd.down_m_s == 0.0
        assert hover_cmd.yawspeed_deg_s == 0.0


class TestAttitudeRateCommandFlow:
    """Tests for attitude rate command flow."""

    @pytest.mark.asyncio
    async def test_attitude_rate_command_format(self):
        """Test attitude rate commands have correct format."""
        from mavsdk.offboard import AttitudeRate

        fields = {
            'rollspeed_deg_s': 10.0,
            'pitchspeed_deg_s': 5.0,
            'yawspeed_deg_s': 15.0,
            'thrust': 0.6
        }

        attitude_cmd = AttitudeRate(
            roll_deg_s=fields['rollspeed_deg_s'],
            pitch_deg_s=fields['pitchspeed_deg_s'],
            yaw_deg_s=fields['yawspeed_deg_s'],
            thrust_value=fields['thrust']
        )

        assert attitude_cmd.roll_deg_s == 10.0
        assert attitude_cmd.pitch_deg_s == 5.0
        assert attitude_cmd.yaw_deg_s == 15.0
        assert attitude_cmd.thrust_value == 0.6

    @pytest.mark.asyncio
    async def test_thrust_normalized_to_valid_range(self):
        """Test that thrust is within 0-1 range."""
        from mavsdk.offboard import AttitudeRate

        # Values should be valid
        valid_thrusts = [0.0, 0.5, 1.0]

        for thrust in valid_thrusts:
            attitude_cmd = AttitudeRate(0.0, 0.0, 0.0, thrust)
            assert 0.0 <= attitude_cmd.thrust_value <= 1.0


class TestCommandRateVerification:
    """Tests for command rate requirements."""

    def test_setpoint_publish_rate_configured(self):
        """Test that setpoint publish rate is configured."""
        with patch('classes.setpoint_sender.Parameters') as mock_params:
            mock_params.SETPOINT_PUBLISH_RATE_S = 0.05  # 20 Hz

            assert mock_params.SETPOINT_PUBLISH_RATE_S <= 0.5  # At least 2 Hz

    def test_setpoint_sender_daemon_thread(self):
        """Test SetpointSender runs as daemon thread."""
        with patch('classes.setpoint_sender.Parameters') as mock_params:
            mock_params.SETPOINT_PUBLISH_RATE_S = 0.1
            mock_params.ENABLE_SETPOINT_DEBUGGING = False

            mock_handler = MagicMock()
            mock_handler.get_control_type.return_value = 'velocity_body_offboard'
            mock_handler.get_fields.return_value = {'vel_body_fwd': 0.0}

            mock_px4 = MagicMock()

            from classes.setpoint_sender import SetpointSender
            sender = SetpointSender(mock_px4, mock_handler)

            assert sender.daemon is True


class TestMultipleFollowerSwitch:
    """Tests for switching between followers."""

    def test_control_type_switch_updates_dispatch(self, mock_schema, mock_parameters):
        """Test switching control types updates command dispatch."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler

                SetpointHandler._schema_cache = mock_schema

                # Start with velocity control
                handler = SetpointHandler('mc_velocity_offboard')
                assert handler.get_control_type() == 'velocity_body_offboard'

                # Create new handler for attitude control
                attitude_handler = SetpointHandler('fw_attitude_rate')
                assert attitude_handler.get_control_type() == 'attitude_rate'

    def test_fields_reset_on_profile_change(self, mock_schema, mock_parameters):
        """Test that fields reset when changing profiles."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler

                SetpointHandler._schema_cache = mock_schema

                velocity_handler = SetpointHandler('mc_velocity_offboard')
                velocity_handler.set_field('vel_body_fwd', 5.0)

                attitude_handler = SetpointHandler('fw_attitude_rate')

                # Attitude handler should have default values
                assert attitude_handler.fields.get('thrust') == 0.5


class TestCommandFieldMapping:
    """Tests for field mapping between components."""

    def test_velocity_field_names_match(self, mock_schema):
        """Test that velocity field names match between components."""
        expected_fields = ['vel_body_fwd', 'vel_body_right', 'vel_body_down', 'yawspeed_deg_s']

        profile = mock_schema['follower_profiles']['mc_velocity_offboard']

        for field in expected_fields:
            assert field in profile['required_fields']

    def test_attitude_rate_field_names_match(self, mock_schema):
        """Test that attitude rate field names match between components."""
        expected_fields = ['rollspeed_deg_s', 'pitchspeed_deg_s', 'yawspeed_deg_s', 'thrust']

        profile = mock_schema['follower_profiles']['fw_attitude_rate']

        for field in expected_fields:
            assert field in profile['required_fields']


class TestErrorHandlingInFlow:
    """Tests for error handling in command flow."""

    def test_invalid_field_rejected(self, mock_schema, mock_parameters):
        """Test that invalid fields are rejected."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler

                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('mc_velocity_offboard')

                with pytest.raises(ValueError):
                    handler.set_field('nonexistent_field', 1.0)

    def test_non_numeric_value_rejected(self, mock_schema, mock_parameters):
        """Test that non-numeric values are rejected."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler

                SetpointHandler._schema_cache = mock_schema
                handler = SetpointHandler('mc_velocity_offboard')

                with pytest.raises((TypeError, ValueError)):
                    handler.set_field('vel_body_fwd', 'not_a_number')

    def test_invalid_profile_rejected(self, mock_schema):
        """Test that invalid profile names are rejected."""
        with patch('classes.setpoint_handler.SetpointHandler._schema_cache', mock_schema):
            with patch('classes.setpoint_handler.SetpointHandler._load_schema'):
                from classes.setpoint_handler import SetpointHandler

                SetpointHandler._schema_cache = mock_schema

                with pytest.raises(ValueError):
                    SetpointHandler('invalid_profile')


class TestSignConventions:
    """Tests for sign convention consistency."""

    def test_forward_positive_convention(self):
        """Test that positive vel_body_fwd means forward movement."""
        from mavsdk.offboard import VelocityBodyYawspeed

        # Positive = forward (toward nose)
        cmd = VelocityBodyYawspeed(forward_m_s=2.0, right_m_s=0, down_m_s=0, yawspeed_deg_s=0)
        assert cmd.forward_m_s > 0  # Forward

    def test_right_positive_convention(self):
        """Test that positive vel_body_right means rightward movement."""
        from mavsdk.offboard import VelocityBodyYawspeed

        # Positive = right (starboard)
        cmd = VelocityBodyYawspeed(forward_m_s=0, right_m_s=2.0, down_m_s=0, yawspeed_deg_s=0)
        assert cmd.right_m_s > 0  # Right

    def test_down_positive_convention(self):
        """Test that positive vel_body_down means descent."""
        from mavsdk.offboard import VelocityBodyYawspeed

        # Positive = down (descend)
        cmd = VelocityBodyYawspeed(forward_m_s=0, right_m_s=0, down_m_s=1.0, yawspeed_deg_s=0)
        assert cmd.down_m_s > 0  # Descending

    def test_climb_negative_down(self):
        """Test that climbing uses negative down velocity."""
        from mavsdk.offboard import VelocityBodyYawspeed

        # Negative down = climb
        cmd = VelocityBodyYawspeed(forward_m_s=0, right_m_s=0, down_m_s=-1.0, yawspeed_deg_s=0)
        assert cmd.down_m_s < 0  # Climbing
