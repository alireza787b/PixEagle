# tests/unit/drone_interface/test_mavlink_data_manager.py
"""
Unit tests for MavlinkDataManager.

Tests MAVLink2REST polling and data parsing:
- Polling lifecycle (start, stop)
- Attitude data parsing
- Altitude data parsing
- Velocity/ground speed calculation
- Flight mode detection
- Offboard exit callback
- Connection error handling
- Threading safety
"""

import pytest
import math
import time
import threading
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_parameters():
    """Mock Parameters class."""
    with patch('classes.mavlink_data_manager.Parameters') as mock_params:
        mock_params.get_effective_limit = MagicMock(return_value=10.0)
        yield mock_params


@pytest.fixture
def mock_requests():
    """Mock requests module."""
    with patch('classes.mavlink_data_manager.requests') as mock_req:
        yield mock_req


@pytest.fixture
def sample_data_points():
    """Sample data points configuration."""
    return {
        'latitude': '/vehicles/1/components/1/messages/GLOBAL_POSITION_INT/message/lat',
        'longitude': '/vehicles/1/components/1/messages/GLOBAL_POSITION_INT/message/lon',
        'altitude': '/vehicles/1/components/1/messages/ALTITUDE/message/altitude_relative',
        'flight_mode': '/vehicles/1/components/191/messages/HEARTBEAT/message/custom_mode',
        'arm_status': '/vehicles/1/components/191/messages/HEARTBEAT/message/base_mode/bits',
        'vn': '/vehicles/1/components/1/messages/LOCAL_POSITION_NED/message/vx',
        've': '/vehicles/1/components/1/messages/LOCAL_POSITION_NED/message/vy',
        'vd': '/vehicles/1/components/1/messages/LOCAL_POSITION_NED/message/vz',
    }


@pytest.fixture
def mavlink_data_manager(sample_data_points, mock_parameters):
    """Create MavlinkDataManager instance for testing."""
    with patch('classes.mavlink_data_manager.logging_manager'):
        from classes.mavlink_data_manager import MavlinkDataManager
        manager = MavlinkDataManager(
            mavlink_host='127.0.0.1',
            mavlink_port=8088,
            polling_interval=0.5,
            data_points=sample_data_points,
            enabled=True
        )
        yield manager
        # Cleanup
        if hasattr(manager, '_thread') and manager._thread and manager._thread.is_alive():
            manager.stop_polling()


# ============================================================================
# Test Classes
# ============================================================================

class TestMavlinkDataManagerInitialization:
    """Tests for MavlinkDataManager initialization."""

    def test_init_with_default_values(self, sample_data_points, mock_parameters):
        """Test initialization with default values."""
        with patch('classes.mavlink_data_manager.logging_manager'):
            from classes.mavlink_data_manager import MavlinkDataManager
            manager = MavlinkDataManager(
                mavlink_host='127.0.0.1',
                mavlink_port=8088,
                polling_interval=0.5,
                data_points=sample_data_points
            )

            assert manager.mavlink_host == '127.0.0.1'
            assert manager.mavlink_port == 8088
            assert manager.polling_interval == 0.5
            assert manager.enabled is True
            assert manager.connection_state == "disconnected"

    def test_init_disabled(self, sample_data_points, mock_parameters):
        """Test initialization with polling disabled."""
        with patch('classes.mavlink_data_manager.logging_manager'):
            from classes.mavlink_data_manager import MavlinkDataManager
            manager = MavlinkDataManager(
                mavlink_host='127.0.0.1',
                mavlink_port=8088,
                polling_interval=0.5,
                data_points=sample_data_points,
                enabled=False
            )

            assert manager.enabled is False

    def test_init_connection_state(self, mavlink_data_manager):
        """Test initial connection state."""
        assert mavlink_data_manager.connection_state == "disconnected"
        assert mavlink_data_manager.connection_error_count == 0

    def test_init_offboard_mode_code(self, mavlink_data_manager):
        """Test offboard mode code is set correctly."""
        assert mavlink_data_manager.offboard_mode_code == 393216


