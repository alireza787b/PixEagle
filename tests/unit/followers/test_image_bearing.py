"""Independent pinhole projections exercise dormant image-bearing contracts."""

from dataclasses import FrozenInstanceError, replace
import math

import numpy as np
import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.frame_publisher import CaptureStamp
from classes.guidance_observation import (
    CalibratedBearing,
    ImageMeasurement,
    ObservationProvenance,
    PinholeCalibration,
)
from classes.image_bearing import image_to_body_bearing


def _provenance():
    return ObservationProvenance("camera-1", 7, "geometry-3", "calibration-2",
                                 CaptureStamp("source-4", "frame-15", 100.0, "fresh"))


def _calibration():
    return PinholeCalibration(
        "camera-1", "calibration-2", (1280, 960), (900.0, 850.0), (640.0, 480.0),
        Quaternion(0.5, 0.5, 0.5, 0.5), "none",
    )


def _measurement(pixel=(640.0, 480.0)):
    return ImageMeasurement(_provenance(), pixel, (1280, 960), (1.0, 0.0, 0.0, 0.0, 1.0, 0.0), True)


def _current():
    return dict(source_id="camera-1", source_epoch="source-4", target_generation=7,
                geometry_revision="geometry-3", calibration_revision="calibration-2",
                now_monotonic_s=100.25, max_receipt_age_s=0.5)


def _rotation(roll, pitch, yaw):
    """Independent active Rz Ry Rx matrices, without production quaternion math."""
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    return (np.array(((cy, -sy, 0.0), (sy, cy, 0.0), (0.0, 0.0, 1.0)))
            @ np.array(((cp, 0.0, sp), (0.0, 1.0, 0.0), (-sp, 0.0, cp)))
            @ np.array(((1.0, 0.0, 0.0), (0.0, cr, -sr), (0.0, sr, cr))))


def _multiply_quaternions(left, right):
    w, x, y, z = left
    a, b, c, d = right
    return Quaternion(w*a-x*b-y*c-z*d, w*b+x*a+y*d-z*c,
                      w*c-x*d+y*a+z*b, w*d+x*c-y*b+z*a)


