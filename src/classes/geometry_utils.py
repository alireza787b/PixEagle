"""
Geometry helpers for SmartTracker.

This module provides robust utilities for oriented bounding boxes (OBB) with
safe fallbacks so tracker pipelines do not crash on malformed geometry.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple


Point2D = Tuple[float, float]
AABB = Tuple[int, int, int, int]  # x1, y1, x2, y2
OBBXYWHR = Tuple[float, float, float, float, float]  # cx, cy, w, h, rad


def is_finite_number(value: float) -> bool:
    """Return True when value is finite."""
    return math.isfinite(value)


def validate_obb_xywhr(obb: Sequence[float]) -> bool:
    """Validate OBB tuple in (cx, cy, w, h, rad) format."""
    if len(obb) != 5:
        return False
    cx, cy, w, h, r = obb
    if not all(is_finite_number(v) for v in (cx, cy, w, h, r)):
        return False
    if w <= 0 or h <= 0:
        return False
    return True


def normalize_angle_degrees(deg: float) -> float:
    """Normalize degrees to [-180, 180)."""
    v = ((deg + 180.0) % 360.0) - 180.0
    return v


def obb_xywhr_to_polygon(obb: OBBXYWHR) -> List[Point2D]:
    """
    Convert OBB (cx, cy, w, h, rad) to 4 polygon points (clockwise).
    Raises ValueError on invalid geometry.
    """
    if not validate_obb_xywhr(obb):
        raise ValueError("invalid_obb_xywhr")

    cx, cy, w, h, rad = obb
    cos_t = math.cos(rad)
    sin_t = math.sin(rad)
    hw = w / 2.0
    hh = h / 2.0

    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    points: List[Point2D] = []
    for x, y in corners:
        rx = x * cos_t - y * sin_t + cx
        ry = x * sin_t + y * cos_t + cy
        points.append((rx, ry))
    return points


def polygon_to_aabb(points: Iterable[Point2D]) -> AABB:
    """Convert polygon points into integer AABB (x1, y1, x2, y2)."""
    pts = list(points)
    if len(pts) < 3:
        raise ValueError("invalid_polygon")
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if not xs or not ys:
        raise ValueError("invalid_polygon")
    if not all(math.isfinite(v) for v in xs + ys):
        raise ValueError("non_finite_polygon")
    return (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))


def obb_xywhr_to_aabb(obb: OBBXYWHR) -> AABB:
    """Convert OBB (cx, cy, w, h, rad) to integer AABB."""
    return polygon_to_aabb(obb_xywhr_to_polygon(obb))


def point_in_polygon(point: Point2D, polygon: Sequence[Point2D]) -> bool:
    """
    Ray casting point-in-polygon test.
    Includes points on boundary by epsilon-safe arithmetic.
    """
    if len(polygon) < 3:
        return False

    x, y = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def clip_aabb_to_frame(aabb: AABB, width: int, height: int) -> Optional[AABB]:
    """Clip AABB to frame bounds. Returns None if fully outside."""
    x1, y1, x2, y2 = aabb
    cx1 = max(0, min(x1, width - 1))
    cy1 = max(0, min(y1, height - 1))
    cx2 = max(0, min(x2, width - 1))
    cy2 = max(0, min(y2, height - 1))
    if cx2 <= cx1 or cy2 <= cy1:
        return None
    return (cx1, cy1, cx2, cy2)
