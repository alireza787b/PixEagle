import math

from classes.geometry_utils import (
    normalize_angle_degrees,
    obb_xywhr_to_aabb,
    obb_xywhr_to_polygon,
    point_in_polygon,
    validate_obb_xywhr,
)


def test_validate_obb_xywhr():
    assert validate_obb_xywhr((10.0, 10.0, 20.0, 5.0, 0.0))
    assert not validate_obb_xywhr((10.0, 10.0, 0.0, 5.0, 0.0))
    assert not validate_obb_xywhr((10.0, 10.0, 20.0, -1.0, 0.0))
    assert not validate_obb_xywhr((10.0, 10.0, 20.0, 5.0, float("nan")))


def test_obb_to_polygon_and_aabb():
    poly = obb_xywhr_to_polygon((100.0, 120.0, 40.0, 20.0, math.radians(45)))
    assert len(poly) == 4
    x1, y1, x2, y2 = obb_xywhr_to_aabb((100.0, 120.0, 40.0, 20.0, math.radians(45)))
    assert x2 > x1
    assert y2 > y1


def test_point_in_polygon():
    poly = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert point_in_polygon((5.0, 5.0), poly)
    assert not point_in_polygon((15.0, 5.0), poly)


def test_normalize_angle_degrees():
    assert normalize_angle_degrees(190.0) == -170.0
    assert normalize_angle_degrees(-190.0) == 170.0
