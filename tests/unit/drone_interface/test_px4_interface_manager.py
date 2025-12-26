# tests/unit/drone_interface/test_px4_interface_manager.py
"""
Unit tests for PX4InterfaceManager.

Tests MAVSDK command dispatch and telemetry:
- Connection lifecycle (connect, disconnect, reconnect)
- Offboard mode management (start, stop, transitions)
- Velocity body command dispatch
- Attitude rate command dispatch
- Telemetry update (MAVLink2REST mode)
- Circuit breaker integration
- Error handling
"""

import pytest
import math
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
import sys
import os

# Add fixtures to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'fixtures'))


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_mavsdk_system():
    """Create mock MAVSDK System."""
    mock_system = MagicMock()
    mock_system.connect = AsyncMock()
    mock_system.offboard = MagicMock()
    mock_system.offboard.start = AsyncMock()
    mock_system.offboard.stop = AsyncMock()
    mock_system.offboard.set_velocity_body = AsyncMock()
    mock_system.offboard.set_attitude_rate = AsyncMock()
    mock_system.action = MagicMock()
    mock_system.action.return_to_launch = AsyncMock()
    mock_system.telemetry = MagicMock()
    return mock_system


@pytest.fixture
def mock_parameters():
    """Mock Parameters class."""
    with patch('classes.px4_interface_manager.Parameters') as mock_params:
        mock_params.SYSTEM_ADDRESS = "udp://:14540"
        mock_params.EXTERNAL_MAVSDK_SERVER = True
        mock_params.USE_MAVLINK2REST = True
        mock_params.FOLLOWER_MODE = "mc_velocity_offboard"
        mock_params.CAMERA_YAW_OFFSET = 0.0
        mock_params.FOLLOWER_DATA_REFRESH_RATE = 1
        yield mock_params


@pytest.fixture
def mock_setpoint_handler():
    """Create mock SetpointHandler."""
    mock_handler = MagicMock()
    mock_handler.get_control_type.return_value = 'velocity_body_offboard'
    mock_handler.get_display_name.return_value = 'MC Velocity Offboard'
    mock_handler.get_fields.return_value = {
        'vel_body_fwd': 0.0,
        'vel_body_right': 0.0,
        'vel_body_down': 0.0,
        'yawspeed_deg_s': 0.0
    }
    mock_handler.set_field = MagicMock()
    mock_handler.reset_setpoints = MagicMock()
    mock_handler.validate_profile_consistency.return_value = True
    return mock_handler


@pytest.fixture
def mock_mavlink_data_manager():
    """Create mock MavlinkDataManager."""
    mock_manager = MagicMock()
    mock_manager.fetch_attitude_data = AsyncMock(return_value={
        'roll': 0.0,
        'pitch': 0.0,
        'yaw': 0.0
    })
    mock_manager.fetch_altitude_data = AsyncMock(return_value={
        'altitude_relative': 50.0,
        'altitude_amsl': 150.0
    })
    mock_manager.fetch_ground_speed = AsyncMock(return_value=0.0)
    mock_manager.fetch_throttle_percent = AsyncMock(return_value=50)
    return mock_manager


@pytest.fixture
def mock_circuit_breaker_active():
    """Mock circuit breaker in active (blocking) state."""
    with patch('classes.px4_interface_manager.CIRCUIT_BREAKER_AVAILABLE', True):
        with patch('classes.px4_interface_manager.FollowerCircuitBreaker') as mock_cb:
            mock_cb.is_active.return_value = True
            mock_cb.log_command_instead_of_execute = MagicMock()
            mock_cb.log_command_allowed = MagicMock()
            yield mock_cb


@pytest.fixture
def mock_circuit_breaker_inactive():
    """Mock circuit breaker in inactive (allowing) state."""
    with patch('classes.px4_interface_manager.CIRCUIT_BREAKER_AVAILABLE', True):
        with patch('classes.px4_interface_manager.FollowerCircuitBreaker') as mock_cb:
            mock_cb.is_active.return_value = False
            mock_cb.log_command_instead_of_execute = MagicMock()
            mock_cb.log_command_allowed = MagicMock()
            yield mock_cb


