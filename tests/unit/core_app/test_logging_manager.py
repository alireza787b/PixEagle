"""
LoggingManager Unit Tests

Tests for the professional logging manager with spam reduction
and periodic summaries.
"""

import pytest
import time
import logging
from unittest.mock import MagicMock, patch

from classes.logging_manager import LoggingManager, ConnectionStatus


pytestmark = [pytest.mark.unit, pytest.mark.core_app]


class TestConnectionStatus:
    """Tests for ConnectionStatus dataclass."""

    def test_default_values(self):
        """Test default initialization."""
        status = ConnectionStatus()

        assert status.is_connected is False
        assert status.last_connected_time is None
        assert status.last_disconnected_time is None
        assert status.connection_attempts == 0
        assert status.successful_connections == 0
        assert status.last_error is None
        assert status.consecutive_failures == 0
        assert status.last_log_time == 0.0

    def test_custom_values(self):
        """Test custom initialization."""
        status = ConnectionStatus(
            is_connected=True,
            connection_attempts=5,
            successful_connections=3
        )

        assert status.is_connected is True
        assert status.connection_attempts == 5
        assert status.successful_connections == 3


class TestLoggingManagerInit:
    """Tests for LoggingManager initialization."""

    def test_default_summary_interval(self):
        """Test default summary interval."""
        manager = LoggingManager()
        assert manager.summary_interval == 15.0

    def test_custom_summary_interval(self):
        """Test custom summary interval."""
        manager = LoggingManager(summary_interval=30.0)
        assert manager.summary_interval == 30.0

    def test_empty_connections(self):
        """Test connections start empty."""
        manager = LoggingManager()
        assert len(manager._connections) == 0

    def test_empty_polling_stats(self):
        """Test polling stats start empty."""
        manager = LoggingManager()
        assert len(manager._polling_stats) == 0


class TestConnectionStatusLogging:
    """Tests for log_connection_status method."""

    @pytest.fixture
    def manager(self):
        return LoggingManager()

    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=logging.Logger)

    def test_first_connection(self, manager, mock_logger):
        """Test logging first connection."""
        manager.log_connection_status(mock_logger, "TestService", True)

        mock_logger.info.assert_called_once()
        assert "TestService" in str(mock_logger.info.call_args)
        assert "Connected" in str(mock_logger.info.call_args)

    def test_disconnection(self, manager, mock_logger):
        """Test logging disconnection after connection."""
        # First connect
        manager.log_connection_status(mock_logger, "TestService", True)
        mock_logger.reset_mock()

        # Then disconnect
        manager.log_connection_status(mock_logger, "TestService", False)

        mock_logger.warning.assert_called_once()
        assert "Disconnected" in str(mock_logger.warning.call_args)

    def test_connection_state_tracked(self, manager, mock_logger):
        """Test connection state is properly tracked."""
        manager.log_connection_status(mock_logger, "TestService", True)

        assert "TestService" in manager._connections
        status = manager._connections["TestService"]
        assert status.is_connected is True
        assert status.successful_connections == 1

    def test_consecutive_failures_tracked(self, manager, mock_logger):
        """Test consecutive failures are tracked."""
        manager.log_connection_status(mock_logger, "TestService", False)
        manager._connections["TestService"].last_log_time = 0  # Reset for test
        manager.log_connection_status(mock_logger, "TestService", False)

        status = manager._connections["TestService"]
        assert status.consecutive_failures == 2

    def test_connection_resets_failures(self, manager, mock_logger):
        """Test connection resets consecutive failures."""
        manager.log_connection_status(mock_logger, "TestService", False)
        manager.log_connection_status(mock_logger, "TestService", False)
        manager.log_connection_status(mock_logger, "TestService", True)

        status = manager._connections["TestService"]
        assert status.consecutive_failures == 0

    def test_spam_reduction(self, manager, mock_logger):
        """Test spam reduction for repeated disconnection."""
        # First disconnection
        manager.log_connection_status(mock_logger, "TestService", False)

        # Immediate second disconnection (should be filtered)
        manager.log_connection_status(mock_logger, "TestService", False)

        # Only one warning should be logged (initial disconnection)
        assert mock_logger.warning.call_count == 1


