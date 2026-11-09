"""Immutable image/bearing values; geometry does not grant flight authority.

CaptureStamp records backend receipt, not exposure. These dormant contracts do
not establish sensor timing, attitude alignment, tracker lock or live readiness.
"""

from dataclasses import dataclass, field
import math

from classes.aircraft_state import Quaternion, Vector3, finite_number
from classes.frame_publisher import CaptureStamp


def _identity(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}_missing")


def _generation(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("target_generation_invalid")


def _finite_tuple(value: tuple, length: int, name: str) -> None:
    if not isinstance(value, tuple) or len(value) != length:
        raise ValueError(f"{name}_invalid")
    for component in value:
        finite_number(component, name)


def _image_size(value: tuple[int, int]) -> None:
    if (not isinstance(value, tuple) or len(value) != 2
            or any(type(dimension) is not int or dimension <= 0 for dimension in value)):
        raise ValueError("image_size_invalid")


@dataclass(frozen=True)
class ObservationProvenance:
    """Source/target revisions and the unchanged receipt identity of a sample."""

    source_id: str
    target_generation: int
    geometry_revision: str
    calibration_revision: str | None
    capture: CaptureStamp
    time_basis: str = field(default="backend_receipt", init=False)

    def __post_init__(self):
        for name in ("source_id", "geometry_revision"):
            _identity(getattr(self, name), name)
        if self.calibration_revision is not None:
            _identity(self.calibration_revision, "calibration_revision")
        _generation(self.target_generation)
        if not isinstance(self.capture, CaptureStamp):
            raise ValueError("capture_stamp_invalid")
        _identity(self.capture.source_epoch, "source_epoch")
        _identity(self.capture.capture_id, "capture_id")
        if finite_number(self.capture.captured_at, "receipt_time") < 0:
            raise ValueError("receipt_time_invalid")
        if self.capture.state not in {"fresh", "cached", "unavailable", "unknown"}:
            raise ValueError("capture_state_invalid")

    def require_current(
        self, *, source_id: str, source_epoch: str, target_generation: int,
        geometry_revision: str, calibration_revision: str | None,
        now_monotonic_s: float, max_receipt_age_s: float,
    ) -> None:
        """Check binding and receipt age only; this does not qualify sample timing."""
        _generation(target_generation)
        expected = {
            "source_id": source_id, "source_epoch": source_epoch,
            "geometry_revision": geometry_revision,
        }
        for name, value in expected.items():
            _identity(value, name)
            actual = self.capture.source_epoch if name == "source_epoch" else getattr(self, name)
            if actual != value:
                raise ValueError(f"{name}_changed")
        if calibration_revision is not None:
            _identity(calibration_revision, "calibration_revision")
        if self.calibration_revision != calibration_revision:
            raise ValueError("calibration_revision_changed")
        if self.target_generation != target_generation:
            raise ValueError("target_generation_changed")
        if self.capture.state != "fresh":
            raise ValueError("image_receipt_not_fresh")
        now = finite_number(now_monotonic_s, "observation_clock")
        limit = finite_number(max_receipt_age_s, "receipt_age_limit")
        if limit <= 0:
            raise ValueError("receipt_age_limit_not_positive")
        age = now - self.capture.captured_at
        if age < 0:
            raise ValueError("image_receipt_in_future")
        if age > limit:
            raise ValueError("image_receipt_stale")


@dataclass(frozen=True)
class ImageMeasurement:
    """A measured analysis pixel and its explicit inverse affine image mapping.

Pixel centres use right/down coordinates in [0, width-1] × [0, height-1].
image_to_calibration is row-major (a, b, tx, c, d, ty), mapping this image
back to calibration pixels. It includes any crop/resize/rotation/mirroring;
the adapter must not infer or repeat those operations. None means that mapping
is unknown; uncalibrated pixels remain valid image measurements.
"""

    provenance: ObservationProvenance
    pixel_xy: tuple[float, float]
    image_size_px: tuple[int, int]
    image_to_calibration: tuple[float, float, float, float, float, float] | None
    measured: bool

    def __post_init__(self):
        if not isinstance(self.provenance, ObservationProvenance):
            raise ValueError("observation_provenance_invalid")
        _image_size(self.image_size_px)
        _finite_tuple(self.pixel_xy, 2, "image_pixel")
        if any(not 0 <= point <= dimension - 1 for point, dimension in zip(self.pixel_xy, self.image_size_px)):
            raise ValueError("image_pixel_outside_image")
        if self.image_to_calibration is not None:
            _finite_tuple(self.image_to_calibration, 6, "image_affine")
            a, b, _, c, d, _ = self.image_to_calibration
            scale = max(abs(a), abs(b), abs(c), abs(d))
            if scale == 0 or math.isclose((a / scale) * (d / scale) - (b / scale) * (c / scale),
                                         0.0, abs_tol=1e-12):
                raise ValueError("image_affine_singular")
        if type(self.measured) is not bool:
            raise ValueError("image_measurement_validity_invalid")


@dataclass(frozen=True)
class PinholeCalibration:
    """Explicit zero-skew, distortion-free intrinsics and installation rotation.

Optical axes are right/down/forward. optical_to_body rotates those axes into
physical aircraft FRD, independently of aircraft attitude or display offsets.
image_size_px and the intrinsics refer to the same calibration pixel grid.
"""

    source_id: str
    revision: str
    image_size_px: tuple[int, int]
    focal_length_px: tuple[float, float]
    principal_point_px: tuple[float, float]
    optical_to_body: Quaternion
    distortion_model: str

    def __post_init__(self):
        _identity(self.source_id, "calibration_source")
        _identity(self.revision, "calibration_revision")
        _image_size(self.image_size_px)
        _finite_tuple(self.focal_length_px, 2, "focal_length_px")
        _finite_tuple(self.principal_point_px, 2, "principal_point_px")
        if any(value <= 0 for value in self.focal_length_px):
            raise ValueError("calibration_focal_length_not_positive")
        if not isinstance(self.optical_to_body, Quaternion):
            raise ValueError("calibration_rotation_invalid")
        if self.distortion_model != "none":
            raise ValueError("calibration_distortion_unsupported")


@dataclass(frozen=True)
class CalibratedBearing:
    """Unit direction from the camera, expressed in physical-body FRD.

This is a bearing without range. A camera lever arm cannot translate its ray
to an aircraft-origin target position without additional real range evidence.
"""

    provenance: ObservationProvenance
    direction_body_frd: Vector3
    frame: str = field(default="physical_body_frd", init=False)

    def __post_init__(self):
        if not isinstance(self.provenance, ObservationProvenance):
            raise ValueError("observation_provenance_invalid")
        _identity(self.provenance.calibration_revision, "calibration_revision")
        if (not isinstance(self.direction_body_frd, Vector3)
                or not math.isclose(self.direction_body_frd.magnitude, 1.0, rel_tol=0.0, abs_tol=1e-9)):
            raise ValueError("bearing_not_unit")
