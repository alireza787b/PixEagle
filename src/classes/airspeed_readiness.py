"""Fixed-wing speed admission with an explicit, optional ground-speed proxy."""

import math
import time
from collections.abc import Mapping


def get_follower_airspeed(controller):
    """Read a canonical, current airspeed observation or raise a hard refusal.

    Live acquisition is deliberately not implemented here. A future qualified
    telemetry owner supplies this observation without creating a follower store.
    """
    from classes.command_preview import CommandPreviewController

    if isinstance(controller, CommandPreviewController):
        observation = controller.get_airspeed_observation()
        if (observation.get("source") != "command_preview" or
                observation.get("execution_mode") != "COMMAND_PREVIEW" or
                observation.get("commands_sent_to_px4") is not False):
            raise ValueError("following_airspeed_unavailable")
        value = observation.get("airspeed_m_s")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("following_airspeed_unavailable")
        return float(value)
    getter = getattr(controller, "get_airspeed_observation", None)
    health_getter = getattr(controller, "get_telemetry_readiness", None)
    if not callable(getter) or not callable(health_getter):
        raise ValueError("following_airspeed_unavailable")
    try:
        observation, health = getter(), health_getter()
    except Exception as exc:
        raise ValueError("following_airspeed_unavailable") from exc
    if not isinstance(observation, Mapping) or not isinstance(health, Mapping):
        raise ValueError("following_airspeed_unavailable")
    value = observation.get("airspeed_m_s")
    received = observation.get("observed_at_monotonic_s")
    deadline = health.get("stale_timeout_s")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item)
           for item in (value, received, deadline)) or value < 0 or deadline <= 0:
        raise ValueError("following_airspeed_unavailable")
    if (observation.get("available") is not True or observation.get("source") not in {
            "mavsdk.fixedwing_metrics", "mavlink2rest.VFR_HUD"}):
        raise ValueError("following_airspeed_unavailable")
    if (health.get("ready") is not True or health.get("owner_current") is not True or
            observation.get("owner_instance") != str(id(controller)) or
            observation.get("connection_generation") != health.get("connection_generation") or
            observation.get("telemetry_generation") != health.get("telemetry_generation") or
            type(health.get("connection_generation")) is not int or
            type(health.get("telemetry_generation")) is not int or
            type(observation.get("connection_generation")) is not int or
            type(observation.get("telemetry_generation")) is not int):
        raise ValueError("following_airspeed_stale")
    age = time.monotonic() - received
    if observation.get("fresh") is not True or age < 0 or age > deadline:
        raise ValueError("following_airspeed_stale")
    return float(value)


def get_follower_speed_observation(controller):
    """Select fresh airspeed first; never replace a valid underspeed observation."""
    try:
        value = get_follower_airspeed(controller)
    except ValueError:
        from classes.parameters import Parameters
        if Parameters.FW_ATTITUDE_RATE.get("ALLOW_GROUND_SPEED_FALLBACK", False) is not True:
            raise
    else:
        from classes.command_preview import CommandPreviewController
        return {"speed_m_s": value, "source": "command_preview" if isinstance(
            controller, CommandPreviewController) else "airspeed", "fallback_active": False}

    try:
        health = controller.get_telemetry_readiness()
        if not isinstance(health, Mapping):
            raise ValueError("following_ground_speed_unavailable")
        age, deadline = health.get("last_complete_sample_age_s"), health.get("stale_timeout_s")
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item)
               for item in (age, deadline)) or deadline <= 0:
            raise ValueError("following_ground_speed_unavailable")
        if (health.get("ready") is not True or health.get("owner_current") is not True or
                type(health.get("connection_generation")) is not int or
                type(health.get("telemetry_generation")) is not int or
                health.get("connection_generation") != health.get("telemetry_connection_generation") or
                age < 0 or age > deadline):
            raise ValueError("following_ground_speed_stale")
        source = {"mavsdk": "mavsdk.velocity_body", "mavlink2rest": "mavlink2rest.LOCAL_POSITION_NED"}.get(health.get("source"))
        if source is None:
            raise ValueError("following_ground_speed_unavailable")
        observation = health.get("ground_speed_observation")
        if (not isinstance(observation, Mapping) or
                observation.get("connection_generation") != health["connection_generation"] or
                observation.get("telemetry_generation") != health["telemetry_generation"]):
            raise ValueError("following_ground_speed_stale")
        # Value and source receipt belong to the same complete owner snapshot.
        value = observation.get("speed_m_s")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("following_ground_speed_unavailable")
        source_age = observation.get("source_progress_age_s")
        if (isinstance(source_age, bool) or not isinstance(source_age, (int, float)) or
                not math.isfinite(source_age) or source_age < 0 or source_age > deadline):
            raise ValueError("following_ground_speed_stale")
        # Recheck owner after reading the source; never retain a prior-instance choice.
        current = controller.get_telemetry_readiness()
        if (current.get("ready") is not True or current.get("owner_current") is not True or
                current.get("connection_generation") != health["connection_generation"] or
                current.get("telemetry_generation") != health["telemetry_generation"]):
            raise ValueError("following_ground_speed_stale")
        return {"speed_m_s": float(value), "source": source, "fallback_active": True}
    except Exception as exc:
        code = str(exc) if str(exc) in {"following_ground_speed_stale", "following_ground_speed_unavailable"} else "following_ground_speed_unavailable"
        raise ValueError(code) from exc


def evaluate_following_start_airspeed(app, *, mode):
    if str(mode).lower() != "fw_attitude_rate":
        return {"ready": True}
    try:
        from classes.command_preview import CommandPreviewController
        if isinstance(getattr(app, "px4_interface", None), CommandPreviewController):
            raise ValueError("following_airspeed_unavailable")
        observation = get_follower_speed_observation(getattr(app, "px4_interface", None))
        value = observation["speed_m_s"]
        from classes.parameters import Parameters
        config = Parameters.FW_ATTITUDE_RATE
        minimum = config.get("MIN_AIRSPEED", 12.0) + config.get("STALL_MARGIN_BUFFER", 3.0)
        if not math.isfinite(minimum) or value < minimum:
            fallback = observation["fallback_active"]
            return {"ready": False, "code": "following_ground_speed_below_start_margin" if fallback else "following_airspeed_below_start_margin",
                    "message": f"Fixed-wing following requires {'ground-speed proxy' if fallback else 'aircraft airspeed'} at or above {minimum:.1f} m/s.",
                    "speed_observation": observation}
    except (ValueError, TypeError, RuntimeError) as exc:
        code = str(exc) if str(exc) in {"following_airspeed_unavailable", "following_airspeed_stale", "following_ground_speed_unavailable", "following_ground_speed_stale"} else "following_airspeed_unavailable"
        return {"ready": False, "code": code,
                "message": "Fixed-wing following requires fresh aircraft airspeed, or fresh ground speed when its fallback is enabled."}
    return {"ready": True, "speed_observation": observation,
            "message": "Using the operator-enabled ground-speed proxy; this is not measured airspeed." if observation["fallback_active"] else "Fresh aircraft airspeed is available."}
