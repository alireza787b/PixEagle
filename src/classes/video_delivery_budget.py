"""Shared bounded JPEG pacing, independent of capture and control traffic."""

import math
import threading
import time
from typing import Callable, Optional


class VideoDeliveryBudget:
    """Reserve JPEG serialization time against an aggregate decimal-kbps budget.

    The caller waits the returned delay before sending one JPEG. Reservations
    hold no payloads and cannot extend beyond max_delay_seconds. Rejections
    do not consume capacity. A cancelled sender may waste its reservation for
    at most that bounded horizon; there is no background queue to drain.
    WebRTC's negotiated media and congestion control are outside this budget.
    """

    def __init__(
        self, bitrate_kbps: float, *, max_delay_seconds: float = 0.25,
        clock: Optional[Callable[[], float]] = None,
    ):
        if (isinstance(bitrate_kbps, bool) or not isinstance(bitrate_kbps, (int, float))
                or not math.isfinite(bitrate_kbps) or bitrate_kbps <= 0):
            raise ValueError("Video bitrate budget must be finite and positive")
        if (isinstance(max_delay_seconds, bool) or not isinstance(max_delay_seconds, (int, float))
                or not math.isfinite(max_delay_seconds) or not 0 < max_delay_seconds <= 0.25):
            raise ValueError("Video budget delay must be greater than zero and at most 0.25 seconds")
        self._bytes_per_second = bitrate_kbps * 1000 / 8
        self._max_delay = max_delay_seconds
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._reserved_until: Optional[float] = None

    @property
    def max_frame_bytes(self) -> int:
        """Largest JPEG that can fit the bounded scheduling horizon."""
        return int(self._bytes_per_second * self._max_delay)

    def reserve(self, frame_size_bytes: int) -> Optional[float]:
        """Return a bounded wait before sending, or None if capacity is unavailable."""
        if (isinstance(frame_size_bytes, bool) or not isinstance(frame_size_bytes, int)
                or frame_size_bytes <= 0):
            raise ValueError("JPEG byte count must be a positive integer")
        duration = frame_size_bytes / self._bytes_per_second
        if duration > self._max_delay:
            return None
        with self._lock:
            now = self._clock()
            finish = max(now, self._reserved_until or now) + duration
            delay = finish - now
            # Do not lose a slot solely to addition rounding at the horizon.
            tolerance = max(1e-12, math.ulp(now) * 4)
            if delay > self._max_delay + tolerance:
                return None
            delay = min(delay, self._max_delay)
            self._reserved_until = now + delay
            return delay
