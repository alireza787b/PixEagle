"""Thread-safe immutable pixels and provenance shared by media consumers."""

import threading
import time
import uuid
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Optional

import numpy as np
import cv2

from classes.runtime_identity import INSTANCE_ID, RUNTIME_ID


@dataclass(frozen=True)
class CaptureStamp:
    """Capture observation, distinct from later processing/publication time."""

    source_epoch: Optional[str] = None
    capture_id: Optional[str] = None
    captured_at: Optional[float] = None  # monotonic backend receipt, not sensor exposure
    state: str = "unknown"


@dataclass(frozen=True)
class StampedFrame:
    frame: np.ndarray
    frame_id: int
    timestamp: float
    is_osd: bool
    stream_id: str = ""
    stream_epoch: str = ""
    capture: CaptureStamp = CaptureStamp()
    selection_geometry: Optional[dict] = None

    @property
    def cache_identity(self) -> str:
        return f"{self.stream_id}:{self.stream_epoch}:{self.frame_id}:{self.variant}:{self.frame.shape[:2]}"

    @property
    def variant(self) -> str:
        return "processed_osd" if self.is_osd else "raw"

    def provenance(self, now=None) -> dict:
        now = time.monotonic() if now is None else now
        return {
            "version": "1", "instance_id": INSTANCE_ID, "runtime_id": RUNTIME_ID,
            "stream_id": self.stream_id, "stream_epoch": self.stream_epoch,
            "source_epoch": self.capture.source_epoch, "frame_id": str(self.frame_id),
            "capture_id": self.capture.capture_id, "capture_state": self.capture.state,
            "capture_age_ms": (max(0.0, (now - self.capture.captured_at) * 1000)
                               if self.capture.captured_at is not None else None),
            "publication_age_ms": max(0.0, (now - self.timestamp) * 1000),
            "encoded_width": int(self.frame.shape[1]),
            "encoded_height": int(self.frame.shape[0]),
            "variant": self.variant, "geometry_verified": False,
        }


