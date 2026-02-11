# src/classes/frame_publisher.py
"""
Thread-safe frame distribution between producer (main processing thread)
and consumers (FastAPI streaming thread, WebRTC, etc.).

Uses a simple lock + reference-swap pattern. The monotonic frame_id
replaces expensive MD5 hashing for frame deduplication.
"""

import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class StampedFrame:
    """An immutable frame snapshot with metadata."""
    frame: np.ndarray
    frame_id: int
    timestamp: float  # time.monotonic()
    is_osd: bool


class FramePublisher:
    """
    Thread-safe frame publisher.

    Main thread calls publish() after compositing OSD.
    Consumer threads call get_latest() to read the most recent frame.

    Design:
    - Uses threading.Lock for cross-thread safety (main thread vs asyncio thread)
    - frame_id is a monotonic counter — consumers compare it to detect new frames
    - Client counting allows the main loop to skip OSD/resize when no one is connected
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._current_osd: Optional[StampedFrame] = None
        self._current_raw: Optional[StampedFrame] = None
        self._frame_counter: int = 0
        self._client_count: int = 0

    @property
    def has_clients(self) -> bool:
        """Check if any streaming clients are registered."""
        return self._client_count > 0

    @property
    def client_count(self) -> int:
        """Current number of registered clients."""
        return self._client_count

    @property
    def current_frame_id(self) -> int:
        """Most recently published frame ID."""
        return self._frame_counter

    def register_client(self) -> None:
        """Called when a streaming client connects."""
        with self._lock:
            self._client_count += 1

    def unregister_client(self) -> None:
        """Called when a streaming client disconnects."""
        with self._lock:
            self._client_count = max(0, self._client_count - 1)

    def publish(self, osd_frame: Optional[np.ndarray], raw_frame: Optional[np.ndarray]) -> int:
        """
        Publish new frames. Called by main thread after OSD compositing.

        Args:
            osd_frame: Frame with OSD overlays (may be None if OSD disabled)
            raw_frame: Raw frame without overlays (may be None)

        Returns:
            The frame_id assigned to this publication.
        """
        with self._lock:
            self._frame_counter += 1
            ts = time.monotonic()

            if osd_frame is not None:
                self._current_osd = StampedFrame(
                    frame=osd_frame,
                    frame_id=self._frame_counter,
                    timestamp=ts,
                    is_osd=True,
                )

            if raw_frame is not None:
                self._current_raw = StampedFrame(
                    frame=raw_frame,
                    frame_id=self._frame_counter,
                    timestamp=ts,
                    is_osd=False,
                )

            return self._frame_counter

    def get_latest(self, prefer_osd: bool = True) -> Optional[StampedFrame]:
        """
        Get the most recent frame. Called by streaming consumer threads.

        Args:
            prefer_osd: If True, return OSD frame when available; else raw.

        Returns:
            StampedFrame or None if no frame has been published yet.
        """
        with self._lock:
            if prefer_osd and self._current_osd is not None:
                return self._current_osd
            if self._current_raw is not None:
                return self._current_raw
            # Fallback: return whichever exists
            return self._current_osd
