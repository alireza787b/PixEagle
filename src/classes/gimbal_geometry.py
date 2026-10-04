"""Shared validation boundary for camera-body angle observations.

Physical mount transforms are added only after their provider conventions are
measured. This module does not reinterpret the raw yaw, pitch or roll channels.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Mapping


class InvalidGimbalGeometry(ValueError):
    """An angle observation cannot safely produce aircraft command intent."""


@dataclass(frozen=True)
class AngleGeometry:
    azimuth_axis: str
    azimuth_sign: int
    azimuth_zero_deg: float
    depression_axis: str
    depression_sign: int
    depression_zero_deg: float


_TOPOTEK_PRESETS = {
    "HORIZONTAL": AngleGeometry("YAW", 1, 0.0, "PITCH", 1, 0.0),
    "VERTICAL": AngleGeometry("ROLL", -1, 0.0, "PITCH", 1, 90.0),
}


def migrate_legacy_geometry(config: Mapping) -> dict:
    """Move an unambiguous old mount choice before retiring follower-local keys.

    Corrections are not guessed: an old non-neutral value requires the operator
    to set the camera-level expert mapping explicitly.
    """
    candidate = copy.deepcopy(dict(config))
    chase = candidate.get("GM_VELOCITY_CHASE", {})
    vector = candidate.get("GM_VELOCITY_VECTOR", {})
    camera = candidate.get("GimbalTracker", {})
    tracking = candidate.get("Tracking", {})
    follower = candidate.get("Follower", {})
    local_profile = (
        isinstance(tracking, Mapping)
        and isinstance(follower, Mapping)
        and tracking.get("DEFAULT_TRACKING_ALGORITHM") not in (None, "Gimbal")
        and follower.get("FOLLOWER_MODE") not in (
            None, "gm_velocity_chase", "gm_velocity_vector"
        )
    )
    for name, section in (("GM_VELOCITY_CHASE", chase), ("GM_VELOCITY_VECTOR", vector)):
        if isinstance(section, Mapping):
            checked = section
            if (local_profile and name == "GM_VELOCITY_CHASE"
                    and section.get("INVERT_VERTICAL_CONTROL") is True):
                checked = dict(section)
                checked["INVERT_VERTICAL_CONTROL"] = False
            require_canonical_geometry_settings(name, checked)
    if not all(isinstance(section, Mapping) for section in (chase, vector, camera)):
        return candidate
    mount = resolve_mount_type(camera, chase, vector, allowed=("HORIZONTAL", "VERTICAL"))
    if "MOUNT_TYPE" not in camera and any(
        "MOUNT_TYPE" in section for section in (chase, vector)
    ):
        candidate.setdefault("GimbalTracker", {})["MOUNT_TYPE"] = mount
    return candidate


def resolve_angle_geometry(camera_config: Mapping, mount_type: str) -> AngleGeometry:
    """Resolve a provider/mount preset and optional expert corrections once."""
    provider = str(camera_config.get("PROVIDER", "topotek_sip_udp")).strip().lower()
    if provider not in ("topotek_sip_udp", "sip_udp", "topotek", "topotek_sip"):
        raise InvalidGimbalGeometry(f"No angle geometry preset for provider {provider!r}")
    preset = _TOPOTEK_PRESETS.get(mount_type)
    if preset is None:
        raise InvalidGimbalGeometry(f"Unsupported gimbal MOUNT_TYPE: {mount_type!r}")
    override = camera_config.get("GEOMETRY_OVERRIDE", {})
    if not isinstance(override, Mapping):
        raise InvalidGimbalGeometry("GimbalTracker.GEOMETRY_OVERRIDE must be an object")

    def axis(name: str, default: str) -> str:
        value = override.get(name, "AUTO")
        if value == "AUTO":
            return default
        if value not in ("YAW", "PITCH", "ROLL"):
            raise InvalidGimbalGeometry(f"Invalid {name}: {value!r}")
        return value

    def sign(name: str, default: int) -> int:
        value = override.get(name, "AUTO")
        if value == "AUTO":
            return default
        if value not in ("POSITIVE", "NEGATIVE"):
            raise InvalidGimbalGeometry(f"Invalid {name}: {value!r}")
        return 1 if value == "POSITIVE" else -1

    def zero_adjust(name: str) -> float:
        value = override.get(name, 0.0)
        if isinstance(value, (str, bytes, bool)):
            raise InvalidGimbalGeometry(f"Invalid {name}: {value!r}")
        try:
            correction = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise InvalidGimbalGeometry(f"Invalid {name}: {value!r}") from exc
        if not math.isfinite(correction) or abs(correction) > 180.0:
            raise InvalidGimbalGeometry(f"Invalid {name}: {value!r}")
        return correction

    resolved = AngleGeometry(
        azimuth_axis=axis("AZIMUTH_AXIS", preset.azimuth_axis),
        azimuth_sign=sign("AZIMUTH_SIGN", preset.azimuth_sign),
        azimuth_zero_deg=preset.azimuth_zero_deg + zero_adjust("AZIMUTH_ZERO_ADJUST_DEG"),
        depression_axis=axis("DEPRESSION_AXIS", preset.depression_axis),
        depression_sign=sign("DEPRESSION_SIGN", preset.depression_sign),
        depression_zero_deg=preset.depression_zero_deg + zero_adjust("DEPRESSION_ZERO_ADJUST_DEG"),
    )
    if resolved.azimuth_axis == resolved.depression_axis:
        raise InvalidGimbalGeometry("Azimuth and depression cannot use the same camera angle channel")
    return resolved


def resolve_mount_type(camera_config, chase_config, vector_config, *, allowed: tuple[str, ...]) -> str:
    """Resolve the camera's single installation choice with legacy safeguards."""
    camera_config = camera_config or {}
    chase_config = chase_config or {}
    vector_config = vector_config or {}
    canonical = camera_config.get("MOUNT_TYPE")
    if "MOUNT_TYPE" in camera_config and canonical is None:
        raise InvalidGimbalGeometry("GimbalTracker.MOUNT_TYPE cannot be null")
    legacy = [
        config["MOUNT_TYPE"] for config in (chase_config, vector_config)
        if "MOUNT_TYPE" in config
    ]
    if any(value is None for value in legacy):
        raise InvalidGimbalGeometry("Legacy gimbal MOUNT_TYPE cannot be null")
    if canonical is None:
        if len(set(legacy)) > 1:
            raise InvalidGimbalGeometry("Conflicting legacy gimbal MOUNT_TYPE values require correction")
        canonical = legacy[0] if legacy else "HORIZONTAL"
    elif any(value not in ("HORIZONTAL", canonical) for value in legacy):
        raise InvalidGimbalGeometry("Legacy gimbal MOUNT_TYPE conflicts with GimbalTracker.MOUNT_TYPE")
    if canonical not in allowed:
        raise InvalidGimbalGeometry(f"Unsupported gimbal MOUNT_TYPE: {canonical!r}")
    return canonical