class FramePublisher:
    """Publish pixels and their provenance in one atomic reference swap.

    Arrays are copied and made read-only; mutating a producer buffer cannot
    change an in-flight JPEG. Legacy integer IDs remain monotonic for ACKs.
    Epochs invalidate encoded caches and work finishing after a source reset.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._current_osd: Optional[StampedFrame] = None
        self._current_raw: Optional[StampedFrame] = None
        self._frame_counter = 0
        self._client_count = 0
        self.stream_id = str(uuid.uuid4())
        self._stream_epoch = str(uuid.uuid4())
        self._source_epoch = None
        self._format_signature = None
        self._selection_frames = OrderedDict()
        self._delivery_variants = OrderedDict()
        self._selection_bytes = 0
        self._delivered_selection_frames = OrderedDict()
        self._delivered_selection_bytes = 0
        self.selection_max_bytes = 128 * 1024 * 1024
        self.selection_max_frames = 90
        self.selection_max_age_ms = 1500
        self.selection_delivery_max_bytes = 96 * 1024 * 1024
        self.selection_delivery_frames_per_client = 3

    @property
    def has_clients(self) -> bool:
        return self._client_count > 0

    @property
    def client_count(self) -> int:
        return self._client_count

    @property
    def current_frame_id(self) -> int:
        return self._frame_counter

    def register_client(self) -> None:
        with self._lock:
            self._client_count += 1

    def unregister_client(self) -> None:
        with self._lock:
            self._client_count = max(0, self._client_count - 1)

    def invalidate_source(self, source_epoch: Optional[str]) -> None:
        """Retire old pixels immediately, including during failed source opens."""
        with self._lock:
            self._source_epoch = source_epoch
            self._stream_epoch = str(uuid.uuid4())
            self._format_signature = None
            self._current_osd = self._current_raw = None
            self._selection_frames.clear()
            self._delivery_variants.clear()
            self._selection_bytes = 0
            self._delivered_selection_frames.clear()
            self._delivered_selection_bytes = 0

    def is_current(self, stamped: StampedFrame) -> bool:
        with self._lock:
            return (stamped.stream_id == self.stream_id
                    and stamped.stream_epoch == self._stream_epoch)

    def publish(self, osd_frame, raw_frame, *, capture: CaptureStamp = CaptureStamp(),
                analysis_frame=None, target_revision=None, candidates=(), geometry_key=(),
                retain_analysis_pixels=True, selectable_variant=None) -> int:
        def owned(frame):
            if frame is None:
                return None
            snapshot = np.array(frame, copy=True)
            if snapshot.ndim not in (2, 3) or min(snapshot.shape[:2]) <= 0:
                raise ValueError("Published frame must contain pixels")
            snapshot.setflags(write=False)
            return snapshot

        osd, raw = owned(osd_frame), owned(raw_frame)
        analysis_shape = None if analysis_frame is None else analysis_frame.shape
        analysis = owned(analysis_frame) if retain_analysis_pixels else None
        if selectable_variant == "processed_osd" and osd is None:
            selectable_variant = "raw"
        elif selectable_variant == "raw" and raw is None:
            selectable_variant = "processed_osd"
        signature = (tuple(None if frame is None else frame.shape for frame in (osd, raw)),
                     analysis_shape, tuple(geometry_key))
        with self._lock:
            # A captured/processed frame from a retired source cannot resurrect it.
            if self._source_epoch is not None and capture.source_epoch != self._source_epoch:
                return self._frame_counter
            if self._source_epoch is None:
                self._source_epoch = capture.source_epoch
            if signature != self._format_signature:
                self._stream_epoch = str(uuid.uuid4())
                self._format_signature = signature
                self._selection_frames.clear()
                self._delivery_variants.clear()
                self._selection_bytes = 0
                self._delivered_selection_frames.clear()
                self._delivered_selection_bytes = 0
            self._frame_counter += 1
            ts = time.monotonic()

            def stamped(frame, is_osd):
                if frame is None:
                    return None
                geometry = None
                selectable = selectable_variant is None or selectable_variant == (
                    "processed_osd" if is_osd else "raw")
                if (selectable and analysis_shape is not None and target_revision is not None
                        and capture.state == "fresh" and capture.captured_at is not None
                        and capture.source_epoch and capture.capture_id):
                    geometry = {
                        "version": "1", "verified": True,
                        "geometry_id": self._stream_epoch, "mapping": "full_frame_scale",
                        "encoded_width": int(frame.shape[1]), "encoded_height": int(frame.shape[0]),
                        "analysis_width": int(analysis_shape[1]), "analysis_height": int(analysis_shape[0]),
                        "target_revision": str(target_revision), "token": uuid.uuid4().hex,
                        "max_age_ms": self.selection_max_age_ms,
                    }
                result = StampedFrame(
                    frame, self._frame_counter, ts, is_osd,
                    self.stream_id, self._stream_epoch, capture, geometry,
                )
                if geometry is not None:
                    self._selection_frames[geometry["token"]] = {
                        "stamped": result, "analysis": analysis,
                        "candidates": deepcopy(tuple(candidates)),
                        "geometry_key": tuple(geometry_key),
                    }
                    self._selection_bytes += (analysis.nbytes if analysis is not None else 0) + frame.nbytes
                return result
            # Missing variants are removed, never inherited from older pixels.
            self._current_osd = stamped(osd, True)
            self._current_raw = stamped(raw, False)
            self._prune_selection_frames(ts)
            self._prune_delivered_selection_frames(ts)
            return self._frame_counter

    def _prune_selection_frames(self, now):
        while self._selection_frames:
            entry = next(iter(self._selection_frames.values()))
            capture_time = entry["stamped"].capture.captured_at
            if (len(self._selection_frames) <= self.selection_max_frames
                    and self._selection_bytes <= self.selection_max_bytes
                    and (now - capture_time) * 1000 <= self.selection_max_age_ms):
                break
            _, removed = self._selection_frames.popitem(last=False)
            analysis = removed["analysis"]
            self._selection_bytes -= (analysis.nbytes if analysis is not None else 0) + removed["stamped"].frame.nbytes

    @staticmethod
    def _selection_entry_bytes(entry):
        analysis = entry["analysis"]
        return (analysis.nbytes if analysis is not None else 0) + entry["stamped"].frame.nbytes

    def _remove_delivered_selection_frame(self, key):
        entry = self._delivered_selection_frames.pop(key)
        self._delivered_selection_bytes -= self._selection_entry_bytes(entry)

    def _prune_delivered_selection_frames(self, now):
        for key, entry in tuple(self._delivered_selection_frames.items()):
            captured_at = entry["stamped"].capture.captured_at
            if (captured_at is None or
                    (now - captured_at) * 1000 > self.selection_max_age_ms):
                self._remove_delivered_selection_frame(key)
        while self._delivered_selection_bytes > self.selection_delivery_max_bytes:
            self._remove_delivered_selection_frame(next(iter(self._delivered_selection_frames)))

    def pin_selection_delivery(self, stamped: StampedFrame, client_id: str) -> bool:
        """Hold a frame actually sampled for WebSocket delivery until its age limit."""
        with self._lock:
            if not self.is_current(stamped) or stamped.selection_geometry is None:
                return False
            token = stamped.selection_geometry["token"]
            entry = self._selection_frames.get(token)
            if entry is None:
                return False
            key = (client_id, token)
            if key not in self._delivered_selection_frames:
                self._delivered_selection_frames[key] = entry
                self._delivered_selection_bytes += self._selection_entry_bytes(entry)
            client_keys = [item for item in self._delivered_selection_frames if item[0] == client_id]
            for old_key in client_keys[:-self.selection_delivery_frames_per_client]:
                self._remove_delivered_selection_frame(old_key)
            self._prune_delivered_selection_frames(time.monotonic())
            return key in self._delivered_selection_frames

    def delivery_variant(self, stamped: StampedFrame, scale: float) -> StampedFrame:
        """Retain exact geometry for a negotiated, uniformly downscaled delivery."""
        if scale >= 1.0:
            return stamped
        if not 0.25 <= scale < 1.0:
            raise ValueError("Delivery scale must be between 0.25 and 1")
        height, width = stamped.frame.shape[:2]
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        key = (stamped.cache_identity, size)
        with self._lock:
            cached = self._delivery_variants.get(key)
            if cached is not None:
                return cached
        pixels = cv2.resize(stamped.frame, size,
                            interpolation=cv2.INTER_AREA)
        pixels.setflags(write=False)
        geometry = stamped.selection_geometry
        with self._lock:
            if not self.is_current(stamped):
                return stamped
            cached = self._delivery_variants.get(key)
            if cached is not None:
                return cached
            entry = self._selection_frames.get(geometry["token"]) if geometry else None
            if geometry is not None:
                geometry = dict(geometry, token=uuid.uuid4().hex,
                                encoded_width=pixels.shape[1], encoded_height=pixels.shape[0])
            result = replace(stamped, frame=pixels, selection_geometry=geometry if entry else None)
            if entry is not None:
                replacement = dict(entry, stamped=result)
                self._selection_frames[geometry["token"]] = replacement
                self._selection_bytes += self._selection_entry_bytes(replacement)
                self._prune_selection_frames(time.monotonic())
            self._delivery_variants[key] = result
            while len(self._delivery_variants) > 4:
                self._delivery_variants.popitem(last=False)
            return result

    def unpin_selection_client(self, client_id: str) -> None:
        with self._lock:
            for key in tuple(self._delivered_selection_frames):
                if key[0] == client_id:
                    self._remove_delivered_selection_frame(key)

    def selection_snapshot(self, token):
        """Return retained immutable pixels; absence never substitutes latest."""
        with self._lock:
            entry = self._selection_frames.get(token)
            if entry is None:
                self._prune_delivered_selection_frames(time.monotonic())
                entry = next((value for (client, frame_token), value in self._delivered_selection_frames.items()
                              if frame_token == token), None)
            if entry is None:
                return None
            return {**entry, "candidates": deepcopy(entry["candidates"])}

    @property
    def control_source_epoch(self):
        """Read the immutable source identity without waiting on frame/model work.

        Camera control checks this again before dispatch and on its watchdog;
        geometry consumers must still use selection_transaction/video_context.
        """
        return self._source_epoch

    def selection_transaction(self):
        """Serialize source retirement with validation and synchronous commit."""
        return self._lock

    def _latest(self, prefer_osd):
        if prefer_osd and self._current_osd is not None:
            return self._current_osd
        return self._current_raw if self._current_raw is not None else self._current_osd

    def get_latest(self, prefer_osd=True) -> Optional[StampedFrame]:
        with self._lock:
            return self._latest(prefer_osd)

    def video_context(self, prefer_osd=True) -> dict:
        with self._lock:
            frame = self._latest(prefer_osd)
            return {
                "provenance_version": "1", "ws_path": "/ws/video_feed",
                "delivery_scaling_version": "1",
                "stream_id": self.stream_id, "stream_epoch": self._stream_epoch,
                "source_epoch": self._source_epoch,
                "width": int(frame.frame.shape[1]) if frame else None,
                "height": int(frame.frame.shape[0]) if frame else None,
                "variant": frame.variant if frame else None,
                # The context is not a new capture observation. Only each JPEG
                # carries the stamped capture state and measured capture age.
                "capture_state": "unknown" if frame else "unavailable",
                "geometry_verified": False,
            }