@pytest.fixture
def px4_interface(mock_parameters, mock_mavsdk_system, mock_setpoint_handler, mock_mavlink_data_manager):
    """Create PX4InterfaceManager instance for testing."""
    with patch('classes.px4_interface_manager.System', return_value=mock_mavsdk_system):
        with patch('classes.px4_interface_manager.SetpointHandler', return_value=mock_setpoint_handler):
            with patch('classes.px4_interface_manager.CIRCUIT_BREAKER_AVAILABLE', False):
                from classes.px4_interface_manager import PX4InterfaceManager

                mock_app_controller = MagicMock()
                mock_app_controller.mavlink_data_manager = mock_mavlink_data_manager

                interface = PX4InterfaceManager(app_controller=mock_app_controller)
                interface.drone = mock_mavsdk_system
                interface.setpoint_handler = mock_setpoint_handler
                interface.mavlink_data_manager = mock_mavlink_data_manager

                yield interface


# ============================================================================
# Test Classes
# ============================================================================

class TestPX4InterfaceManagerInitialization:
    """Tests for PX4InterfaceManager initialization."""

    def test_init_state_variables(self, px4_interface):
        """Test initial state variables."""
        assert px4_interface.current_yaw == 0.0
        assert px4_interface.current_pitch == 0.0
        assert px4_interface.current_roll == 0.0
        assert px4_interface.current_altitude == 0.0
        assert px4_interface.current_ground_speed == 0.0
        assert px4_interface.active_mode is False

    def test_init_setpoint_handler_created(self, px4_interface):
        """Test setpoint handler is created."""
        assert px4_interface.setpoint_handler is not None

    def test_init_mavlink_data_manager_set(self, px4_interface):
        """Test MAVLink data manager is set when USE_MAVLINK2REST is True."""
        assert px4_interface.mavlink_data_manager is not None


class TestPX4InterfaceManagerFlightModes:
    """Tests for flight mode definitions."""

    def test_flight_modes_dict(self, px4_interface):
        """Test flight modes dictionary is populated."""
        assert 393216 in px4_interface.FLIGHT_MODES
        assert px4_interface.FLIGHT_MODES[393216] == 'Offboard'

    def test_get_flight_mode_text_known(self, px4_interface):
        """Test getting text for known flight mode."""
        text = px4_interface.get_flight_mode_text(393216)
        assert text == 'Offboard'

    def test_get_flight_mode_text_unknown(self, px4_interface):
        """Test getting text for unknown flight mode."""
        text = px4_interface.get_flight_mode_text(999999)
        assert 'Unknown' in text

    def test_all_flight_modes_present(self, px4_interface):
        """Test all expected flight modes are defined."""
        expected_modes = [
            458752,   # Stabilized
            196608,   # Position
            100925440,  # Land
            393216,   # Offboard
            50593792,  # Hold
            84148224,  # Return
        ]
        for mode in expected_modes:
            assert mode in px4_interface.FLIGHT_MODES


class TestPX4InterfaceManagerConnection:
    """Tests for connection management."""

    @pytest.mark.asyncio
    async def test_connect_success(self, px4_interface, mock_parameters):
        """Test successful connection."""
        await px4_interface.connect()

        assert px4_interface.active_mode is True
        px4_interface.drone.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_circuit_breaker_active(self, mock_parameters, mock_mavsdk_system,
                                                        mock_setpoint_handler, mock_mavlink_data_manager,
                                                        mock_circuit_breaker_active):
        """Test connection blocked when circuit breaker active."""
        with patch('classes.px4_interface_manager.System', return_value=mock_mavsdk_system):
            with patch('classes.px4_interface_manager.SetpointHandler', return_value=mock_setpoint_handler):
                from classes.px4_interface_manager import PX4InterfaceManager

                mock_app_controller = MagicMock()
                mock_app_controller.mavlink_data_manager = mock_mavlink_data_manager

                interface = PX4InterfaceManager(app_controller=mock_app_controller)

                await interface.connect()

                # Should set active mode but not actually connect
                assert interface.active_mode is True
                mock_mavsdk_system.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_cancels_update_task(self, px4_interface):
        """Test that stop cancels update task."""
        import asyncio

        task_started = asyncio.Event()

        # Create a real asyncio task that handles cancellation like the real one
        async def dummy_task():
            task_started.set()
            try:
                await asyncio.sleep(10)  # Will be cancelled before this completes
            except asyncio.CancelledError:
                return  # Handle cancellation gracefully and return

        px4_interface.update_task = asyncio.create_task(dummy_task())

        # Ensure the task has started before stopping
        await task_started.wait()

        await px4_interface.stop()

        assert px4_interface.active_mode is False
        # Task should be done (completed after handling CancelledError)
        assert px4_interface.update_task.done()


