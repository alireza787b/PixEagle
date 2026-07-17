"""Validation-only SITL injection helpers for typed /api/v1 routes."""

from __future__ import annotations

import hashlib
import asyncio
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, Optional

from fastapi import status
from fastapi.responses import JSONResponse, Response

from classes.api_v1_contracts import (
    SITL_VALIDATION_STATUS_CLAIM_BOUNDARY,
    SITLCommanderPublishFailureInjection,
    SITLMavlink2RestTimeoutInjection,
    SITLMavsdkDisconnectInjection,
    SITLTrackerOutputInjection,
    SITLVideoStallInjection,
)
from classes.api_v1_errors import build_sitl_error_response
from classes.api_v1_paths import (
    SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH,
    SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH,
    SITL_MAVSDK_DISCONNECT_INJECTION_PATH,
    SITL_TRACKER_OUTPUT_INJECTION_PATH,
    SITL_VALIDATION_STATUS_PATH,
    SITL_VIDEO_STALL_INJECTION_PATH,
)
from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.managed_sih import public_managed_sih_status


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITL_PLAN_PATH = (
    PROJECT_ROOT / "tools" / "sitl_plans" / "phase2_follower_validation.json"
)
DEFAULT_SITL_ARTIFACT_ROOT = PROJECT_ROOT / "reports" / "sitl"
LATEST_RUN_ARTIFACT_LIMIT = 12
REQUIRED_PHASE2_SCENARIOS = {
    "offboard_entry",
    "offboard_heartbeat",
    "follower_setpoints",
    "target_loss",
    "video_stall",
    "mavsdk_disconnect",
    "mavlink2rest_timeout",
    "operator_abort",
    "commander_publish_failure",
}
ABSOLUTE_PATH_PATTERN = re.compile(r"(?<![:\w])/[A-Za-z0-9._~!$&'()*+,;=:@%/-]+")


def sitl_injections_enabled() -> bool:
    """Return True only when validation-only mutation routes are enabled."""
    return os.getenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def sitl_error_response(
    *,
    status_code: int,
    code: str,
    detail: Any,
    path: str = SITL_TRACKER_OUTPUT_INJECTION_PATH,
) -> JSONResponse:
    """Build a typed /api/v1 error envelope for SITL validation routes."""
    return build_sitl_error_response(
        status_code=status_code,
        code=code,
        detail=detail,
        path=path,
    )


def _disabled_response(path: str = SITL_TRACKER_OUTPUT_INJECTION_PATH) -> JSONResponse:
    return sitl_error_response(
        status_code=status.HTTP_403_FORBIDDEN,
        code="SITL_INJECTIONS_DISABLED",
        detail={
            "message": (
                "Set PIXEAGLE_ENABLE_SITL_INJECTIONS=1 only for an "
                "operator-approved validation stack."
            ),
        },
        path=path,
    )


def _repo_relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _sanitize_manifest_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    project_root = PROJECT_ROOT.resolve().as_posix()
    text = text.replace(f"{project_root}/", "")
    text = text.replace(project_root, ".")
    return ABSOLUTE_PATH_PATTERN.sub("<absolute-path>", text)


def _sanitize_manifest_list(value: Any) -> list[str]:
    return [
        sanitized
        for item in _string_list(value)
        if (sanitized := _sanitize_manifest_text(item))
    ]


def _plan_hash(raw_plan: str) -> str:
    return hashlib.sha256(raw_plan.encode("utf-8")).hexdigest()


