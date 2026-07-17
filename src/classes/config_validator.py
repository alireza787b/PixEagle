# src/classes/config_validator.py
"""
Startup Validation for Safety-Critical Config Sections
========================================================

Validates and normalizes safety-critical config sections using Pydantic at
application startup. All other parameters are validated by ConfigService.

Design decisions:
- ``validate_safety_config`` remains a boolean compatibility helper.
- ``normalize_safety_config`` is the production publication gate. It raises on
  invalid input and returns a defensive copy containing validated Python values.
- Global limits are complete and follower overrides are sparse, but a supplied
  safety value may never be null, coercive, non-finite, or unknown.

Usage:
    from classes.config_validator import validate_safety_config
    validate_safety_config(Parameters._raw_config)
"""

from __future__ import annotations

import copy
import logging
from typing import Annotated, Any, Dict, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    model_validator,
)

from classes.follower_types import FollowerType
from classes.safety_types import is_target_loss_override_compatible

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models — only safety-critical fields
# ---------------------------------------------------------------------------

VelocityLimit = Annotated[
    float,
    Field(strict=True, gt=0, le=30.0, allow_inf_nan=False),
]
RateLimit = Annotated[
    float,
    Field(strict=True, gt=0, le=360.0, allow_inf_nan=False),
]
MinimumAltitude = Annotated[
    float,
    Field(strict=True, ge=-10.0, le=100.0, allow_inf_nan=False),
]
MaximumAltitude = Annotated[
    float,
    Field(strict=True, gt=0, le=500.0, allow_inf_nan=False),
]
AltitudeWarningBuffer = Annotated[
    float,
    Field(strict=True, ge=0, le=100.0, allow_inf_nan=False),
]
SafetyViolationLimit = Annotated[StrictInt, Field(gt=0, le=1000)]
TargetLossPolicy = Literal["hover", "orbit", "stop", "rtl", "continue"]

_MAXIMUM_ENVELOPE_FIELDS = frozenset(
    {
        "MAX_ALTITUDE",
        "MAX_VELOCITY",
        "MAX_VELOCITY_FORWARD",
        "MAX_VELOCITY_LATERAL",
        "MAX_VELOCITY_VERTICAL",
        "MAX_YAW_RATE",
        "MAX_PITCH_RATE",
        "MAX_ROLL_RATE",
        "MAX_SAFETY_VIOLATIONS",
    }
)
_MINIMUM_ENVELOPE_FIELDS = frozenset(
    {"MIN_ALTITUDE", "ALTITUDE_WARNING_BUFFER"}
)
_PROTECTION_ENABLE_FIELDS = frozenset(
    {
        "ALTITUDE_SAFETY_ENABLED",
        "EMERGENCY_STOP_ENABLED",
        "RTL_ON_VIOLATION",
    }
)
_CANONICAL_FOLLOWER_NAMES = frozenset(
    follower.value.upper() for follower in FollowerType
)


class GlobalLimitsModel(BaseModel):
    """Complete canonical ``Safety.GlobalLimits`` contract."""

    MIN_ALTITUDE: MinimumAltitude
    MAX_ALTITUDE: MaximumAltitude
    ALTITUDE_WARNING_BUFFER: AltitudeWarningBuffer
    ALTITUDE_SAFETY_ENABLED: StrictBool
    MAX_VELOCITY: VelocityLimit
    MAX_VELOCITY_FORWARD: VelocityLimit
    MAX_VELOCITY_LATERAL: VelocityLimit
    MAX_VELOCITY_VERTICAL: VelocityLimit
    MAX_YAW_RATE: RateLimit
    MAX_PITCH_RATE: RateLimit
    MAX_ROLL_RATE: RateLimit
    EMERGENCY_STOP_ENABLED: StrictBool
    RTL_ON_VIOLATION: StrictBool
    TARGET_LOSS_ACTION: TargetLossPolicy
    MAX_SAFETY_VIOLATIONS: SafetyViolationLimit

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_altitude_envelope(self) -> "GlobalLimitsModel":
        """Reject contradictory altitude limits before publication."""
        if self.MIN_ALTITUDE >= self.MAX_ALTITUDE:
            raise ValueError("MIN_ALTITUDE must be lower than MAX_ALTITUDE")
        if self.ALTITUDE_WARNING_BUFFER >= (
            self.MAX_ALTITUDE - self.MIN_ALTITUDE
        ):
            raise ValueError(
                "ALTITUDE_WARNING_BUFFER must be smaller than the altitude envelope"
            )
        return self