class TestPX4InterfaceManagerTelemetry:
    """Tests for telemetry updates."""

    @pytest.mark.asyncio
    async def test_update_telemetry_via_mavlink2rest(self, px4_interface, mock_mavlink_data_manager):
        """Test telemetry update via MAVLink2REST."""
        mock_mavlink_data_manager.fetch_attitude_data.return_value = {
            'roll': 5.0,
            'pitch': 10.0,
            'yaw': 45.0
        }
        mock_mavlink_data_manager.fetch_altitude_data.return_value = {
            'altitude_relative': 50.0
        }
        mock_mavlink_data_manager.fetch_ground_speed.return_value = 5.0

        await px4_interface._update_telemetry_via_mavlink2rest()

        assert px4_interface.current_roll == 5.0
        assert px4_interface.current_pitch == 10.0
        assert px4_interface.current_yaw == 45.0
        assert px4_interface.current_altitude == 50.0
        assert px4_interface.current_ground_speed == 5.0

    def test_get_orientation(self, px4_interface):
        """Test get_orientation returns current values."""
        px4_interface.current_yaw = 45.0
        px4_interface.current_pitch = 10.0
        px4_interface.current_roll = 5.0

        yaw, pitch, roll = px4_interface.get_orientation()

        assert yaw == 45.0
        assert pitch == 10.0
        assert roll == 5.0

    def test_get_ground_speed(self, px4_interface):
        """Test get_ground_speed returns current value."""
        px4_interface.current_ground_speed = 15.0

        result = px4_interface.get_ground_speed()

        assert result == 15.0


class TestPX4InterfaceManagerOffboard:
    """Tests for offboard mode control."""

    @pytest.mark.asyncio
    async def test_start_offboard_mode_success(self, px4_interface):
        """Test starting offboard mode."""
        result = await px4_interface.start_offboard_mode()

        assert 'steps' in result
        px4_interface.drone.offboard.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_offboard_mode_with_circuit_breaker(self, mock_parameters, mock_mavsdk_system,
                                                              mock_setpoint_handler, mock_mavlink_data_manager,
                                                              mock_circuit_breaker_active):
        """Test start offboard blocked by circuit breaker."""
        with patch('classes.px4_interface_manager.System', return_value=mock_mavsdk_system):
            with patch('classes.px4_interface_manager.SetpointHandler', return_value=mock_setpoint_handler):
                from classes.px4_interface_manager import PX4InterfaceManager

                mock_app_controller = MagicMock()
                mock_app_controller.mavlink_data_manager = mock_mavlink_data_manager

                interface = PX4InterfaceManager(app_controller=mock_app_controller)
                interface.drone = mock_mavsdk_system

                result = await interface.start_offboard_mode()

                assert 'intercepted' in result['steps'][0].lower() or 'circuit breaker' in result['steps'][0].lower()
                mock_mavsdk_system.offboard.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_offboard_mode(self, px4_interface):
        """Test stopping offboard mode."""
        await px4_interface.stop_offboard_mode()

        px4_interface.drone.offboard.stop.assert_called_once()


class TestPX4InterfaceManagerVelocityCommands:
    """Tests for velocity body offboard commands."""

    @pytest.mark.asyncio
    async def test_send_velocity_body_offboard_commands(self, px4_interface, mock_setpoint_handler):
        """Test sending velocity body commands."""
        mock_setpoint_handler.get_fields.return_value = {
            'vel_body_fwd': 2.0,
            'vel_body_right': 1.0,
            'vel_body_down': -0.5,
            'yawspeed_deg_s': 15.0
        }

        await px4_interface.send_velocity_body_offboard_commands()

        px4_interface.drone.offboard.set_velocity_body.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_velocity_body_with_zero_values(self, px4_interface, mock_setpoint_handler):
        """Test sending zero velocity commands."""
        mock_setpoint_handler.get_fields.return_value = {
            'vel_body_fwd': 0.0,
            'vel_body_right': 0.0,
            'vel_body_down': 0.0,
            'yawspeed_deg_s': 0.0
        }

        await px4_interface.send_velocity_body_offboard_commands()

        px4_interface.drone.offboard.set_velocity_body.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_velocity_body_missing_handler(self, px4_interface):
        """Test handling missing setpoint handler."""
        px4_interface.setpoint_handler = None

        # Should not raise, just log error
        await px4_interface.send_velocity_body_offboard_commands()