def _get_sitl_plan_summary(plan_path: Optional[Path] = None) -> dict[str, Any]:
    plan_path = plan_path or DEFAULT_SITL_PLAN_PATH
    raw_plan = plan_path.read_text(encoding="utf-8")
    plan = json.loads(raw_plan)
    if not isinstance(plan, dict):
        raise ValueError("SITL plan must be a JSON object.")

    stack = plan.get("stack") if isinstance(plan.get("stack"), dict) else {}
    px4 = stack.get("px4") if isinstance(stack.get("px4"), dict) else {}
    routing = stack.get("routing") if isinstance(stack.get("routing"), dict) else {}
    scenarios = plan.get("scenarios") if isinstance(plan.get("scenarios"), list) else []
    evidence = (
        plan.get("evidence_contract")
        if isinstance(plan.get("evidence_contract"), list)
        else []
    )
    required_present = sorted(
        str(scenario.get("id"))
        for scenario in scenarios
        if isinstance(scenario, dict) and scenario.get("id")
    )
    scenario_ids = set(required_present)
    tags = set(_string_list(plan.get("tags")))
    phase2_required_applicable = (
        "phase2" in tags
        or str(plan.get("name") or "") == "phase2_follower_validation"
    )

    return {
        "name": str(plan.get("name") or "phase2_follower_validation"),
        "title": str(plan.get("title") or "Phase 2 PX4-In-Loop Follower Validation"),
        "level": "L2",
        "source": _repo_relative_path(plan_path),
        "hash": _plan_hash(raw_plan),
        "scenario_count": len(scenarios),
        "required_phase2_scenarios_present": sorted(
            REQUIRED_PHASE2_SCENARIOS.intersection(scenario_ids)
            if phase2_required_applicable
            else []
        ),
        "required_phase2_scenarios_missing": sorted(
            REQUIRED_PHASE2_SCENARIOS - scenario_ids
            if phase2_required_applicable
            else []
        ),
        "evidence_artifact_count": len(evidence),
        "routing_provider": str(routing.get("provider") or "mavlink-anywhere"),
        "px4_image": px4.get("recommended_image"),
        "px4_model": px4.get("vehicle_model"),
    }


def _manifest_sort_value(path: Path, payload: dict[str, Any]) -> tuple[str, float]:
    timestamp = str(
        payload.get("updated_at")
        or payload.get("finished_at")
        or payload.get("started_at")
        or ""
    )
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    return timestamp, modified


def _latest_sitl_manifest(
    *,
    artifact_root: Optional[Path] = None,
    plan_name: str = "phase2_follower_validation",
) -> tuple[Optional[Path], Optional[dict[str, Any]]]:
    artifact_root = artifact_root or DEFAULT_SITL_ARTIFACT_ROOT
    if not artifact_root.exists():
        return None, None

    candidates: list[tuple[tuple[str, float], Path, dict[str, Any]]] = []
    for manifest_path in artifact_root.glob("*/manifest.json"):
        try:
            payload = _load_json_object(manifest_path)
        except (OSError, json.JSONDecodeError):
            continue
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        if plan.get("name") != plan_name:
            continue
        candidates.append((
            _manifest_sort_value(manifest_path, payload),
            manifest_path,
            payload,
        ))

    if not candidates:
        return None, None

    _sort_value, path, payload = max(candidates, key=lambda item: item[0])
    return path, payload


def _latest_run_summary(artifact_root: Optional[Path] = None) -> dict[str, Any]:
    artifact_root = artifact_root or DEFAULT_SITL_ARTIFACT_ROOT
    manifest_path, payload = _latest_sitl_manifest(artifact_root=artifact_root)
    if manifest_path is None or payload is None:
        return {
            "available": False,
            "run_id": None,
            "mode": None,
            "result": None,
            "result_reason": None,
            "artifact_dir": None,
            "started_at": None,
            "finished_at": None,
            "updated_at": None,
            "scenario_execution_enabled": False,
            "control_actions_allowed": False,
            "missing_or_placeholder_count": 0,
            "missing_or_placeholder_artifacts": [],
            "missing_or_placeholder_truncated": False,
            "semantic_failures": [],
            "artifact_content_failures": [],
            "claim_boundary": SITL_VALIDATION_STATUS_CLAIM_BOUNDARY,
        }

    scenario_execution = (
        payload.get("scenario_execution")
        if isinstance(payload.get("scenario_execution"), dict)
        else {}
    )
    result = payload.get("result")
    if result not in {"pass", "incomplete", "failed"}:
        result = None
    missing_all = _string_list(payload.get("missing_or_placeholder_artifacts"))
    missing = missing_all[:LATEST_RUN_ARTIFACT_LIMIT]

    return {
        "available": True,
        "run_id": str(payload.get("run_id") or manifest_path.parent.name),
        "mode": payload.get("mode"),
        "result": result,
        "result_reason": _sanitize_manifest_text(payload.get("result_reason")),
        "artifact_dir": _repo_relative_path(manifest_path.parent),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "updated_at": payload.get("updated_at"),
        "scenario_execution_enabled": bool(scenario_execution.get("enabled")),
        "control_actions_allowed": bool(
            scenario_execution.get("control_actions_allowed")
        ),
        "missing_or_placeholder_count": len(missing_all),
        "missing_or_placeholder_artifacts": missing,
        "missing_or_placeholder_truncated": len(missing_all) > len(missing),
        "semantic_failures": _sanitize_manifest_list(payload.get("semantic_failures")),
        "artifact_content_failures": _sanitize_manifest_list(
            payload.get("artifact_content_failures")
        ),
        "claim_boundary": SITL_VALIDATION_STATUS_CLAIM_BOUNDARY,
    }


