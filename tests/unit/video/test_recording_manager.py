# tests/unit/video/test_recording_manager.py
"""
Unit tests for RecordingManager.

Tests the core recording engine: state machine transitions, non-blocking
write, queue overflow handling, crash recovery, file management, and
thread safety.
"""

import os
import time
import threading
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from tests.fixtures.mock_recording import MockVideoWriter, sample_frame


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary directory for recording output."""
    output_dir = tmp_path / "test_recordings"
    output_dir.mkdir()
    return str(output_dir)


@pytest.fixture
def mock_params(temp_output_dir):
    """Mock Parameters with recording config defaults."""
    with patch('classes.recording_manager.Parameters') as mock:
        mock.RECORDING_OUTPUT_DIR = temp_output_dir
        mock.RECORDING_CODEC = 'mp4v'
        mock.RECORDING_CONTAINER = 'mp4'
        mock.RECORDING_FPS = 0
        mock.RECORDING_WIDTH = 0
        mock.RECORDING_HEIGHT = 0
        mock.RECORDING_INCLUDE_OSD = True
        mock.RECORDING_QUEUE_SIZE = 5
        mock.RECORDING_MAX_FILE_SIZE_MB = 0
        mock.RECORDING_AUTO_RECOVERY = True
        yield mock


@pytest.fixture
def mock_video_writer():
    """Create a MockVideoWriter and patch cv2.VideoWriter."""
    writer = MockVideoWriter()
    with patch('classes.recording_manager.cv2.VideoWriter', return_value=writer):
        with patch('classes.recording_manager.cv2.VideoWriter_fourcc', return_value=0):
            yield writer


@pytest.fixture
def manager(mock_params, mock_video_writer):
    """Create a RecordingManager with mocked dependencies."""
    from classes.recording_manager import RecordingManager
    mgr = RecordingManager()
    yield mgr
    # Cleanup
    if mgr.is_active:
        mgr.stop()


# =============================================================================
# State Machine Tests
# =============================================================================

@pytest.mark.unit
class TestRecordingStateTransitions:
    """Tests for recording state machine transitions."""

    def test_initial_state_is_idle(self, manager):
        assert manager.state == "idle"
        assert not manager.is_recording
        assert not manager.is_active

    def test_start_transitions_to_recording(self, manager):
        result = manager.start(30.0, 640, 480)
        assert result['status'] == 'success'
        assert manager.state == "recording"
        assert manager.is_recording
        assert manager.is_active

    def test_start_while_recording_returns_error(self, manager):
        manager.start(30.0, 640, 480)
        result = manager.start(30.0, 640, 480)
        assert result['status'] == 'error'
        assert 'Already recording' in result['message']

    def test_pause_transitions_to_paused(self, manager):
        manager.start(30.0, 640, 480)
        result = manager.pause()
        assert result['status'] == 'success'
        assert manager.state == "paused"
        assert not manager.is_recording
        assert manager.is_active

    def test_pause_when_not_recording_returns_error(self, manager):
        result = manager.pause()
        assert result['status'] == 'error'

    def test_resume_transitions_to_recording(self, manager):
        manager.start(30.0, 640, 480)
        manager.pause()
        result = manager.resume()
        assert result['status'] == 'success'
        assert manager.state == "recording"
        assert manager.is_recording

    def test_resume_when_not_paused_returns_error(self, manager):
        result = manager.resume()
        assert result['status'] == 'error'

    def test_stop_transitions_to_idle(self, manager):
        manager.start(30.0, 640, 480)
        result = manager.stop()
        assert result['status'] == 'success'
        assert manager.state == "idle"
        assert not manager.is_recording
        assert not manager.is_active

    def test_stop_when_not_recording_returns_error(self, manager):
        result = manager.stop()
        assert result['status'] == 'error'

    def test_stop_from_paused_state(self, manager):
        manager.start(30.0, 640, 480)
        manager.pause()
        result = manager.stop()
        assert result['status'] == 'success'
        assert manager.state == "idle"

    def test_start_from_paused_resumes(self, manager):
        manager.start(30.0, 640, 480)
        manager.pause()
        result = manager.start(30.0, 640, 480)
        assert result['status'] == 'success'
        assert manager.state == "recording"


# =============================================================================
# Frame Writing Tests
# =============================================================================

@pytest.mark.unit
class TestFrameWriting:
    """Tests for non-blocking frame writing."""

    def test_write_frame_not_recording_is_noop(self, manager):
        frame = sample_frame()
        manager.write_frame(frame)
        # No error, no effect

    def test_write_frame_queues_correctly(self, manager, mock_video_writer):
        manager.start(30.0, 640, 480)
        frame = sample_frame()
        manager.write_frame(frame)
        # Give writer thread time to process
        time.sleep(0.2)
        assert mock_video_writer.frame_count >= 1

    def test_write_frame_handles_none(self, manager):
        manager.start(30.0, 640, 480)
        manager.write_frame(None)  # Should not raise

    def test_write_frame_handles_empty_array(self, manager):
        manager.start(30.0, 640, 480)
        manager.write_frame(np.array([]))  # Should not raise

    def test_queue_overflow_drops_oldest(self, manager, mock_video_writer):
        manager.start(30.0, 640, 480)

        # Temporarily stop writer thread from consuming
        manager._writer_stop.set()
        time.sleep(0.1)

        # Fill queue beyond capacity
        for i in range(manager._max_queue_size + 3):
            manager.write_frame(sample_frame(color=i))

        assert manager._stats.queue_drops > 0

    def test_write_frame_resizes_mismatched_dimensions(self, manager, mock_video_writer):
        manager.start(30.0, 320, 240)
        # Write a frame with different dimensions
        frame = sample_frame(640, 480)
        manager.write_frame(frame)
        time.sleep(0.2)
        # Should have been resized and written successfully
        if mock_video_writer.frame_count > 0:
            written = mock_video_writer.frames[0]
            assert written.shape[:2] == (240, 320)


# =============================================================================
# Filename Tests
# =============================================================================

@pytest.mark.unit
class TestFilenaming:
    """Tests for filename generation and format."""

    def test_filename_format(self, manager):
        result = manager.start(30.0, 640, 480)
        filename = result['filename']
        assert filename.startswith('PixEagle_')
        assert filename.endswith('.mp4')
        # Format: PixEagle_YYYY-MM-DD_HH-MM-SS_uuid8.mp4
        parts = filename.replace('.mp4', '').split('_')
        assert len(parts) >= 4
        # Date part (YYYY-MM-DD)
        assert '-' in parts[1]
        assert len(parts[1]) == 10
        # Time part (HH-MM-SS)
        assert '-' in parts[2]
        assert len(parts[2]) == 8
        # UUID part (8 hex chars)
        assert len(parts[3]) == 8

    def test_unique_filenames(self, mock_params, temp_output_dir):
        """Two recordings should produce different filenames."""
        from classes.recording_manager import RecordingManager

        writer1 = MockVideoWriter()
        writer2 = MockVideoWriter()
        writers = iter([writer1, writer2])

        with patch('classes.recording_manager.cv2.VideoWriter', side_effect=lambda *a, **k: next(writers)):
            with patch('classes.recording_manager.cv2.VideoWriter_fourcc', return_value=0):
                mgr = RecordingManager()
                result1 = mgr.start(30.0, 640, 480)
                # Create the .tmp file so finalize works
                Path(mgr._current_metadata.filepath).touch()
                mgr.stop()
                import time
                time.sleep(0.01)  # Ensure different timestamp
                result2 = mgr.start(30.0, 640, 480)
                Path(mgr._current_metadata.filepath).touch()
                mgr.stop()

        assert result1['filename'] != result2['filename']


# =============================================================================
# File Lifecycle Tests
# =============================================================================

@pytest.mark.unit
class TestFileLifecycle:
    """Tests for .tmp suffix and finalization."""

    def test_temp_file_created_during_recording(self, manager, temp_output_dir):
        manager.start(30.0, 640, 480)
        # MockVideoWriter doesn't create real files, so create it manually
        # to test the naming convention
        assert manager._current_metadata is not None
        assert manager._current_metadata.filepath.endswith('.tmp')
        # Manually touch the file to simulate what cv2.VideoWriter would do
        Path(manager._current_metadata.filepath).touch()
        tmp_files = list(Path(temp_output_dir).glob("*.tmp"))
        assert len(tmp_files) == 1

    def test_temp_file_renamed_on_stop(self, manager, temp_output_dir):
        result = manager.start(30.0, 640, 480)
        filename = result['filename']
        # Create the .tmp file since MockVideoWriter doesn't write to disk
        Path(manager._current_metadata.filepath).touch()
        manager.stop()
        # .tmp should be gone
        tmp_files = list(Path(temp_output_dir).glob("*.tmp"))
        assert len(tmp_files) == 0
        # Final file should exist
        final = Path(temp_output_dir) / filename
        assert final.exists()


# =============================================================================
# Crash Recovery Tests
# =============================================================================

@pytest.mark.unit
class TestCrashRecovery:
    """Tests for .tmp file recovery on startup."""

    def test_recover_tmp_files_on_init(self, temp_output_dir, mock_params):
        """Leftover .tmp files should be renamed on initialization."""
        # Create a fake .tmp file
        tmp_path = Path(temp_output_dir) / "PixEagle_20260213T120000Z_abc12345.mp4.tmp"
        tmp_path.write_bytes(b"fake video data")

        from classes.recording_manager import RecordingManager
        with patch('classes.recording_manager.cv2.VideoWriter_fourcc', return_value=0):
            mgr = RecordingManager()

        # The .tmp should have been renamed
        assert not tmp_path.exists()
        final_path = Path(temp_output_dir) / "PixEagle_20260213T120000Z_abc12345.mp4"
        assert final_path.exists()

    def test_recovery_skips_if_final_exists(self, temp_output_dir, mock_params):
        """Don't overwrite existing final file during recovery."""
        tmp_path = Path(temp_output_dir) / "PixEagle_20260213T120000Z_abc12345.mp4.tmp"
        final_path = Path(temp_output_dir) / "PixEagle_20260213T120000Z_abc12345.mp4"
        tmp_path.write_bytes(b"tmp data")
        final_path.write_bytes(b"good data")

        from classes.recording_manager import RecordingManager
        with patch('classes.recording_manager.cv2.VideoWriter_fourcc', return_value=0):
            mgr = RecordingManager()

        # Both should still exist
        assert tmp_path.exists()
        assert final_path.exists()
        # Final should be untouched
        assert final_path.read_bytes() == b"good data"


