# tests/unit/drone_interface/test_telemetry_handler.py
"""
Unit tests for TelemetryHandler.

Tests data formatting and UDP broadcast:
- Data formatting (tracker, follower)
- UDP transmission
- Rate limiting
- TrackerOutput integration
- Legacy format compatibility
"""

import pytest
import json
import socket
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, PropertyMock


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_parameters():
    """Mock Parameters class."""
    with patch('classes.telemetry_handler.Parameters') as mock_params:
        mock_params.UDP_HOST = '127.0.0.1'
        mock_params.UDP_PORT = 5005
        mock_params.TELEMETRY_SEND_RATE = 10
        mock_params.ENABLE_UDP_STREAM = True
        mock_params.ENABLE_FOLLOWER_TELEMETRY = True
        mock_params.MAVLINK_ENABLED = True
        yield mock_params


@pytest.fixture
def mock_tracker():
    """Create mock tracker."""
    mock = MagicMock()
    mock.normalized_bbox = [0.4, 0.4, 0.2, 0.3]
    mock.normalized_center = [0.5, 0.55]
    mock.confidence = 0.85
    return mock


@pytest.fixture
def mock_follower():
    """Create mock follower."""
    mock = MagicMock()
    mock.get_follower_telemetry.return_value = {
        'setpoints': {
            'vel_body_fwd': 2.0,
            'yawspeed_deg_s': 15.0
        },
        'error_metrics': {
            'position_error': 0.1
        }
    }
    mock.get_display_name.return_value = 'MC Velocity Position'
    return mock


@pytest.fixture
def mock_mavlink_data_manager():
    """Create mock MAVLink data manager."""
    mock = MagicMock()
    mock.get_data.return_value = 393216  # Offboard mode
    return mock


@pytest.fixture
def mock_px4_interface():
    """Create mock PX4 interface."""
    mock = MagicMock()
    mock.get_flight_mode_text.return_value = 'Offboard'
    return mock


@pytest.fixture
def mock_app_controller(mock_tracker, mock_follower, mock_mavlink_data_manager, mock_px4_interface):
    """Create mock app controller."""
    mock = MagicMock()
    mock.tracker = mock_tracker
    mock.follower = mock_follower
    mock.mavlink_data_manager = mock_mavlink_data_manager
    mock.px4_interface = mock_px4_interface
    mock.following_active = True
    mock.get_tracker_output = MagicMock(return_value=None)
    return mock


@pytest.fixture
def telemetry_handler(mock_parameters, mock_app_controller):
    """Create TelemetryHandler instance for testing."""
    with patch('classes.telemetry_handler.socket') as mock_socket:
        mock_socket.socket.return_value = MagicMock()
        mock_socket.AF_INET = socket.AF_INET
        mock_socket.SOCK_DGRAM = socket.SOCK_DGRAM

        from classes.telemetry_handler import TelemetryHandler

        def tracking_started():
            return True

        handler = TelemetryHandler(mock_app_controller, tracking_started)
        yield handler


# ============================================================================
# Test Classes
# ============================================================================

class TestTelemetryHandlerInitialization:
    """Tests for TelemetryHandler initialization."""

    def test_init_host_port(self, telemetry_handler, mock_parameters):
        """Test host and port initialization."""
        assert telemetry_handler.host == '127.0.0.1'
        assert telemetry_handler.port == 5005

    def test_init_send_rate(self, telemetry_handler, mock_parameters):
        """Test send rate initialization."""
        assert telemetry_handler.send_rate == 10
        assert telemetry_handler.send_interval == 0.1

    def test_init_udp_socket_created(self, telemetry_handler):
        """Test UDP socket is created."""
        assert telemetry_handler.udp_socket is not None

    def test_init_tracker_and_follower_set(self, telemetry_handler, mock_tracker, mock_follower):
        """Test tracker and follower are set."""
        assert telemetry_handler.tracker is not None
        assert telemetry_handler.follower is not None


