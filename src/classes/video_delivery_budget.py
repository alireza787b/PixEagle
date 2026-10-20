"""Shared video payload admission, independent of capture/control traffic."""

import math
import threading
import time
from typing import Callable, Optional


class VideoDeliveryBudget:
    """Reserve encoded ceilings and JPEG serialization within one payload budget.

    The caller waits the returned delay before sending one JPEG. Reservations
    hold no payloads and cannot extend beyond max_delay_seconds. Rejections
    do not consume capacity. A cancelled sender may waste its reservation for
    at most that bounded horizon; there is no background queue to drain.
    Native encoder reservations are target ceilings, not a wire-rate shaper:
    RTCP/retransmission/protocol overhead remains outside this payload budget.
    GCC still estimates link capacity and may reduce each reserved target.
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
        self._bitrate_bps = bitrate_kbps * 1000
        self._max_delay = max_delay_seconds
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._reserved_until: Optional[float] = None
        self._encoded: dict[str, int] = {}

    @property
    def bitrate_bps(self) -> float:
        return self._bitrate_bps

    def reserve_encoded(self, owner: str, bitrate_bps: int) -> Optional[float]:
        """Hold a ceiling until encoder teardown; drain earlier JPEG slots first.

        The caller must wait the returned bounded delay before starting media.
        Rejected or duplicate owners consume nothing. Always retain positive
        JPEG capacity so fallback is not starved by encoded admission.
        """
        if not isinstance(owner, str) or not owner or len(owner) > 128:
            raise ValueError("A bounded encoder owner is required")
        if type(bitrate_bps) is not int or bitrate_bps <= 0:
            raise ValueError("Encoder ceiling must be a positive integer")
        with self._lock:
            if owner in self._encoded or sum(self._encoded.values()) + bitrate_bps >= self._bitrate_bps:
                return None
            self._encoded[owner] = bitrate_bps
            now = self._clock()
            return max(0.0, (self._reserved_until or now) - now)

    def release_encoded(self, owner: str) -> None:
        """Release only after its encoder/transport no longer owns resources."""
        with self._lock:
            self._encoded.pop(owner, None)

    def snapshot(self) -> dict:
        with self._lock:
            encoded = sum(self._encoded.values())
            return {"payload_budget_bps": self._bitrate_bps,
                    "native_encoder_ceiling_bps": encoded,
                    "jpeg_available_bps": self._bitrate_bps - encoded,
                    "native_reservations": len(self._encoded)}

    @property
    def max_frame_bytes(self) -> int:
        """Largest JPEG that can fit the bounded scheduling horizon."""
        with self._lock:
            return int((self._bitrate_bps - sum(self._encoded.values())) / 8 * self._max_delay)

    def reserve(self, frame_size_bytes: int) -> Optional[float]:
        """Return a bounded wait before sending, or None if capacity is unavailable."""
        if (isinstance(frame_size_bytes, bool) or not isinstance(frame_size_bytes, int)
                or frame_size_bytes <= 0):
            raise ValueError("JPEG byte count must be a positive integer")
        with self._lock:
            duration = frame_size_bytes * 8 / (self._bitrate_bps - sum(self._encoded.values()))
            if duration > self._max_delay:
                return None
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