class TestMavlinkDataManagerPolling:
    """Tests for polling lifecycle."""

    def test_start_polling_creates_thread(self, mavlink_data_manager, mock_requests):
        """Test that start_polling creates a thread."""
        mock_requests.get.return_value = MagicMock(
            json=lambda: {},
            raise_for_status=lambda: None
        )

        mavlink_data_manager.start_polling()

        assert hasattr(mavlink_data_manager, '_thread')
        assert mavlink_data_manager._thread.is_alive()

        mavlink_data_manager.stop_polling()

    def test_stop_polling_stops_thread(self, mavlink_data_manager, mock_requests):
        """Test that stop_polling stops the thread."""
        mock_requests.get.return_value = MagicMock(
            json=lambda: {},
            raise_for_status=lambda: None
        )

        mavlink_data_manager.start_polling()
        mavlink_data_manager.stop_polling()

        assert not mavlink_data_manager._thread.is_alive()

    def test_polling_disabled_no_thread(self, sample_data_points, mock_parameters):
        """Test that no thread is created when disabled."""
        with patch('classes.mavlink_data_manager.logging_manager'):
            from classes.mavlink_data_manager import MavlinkDataManager
            manager = MavlinkDataManager(
                mavlink_host='127.0.0.1',
                mavlink_port=8088,
                polling_interval=0.5,
                data_points=sample_data_points,
                enabled=False
            )

            manager.start_polling()

            # Should not have started a thread
            assert not hasattr(manager, '_thread') or not getattr(manager, '_thread', None)