class TestTelemetryHandlerRateLimiting:
    """Tests for rate limiting."""

    def test_should_send_telemetry_after_interval(self, telemetry_handler):
        """Test should_send_telemetry returns True after interval."""
        telemetry_handler.last_sent_time = datetime.utcnow() - timedelta(seconds=1)

        result = telemetry_handler.should_send_telemetry()

        assert result is True

    def test_should_not_send_telemetry_within_interval(self, telemetry_handler):
        """Test should_send_telemetry returns False within interval."""
        telemetry_handler.last_sent_time = datetime.utcnow()

        result = telemetry_handler.should_send_telemetry()

        assert result is False

    def test_send_interval_calculation(self, telemetry_handler):
        """Test send interval is correctly calculated."""
        assert telemetry_handler.send_interval == 1.0 / telemetry_handler.send_rate


class TestTelemetryHandlerTrackerData:
    """Tests for tracker data collection."""

    def test_get_tracker_data_legacy(self, telemetry_handler, mock_tracker, mock_app_controller):
        """Test getting legacy tracker data."""
        mock_app_controller.get_tracker_output.return_value = None

        data = telemetry_handler.get_tracker_data()

        assert 'bounding_box' in data
        assert 'center' in data
        assert 'timestamp' in data
        assert 'tracker_started' in data

    def test_get_tracker_data_contains_tracker_data_section(self, telemetry_handler, mock_app_controller):
        """Test that tracker_data section is included."""
        mock_app_controller.get_tracker_output.return_value = None

        data = telemetry_handler.get_tracker_data()

        assert 'tracker_data' in data
        assert 'data_type' in data['tracker_data']
        assert 'tracking_active' in data['tracker_data']

    def test_get_tracker_data_with_tracker_output(self, telemetry_handler, mock_app_controller):
        """Test getting data with structured TrackerOutput."""
        from classes.tracker_output import TrackerOutput, TrackerDataType

        mock_output = MagicMock(spec=TrackerOutput)
        mock_output.data_type = TrackerDataType.POSITION_2D
        mock_output.normalized_bbox = [0.4, 0.4, 0.2, 0.3]
        mock_output.position_2d = [0.5, 0.55]
        mock_output.tracking_active = True
        mock_output.confidence = 0.9
        mock_output.tracker_id = 'test_tracker'
        mock_output.timestamp = '2024-01-01T00:00:00'
        mock_output.velocity = None
        mock_output.quality_metrics = None
        mock_output.bbox = [100, 100, 50, 75]

        mock_app_controller.get_tracker_output.return_value = mock_output
        mock_app_controller.get_tracker_capabilities = MagicMock(return_value=None)

        data = telemetry_handler.get_tracker_data()

        assert 'tracker_data' in data
        assert data['tracker_data']['tracking_active'] is True

    def test_get_legacy_tracker_data(self, telemetry_handler):
        """Test legacy tracker data fallback."""
        data = telemetry_handler._get_legacy_tracker_data(
            datetime.utcnow().isoformat(),
            True
        )

        assert data['tracker_data']['legacy_mode'] is True
        assert data['tracker_data']['data_type'] == 'position_2d'


class TestTelemetryHandlerFollowerData:
    """Tests for follower data collection."""

    def test_get_follower_data_basic(self, telemetry_handler, mock_follower, mock_app_controller, mock_parameters):
        """Test getting basic follower data."""
        data = telemetry_handler.get_follower_data()

        assert 'following_active' in data
        assert data['following_active'] is True

    def test_get_follower_data_includes_setpoints(self, telemetry_handler, mock_follower, mock_app_controller, mock_parameters):
        """Test that follower data includes setpoints."""
        mock_follower.get_follower_telemetry.return_value = {
            'setpoints': {'vel_body_fwd': 2.0}
        }

        data = telemetry_handler.get_follower_data()

        assert 'setpoints' in data

    def test_get_follower_data_includes_profile_name(self, telemetry_handler, mock_follower, mock_app_controller, mock_parameters):
        """Test that follower data includes profile name."""
        data = telemetry_handler.get_follower_data()

        assert 'profile_name' in data

    def test_get_follower_data_includes_flight_mode(self, telemetry_handler, mock_app_controller, mock_parameters):
        """Test that follower data includes flight mode."""
        data = telemetry_handler.get_follower_data()

        assert 'flight_mode' in data or 'is_offboard' in data

    def test_get_follower_data_no_follower(self, telemetry_handler, mock_parameters):
        """Test getting data when follower is None."""
        telemetry_handler.follower = None

        data = telemetry_handler.get_follower_data()

        assert data == {}

    def test_get_follower_data_exception_handling(self, telemetry_handler, mock_follower, mock_app_controller, mock_parameters):
        """Test exception handling in follower data."""
        mock_follower.get_follower_telemetry.side_effect = Exception("Test error")

        data = telemetry_handler.get_follower_data()

        assert 'error' in data