class TestPollingActivityLogging:
    """Tests for log_polling_activity method."""

    @pytest.fixture
    def manager(self):
        return LoggingManager(summary_interval=0.1)

    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=logging.Logger)

    def test_successful_poll_tracked(self, manager, mock_logger):
        """Test successful poll is tracked."""
        manager.log_polling_activity(mock_logger, "TestService", True)

        stats = manager._polling_stats["TestService"]
        assert stats['total_polls'] == 1
        assert stats['successful_polls'] == 1
        assert stats['failed_polls'] == 0
        assert stats['current_status'] == 'healthy'

    def test_failed_poll_tracked(self, manager, mock_logger):
        """Test failed poll is tracked."""
        manager.log_polling_activity(mock_logger, "TestService", False)

        stats = manager._polling_stats["TestService"]
        assert stats['total_polls'] == 1
        assert stats['successful_polls'] == 0
        assert stats['failed_polls'] == 1

    def test_degraded_status(self, manager, mock_logger):
        """Test degraded status when failures exceed successes."""
        manager.log_polling_activity(mock_logger, "TestService", True)
        manager.log_polling_activity(mock_logger, "TestService", False)
        manager.log_polling_activity(mock_logger, "TestService", False)

        stats = manager._polling_stats["TestService"]
        assert stats['current_status'] == 'degraded'

    def test_periodic_summary(self, manager, mock_logger):
        """Test periodic summary is logged."""
        # First poll - no summary yet
        manager.log_polling_activity(mock_logger, "TestService", True)
        initial_calls = mock_logger.info.call_count

        # Wait for summary interval
        time.sleep(0.15)

        # Next poll should trigger summary
        manager.log_polling_activity(mock_logger, "TestService", True)

        assert mock_logger.info.call_count > initial_calls


class TestOperationLogging:
    """Tests for log_operation method."""

    @pytest.fixture
    def manager(self):
        manager = LoggingManager()
        manager._spam_cooldown = 0.1  # Short cooldown for testing
        return manager

    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=logging.Logger)

    def test_operation_logged(self, manager, mock_logger):
        """Test operation is logged."""
        manager.log_operation(mock_logger, "TEST_OP", "info", "test details")

        mock_logger.info.assert_called_once()
        assert "TEST_OP" in str(mock_logger.info.call_args)

    def test_operation_counted(self, manager, mock_logger):
        """Test operation is counted."""
        manager.log_operation(mock_logger, "TEST_OP", "info", "test")

        assert manager._operation_counters["TEST_OP"] == 1

    def test_spam_reduction(self, manager, mock_logger):
        """Test spam reduction for operations."""
        manager.log_operation(mock_logger, "TEST_OP", "info", "test")
        manager.log_operation(mock_logger, "TEST_OP", "info", "test")

        # Only first should be logged
        assert mock_logger.info.call_count == 1

    def test_different_operations_not_filtered(self, manager, mock_logger):
        """Test different operations are not filtered."""
        manager.log_operation(mock_logger, "OP_A", "info", "test")
        manager.log_operation(mock_logger, "OP_B", "info", "test")

        assert mock_logger.info.call_count == 2

    def test_log_levels(self, manager, mock_logger):
        """Test different log levels work."""
        manager.log_operation(mock_logger, "OP_DEBUG", "debug", "debug")
        manager.log_operation(mock_logger, "OP_WARN", "warning", "warn")
        manager.log_operation(mock_logger, "OP_ERROR", "error", "error")

        mock_logger.debug.assert_called_once()
        mock_logger.warning.assert_called_once()
        mock_logger.error.assert_called_once()


class TestSystemSummary:
    """Tests for log_system_summary method."""

    @pytest.fixture
    def manager(self):
        return LoggingManager()

    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=logging.Logger)

    def test_summary_header(self, manager, mock_logger):
        """Test summary includes header."""
        manager.log_system_summary(mock_logger)

        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("SYSTEM STATUS SUMMARY" in c for c in calls)

    def test_empty_summary(self, manager, mock_logger):
        """Test summary with no data."""
        manager.log_system_summary(mock_logger)

        # Should still complete without error
        assert mock_logger.info.call_count >= 2  # Header and footer

    def test_connection_status_in_summary(self, manager, mock_logger):
        """Test connection status appears in summary."""
        manager._connections["TestService"] = ConnectionStatus(
            is_connected=True,
            last_connected_time=time.time()
        )

        manager.log_system_summary(mock_logger)

        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Connection Status" in c for c in calls)
        assert any("TestService" in c for c in calls)

    def test_polling_stats_in_summary(self, manager, mock_logger):
        """Test polling stats appear in summary."""
        manager._polling_stats["TestService"] = {
            'total_polls': 100,
            'successful_polls': 95,
            'failed_polls': 5,
            'current_status': 'healthy',
            'last_summary_time': 0
        }

        manager.log_system_summary(mock_logger)

        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Polling Status" in c for c in calls)


class TestSpamFilter:
    """Tests for spam filter functionality."""

    @pytest.fixture
    def manager(self):
        manager = LoggingManager()
        manager._spam_cooldown = 0.1
        return manager

    def test_initial_log_allowed(self, manager):
        """Test first log is always allowed."""
        assert manager._should_log_operation("TEST") is True

    def test_immediate_repeat_blocked(self, manager):
        """Test immediate repeat is blocked."""
        manager._should_log_operation("TEST")
        assert manager._should_log_operation("TEST") is False

    def test_after_cooldown_allowed(self, manager):
        """Test log allowed after cooldown."""
        manager._should_log_operation("TEST")
        time.sleep(0.15)
        assert manager._should_log_operation("TEST") is True

    def test_different_ops_independent(self, manager):
        """Test different operations have independent filters."""
        manager._should_log_operation("OP_A")
        assert manager._should_log_operation("OP_B") is True