def _sih_training_commands() -> list[dict[str, Any]]:
    return [
        {
            "label": "SIH dry run",
            "command": "make sitl-sih-dry-run",
            "mode": "dry_run",
            "starts_processes": False,
            "writes_artifacts": False,
            "requires_operator_stack": False,
            "claim_boundary": (
                "Validates the checked-in L2 plan only; no Docker, PX4, "
                "routing, PixEagle, MAVLink2REST, or evidence artifact is started."
            ),
        },
        {
            "label": "Probe prepared stack",
            "command": "make sitl-sih-probe",
            "mode": "probe_only",
            "starts_processes": False,
            "writes_artifacts": True,
            "requires_operator_stack": True,
            "claim_boundary": (
                "Collects evidence from an already prepared operator-approved "
                "SIH stack; it does not start PX4 or mutate routing."
            ),
        },
        {
            "label": "PX4-only SIH container",
            "command": "make sitl-sih-execute-px4",
            "mode": "execute_px4",
            "starts_processes": True,
            "writes_artifacts": True,
            "requires_operator_stack": True,
            "claim_boundary": (
                "Starts only the harness-owned official PX4 SIH container; "
                "MavlinkAnywhere, MAVLink2REST, PixEagle, and routing remain "
                "operator-managed."
            ),
        },
    ]


def get_sitl_validation_status_snapshot(owner: Optional[Any] = None) -> dict[str, Any]:
    """Return read-only SIH validation plan and latest-manifest metadata."""
    plan = _get_sitl_plan_summary()
    return {
        "schema_version": 3,
        "source": "pixeagle_sitl_validation_status",
        "profile": "official_px4_sih",
        "default_artifact_root": _repo_relative_path(DEFAULT_SITL_ARTIFACT_ROOT),
        "injections_enabled": sitl_injections_enabled(),
        "raw_injection_controls_exposed": False,
        "plan": plan,
        "commands": _sih_training_commands(),
        "managed_lifecycle": public_managed_sih_status(owner),
        "latest_run": _latest_run_summary(),
        "claim_boundary": SITL_VALIDATION_STATUS_CLAIM_BOUNDARY,
        "timestamp": time.time(),
    }


async def get_sitl_validation_status(owner: Any) -> Any:
    """Return read-only SIH validation training status for dashboard users."""
    try:
        return await asyncio.to_thread(get_sitl_validation_status_snapshot, owner)
    except Exception as error:
        logger = getattr(owner, "logger", None)
        if logger is not None:
            logger.error(f"Error in get_sitl_validation_status: {error}")
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="sitl_validation_status_error",
            detail=str(error),
            path=SITL_VALIDATION_STATUS_PATH,
        )


def parse_tracker_data_type(value: str) -> TrackerDataType:
    token = str(value).strip()
    if token in TrackerDataType.__members__:
        return TrackerDataType[token]

    upper_token = token.upper()
    if upper_token in TrackerDataType.__members__:
        return TrackerDataType[upper_token]

    try:
        return TrackerDataType(token)
    except ValueError:
        try:
            return TrackerDataType(upper_token)
        except ValueError as exc:
            valid = ", ".join(item.value for item in TrackerDataType)
            raise ValueError(
                f"Unsupported tracker data_type {value!r}. Valid values: {valid}"
            ) from exc


