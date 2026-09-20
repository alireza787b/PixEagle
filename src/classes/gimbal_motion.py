"""Provider-advertised bounds for optional, finite camera movement pulses."""

SIP_MOTION_SETTINGS = {
    "min_speed_deg_s": 1, "max_speed_deg_s": 30,
    "min_duration_ms": 100, "max_duration_ms": 1000,
    "default_speed_deg_s": 10, "default_duration_ms": 250,
    "presets": [
        {"name": "fine", "label": "Fine", "speed_deg_s": 5, "duration_ms": 150},
        {"name": "normal", "label": "Normal", "speed_deg_s": 10, "duration_ms": 250},
        {"name": "fast", "label": "Fast", "speed_deg_s": 20, "duration_ms": 500},
    ],
}


def resolve_motion(settings, speed_deg_s=None, duration_ms=None):
    """Resolve defaults and reject unsupported/out-of-bounds values before IO."""
    if not settings:
        raise ValueError("This camera does not support adjustable movement")
    speed = settings["default_speed_deg_s"] if speed_deg_s is None else speed_deg_s
    duration = settings["default_duration_ms"] if duration_ms is None else duration_ms
    for value, low, high, label in (
        (speed, settings["min_speed_deg_s"], settings["max_speed_deg_s"], "Speed"),
        (duration, settings["min_duration_ms"], settings["max_duration_ms"], "Duration"),
    ):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{label} must be an integer between {low} and {high}")
    return speed, duration
