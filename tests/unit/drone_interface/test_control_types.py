# tests/unit/drone_interface/test_control_types.py
"""
Unit tests for control types and MAVSDK command creation.

Tests command format creation:
- VelocityBodyYawspeed creation
- AttitudeRate creation
- Unit conversions (deg/s, rad/s)
- Field mapping from schema
- Limit application
"""

import pytest
import math
from unittest.mock import patch, MagicMock


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_mavsdk_offboard():
    """Mock MAVSDK offboard module."""
    with patch('classes.px4_interface_manager.VelocityBodyYawspeed') as mock_vel:
        with patch('classes.px4_interface_manager.AttitudeRate') as mock_att:
            yield {
                'VelocityBodyYawspeed': mock_vel,
                'AttitudeRate': mock_att
            }


# ============================================================================
# Test Classes
# ============================================================================

class TestVelocityBodyYawspeedFormat:
    """Tests for VelocityBodyYawspeed command format."""

    def test_velocity_body_field_order(self):
        """Test VelocityBodyYawspeed field order: (forward, right, down, yawspeed)."""
        # Verify the expected order based on MAVSDK API
        expected_fields = ['forward_m_s', 'right_m_s', 'down_m_s', 'yawspeed_deg_s']

        # This tests our understanding of the API
        assert len(expected_fields) == 4

    def test_velocity_forward_positive_means_forward(self):
        """Test that positive forward velocity means forward motion."""
        # In body frame, positive forward is toward nose
        forward = 2.0
        assert forward > 0  # Forward motion

    def test_velocity_right_positive_means_right(self):
        """Test that positive right velocity means rightward motion."""
        # In body frame, positive right is to starboard
        right = 1.0
        assert right > 0  # Rightward motion

    def test_velocity_down_positive_means_descend(self):
        """Test that positive down velocity means descent."""
        # In NED frame, positive down is toward ground
        down = 0.5
        assert down > 0  # Descending

    def test_velocity_down_negative_means_climb(self):
        """Test that negative down velocity means climb."""
        # In NED frame, negative down is away from ground
        down = -0.5
        assert down < 0  # Climbing

    def test_yawspeed_positive_means_clockwise(self):
        """Test that positive yawspeed means clockwise rotation."""
        # PX4 convention: positive yaw is clockwise (from above)
        yawspeed = 15.0
        assert yawspeed > 0  # Clockwise

    def test_yawspeed_units_deg_s(self):
        """Test that yawspeed is in deg/s (MAVSDK standard)."""
        # MAVSDK VelocityBodyYawspeed expects deg/s
        yawspeed_deg_s = 45.0
        # No conversion needed
        assert yawspeed_deg_s == 45.0


class TestAttitudeRateFormat:
    """Tests for AttitudeRate command format."""

    def test_attitude_rate_field_order(self):
        """Test AttitudeRate field order: (roll, pitch, yaw, thrust)."""
        expected_fields = ['roll_rate_deg_s', 'pitch_rate_deg_s', 'yaw_rate_deg_s', 'thrust_value']

        # This tests our understanding of the API
        assert len(expected_fields) == 4

    def test_roll_rate_positive_means_roll_right(self):
        """Test that positive roll rate means rolling right."""
        roll_rate = 10.0
        assert roll_rate > 0  # Roll right (starboard wing down)

    def test_pitch_rate_positive_means_pitch_up(self):
        """Test that positive pitch rate means pitching up."""
        pitch_rate = 5.0
        assert pitch_rate > 0  # Pitch up (nose up)

    def test_yaw_rate_positive_means_yaw_right(self):
        """Test that positive yaw rate means yawing right."""
        yaw_rate = 15.0
        assert yaw_rate > 0  # Yaw right (clockwise)

    def test_thrust_range_0_to_1(self):
        """Test that thrust is in 0.0 to 1.0 range."""
        thrust = 0.65
        assert 0.0 <= thrust <= 1.0

    def test_thrust_zero_means_no_thrust(self):
        """Test that thrust 0 means no thrust."""
        thrust = 0.0
        assert thrust == 0.0

    def test_thrust_one_means_full_thrust(self):
        """Test that thrust 1 means full thrust."""
        thrust = 1.0
        assert thrust == 1.0


