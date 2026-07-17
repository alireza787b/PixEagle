"""Process-local API v1 telemetry health helpers."""

from __future__ import annotations

import time
from typing import Any, Dict

from classes.api_v1_contracts import MAVLINK_TELEMETRY_CLAIM_BOUNDARY


def get_telemetry_health_snapshot(owner: Any) -> Dict[str, Any]:
    """Return typed MAVLink2REST health or a fail-closed unavailable snapshot."""
    app_controller = owner.app_controller
    mavlink_manager = getattr(app_controller, "mavlink_data_manager", None)
    if mavlink_manager and hasattr(mavlink_manager, "get_telemetry_health"):
        return mavlink_manager.get_telemetry_health()

    return {
        "schema_version": 1,
        "source": "mavlink2rest",
        "enabled": False,
        "status": "disconnected",
        "consumer_guidance": "unavailable",
        "transport": {
            "state": "unavailable",
            "latest_request_ok": False,
            "latest_request_result": "not_attempted",
            "latest_request_age_s": None,
            "last_error": "MAVLink data manager is not configured",
            "error_count": 0,
            "validation_timeout_active": False,
            "request_timeout_s": None,
            "request_retries": None,
            "endpoint": None,
        },
        "request_freshness": {
            "fresh": False,
            "last_success_age_s": None,
            "stale_timeout_s": None,
            "last_success_monotonic_available": False,
        },
        "payload": {
            "has_payload": False,
            "sample_count": 0,
            "available_keys": [],
            "flight_mode": None,
            "arm_status": None,
            "fresh": False,
            "payload_age_s": None,
        },
        "claim_boundary": MAVLINK_TELEMETRY_CLAIM_BOUNDARY,
        "timestamp": time.time(),
    }


__all__ = [
    "get_telemetry_health_snapshot",
]