def tracker_output_from_sitl_injection(
    injection: SITLTrackerOutputInjection,
) -> TrackerOutput:
    """Build TrackerOutput from the typed validation injection request."""
    raw_data = dict(injection.raw_data or {})
    metadata = dict(injection.metadata or {})

    freshness_fields = {
        "usable_for_following": injection.usable_for_following,
        "data_is_stale": injection.data_is_stale,
        "freshness_reason": injection.freshness_reason,
        "has_output": injection.has_output,
    }
    for key, value in freshness_fields.items():
        if value is not None:
            raw_data.setdefault(key, value)
            metadata.setdefault(key, value)

    raw_data.setdefault("sitl_injection", True)
    raw_data.setdefault("sitl_injection_id", injection.injection_id)
    metadata.setdefault("source", injection.source)
    metadata.setdefault("sitl_injection", True)
    metadata.setdefault("sitl_injection_id", injection.injection_id)

    return TrackerOutput(
        data_type=parse_tracker_data_type(injection.data_type),
        timestamp=injection.timestamp or time.time(),
        tracking_active=injection.tracking_active,
        tracker_id=injection.tracker_id,
        position_2d=injection.position_2d,
        position_3d=injection.position_3d,
        angular=injection.angular,
        bbox=injection.bbox,
        normalized_bbox=injection.normalized_bbox,
        confidence=injection.confidence,
        quality_metrics=dict(injection.quality_metrics or {}),
        velocity=injection.velocity,
        acceleration=injection.acceleration,
        target_id=injection.target_id,
        targets=injection.targets,
        raw_data=raw_data,
        metadata=metadata,
    )


def frame_status_from_sitl_video_stall(
    injection: SITLVideoStallInjection,
) -> Dict[str, Any]:
    """Build frame freshness metadata from a validation video-stall request."""
    frame_status = {
        "source": injection.frame_source,
        "status": injection.frame_status,
        "usable_for_following": injection.usable_for_following,
        "reason": injection.reason,
        "timestamp": injection.timestamp or time.time(),
        "sitl_injection": True,
        "sitl_injection_id": injection.injection_id,
    }
    if injection.consecutive_failures is not None:
        frame_status["consecutive_failures"] = injection.consecutive_failures
    if injection.metadata:
        frame_status["metadata"] = dict(injection.metadata)
    return frame_status


async def inject_sitl_tracker_output(
    owner: Any,
    injection: SITLTrackerOutputInjection,
    response: Response,
) -> Any:
    """
    Validation-only handler for injecting TrackerOutput into follow mode.

    The route is disabled by default and exists for operator-gated SITL runs.
    It never starts PX4, routing, video, Docker, or Offboard mode.
    """
    if not sitl_injections_enabled():
        return _disabled_response()

    try:
        tracker_output = tracker_output_from_sitl_injection(injection)
    except ValueError as exc:
        return sitl_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="INVALID_TRACKER_OUTPUT",
            detail={"message": str(exc)},
        )

    app_controller = owner.app_controller
    if injection.dry_run:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "validated",
            "accepted": False,
            "reason": "dry_run",
            "following_active": bool(getattr(app_controller, "following_active", False)),
            "injection": {
                "source": injection.source,
                "tracker_id": tracker_output.tracker_id,
                "data_type": tracker_output.data_type.value,
                "input_tracking_active": tracker_output.tracking_active,
            },
            "command_intent": None,
            "offboard_commander": None,
            "timestamp": time.time(),
        }

    if not hasattr(app_controller, "inject_tracker_output_for_validation"):
        return sitl_error_response(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="SITL_INJECTION_UNAVAILABLE",
            detail={
                "message": "AppController validation injection hook is unavailable.",
            },
        )

    result = await app_controller.inject_tracker_output_for_validation(
        tracker_output,
        source=injection.source,
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED
        if result.get("accepted") is True
        else status.HTTP_409_CONFLICT
    )
    if result.get("accepted") is not True:
        return sitl_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SITL_INJECTION_REJECTED",
            detail=result,
        )
    return result


