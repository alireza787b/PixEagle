# tests/fixtures/mock_recording.py
"""
Mock recording objects for testing RecordingManager and StorageManager.

Provides mock implementations of cv2.VideoWriter and recording-related
utilities for isolated unit testing without requiring actual video I/O.
"""

import numpy as np
from typing import List, Optional
from unittest.mock import MagicMock


class MockVideoWriter:
    """
    Mock cv2.VideoWriter for testing RecordingManager.

    Records frames in memory instead of writing to disk.
    Can simulate failure states for error testing.

    Attributes:
        frames: List of frames "written"
        is_opened: Whether writer is currently open
        fail_on_write: If True, write() raises an exception
    """

    def __init__(self, *args, **kwargs):
        self._opened = True
        self.frames: List[np.ndarray] = []
        self.fail_on_write = False
        self._init_args = args
        self._init_kwargs = kwargs

    def isOpened(self) -> bool:
        return self._opened

    def write(self, frame: np.ndarray):
        if self.fail_on_write:
            raise IOError("Simulated write failure")
        if self._opened:
            self.frames.append(frame)

    def release(self):
        self._opened = False

    @property
    def frame_count(self) -> int:
        return len(self.frames)


def sample_frame(width: int = 640, height: int = 480, color: int = 0) -> np.ndarray:
    """
    Create a sample BGR frame for testing.

    Args:
        width: Frame width in pixels
        height: Frame height in pixels
        color: Fill value (0-255) for all channels

    Returns:
        numpy array of shape (height, width, 3) dtype uint8
    """
    return np.full((height, width, 3), color, dtype=np.uint8)


def create_mock_parameters(**overrides):
    """
    Create a mock Parameters class with recording defaults.

    Args:
        **overrides: Parameter overrides (e.g., RECORDING_CODEC='XVID')

    Returns:
        MagicMock configured with recording parameter attributes
    """
    defaults = {
        'ENABLE_RECORDING': True,
        'RECORDING_OUTPUT_DIR': 'test_recordings',
        'RECORDING_CODEC': 'mp4v',
        'RECORDING_CONTAINER': 'mp4',
        'RECORDING_FPS': 0,
        'RECORDING_WIDTH': 0,
        'RECORDING_HEIGHT': 0,
        'RECORDING_INCLUDE_OSD': True,
        'RECORDING_QUEUE_SIZE': 5,
        'RECORDING_MAX_FILE_SIZE_MB': 0,
        'RECORDING_AUTO_RECOVERY': True,
        'STORAGE_WARNING_THRESHOLD_MB': 500,
        'STORAGE_CRITICAL_THRESHOLD_MB': 100,
        'STORAGE_POLL_INTERVAL': 10.0,
    }
    defaults.update(overrides)

    mock = MagicMock()
    for key, value in defaults.items():
        setattr(mock, key, value)

    # Make getattr work with defaults
    def mock_getattr(name, default=None):
        return defaults.get(name, default)

    mock.__getattr__ = mock_getattr
    return mock