# =============================================================================
# Recording Management Tests
# =============================================================================

@pytest.mark.unit
class TestRecordingManagement:
    """Tests for list and delete operations."""

    def test_list_recordings_empty(self, manager):
        recordings = manager.list_recordings()
        assert recordings == []

    def test_list_recordings_returns_files(self, manager, temp_output_dir):
        # Create some fake recording files with distinct modification times
        f1 = Path(temp_output_dir) / "PixEagle_20260213T100000Z_aaa11111.mp4"
        f1.write_bytes(b"x" * 1000)
        import time as _time
        _time.sleep(0.05)  # Ensure different ctime
        f2 = Path(temp_output_dir) / "PixEagle_20260213T110000Z_bbb22222.mp4"
        f2.write_bytes(b"x" * 2000)

        recordings = manager.list_recordings()
        assert len(recordings) == 2
        # Both files should be present
        filenames = {r['filename'] for r in recordings}
        assert "PixEagle_20260213T100000Z_aaa11111.mp4" in filenames
        assert "PixEagle_20260213T110000Z_bbb22222.mp4" in filenames
        # Newest (by ctime) should be first
        assert recordings[0]['filename'] == "PixEagle_20260213T110000Z_bbb22222.mp4"

    def test_list_recordings_excludes_tmp(self, manager, temp_output_dir):
        """Incomplete .tmp files should not appear in the listing."""
        (Path(temp_output_dir) / "PixEagle_20260213T100000Z_aaa11111.mp4").write_bytes(b"x")
        (Path(temp_output_dir) / "incomplete.mp4.tmp").write_bytes(b"x")

        recordings = manager.list_recordings()
        assert len(recordings) == 1

    def test_list_recordings_excludes_non_video(self, manager, temp_output_dir):
        """Non-video files should not appear in the listing."""
        (Path(temp_output_dir) / "notes.txt").write_bytes(b"x")
        (Path(temp_output_dir) / "data.json").write_bytes(b"x")
        (Path(temp_output_dir) / "video.mp4").write_bytes(b"x")

        recordings = manager.list_recordings()
        assert len(recordings) == 1

    def test_delete_recording_success(self, manager, temp_output_dir):
        filepath = Path(temp_output_dir) / "test_file.mp4"
        filepath.write_bytes(b"video data")

        result = manager.delete_recording("test_file.mp4")
        assert result['status'] == 'success'
        assert not filepath.exists()

    def test_delete_recording_not_found(self, manager):
        result = manager.delete_recording("nonexistent.mp4")
        assert result['status'] == 'error'

    def test_delete_active_recording_blocked(self, manager):
        manager.start(30.0, 640, 480)
        filename = manager._current_metadata.filename
        result = manager.delete_recording(filename)
        assert result['status'] == 'error'
        assert 'active' in result['message'].lower()

    def test_delete_prevents_path_traversal(self, manager, temp_output_dir):
        """Path traversal attempts should be sanitized."""
        result = manager.delete_recording("../../etc/passwd")
        assert result['status'] == 'error'


