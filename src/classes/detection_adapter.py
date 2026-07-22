"""
Universal detection schema for SmartTracker.

Defines NormalizedDetection — the backend-agnostic detection record consumed by
SmartTracker, TrackingStateManager, and all downstream components.

Backend-specific result parsing lives in the respective backend module
(e.g., classes.backends.ultralytics_backend).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass
class NormalizedDetection:
    """Unified detection record used by SmartTracker internals."""

    track_id: int
    class_id: int
    confidence: float
    aabb_xyxy: Tuple[int, int, int, int]
    center_xy: Tuple[int, int]
    geometry_type: str = "aabb"  # aabb or obb
    obb_xywhr: Optional[Tuple[float, float, float, float, float]] = None
    polygon_xy: Optional[List[Tuple[float, float]]] = None
    rotation_deg: Optional[float] = None
    # ``predict`` results (notably OBB) may not have a persistent identity.
    # Synthetic list-position ids must never be treated as stable IDs.
    track_id_is_stable: bool = True


def to_tracking_state_rows(detections: Sequence[NormalizedDetection]) -> List[List[float]]:
    """Convert normalized detections to tracking manager row format."""
    rows: List[List[float]] = []
    for d in detections:
        x1, y1, x2, y2 = d.aabb_xyxy
        rows.append([
            x1, y1, x2, y2, d.track_id, d.confidence, d.class_id,
            1 if d.track_id_is_stable else 0,
        ])
    return rows
