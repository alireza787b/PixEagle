"""
Detection adapter for SmartTracker.

Normalizes Ultralytics results into one geometry-agnostic detection schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
import logging
import math

from classes.geometry_utils import obb_xywhr_to_aabb, validate_obb_xywhr

logger = logging.getLogger(__name__)


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


def _to_list(value: Any) -> List[Any]:
    """Convert torch/numpy-like object to a Python list safely."""
    if value is None:
        return []
    try:
        if hasattr(value, "detach"):
            value = value.detach()
        if hasattr(value, "cpu"):
            value = value.cpu()
        if hasattr(value, "numpy"):
            value = value.numpy()
        if hasattr(value, "tolist"):
            return value.tolist()
    except Exception:
        pass
    if isinstance(value, list):
        return value
    return []


def detect_result_mode(result: Any) -> str:
    """
    Return result mode for a single Ultralytics result item:
    - detect: boxes only
    - obb: obb only
    - mixed: both present
    - none: no detections
    """
    has_boxes = getattr(result, "boxes", None) is not None and len(getattr(result.boxes, "data", [])) > 0
    has_obb = getattr(result, "obb", None) is not None and len(getattr(result.obb, "data", [])) > 0

    if has_boxes and has_obb:
        return "mixed"
    if has_obb:
        return "obb"
    if has_boxes:
        return "detect"
    return "none"


def _parse_boxes(result: Any) -> List[NormalizedDetection]:
    """Parse Ultralytics boxes result."""
    boxes = result.boxes
    if boxes is None:
        return []

    xyxy = _to_list(getattr(boxes, "xyxy", None))
    confs = _to_list(getattr(boxes, "conf", None))
    classes = _to_list(getattr(boxes, "cls", None))
    ids = _to_list(getattr(boxes, "id", None))

    n = min(len(xyxy), len(confs), len(classes))
    out: List[NormalizedDetection] = []
    for i in range(n):
        x1, y1, x2, y2 = xyxy[i]
        if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
            continue
        aabb = (int(x1), int(y1), int(x2), int(y2))
        center = ((aabb[0] + aabb[2]) // 2, (aabb[1] + aabb[3]) // 2)
        track_id = int(ids[i]) if i < len(ids) and ids[i] is not None else -(i + 1)
        out.append(
            NormalizedDetection(
                track_id=track_id,
                class_id=int(classes[i]),
                confidence=float(confs[i]),
                aabb_xyxy=aabb,
                center_xy=center,
                geometry_type="aabb",
            )
        )
    return out


def _parse_obb(result: Any) -> List[NormalizedDetection]:
    """Parse Ultralytics OBB result."""
    obb = result.obb
    if obb is None:
        return []

    xywhr = _to_list(getattr(obb, "xywhr", None))
    confs = _to_list(getattr(obb, "conf", None))
    classes = _to_list(getattr(obb, "cls", None))
    ids = _to_list(getattr(obb, "id", None))
    polys = _to_list(getattr(obb, "xyxyxyxy", None))

    n = min(len(xywhr), len(confs), len(classes))
    out: List[NormalizedDetection] = []
    for i in range(n):
        vals = xywhr[i]
        if len(vals) < 5:
            continue
        cx, cy, w, h, r = map(float, vals[:5])
        obb_xywhr = (cx, cy, w, h, r)
        if not validate_obb_xywhr(obb_xywhr):
            logger.warning("[DetectionAdapter] Skipping invalid OBB geometry")
            continue
        try:
            aabb = obb_xywhr_to_aabb(obb_xywhr)
        except Exception:
            logger.warning("[DetectionAdapter] OBB->AABB conversion failed, skipping detection")
            continue
        center = ((aabb[0] + aabb[2]) // 2, (aabb[1] + aabb[3]) // 2)
        poly = None
        if i < len(polys) and isinstance(polys[i], list) and len(polys[i]) == 4:
            poly = [(float(p[0]), float(p[1])) for p in polys[i]]
        track_id = int(ids[i]) if i < len(ids) and ids[i] is not None else -(i + 1)
        out.append(
            NormalizedDetection(
                track_id=track_id,
                class_id=int(classes[i]),
                confidence=float(confs[i]),
                aabb_xyxy=aabb,
                center_xy=center,
                geometry_type="obb",
                obb_xywhr=obb_xywhr,
                polygon_xy=poly,
                rotation_deg=float(math.degrees(r)),
            )
        )
    return out


def normalize_results(results: Sequence[Any], allow_mixed: bool = False) -> Tuple[str, List[NormalizedDetection]]:
    """
    Normalize first Ultralytics result frame to (mode, detections).
    Raises ValueError on mixed-mode when allow_mixed=False.
    """
    if not results:
        return "none", []

    result = results[0]
    mode = detect_result_mode(result)
    if mode == "mixed" and not allow_mixed:
        raise ValueError("mixed_detect_obb_output_not_supported")
    if mode == "obb":
        return mode, _parse_obb(result)
    if mode == "detect":
        return mode, _parse_boxes(result)
    if mode == "mixed":
        # Prefer OBB when mixed is explicitly allowed.
        dets = _parse_obb(result)
        if not dets:
            dets = _parse_boxes(result)
        return mode, dets
    return "none", []


def to_tracking_state_rows(detections: Sequence[NormalizedDetection]) -> List[List[float]]:
    """Convert normalized detections to tracking manager row format."""
    rows: List[List[float]] = []
    for d in detections:
        x1, y1, x2, y2 = d.aabb_xyxy
        rows.append([x1, y1, x2, y2, d.track_id, d.confidence, d.class_id])
    return rows