class TestPX4InterfaceManagerAttitudeRateCommands:
    """Tests for attitude rate commands."""

    @pytest.mark.asyncio
    async def test_send_attitude_rate_commands(self, px4_interface, mock_setpoint_handler):
        """Test sending attitude rate commands."""
        mock_setpoint_handler.get_control_type.return_value = 'attitude_rate'
        mock_setpoint_handler.get_fields.return_value = {
            'rollspeed_deg_s': 10.0,
            'pitchspeed_deg_s': 5.0,
            'yawspeed_deg_s': 15.0,
            'thrust': 0.6
        }

        await px4_interface.send_attitude_rate_commands()

        px4_interface.drone.offboard.set_attitude_rate.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_attitude_rate_with_hover_throttle(self, px4_interface, mock_setpoint_handler):
        """Test attitude rate uses hover throttle as default."""
        px4_interface.hover_throttle = 0.5
        mock_setpoint_handler.get_control_type.return_value = 'attitude_rate'
        mock_setpoint_handler.get_fields.return_value = {
            'rollspeed_deg_s': 0.0,
            'pitchspeed_deg_s': 0.0,
            'yawspeed_deg_s': 0.0,
            # thrust not specified, should use hover_throttle
        }

        await px4_interface.send_attitude_rate_commands()

        px4_interface.drone.offboard.set_attitude_rate.assert_called_once()


class TestPX4InterfaceManagerUnifiedDispatch:
    """Tests for unified command dispatch."""

    @pytest.mark.asyncio
    async def test_send_commands_unified_velocity(self, px4_interface, mock_setpoint_handler):
        """Test unified dispatch for velocity commands."""
        mock_setpoint_handler.get_control_type.return_value = 'velocity_body_offboard'

        result = await px4_interface.send_commands_unified()

        assert result is True
        px4_interface.drone.offboard.set_velocity_body.assert_called()

    @pytest.mark.asyncio
    async def test_send_commands_unified_attitude(self, px4_interface, mock_setpoint_handler):
        """Test unified dispatch for attitude commands."""
        mock_setpoint_handler.get_control_type.return_value = 'attitude_rate'
        mock_setpoint_handler.get_fields.return_value = {
            'rollspeed_deg_s': 0.0,
            'pitchspeed_deg_s': 0.0,
            'yawspeed_deg_s': 0.0,
            'thrust': 0.5
        }

        result = await px4_interface.send_commands_unified()

        assert result is True
        px4_interface.drone.offboard.set_attitude_rate.assert_called()

    @pytest.mark.asyncio
    async def test_send_commands_unified_unknown_type(self, px4_interface, mock_setpoint_handler):
        """Test unified dispatch with unknown control type."""
        mock_setpoint_handler.get_control_type.return_value = 'unknown_type'

        result = await px4_interface.send_commands_unified()

        assert result is False


class TestPX4InterfaceManagerSafetyActions:
    """Tests for safety actions."""

    @pytest.mark.asyncio
    async def test_trigger_return_to_launch(self, px4_interface):
        """Test RTL trigger."""
        await px4_interface.trigger_return_to_launch()

        px4_interface.drone.action.return_to_launch.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_return_to_launch_with_circuit_breaker(self, mock_parameters, mock_mavsdk_system,
                                                                   mock_setpoint_handler, mock_mavlink_data_manager,
                                                                   mock_circuit_breaker_active):
        """Test RTL blocked by circuit breaker."""
        with patch('classes.px4_interface_manager.System', return_value=mock_mavsdk_system):
            with patch('classes.px4_interface_manager.SetpointHandler', return_value=mock_setpoint_handler):
                from classes.px4_interface_manager import PX4InterfaceManager

                mock_app_controller = MagicMock()
                mock_app_controller.mavlink_data_manager = mock_mavlink_data_manager

                interface = PX4InterfaceManager(app_controller=mock_app_controller)
                interface.drone = mock_mavsdk_system

                await interface.trigger_return_to_launch()

                mock_mavsdk_system.action.return_to_launch.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_failsafe(self, px4_interface):
        """Test failsafe triggers RTL."""
        await px4_interface.trigger_failsafe()

        px4_interface.drone.action.return_to_launch.assert_called_once()


