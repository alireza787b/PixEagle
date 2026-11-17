"""Pure fixed-camera calibration parsing and explicit decoder-grid binding.

No capture, configuration, clock, or aircraft authority is acquired here. The
caller supplies the selected source and exact image geometry for one epoch.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re

from classes.aircraft_state import Quaternion, finite_number
from classes.guidance_observation import PinholeCalibration


PIXEL_GRID = "decoder_pre_orientation"
_SIGNATURE = re.compile(r"sha256-v1:[a-f0-9]{64}")
_REVISION = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_SOURCE_TYPES = frozenset({
    "VIDEO_FILE", "USB_CAMERA", "RTSP_OPENCV", "RTSP_STREAM", "UDP_STREAM",
    "HTTP_STREAM", "CSI_CAMERA", "CUSTOM_GSTREAMER", "GAZEBO_CAMERA",
})
_CALIBRATION_KEYS = frozenset({
    "source_signature", "revision", "pixel_grid", "image_size_px",
    "focal_length_px", "principal_point_px", "optical_to_body_frd_wxyz",
    "distortion_model", "mount_kind",
})


def _digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _identity(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{name}_invalid")


def _source_signature(value: str) -> None:
    if not isinstance(value, str) or _SIGNATURE.fullmatch(value) is None:
        raise ValueError("calibration_source_signature_invalid")


def _size(value: tuple[int, int]) -> None:
    if (not isinstance(value, tuple) or len(value) != 2
            or any(type(part) is not int or part <= 0 for part in value)):
        raise ValueError("calibration_image_size_invalid")


def selected_source_signature(
    *, source_type: str, backend: str, locator: str,
    options: Mapping[str, str | int | float | bool | None],
) -> str:
    """Hash an exact effective capture selection without retaining its secrets.

    Backend-specific options describe the actual opening path, including any
    pipeline or selected mode. Equal hashes establish selected-spec identity,
    not physical camera identity or equivalence between fallback backends.
    """
    if not isinstance(source_type, str) or source_type not in _SOURCE_TYPES:
        raise ValueError("selected_source_type_invalid")
    if not isinstance(backend, str) or backend not in {"opencv", "gstreamer", "gazebo_transport"}:
        raise ValueError("selected_source_backend_invalid")
    if not isinstance(locator, str) or not locator:
        raise ValueError("selected_source_locator_invalid")
    if not isinstance(options, Mapping):
        raise ValueError("selected_source_options_invalid")
    copied_options = {}
    for name, value in options.items():
        if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9_]*", name) is None:
            raise ValueError("selected_source_option_name_invalid")
        if value is not None and type(value) not in {str, int, float, bool}:
            raise ValueError("selected_source_option_value_invalid")
        if type(value) in {int, float}:
            try:
                if not math.isfinite(value):
                    raise ValueError("selected_source_option_value_invalid")
            except OverflowError as error:
                raise ValueError("selected_source_option_value_invalid") from error
        copied_options[name] = value
    return "sha256-v1:" + _digest({
        "version": 1, "source_type": source_type, "backend": backend,
        "locator": locator, "options": copied_options,
    })


@dataclass(frozen=True)
class FixedCameraCalibration:
    """Saved measured values, bound to a selected spec rather than a stream UUID."""

    source_signature: str
    revision: str
    pixel_grid: str
    image_size_px: tuple[int, int]
    focal_length_px: tuple[float, float]
    principal_point_px: tuple[float, float]
    optical_to_body: Quaternion
    distortion_model: str
    mount_kind: str

    def __post_init__(self):
        _source_signature(self.source_signature)
        if not isinstance(self.revision, str) or _REVISION.fullmatch(self.revision) is None:
            raise ValueError("calibration_revision_invalid")
        if self.pixel_grid != PIXEL_GRID:
            raise ValueError("calibration_pixel_grid_unsupported")
        if self.mount_kind != "fixed":
            raise ValueError("calibration_mount_not_fixed")
        PinholeCalibration(
            self.source_signature, self.revision, self.image_size_px,
            self.focal_length_px, self.principal_point_px,
            self.optical_to_body, self.distortion_model,
        )

    @classmethod
    def from_mapping(cls, value: dict | None) -> "FixedCameraCalibration | None":
        """Parse an optional closed config object once, without inferred values."""
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != _CALIBRATION_KEYS:
            raise ValueError("fixed_camera_calibration_keys_invalid")
        arrays = {}
        for name, length in (("image_size_px", 2), ("focal_length_px", 2),
                             ("principal_point_px", 2), ("optical_to_body_frd_wxyz", 4)):
            parts = value[name]
            if not isinstance(parts, list) or len(parts) != length:
                raise ValueError(f"calibration_{name}_invalid")
            arrays[name] = tuple(parts)
        return cls(
            value["source_signature"], value["revision"], value["pixel_grid"],
            arrays["image_size_px"], arrays["focal_length_px"], arrays["principal_point_px"],
            Quaternion(*arrays["optical_to_body_frd_wxyz"]),
            value["distortion_model"], value["mount_kind"],
        )

    @property
    def content_revision(self) -> str:
        """Changed values invalidate bindings even if the label was not edited."""
        return f"calibration-v1:{self.revision}:{_digest(asdict(self))}"


@dataclass(frozen=True)
class ActiveImageGeometry:
    """An explicit full-frame application mapping for one active source epoch.

    Decoder dimensions describe actual delivered pixels, not original sensor
    dimensions, upstream crops, zoom stability, or optical applicability.
    """

    source_signature: str
    runtime_stream_id: str
    source_epoch: str
    oriented_decoded_size_px: tuple[int, int]
    rotation_deg: int
    flip_mode: str
    analysis_size_px: tuple[int, int]
    pixel_grid: str

    def __post_init__(self):
        _source_signature(self.source_signature)
        _identity(self.runtime_stream_id, "calibration_runtime_stream")
        _identity(self.source_epoch, "calibration_source_epoch")
        _size(self.oriented_decoded_size_px)
        _size(self.analysis_size_px)
        if type(self.rotation_deg) is not int or self.rotation_deg not in {0, 90, 180, 270}:
            raise ValueError("calibration_rotation_unsupported")
        if not isinstance(self.flip_mode, str) or self.flip_mode not in {"none", "horizontal", "vertical", "both"}:
            raise ValueError("calibration_flip_unsupported")
        if self.pixel_grid != PIXEL_GRID:
            raise ValueError("calibration_pixel_grid_unsupported")

    @property
    def decoded_size_px(self) -> tuple[int, int]:
        width, height = self.oriented_decoded_size_px
        return (height, width) if self.rotation_deg in {90, 270} else (width, height)

    @property
    def geometry_revision(self) -> str:
        return "image-geometry-v1:" + _digest({**asdict(self), "mapping": "full_frame_pixel_centres_v1"})


def _compose(left: tuple, right: tuple) -> tuple:
    a, b, tx, c, d, ty = left
    e, f, ux, g, h, uy = right
    return (a*e+b*g, a*f+b*h, a*ux+b*uy+tx,
            c*e+d*g, c*f+d*h, c*ux+d*uy+ty)


@dataclass(frozen=True)
class BoundFixedCameraCalibration:
    """Runtime calibration plus its exact source/geometry binding; no timing claim."""

    geometry: ActiveImageGeometry
    calibration: PinholeCalibration
    image_to_calibration: tuple[float, float, float, float, float, float]

    @property
    def geometry_revision(self) -> str:
        return self.geometry.geometry_revision

    @property
    def calibration_revision(self) -> str:
        return self.calibration.revision

    def require_current(self, geometry: ActiveImageGeometry) -> None:
        if not isinstance(geometry, ActiveImageGeometry):
            raise ValueError("calibration_active_geometry_invalid")
        if geometry.source_signature != self.geometry.source_signature:
            raise ValueError("calibration_source_changed")
        if geometry.runtime_stream_id != self.geometry.runtime_stream_id:
            raise ValueError("calibration_runtime_stream_changed")
        if geometry.source_epoch != self.geometry.source_epoch:
            raise ValueError("calibration_source_epoch_changed")
        if geometry.geometry_revision != self.geometry_revision:
            raise ValueError("calibration_geometry_changed")


def bind_fixed_camera_calibration(
    saved: FixedCameraCalibration | None, geometry: ActiveImageGeometry,
) -> BoundFixedCameraCalibration | None:
    """Bind only the exact measured decoder grid; never scale guessed intrinsics."""
    if saved is None:
        return None
    if not isinstance(saved, FixedCameraCalibration) or not isinstance(geometry, ActiveImageGeometry):
        raise ValueError("fixed_camera_calibration_binding_invalid")
    if saved.source_signature != geometry.source_signature:
        raise ValueError("calibration_source_mismatch")
    if saved.image_size_px != geometry.decoded_size_px:
        raise ValueError("calibration_decoder_grid_mismatch")

    width, height = geometry.oriented_decoded_size_px
    analysis_width, analysis_height = geometry.analysis_size_px
    sx, sy = width / analysis_width, height / analysis_height
    resize = (sx, 0., (sx-1.)/2., 0., sy, (sy-1.)/2.)
    flip_x = geometry.flip_mode in {"horizontal", "both"}
    flip_y = geometry.flip_mode in {"vertical", "both"}
    flip = (-1. if flip_x else 1., 0., width-1. if flip_x else 0.,
            0., -1. if flip_y else 1., height-1. if flip_y else 0.)
    decoded_width, decoded_height = geometry.decoded_size_px
    rotation = {
        0: (1., 0., 0., 0., 1., 0.),
        90: (0., 1., 0., -1., 0., decoded_height-1.),
        180: (-1., 0., decoded_width-1., 0., -1., decoded_height-1.),
        270: (0., -1., decoded_width-1., 1., 0., 0.),
    }[geometry.rotation_deg]
    affine = _compose(rotation, _compose(flip, resize))
    for component in affine:
        finite_number(component, "calibration_image_affine")
    calibration = PinholeCalibration(
        geometry.runtime_stream_id, saved.content_revision, saved.image_size_px,
        saved.focal_length_px, saved.principal_point_px,
        saved.optical_to_body, saved.distortion_model,
    )
    return BoundFixedCameraCalibration(geometry, calibration, affine)
