"""Software attitude lookahead for body-rate commands; not a motor-stop guarantee."""

import math

from classes.command_safety import CommandValidationError, coerce_finite_command_value


def guard_body_rates(
    fields, *, roll_deg, pitch_deg, max_roll_deg, max_pitch_deg, horizon_s
):
    """Scale all body rates together against coupled Euler-angle travel bounds.

    The derivatives describe commanded kinematics, not measured angular velocity
    or aircraft inertia. Publication must recheck fresh attitude independently.
    """
    roll = coerce_finite_command_value("roll_deg", roll_deg)
    pitch = coerce_finite_command_value("pitch_deg", pitch_deg)
    roll_limit = coerce_finite_command_value("max_roll_deg", max_roll_deg)
    pitch_limit = coerce_finite_command_value("max_pitch_deg", max_pitch_deg)
    horizon = coerce_finite_command_value("horizon_s", horizon_s)
    if not 0 < roll_limit < 180 or not 0 < pitch_limit < 90 or horizon <= 0:
        raise CommandValidationError("attitude_envelope_invalid_limits")
    if abs(roll) > roll_limit or abs(pitch) > pitch_limit:
        raise CommandValidationError("attitude_envelope_exceeded")
    result = {
        name: coerce_finite_command_value(name, value) for name, value in fields.items()
    }
    phi, theta = math.radians(roll), math.radians(pitch)
    p, q, r = (
        result[name]
        for name in ("rollspeed_deg_s", "pitchspeed_deg_s", "yawspeed_deg_s")
    )
    pitch_rate = q * math.cos(phi) - r * math.sin(phi)
    roll_rate = p + math.tan(theta) * (q * math.sin(phi) + r * math.cos(phi))
    scale = 1.0
    for angle, rate, limit in (
        (roll, roll_rate, roll_limit),
        (pitch, pitch_rate, pitch_limit),
    ):
        if rate > 0:
            scale = min(scale, (limit - angle) / (rate * horizon))
        elif rate < 0:
            scale = min(scale, (-limit - angle) / (rate * horizon))
    scale = max(0.0, min(1.0, scale))
    for name in ("rollspeed_deg_s", "pitchspeed_deg_s", "yawspeed_deg_s"):
        result[name] *= scale
    return result, {
        "scale": scale,
        "horizon_s": horizon,
        "roll_deg": roll,
        "pitch_deg": pitch,
        "euler_roll_rate_deg_s": roll_rate * scale,
        "euler_pitch_rate_deg_s": pitch_rate * scale,
        "effective_fields": dict(result),
    }
