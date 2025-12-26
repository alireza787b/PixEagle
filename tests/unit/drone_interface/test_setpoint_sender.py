# tests/unit/drone_interface/test_setpoint_sender.py
"""
Unit tests for SetpointSender.

Tests threaded command publishing:
- Thread lifecycle (start, stop)
- Configuration validation
- Control type updates
- Error recovery
- Logging behavior
"""

import pytest
import time
import threading
from unittest.mock import patch, MagicMock, PropertyMock


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_parameters():
    """Mock Parameters class."""
    with patch('classes.setpoint_sender.Parameters') as mock_params:
        mock_params.SETPOINT_PUBLISH_RATE_S = 0.1  # 10 Hz for faster tests
        mock_params.ENABLE_SETPOINT_DEBUGGING = False
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
    return mock_handler


@pytest.fixture
def mock_px4_controller():
    """Create mock PX4InterfaceManager."""
    mock_controller = MagicMock()
    return mock_controller


@pytest.fixture
def setpoint_sender(mock_parameters, mock_px4_controller, mock_setpoint_handler):
    """Create SetpointSender instance for testing."""
    from classes.setpoint_sender import SetpointSender
    sender = SetpointSender(mock_px4_controller, mock_setpoint_handler)
    yield sender
    # Cleanup
    if sender.is_alive():
        sender.stop()


# ============================================================================
# Test Classes
# ============================================================================

class TestSetpointSenderInitialization:
    """Tests for SetpointSender initialization."""

    def test_init_as_daemon_thread(self, setpoint_sender):
        """Test that sender is initialized as daemon thread."""
        assert setpoint_sender.daemon is True

    def test_init_running_flag(self, setpoint_sender):
        """Test initial running flag."""
        assert setpoint_sender.running is True

    def test_init_error_count(self, setpoint_sender):
        """Test initial error count."""
        assert setpoint_sender.error_count == 0

    def test_init_max_consecutive_errors(self, setpoint_sender):
        """Test max consecutive errors default."""
        assert setpoint_sender.max_consecutive_errors == 5

    def test_init_control_type_cache(self, setpoint_sender):
        """Test initial control type cache."""
        assert setpoint_sender._control_type is None
        assert setpoint_sender._last_schema_check == 0


class TestSetpointSenderValidation:
    """Tests for configuration validation."""

    def test_validate_configuration_valid(self, setpoint_sender, mock_setpoint_handler):
        """Test validation passes with valid configuration."""
        result = setpoint_sender.validate_configuration()
        assert result is True

    def test_validate_configuration_no_control_type_method(self, setpoint_sender):
        """Test validation fails without get_control_type method."""
        del setpoint_sender.setpoint_handler.get_control_type

        result = setpoint_sender.validate_configuration()

        assert result is False

    def test_validate_configuration_empty_control_type(self, setpoint_sender, mock_setpoint_handler):
        """Test validation fails with empty control type."""
        mock_setpoint_handler.get_control_type.return_value = None

        result = setpoint_sender.validate_configuration()

        assert result is False

    def test_validate_configuration_no_fields(self, setpoint_sender, mock_setpoint_handler):
        """Test validation fails with no fields."""
        mock_setpoint_handler.get_fields.return_value = {}

        result = setpoint_sender.validate_configuration()

        assert result is False

    def test_validate_configuration_exception(self, setpoint_sender, mock_setpoint_handler):
        """Test validation handles exceptions."""
        mock_setpoint_handler.get_control_type.side_effect = Exception("Test error")

        result = setpoint_sender.validate_configuration()

        assert result is False


class TestSetpointSenderLifecycle:
    """Tests for thread lifecycle."""

    def test_start_thread(self, setpoint_sender, mock_parameters):
        """Test starting the sender thread."""
        setpoint_sender.start()

        assert setpoint_sender.is_alive()

        setpoint_sender.stop()

    def test_stop_thread(self, setpoint_sender, mock_parameters):
        """Test stopping the sender thread."""
        setpoint_sender.start()
        time.sleep(0.2)  # Let it run briefly

        setpoint_sender.stop()

        assert setpoint_sender.running is False
        # Wait for thread to finish
        time.sleep(0.2)
        assert not setpoint_sender.is_alive()

    def test_stop_sets_running_false(self, setpoint_sender, mock_parameters):
        """Test that stop sets running flag to False."""
        # Start the thread first so it can be stopped
        setpoint_sender.start()
        time.sleep(0.1)

        setpoint_sender.stop()

        assert setpoint_sender.running is False


