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
import time
from types import SimpleNamespace
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
    mock_system.core = MagicMock()

    async def connected_states():
        yield SimpleNamespace(is_connected=True)
        await asyncio.Event().wait()

    mock_system.core.connection_state.side_effect = connected_states
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
        mock_params.SYSTEM_ADDRESS = "udpin://0.0.0.0:14540"
        mock_params.EXTERNAL_MAVSDK_SERVER = True
        mock_params.MAVSDK_SERVER_ADDRESS = "127.0.0.1"
        mock_params.MAVSDK_SERVER_PORT = 50051
        mock_params.USE_MAVLINK2REST = True
        mock_params.FOLLOWER_MODE = "mc_velocity_offboard"
        mock_params.CAMERA_YAW_OFFSET = 0.0
        mock_params.FOLLOWER_DATA_REFRESH_RATE = 1
        mock_params.MAVSDK_CONNECTION_TIMEOUT_S = 1.0
        mock_params.MAVSDK_COMMAND_TIMEOUT_S = 1.0
        mock_params.MAVLINK_STALE_TIMEOUT_S = 2.0
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
            with patch('classes.px4_interface_manager.CIRCUIT_BREAKER_AVAILABLE', True):
                with patch('classes.px4_interface_manager.FollowerCircuitBreaker') as mock_cb:
                    mock_cb.is_active.return_value = False
                    mock_cb.log_command_instead_of_execute = MagicMock()
                    mock_cb.log_command_allowed = MagicMock()
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
        assert px4_interface.current_yaw is None
        assert px4_interface.current_pitch is None
        assert px4_interface.current_roll is None
        assert px4_interface.current_altitude is None
        assert px4_interface.current_ground_speed is None
        assert px4_interface.active_mode is False
        assert px4_interface.get_telemetry_readiness()["state"] == "idle"

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
        try:
            result = await px4_interface.connect()

            assert result["status"] == "connected"
            assert result["connected"] is True
            assert px4_interface.active_mode is True
            px4_interface.drone.connect.assert_awaited_once_with()
            px4_interface.drone.core.connection_state.assert_called_once_with()
        finally:
            px4_interface.active_mode = False
            await px4_interface._cancel_connection_monitor_task()
            await px4_interface._cancel_telemetry_update_task()

    @pytest.mark.asyncio
    async def test_embedded_server_connect_applies_vehicle_link(
        self,
        px4_interface,
        mock_parameters,
    ):
        """Only the embedded-server mode passes SYSTEM_ADDRESS from Python."""
        px4_interface._uses_external_mavsdk_server = False
        try:
            await px4_interface.connect()
            px4_interface.drone.connect.assert_awaited_once_with(
                system_address=mock_parameters.SYSTEM_ADDRESS
            )
        finally:
            px4_interface.active_mode = False
            await px4_interface._cancel_connection_monitor_task()
            await px4_interface._cancel_telemetry_update_task()

    @pytest.mark.asyncio
    async def test_live_connection_restarts_telemetry_when_requested_source_changes(
        self,
        px4_interface,
        mock_parameters,
    ):
        """Status and worker source must change together across follow sessions."""
        stop_event = asyncio.Event()
        source_started = asyncio.Event()
        observed_sources = []

        async def wait_forever():
            await stop_event.wait()

        async def replacement_worker(source, **_ownership):
            observed_sources.append(source)
            source_started.set()
            await stop_event.wait()

        px4_interface.active_mode = True
        px4_interface.connection_monitor_task = asyncio.create_task(wait_forever())
        px4_interface.update_task = asyncio.create_task(wait_forever())
        px4_interface._telemetry_source_active = "mavlink2rest"
        px4_interface._telemetry_source_requested = "mavlink2rest"
        px4_interface.update_drone_data = replacement_worker
        px4_interface.drone.connect.reset_mock()
        mock_parameters.USE_MAVLINK2REST = False

        try:
            status = await px4_interface.connect()
            await asyncio.wait_for(source_started.wait(), timeout=1.0)

            assert observed_sources == ["mavsdk"]
            assert status["telemetry_source"] == "mavsdk"
            assert status["telemetry_source_requested"] == "mavsdk"
            px4_interface.drone.connect.assert_not_awaited()
        finally:
            px4_interface.active_mode = False
            stop_event.set()
            await px4_interface._cancel_connection_monitor_task()
            await px4_interface._cancel_telemetry_update_task()

    @pytest.mark.asyncio
    async def test_missing_mavlink2rest_manager_fails_before_opening_vehicle_link(
        self,
        px4_interface,
        mock_parameters,
    ):
        """Telemetry dependency failure must leave explicit disconnected truth."""
        mock_parameters.USE_MAVLINK2REST = True
        px4_interface.app_controller = None
        del px4_interface.mavlink_data_manager

        with pytest.raises(RuntimeError, match="MavlinkDataManager is unavailable"):
            await px4_interface.connect()

        status = px4_interface.get_connection_status()
        assert status["status"] == "connection_failed"
        assert status["connected"] is False
        assert "Telemetry source preparation failed" in status["last_error"]
        assert status["telemetry_error"] == status["last_error"]
        assert px4_interface.update_task is None
        px4_interface.drone.connect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_live_source_reconfiguration_failure_preserves_working_telemetry(
        self,
        px4_interface,
        mock_parameters,
    ):
        """Invalid replacement source must not cancel the active telemetry worker."""
        stop_event = asyncio.Event()

        async def wait_forever():
            await stop_event.wait()

        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        px4_interface.connection_monitor_task = asyncio.create_task(wait_forever())
        original_update_task = asyncio.create_task(wait_forever())
        px4_interface.update_task = original_update_task
        px4_interface._telemetry_source_active = "mavsdk"
        px4_interface._telemetry_source_requested = "mavsdk"
        px4_interface.app_controller = None
        del px4_interface.mavlink_data_manager
        mock_parameters.USE_MAVLINK2REST = True

        try:
            with pytest.raises(RuntimeError, match="MavlinkDataManager is unavailable"):
                await px4_interface.connect()

            status = px4_interface.get_connection_status()
            assert status["status"] == "connected"
            assert status["telemetry_source_requested"] == "mavlink2rest"
            assert status["telemetry_source_active"] == "mavsdk"
            assert status["telemetry_update_running"] is True
            assert "Telemetry source preparation failed" in status["telemetry_error"]
            assert px4_interface.update_task is original_update_task
            px4_interface.drone.connect.assert_not_awaited()
        finally:
            px4_interface.active_mode = False
            stop_event.set()
            await px4_interface._cancel_connection_monitor_task()
            await px4_interface._cancel_telemetry_update_task()

    @pytest.mark.asyncio
    async def test_connect_with_circuit_breaker_active(self, mock_parameters, mock_mavsdk_system,
                                                        mock_setpoint_handler, mock_mavlink_data_manager,
                                                        mock_circuit_breaker_active):
        """Circuit breaker blocks commands, not connection or telemetry."""
        with patch('classes.px4_interface_manager.System', return_value=mock_mavsdk_system):
            with patch('classes.px4_interface_manager.SetpointHandler', return_value=mock_setpoint_handler):
                from classes.px4_interface_manager import PX4InterfaceManager

                mock_app_controller = MagicMock()
                mock_app_controller.mavlink_data_manager = mock_mavlink_data_manager

                interface = PX4InterfaceManager(app_controller=mock_app_controller)

                try:
                    result = await interface.connect()

                    assert result["connected"] is True
                    assert interface.active_mode is True
                    mock_mavsdk_system.connect.assert_awaited_once()
                    mock_circuit_breaker_active.is_active.assert_not_called()
                finally:
                    interface.active_mode = False
                    await interface._cancel_connection_monitor_task()
                    await interface._cancel_telemetry_update_task()

    @pytest.mark.asyncio
    async def test_connect_remains_available_when_command_gate_is_unavailable(
        self,
        mock_parameters,
        mock_mavsdk_system,
        mock_setpoint_handler,
        mock_mavlink_data_manager,
    ):
        """Command-gate availability must not suppress observational connection."""
        with patch('classes.px4_interface_manager.System', return_value=mock_mavsdk_system):
            with patch('classes.px4_interface_manager.SetpointHandler', return_value=mock_setpoint_handler):
                with patch('classes.px4_interface_manager.CIRCUIT_BREAKER_AVAILABLE', False):
                    from classes.px4_interface_manager import PX4InterfaceManager

                    mock_app_controller = MagicMock()
                    mock_app_controller.mavlink_data_manager = mock_mavlink_data_manager
                    interface = PX4InterfaceManager(app_controller=mock_app_controller)

                    try:
                        result = await interface.connect()

                        assert result["connected"] is True
                        assert interface.active_mode is True
                        mock_mavsdk_system.connect.assert_awaited_once()
                    finally:
                        interface.active_mode = False
                        await interface._cancel_connection_monitor_task()
                        await interface._cancel_telemetry_update_task()

    @pytest.mark.asyncio
    async def test_connect_times_out_without_vehicle_discovery(
        self,
        px4_interface,
        mock_parameters,
    ):
        """Opening a link is not success when MAVSDK never discovers a vehicle."""
        mock_parameters.MAVSDK_CONNECTION_TIMEOUT_S = 0.01

        async def never_discovers_vehicle():
            await asyncio.Event().wait()

        px4_interface._wait_for_mavsdk_connection = never_discovers_vehicle

        with pytest.raises(TimeoutError, match="did not discover a PX4 vehicle"):
            await px4_interface.connect()

        status = px4_interface.get_connection_status()
        assert status["status"] == "connection_failed"
        assert status["connected"] is False
        assert "did not discover" in status["last_error"]
        assert px4_interface.update_task is None

    @pytest.mark.asyncio
    async def test_connect_cancellation_restores_disconnected_state(
        self,
        px4_interface,
    ):
        """Operator abort must not leave the connection state at connecting."""
        entered = asyncio.Event()

        async def never_discovers_vehicle():
            entered.set()
            await asyncio.Event().wait()

        px4_interface._wait_for_mavsdk_connection = never_discovers_vehicle
        task = asyncio.create_task(px4_interface.connect())
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        status = px4_interface.get_connection_status()
        assert status["status"] == "disconnected"
        assert status["connected"] is False
        assert status["last_error"] == "MAVSDK connection attempt canceled"

    @pytest.mark.asyncio
    async def test_connect_reuses_verified_connection_and_telemetry_task(
        self,
        px4_interface,
    ):
        """Follow stop/start must not fail on the still-owned telemetry task."""
        try:
            first = await px4_interface.connect()
            telemetry_task = px4_interface.update_task
            second = await px4_interface.connect()

            assert first["connected"] is True
            assert second["connected"] is True
            assert px4_interface.update_task is telemetry_task
            px4_interface.drone.connect.assert_awaited_once()
        finally:
            px4_interface.active_mode = False
            await px4_interface._cancel_connection_monitor_task()
            await px4_interface._cancel_telemetry_update_task()

    @pytest.mark.asyncio
    async def test_connection_monitor_marks_loss_and_notifies_lifecycle_owner(
        self,
        px4_interface,
    ):
        """A post-discovery disconnect must revoke connection truth and notify."""
        subscription_count = 0
        release_disconnect = asyncio.Event()
        connection_lost = AsyncMock()

        async def connection_states():
            nonlocal subscription_count
            subscription_count += 1
            yield SimpleNamespace(is_connected=True)
            if subscription_count >= 2:
                await release_disconnect.wait()
                yield SimpleNamespace(is_connected=False)
            else:
                await asyncio.Event().wait()

        px4_interface.drone.core.connection_state.side_effect = connection_states
        px4_interface._on_connection_lost = connection_lost

        try:
            await px4_interface.connect()
            for _ in range(100):
                if subscription_count >= 2:
                    break
                await asyncio.sleep(0.001)
            else:
                pytest.fail("MAVSDK connection monitor did not subscribe")

            release_disconnect.set()
            for _ in range(100):
                if not px4_interface.active_mode:
                    break
                await asyncio.sleep(0.001)
            else:
                pytest.fail("MAVSDK disconnect did not revoke connection state")

            status = px4_interface.get_connection_status()
            assert status["status"] == "connection_lost"
            assert status["connected"] is False
            assert "disconnected" in status["last_error"]
            assert status["telemetry_update_running"] is False
            connection_lost.assert_awaited_once()
            assert connection_lost.await_args.args[0]["status"] == "connection_lost"
        finally:
            px4_interface.active_mode = False
            await px4_interface._cancel_connection_monitor_task()
            await px4_interface._cancel_telemetry_update_task()

    @pytest.mark.asyncio
    async def test_superseded_connection_monitor_cannot_invalidate_reconnect(
        self,
        px4_interface,
    ):
        """A late disconnect event belongs only to the monitor that observed it."""
        subscribed = asyncio.Event()
        release_disconnect = asyncio.Event()

        async def old_connection_states():
            yield SimpleNamespace(is_connected=True)
            subscribed.set()
            await release_disconnect.wait()
            yield SimpleNamespace(is_connected=False)

        px4_interface.drone.core.connection_state.side_effect = old_connection_states
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        old_generation = px4_interface.connection_generation
        old_monitor = asyncio.create_task(
            px4_interface._monitor_mavsdk_connection(old_generation)
        )
        await asyncio.wait_for(subscribed.wait(), timeout=1.0)

        px4_interface._advance_connection_generation()
        new_generation = px4_interface.connection_generation
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        release_disconnect.set()
        await asyncio.wait_for(old_monitor, timeout=1.0)

        assert px4_interface.connection_generation == new_generation
        assert px4_interface.active_mode is True
        assert px4_interface._connection_state == "connected"

    @pytest.mark.asyncio
    async def test_stop_reports_cleanup_failed_and_preserves_resistant_task(
        self,
        px4_interface,
    ):
        cancellation_seen = asyncio.Event()
        release = asyncio.Event()

        async def resistant_telemetry_owner():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellation_seen.set()
                await release.wait()

        px4_interface.DEFAULT_OWNED_TASK_STOP_TIMEOUT_S = 0.01
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        telemetry_owner = asyncio.create_task(resistant_telemetry_owner())
        px4_interface.update_task = telemetry_owner
        await asyncio.sleep(0)

        outcome = await px4_interface.stop()

        assert cancellation_seen.is_set()
        assert outcome["status"] == "cleanup_failed"
        assert outcome["cleanup_failed"] is True
        assert outcome["owned_tasks"]["telemetry_supervisor_alive"] is True
        assert px4_interface.update_task is telemetry_owner
        assert telemetry_owner.done() is False
        status = px4_interface.get_connection_status()
        assert status["status"] == "cleanup_failed"
        assert status["connected"] is False
        assert status["cleanup_failed"] is True
        assert px4_interface.is_command_connection_ready(
            require_fresh_telemetry=False
        ) is False

        release.set()
        await telemetry_owner
        retry = await px4_interface.stop()
        assert retry["status"] == "disconnected"
        assert retry["cleanup_failed"] is False

    @pytest.mark.asyncio
    async def test_cancellation_timeout_refuses_telemetry_replacement(
        self,
        px4_interface,
        mock_parameters,
    ):
        cancellation_seen = asyncio.Event()
        release = asyncio.Event()

        async def resistant_telemetry_owner():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellation_seen.set()
                await release.wait()

        async def monitor_owner():
            await asyncio.Event().wait()

        px4_interface.DEFAULT_OWNED_TASK_STOP_TIMEOUT_S = 0.01
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        px4_interface._telemetry_source_active = "mavlink2rest"
        px4_interface.connection_monitor_task = asyncio.create_task(monitor_owner())
        original_owner = asyncio.create_task(resistant_telemetry_owner())
        px4_interface.update_task = original_owner
        mock_parameters.USE_MAVLINK2REST = False
        await asyncio.sleep(0)

        with pytest.raises(RuntimeError, match="previous telemetry owner did not stop"):
            await px4_interface.connect()

        assert cancellation_seen.is_set()
        assert px4_interface.update_task is original_owner
        assert original_owner.done() is False
        assert px4_interface.get_connection_status()["cleanup_failed"] is True

        release.set()
        await original_owner
        await px4_interface._cancel_connection_monitor_task()

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
        px4_interface.drone.offboard.stop.assert_not_called()


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

        px4_interface.active_mode = True
        px4_interface._reset_telemetry_health("mavlink2rest")
        updated = await px4_interface._update_telemetry_via_mavlink2rest()

        assert updated is True
        assert px4_interface.current_roll == 5.0
        assert px4_interface.current_pitch == 10.0
        assert px4_interface.current_yaw == 45.0
        assert px4_interface.current_altitude == 50.0
        assert px4_interface.current_ground_speed == 5.0
        assert px4_interface.get_telemetry_readiness()["ready"] is True

    @pytest.mark.asyncio
    async def test_mavlink2rest_partial_sample_preserves_last_complete_snapshot(
        self,
        px4_interface,
        mock_mavlink_data_manager,
    ):
        """One missing field cannot partially overwrite follower telemetry."""
        px4_interface.active_mode = True
        px4_interface._reset_telemetry_health("mavlink2rest")
        px4_interface._commit_telemetry_snapshot(
            {
                "roll_deg": 1.0,
                "pitch_deg": 2.0,
                "yaw_deg": 3.0,
                "relative_altitude_m": 40.0,
                "ground_speed_m_s": 5.0,
            }
        )
        mock_mavlink_data_manager.fetch_attitude_data.return_value = None
        mock_mavlink_data_manager.fetch_altitude_data.return_value = {
            "altitude_relative": 99.0,
            "altitude_amsl": 199.0,
        }
        mock_mavlink_data_manager.fetch_ground_speed.return_value = 20.0

        updated = await px4_interface._update_telemetry_via_mavlink2rest()

        assert updated is False
        assert px4_interface.current_roll == 1.0
        assert px4_interface.current_altitude == 40.0
        assert px4_interface.current_ground_speed == 5.0
        assert "attitude payload unavailable" in px4_interface._last_telemetry_error

    def test_superseded_telemetry_generation_cannot_commit_over_new_connection(
        self,
        px4_interface,
    ):
        """A late producer from an old link cannot publish into a reconnect."""
        px4_interface.active_mode = True
        old_connection = px4_interface.connection_generation
        old_telemetry = px4_interface._reset_telemetry_health(
            "mavlink2rest",
            connection_generation=old_connection,
        )

        px4_interface._advance_connection_generation()
        new_connection = px4_interface.connection_generation
        new_telemetry = px4_interface._reset_telemetry_health(
            "mavsdk",
            connection_generation=new_connection,
        )
        assert px4_interface._commit_telemetry_snapshot(
            {
                "roll_deg": 10.0,
                "pitch_deg": 20.0,
                "yaw_deg": 30.0,
                "relative_altitude_m": 40.0,
                "ground_speed_m_s": 50.0,
            },
            connection_generation=new_connection,
            telemetry_generation=new_telemetry,
        ) is True

        committed = px4_interface._commit_telemetry_snapshot(
            {
                "roll_deg": -1.0,
                "pitch_deg": -2.0,
                "yaw_deg": -3.0,
                "relative_altitude_m": -4.0,
                "ground_speed_m_s": -5.0,
            },
            connection_generation=old_connection,
            telemetry_generation=old_telemetry,
        )

        assert committed is False
        assert px4_interface.current_roll == 10.0
        assert px4_interface.current_altitude == 40.0
        readiness = px4_interface.get_telemetry_readiness()
        assert readiness["telemetry_generation"] == new_telemetry
        assert readiness["owner_current"] is True

    @pytest.mark.asyncio
    async def test_mavlink2rest_cycle_fetches_all_messages_concurrently(
        self,
        px4_interface,
        mock_mavlink_data_manager,
    ):
        """The cycle deadline covers three concurrent requests, not a serial chain."""
        started = set()
        all_started = asyncio.Event()
        release = asyncio.Event()

        async def fetch(name, value):
            started.add(name)
            if len(started) == 3:
                all_started.set()
            await release.wait()
            return value

        async def fetch_attitude():
            return await fetch(
                "attitude",
                {"roll": 1.0, "pitch": 2.0, "yaw": 3.0},
            )

        async def fetch_altitude():
            return await fetch(
                "altitude",
                {"altitude_relative": 4.0, "altitude_amsl": 104.0},
            )

        async def fetch_ground_speed():
            return await fetch("ground_speed", 5.0)

        mock_mavlink_data_manager.fetch_attitude_data.side_effect = fetch_attitude
        mock_mavlink_data_manager.fetch_altitude_data.side_effect = fetch_altitude
        mock_mavlink_data_manager.fetch_ground_speed.side_effect = fetch_ground_speed
        px4_interface.active_mode = True
        telemetry_generation = px4_interface._reset_telemetry_health(
            "mavlink2rest"
        )

        update = asyncio.create_task(
            px4_interface._update_telemetry_via_mavlink2rest(
                connection_generation=px4_interface.connection_generation,
                telemetry_generation=telemetry_generation,
            )
        )
        await asyncio.wait_for(all_started.wait(), timeout=1.0)
        assert started == {"attitude", "altitude", "ground_speed"}
        release.set()

        assert await update is True
        assert px4_interface.current_ground_speed == 5.0

    @pytest.mark.asyncio
    async def test_mavlink2rest_rejects_temporally_skewed_cycle(
        self,
        px4_interface,
        mock_mavlink_data_manager,
    ):
        """Individually valid messages cannot form an incoherent snapshot."""
        async def delayed_altitude():
            await asyncio.sleep(0.02)
            return {"altitude_relative": 99.0, "altitude_amsl": 199.0}

        mock_mavlink_data_manager.fetch_attitude_data.return_value = {
            "roll": 1.0,
            "pitch": 2.0,
            "yaw": 3.0,
        }
        mock_mavlink_data_manager.fetch_altitude_data.side_effect = delayed_altitude
        mock_mavlink_data_manager.fetch_ground_speed.return_value = 8.0
        px4_interface.get_telemetry_max_skew_s = MagicMock(return_value=0.005)
        px4_interface.active_mode = True
        telemetry_generation = px4_interface._reset_telemetry_health(
            "mavlink2rest"
        )

        updated = await px4_interface._update_telemetry_via_mavlink2rest(
            connection_generation=px4_interface.connection_generation,
            telemetry_generation=telemetry_generation,
        )

        assert updated is False
        assert px4_interface.current_altitude is None
        assert "completion skew" in px4_interface._last_telemetry_error

    @pytest.mark.asyncio
    async def test_mavlink2rest_cycle_has_one_bounded_deadline(
        self,
        px4_interface,
        mock_mavlink_data_manager,
    ):
        async def never_returns():
            await asyncio.Event().wait()

        mock_mavlink_data_manager.fetch_attitude_data.side_effect = never_returns
        px4_interface.get_mavlink2rest_cycle_timeout_s = MagicMock(
            return_value=0.01
        )
        px4_interface.active_mode = True
        telemetry_generation = px4_interface._reset_telemetry_health(
            "mavlink2rest"
        )

        updated = await px4_interface._update_telemetry_via_mavlink2rest(
            connection_generation=px4_interface.connection_generation,
            telemetry_generation=telemetry_generation,
        )

        assert updated is False
        assert "cycle exceeded" in px4_interface._last_telemetry_error

    def test_mavsdk_snapshot_requires_current_generation_and_bounded_skew(
        self,
        px4_interface,
    ):
        px4_interface.active_mode = True
        connection_generation = px4_interface.connection_generation
        telemetry_generation = px4_interface._reset_telemetry_health("mavsdk")
        px4_interface._telemetry_pending_values = {
            "roll_deg": 1.0,
            "pitch_deg": 2.0,
            "yaw_deg": 3.0,
            "relative_altitude_m": 4.0,
            "ground_speed_m_s": 5.0,
        }
        now = time.monotonic()
        for status in px4_interface._telemetry_stream_status.values():
            status["last_update_monotonic_s"] = now

        px4_interface._telemetry_stream_status["position"][
            "telemetry_generation"
        ] = telemetry_generation - 1
        assert px4_interface._try_commit_mavsdk_telemetry_snapshot(
            connection_generation=connection_generation,
            telemetry_generation=telemetry_generation,
        ) is False

        px4_interface._telemetry_stream_status["position"][
            "telemetry_generation"
        ] = telemetry_generation
        px4_interface._telemetry_stream_status["position"][
            "last_update_monotonic_s"
        ] = now - 0.5
        assert px4_interface._try_commit_mavsdk_telemetry_snapshot(
            connection_generation=connection_generation,
            telemetry_generation=telemetry_generation,
        ) is False
        assert "stream skew" in px4_interface._last_telemetry_error

        for status in px4_interface._telemetry_stream_status.values():
            status["last_update_monotonic_s"] = time.monotonic()
        assert px4_interface._try_commit_mavsdk_telemetry_snapshot(
            connection_generation=connection_generation,
            telemetry_generation=telemetry_generation,
        ) is True

    def test_stale_telemetry_blocks_ordinary_command_ownership(
        self,
        px4_interface,
        mock_parameters,
    ):
        """A live link cannot remain command-ready after telemetry expires."""
        mock_parameters.MAVLINK_STALE_TIMEOUT_S = 0.1
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        px4_interface._reset_telemetry_health("mavsdk")
        px4_interface._commit_telemetry_snapshot(
            {
                "roll_deg": 0.0,
                "pitch_deg": 0.0,
                "yaw_deg": 0.0,
                "relative_altitude_m": 25.0,
                "ground_speed_m_s": 0.0,
            }
        )
        px4_interface._telemetry_last_complete_sample_monotonic_s -= 1.0

        readiness = px4_interface.get_telemetry_readiness()

        assert readiness["state"] == "stale"
        assert readiness["ready"] is False
        assert px4_interface.is_command_connection_ready() is False
        assert px4_interface.is_command_connection_ready(
            require_fresh_telemetry=False
        ) is True

    @pytest.mark.asyncio
    async def test_wait_for_telemetry_ready_reports_bounded_failure(
        self,
        px4_interface,
    ):
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        px4_interface._reset_telemetry_health("mavsdk")

        readiness = await px4_interface.wait_for_telemetry_ready(timeout_s=0.001)

        assert readiness["state"] == "failed"
        assert readiness["ready"] is False
        assert "No complete follower telemetry" in readiness["last_error"]

    @pytest.mark.asyncio
    async def test_owned_task_cancellation_timeout_is_bounded(
        self,
        px4_interface,
    ):
        """A cancellation-resistant child cannot hang PX4 shutdown forever."""
        cancellation_seen = asyncio.Event()
        release = asyncio.Event()

        async def resistant_task():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellation_seen.set()
                await release.wait()

        px4_interface.DEFAULT_OWNED_TASK_STOP_TIMEOUT_S = 0.01
        task = asyncio.create_task(resistant_task())
        await asyncio.sleep(0)

        stopped = await px4_interface._cancel_owned_task(task, label="unit child")

        assert stopped is False
        assert cancellation_seen.is_set()
        assert task.done() is False
        release.set()
        await task

    @pytest.mark.asyncio
    async def test_owned_task_cancellation_does_not_swallow_parent_cancel(
        self,
        px4_interface,
    ):
        cancellation_seen = asyncio.Event()
        release = asyncio.Event()

        async def resistant_task():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellation_seen.set()
                await release.wait()

        owned = asyncio.create_task(resistant_task())
        await asyncio.sleep(0)
        waiter = asyncio.create_task(
            px4_interface._cancel_owned_task(owned, label="unit child")
        )
        await asyncio.wait_for(cancellation_seen.wait(), timeout=1.0)
        waiter.cancel()

        with pytest.raises(asyncio.CancelledError):
            await waiter

        release.set()
        await owned

    @pytest.mark.asyncio
    async def test_mavsdk_streams_update_concurrently_with_sdk_field_names(
        self,
        px4_interface,
        mock_parameters,
    ):
        """Position, attitude, and velocity must not starve one another."""
        mock_parameters.USE_MAVLINK2REST = False
        mock_parameters.CAMERA_YAW_OFFSET = 7.0
        px4_interface.camera_yaw_offset = 7.0

        async def stream(sample):
            while True:
                yield sample
                await asyncio.sleep(0.001)

        px4_interface.drone.telemetry.position.side_effect = lambda: stream(
            SimpleNamespace(relative_altitude_m=42.5)
        )
        px4_interface.drone.telemetry.attitude_euler.side_effect = lambda: stream(
            SimpleNamespace(roll_deg=1.5, pitch_deg=-2.5, yaw_deg=90.0)
        )
        px4_interface.drone.telemetry.velocity_body.side_effect = lambda: stream(
            SimpleNamespace(x_m_s=3.0, y_m_s=4.0, z_m_s=0.0)
        )

        px4_interface.active_mode = True
        px4_interface._reset_telemetry_health("mavsdk")
        px4_interface.update_task = asyncio.create_task(px4_interface.update_drone_data())
        try:
            async def all_streams_sampled():
                return all(
                    status["sample_count"] > 0
                    for status in px4_interface._telemetry_stream_status.values()
                )

            for _ in range(100):
                if await all_streams_sampled():
                    break
                await asyncio.sleep(0.002)
            else:
                pytest.fail("MAVSDK telemetry streams did not all produce samples")

            assert px4_interface.current_altitude == pytest.approx(42.5)
            assert px4_interface.current_roll == pytest.approx(1.5)
            assert px4_interface.current_pitch == pytest.approx(-2.5)
            assert px4_interface.current_yaw == pytest.approx(97.0)
            assert px4_interface.current_ground_speed == pytest.approx(5.0)
            assert px4_interface.get_telemetry_readiness()["ready"] is True
            assert px4_interface.get_connection_status()["telemetry_update_running"] is True
        finally:
            px4_interface.active_mode = False
            await px4_interface._cancel_connection_monitor_task()
            await px4_interface._cancel_telemetry_update_task()

        assert px4_interface._telemetry_stream_tasks == {}
        assert all(
            status["state"] == "cancelled"
            for status in px4_interface._telemetry_stream_status.values()
        )

    @pytest.mark.asyncio
    async def test_failed_mavsdk_stream_retries_without_stopping_peer_streams(
        self,
        px4_interface,
        mock_parameters,
    ):
        """A failed telemetry subscription must not stop unrelated telemetry."""
        mock_parameters.USE_MAVLINK2REST = False
        position_subscriptions = 0

        async def position_stream():
            nonlocal position_subscriptions
            position_subscriptions += 1
            if position_subscriptions == 1:
                raise RuntimeError("transient position subscription failure")
            while True:
                yield SimpleNamespace(relative_altitude_m=25.0)
                await asyncio.sleep(0.001)

        async def attitude_stream():
            while True:
                yield SimpleNamespace(roll_deg=2.0, pitch_deg=3.0, yaw_deg=4.0)
                await asyncio.sleep(0.001)

        async def velocity_stream():
            while True:
                yield SimpleNamespace(x_m_s=6.0, y_m_s=8.0, z_m_s=0.0)
                await asyncio.sleep(0.001)

        px4_interface.drone.telemetry.position.side_effect = position_stream
        px4_interface.drone.telemetry.attitude_euler.side_effect = attitude_stream
        px4_interface.drone.telemetry.velocity_body.side_effect = velocity_stream
        px4_interface.MIN_MAVSDK_STREAM_RETRY_DELAY_S = 0.001
        px4_interface.get_follower_data_refresh_period_s = MagicMock(return_value=0.001)

        px4_interface.active_mode = True
        px4_interface._reset_telemetry_health("mavsdk")
        px4_interface.update_task = asyncio.create_task(px4_interface.update_drone_data())
        try:
            for _ in range(200):
                if (
                    position_subscriptions >= 2
                    and px4_interface.current_altitude == 25.0
                    and px4_interface.current_ground_speed == 10.0
                ):
                    break
                await asyncio.sleep(0.002)
            else:
                pytest.fail("Failed MAVSDK stream did not recover independently")

            assert px4_interface._telemetry_stream_status["position"]["restart_count"] == 1
            assert px4_interface._telemetry_stream_status["attitude"]["sample_count"] > 0
            assert px4_interface._telemetry_stream_status["velocity_body"]["sample_count"] > 0
        finally:
            px4_interface.active_mode = False
            await px4_interface._cancel_telemetry_update_task()

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

    def test_follower_data_refresh_rate_is_hz(self, px4_interface, mock_parameters):
        """FOLLOWER_DATA_REFRESH_RATE is Hz and converts to a sleep period."""
        mock_parameters.FOLLOWER_DATA_REFRESH_RATE = 5.0

        assert px4_interface.get_follower_data_refresh_rate_hz() == 5.0
        assert px4_interface.get_follower_data_refresh_period_s() == pytest.approx(0.2)

    def test_telemetry_stale_timeout_is_runtime_bounded_to_five_seconds(
        self,
        px4_interface,
        mock_parameters,
    ):
        mock_parameters.MAVLINK_STALE_TIMEOUT_S = 120.0

        assert px4_interface.get_telemetry_stale_timeout_s() == 5.0

    def test_follower_data_refresh_rate_invalid_uses_default(self, px4_interface, mock_parameters):
        """Invalid telemetry refresh values fall back to the safe default rate."""
        mock_parameters.FOLLOWER_DATA_REFRESH_RATE = 0

        assert px4_interface.get_follower_data_refresh_rate_hz() == 5.0
        assert px4_interface.get_follower_data_refresh_period_s() == pytest.approx(0.2)

    def test_follower_data_refresh_rate_clamps_high_value(self, px4_interface, mock_parameters):
        """Excessive telemetry refresh rates are bounded before conversion."""
        mock_parameters.FOLLOWER_DATA_REFRESH_RATE = 1000.0

        assert px4_interface.get_follower_data_refresh_rate_hz() == 100.0
        assert px4_interface.get_follower_data_refresh_period_s() == pytest.approx(0.01)

    @pytest.mark.parametrize(
        "raw_rate, expected_hz",
        [
            ("2.5", 2.5),
            (None, 5.0),
            ("not-a-rate", 5.0),
            (-1.0, 5.0),
            (math.nan, 5.0),
            (math.inf, 5.0),
            (0.05, 0.1),
            (1000.0, 100.0),
        ],
    )
    def test_follower_data_refresh_rate_validation_matrix(
        self,
        px4_interface,
        mock_parameters,
        raw_rate,
        expected_hz,
    ):
        """Telemetry refresh rate validation handles strings, bounds, and non-finite values."""
        mock_parameters.FOLLOWER_DATA_REFRESH_RATE = raw_rate

        assert px4_interface.get_follower_data_refresh_rate_hz() == pytest.approx(expected_hz)
        assert px4_interface.get_follower_data_refresh_period_s() == pytest.approx(1.0 / expected_hz)

    def test_follower_data_refresh_rate_invalid_value_logs_warning(
        self,
        px4_interface,
        mock_parameters,
        caplog,
    ):
        """Invalid telemetry refresh config emits a visible warning."""
        mock_parameters.FOLLOWER_DATA_REFRESH_RATE = "bad-rate"

        with caplog.at_level("WARNING"):
            rate_hz = px4_interface.get_follower_data_refresh_rate_hz()

        assert rate_hz == 5.0
        assert "Invalid FOLLOWER_DATA_REFRESH_RATE" in caplog.text

    @pytest.mark.asyncio
    async def test_update_drone_data_sleeps_using_hz_conversion(
        self,
        px4_interface,
        mock_parameters,
    ):
        """The background telemetry loop sleeps for 1 / configured Hz."""
        mock_parameters.USE_MAVLINK2REST = True
        mock_parameters.FOLLOWER_DATA_REFRESH_RATE = 5.0
        px4_interface.active_mode = True
        px4_interface._reset_telemetry_health("mavlink2rest")

        async def update_once(**_ownership):
            px4_interface.active_mode = False

        px4_interface._update_telemetry_via_mavlink2rest = AsyncMock(side_effect=update_once)

        with patch('classes.px4_interface_manager.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await px4_interface.update_drone_data()

        mock_sleep.assert_awaited_once()
        assert mock_sleep.await_args.args[0] == pytest.approx(0.2)


class TestPX4InterfaceManagerOffboard:
    """Tests for offboard mode control."""

    @pytest.fixture(autouse=True)
    def _complete_telemetry_sample(self, px4_interface):
        px4_interface._reset_telemetry_health("mavlink2rest")
        px4_interface._commit_telemetry_snapshot(
            {
                "roll_deg": 0.0,
                "pitch_deg": 0.0,
                "yaw_deg": 0.0,
                "relative_altitude_m": 50.0,
                "ground_speed_m_s": 0.0,
            }
        )

    @pytest.mark.asyncio
    async def test_start_offboard_mode_success(self, px4_interface):
        """Actual mode entry primes a default setpoint before MAVSDK start."""
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        with patch(
            'classes.px4_interface_manager.asyncio.sleep',
            new_callable=AsyncMock,
        ) as sleep:
            result = await px4_interface.start_offboard_mode()

        assert 'steps' in result
        assert result['status'] == 'executed'
        assert result['executed'] is True
        assert result['simulated'] is False
        px4_interface.setpoint_handler.reset_setpoints.assert_called_once_with()
        px4_interface.drone.offboard.set_velocity_body.assert_awaited_once()
        sleep.assert_awaited_once_with(px4_interface.OFFBOARD_PRIME_DURATION_S)
        px4_interface.drone.offboard.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_offboard_mode_fails_closed_without_connection(self, px4_interface):
        """Live Offboard entry requires a confirmed MAVSDK vehicle connection."""
        result = await px4_interface.start_offboard_mode()

        assert result['status'] == 'blocked'
        assert result['reason'] == 'mavsdk_not_connected'
        assert result['degraded'] is True
        px4_interface.drone.offboard.set_velocity_body.assert_not_called()
        px4_interface.drone.offboard.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_offboard_mode_fails_closed_without_fresh_telemetry(
        self,
        px4_interface,
    ):
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        px4_interface._telemetry_last_complete_sample_monotonic_s = None
        px4_interface._telemetry_ready_event.clear()
        px4_interface._set_telemetry_state("starting")

        result = await px4_interface.start_offboard_mode()

        assert result["status"] == "blocked"
        assert result["reason"] == "telemetry_starting"
        px4_interface.drone.offboard.set_velocity_body.assert_not_called()
        px4_interface.drone.offboard.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_offboard_mode_does_not_start_when_priming_fails(
        self,
        px4_interface,
    ):
        """A failed initial setpoint must prevent mode entry."""
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        px4_interface.send_commands_unified = AsyncMock(return_value=False)

        result = await px4_interface.start_offboard_mode()

        assert result['status'] == 'failed'
        assert result['reason'] == 'mavsdk_action_failed'
        assert any('initial' in error.lower() for error in result['errors'])
        px4_interface.drone.offboard.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_offboard_mode_refuses_start_after_link_loss_during_priming(
        self,
        px4_interface,
    ):
        """A disconnect during the priming interval must prevent mode entry."""
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"

        async def lose_connection(_duration):
            px4_interface.active_mode = False

        with patch(
            'classes.px4_interface_manager.asyncio.sleep',
            side_effect=lose_connection,
        ):
            result = await px4_interface.start_offboard_mode()

        assert result['status'] == 'failed'
        assert any('lost while priming' in error for error in result['errors'])
        px4_interface.drone.offboard.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_offboard_mode_refuses_stale_telemetry_after_priming(
        self,
        px4_interface,
        mock_parameters,
    ):
        """Telemetry must remain fresh through the complete priming interval."""
        mock_parameters.MAVLINK_STALE_TIMEOUT_S = 0.1
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"

        async def expire_telemetry(_duration):
            px4_interface._telemetry_last_complete_sample_monotonic_s -= 1.0

        with patch(
            'classes.px4_interface_manager.asyncio.sleep',
            side_effect=expire_telemetry,
        ):
            result = await px4_interface.start_offboard_mode()

        assert result["status"] == "failed"
        assert any("became unavailable" in error for error in result["errors"])
        px4_interface.drone.offboard.start.assert_not_called()
        px4_interface.drone.offboard.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_offboard_mode_reports_completed_action_then_link_loss(
        self,
        px4_interface,
    ):
        """A completed start followed by immediate loss must not activate Follow."""
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"

        async def start_then_lose_connection():
            px4_interface.active_mode = False

        px4_interface.drone.offboard.start.side_effect = start_then_lose_connection
        with patch(
            'classes.px4_interface_manager.asyncio.sleep',
            new_callable=AsyncMock,
        ):
            result = await px4_interface.start_offboard_mode()

        assert result['status'] == 'executed'
        assert result['executed'] is True
        assert result['degraded'] is True
        assert result['reason'] == 'mavsdk_action_acknowledged_then_link_lost'
        assert result['errors']

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
                assert result['status'] == 'simulated'
                assert result['executed'] is False
                assert result['simulated'] is True
                assert result['reason'] == 'circuit_breaker_active'
                mock_setpoint_handler.reset_setpoints.assert_not_called()
                mock_mavsdk_system.offboard.set_velocity_body.assert_not_called()
                mock_mavsdk_system.offboard.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_rechecks_gate_after_priming_and_quiesces_sender(
        self,
        px4_interface,
    ):
        """A breaker transition during priming must prevent mode entry."""
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"
        with patch(
            "classes.px4_interface_manager.FollowerCircuitBreaker"
        ) as circuit_breaker, patch(
            "classes.px4_interface_manager.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            circuit_breaker.is_active.side_effect = [False, False, True]
            circuit_breaker.log_command_allowed = MagicMock()
            circuit_breaker.log_command_instead_of_execute = MagicMock()
            result = await px4_interface.start_offboard_mode()

        assert result["status"] == "simulated"
        assert result["reason"] == "circuit_breaker_active"
        px4_interface.drone.offboard.start.assert_not_awaited()
        px4_interface.drone.offboard.stop.assert_awaited_once()
        assert px4_interface._mavsdk_offboard_sender_state == "quiesced"

    @pytest.mark.asyncio
    async def test_failed_start_quiesces_primed_mavsdk_sender(
        self,
        px4_interface,
        mock_parameters,
    ):
        """A hung start RPC must not leave MAVSDK retransmitting setpoints."""
        mock_parameters.MAVSDK_COMMAND_TIMEOUT_S = 0.01
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"

        async def never_finishes():
            await asyncio.Event().wait()

        px4_interface.drone.offboard.start.side_effect = never_finishes
        with patch(
            "classes.px4_interface_manager.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await px4_interface.start_offboard_mode()

        assert result["status"] == "failed"
        assert any("Failed to start" in error for error in result["errors"])
        px4_interface.drone.offboard.stop.assert_awaited_once()
        assert px4_interface._mavsdk_offboard_sender_state == "quiesced"

    @pytest.mark.asyncio
    async def test_stop_offboard_mode(self, px4_interface):
        """Test stopping offboard mode."""
        px4_interface.active_mode = True
        result = await px4_interface.stop_offboard_mode()

        assert result['status'] == 'executed'
        assert result['executed'] is True
        px4_interface.drone.offboard.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_offboard_mode_fails_closed_without_connection(self, px4_interface):
        """A known-dead link must never receive an inferred stop command."""
        result = await px4_interface.stop_offboard_mode()

        assert result['status'] == 'blocked'
        assert result['reason'] == 'mavsdk_not_connected'
        px4_interface.drone.offboard.stop.assert_not_called()


class TestPX4InterfaceManagerValidationDisconnect:
    """Tests for the validation-only local MAVSDK disconnect hook."""

    @pytest.mark.asyncio
    async def test_validation_disconnect_marks_command_path_and_cancels_update_task(
        self,
        px4_interface,
    ):
        """Local validation disconnect should stop telemetry updates and expose status."""
        px4_interface.active_mode = True
        task_started = asyncio.Event()

        async def dummy_task():
            task_started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise

        px4_interface.update_task = asyncio.create_task(dummy_task())
        await task_started.wait()

        status = await px4_interface.inject_mavsdk_disconnect_for_validation(
            reason="sitl_mavsdk_disconnect",
            source="unit.px4",
        )

        assert status["status"] == "validation_disconnected"
        assert status["connected"] is False
        assert status["active_mode"] is False
        assert status["validation_disconnect_active"] is True
        assert status["disconnect_reason"] == "sitl_mavsdk_disconnect"
        assert status["disconnect_source"] == "unit.px4"
        assert status["disconnect_count"] == 1
        assert status["last_error"] == "MAVSDK disconnected - sitl_mavsdk_disconnect"
        assert px4_interface.update_task.done()

    @pytest.mark.asyncio
    async def test_validation_disconnect_blocks_commands_and_offboard_stop(
        self,
        px4_interface,
    ):
        """Command publication must fail closed while validation-disconnected."""
        await px4_interface.inject_mavsdk_disconnect_for_validation(
            reason="sitl_mavsdk_disconnect",
            source="unit.px4",
        )

        command_result = await px4_interface.send_commands_unified()

        assert command_result is False
        px4_interface.drone.offboard.set_velocity_body.assert_not_called()
        stop_result = await px4_interface.stop_offboard_mode()
        assert stop_result["status"] == "blocked"
        assert stop_result["reason"] == "validation_mavsdk_disconnected"
        assert stop_result["degraded"] is True
        px4_interface.drone.offboard.stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_clears_validation_disconnect(self, px4_interface):
        """A successful reconnect should clear validation-only disconnect state."""
        await px4_interface.inject_mavsdk_disconnect_for_validation(
            reason="sitl_mavsdk_disconnect",
            source="unit.px4",
        )

        try:
            await px4_interface.connect()

            status = px4_interface.get_connection_status()
            assert status["status"] == "connected"
            assert status["connected"] is True
            assert status["validation_disconnect_active"] is False
            assert status["disconnect_reason"] is None
            assert px4_interface.drone.connect.await_count == 1
        finally:
            px4_interface.active_mode = False
            await px4_interface._cancel_telemetry_update_task()


class TestPX4InterfaceManagerVelocityCommands:
    """Tests for velocity body offboard commands."""

    @pytest.fixture(autouse=True)
    def _connected_command_path(self, px4_interface):
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"

    @pytest.mark.asyncio
    async def test_send_velocity_body_offboard_commands(self, px4_interface, mock_setpoint_handler):
        """Test sending velocity body commands."""
        mock_setpoint_handler.get_fields.return_value = {
            'vel_body_fwd': 2.0,
            'vel_body_right': 1.0,
            'vel_body_down': -0.5,
            'yawspeed_deg_s': 15.0
        }

        result = await px4_interface.send_velocity_body_offboard_commands()

        assert result is True
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

        result = await px4_interface.send_velocity_body_offboard_commands()

        assert result is True
        px4_interface.drone.offboard.set_velocity_body.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_velocity_body_missing_handler(self, px4_interface):
        """Test handling missing setpoint handler."""
        px4_interface.setpoint_handler = None

        result = await px4_interface.send_velocity_body_offboard_commands()

        assert result is False

    @pytest.mark.asyncio
    async def test_send_velocity_body_rejects_wrong_control_type(
        self,
        px4_interface,
        mock_setpoint_handler,
    ):
        mock_setpoint_handler.get_control_type.return_value = 'attitude_rate'

        result = await px4_interface.send_velocity_body_offboard_commands()

        assert result is False
        px4_interface.drone.offboard.set_velocity_body.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_velocity_body_rejects_partial_snapshot(
        self,
        px4_interface,
        mock_setpoint_handler,
    ):
        mock_setpoint_handler.get_fields.return_value = {
            'vel_body_down': 0.0,
            'yawspeed_deg_s': 0.0,
        }

        result = await px4_interface.send_velocity_body_offboard_commands()

        assert result is False
        px4_interface.drone.offboard.set_velocity_body.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_velocity_body_propagates_mavsdk_failure(self, px4_interface):
        """MAVSDK send failure should return False to callers."""
        px4_interface._safe_mavsdk_call = AsyncMock(return_value=False)

        result = await px4_interface.send_velocity_body_offboard_commands()

        assert result is False

    @pytest.mark.asyncio
    async def test_send_velocity_body_blocks_non_finite_values(self, px4_interface, mock_setpoint_handler):
        """Final PX4 boundary rejects NaN/Inf before MAVSDK construction."""
        mock_setpoint_handler.get_fields.return_value = {
            'vel_body_fwd': float('nan'),
            'vel_body_right': 0.0,
            'vel_body_down': 0.0,
            'yawspeed_deg_s': 0.0,
        }

        result = await px4_interface.send_velocity_body_offboard_commands()

        assert result is False
        px4_interface.drone.offboard.set_velocity_body.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_velocity_body_degrades_when_circuit_breaker_unavailable(
        self,
        px4_interface,
        mock_setpoint_handler,
    ):
        """Unavailable circuit-breaker module blocks PX4 send and reports degraded failure."""
        mock_setpoint_handler.get_fields.return_value = {
            'vel_body_fwd': 0.1,
            'vel_body_right': 0.0,
            'vel_body_down': 0.0,
            'yawspeed_deg_s': 0.0,
        }

        with patch('classes.px4_interface_manager.CIRCUIT_BREAKER_AVAILABLE', False):
            result = await px4_interface.send_velocity_body_offboard_commands()

        assert result is False
        px4_interface.drone.offboard.set_velocity_body.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_velocity_body_allows_explicit_safety_module_bypass(
        self,
        px4_interface,
        mock_setpoint_handler,
        monkeypatch,
    ):
        """The safety-module bypass is explicit and testable."""
        from classes.parameters import Parameters

        monkeypatch.setattr(Parameters, "FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES", True, raising=False)
        mock_setpoint_handler.get_fields.return_value = {
            'vel_body_fwd': 0.1,
            'vel_body_right': 0.0,
            'vel_body_down': 0.0,
            'yawspeed_deg_s': 0.0,
        }

        with patch('classes.px4_interface_manager.CIRCUIT_BREAKER_AVAILABLE', False):
            result = await px4_interface.send_velocity_body_offboard_commands()

        assert result is True
        px4_interface.drone.offboard.set_velocity_body.assert_called_once()


class TestPX4InterfaceManagerAttitudeRateCommands:
    """Tests for attitude rate commands."""

    @pytest.fixture(autouse=True)
    def _connected_command_path(self, px4_interface):
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"

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

        result = await px4_interface.send_attitude_rate_commands()

        assert result is True
        px4_interface.drone.offboard.set_attitude_rate.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_attitude_rate_fails_closed_without_thrust(self, px4_interface, mock_setpoint_handler):
        """Attitude-rate dispatch must never invent a missing thrust value."""
        mock_setpoint_handler.get_control_type.return_value = 'attitude_rate'
        mock_setpoint_handler.get_fields.return_value = {
            'rollspeed_deg_s': 0.0,
            'pitchspeed_deg_s': 0.0,
            'yawspeed_deg_s': 0.0,
        }

        result = await px4_interface.send_attitude_rate_commands()

        assert result is False
        px4_interface.drone.offboard.set_attitude_rate.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_attitude_rate_rejects_wrong_control_type(
        self,
        px4_interface,
        mock_setpoint_handler,
    ):
        mock_setpoint_handler.get_control_type.return_value = 'velocity_body_offboard'

        result = await px4_interface.send_attitude_rate_commands()

        assert result is False
        px4_interface.drone.offboard.set_attitude_rate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_attitude_rate_blocks_invalid_thrust(self, px4_interface, mock_setpoint_handler):
        """Final PX4 boundary clamps normalized thrust before MAVSDK dispatch."""
        mock_setpoint_handler.get_control_type.return_value = 'attitude_rate'
        mock_setpoint_handler.get_fields.return_value = {
            'rollspeed_deg_s': 0.0,
            'pitchspeed_deg_s': 0.0,
            'yawspeed_deg_s': 0.0,
            'thrust': 2.0,
        }

        result = await px4_interface.send_attitude_rate_commands()

        assert result is True
        sent = px4_interface.drone.offboard.set_attitude_rate.await_args.args[0]
        assert sent.thrust_value == 1.0


class TestPX4InterfaceManagerUnifiedDispatch:
    """Tests for unified command dispatch."""

    @pytest.fixture(autouse=True)
    def _connected_command_path(self, px4_interface):
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"

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
        px4_interface.active_mode = True
        result = await px4_interface.trigger_return_to_launch()

        assert result['status'] == 'executed'
        assert result['executed'] is True
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

                result = await interface.trigger_return_to_launch()

                assert result['status'] == 'simulated'
                assert result['simulated'] is True
                assert result['reason'] == 'circuit_breaker_active'
                mock_mavsdk_system.action.return_to_launch.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_failsafe(self, px4_interface):
        """Test failsafe triggers RTL."""
        px4_interface.active_mode = True
        await px4_interface.trigger_failsafe()

        px4_interface.drone.action.return_to_launch.assert_called_once()


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

    @pytest.fixture(autouse=True)
    def _connected_command_path(self, px4_interface):
        px4_interface.active_mode = True
        px4_interface._connection_state = "connected"

    @pytest.mark.asyncio
    async def test_safe_mavsdk_call_success(self, px4_interface):
        """Test successful MAVSDK call."""
        async_func = AsyncMock()

        result = await px4_interface._safe_mavsdk_call(async_func, "arg1", key="value")

        assert result is True
        async_func.assert_called_once_with("arg1", key="value")

    @pytest.mark.asyncio
    async def test_safe_mavsdk_call_does_not_hide_loop_ownership_error(self, px4_interface):
        """Cross-loop failures are architectural and must not be retried."""
        call_count = 0

        async def failing_first_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("attached to a different loop")

        result = await px4_interface._safe_mavsdk_call(failing_first_call)

        assert result is False
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_safe_mavsdk_call_other_error(self, px4_interface):
        """Test handling of other errors."""
        async def failing_call(*args, **kwargs):
            raise ValueError("Some other error")

        result = await px4_interface._safe_mavsdk_call(failing_call)

        assert result is False

    @pytest.mark.asyncio
    async def test_safe_mavsdk_call_is_bounded(
        self,
        px4_interface,
        mock_parameters,
    ):
        mock_parameters.MAVSDK_COMMAND_TIMEOUT_S = 0.01

        async def never_finishes():
            await asyncio.Event().wait()

        result = await px4_interface._safe_mavsdk_call(never_finishes)

        assert result is False

    @pytest.mark.asyncio
    async def test_safe_mavsdk_call_rejects_disconnected_interface(self, px4_interface):
        px4_interface.active_mode = False
        px4_interface._connection_state = "connection_lost"
        async_func = AsyncMock()

        result = await px4_interface._safe_mavsdk_call(async_func)

        assert result is False
        async_func.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_safe_mavsdk_call_rejects_generation_change_during_rpc(
        self,
        px4_interface,
    ):
        async def command_then_disconnect():
            px4_interface._advance_connection_generation()
            px4_interface.active_mode = False
            px4_interface._connection_state = "connection_lost"

        result = await px4_interface._safe_mavsdk_call(command_then_disconnect)

        assert result is False

    @pytest.mark.asyncio
    async def test_blocked_setpoint_quiesces_existing_mavsdk_sender(
        self,
        px4_interface,
        mock_setpoint_handler,
    ):
        px4_interface._set_offboard_sender_state("primed", "unit_test")
        mock_setpoint_handler.get_fields.return_value = {
            "vel_body_fwd": 0.1,
            "vel_body_right": 0.0,
            "vel_body_down": 0.0,
            "yawspeed_deg_s": 0.0,
        }
        with patch(
            "classes.px4_interface_manager.FollowerCircuitBreaker"
        ) as circuit_breaker:
            circuit_breaker.is_active.return_value = True
            circuit_breaker.log_command_instead_of_execute = MagicMock()
            result = await px4_interface.send_velocity_body_offboard_commands()

        assert result is False
        px4_interface.drone.offboard.set_velocity_body.assert_not_awaited()
        px4_interface.drone.offboard.stop.assert_awaited_once()
        assert px4_interface._mavsdk_offboard_sender_state == "quiesced"


class TestPX4CommandGateFailClosed:
    """Regression tests for fail-closed command gating."""

    def test_unavailable_circuit_breaker_blocks_without_bypass(self, monkeypatch):
        from classes.parameters import Parameters
        from classes.px4_interface_manager import _evaluate_px4_command_gate

        monkeypatch.setattr(Parameters, "FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES", False, raising=False)
        with patch('classes.px4_interface_manager.CIRCUIT_BREAKER_AVAILABLE', False):
            decision = _evaluate_px4_command_gate("velocity_body")

        assert decision.blocked is True
        assert decision.degraded is True
        assert decision.reason == "circuit_breaker_unavailable"

    def test_circuit_breaker_status_exception_blocks_without_bypass(self, monkeypatch):
        from classes.parameters import Parameters
        from classes.px4_interface_manager import _evaluate_px4_command_gate

        monkeypatch.setattr(Parameters, "FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES", False, raising=False)
        with patch('classes.px4_interface_manager.CIRCUIT_BREAKER_AVAILABLE', True):
            with patch('classes.px4_interface_manager.FollowerCircuitBreaker') as mock_cb:
                mock_cb.is_active.side_effect = RuntimeError("status unavailable")

                decision = _evaluate_px4_command_gate("velocity_body")

        assert decision.blocked is True
        assert decision.degraded is True
        assert decision.reason == "circuit_breaker_status_failed"

    def test_circuit_breaker_audit_exception_blocks_without_bypass(self, monkeypatch):
        from classes.parameters import Parameters
        from classes.px4_interface_manager import _evaluate_px4_command_gate

        monkeypatch.setattr(Parameters, "FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES", False, raising=False)
        with patch('classes.px4_interface_manager.CIRCUIT_BREAKER_AVAILABLE', True):
            with patch('classes.px4_interface_manager.FollowerCircuitBreaker') as mock_cb:
                mock_cb.is_active.return_value = False
                mock_cb.log_command_allowed.side_effect = RuntimeError("audit unavailable")

                decision = _evaluate_px4_command_gate("velocity_body")

        assert decision.blocked is True
        assert decision.degraded is True
        assert decision.reason == "circuit_breaker_audit_failed"
