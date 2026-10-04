"""Authenticated native-client observation contract; never a flight action."""

from __future__ import annotations

import asyncio

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.api_security_types import APIPrincipalKind
from classes.api_v1_contracts import APIIntegrationContextResponse
from classes.api_v1_paths import API_V1_INTEGRATION_CONNECTION_PATH, API_V1_INTEGRATION_CONTEXT_PATH
from classes.app_version import PIXEAGLE_VERSION
from classes.backend_supervisor import supervisor_available
from classes.parameters import Parameters
from classes.runtime_identity import INSTANCE_ID, INSTANCE_ID_SOURCE, RUNTIME_ID


def context_snapshot(owner, principal):
    controller = owner.app_controller
    px4 = getattr(controller, "px4_interface", None)
    command = {"source": "mavsdk", "connected": False,
               "connection_generation": "0", "autopilot_uid": None}
    if px4 is not None:
        command = px4.get_aircraft_identity()
    telemetry = {"source": "mavlink2rest", "connected": False, "fresh": False,
                 "connection_generation": "0", "autopilot_uid": None}
    if bool(getattr(Parameters, "USE_MAVLINK2REST", False)):
        manager = getattr(controller, "mavlink_data_manager", None)
        if manager is not None:
            telemetry = manager.get_aircraft_identity()
    elif px4 is not None:
        readiness = px4.get_telemetry_readiness()
        telemetry = {**command, "fresh": readiness.get("ready") is True}
        # MAVSDK Python info does not expose the target system ID. UID alone
        # cannot establish QGC's requested system/component route.
    reasons = []
    if not command.get("connected"):
        reasons.append("command_disconnected")
    if not command.get("autopilot_uid"):
        reasons.append("command_identity_unknown")
    if not telemetry.get("connected"):
        reasons.append("telemetry_disconnected")
    if not telemetry.get("fresh"):
        reasons.append(telemetry.get("reason") or "telemetry_stale")
    if not telemetry.get("autopilot_uid"):
        reasons.append("telemetry_identity_unknown")
    if telemetry.get("system_id") is None:
        reasons.append("telemetry_route_unobserved")
    if command.get("autopilot_uid") and telemetry.get("autopilot_uid") and (
        command["autopilot_uid"] != telemetry["autopilot_uid"]
    ):
        reasons.append("aircraft_identity_mismatch")
    # Reject a snapshot that straddled a connection-generation change.
    if px4 is not None and command != px4.get_aircraft_identity():
        reasons.append("command_generation_changed")
    reasons = list(dict.fromkeys(reasons))
    publisher = (getattr(owner, "frame_publisher", None)
                 if getattr(Parameters, "ENABLE_STREAMING", True) else None)
    video = publisher.video_context(prefer_osd=Parameters.STREAM_PROCESSED_OSD) if publisher else {}
    payload = APIIntegrationContextResponse(
        instance_id=INSTANCE_ID, instance_id_source=INSTANCE_ID_SOURCE,
        runtime_id=RUNTIME_ID, backend_version=PIXEAGLE_VERSION,
        command=command, telemetry=telemetry,
        video=video,
        capabilities=["integration.context.v1", "status.tracker_runtime.v1", "models.operations.v1",
                      "following.operations.v1", "config.operations.v1", "camera.control.v1",
                      "safety.circuit_breaker.v1"] + (["config.system_restart.v1"] if supervisor_available() else []) + (
            ["video.frame_provenance.v1", "target.operations.v1", "target.unbound_tracking.v1"]
            if publisher is not None else []
        ),
        association={"verified": not reasons, "reason_codes": reasons},
        permissions={"principal_kind": principal.kind.value, "scopes": sorted(principal.scopes)},
        readiness={"connection_ready": not reasons, "following_allowed": False,
                   "reason_codes": reasons + ["following_status_required"]},
    )
    return payload.model_dump(mode="json")


async def integration_context(owner, request, *, connect=False):
    path = API_V1_INTEGRATION_CONNECTION_PATH if connect else API_V1_INTEGRATION_CONTEXT_PATH
    principal = getattr(request.state, "api_principal", None)
    if principal is None or principal.kind not in (APIPrincipalKind.SESSION, APIPrincipalKind.BEARER):
        return owner._api_v1_error_response(
            status_code=401, code="native_credentials_required",
            detail="Native integration requires a browser session or scoped bearer credential.", path=path,
        )
    try:
        if connect:
            # Bound total time, including waiting for the lifecycle barrier.
            await asyncio.wait_for(owner.app_controller.observe_native_connection(), timeout=17.0)
        return JSONResponse(context_snapshot(owner, principal), headers={"Cache-Control": "no-store"})
    except asyncio.TimeoutError:
        return owner._api_v1_error_response(
            status_code=504, code="native_discovery_timeout",
            detail="Observational aircraft discovery timed out.", path=path,
        )
    except Exception:
        # Do not expose raw transport endpoints or internal exception strings.
        return owner._api_v1_error_response(
            status_code=503, code="native_context_unavailable",
            detail="Aircraft observation is unavailable.", path=path,
        )