class TestTelemetryHandlerGatherData:
    """Tests for gathering all telemetry data."""

    def test_gather_telemetry_data_structure(self, telemetry_handler, mock_parameters):
        """Test gathered data structure."""
        data = telemetry_handler.gather_telemetry_data()

        assert 'tracker_data' in data
        assert 'follower_data' in data


class TestTelemetryHandlerUDPTransmission:
    """Tests for UDP transmission."""

    def test_send_telemetry_sends_data(self, telemetry_handler, mock_parameters):
        """Test that telemetry is sent via UDP."""
        telemetry_handler.last_sent_time = datetime.utcnow() - timedelta(seconds=1)

        telemetry_handler.send_telemetry()

        telemetry_handler.udp_socket.sendto.assert_called()

    def test_send_telemetry_updates_last_sent_time(self, telemetry_handler, mock_parameters):
        """Test that last_sent_time is updated."""
        telemetry_handler.last_sent_time = datetime.utcnow() - timedelta(seconds=1)
        old_time = telemetry_handler.last_sent_time

        telemetry_handler.send_telemetry()

        assert telemetry_handler.last_sent_time > old_time

    def test_send_telemetry_respects_rate_limit(self, telemetry_handler, mock_parameters):
        """Test that rate limit is respected."""
        telemetry_handler.last_sent_time = datetime.utcnow()

        telemetry_handler.send_telemetry()

        telemetry_handler.udp_socket.sendto.assert_not_called()

    def test_send_telemetry_disabled(self, telemetry_handler):
        """Test that telemetry is not sent when disabled."""
        telemetry_handler.enable_udp = False
        telemetry_handler.last_sent_time = datetime.utcnow() - timedelta(seconds=1)

        telemetry_handler.send_telemetry()

        telemetry_handler.udp_socket.sendto.assert_not_called()

    def test_send_telemetry_updates_cached_data(self, telemetry_handler, mock_parameters):
        """Test that cached data is updated regardless of sending."""
        telemetry_handler.send_telemetry()

        # Cached data should be updated even if not sent
        assert telemetry_handler.latest_tracker_data is not None


class TestTelemetryHandlerDataFormatting:
    """Tests for data formatting."""

    def test_tracker_data_json_serializable(self, telemetry_handler):
        """Test that tracker data is JSON serializable."""
        data = telemetry_handler.get_tracker_data()

        # Should not raise
        json_str = json.dumps(data)
        assert len(json_str) > 0

    def test_follower_data_json_serializable(self, telemetry_handler, mock_parameters):
        """Test that follower data is JSON serializable."""
        data = telemetry_handler.get_follower_data()

        # Should not raise
        json_str = json.dumps(data)
        assert len(json_str) > 0

    def test_gathered_data_json_serializable(self, telemetry_handler, mock_parameters):
        """Test that gathered data is JSON serializable."""
        data = telemetry_handler.gather_telemetry_data()

        # Should not raise
        json_str = json.dumps(data)
        assert len(json_str) > 0