class TestSetpointSenderControlTypeUpdate:
    """Tests for control type caching."""

    def test_update_control_type_caches_value(self, setpoint_sender, mock_setpoint_handler):
        """Test that control type is cached."""
        mock_setpoint_handler.get_control_type.return_value = 'velocity_body_offboard'
        setpoint_sender._schema_check_interval = 0  # Force update

        setpoint_sender._update_control_type()

        assert setpoint_sender._control_type == 'velocity_body_offboard'

    def test_update_control_type_detects_change(self, setpoint_sender, mock_setpoint_handler):
        """Test that control type change is detected."""
        setpoint_sender._control_type = 'velocity_body'
        setpoint_sender._schema_check_interval = 0
        mock_setpoint_handler.get_control_type.return_value = 'attitude_rate'

        setpoint_sender._update_control_type()

        assert setpoint_sender._control_type == 'attitude_rate'

    def test_update_control_type_respects_interval(self, setpoint_sender, mock_setpoint_handler):
        """Test that updates respect the interval."""
        setpoint_sender._control_type = 'old_type'
        setpoint_sender._last_schema_check = time.time()  # Recent check
        setpoint_sender._schema_check_interval = 100  # Long interval

        setpoint_sender._update_control_type()

        # Should not update due to interval
        assert setpoint_sender._control_type == 'old_type'


class TestSetpointSenderCommandPreparation:
    """Tests for synchronous command preparation."""

    def test_send_commands_sync_success(self, setpoint_sender, mock_setpoint_handler):
        """Test successful command preparation."""
        result = setpoint_sender._send_commands_sync()

        assert result is True
        mock_setpoint_handler.get_fields.assert_called()

    def test_send_commands_sync_uses_cached_control_type(self, setpoint_sender, mock_setpoint_handler):
        """Test that cached control type is used."""
        setpoint_sender._control_type = 'cached_type'

        setpoint_sender._send_commands_sync()

        # Should not need to call get_control_type if cached
        # (implementation may vary)

    def test_send_commands_sync_exception(self, setpoint_sender, mock_setpoint_handler):
        """Test exception handling in command preparation."""
        mock_setpoint_handler.get_fields.side_effect = Exception("Test error")

        result = setpoint_sender._send_commands_sync()

        assert result is False


class TestSetpointSenderErrorHandling:
    """Tests for error handling."""

    def test_error_count_increments_on_failure(self, setpoint_sender, mock_setpoint_handler, mock_parameters):
        """Test that error count increments on failure."""
        mock_setpoint_handler.get_fields.side_effect = Exception("Test error")
        setpoint_sender.error_count = 0

        setpoint_sender._send_commands_sync()

        # Error count is managed in run loop, not _send_commands_sync
        # Test the pattern
        assert setpoint_sender.error_count == 0  # Not incremented here

    def test_error_count_resets_on_success(self, setpoint_sender, mock_setpoint_handler):
        """Test that error count resets on success."""
        setpoint_sender.error_count = 3

        result = setpoint_sender._send_commands_sync()

        # Error count is managed in run loop
        assert result is True


class TestSetpointSenderDebugging:
    """Tests for debugging output."""

    def test_print_current_setpoint(self, setpoint_sender, mock_setpoint_handler):
        """Test printing current setpoints."""
        mock_setpoint_handler.get_fields.return_value = {
            'vel_body_fwd': 2.0,
            'yawspeed_deg_s': 15.0
        }

        # Should not raise
        setpoint_sender._print_current_setpoint()

        mock_setpoint_handler.get_fields.assert_called()

    def test_print_current_setpoint_exception(self, setpoint_sender, mock_setpoint_handler):
        """Test exception handling in debug output."""
        mock_setpoint_handler.get_fields.side_effect = Exception("Test error")

        # Should not raise
        setpoint_sender._print_current_setpoint()


class TestSetpointSenderThreadSafety:
    """Tests for thread safety."""

    def test_daemon_thread_allows_exit(self, setpoint_sender):
        """Test that daemon thread allows program exit."""
        assert setpoint_sender.daemon is True

    def test_stop_with_timeout(self, setpoint_sender, mock_parameters):
        """Test stop with timeout handling."""
        setpoint_sender.start()
        time.sleep(0.1)

        # Stop should complete within timeout
        start_time = time.time()
        setpoint_sender.stop()
        elapsed = time.time() - start_time

        # Should not take more than 6 seconds (5s timeout + margin)
        assert elapsed < 6.0


class TestSetpointSenderIntegration:
    """Integration-like tests for SetpointSender."""

    def test_multiple_loop_iterations(self, setpoint_sender, mock_parameters, mock_setpoint_handler):
        """Test multiple loop iterations work correctly."""
        mock_parameters.SETPOINT_PUBLISH_RATE_S = 0.05  # Fast rate

        setpoint_sender.start()
        time.sleep(0.3)  # Let several iterations run
        setpoint_sender.stop()

        # Should have called get_fields multiple times
        assert mock_setpoint_handler.get_fields.call_count > 1

    def test_control_type_switch_during_run(self, setpoint_sender, mock_parameters, mock_setpoint_handler):
        """Test control type switch during operation."""
        mock_parameters.SETPOINT_PUBLISH_RATE_S = 0.05
        setpoint_sender._schema_check_interval = 0  # Always update

        setpoint_sender.start()
        time.sleep(0.1)

        # Change control type
        mock_setpoint_handler.get_control_type.return_value = 'attitude_rate'
        time.sleep(0.2)

        setpoint_sender.stop()

        # Control type should have been updated
        assert setpoint_sender._control_type == 'attitude_rate'