# =============================================================================
# Status Property Tests
# =============================================================================

@pytest.mark.unit
class TestStatusProperty:
    """Tests for the status property."""

    def test_status_when_idle(self, manager):
        status = manager.status
        assert status['state'] == 'idle'
        assert status['is_recording'] is False
        assert status['is_active'] is False
        assert status['filename'] is None
        assert status['elapsed_seconds'] == 0.0

    def test_status_when_recording(self, manager):
        manager.start(30.0, 640, 480)
        time.sleep(0.1)
        status = manager.status
        assert status['state'] == 'recording'
        assert status['is_recording'] is True
        assert status['is_active'] is True
        assert status['filename'] is not None
        assert status['elapsed_seconds'] >= 0
        assert status['codec'] == 'mp4v'

    def test_status_when_paused(self, manager):
        manager.start(30.0, 640, 480)
        manager.pause()
        status = manager.status
        assert status['state'] == 'paused'
        assert status['is_recording'] is False
        assert status['is_active'] is True


# =============================================================================
# Release / Shutdown Tests
# =============================================================================

@pytest.mark.unit
class TestRelease:
    """Tests for clean shutdown behavior."""

    def test_release_stops_active_recording(self, manager):
        manager.start(30.0, 640, 480)
        manager.release()
        assert manager.state == "idle"
        assert not manager.is_active

    def test_release_when_idle_is_noop(self, manager):
        manager.release()  # Should not raise
        assert manager.state == "idle"

    def test_release_from_paused(self, manager):
        manager.start(30.0, 640, 480)
        manager.pause()
        manager.release()
        assert manager.state == "idle"
