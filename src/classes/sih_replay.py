"""Replay authorization for the launcher-owned isolated PX4 SIH bench only."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import time

from classes.backend_supervisor import supervisor_available, validate_sih_routes
from classes.parameters import Parameters


def isolated_sih_replay_authorized(app) -> bool:
    if (getattr(Parameters, "SIH_RECORDED_VIDEO_FOLLOWING", False) is not True
            or getattr(Parameters, "FOLLOWER_EXECUTION_MODE", "PX4") != "PX4"
            or getattr(Parameters, "VIDEO_SOURCE_TYPE", "") != "VIDEO_FILE"
            or not supervisor_available()):
        return False
    try:
        root = Path(os.environ["PIXEAGLE_PROJECT_ROOT"])
        path = root / "logs/sih-replay-binding.json"
        if os.environ.get("PIXEAGLE_SIH_REPLAY_BINDING") != str(path):
            return False
        if path.is_symlink() or path.stat().st_mode & 0o077:
            return False
        binding = json.loads(path.read_text(encoding="utf-8"))
        uid = binding["simulated_autopilot_uid"]
        if (binding.get("kind") != "owned-isolated-sih-v1"
                or binding.get("instance_id") != os.environ.get("PIXEAGLE_INSTANCE_ID")
                or binding.get("network_namespace") != os.readlink("/proc/self/ns/net")
                or not isinstance(uid, str) or not uid.isdecimal() or int(uid) <= 0):
            return False
        validate_sih_routes(Parameters._raw_config)
        command = app.px4_interface.get_aircraft_identity()
        telemetry = app.mavlink_data_manager.get_aircraft_identity()
        flight = app.mavlink_data_manager.get_flight_state()
        return bool(command.get("connected") is True
            and command.get("autopilot_uid") == uid
            and telemetry.get("connected") is True and telemetry.get("fresh") is True
            and telemetry.get("autopilot_uid") == uid
            and flight.get("fresh") is True and flight.get("autopilot_uid") == uid
            and flight.get("connection_generation") == telemetry.get("connection_generation")
            and command.get("connection_generation") is not None
            and (not getattr(app, "following_active", False)
                 or getattr(app, "_following_session_aircraft_uid", None) == uid))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def following_video_frame_status(app, frame_status: dict) -> dict:
    """Retain replay provenance; authorize only a current decoded SIH frame."""
    result = dict(frame_status)
    # A status dictionary cannot assert its own simulator authorization.
    result.pop("sih_replay_authorized", None)
    if result.get("replay_source") is not True or not isolated_sih_replay_authorized(app):
        return result
    try:
        stamp = app.video_handler.get_capture_stamp()
        age = time.monotonic() - stamp.captured_at
        fresh = (stamp.state == "fresh" and math.isfinite(age) and 0 <= age <= 1.5
                 and result.get("source") == "fresh" and result.get("connection_open") is True)
    except (AttributeError, TypeError, ValueError):
        fresh = False
    result["sih_replay_authorized"] = fresh
    result["usable_for_following"] = fresh
    return result
