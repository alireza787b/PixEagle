"""Deterministic tracker-in-loop fixtures.

These helpers create small synthetic frame sequences and replayable gimbal
samples. They are intentionally test-only: production trackers stay unchanged,
while validation tests get deterministic pixels, expected geometry, and
TrackerOutput metadata that can be fed into follower contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace
import time
from typing import Iterable

import numpy as np

from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.trackers.base_tracker import BaseTracker


BBox = tuple[int, int, int, int]


def normalized_center(width: int, height: int, bbox: BBox) -> tuple[float, float]:
    """Return PixEagle's normalized center coordinates for a pixel bbox."""
    x, y, w, h = bbox
    center_x = x + w / 2
    center_y = y + h / 2
    return (
        (center_x - width / 2) / (width / 2),
        (center_y - height / 2) / (height / 2),
    )


@dataclass(frozen=True)
class SyntheticFrameSample:
    index: int
    frame: np.ndarray
    bbox: BBox | None
    visible: bool
    expected_position_2d: tuple[float, float] | None


class SyntheticTargetScene:
    """Synthetic BGR frame sequence with a bright green rectangular target."""

    def __init__(
        self,
        bboxes: Iterable[BBox | None],
        *,
        width: int = 640,
        height: int = 480,
        target_color: tuple[int, int, int] = (0, 255, 0),
    ) -> None:
        self.width = width
        self.height = height
        self.target_color = target_color
        self.samples = [
            self._make_sample(index, bbox)
            for index, bbox in enumerate(bboxes)
        ]

    @classmethod
    def from_clip_manifest(cls, path: Path) -> "SyntheticTargetScene":
        """Load a deterministic simulated clip manifest from JSON."""
        data = json.loads(path.read_text(encoding="utf-8"))
        frames = data.get("frames", [])
        bboxes = [
            tuple(frame["bbox"]) if frame.get("visible", True) else None
            for frame in frames
        ]
        return cls(
            bboxes,
            width=int(data.get("width", 640)),
            height=int(data.get("height", 480)),
            target_color=tuple(data.get("target_color_bgr", [0, 255, 0])),
        )

    def _make_sample(self, index: int, bbox: BBox | None) -> SyntheticFrameSample:
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        expected = None
        visible = bbox is not None
        if bbox is not None:
            x, y, w, h = bbox
            frame[y:y + h, x:x + w] = self.target_color
            expected = normalized_center(self.width, self.height, bbox)
        return SyntheticFrameSample(
            index=index,
            frame=frame,
            bbox=bbox,
            visible=visible,
            expected_position_2d=expected,
        )

    def __iter__(self):
        return iter(self.samples)

    def __getitem__(self, index: int) -> SyntheticFrameSample:
        return self.samples[index]


class ColorBlobTrackerProbe(BaseTracker):
    """Small deterministic tracker probe for synthetic green-target scenes."""

    def _create_tracker(self):
        return None

    def start_tracking(self, frame: np.ndarray, bbox: BBox) -> None:
        self.bbox = bbox
        self.prev_bbox = bbox
        self.prev_center = None
        self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
        self.normalize_bbox()
        self.tracking_started = True
        self.failure_count = 0
        self.confidence = 1.0

    def update(self, frame: np.ndarray) -> tuple[bool, BBox]:
        self.frame_count += 1
        mask = frame[:, :, 1] >= 200
        ys, xs = np.where(mask)
        if xs.size == 0 or ys.size == 0:
            self.failed_frames += 1
            self.failure_count += 1
            return False, self.bbox or (0, 0, 0, 0)

        x_min = int(xs.min())
        x_max = int(xs.max())
        y_min = int(ys.min())
        y_max = int(ys.max())
        bbox = (x_min, y_min, x_max - x_min + 1, y_max - y_min + 1)
        self.prev_bbox = self.bbox
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
        self.normalize_bbox()
        self.tracking_started = True
        self.failure_count = 0
        self.successful_frames += 1
        self.confidence = 1.0
        return True, bbox

    def get_output(self) -> TrackerOutput:
        has_output = self.bbox is not None
        return self._build_output(
            tracker_algorithm="synthetic_color_blob",
            extra_raw={"has_output": has_output},
            extra_metadata={"has_output": has_output},
        )


@dataclass(frozen=True)
class GimbalReplaySample:
    yaw_deg: float
    pitch_deg: float
    roll_deg: float = 0.0
    tracking_active: bool = True
    fresh: bool = True
    confidence: float = 0.95
    reason: str = "measurement"

    def to_tracker_output(self) -> TrackerOutput:
        usable_for_following = bool(self.tracking_active and self.fresh)
        return TrackerOutput(
            data_type=TrackerDataType.GIMBAL_ANGLES,
            timestamp=time.time(),
            tracking_active=self.tracking_active,
            tracker_id="synthetic_gimbal_replay",
            position_2d=(0.0, 0.0),
            angular=(self.yaw_deg, self.pitch_deg, self.roll_deg),
            confidence=self.confidence,
            raw_data={
                "has_output": True,
                "usable_for_following": usable_for_following,
                "data_is_stale": not self.fresh,
                "freshness_reason": self.reason,
            },
            metadata={
                "tracker_class": "GimbalReplayFixture",
                "has_output": True,
                "usable_for_following": usable_for_following,
                "data_is_stale": not self.fresh,
                "freshness_reason": self.reason,
            },
        )


def synthetic_video_handler(width: int = 640, height: int = 480) -> SimpleNamespace:
    return SimpleNamespace(width=width, height=height)