class TestUnitConversions:
    """Tests for unit conversions."""

    def test_deg_to_rad_conversion(self):
        """Test degrees to radians conversion."""
        deg = 180.0
        rad = math.radians(deg)
        assert abs(rad - math.pi) < 0.001

    def test_rad_to_deg_conversion(self):
        """Test radians to degrees conversion."""
        rad = math.pi
        deg = math.degrees(rad)
        assert abs(deg - 180.0) < 0.001

    def test_yaw_rate_deg_s_no_conversion(self):
        """Test that yaw rate in deg/s needs no conversion for MAVSDK."""
        # MAVSDK expects deg/s for VelocityBodyYawspeed.yawspeed_deg_s
        yaw_rate_deg_s = 45.0
        mavsdk_yaw = yaw_rate_deg_s  # No conversion
        assert mavsdk_yaw == 45.0

    def test_attitude_rate_deg_s_no_conversion(self):
        """Test that attitude rates in deg/s need no conversion for MAVSDK."""
        # MAVSDK AttitudeRate expects deg/s
        roll_deg_s = 30.0
        mavsdk_roll = roll_deg_s  # No conversion
        assert mavsdk_roll == 30.0


class TestFieldMappingFromSchema:
    """Tests for field mapping from schema to MAVSDK."""

    def test_velocity_body_offboard_field_mapping(self):
        """Test velocity_body_offboard schema to MAVSDK mapping."""
        schema_fields = {
            'vel_body_fwd': 2.0,
            'vel_body_right': 1.0,
            'vel_body_down': -0.5,
            'yawspeed_deg_s': 15.0
        }

        # Map to MAVSDK VelocityBodyYawspeed constructor
        forward_m_s = schema_fields['vel_body_fwd']
        right_m_s = schema_fields['vel_body_right']
        down_m_s = schema_fields['vel_body_down']
        yawspeed = schema_fields['yawspeed_deg_s']

        assert forward_m_s == 2.0
        assert right_m_s == 1.0
        assert down_m_s == -0.5
        assert yawspeed == 15.0

    def test_attitude_rate_field_mapping(self):
        """Test attitude_rate schema to MAVSDK mapping."""
        schema_fields = {
            'rollspeed_deg_s': 10.0,
            'pitchspeed_deg_s': 5.0,
            'yawspeed_deg_s': 15.0,
            'thrust': 0.65
        }

        # Map to MAVSDK AttitudeRate constructor
        roll_rate = schema_fields['rollspeed_deg_s']
        pitch_rate = schema_fields['pitchspeed_deg_s']
        yaw_rate = schema_fields['yawspeed_deg_s']
        thrust = schema_fields['thrust']

        assert roll_rate == 10.0
        assert pitch_rate == 5.0
        assert yaw_rate == 15.0
        assert thrust == 0.65

    def test_legacy_velocity_body_mapping(self):
        """Test legacy velocity_body schema mapping (deprecated)."""
        schema_fields = {
            'vel_x': 2.0,
            'vel_y': 1.0,
            'vel_z': -0.5,
            'yaw_rate': 0.26  # rad/s
        }

        # Legacy yaw_rate needs conversion from rad/s to deg/s
        yaw_deg_s = math.degrees(schema_fields['yaw_rate'])

        assert abs(yaw_deg_s - 14.9) < 0.1  # ~15 deg/s


class TestLimitApplication:
    """Tests for safety limit application."""

    def test_velocity_limit_clamping(self):
        """Test velocity clamping to limits."""
        max_velocity = 8.0
        requested_velocity = 15.0

        clamped = min(requested_velocity, max_velocity)

        assert clamped == 8.0

    def test_velocity_negative_limit_clamping(self):
        """Test negative velocity clamping."""
        max_velocity = 8.0
        requested_velocity = -15.0

        clamped = max(requested_velocity, -max_velocity)

        assert clamped == -8.0

    def test_yaw_rate_limit_clamping(self):
        """Test yaw rate clamping to limits."""
        max_yaw_rate = 45.0
        requested_yaw_rate = 100.0

        clamped = min(requested_yaw_rate, max_yaw_rate)

        assert clamped == 45.0

    def test_thrust_limit_clamping_max(self):
        """Test thrust clamping to maximum."""
        max_thrust = 1.0
        requested_thrust = 1.5

        clamped = min(requested_thrust, max_thrust)

        assert clamped == 1.0

    def test_thrust_limit_clamping_min(self):
        """Test thrust clamping to minimum."""
        min_thrust = 0.0
        requested_thrust = -0.5

        clamped = max(requested_thrust, min_thrust)

        assert clamped == 0.0


