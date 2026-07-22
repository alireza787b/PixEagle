"""Shared command validation for follower setpoints and PX4 command dispatch."""

import logging
import math
from typing import Any, Dict, Optional

from classes.safety_types import FIELD_LIMIT_MAPPING

logger = logging.getLogger(__name__)

SCHEMA_FIELD_LIMITS = {
    "thrust": (0.0, 1.0),
}


class CommandValidationError(ValueError):
    """Raised when a command cannot be proven safe to publish."""


def normalize_follower_name(follower_name: Optional[str]) -> Optional[str]:
    """Normalize profile/follower names for SafetyManager lookup."""
    if not follower_name:
        return None
    return str(follower_name).strip().lower().replace(" ", "_").upper()


def coerce_finite_command_value(field_name: str, value: Any) -> float:
    """Convert a command value to float and reject NaN/Inf."""
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise CommandValidationError(
            f"{field_name} must be numeric, got {type(value).__name__}"
        ) from exc

    if not math.isfinite(numeric_value):
        raise CommandValidationError(f"{field_name} must be finite, got {value!r}")

    return numeric_value


def _get_effective_limit(limit_name: str, follower_name: Optional[str]) -> Optional[float]:
    from classes.parameters import Parameters

    raw_limit = Parameters.get_effective_limit(limit_name, follower_name)
    if raw_limit is None:
        return None

    try:
        limit = float(raw_limit)
    except (TypeError, ValueError) as exc:
        raise CommandValidationError(
            f"Safety limit {limit_name} is not numeric: {raw_limit!r}"
        ) from exc

    if not math.isfinite(limit):
        raise CommandValidationError(f"Safety limit {limit_name} is not finite: {raw_limit!r}")
    if limit < 0.0:
        raise CommandValidationError(f"Safety limit {limit_name} must be non-negative: {limit}")

    return limit


def _clamp(
    command_type: str,
    field_name: str,
    value: float,
    min_value: float,
    max_value: float,
    *,
    clamp: bool,
) -> float:
    clamped = max(min_value, min(max_value, value))
    if clamped == value:
        return value

    if not clamp:
        raise CommandValidationError(
            f"{command_type}.{field_name}={value} outside [{min_value}, {max_value}]"
        )

    logger.warning(
        "%s command field %s clamped from %.3f to %.3f",
        command_type,
        field_name,
        value,
        clamped,
    )
    return clamped


def validate_and_clamp_command_value(
    field_name: str,
    value: Any,
    *,
    follower_name: Optional[str] = None,
    command_type: str = "setpoint",
    clamp: bool = True,
) -> float:
    """
    Validate one command field and clamp it to the applicable safety limit.

    Safety.GlobalLimits/FollowerOverrides remain the source of truth for mapped
    flight-control fields. Schema-only fields, currently thrust, are handled
    here so the final PX4 boundary uses the same finite-value checks.
    """
    numeric_value = coerce_finite_command_value(field_name, value)

    if field_name in SCHEMA_FIELD_LIMITS:
        min_value, max_value = SCHEMA_FIELD_LIMITS[field_name]
        return _clamp(command_type, field_name, numeric_value, min_value, max_value, clamp=clamp)

    limit_name = FIELD_LIMIT_MAPPING.get(field_name)
    if not limit_name:
        return numeric_value

    normalized_follower = normalize_follower_name(follower_name)
    try:
        max_limit = _get_effective_limit(limit_name, normalized_follower)
    except Exception as exc:
        raise CommandValidationError(
            f"Safety limit lookup failed for {command_type}.{field_name} via {limit_name}: {exc}"
        ) from exc

    if max_limit is None:
        raise CommandValidationError(
            f"Safety limit {limit_name} unavailable for {command_type}.{field_name}"
        )

    return _clamp(
        command_type,
        field_name,
        numeric_value,
        -abs(max_limit),
        abs(max_limit),
        clamp=clamp,
    )


def validate_and_clamp_command_values(
    command_type: str,
    values: Dict[str, Any],
    *,
    follower_name: Optional[str] = None,
    clamp: bool = True,
) -> Dict[str, float]:
    """Validate and clamp a command dictionary through one shared path."""
    return {
        field_name: validate_and_clamp_command_value(
            field_name,
            value,
            follower_name=follower_name,
            command_type=command_type,
            clamp=clamp,
        )
        for field_name, value in values.items()
    }