class TestTelemetryHandlerTrackerOutputTypes:
    """Tests for different TrackerOutput data types."""

    def test_format_position_2d_data(self, telemetry_handler, mock_app_controller):
        """Test formatting POSITION_2D tracker output."""
        from classes.tracker_output import TrackerOutput, TrackerDataType

        mock_output = MagicMock(spec=TrackerOutput)
        mock_output.data_type = TrackerDataType.POSITION_2D
        mock_output.position_2d = [0.5, 0.5]
        mock_output.normalized_bbox = [0.4, 0.4, 0.2, 0.2]
        mock_output.bbox = [100, 100, 50, 50]
        mock_output.tracking_active = True
        mock_output.confidence = 0.9
        mock_output.tracker_id = 'csrt'
        mock_output.timestamp = '2024-01-01'
        mock_output.velocity = None
        mock_output.quality_metrics = None

        data = telemetry_handler._format_tracker_data(
            mock_output,
            datetime.utcnow().isoformat(),
            True
        )

        # data_type.value gives the string representation
        assert data['tracker_data']['data_type'] == TrackerDataType.POSITION_2D.value
        assert 'position_2d' in data['tracker_data']

    def test_format_angular_data(self, telemetry_handler):
        """Test formatting ANGULAR tracker output."""
        from classes.tracker_output import TrackerOutput, TrackerDataType

        mock_output = MagicMock(spec=TrackerOutput)
        mock_output.data_type = TrackerDataType.ANGULAR
        mock_output.angular = [45.0, -10.0]
        mock_output.normalized_bbox = None
        mock_output.position_2d = None
        mock_output.tracking_active = True
        mock_output.confidence = 0.85
        mock_output.tracker_id = 'gimbal'
        mock_output.timestamp = '2024-01-01'
        mock_output.velocity = None
        mock_output.quality_metrics = None

        data = telemetry_handler._format_tracker_data(
            mock_output,
            datetime.utcnow().isoformat(),
            True
        )

        # data_type.value gives the string representation
        assert data['tracker_data']['data_type'] == TrackerDataType.ANGULAR.value
        assert 'bearing' in data['tracker_data']
        assert 'elevation' in data['tracker_data']

    def test_format_data_with_velocity(self, telemetry_handler):
        """Test formatting tracker output with velocity."""
        from classes.tracker_output import TrackerOutput, TrackerDataType

        mock_output = MagicMock(spec=TrackerOutput)
        mock_output.data_type = TrackerDataType.POSITION_2D
        mock_output.position_2d = [0.5, 0.5]
        mock_output.normalized_bbox = [0.4, 0.4, 0.2, 0.2]
        mock_output.bbox = [100, 100, 50, 50]
        mock_output.tracking_active = True
        mock_output.confidence = 0.9
        mock_output.tracker_id = 'csrt'
        mock_output.timestamp = '2024-01-01'
        mock_output.velocity = [0.1, -0.05]
        mock_output.quality_metrics = None

        data = telemetry_handler._format_tracker_data(
            mock_output,
            datetime.utcnow().isoformat(),
            True
        )

        assert 'velocity' in data['tracker_data']
        assert 'vx' in data['tracker_data']['velocity']
        assert 'magnitude' in data['tracker_data']['velocity']


class TestTelemetryHandlerFlightModeIntegration:
    """Tests for flight mode integration."""

    def test_offboard_flag_set(self, telemetry_handler, mock_app_controller, mock_parameters):
        """Test is_offboard flag is set correctly."""
        mock_app_controller.mavlink_data_manager.get_data.return_value = 393216  # Offboard

        data = telemetry_handler.get_follower_data()

        assert 'is_offboard' in data
        assert data['is_offboard'] is True

    def test_non_offboard_flag_set(self, telemetry_handler, mock_app_controller, mock_parameters):
        """Test is_offboard flag for non-offboard mode."""
        mock_app_controller.mavlink_data_manager.get_data.return_value = 196608  # Position

        data = telemetry_handler.get_follower_data()

        assert 'is_offboard' in data
        assert data['is_offboard'] is False

    def test_flight_mode_text_included(self, telemetry_handler, mock_app_controller, mock_parameters):
        """Test flight mode text is included."""
        data = telemetry_handler.get_follower_data()

        if 'flight_mode_text' in data:
            assert data['flight_mode_text'] == 'Offboard'
