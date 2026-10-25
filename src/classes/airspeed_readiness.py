"""Fixed-wing speed admission with an explicit, optional ground-speed proxy."""

import math
import time
from collections.abc import Mapping


def _speed_source_policy():
    """Resolve the single fixed-wing speed policy with legacy read compatibility."""
    from classes.parameters import Parameters

    config = Parameters.FW_ATTITUDE_RATE
    policy = config.get("SPEED_SOURCE_POLICY")
    if policy is None:
        # Older saved configurations only have the boolean fallback. Read it
        # once at the boundary; all runtime decisions use the typed policy.
        policy = "auto" if config.get("ALLOW_GROUND_SPEED_FALLBACK", False) is True else "airspeed_only"
    policy = str(policy).strip().lower()
    if policy not in {"auto", "airspeed_only", "ground_speed_only"}:
        raise ValueError("following_speed_source_policy_invalid")
    return policy, config


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
    """Select the configured fresh speed source and retain provenance."""
    policy, config = _speed_source_policy()
    reference_speed = config.get("INITIAL_ENGAGING_SPEED", config.get("CRUISE_AIRSPEED", 18.0))
    if isinstance(reference_speed, bool) or not isinstance(reference_speed, (int, float)) or not math.isfinite(reference_speed) or reference_speed < 0:
        raise ValueError("following_speed_source_policy_invalid")
    if policy == "ground_speed_only":
        airspeed_error = "following_ground_speed_unavailable"
    else:
        airspeed_error = None
        try:
            value = get_follower_airspeed(controller)
        except ValueError as exc:
            airspeed_error = str(exc)
            if policy == "airspeed_only":
                raise
        else:
            from classes.command_preview import CommandPreviewController
            return {"speed_m_s": value, "source": "command_preview" if isinstance(
                controller, CommandPreviewController) else "airspeed", "fallback_active": False,
                "reference_speed_m_s": float(reference_speed), "policy": policy}

    if airspeed_error == "following_airspeed_stale" and policy == "airspeed_only":
        raise ValueError(airspeed_error)
    if policy not in {"auto", "ground_speed_only"}:
        raise ValueError(airspeed_error or "following_airspeed_unavailable")

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
        return {"speed_m_s": float(value), "source": "ground_speed_proxy", "fallback_active": True,
                "source_detail": source, "reference_speed_m_s": float(reference_speed), "policy": policy}
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
                "message": "Fixed-wing following requires fresh airspeed or fresh ground speed under the automatic speed policy."}
    return {"ready": True, "speed_observation": observation,
            "message": "Using fresh ground speed as a labelled proxy; it is not measured airspeed." if observation["fallback_active"] else "Fresh aircraft airspeed is available."}
