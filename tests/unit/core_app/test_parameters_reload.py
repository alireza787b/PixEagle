"""
Tests for Parameters.reload_config() functionality (v5.3.0+)
=============================================================

Tests the hot-reload capability of the Parameters class,
including thread safety and SafetyManager integration.

Run with: pytest tests/unit/core_app/test_parameters_reload.py -v
"""

import os
import sys
import pytest
import threading
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from classes.parameters import Parameters


class TestParametersReloadConfig:
    """Test Parameters.reload_config() method."""

    def test_reload_config_returns_bool(self):
        """reload_config should return a boolean."""
        result = Parameters.reload_config()
        assert isinstance(result, bool)

    def test_reload_config_success_returns_true(self):
        """Successful reload should return True."""
        # Default config file should exist and be valid
        result = Parameters.reload_config()
        assert result is True

    def test_reload_config_invalid_file_returns_false(self):
        """Invalid config file should return False."""
        result = Parameters.reload_config('nonexistent_config_file.yaml')
        assert result is False

    def test_reload_config_updates_class_attributes(self):
        """reload_config should update class attributes."""
        # First ensure config is loaded
        Parameters.reload_config()

        # Get current value of an attribute that should exist
        assert hasattr(Parameters, 'ALTITUDE_FAILSAFE_ENABLED')
        original_value = Parameters.ALTITUDE_FAILSAFE_ENABLED

        # Reload should work
        result = Parameters.reload_config()
        assert result is True

        # Value should still be accessible (and same since we didn't change file)
        assert hasattr(Parameters, 'ALTITUDE_FAILSAFE_ENABLED')
        assert Parameters.ALTITUDE_FAILSAFE_ENABLED == original_value

    def test_reload_config_is_thread_safe(self):
        """Multiple concurrent reload calls should not cause race conditions."""
        results = []
        errors = []

        def reload_task():
            try:
                result = Parameters.reload_config()
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [threading.Thread(target=reload_task) for _ in range(10)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0, f"Errors occurred during concurrent reload: {errors}"

        # All reloads should have succeeded
        assert all(r is True for r in results), "Some reloads failed"
        assert len(results) == 10


class TestParametersReloadSafetyManager:
    """Test SafetyManager integration with reload."""

    @patch('classes.parameters._get_safety_manager')
    def test_reload_notifies_safety_manager(self, mock_get_safety_manager):
        """reload_config should notify SafetyManager to reload."""
        # Setup mock
        mock_safety_manager = MagicMock()
        mock_safety_manager.load_from_config = MagicMock()
        mock_get_safety_manager.return_value = mock_safety_manager

        # Trigger reload
        result = Parameters.reload_config()

        # Verify SafetyManager was notified
        assert result is True
        mock_get_safety_manager.assert_called()

    @patch('classes.parameters._get_safety_manager')
    def test_reload_continues_if_safety_manager_fails(self, mock_get_safety_manager):
        """reload_config should continue even if SafetyManager fails."""
        # Setup mock to raise exception
        mock_get_safety_manager.side_effect = Exception("SafetyManager error")

        # Reload should still succeed (config loading is primary)
        result = Parameters.reload_config()
        assert result is True


class TestParametersReloadEdgeCases:
    """Test edge cases for reload functionality."""

    def test_reload_with_custom_config_path(self):
        """reload_config should work with custom config path."""
        # Use the default config path explicitly
        result = Parameters.reload_config('configs/config.yaml')
        assert result is True

    def test_reload_preserves_raw_config(self):
        """reload_config should preserve _raw_config for SafetyManager."""
        Parameters.reload_config()
        assert hasattr(Parameters, '_raw_config')
        assert Parameters._raw_config is not None

    def test_reload_multiple_times(self):
        """Multiple sequential reloads should all succeed."""
        for i in range(5):
            result = Parameters.reload_config()
            assert result is True, f"Reload {i+1} failed"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
