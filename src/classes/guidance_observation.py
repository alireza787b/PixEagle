"""Immutable image/bearing values; geometry does not grant flight authority.

CaptureStamp and gimbal observations retain backend receipt, not exposure.
These contracts do not establish timing, attitude alignment or live readiness.
"""

from dataclasses import dataclass, field
import math

from classes.aircraft_state import Quaternion, Vector3, finite_number
from classes.frame_publisher import CaptureStamp
from classes.capture_timing import SourceSampleStamp
from classes.gimbal_types import GimbalAngleObservation


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


def _image_affine(value) -> None:
    if value is None:
        return
    _finite_tuple(value, 6, "image_affine")
    a, b, _, c, d, _ = value
    scale = max(abs(a), abs(b), abs(c), abs(d))
    if scale == 0 or math.isclose((a / scale) * (d / scale) - (b / scale) * (c / scale), 0.0, abs_tol=1e-12):
        raise ValueError("image_affine_singular")


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
        _image_affine(self.image_to_calibration)
        if type(self.measured) is not bool:
            raise ValueError("image_measurement_validity_invalid")

    @classmethod
    def from_dict(cls, payload: dict) -> "ImageMeasurement":
        """Decode serialized values without refreshing identity or receipt time."""
        try:
            values = dict(payload)
            provenance = dict(values.pop("provenance"))
            if provenance.pop("time_basis") != "backend_receipt":
                raise ValueError("image_time_basis_invalid")
            capture = dict(provenance["capture"])
            if capture.get("source_sample") is not None:
                capture["source_sample"] = SourceSampleStamp(**capture["source_sample"])
            provenance["capture"] = CaptureStamp(**capture)
            values["provenance"] = ObservationProvenance(**provenance)
            for name in ("pixel_xy", "image_size_px", "image_to_calibration"):
                if values[name] is not None:
                    values[name] = tuple(values[name])
            return cls(**values)
        except (KeyError, TypeError) as error:
            raise ValueError("image_measurement_contract_invalid") from error


@dataclass(frozen=True)
class ImageFrameContext:
    """Capture/geometry/target binding frozen before tracker processing."""

    provenance: ObservationProvenance
    image_size_px: tuple[int, int]
    image_to_calibration: tuple[float, float, float, float, float, float] | None = None

    def __post_init__(self):
        if not isinstance(self.provenance, ObservationProvenance):
            raise ValueError("observation_provenance_invalid")
        _image_size(self.image_size_px)
        _image_affine(self.image_to_calibration)

    def at_pixel(self, pixel_xy: tuple[float, float]) -> ImageMeasurement:
        """Preserve the mapping frozen before inference; never derive it on reads."""
        return ImageMeasurement(self.provenance, pixel_xy, self.image_size_px, self.image_to_calibration, True)


def image_measurement_for_output(
    measurement: ImageMeasurement | None, *, measured: bool,
    source_epoch: str | None, target_generation: int | None,
) -> ImageMeasurement | None:
    """Expose a committed sample only for its still-current source and target."""
    if (not measured or not isinstance(measurement, ImageMeasurement)
            or measurement.provenance.capture.source_epoch != source_epoch
            or measurement.provenance.target_generation != target_generation):
        return None
    return measurement


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
    """Unit direction under an explicit camera mapping, in physical-body FRD.

This is a bearing without range. A camera lever arm cannot translate its ray
to an aircraft-origin target position without additional real range evidence.
Image bearings retain optical calibration; gimbal bearings retain their typed
provider/mount observation without manufacturing an image calibration.
"""

    provenance: ObservationProvenance | GimbalAngleObservation
    direction_body_frd: Vector3
    frame: str = field(default="physical_body_frd", init=False)

    def __post_init__(self):
        if isinstance(self.provenance, ObservationProvenance):
            _identity(self.provenance.calibration_revision, "calibration_revision")
        elif isinstance(self.provenance, GimbalAngleObservation):
            if self.provenance.source is None or self.provenance.target_generation is None:
                raise ValueError("gimbal_bearing_ownership_unavailable")
        else:
            raise ValueError("observation_provenance_invalid")
        if (not isinstance(self.direction_body_frd, Vector3)
                or not math.isclose(self.direction_body_frd.magnitude, 1.0, rel_tol=0.0, abs_tol=1e-9)):
            raise ValueError("bearing_not_unit")


@dataclass(frozen=True)
class BearingReceipt:
    """Read-only projection of existing provenance for one alignment algorithm.

    This value does not create an image, sample, clock mapping or freshness. A
    gimbal sequence remains a received angle packet, never a camera exposure.
    """

    source_id: str
    source_epoch: str | int
    geometry_revision: str
    calibration_revision: str | None
    target_generation: int
    sample_id: str | int
    received_at_monotonic_s: float
    state: str
    provider_id: str | None = None


def bearing_receipt(provenance: ObservationProvenance | GimbalAngleObservation) -> BearingReceipt:
    if isinstance(provenance, ObservationProvenance):
        return BearingReceipt(provenance.source_id, provenance.capture.source_epoch,
            provenance.geometry_revision, provenance.calibration_revision, provenance.target_generation,
            provenance.capture.capture_id, provenance.capture.captured_at, provenance.capture.state)
    if (isinstance(provenance, GimbalAngleObservation) and provenance.source is not None
            and provenance.target_generation is not None):
        return BearingReceipt(provenance.source.camera_id, provenance.source.source_generation,
            provenance.geometry_revision, None, provenance.target_generation,
            provenance.angle_receipt_sequence, provenance.angle_received_at_monotonic_s, "fresh", provenance.provider_id)
    raise ValueError("bearing_provenance_unavailable")
