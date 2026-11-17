"""Pure calibrated pinhole projection boundary, without runtime/config ownership."""

from classes.aircraft_state import Vector3, finite_number
from classes.guidance_observation import (
    CalibratedBearing,
    ImageMeasurement,
    PinholeCalibration,
)


def image_to_body_bearing(measurement: ImageMeasurement, calibration: PinholeCalibration) -> CalibratedBearing:
    """Unproject an actual measurement; callers separately qualify age and alignment."""
    if not isinstance(measurement, ImageMeasurement) or not isinstance(calibration, PinholeCalibration):
        raise ValueError("image_bearing_contract_invalid")
    provenance = measurement.provenance
    if not measurement.measured:
        raise ValueError("image_measurement_not_measured")
    if provenance.capture.state != "fresh":
        raise ValueError("image_receipt_not_fresh")
    if provenance.calibration_revision is None:
        raise ValueError("image_calibration_unavailable")
    if measurement.image_to_calibration is None:
        raise ValueError("image_calibration_mapping_unavailable")
    if provenance.source_id != calibration.source_id:
        raise ValueError("calibration_source_mismatch")
    if provenance.calibration_revision != calibration.revision:
        raise ValueError("calibration_revision_changed")
    x, y = measurement.pixel_xy
    a, b, tx, c, d, ty = measurement.image_to_calibration
    u, v = a * x + b * y + tx, c * x + d * y + ty
    finite_number(u, "calibration_pixel")
    finite_number(v, "calibration_pixel")
    if not (0 <= u <= calibration.image_size_px[0] - 1 and 0 <= v <= calibration.image_size_px[1] - 1):
        raise ValueError("calibration_pixel_outside_image")
    fx, fy = calibration.focal_length_px
    cx, cy = calibration.principal_point_px
    optical = Vector3((u - cx) / fx, (v - cy) / fy, 1.0).normalized()
    body = calibration.optical_to_body.rotate(optical).normalized()
    return CalibratedBearing(provenance, body)
