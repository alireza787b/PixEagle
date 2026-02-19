# src/classes/config_validator.py
"""
Startup Validation for Safety-Critical Config Sections
========================================================

Validates a subset of config sections using Pydantic at application startup.
Only safety-critical sections are validated here (Safety.GlobalLimits, VideoSource).
All other parameters are validated at runtime by config_service.validate_value().

Design decisions:
- Validation is NON-BLOCKING: logs a WARNING if invalid but does NOT raise or abort startup.
  Operators often run with partial configs (e.g., ground testing, no drone connected).
- Only safety-critical sections are modelled — this is NOT a full Pydantic config rewrite.
  The operator-edited YAML remains the single source of truth.
- Returns bool so callers can decide whether to escalate (e.g., refuse arming in flight code).

Usage:
    from classes.config_validator import validate_safety_config
    validate_safety_config(Parameters._raw_config)
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models — only safety-critical fields
# ---------------------------------------------------------------------------

class GlobalLimitsModel(BaseModel):
    """Validates Safety.GlobalLimits section.

    Field names match config_default.yaml Safety.GlobalLimits exactly.
    All fields are optional (config may omit some limits) — only present values are range-checked.
    """
    MAX_VELOCITY: Optional[float] = Field(None, gt=0, le=30.0,
        description="Maximum resultant velocity (m/s).")
    MAX_VELOCITY_FORWARD: Optional[float] = Field(None, gt=0, le=30.0)
    MAX_VELOCITY_LATERAL: Optional[float] = Field(None, gt=0, le=30.0)
    MAX_VELOCITY_VERTICAL: Optional[float] = Field(None, gt=0, le=30.0)
    MAX_YAW_RATE: Optional[float] = Field(None, gt=0, le=360.0,
        description="Maximum yaw rate (deg/s).")
    MAX_PITCH_RATE: Optional[float] = Field(None, gt=0, le=360.0)
    MAX_ROLL_RATE: Optional[float] = Field(None, gt=0, le=360.0)
    MAX_ALTITUDE: Optional[float] = Field(None, gt=0, le=500.0,
        description="Maximum altitude above takeoff (m).")
    MIN_ALTITUDE: Optional[float] = Field(None, ge=-10.0, le=100.0,
        description="Minimum altitude (m). Negative allowed for indoor/below-ground testing.")

    model_config = {"extra": "allow"}  # Ignore EMERGENCY_STOP_ENABLED etc.


class SafetySectionModel(BaseModel):
    """Validates the Safety section (GlobalLimits validated if present)."""
    GlobalLimits: Optional[GlobalLimitsModel] = None

    model_config = {"extra": "allow"}  # Ignore FollowerOverrides and other keys


class VideoSourceModel(BaseModel):
    """Validates VideoSource section for sane sensor bounds.

    Field names match config_default.yaml VideoSource exactly.
    """
    VIDEO_SOURCE_TYPE: Optional[str] = None   # e.g. 'VIDEO_FILE', 'USB', 'RTSP'
    CAPTURE_FPS: Optional[float] = Field(None, gt=0, le=240.0,
        description="Target capture frame rate (fps).")
    DEFAULT_FPS: Optional[float] = Field(None, gt=0, le=240.0)
    CAPTURE_WIDTH: Optional[int] = Field(None, gt=0, le=7680,
        description="Capture width in pixels.")
    CAPTURE_HEIGHT: Optional[int] = Field(None, gt=0, le=4320,
        description="Capture height in pixels.")

    model_config = {"extra": "allow"}


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

    # --- Safety.GlobalLimits ---
    safety_raw = config.get('Safety')
    if safety_raw and isinstance(safety_raw, dict):
        try:
            SafetySectionModel(**safety_raw)
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