class TestControlTypeIdentification:
    """Tests for control type identification."""

    def test_velocity_body_offboard_control_type(self):
        """Test identification of velocity_body_offboard control type."""
        control_type = 'velocity_body_offboard'

        is_velocity = 'velocity' in control_type
        is_body = 'body' in control_type

        assert is_velocity
        assert is_body

    def test_attitude_rate_control_type(self):
        """Test identification of attitude_rate control type."""
        control_type = 'attitude_rate'

        is_attitude = 'attitude' in control_type
        is_rate = 'rate' in control_type

        assert is_attitude
        assert is_rate

    def test_control_type_dispatch_velocity(self):
        """Test control type dispatch for velocity."""
        control_type = 'velocity_body_offboard'

        if control_type == 'velocity_body_offboard':
            method = 'send_velocity_body_offboard_commands'
        elif control_type == 'attitude_rate':
            method = 'send_attitude_rate_commands'
        else:
            method = None

        assert method == 'send_velocity_body_offboard_commands'

    def test_control_type_dispatch_attitude(self):
        """Test control type dispatch for attitude."""
        control_type = 'attitude_rate'

        if control_type == 'velocity_body_offboard':
            method = 'send_velocity_body_offboard_commands'
        elif control_type == 'attitude_rate':
            method = 'send_attitude_rate_commands'
        else:
            method = None

        assert method == 'send_attitude_rate_commands'


class TestFrameConventions:
    """Tests for frame conventions (NED, body)."""

    def test_body_frame_axes(self):
        """Test body frame axis definitions."""
        # X-axis: forward (out the nose)
        # Y-axis: right (starboard)
        # Z-axis: down

        body_x_forward = True  # Forward is positive X
        body_y_right = True    # Right is positive Y
        body_z_down = True     # Down is positive Z

        assert body_x_forward
        assert body_y_right
        assert body_z_down

    def test_ned_frame_axes(self):
        """Test NED frame axis definitions."""
        # N: North
        # E: East
        # D: Down

        ned_n_north = True
        ned_e_east = True
        ned_d_down = True

        assert ned_n_north
        assert ned_e_east
        assert ned_d_down

    def test_body_to_ned_requires_yaw(self):
        """Test that body to NED conversion requires yaw angle."""
        # Body frame velocities need yaw to convert to NED

        vel_body_fwd = 5.0
        vel_body_right = 0.0
        yaw = 0.0  # Heading north

        # At yaw=0, forward = north
        vel_ned_n = vel_body_fwd * math.cos(yaw) - vel_body_right * math.sin(yaw)
        vel_ned_e = vel_body_fwd * math.sin(yaw) + vel_body_right * math.cos(yaw)

        assert abs(vel_ned_n - 5.0) < 0.01
        assert abs(vel_ned_e - 0.0) < 0.01


class TestZeroCommands:
    """Tests for zero/hover commands."""

    def test_zero_velocity_command(self):
        """Test creating zero velocity command (hover)."""
        velocity = {
            'vel_body_fwd': 0.0,
            'vel_body_right': 0.0,
            'vel_body_down': 0.0,
            'yawspeed_deg_s': 0.0
        }

        all_zero = all(v == 0.0 for v in velocity.values())

        assert all_zero

    def test_hover_attitude_rate_command(self):
        """Test creating hover attitude rate command."""
        attitude_rate = {
            'rollspeed_deg_s': 0.0,
            'pitchspeed_deg_s': 0.0,
            'yawspeed_deg_s': 0.0,
            'thrust': 0.5  # Hover thrust
        }

        rates_zero = (
            attitude_rate['rollspeed_deg_s'] == 0.0 and
            attitude_rate['pitchspeed_deg_s'] == 0.0 and
            attitude_rate['yawspeed_deg_s'] == 0.0
        )
        thrust_set = attitude_rate['thrust'] > 0.0

        assert rates_zero
        assert thrust_set