class SafetyLimitOverrideModel(BaseModel):
    """Sparse per-follower override with non-null canonical values."""

    MIN_ALTITUDE: Optional[MinimumAltitude] = None
    MAX_ALTITUDE: Optional[MaximumAltitude] = None
    ALTITUDE_WARNING_BUFFER: Optional[AltitudeWarningBuffer] = None
    ALTITUDE_SAFETY_ENABLED: Optional[StrictBool] = None
    MAX_VELOCITY: Optional[VelocityLimit] = None
    MAX_VELOCITY_FORWARD: Optional[VelocityLimit] = None
    MAX_VELOCITY_LATERAL: Optional[VelocityLimit] = None
    MAX_VELOCITY_VERTICAL: Optional[VelocityLimit] = None
    MAX_YAW_RATE: Optional[RateLimit] = None
    MAX_PITCH_RATE: Optional[RateLimit] = None
    MAX_ROLL_RATE: Optional[RateLimit] = None
    EMERGENCY_STOP_ENABLED: Optional[StrictBool] = None
    RTL_ON_VIOLATION: Optional[StrictBool] = None
    TARGET_LOSS_ACTION: Optional[TargetLossPolicy] = None
    MAX_SAFETY_VIOLATIONS: Optional[SafetyViolationLimit] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, value: Any) -> Any:
        """Distinguish an omitted override from a dangerous null override."""
        if isinstance(value, dict):
            null_fields = sorted(key for key, item in value.items() if item is None)
            if null_fields:
                raise ValueError(
                    "Safety override values may not be null: "
                    + ", ".join(null_fields)
                )
        return value