async def inject_sitl_video_stall(
    owner: Any,
    injection: SITLVideoStallInjection,
    response: Response,
) -> Any:
    """
    Validation-only handler for injecting video-frame stall metadata.

    The route is disabled by default and uses the same fail-closed path as the
    main frame loop when VideoHandler cannot provide a fresh frame.
    """
    if not sitl_injections_enabled():
        return _disabled_response(SITL_VIDEO_STALL_INJECTION_PATH)

    app_controller = owner.app_controller
    frame_status = frame_status_from_sitl_video_stall(injection)

    if injection.dry_run:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "validated",
            "accepted": False,
            "reason": "dry_run",
            "following_active": bool(getattr(app_controller, "following_active", False)),
            "injection": {
                "source": injection.source,
                "tracker_requires_video": bool(
                    app_controller._tracker_requires_video_for_following()
                )
                if hasattr(app_controller, "_tracker_requires_video_for_following")
                else True,
                "frame_status": frame_status,
            },
            "command_intent": None,
            "offboard_commander": None,
            "timestamp": time.time(),
        }

    if not hasattr(app_controller, "inject_video_stall_for_validation"):
        return sitl_error_response(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="SITL_INJECTION_UNAVAILABLE",
            detail={
                "message": "AppController video-stall validation hook is unavailable.",
            },
            path=SITL_VIDEO_STALL_INJECTION_PATH,
        )

    result = await app_controller.inject_video_stall_for_validation(
        frame_status,
        source=injection.source,
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED
        if result.get("accepted") is True
        else status.HTTP_409_CONFLICT
    )
    if result.get("accepted") is not True:
        return sitl_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SITL_INJECTION_REJECTED",
            detail=result,
            path=SITL_VIDEO_STALL_INJECTION_PATH,
        )
    return result


async def inject_sitl_commander_publish_failure(
    owner: Any,
    injection: SITLCommanderPublishFailureInjection,
    response: Response,
) -> Any:
    """
    Validation-only handler for commander publish-failure policy checks.

    The route records bounded synthetic publish failures inside the active
    OffboardCommander and exercises local fail-closed cleanup without sending
    synthetic MAVSDK setpoints, stopping services, or changing MAVLink routing.
    """
    if not sitl_injections_enabled():
        return _disabled_response(SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH)

    app_controller = owner.app_controller
    if injection.dry_run:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "validated",
            "accepted": False,
            "reason": "dry_run",
            "following_active": bool(getattr(app_controller, "following_active", False)),
            "injection": {
                "source": injection.source,
                "failure_mode": injection.failure_mode,
                "requested_failure_count": injection.failure_count,
                "applied_failure_count": 0,
                "failure_reason": injection.reason,
                "metadata": dict(injection.metadata or {}),
            },
            "offboard_commander": None,
            "offboard_commander_before": None,
            "offboard_commander_after": None,
            "offboard_commander_failure": None,
            "disconnect_result": None,
            "timestamp": time.time(),
        }

    if not hasattr(
        app_controller,
        "inject_commander_publish_failure_for_validation",
    ):
        return sitl_error_response(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="SITL_INJECTION_UNAVAILABLE",
            detail={
                "message": (
                    "AppController commander publish-failure validation "
                    "hook is unavailable."
                ),
            },
            path=SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH,
        )

    result = await app_controller.inject_commander_publish_failure_for_validation(
        failure_count=injection.failure_count,
        reason=injection.reason,
        source=injection.source,
        metadata={
            **dict(injection.metadata or {}),
            "sitl_injection": True,
            "sitl_injection_id": injection.injection_id,
        },
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED
        if result.get("accepted") is True
        else status.HTTP_409_CONFLICT
    )
    if result.get("accepted") is not True:
        return sitl_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SITL_INJECTION_REJECTED",
            detail=result,
            path=SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH,
        )
    return result