def require_canonical_geometry_settings(follower_name: str, config: Mapping) -> None:
    """Reject retired per-follower direction corrections before command use."""
    if follower_name == "GM_VELOCITY_CHASE":
        legacy_values = {
            "ROLL_RIGHT_SIGN": "NEGATIVE",
            "NEUTRAL_PITCH_ANGLE": 0.0,
            "INVERT_LATERAL_CONTROL": False,
            "INVERT_VERTICAL_CONTROL": False,
        }
    elif follower_name == "GM_VELOCITY_VECTOR":
        legacy_values = {
            "MOUNT_ROLL_OFFSET_DEG": 0.0,
            "MOUNT_PITCH_OFFSET_DEG": 0.0,
            "MOUNT_YAW_OFFSET_DEG": 0.0,
            "INVERT_GIMBAL_ROLL": False,
            "INVERT_GIMBAL_PITCH": False,
            "INVERT_GIMBAL_YAW": False,
        }
    else:
        raise InvalidGimbalGeometry(f"Unknown gimbal follower {follower_name!r}")
    conflicting = [
        name for name, neutral in legacy_values.items()
        if name in config and config[name] != neutral
    ]
    if conflicting:
        raise InvalidGimbalGeometry(
            f"{follower_name} legacy geometry settings conflict with "
            f"GimbalTracker.GEOMETRY_OVERRIDE: {', '.join(conflicting)}. "
            "Move the correction to the camera setting before following."
        )


def require_finite_body_angles(angular) -> tuple[float, float, float]:
    try:
        first_three = tuple(angular[:3])
    except (TypeError, ValueError) as exc:
        raise InvalidGimbalGeometry("Camera-body yaw, pitch and roll are required") from exc
    if len(first_three) < 3:
        raise InvalidGimbalGeometry("Camera-body yaw, pitch and roll are required")
    values = []
    for value in first_three:
        if isinstance(value, (str, bytes, bool)):
            raise InvalidGimbalGeometry("Camera-body angles must be numeric")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise InvalidGimbalGeometry("Camera-body angles must be numeric") from exc
        if not math.isfinite(number):
            raise InvalidGimbalGeometry("Camera-body angles must be finite")
        values.append(number)
    return tuple(values)


def body_line_of_sight(
    angular, mount_type: str, geometry: AngleGeometry | None = None
) -> tuple[float, float, float]:
    """Return a unit target ray in aircraft forward/right/down coordinates.

    The vertical Topotek convention follows the observed base-pitched-up-90°
    installation: pitch 90° and roll 0° look forward; positive raw roll pans
    left and decreasing raw pitch elevates the lens. Raw yaw rotates the image
    about the optical axis and does not steer the ray. Horizontal and tilted
    conventions preserve the vector follower's previous yaw/pitch meaning;
    their physical installations still require separate qualification.
    """
    yaw_deg, pitch_deg, roll_deg = require_finite_body_angles(angular)
    mapping = geometry or resolve_angle_geometry({}, mount_type)
    channels = {"YAW": yaw_deg, "PITCH": pitch_deg, "ROLL": roll_deg}
    azimuth_deg = mapping.azimuth_sign * (channels[mapping.azimuth_axis] - mapping.azimuth_zero_deg)
    depression_deg = mapping.depression_sign * (
        channels[mapping.depression_axis] - mapping.depression_zero_deg
    )

    azimuth = math.radians(azimuth_deg)
    depression = math.radians(depression_deg)
    horizontal = math.cos(depression)
    ray = (
        horizontal * math.cos(azimuth),
        horizontal * math.sin(azimuth),
        math.sin(depression),
    )
    if not all(math.isfinite(value) for value in ray):
        raise InvalidGimbalGeometry("Camera line of sight is not finite")
    return ray