class SafetySectionModel(BaseModel):
    """Validated hard global envelope and sparse, tightening overrides."""

    GlobalLimits: GlobalLimitsModel
    FollowerOverrides: Dict[str, SafetyLimitOverrideModel] = Field(
        default_factory=dict
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_effective_follower_envelopes(self) -> "SafetySectionModel":
        """Reject unknown profiles and overrides that weaken the global envelope."""
        global_values = self.GlobalLimits.model_dump(mode="python")
        for follower_name, override in self.FollowerOverrides.items():
            if follower_name not in _CANONICAL_FOLLOWER_NAMES:
                raise ValueError(
                    f"FollowerOverrides.{follower_name} is not a canonical follower profile"
                )
            override_values = override.model_dump(exclude_none=True, mode="python")
            weakening_fields = []
            for field_name, override_value in override_values.items():
                global_value = global_values[field_name]
                weakens = (
                    field_name in _MAXIMUM_ENVELOPE_FIELDS
                    and override_value > global_value
                ) or (
                    field_name in _MINIMUM_ENVELOPE_FIELDS
                    and override_value < global_value
                ) or (
                    field_name in _PROTECTION_ENABLE_FIELDS
                    and global_value is True
                    and override_value is False
                ) or (
                    field_name == "TARGET_LOSS_ACTION"
                    and not is_target_loss_override_compatible(
                        follower_name,
                        global_value,
                        override_value,
                    )
                )
                if weakens:
                    weakening_fields.append(
                        f"{field_name}={override_value!r} (global {global_value!r})"
                    )
            if weakening_fields:
                raise ValueError(
                    f"FollowerOverrides.{follower_name} weakens the hard global "
                    "safety envelope: " + ", ".join(weakening_fields)
                )

            effective = dict(global_values)
            effective.update(override_values)
            try:
                GlobalLimitsModel.model_validate(effective)
            except ValidationError as exc:
                raise ValueError(
                    f"FollowerOverrides.{follower_name} creates invalid effective limits: "
                    f"{_format_validation_errors(exc).strip()}"
                ) from exc
        return self


class VideoSourceModel(BaseModel):
    """Validates VideoSource section for sane sensor bounds.

    Field names match config_default.yaml VideoSource exactly.
    """
    VIDEO_SOURCE_TYPE: Optional[str] = None   # e.g. 'VIDEO_FILE', 'USB', 'RTSP'
    VIDEO_FILE_EOF_POLICY: Optional[Literal["LOOP", "STOP"]] = None
    CAPTURE_FPS: Optional[float] = Field(None, gt=0, le=240.0,
        description="Target capture frame rate (fps).")
    DEFAULT_FPS: Optional[float] = Field(None, gt=0, le=240.0)
    CAPTURE_WIDTH: Optional[int] = Field(None, gt=0, le=7680,
        description="Capture width in pixels.")
    CAPTURE_HEIGHT: Optional[int] = Field(None, gt=0, le=4320,
        description="Capture height in pixels.")

    model_config = ConfigDict(extra="allow")


def normalize_safety_config(
    config: Dict[str, Any],
    *,
    require_safety: bool = False,
) -> Dict[str, Any]:
    """Return a copy with validated, normalized safety values.

    ``require_safety`` is used by production runtime publication. The boolean
    compatibility validator keeps missing sections non-fatal for isolated
    tooling that is not publishing flight-adjacent state.
    """
    if not isinstance(config, dict):
        raise TypeError("Configuration root must be a mapping")

    normalized = copy.deepcopy(config)
    safety_raw = normalized.get("Safety")
    if safety_raw is None:
        if require_safety:
            raise ValueError("Safety section is required")
        return normalized
    if not isinstance(safety_raw, dict):
        raise TypeError("Safety section must be a mapping")

    validated = SafetySectionModel.model_validate(safety_raw)
    normalized["Safety"] = validated.model_dump(
        mode="python",
        exclude_none=True,
    )
    return normalized


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_safety_config(config: dict) -> bool:
    """
    Validate safety-critical config sections at application startup.

    Validates:
    - Safety.GlobalLimits: velocity, yaw rate, altitude and distance bounds
    - VideoSource: sensor resolution and frame rate sanity

    Returns:
        True if all validated sections pass.
        False if any section fails (errors are logged, startup is NOT aborted).

    Args:
        config: The full loaded config dict (e.g., Parameters._raw_config).
    """
    ok = True

    # --- Safety.GlobalLimits and follower overrides ---
    safety_raw = config.get('Safety')
    if safety_raw and isinstance(safety_raw, dict):
        try:
            normalize_safety_config(config)
            logger.debug("Safety config validation passed.")
        except ValidationError as e:
            logger.warning(
                "Safety config validation failed — check values before flight:\n%s",
                _format_validation_errors(e)
            )
            ok = False
        except Exception as e:
            logger.warning("Safety config validation error: %s", e)
            ok = False
    else:
        logger.debug("Safety section not present in config — skipping validation.")

    # --- VideoSource ---
    vs_raw = config.get('VideoSource')
    if vs_raw and isinstance(vs_raw, dict):
        try:
            VideoSourceModel(**vs_raw)
            logger.debug("VideoSource config validation passed.")
        except ValidationError as e:
            logger.warning(
                "VideoSource config validation failed:\n%s",
                _format_validation_errors(e)
            )
            ok = False
        except Exception as e:
            logger.warning("VideoSource config validation error: %s", e)
            ok = False

    return ok


def _format_validation_errors(exc: ValidationError) -> str:
    """Format Pydantic ValidationError for readable log output."""
    lines = []
    for err in exc.errors():
        loc = ' → '.join(str(x) for x in err['loc'])
        lines.append(f"  {loc}: {err['msg']} (got {err.get('input', '?')!r})")
    return '\n'.join(lines)