async def inject_sitl_mavsdk_disconnect(
    owner: Any,
    injection: SITLMavsdkDisconnectInjection,
    response: Response,
) -> Any:
    """
    Validation-only handler for local MAVSDK command-path disconnect.

    This marks PixEagle's local PX4/MAVSDK command path disconnected, records
    bounded OffboardCommander publish failures, then awaits the existing
    fail-closed cleanup path. It does not stop PX4, Docker, MavlinkAnywhere,
    MAVLink2REST, network interfaces, MAVSDK server, or MAVLink routes.
    """
    if not sitl_injections_enabled():
        return _disabled_response(SITL_MAVSDK_DISCONNECT_INJECTION_PATH)

    app_controller = owner.app_controller
    if injection.dry_run:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "validated",
            "accepted": False,
            "reason": "dry_run",
            "following_active": bool(getattr(app_controller, "following_active", False)),
            "injection": {
                "source": injection.source,
                "failure_mode": injection.failure_mode,
                "requested_failure_count": injection.failure_count,
                "applied_failure_count": 0,
                "failure_reason": injection.reason,
                "metadata": dict(injection.metadata or {}),
            },
            "px4_connection_before": None,
            "px4_connection_after": None,
            "offboard_commander": None,
            "offboard_commander_before": None,
            "offboard_commander_after": None,
            "offboard_commander_failure": None,
            "disconnect_result": None,
            "timestamp": time.time(),
        }

    if not hasattr(app_controller, "inject_mavsdk_disconnect_for_validation"):
        return sitl_error_response(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="SITL_INJECTION_UNAVAILABLE",
            detail={
                "message": (
                    "AppController MAVSDK disconnect validation hook is unavailable."
                ),
            },
            path=SITL_MAVSDK_DISCONNECT_INJECTION_PATH,
        )

    result = await app_controller.inject_mavsdk_disconnect_for_validation(
        failure_count=injection.failure_count,
        reason=injection.reason,
        source=injection.source,
        failure_mode=injection.failure_mode,
        metadata={
            **dict(injection.metadata or {}),
            "sitl_injection": True,
            "sitl_injection_id": injection.injection_id,
            "stimulus": "mavsdk_disconnect",
            "transport_scope": "pixeagle_local_only",
        },
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED
        if result.get("accepted") is True
        else status.HTTP_409_CONFLICT
    )
    if result.get("accepted") is not True:
        return sitl_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SITL_INJECTION_REJECTED",
            detail=result,
            path=SITL_MAVSDK_DISCONNECT_INJECTION_PATH,
        )
    return result


async def inject_sitl_mavlink2rest_timeout(
    owner: Any,
    injection: SITLMavlink2RestTimeoutInjection,
    response: Response,
) -> Any:
    """
    Validation-only handler for MAVLink2REST client timeout freshness.

    The route records local telemetry transport timeout state in
    MavlinkDataManager without stopping MAVLink2REST, Docker, PX4, MAVLink
    routing, or network interfaces.
    """
    if not sitl_injections_enabled():
        return _disabled_response(SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH)

    app_controller = owner.app_controller
    if injection.dry_run:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "validated",
            "accepted": False,
            "reason": "dry_run",
            "injection": {
                "source": injection.source,
                "requested_failure_count": injection.failure_count,
                "applied_failure_count": 0,
                "failure_reason": injection.reason,
                "force_stale": injection.force_stale,
                "timeout_window_s": injection.timeout_window_s,
                "metadata": dict(injection.metadata or {}),
            },
            "mavlink_telemetry": None,
            "timestamp": time.time(),
        }

    if not hasattr(app_controller, "inject_mavlink2rest_timeout_for_validation"):
        return sitl_error_response(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="SITL_INJECTION_UNAVAILABLE",
            detail={
                "message": (
                    "AppController MAVLink2REST timeout validation hook is unavailable."
                ),
            },
            path=SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH,
        )

    result = await app_controller.inject_mavlink2rest_timeout_for_validation(
        failure_count=injection.failure_count,
        reason=injection.reason,
        force_stale=injection.force_stale,
        timeout_window_s=injection.timeout_window_s,
        source=injection.source,
        metadata={
            **dict(injection.metadata or {}),
            "sitl_injection": True,
            "sitl_injection_id": injection.injection_id,
        },
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED
        if result.get("accepted") is True
        else status.HTTP_409_CONFLICT
    )
    if result.get("accepted") is not True:
        return sitl_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SITL_INJECTION_REJECTED",
            detail=result,
            path=SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH,
        )
    return result


__all__ = [
    "frame_status_from_sitl_video_stall",
    "get_sitl_validation_status",
    "get_sitl_validation_status_snapshot",
    "inject_sitl_commander_publish_failure",
    "inject_sitl_mavlink2rest_timeout",
    "inject_sitl_mavsdk_disconnect",
    "inject_sitl_tracker_output",
    "inject_sitl_video_stall",
    "parse_tracker_data_type",
    "sitl_error_response",
    "sitl_injections_enabled",
    "tracker_output_from_sitl_injection",
]
