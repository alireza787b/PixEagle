# tests/unit/video/test_storage_manager.py
"""
Unit tests for StorageManager.

Tests disk space monitoring, warning levels, remaining time estimation,
and auto-stop behavior when disk space is critically low.
"""

import os
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from tests.fixtures.mock_recording import create_mock_parameters


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary directory for storage monitoring."""
    output_dir = tmp_path / "test_recordings"
    output_dir.mkdir()
    return str(output_dir)


@pytest.fixture
def mock_params(temp_output_dir):
    """Mock Parameters with storage config defaults."""
    with patch('classes.storage_manager.Parameters') as mock:
        mock.RECORDING_OUTPUT_DIR = temp_output_dir
        mock.STORAGE_WARNING_THRESHOLD_MB = 500
        mock.STORAGE_CRITICAL_THRESHOLD_MB = 100
        mock.STORAGE_POLL_INTERVAL = 10.0
        yield mock


# =============================================================================
# Storage Check Tests
# =============================================================================

@pytest.mark.unit
class TestStorageCheck:
    """Tests for check_storage() method."""

    def test_check_storage_returns_required_keys(self, mock_params, temp_output_dir):
        from classes.storage_manager import StorageManager
        sm = StorageManager()
        result = sm.check_storage()

        required_keys = [
            'free_bytes', 'free_mb', 'free_gb',
            'total_bytes', 'total_gb', 'used_percent',
            'estimated_remaining_seconds', 'warning_level',
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_check_storage_free_values_positive(self, mock_params, temp_output_dir):
        from classes.storage_manager import StorageManager
        sm = StorageManager()
        result = sm.check_storage()

        assert result['free_bytes'] > 0
        assert result['free_mb'] > 0
        assert result['free_gb'] > 0
        assert result['total_bytes'] > 0

    def test_check_storage_used_percent_valid(self, mock_params, temp_output_dir):
        from classes.storage_manager import StorageManager
        sm = StorageManager()
        result = sm.check_storage()

        assert 0 <= result['used_percent'] <= 100

    def test_check_storage_updates_last_check(self, mock_params, temp_output_dir):
        from classes.storage_manager import StorageManager
        sm = StorageManager()
        result = sm.check_storage()
        assert sm.status == result


# =============================================================================
# Warning Level Tests
# =============================================================================

@pytest.mark.unit
class TestWarningLevels:
    """Tests for warning level classification."""

    def test_warning_level_ok(self, temp_output_dir):
        """Normal disk space should return 'ok'."""
        with patch('classes.storage_manager.Parameters') as mock:
            mock.RECORDING_OUTPUT_DIR = temp_output_dir
            mock.STORAGE_WARNING_THRESHOLD_MB = 1      # Very low thresholds
            mock.STORAGE_CRITICAL_THRESHOLD_MB = 0.5
            mock.STORAGE_POLL_INTERVAL = 10.0

            from classes.storage_manager import StorageManager
            sm = StorageManager()
            result = sm.check_storage()
            assert result['warning_level'] == 'ok'

    def test_warning_level_with_high_threshold(self, temp_output_dir):
        """Setting threshold higher than available space should trigger warning."""
        with patch('classes.storage_manager.Parameters') as mock:
            mock.RECORDING_OUTPUT_DIR = temp_output_dir
            mock.STORAGE_WARNING_THRESHOLD_MB = 999999999  # Unreasonably high
            mock.STORAGE_CRITICAL_THRESHOLD_MB = 1
            mock.STORAGE_POLL_INTERVAL = 10.0

            from classes.storage_manager import StorageManager
            sm = StorageManager()
            result = sm.check_storage()
            assert result['warning_level'] in ('warning', 'critical')

    def test_warning_level_critical_with_high_threshold(self, temp_output_dir):
        """Setting critical threshold higher than available space should return critical."""
        with patch('classes.storage_manager.Parameters') as mock:
            mock.RECORDING_OUTPUT_DIR = temp_output_dir
            mock.STORAGE_WARNING_THRESHOLD_MB = 999999999
            mock.STORAGE_CRITICAL_THRESHOLD_MB = 999999999
            mock.STORAGE_POLL_INTERVAL = 10.0

            from classes.storage_manager import StorageManager
            sm = StorageManager()
            result = sm.check_storage()
            assert result['warning_level'] == 'critical'


# =============================================================================
# Remaining Time Estimation Tests
# =============================================================================

@pytest.mark.unit
class TestRemainingTimeEstimation:
    """Tests for remaining recording time estimation."""

    def test_no_estimation_without_recording_manager(self, mock_params):
        from classes.storage_manager import StorageManager
        sm = StorageManager(recording_manager=None)
        result = sm.check_storage()
        assert result['estimated_remaining_seconds'] is None

    def test_no_estimation_when_not_recording(self, mock_params):
        mock_rm = MagicMock()
        mock_rm.is_active = False

        from classes.storage_manager import StorageManager
        sm = StorageManager(recording_manager=mock_rm)
        result = sm.check_storage()
        assert result['estimated_remaining_seconds'] is None

    def test_estimation_when_recording(self, mock_params, temp_output_dir):
        """Should estimate remaining time based on write rate."""
        mock_rm = MagicMock()
        mock_rm.is_active = True
        mock_rm._stats = MagicMock()
        mock_rm._stats.frames_written = 100
        mock_rm._stats.file_size_bytes = 10 * 1024 * 1024  # 10MB
        mock_rm._current_metadata = MagicMock()
        mock_rm._current_metadata.started_at = time.time() - 10  # 10 seconds ago

        from classes.storage_manager import StorageManager
        sm = StorageManager(recording_manager=mock_rm)
        result = sm.check_storage()

        assert result['estimated_remaining_seconds'] is not None
        assert result['estimated_remaining_seconds'] > 0

    def test_no_estimation_with_few_frames(self, mock_params):
        """Should not estimate with less than 30 frames."""
        mock_rm = MagicMock()
        mock_rm.is_active = True
        mock_rm._stats = MagicMock()
        mock_rm._stats.frames_written = 5  # Too few
        mock_rm._current_metadata = MagicMock()

        from classes.storage_manager import StorageManager
        sm = StorageManager(recording_manager=mock_rm)
        result = sm.check_storage()
        assert result['estimated_remaining_seconds'] is None


# =============================================================================
# Auto-Stop Tests
# =============================================================================

@pytest.mark.unit
class TestAutoStop:
    """Tests for auto-stop on critical disk space."""

    def test_auto_stop_on_critical(self, temp_output_dir):
        """Recording should be stopped when disk space is critical."""
        mock_rm = MagicMock()
        mock_rm.is_active = True
        mock_rm.stop.return_value = {'status': 'success'}
        # Provide real values to avoid MagicMock comparison errors in estimation
        mock_rm._stats.frames_written = 0
        mock_rm._stats.file_size_bytes = 0
        mock_rm._current_metadata = None

        with patch('classes.storage_manager.Parameters') as mock:
            mock.RECORDING_OUTPUT_DIR = temp_output_dir
            mock.STORAGE_WARNING_THRESHOLD_MB = 999999999
            mock.STORAGE_CRITICAL_THRESHOLD_MB = 999999999  # Always critical
            mock.STORAGE_POLL_INTERVAL = 0.1  # Fast polling for test

            from classes.storage_manager import StorageManager
            sm = StorageManager(recording_manager=mock_rm)
            sm.start_monitoring()
            time.sleep(0.5)  # Wait for at least one poll cycle
            sm.stop_monitoring()

            # Recording should have been stopped
            mock_rm.stop.assert_called()


# =============================================================================
# Monitoring Lifecycle Tests
# =============================================================================

@pytest.mark.unit
class TestMonitoringLifecycle:
    """Tests for start/stop monitoring."""

    def test_start_stop_monitoring(self, mock_params):
        from classes.storage_manager import StorageManager
        sm = StorageManager()
        sm.start_monitoring()
        assert sm._monitor_thread is not None
        assert sm._monitor_thread.is_alive()
        sm.stop_monitoring()
        assert sm._monitor_thread is None

    def test_double_start_is_safe(self, mock_params):
        from classes.storage_manager import StorageManager
        sm = StorageManager()
        sm.start_monitoring()
        sm.start_monitoring()  # Should not create second thread
        sm.stop_monitoring()

    def test_stop_without_start_is_safe(self, mock_params):
        from classes.storage_manager import StorageManager
        sm = StorageManager()
        sm.stop_monitoring()  # Should not raise

    def test_status_property_returns_dict(self, mock_params):
        from classes.storage_manager import StorageManager
        sm = StorageManager()
        status = sm.status
        assert isinstance(status, dict)
        assert 'warning_level' in status