@pytest.mark.parametrize("attitude,target", [
    ((0.0, 0.0, 0.0), (120.0, 35.0, 10.0)),
    ((0.3, -0.2, 0.4), (120.0, 35.0, 10.0)),
    ((-0.25, 0.15, -0.3), (120.0, 5.0, -10.0)),
    ((0.25, -0.15, 3.12), (-120.0, 10.0, 0.0)),
    ((-0.2, 0.15, -3.12), (-120.0, -10.0, -10.0)),
])
def test_world_projection_recovers_body_direction_with_combined_aircraft_and_mount_rotation(attitude, target):
    aircraft = _rotation(*attitude)
    installation = _rotation(0.12, -0.08, 0.05)
    optical_basis = np.array(((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
    optical_to_body = installation @ optical_basis
    delta = np.array(target) - np.array((4.0, -2.0, -20.0))
    camera = optical_to_body.T @ aircraft.T @ delta
    assert camera[2] > 0.0
    pixel = (900.0 * camera[0] / camera[2] + 640.0, 850.0 * camera[1] / camera[2] + 480.0)
    mount = Quaternion.from_euler(0.12, -0.08, 0.05)
    calibration = replace(_calibration(), optical_to_body=_multiply_quaternions(
        (mount.w, mount.x, mount.y, mount.z), (0.5, 0.5, 0.5, 0.5),
    ))

    bearing = image_to_body_bearing(_measurement(pixel), calibration)

    direction = np.array((bearing.direction_body_frd.x, bearing.direction_body_frd.y, bearing.direction_body_frd.z))
    assert direction == pytest.approx(aircraft.T @ delta / np.linalg.norm(delta))
    assert aircraft @ direction == pytest.approx(delta / np.linalg.norm(delta))


@pytest.mark.parametrize("turn", [0, 90, 180, 270])
@pytest.mark.parametrize("mirror", ["none", "horizontal", "vertical", "both"])
def test_declared_inverse_recovers_crop_resize_rotation_and_mirror(turn, mirror):
    # Forward fixture mapping: crop (160,80), resize 960x720 to 480x360,
    # rotate, then mirror. Pixel-centre resize offsets remain explicit.
    forward = np.array(((0.5, 0.0, -80.25), (0.0, 0.5, -40.25), (0.0, 0.0, 1.0)))
    width, height = 480, 360
    if turn == 90:
        forward = np.array(((0.0, -1.0, height - 1), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))) @ forward
        width, height = height, width
    elif turn == 180:
        forward = np.array(((-1.0, 0.0, width - 1), (0.0, -1.0, height - 1), (0.0, 0.0, 1.0))) @ forward
    elif turn == 270:
        forward = np.array(((0.0, 1.0, 0.0), (-1.0, 0.0, width - 1), (0.0, 0.0, 1.0))) @ forward
        width, height = height, width
    if mirror in {"horizontal", "both"}:
        forward = np.array(((-1.0, 0.0, width - 1), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))) @ forward
    if mirror in {"vertical", "both"}:
        forward = np.array(((1.0, 0.0, 0.0), (0.0, -1.0, height - 1), (0.0, 0.0, 1.0))) @ forward
    calibration_pixel = np.array((730.0, 390.0, 1.0))
    pixel = forward @ calibration_pixel
    inverse = np.linalg.inv(forward)
    measurement = ImageMeasurement(_provenance(), tuple(pixel[:2]), (width, height),
                                   tuple(inverse[:2].reshape(-1)), True)

    bearing = image_to_body_bearing(measurement, _calibration())

    expected = np.array((1.0, (730.0 - 640.0) / 900.0, (390.0 - 480.0) / 850.0))
    expected /= np.linalg.norm(expected)
    assert (bearing.direction_body_frd.x, bearing.direction_body_frd.y, bearing.direction_body_frd.z) == pytest.approx(expected)
    assert bearing.provenance is measurement.provenance


def test_centre_and_offcentre_pixels_use_calibrated_intrinsics_without_aim_subtraction():
    assert image_to_body_bearing(_measurement(), _calibration()).direction_body_frd == Vector3(1.0, 0.0, 0.0)
    bearing = image_to_body_bearing(_measurement((820.0, 650.0)), _calibration())
    expected = Vector3(1.0, 0.2, 0.2).normalized()
    assert (bearing.direction_body_frd.x, bearing.direction_body_frd.y, bearing.direction_body_frd.z) == pytest.approx(
        (expected.x, expected.y, expected.z),
    )
    assert bearing.frame == "physical_body_frd"


def test_contracts_and_capture_identity_are_immutable_without_fabricated_exposure_time():
    measurement = _measurement()
    bearing = image_to_body_bearing(measurement, _calibration())
    assert bearing.provenance is measurement.provenance
    assert bearing.provenance.capture is measurement.provenance.capture
    assert bearing.provenance.time_basis == "backend_receipt"
    for value, attribute, replacement in (
        (measurement, "measured", False), (bearing, "frame", "ned"),
        (measurement.provenance, "target_generation", 8),
        (measurement.provenance.capture, "captured_at", 101.0),
        (_calibration(), "revision", "replacement"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(value, attribute, replacement)
    measurement.provenance.require_current(**_current())
    measurement.provenance.require_current(**{**_current(), "now_monotonic_s": 100.5})
    assert measurement.provenance.capture.captured_at == 100.0


def test_uncalibrated_measured_pixels_preserve_real_geometry_and_capture_identity():
    calibrated = _measurement((820.0, 650.0))
    provenance = replace(calibrated.provenance, calibration_revision=None)
    measurement = replace(calibrated, provenance=provenance, image_to_calibration=None)

    measurement.provenance.require_current(**{**_current(), "calibration_revision": None})

    assert measurement.measured
    assert measurement.pixel_xy == (820.0, 650.0)
    assert measurement.image_size_px == calibrated.image_size_px
    assert measurement.provenance.geometry_revision == calibrated.provenance.geometry_revision
    assert measurement.provenance.capture is calibrated.provenance.capture
    assert measurement.provenance.calibration_revision is None
    assert measurement.image_to_calibration is None


@pytest.mark.parametrize("revision,mapping,reason", [
    (None, None, "image_calibration_unavailable"),
    (None, (1.0, 0.0, 0.0, 0.0, 1.0, 0.0), "image_calibration_unavailable"),
    ("calibration-2", None, "image_calibration_mapping_unavailable"),
])
def test_bearing_conversion_requires_actual_calibration_and_declared_mapping(revision, mapping, reason):
    measurement = replace(_measurement(), provenance=replace(_provenance(), calibration_revision=revision),
                          image_to_calibration=mapping)
    with pytest.raises(ValueError, match=reason):
        image_to_body_bearing(measurement, _calibration())


def test_bearing_constructor_rejects_unknown_calibration_revision():
    provenance = replace(_provenance(), calibration_revision=None)
    with pytest.raises(ValueError, match="calibration_revision_missing"):
        CalibratedBearing(provenance, Vector3(1.0, 0.0, 0.0))


@pytest.mark.parametrize("revision", [None, "calibration-2"])
def test_current_binding_accepts_matching_optional_calibration_and_rejects_its_change(revision):
    provenance = replace(_provenance(), calibration_revision=revision)
    provenance.require_current(**{**_current(), "calibration_revision": revision})
    replacement = "calibration-2" if revision is None else None
    with pytest.raises(ValueError, match="calibration_revision_changed"):
        provenance.require_current(**{**_current(), "calibration_revision": replacement})


@pytest.mark.parametrize("updates,reason", [
    ({"source_id": "another-camera"}, "source_id_changed"),
    ({"source_epoch": "source-5"}, "source_epoch_changed"),
    ({"target_generation": 8}, "target_generation_changed"),
    ({"geometry_revision": "geometry-4"}, "geometry_revision_changed"),
    ({"calibration_revision": "calibration-3"}, "calibration_revision_changed"),
    ({"now_monotonic_s": 100.501}, "image_receipt_stale"),
    ({"now_monotonic_s": 99.999}, "image_receipt_in_future"),
    ({"max_receipt_age_s": 0.0}, "receipt_age_limit_not_positive"),
])
def test_current_binding_and_receipt_checks_reject_old_identity_without_refresh(updates, reason):
    provenance = _provenance()
    with pytest.raises(ValueError, match=reason):
        provenance.require_current(**{**_current(), **updates})
    assert provenance.capture == CaptureStamp("source-4", "frame-15", 100.0, "fresh")


@pytest.mark.parametrize("updates,reason", [
    ({"focal_length_px": (0.0, 850.0)}, "focal_length"),
    ({"focal_length_px": (-900.0, 850.0)}, "focal_length"),
    ({"focal_length_px": (float("inf"), 850.0)}, "focal_length"),
    ({"focal_length_px": [900.0, 850.0]}, "focal_length"),
    ({"principal_point_px": (float("nan"), 480.0)}, "principal_point"),
    ({"image_size_px": (0, 960)}, "image_size"),
    ({"image_size_px": (1280.0, 960)}, "image_size"),
    ({"revision": ""}, "calibration_revision_missing"),
    ({"optical_to_body": (0.5, 0.5, 0.5, 0.5)}, "calibration_rotation_invalid"),
    ({"distortion_model": "fisheye"}, "calibration_distortion_unsupported"),
])
def test_invalid_or_unsupported_calibration_is_explicit(updates, reason):
    with pytest.raises(ValueError, match=reason):
        replace(_calibration(), **updates)


@pytest.mark.parametrize("updates,reason", [
    ({"pixel_xy": (float("nan"), 480.0)}, "image_pixel"),
    ({"pixel_xy": (-1.0, 480.0)}, "image_pixel_outside_image"),
    ({"pixel_xy": (1280.0, 480.0)}, "image_pixel_outside_image"),
    ({"pixel_xy": [640.0, 480.0]}, "image_pixel_invalid"),
    ({"image_to_calibration": (1.0, 2.0, 0.0, 2.0, 4.0, 0.0)}, "image_affine_singular"),
    ({"image_to_calibration": (0.0,) * 6}, "image_affine_singular"),
    ({"image_to_calibration": (1.0, 0.0, float("inf"), 0.0, 1.0, 0.0)}, "image_affine"),
    ({"measured": "true"}, "image_measurement_validity_invalid"),
])
def test_invalid_pixel_or_affine_mapping_does_not_become_a_forward_ray(updates, reason):
    with pytest.raises(ValueError, match=reason):
        replace(_measurement(), **updates)


def test_projection_rejects_prediction_cached_capture_and_mismatched_calibration():
    measurement = _measurement()
    with pytest.raises(ValueError, match="not_measured"):
        image_to_body_bearing(replace(measurement, measured=False), _calibration())
    cached = replace(measurement.provenance, capture=replace(measurement.provenance.capture, state="cached"))
    with pytest.raises(ValueError, match="not_fresh"):
        image_to_body_bearing(replace(measurement, provenance=cached), _calibration())
    for updates, reason in (({"source_id": "another-camera"}, "source_mismatch"),
                            ({"revision": "calibration-3"}, "revision_changed")):
        with pytest.raises(ValueError, match=reason):
            image_to_body_bearing(measurement, replace(_calibration(), **updates))
    translated = replace(measurement, image_to_calibration=(1.0, 0.0, 1280.0, 0.0, 1.0, 0.0))
    with pytest.raises(ValueError, match="calibration_pixel_outside_image"):
        image_to_body_bearing(translated, _calibration())


@pytest.mark.parametrize("capture", [
    CaptureStamp(), CaptureStamp("source-4", "", 100.0, "fresh"),
    CaptureStamp("source-4", "frame-15", None, "fresh"),
    CaptureStamp("source-4", "frame-15", float("nan"), "fresh"),
])
def test_missing_sample_identity_or_receipt_is_not_invented(capture):
    with pytest.raises(ValueError):
        replace(_provenance(), capture=capture)


@pytest.mark.parametrize("direction", [Vector3(0.0, 0.0, 0.0), Vector3(2.0, 0.0, 0.0)])
def test_bearing_constructor_requires_a_unit_direction(direction):
    with pytest.raises(ValueError, match="bearing_not_unit"):
        CalibratedBearing(_provenance(), direction)