class TestMavlinkDataManagerDataParsing:
    """Tests for data parsing from JSON responses."""

    def test_extract_nested_json_data(self, mavlink_data_manager):
        """Test extracting data from nested JSON path."""
        json_data = {
            'vehicles': {
                '1': {
                    'components': {
                        '1': {
                            'messages': {
                                'ATTITUDE': {
                                    'message': {
                                        'roll': 0.1,
                                        'pitch': 0.2,
                                        'yaw': 0.3
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        result = mavlink_data_manager._extract_data_from_json(
            json_data,
            '/vehicles/1/components/1/messages/ATTITUDE/message/roll'
        )

        assert result == 0.1

    def test_extract_missing_key_returns_none(self, mavlink_data_manager):
        """Test that missing key returns None."""
        json_data = {'vehicles': {}}

        result = mavlink_data_manager._extract_data_from_json(
            json_data,
            '/vehicles/1/components/1/messages/ATTITUDE/message/roll'
        )

        assert result is None


class TestMavlinkDataManagerAttitude:
    """Tests for attitude data fetching."""

    @pytest.mark.asyncio
    async def test_fetch_attitude_data_success(self, mavlink_data_manager, mock_requests):
        """Test fetching attitude data successfully."""
        mock_requests.get.return_value = MagicMock(
            json=lambda: {
                'message': {
                    'roll': 0.1,  # radians
                    'pitch': 0.2,
                    'yaw': 0.5
                }
            },
            raise_for_status=lambda: None
        )

        result = await mavlink_data_manager.fetch_attitude_data()

        assert 'roll' in result
        assert 'pitch' in result
        assert 'yaw' in result
        # Should be converted to degrees
        assert abs(result['roll'] - math.degrees(0.1)) < 0.01
        assert abs(result['pitch'] - math.degrees(0.2)) < 0.01
        assert abs(result['yaw'] - math.degrees(0.5)) < 0.01

    @pytest.mark.asyncio
    async def test_fetch_attitude_data_failure_returns_zeros(self, mavlink_data_manager, mock_requests):
        """Test that failure returns zero values."""
        mock_response = MagicMock()
        mock_response.json.return_value = {}  # Empty response
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response
        mock_requests.RequestException = Exception

        result = await mavlink_data_manager.fetch_attitude_data()

        assert result['roll'] == 0
        assert result['pitch'] == 0
        assert result['yaw'] == 0


class TestMavlinkDataManagerAltitude:
    """Tests for altitude data fetching."""

    @pytest.mark.asyncio
    async def test_fetch_altitude_data_success(self, mavlink_data_manager, mock_requests, mock_parameters):
        """Test fetching altitude data successfully."""
        mock_requests.get.return_value = MagicMock(
            json=lambda: {
                'message': {
                    'altitude_relative': 50.0,
                    'altitude_amsl': 150.0
                }
            },
            raise_for_status=lambda: None
        )

        result = await mavlink_data_manager.fetch_altitude_data()

        assert result['altitude_relative'] == 50.0
        assert result['altitude_amsl'] == 150.0

    @pytest.mark.asyncio
    async def test_fetch_altitude_data_failure_returns_default(self, mavlink_data_manager, mock_requests, mock_parameters):
        """Test that failure returns default altitude."""
        mock_response = MagicMock()
        mock_response.json.return_value = {}  # Empty response
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response
        mock_requests.RequestException = Exception

        result = await mavlink_data_manager.fetch_altitude_data()

        # Should return MIN_ALTITUDE from SafetyLimits
        assert 'altitude_relative' in result
        assert 'altitude_amsl' in result


class TestMavlinkDataManagerGroundSpeed:
    """Tests for ground speed calculation."""

    @pytest.mark.asyncio
    async def test_fetch_ground_speed_horizontal(self, mavlink_data_manager, mock_requests):
        """Test ground speed calculation from horizontal velocities."""
        mock_requests.get.return_value = MagicMock(
            json=lambda: {
                'message': {
                    'vx': 3.0,  # m/s
                    'vy': 4.0   # m/s
                }
            },
            raise_for_status=lambda: None
        )

        result = await mavlink_data_manager.fetch_ground_speed()

        # sqrt(3^2 + 4^2) = 5
        assert abs(result - 5.0) < 0.01

    @pytest.mark.asyncio
    async def test_fetch_ground_speed_zero(self, mavlink_data_manager, mock_requests):
        """Test ground speed when stationary."""
        mock_requests.get.return_value = MagicMock(
            json=lambda: {
                'message': {
                    'vx': 0.0,
                    'vy': 0.0
                }
            },
            raise_for_status=lambda: None
        )

        result = await mavlink_data_manager.fetch_ground_speed()

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_fetch_ground_speed_failure_returns_zero(self, mavlink_data_manager, mock_requests):
        """Test that failure returns zero."""
        mock_response = MagicMock()
        mock_response.json.return_value = {}  # Empty response
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response
        mock_requests.RequestException = Exception

        result = await mavlink_data_manager.fetch_ground_speed()

        assert result == 0.0


class TestMavlinkDataManagerThrottle:
    """Tests for throttle data fetching."""

    @pytest.mark.asyncio
    async def test_fetch_throttle_percent_success(self, mavlink_data_manager, mock_requests):
        """Test fetching throttle percentage."""
        mock_requests.get.return_value = MagicMock(
            json=lambda: {
                'message': {
                    'throttle': 65
                }
            },
            raise_for_status=lambda: None
        )

        result = await mavlink_data_manager.fetch_throttle_percent()

        assert result == 65

    @pytest.mark.asyncio
    async def test_fetch_throttle_percent_failure_returns_zero(self, mavlink_data_manager, mock_requests):
        """Test that failure returns zero."""
        mock_response = MagicMock()
        mock_response.json.return_value = {}  # Empty response
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response
        mock_requests.RequestException = Exception

        result = await mavlink_data_manager.fetch_throttle_percent()

        assert result == 0.0


class TestMavlinkDataManagerFlightMode:
    """Tests for flight mode monitoring."""

    def test_handle_flight_mode_change_offboard_exit(self, mavlink_data_manager):
        """Test detection of offboard mode exit."""
        callback_called = []

        def callback(old_mode, new_mode):
            callback_called.append((old_mode, new_mode))

        mavlink_data_manager.register_offboard_exit_callback(callback)

        # Simulate exit from offboard (393216) to position (196608)
        mavlink_data_manager._handle_flight_mode_change(393216, 196608)

        assert len(callback_called) == 1
        assert callback_called[0] == (393216, 196608)

    def test_handle_flight_mode_change_no_callback_when_not_offboard(self, mavlink_data_manager):
        """Test no callback when not exiting offboard."""
        callback_called = []

        def callback(old_mode, new_mode):
            callback_called.append((old_mode, new_mode))

        mavlink_data_manager.register_offboard_exit_callback(callback)

        # Simulate change from position to stabilized
        mavlink_data_manager._handle_flight_mode_change(196608, 458752)

        assert len(callback_called) == 0

    def test_register_offboard_exit_callback(self, mavlink_data_manager):
        """Test callback registration."""
        def my_callback(old, new):
            pass

        mavlink_data_manager.register_offboard_exit_callback(my_callback)

        assert mavlink_data_manager._offboard_exit_callback == my_callback


class TestMavlinkDataManagerArmStatus:
    """Tests for arm status determination."""

    def test_determine_arm_status_armed(self, mavlink_data_manager):
        """Test arm status detection when armed."""
        # Armed bit is 128
        result = mavlink_data_manager._determine_arm_status(128 + 64)  # 192

        assert result == "Armed"

    def test_determine_arm_status_disarmed(self, mavlink_data_manager):
        """Test arm status detection when disarmed."""
        result = mavlink_data_manager._determine_arm_status(64)  # No arm bit

        assert result == "Disarmed"

    def test_determine_arm_status_unknown(self, mavlink_data_manager):
        """Test arm status when value is None."""
        result = mavlink_data_manager._determine_arm_status(None)

        assert result == "Unknown"


class TestMavlinkDataManagerConnectionState:
    """Tests for connection state tracking."""

    def test_connection_error_handling(self, mavlink_data_manager, mock_requests):
        """Test connection error handling."""
        mock_requests.exceptions = MagicMock()
        mock_requests.exceptions.ConnectionError = ConnectionError
        mock_requests.exceptions.Timeout = TimeoutError
        mock_requests.exceptions.RequestException = Exception
        mock_requests.get.side_effect = ConnectionError("Connection refused")

        mavlink_data_manager._fetch_and_parse_all_data()

        assert mavlink_data_manager.connection_state == "error"
        assert mavlink_data_manager.connection_error_count >= 1


class TestMavlinkDataManagerFlightPathAngle:
    """Tests for flight path angle calculation."""

    def test_calculate_flight_path_angle_level(self, mavlink_data_manager):
        """Test flight path angle when flying level."""
        mavlink_data_manager.data = {'vn': 5.0, 've': 0.0, 'vd': 0.0}

        result = mavlink_data_manager._calculate_flight_path_angle()

        assert abs(result) < 1.0  # Should be approximately 0

    def test_calculate_flight_path_angle_climbing(self, mavlink_data_manager):
        """Test flight path angle when climbing (vd negative = up)."""
        mavlink_data_manager.data = {'vn': 5.0, 've': 0.0, 'vd': -5.0}

        result = mavlink_data_manager._calculate_flight_path_angle()

        assert result > 0  # Positive angle = climbing

    def test_calculate_flight_path_angle_descending(self, mavlink_data_manager):
        """Test flight path angle when descending (vd positive = down)."""
        mavlink_data_manager.data = {'vn': 5.0, 've': 0.0, 'vd': 5.0}

        result = mavlink_data_manager._calculate_flight_path_angle()

        assert result < 0  # Negative angle = descending

    def test_calculate_flight_path_angle_stationary(self, mavlink_data_manager):
        """Test flight path angle when stationary."""
        mavlink_data_manager.data = {'vn': 0.0, 've': 0.0, 'vd': 0.0}

        result = mavlink_data_manager._calculate_flight_path_angle()

        assert result == 0.0  # Should return 0 when stationary


class TestMavlinkDataManagerGetData:
    """Tests for get_data method."""

    def test_get_data_existing_point(self, mavlink_data_manager):
        """Test getting existing data point."""
        with mavlink_data_manager._lock:
            mavlink_data_manager.data['altitude'] = 50.0

        result = mavlink_data_manager.get_data('altitude')

        assert result == 50.0

    def test_get_data_missing_point(self, mavlink_data_manager):
        """Test getting missing data point returns 0."""
        result = mavlink_data_manager.get_data('nonexistent')

        assert result == 0

    def test_get_data_disabled(self, sample_data_points, mock_parameters):
        """Test get_data when disabled returns None."""
        with patch('classes.mavlink_data_manager.logging_manager'):
            from classes.mavlink_data_manager import MavlinkDataManager
            manager = MavlinkDataManager(
                mavlink_host='127.0.0.1',
                mavlink_port=8088,
                polling_interval=0.5,
                data_points=sample_data_points,
                enabled=False
            )

            result = manager.get_data('altitude')

            assert result is None


class TestMavlinkDataManagerThreadSafety:
    """Tests for thread safety."""

    def test_data_access_with_lock(self, mavlink_data_manager):
        """Test that data access is lock-protected."""
        # Verify lock exists
        assert hasattr(mavlink_data_manager, '_lock')
        assert isinstance(mavlink_data_manager._lock, type(threading.Lock()))

    def test_concurrent_data_access(self, mavlink_data_manager):
        """Test concurrent data access doesn't cause issues."""
        results = []
        errors = []

        def reader():
            for _ in range(100):
                try:
                    mavlink_data_manager.get_data('altitude')
                    results.append(True)
                except Exception as e:
                    errors.append(e)

        def writer():
            for i in range(100):
                try:
                    with mavlink_data_manager._lock:
                        mavlink_data_manager.data['altitude'] = float(i)
                    results.append(True)
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=reader) for _ in range(3)
        ] + [
            threading.Thread(target=writer) for _ in range(2)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestMavlinkDataManagerVelocityBuffer:
    """Tests for velocity buffer smoothing."""

    def test_velocity_buffer_initialization(self, mavlink_data_manager):
        """Test velocity buffer is initialized."""
        assert hasattr(mavlink_data_manager, 'velocity_buffer')
        assert len(mavlink_data_manager.velocity_buffer) == 0

    def test_velocity_buffer_max_length(self, mavlink_data_manager):
        """Test velocity buffer respects max length."""
        mavlink_data_manager.data = {'vn': 0.0, 've': 0.0, 'vd': 0.0}

        # Add more than buffer size
        for i in range(15):
            mavlink_data_manager.data = {'vn': float(i), 've': 0.0, 'vd': 0.0}
            mavlink_data_manager._calculate_flight_path_angle()

        assert len(mavlink_data_manager.velocity_buffer) <= 10
