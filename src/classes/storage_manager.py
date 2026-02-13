"""
Storage Manager — Disk space monitoring for video recording.

Monitors free disk space on the recording output directory and provides:
- Periodic free space polling (configurable interval)
- Remaining recording time estimation
- Warning thresholds (configurable)
- Auto-stop trigger when disk space is critically low

Architecture follows the existing manager pattern (OSDModeManager, MavlinkDataManager):
- Background daemon thread for polling
- Thread-safe status access
- Config-driven via Parameters

Author: PixEagle Recording System
"""

import logging
import shutil
from pathlib import Path
import threading
import time
from typing import Any, Dict, Optional

from classes.parameters import Parameters

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Monitors disk space for the recording output directory.

    Starts a background thread that periodically checks free disk space.
    When free space drops below the critical threshold, auto-stops any
    active recording via the linked RecordingManager.
    """

    def __init__(self, recording_manager=None):
        self._recording_manager = recording_manager
        self._output_dir = str(getattr(Parameters, 'RECORDING_OUTPUT_DIR', 'recordings'))
        self._warning_threshold_mb = int(getattr(Parameters, 'STORAGE_WARNING_THRESHOLD_MB', 500))
        self._critical_threshold_mb = int(getattr(Parameters, 'STORAGE_CRITICAL_THRESHOLD_MB', 100))
        self._poll_interval = float(getattr(Parameters, 'STORAGE_POLL_INTERVAL', 10.0))

        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_check: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def start_monitoring(self):
        """Start background disk space monitoring."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="storage-monitor", daemon=True
        )
        self._monitor_thread.start()
        logger.info(
            f"Storage monitoring started: dir={self._output_dir}, "
            f"warning={self._warning_threshold_mb}MB, "
            f"critical={self._critical_threshold_mb}MB, "
            f"interval={self._poll_interval}s"
        )

    def stop_monitoring(self):
        """Stop background monitoring."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=3.0)
            self._monitor_thread = None
        logger.info("Storage monitoring stopped")

    def check_storage(self) -> Dict[str, Any]:
        """
        Check disk space on the recording output directory.

        Returns:
            Dict with free_bytes, free_mb, free_gb, total_bytes, total_gb,
            used_percent, estimated_remaining_seconds, warning_level.
        """
        try:
            # Ensure directory exists before checking
            Path(self._output_dir).mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(self._output_dir)
            free_mb = usage.free / (1024 * 1024)
            free_gb = free_mb / 1024

            used_pct = round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0.0

            # Estimate remaining recording time
            est_remaining = self._estimate_remaining_time(usage.free)

            # Determine warning level
            if free_mb < self._critical_threshold_mb:
                level = "critical"
            elif free_mb < self._warning_threshold_mb:
                level = "warning"
            else:
                level = "ok"

            result = {
                'free_bytes': usage.free,
                'free_mb': round(free_mb, 1),
                'free_gb': round(free_gb, 2),
                'total_bytes': usage.total,
                'total_gb': round(usage.total / (1024 ** 3), 2),
                'used_percent': used_pct,
                'estimated_remaining_seconds': est_remaining,
                'warning_level': level,
            }

            with self._lock:
                self._last_check = result

            return result

        except OSError as e:
            logger.error(f"Storage check failed: {e}")
            error_result = {
                'free_bytes': 0,
                'free_mb': 0,
                'free_gb': 0,
                'total_bytes': 0,
                'total_gb': 0,
                'used_percent': 0,
                'estimated_remaining_seconds': None,
                'warning_level': 'error',
                'error': str(e),
            }
            with self._lock:
                self._last_check = error_result
            return error_result

    @property
    def status(self) -> Dict[str, Any]:
        """Last storage check result (thread-safe)."""
        with self._lock:
            if self._last_check:
                return dict(self._last_check)
        return self.check_storage()

    def _estimate_remaining_time(self, free_bytes: int) -> Optional[float]:
        """
        Estimate remaining recording time from free space and current write rate.

        Returns seconds remaining, or None if estimation is not possible.
        """
        if not self._recording_manager:
            return None

        # Only estimate when actively recording with enough data
        if not self._recording_manager.is_active:
            return None

        stats = self._recording_manager._stats
        meta = self._recording_manager._current_metadata
        if not meta or stats.frames_written < 30:
            return None

        elapsed = time.time() - meta.started_at
        if elapsed <= 0 or stats.file_size_bytes <= 0:
            return None

        bytes_per_sec = stats.file_size_bytes / elapsed
        if bytes_per_sec <= 0:
            return None

        return round(free_bytes / bytes_per_sec, 0)

    def _monitor_loop(self):
        """Background polling loop for disk space monitoring."""
        while not self._stop_event.is_set():
            result = self.check_storage()

            if result.get('warning_level') == 'critical':
                logger.warning(
                    f"CRITICAL: Low disk space ({result.get('free_mb', 0):.0f}MB free). "
                    f"Auto-stopping recording."
                )
                if self._recording_manager and self._recording_manager.is_active:
                    try:
                        self._recording_manager.stop()
                        logger.info("Recording auto-stopped due to critical disk space")
                    except Exception as e:
                        logger.error(f"Failed to auto-stop recording: {e}")

            elif result.get('warning_level') == 'warning':
                logger.warning(
                    f"Low disk space warning: {result.get('free_mb', 0):.0f}MB free "
                    f"(threshold: {self._warning_threshold_mb}MB)"
                )

            self._stop_event.wait(self._poll_interval)
