"""Bounded sender context association using public GStreamer RTP observations.

This module neither imports GI nor enables a media transport. A provider passes
segment running-times from submitted frames and observed payloader packets.
"""

import json
import math
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Mapping, Optional


@dataclass(frozen=True)
class RTPFrameAssociation:
    epoch: str
    running_time_ns: int
    ssrc: int
    rtp_timestamp: int
    metadata_json: bytes

    def metadata(self) -> dict:
        """Return a detached copy; a consumer cannot mutate retained context."""
        return json.loads(self.metadata_json)


@dataclass
class _PendingFrame:
    created_at: float
    metadata_json: bytes
    packet_identity: Optional[tuple[int, int]] = None


class GStreamerFrameAssociation:
    """Associate completed encoded access units without deriving RTP offsets.

    Capture the current epoch in every pipeline callback. Reset retires all
    outstanding contexts, including callbacks from a previous source/session.
    """

    def __init__(self, *, max_pending: int = 64, max_age_seconds: float = 2.0,
                 max_metadata_bytes: int = 32768,
                 clock: Optional[Callable[[], float]] = None):
        if isinstance(max_pending, bool) or not isinstance(max_pending, int) or max_pending < 1:
            raise ValueError("max_pending must be a positive integer")
        if (isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, (int, float))
                or not math.isfinite(max_age_seconds) or max_age_seconds <= 0):
            raise ValueError("max_age_seconds must be finite and positive")
        if (isinstance(max_metadata_bytes, bool) or not isinstance(max_metadata_bytes, int)
                or max_metadata_bytes < 1):
            raise ValueError("max_metadata_bytes must be a positive integer")
        self._max_pending = max_pending
        self._max_age = max_age_seconds
        self._max_metadata = max_metadata_bytes
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._epoch = uuid.uuid4().hex
        self._pending: OrderedDict[int, _PendingFrame] = OrderedDict()
        self._completed: OrderedDict[tuple[int, int], float] = OrderedDict()
        self._last_submitted = -1

    @property
    def epoch(self) -> str:
        with self._lock:
            return self._epoch

    def reset(self) -> str:
        """Start a new provider epoch before source, codec or segment replacement."""
        with self._lock:
            self._epoch = uuid.uuid4().hex
            self._pending.clear()
            self._completed.clear()
            self._last_submitted = -1
            return self._epoch

    @staticmethod
    def _integer(value, maximum: int) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum

    def _prune(self, now: float) -> None:
        while self._pending:
            first = next(iter(self._pending.values()))
            if now - first.created_at <= self._max_age and len(self._pending) <= self._max_pending:
                break
            self._pending.popitem(last=False)
        while self._completed:
            first = next(iter(self._completed.values()))
            if now - first <= self._max_age and len(self._completed) <= self._max_pending:
                break
            self._completed.popitem(last=False)

    def submit(self, epoch: str, running_time_ns: int, metadata: Mapping) -> bool:
        """Freeze context before appsrc submission; reject reused input times."""
        if not self._integer(running_time_ns, (1 << 64) - 2):
            raise ValueError("A valid finite GStreamer running-time is required")
        encoded = json.dumps(dict(metadata), allow_nan=False, separators=(",", ":")).encode()
        if len(encoded) > self._max_metadata:
            raise ValueError("Frame metadata exceeds the bounded context size")
        with self._lock:
            now = self._clock()
            self._prune(now)
            if epoch != self._epoch or running_time_ns <= self._last_submitted:
                return False
            self._pending[running_time_ns] = _PendingFrame(now, encoded)
            self._last_submitted = running_time_ns
            self._prune(now)
            return True

    def discard(self, epoch: str, running_time_ns: int) -> None:
        """Discard a rejected appsrc buffer without assigning it another identity."""
        with self._lock:
            if epoch == self._epoch:
                self._pending.pop(running_time_ns, None)

    def observe_packet(self, epoch: str, running_time_ns: int, ssrc: int,
                       rtp_timestamp: int, *, marker: bool) -> Optional[RTPFrameAssociation]:
        """Emit once at an observed H.264/VP8 access-unit marker, not on receipt.

        The observation is payloader output, not proof of network transmission,
        decode or presentation. All fragments must retain one SSRC/timestamp.
        """
        if (not self._integer(running_time_ns, (1 << 64) - 2)
                or not self._integer(ssrc, (1 << 32) - 1)
                or not self._integer(rtp_timestamp, (1 << 32) - 1)
                or not isinstance(marker, bool)):
            return None
        with self._lock:
            now = self._clock()
            self._prune(now)
            if epoch != self._epoch:
                return None
            frame = self._pending.get(running_time_ns)
            if frame is None:
                return None
            identity = (ssrc, rtp_timestamp)
            conflicting_times = [key for key, pending in self._pending.items()
                                 if key != running_time_ns and pending.packet_identity == identity]
            if conflicting_times:
                for key in (*conflicting_times, running_time_ns):
                    self._pending.pop(key, None)
                self._completed[identity] = now
                self._prune(now)
                return None
            if (identity in self._completed
                    or frame.packet_identity is not None and frame.packet_identity != identity):
                self._pending.pop(running_time_ns, None)
                return None
            frame.packet_identity = identity
            if not marker:
                return None
            self._pending.pop(running_time_ns)
            self._completed[identity] = now
            self._prune(now)
            return RTPFrameAssociation(epoch, running_time_ns, ssrc, rtp_timestamp, frame.metadata_json)

    def snapshot(self) -> dict:
        with self._lock:
            self._prune(self._clock())
            return {"epoch": self._epoch, "pending_frames": len(self._pending),
                    "recent_access_units": len(self._completed),
                    "native_transport_enabled": False, "presentation_verified": False}


def gstreamer_capabilities() -> dict:
    """Optional diagnostics; no GStreamer dependency for existing deployments."""
    requirements = {
        "h264_association": ("appsrc", "videoconvert", "x264enc", "h264parse", "rtph264pay", "appsink"),
        "vp8_association": ("appsrc", "videoconvert", "vp8enc", "rtpvp8pay", "appsink"),
        "webrtc_transport": ("webrtcbin", "nicesrc", "nicesink", "dtlssrtpenc", "dtlssrtpdec", "sctpenc", "sctpdec"),
        "congestion_control": ("rtpgccbwe",),
    }
    result = {"available": False, "native_transport_enabled": False, "presentation_verified": False}
    try:
        import gi
        gi.require_version("Gst", "1.0")
        gi.require_version("GstRtp", "1.0")
        from gi.repository import Gst
        Gst.init(None)
    except (ImportError, ValueError):
        result["reason"] = "GStreamer Python introspection is not installed"
        return result
    result.update(available=True, version=Gst.version_string())
    result["missing_elements"] = {
        group: [name for name in names if Gst.ElementFactory.find(name) is None]
        for group, names in requirements.items()
    }
    return result