class TestPX4InterfaceManagerHoverThrottle:
    """Tests for hover throttle management."""

    @pytest.mark.asyncio
    async def test_set_hover_throttle(self, px4_interface, mock_mavlink_data_manager):
        """Test setting hover throttle from telemetry."""
        mock_mavlink_data_manager.fetch_throttle_percent.return_value = 65

        await px4_interface.set_hover_throttle()

        assert px4_interface.hover_throttle == 0.65


class TestPX4InterfaceManagerValidation:
    """Tests for validation methods."""

    def test_validate_setpoint_compatibility_valid(self, px4_interface, mock_setpoint_handler):
        """Test validation passes for valid configuration."""
        mock_setpoint_handler.get_control_type.return_value = 'velocity_body_offboard'
        mock_setpoint_handler.get_fields.return_value = {
            'vel_body_fwd': 0.0,
            'vel_body_right': 0.0,
            'vel_body_down': 0.0
        }

        result = px4_interface.validate_setpoint_compatibility()

        assert result is True

    def test_validate_setpoint_compatibility_no_handler(self, px4_interface):
        """Test validation fails without handler."""
        px4_interface.setpoint_handler = None

        result = px4_interface.validate_setpoint_compatibility()

        assert result is False


class TestPX4InterfaceManagerCommandSummary:
    """Tests for command summary generation."""

    def test_get_command_summary(self, px4_interface, mock_setpoint_handler):
        """Test command summary generation."""
        summary = px4_interface.get_command_summary()

        assert 'control_type' in summary
        assert 'profile_name' in summary
        assert 'available_fields' in summary
        assert 'current_values' in summary

    def test_get_command_summary_no_handler(self, px4_interface):
        """Test summary with missing handler."""
        px4_interface.setpoint_handler = None

        summary = px4_interface.get_command_summary()

        assert 'error' in summary


class TestPX4InterfaceManagerSafeMAVSDKCall:
    """Tests for safe MAVSDK call wrapper."""

    @pytest.mark.asyncio
    async def test_safe_mavsdk_call_success(self, px4_interface):
        """Test successful MAVSDK call."""
        async_func = AsyncMock()

        result = await px4_interface._safe_mavsdk_call(async_func, "arg1", key="value")

        assert result is True
        async_func.assert_called_once_with("arg1", key="value")

    @pytest.mark.asyncio
    async def test_safe_mavsdk_call_retry_on_loop_error(self, px4_interface):
        """Test retry on async loop error."""
        call_count = 0

        async def failing_first_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("attached to a different loop")

        result = await px4_interface._safe_mavsdk_call(failing_first_call)

        assert result is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_safe_mavsdk_call_other_error(self, px4_interface):
        """Test handling of other errors."""
        async def failing_call(*args, **kwargs):
            raise ValueError("Some other error")

        result = await px4_interface._safe_mavsdk_call(failing_call)

        assert result is False


class TestPX4InterfaceManagerNEDConversion:
    """Tests for NED frame conversion."""

    def test_convert_to_ned_zero_yaw(self, px4_interface):
        """Test NED conversion with zero yaw."""
        ned_x, ned_y = px4_interface.convert_to_ned(1.0, 0.0, 0.0)

        assert abs(ned_x - 1.0) < 0.01
        assert abs(ned_y) < 0.01

    def test_convert_to_ned_90_deg_yaw(self, px4_interface):
        """Test NED conversion with 90 degree yaw."""
        ned_x, ned_y = px4_interface.convert_to_ned(1.0, 0.0, math.radians(90))

        assert abs(ned_x) < 0.01
        assert abs(ned_y - 1.0) < 0.01
