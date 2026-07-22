"""Process-local API v1 runtime, following, and tracking snapshot builders."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from fastapi.encoders import jsonable_encoder

from classes.app_version import PIXEAGLE_VERSION
from classes.api_v1_contracts import (
    FOLLOWING_STATUS_CLAIM_BOUNDARY,
    FOLLOWING_TELEMETRY_CLAIM_BOUNDARY,
    RUNTIME_STATUS_CLAIM_BOUNDARY,
    SYSTEM_ABOUT_CLAIM_BOUNDARY,
    SYSTEM_UPDATE_SAFE_WORKFLOW,
    SYSTEM_UPDATE_STATUS_REASON,
    TRACKING_CATALOG_CLAIM_BOUNDARY,
    TRACKING_TELEMETRY_CLAIM_BOUNDARY,
)
from classes.model_manager import AI_AVAILABLE
from classes.command_preview import (
    COMMAND_PREVIEW_EXECUTION_MODE,
    normalize_follower_execution_mode,
)
from classes.following_readiness import (
    evaluate_following_start_readiness,
    get_configured_follower_execution_mode,
)
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler
from classes.tracker_runtime_status import (
    evaluate_tracker_runtime_status,
    tracker_runtime_unavailable_status,
)

try:
    from classes.circuit_breaker import FollowerCircuitBreaker

    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False


TRACKER_OUTPUT_UNSET = object()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_REPOSITORY_URL = "https://github.com/alireza787b/PixEagle"
PROJECT_DOCS_URL = f"{PROJECT_REPOSITORY_URL}/tree/main/docs"


def _utc_iso_from_timestamp(timestamp: Optional[float]) -> Optional[str]:
    if timestamp is None:
        return None
    try:
        return (
            datetime.fromtimestamp(float(timestamp), timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (TypeError, ValueError, OSError):
        return None


def _git_output(args: List[str], cwd: Path = PROJECT_ROOT) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=1.0,
            check=True,
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        OSError,
    ):
        return None
    value = completed.stdout.strip()
    return value or None


def _get_git_metadata(cwd: Path = PROJECT_ROOT) -> Dict[str, Any]:
    full_commit = _git_output(["rev-parse", "HEAD"], cwd)
    short_commit = _git_output(["rev-parse", "--short", "HEAD"], cwd)
    branch = _git_output(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    commit_date = _git_output(["log", "-1", "--format=%cI"], cwd)
    describe = _git_output(["describe", "--tags", "--always", "--dirty"], cwd)
    dirty_output = _git_output(["status", "--porcelain"], cwd)

    if branch == "HEAD":
        branch = "detached"

    return {
        "available": bool(full_commit),
        "commit": short_commit or "unknown",
        "full_commit": full_commit,
        "branch": branch or "unknown",
        "date": commit_date or "unknown",
        "dirty": None if full_commit is None else bool(dirty_output),
        "describe": describe,
    }


def get_system_about_snapshot(owner: Any) -> Dict[str, Any]:
    """Return process-local system/about metadata without runtime mutations."""
    process = None
    try:
        import psutil

        process = psutil.Process()
    except Exception:
        process = None

    memory_mb = None
    cpu_percent = None
    started_at = None
    uptime_seconds = None
    pid = None
    if process is not None:
        try:
            pid = int(process.pid)
            memory_mb = round(process.memory_info().rss / (1024 * 1024), 2)
            cpu_percent = float(process.cpu_percent(interval=None))
            create_time = float(process.create_time())
            started_at = _utc_iso_from_timestamp(create_time)
            uptime_seconds = round(max(0.0, time.time() - create_time), 3)
        except Exception:
            memory_mb = None
            cpu_percent = None
            started_at = None
            uptime_seconds = None
            pid = None

    video_handler = getattr(owner, "video_handler", None)
    video_health: Dict[str, Any] = {}
    if video_handler and hasattr(video_handler, "get_connection_health"):
        try:
            video_health = video_handler.get_connection_health() or {}
        except Exception:
            video_health = {}

    video_available = None
    if video_handler and hasattr(video_handler, "is_available"):
        try:
            video_available = bool(video_handler.is_available())
        except Exception:
            video_available = False

    runtime_run_id = None
    try:
        from classes.runtime_logging import get_runtime_log_manager

        runtime_run_id = get_runtime_log_manager().run_id
    except Exception:
        runtime_run_id = None

    backend_status = "running"
    if video_health.get("status") in {"unavailable", "error", "failed"}:
        backend_status = "degraded"

    return {
        "schema_version": 1,
        "source": "pixeagle_system_about",
        "version": PIXEAGLE_VERSION,
        "repository": {
            "name": "PixEagle",
            "url": PROJECT_REPOSITORY_URL,
            "docs_url": PROJECT_DOCS_URL,
        },
        "git": _get_git_metadata(),
        "backend": {
            "status": backend_status,
            "restart_pending": bool(getattr(owner, "_restart_pending", False)),
            "pid": pid,
            "memory_mb": memory_mb,
            "cpu_percent": cpu_percent,
            "video_available": video_available,
            "video_status": str(video_health.get("status") or "unknown"),
        },
        "runtime": {
            "uptime_seconds": uptime_seconds,
            "started_at": started_at,
            "python_version": sys.version.split()[0],
            "run_id": runtime_run_id,
        },
        "update": {
            "supported": False,
            "state": "not_checked",
            "available": None,
            "checked_at": None,
            "reason": SYSTEM_UPDATE_STATUS_REASON,
            "safe_workflow": SYSTEM_UPDATE_SAFE_WORKFLOW,
        },
        "claim_boundary": SYSTEM_ABOUT_CLAIM_BOUNDARY,
        "timestamp": time.time(),
    }


def get_legacy_runtime_status_snapshot(owner: Any) -> Dict[str, Any]:
    """Return the legacy flat runtime snapshot behind `/status`."""
    app_controller = getattr(owner, "app_controller", None)
    logger = getattr(owner, "logger", logging.getLogger(__name__))
    video_handler = getattr(owner, "video_handler", None)

    video_health = {}
    if video_handler and hasattr(video_handler, "get_connection_health"):
        video_health = video_handler.get_connection_health() or {}

    smart_tracker_runtime = None
    smart_tracker = getattr(app_controller, "smart_tracker", None)
    if smart_tracker and hasattr(smart_tracker, "get_runtime_info"):
        try:
            smart_tracker_runtime = smart_tracker.get_runtime_info()
        except Exception as runtime_error:
            logger.debug(
                "Could not fetch smart tracker runtime info: %s",
                runtime_error,
            )

    offboard_commander_status = None
    commander = getattr(app_controller, "offboard_commander", None)
    if commander and hasattr(commander, "get_status"):
        offboard_commander_status = commander.get_status()

    offboard_commander_failure = getattr(
        app_controller,
        "last_offboard_commander_failure",
        None,
    )

    mavlink_status = None
    mavlink_manager = getattr(app_controller, "mavlink_data_manager", None)
    if mavlink_manager and hasattr(mavlink_manager, "get_connection_status"):
        mavlink_status = mavlink_manager.get_connection_status()

    px4_connection_status = None
    px4_interface = getattr(app_controller, "px4_interface", None)
    if px4_interface and hasattr(px4_interface, "get_connection_status"):
        px4_connection_status = px4_interface.get_connection_status()

    return {
        "smart_mode_active": bool(getattr(app_controller, "smart_mode_active", False)),
        "tracking_started": bool(getattr(app_controller, "tracking_started", False)),
        "segmentation_active": bool(
            getattr(app_controller, "segmentation_active", False)
        ),
        "following_active": bool(getattr(app_controller, "following_active", False)),
        "offboard_commander": offboard_commander_status,
        "offboard_commander_failure": offboard_commander_failure,
        "px4_connection": px4_connection_status,
        "mavlink_telemetry": mavlink_status,
        "video_status": video_health.get("status", "unknown"),
        "smart_tracker_runtime": smart_tracker_runtime,
    }


def classify_following_commander_degradation(
    commander_status: Optional[Dict[str, Any]],
    following_active: bool,
) -> Optional[str]:
    """Return a fail-closed commander degradation reason for local following."""
    if not following_active:
        return None

    if isinstance(commander_status, dict):
        is_command_preview = (
            commander_status.get("command_publication_source")
            == "command_preview"
        )
        commander_health = str(
            commander_status.get("health_state")
            or commander_status.get("status")
            or ""
        ).lower()
        if commander_health in {"degraded", "failed", "failure", "error"}:
            return f"offboard_commander_{commander_health}"

        commander_running = commander_status.get("running")
        task_active = commander_status.get("task_active")
        last_intent_fresh = commander_status.get("last_intent_fresh")
        failsafe_defaults_active = commander_status.get("failsafe_defaults_active")
        if commander_running is not True:
            return (
                "offboard_commander_not_running"
                if commander_running is False
                else "offboard_commander_running_unknown"
            )
        if task_active is not True:
            return (
                "offboard_commander_task_inactive"
                if task_active is False
                else "offboard_commander_task_unknown"
            )
        if last_intent_fresh is not True:
            # A newly started local preview has no intent until the first
            # tracker frame is processed. That is a waiting state, not a
            # failed PX4 publisher. Once an intent existed, a missing intent
            # is still a real degraded/failsafe condition.
            if (
                is_command_preview
                and commander_status.get("accepted_intents") == 0
                and commander_status.get("failsafe_defaults_active") is False
            ):
                return None
            return (
                "offboard_commander_intent_stale"
                if last_intent_fresh is False
                else "offboard_commander_intent_freshness_unknown"
            )
        if failsafe_defaults_active is not False:
            return (
                "offboard_commander_failsafe_defaults_active"
                if failsafe_defaults_active is True
                else "offboard_commander_failsafe_defaults_unknown"
            )
        if commander_health in {"stopped", "offline", "disabled"}:
            return f"offboard_commander_{commander_health}"
        return None

    return "offboard_commander_unavailable"


def classify_inactive_following_commander_issue(
    commander_status: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Detect command publication that appears active after following stopped."""
    if not isinstance(commander_status, dict):
        return None

    commander_health = str(
        commander_status.get("health_state") or commander_status.get("status") or ""
    ).lower()
    if (
        commander_status.get("running") is True
        or commander_status.get("task_active") is True
        or commander_health in {"running", "active", "healthy"}
    ):
        return "offboard_commander_running_while_inactive"
    return None


def classify_runtime_status(
    legacy_status: Dict[str, Any],
) -> Tuple[str, str, Optional[str]]:
    """Classify process-local runtime state without broadening safety claims."""
    commander_failure = legacy_status.get("offboard_commander_failure")
    if commander_failure:
        return "degraded", "operator_attention", "offboard_commander_failure_present"

    commander_status = legacy_status.get("offboard_commander")
    following_active = bool(legacy_status.get("following_active"))
    commander_degradation = classify_following_commander_degradation(
        commander_status,
        following_active,
    )
    if commander_degradation:
        return "degraded", "operator_attention", commander_degradation

    if following_active:
        return "active", "following_active", None

    if (
        legacy_status.get("smart_mode_active")
        or legacy_status.get("tracking_started")
        or legacy_status.get("segmentation_active")
    ):
        return "active", "vision_active", None

    return "idle", "idle", None


def get_following_profile_status(
    owner: Any,
    following_active: bool,
) -> Tuple[Dict[str, Any], List[str]]:
    """Return current follower profile identity and local health issues."""
    app_controller = getattr(owner, "app_controller", None)
    follower_manager = getattr(app_controller, "follower", None)
    concrete_follower = (
        getattr(follower_manager, "follower", None)
        if follower_manager is not None
        else None
    )
    if concrete_follower is None and follower_manager is not None:
        concrete_follower = follower_manager

    configured_mode = getattr(Parameters, "FOLLOWER_MODE", None)
    current_mode = (
        getattr(follower_manager, "mode", None)
        if follower_manager is not None
        else configured_mode
    )
    health_issues = []
    profile_config = {}
    profile_valid = False
    if configured_mode:
        try:
            profile_config = SetpointHandler.get_profile_info(configured_mode)
            profile_valid = True
        except Exception as profile_error:
            health_issues.append(f"invalid_follower_profile:{configured_mode}")
            profile_config = {
                "error": str(profile_error),
            }

    if following_active and follower_manager is None:
        health_issues.append("follower_instance_unavailable")

    def _call_follower_method(method_name: str, default: Any = None) -> Any:
        if follower_manager is None:
            return default
        method = getattr(follower_manager, method_name, None)
        if not callable(method):
            return default
        try:
            value = method()
            return default if value is None else value
        except Exception as method_error:
            health_issues.append(f"{method_name}_unavailable:{method_error}")
            return default

    display_name = _call_follower_method(
        "get_display_name",
        profile_config.get("display_name") if profile_config else None,
    )
    control_type = _call_follower_method(
        "get_control_type",
        profile_config.get("control_type") if profile_config else None,
    )
    available_fields = _call_follower_method(
        "get_available_fields",
        (
            profile_config.get("required_fields", []) or []
        )
        if profile_config
        else [],
    )
    if not isinstance(available_fields, list):
        available_fields = list(available_fields) if available_fields else []

    return (
        {
            "configured_mode": configured_mode,
            "current_mode": current_mode,
            "profile_valid": profile_valid,
            "display_name": display_name,
            "control_type": control_type,
            "available_fields": available_fields,
            "manager_type": (
                follower_manager.__class__.__name__
                if follower_manager is not None
                else None
            ),
            "follower_type": (
                concrete_follower.__class__.__name__
                if concrete_follower is not None
                else None
            ),
            "follower_instance_present": follower_manager is not None,
        },
        health_issues,
    )


def get_following_command_publication_status(owner: Any) -> Dict[str, Any]:
    """Return publication status without overstating PX4 or preview evidence."""
    app_controller = getattr(owner, "app_controller", None)
    commander = getattr(app_controller, "offboard_commander", None)
    if commander and hasattr(commander, "get_status"):
        commander_status = commander.get_status()
    elif commander:
        commander_status = {"exists": True, "running": False}
    else:
        commander_status = None

    if not isinstance(commander_status, dict):
        commander_status = None

    configured_mode = get_configured_follower_execution_mode()
    following_active = bool(getattr(app_controller, "following_active", False))
    active_mode = getattr(app_controller, "following_execution_mode", None)
    execution_mode = normalize_follower_execution_mode(
        active_mode if following_active and active_mode else configured_mode
    )
    commander_source = (
        commander_status.get("command_publication_source")
        if commander_status is not None
        else None
    )
    source = (
        "command_preview"
        if commander_source == "command_preview"
        or (following_active and execution_mode == COMMAND_PREVIEW_EXECUTION_MODE)
        else "offboard_commander"
    )

    successful_publishes = (
        commander_status.get("successful_publishes")
        if commander_status is not None
        else None
    )
    local_successful_publish_observed = bool(
        commander_status
        and commander_status.get("running") is True
        and isinstance(successful_publishes, int)
        and successful_publishes > 0
    )
    commands_sent_to_px4 = bool(
        source == "offboard_commander"
        and commander_status is not None
        and commander_status.get("sends_mavsdk_commands") is True
        and isinstance(successful_publishes, int)
        and successful_publishes > 0
    )

    return {
        "source": source,
        "execution_mode": execution_mode,
        "exists": bool(
            commander_status.get("exists", True)
            if commander_status is not None
            else commander is not None
        ),
        "running": (
            commander_status.get("running") if commander_status is not None else None
        ),
        "task_active": (
            commander_status.get("task_active")
            if commander_status is not None
            else None
        ),
        "health_state": (
            commander_status.get("health_state")
            if commander_status is not None
            else None
        ),
        "command_publication_source": (
            commander_status.get("command_publication_source")
            if commander_status is not None
            else None
        ),
        "sends_mavsdk_commands": (
            commander_status.get("sends_mavsdk_commands")
            if commander_status is not None
            else None
        ),
        "commands_sent_to_px4": commands_sent_to_px4,
        "last_intent_fresh": (
            commander_status.get("last_intent_fresh")
            if commander_status is not None
            else None
        ),
        "failsafe_defaults_active": (
            commander_status.get("failsafe_defaults_active")
            if commander_status is not None
            else None
        ),
        "successful_publishes": successful_publishes,
        "failed_publishes": (
            commander_status.get("failed_publishes")
            if commander_status is not None
            else None
        ),
        "consecutive_failures": (
            commander_status.get("consecutive_failures")
            if commander_status is not None
            else None
        ),
        "local_successful_publish_observed": local_successful_publish_observed,
        "offboard_commander": commander_status,
    }


def get_command_preview_readiness(owner: Any) -> Dict[str, Any]:
    """Return the typed local replay preview readiness contract."""
    app_controller = getattr(owner, "app_controller", None)
    getter = getattr(app_controller, "_get_command_preview_readiness", None)
    if callable(getter):
        try:
            readiness = getter()
            if isinstance(readiness, dict):
                return readiness
        except Exception as exc:
            return {
                "execution_mode": COMMAND_PREVIEW_EXECUTION_MODE,
                "configured": False,
                "ready": False,
                "usable_for_command_preview": False,
                "autonomous_following_authorized": False,
                "commands_sent_to_px4": False,
                "safety_checks_enabled": None,
                "warnings": [],
                "reason": f"Command preview readiness unavailable: {exc}",
                "video_frame_status": {},
            }

    return {
        "execution_mode": get_configured_follower_execution_mode(),
        "configured": False,
        "ready": False,
        "usable_for_command_preview": False,
        "autonomous_following_authorized": False,
        "commands_sent_to_px4": False,
        "safety_checks_enabled": None,
        "warnings": [],
        "reason": "Command preview is not available in this runtime.",
        "video_frame_status": {},
    }


def get_following_status_snapshot(owner: Any) -> Dict[str, Any]:
    """Return the canonical typed following snapshot used by /api/v1."""
    app_controller = getattr(owner, "app_controller", None)
    following_active = bool(getattr(app_controller, "following_active", False))
    profile, health_issues = get_following_profile_status(owner, following_active)
    command_publication = get_following_command_publication_status(owner)
    command_preview = get_command_preview_readiness(owner)
    commander_status = command_publication.get("offboard_commander")

    reason = None
    commander_failure = getattr(
        app_controller,
        "last_offboard_commander_failure",
        None,
    )
    if commander_failure:
        reason = "offboard_commander_failure_present"
        health_issues.append(reason)

    if following_active and not profile["follower_instance_present"]:
        reason = reason or "follower_instance_unavailable"
    if not profile["profile_valid"]:
        reason = reason or "invalid_follower_profile"

    commander_degradation = classify_following_commander_degradation(
        commander_status,
        following_active,
    )
    if commander_degradation:
        reason = reason or commander_degradation

    inactive_commander_issue = classify_inactive_following_commander_issue(
        commander_status
    )
    if inactive_commander_issue and not following_active:
        reason = reason or inactive_commander_issue
        health_issues.append(inactive_commander_issue)

    if reason:
        following_status = "degraded"
        consumer_guidance = "operator_attention"
    elif following_active:
        following_status = "active"
        consumer_guidance = "following_active"
    else:
        following_status = "inactive"
        consumer_guidance = "inactive"

    return {
        "schema_version": 1,
        "source": "following_runtime",
        "status": following_status,
        "consumer_guidance": consumer_guidance,
        "following_active": following_active,
        "execution_mode": command_publication["execution_mode"],
        "commands_sent_to_px4": command_publication["commands_sent_to_px4"],
        "profile": profile,
        "command_preview": command_preview,
        "command_publication": command_publication,
        "health_issues": health_issues,
        "reason": reason,
        "claim_boundary": FOLLOWING_STATUS_CLAIM_BOUNDARY,
        "timestamp": time.time(),
    }


def get_active_following_setpoint_handler(owner: Any) -> Optional[Any]:
    """Return the active follower setpoint handler, if one is available."""
    app_controller = getattr(owner, "app_controller", None)
    follower_manager = getattr(app_controller, "follower", None)
    concrete_follower = (
        getattr(follower_manager, "follower", None)
        if follower_manager is not None
        else None
    )
    return (
        getattr(follower_manager, "setpoint_handler", None)
        or getattr(concrete_follower, "setpoint_handler", None)
    )


def get_legacy_follower_telemetry_snapshot(owner: Any) -> Dict[str, Any]:
    """Return the legacy follower telemetry payload without route wrapping."""
    telemetry_handler = getattr(owner, "telemetry_handler", None)
    if telemetry_handler and hasattr(telemetry_handler, "get_follower_data"):
        telemetry = telemetry_handler.get_follower_data()
    elif telemetry_handler and hasattr(telemetry_handler, "latest_follower_data"):
        telemetry = telemetry_handler.latest_follower_data
    else:
        telemetry = {}
    return telemetry if isinstance(telemetry, dict) else {}


def get_legacy_tracker_telemetry_snapshot(owner: Any) -> Dict[str, Any]:
    """Return the current tracker telemetry payload without route wrapping."""
    telemetry_handler = getattr(owner, "telemetry_handler", None)
    if telemetry_handler and hasattr(telemetry_handler, "get_tracker_data"):
        telemetry = telemetry_handler.get_tracker_data()
    elif telemetry_handler and hasattr(telemetry_handler, "latest_tracker_data"):
        telemetry = telemetry_handler.latest_tracker_data
    else:
        telemetry = {}
    return telemetry if isinstance(telemetry, dict) else {}


def coerce_mapping(value: Any) -> Dict[str, Any]:
    """Return a shallow dict when value is mapping-like, otherwise empty."""
    return value if isinstance(value, dict) else {}


def first_present(*values: Any) -> Any:
    """Return the first candidate that is not None without truth-value coercion."""
    for value in values:
        if value is not None:
            return value
    return None


def serialize_command_intent(intent: Any) -> Optional[Dict[str, Any]]:
    """Serialize a CommandIntent-like object for typed telemetry."""
    if intent is None:
        return None
    if isinstance(intent, dict):
        return intent

    fields = getattr(intent, "fields", None)
    return {
        "profile_name": getattr(intent, "profile_name", None),
        "control_type": getattr(intent, "control_type", None),
        "source": getattr(intent, "source", None),
        "reason": getattr(intent, "reason", None),
        "created_at_utc": getattr(intent, "created_at_utc", None),
        "fields": fields.copy() if isinstance(fields, dict) else fields,
    }


def get_circuit_breaker_snapshot(
    legacy_telemetry: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[bool], List[str]]:
    """Return follower circuit-breaker state for typed telemetry."""
    issues = []
    legacy_circuit_breaker = coerce_mapping(legacy_telemetry.get("circuit_breaker"))
    if legacy_circuit_breaker:
        active = legacy_circuit_breaker.get("active")
        return legacy_circuit_breaker, active if isinstance(active, bool) else None, issues

    if "circuit_breaker_active" in legacy_telemetry:
        active = bool(legacy_telemetry.get("circuit_breaker_active"))
        return {
            "active": active,
            "status": "SAFE_MODE" if active else "LIVE_MODE",
        }, active, issues

    if CIRCUIT_BREAKER_AVAILABLE:
        try:
            active = bool(FollowerCircuitBreaker.is_active())
            snapshot = {
                "active": active,
                "status": "SAFE_MODE" if active else "LIVE_MODE",
                "commands_allowed_by_circuit_breaker": not active,
                "commands_logged_only": active,
            }
            try:
                snapshot["statistics"] = FollowerCircuitBreaker.get_statistics()
            except Exception as stats_error:
                issues.append(f"circuit_breaker_statistics_unavailable:{stats_error}")
            return snapshot, active, issues
        except Exception as circuit_error:
            issues.append(f"circuit_breaker_status_unavailable:{circuit_error}")

    return {
        "active": True,
        "status": "SAFE_MODE",
        "error": "Circuit breaker status unavailable",
    }, True, issues


def get_following_telemetry_snapshot(owner: Any) -> Dict[str, Any]:
    """Return the canonical typed follower telemetry snapshot used by /api/v1."""
    status_snapshot = get_following_status_snapshot(owner)
    legacy_telemetry = get_legacy_follower_telemetry_snapshot(owner)
    setpoint_handler = get_active_following_setpoint_handler(owner)
    health_issues = list(status_snapshot.get("health_issues", []))

    fields = {}
    field_source = "unavailable"
    if setpoint_handler and hasattr(setpoint_handler, "get_fields"):
        try:
            fields = coerce_mapping(setpoint_handler.get_fields())
            field_source = "active_follower"
        except Exception as fields_error:
            health_issues.append(f"active_fields_unavailable:{fields_error}")

    if not fields:
        legacy_fields = coerce_mapping(legacy_telemetry.get("fields"))
        if legacy_fields:
            fields = legacy_fields
            field_source = "legacy_telemetry"

    if not fields:
        legacy_setpoints = coerce_mapping(legacy_telemetry.get("setpoints"))
        if legacy_setpoints:
            fields = legacy_setpoints
            field_source = "legacy_telemetry"

    if not fields and status_snapshot["profile"].get("available_fields"):
        field_source = "schema_profile"

    last_command_intent = legacy_telemetry.get("last_command_intent")
    if last_command_intent is None:
        follower = getattr(getattr(owner, "app_controller", None), "follower", None)
        getter = getattr(follower, "get_last_command_intent", None)
        if callable(getter):
            try:
                last_command_intent = getter()
            except Exception as intent_error:
                health_issues.append(f"last_command_intent_unavailable:{intent_error}")

    circuit_breaker, circuit_breaker_active, circuit_issues = (
        get_circuit_breaker_snapshot(legacy_telemetry)
    )
    health_issues.extend(circuit_issues)

    legacy_keys = sorted(str(key) for key in legacy_telemetry.keys())
    return {
        "schema_version": 1,
        "source": "following_telemetry",
        "status": status_snapshot["status"],
        "consumer_guidance": status_snapshot["consumer_guidance"],
        "following_active": status_snapshot["following_active"],
        "execution_mode": status_snapshot["execution_mode"],
        "commands_sent_to_px4": status_snapshot["commands_sent_to_px4"],
        "profile": status_snapshot["profile"],
        "command_preview": status_snapshot["command_preview"],
        "fields": fields,
        "field_source": field_source,
        "last_command_intent": serialize_command_intent(last_command_intent),
        "target_loss_handler": (
            coerce_mapping(legacy_telemetry.get("target_loss_handler")) or None
        ),
        "safety_systems": (
            coerce_mapping(legacy_telemetry.get("safety_systems")) or None
        ),
        "performance": coerce_mapping(legacy_telemetry.get("performance")) or None,
        "circuit_breaker": circuit_breaker,
        "circuit_breaker_active": circuit_breaker_active,
        "command_publication": status_snapshot["command_publication"],
        "flight_mode": legacy_telemetry.get("flight_mode"),
        "flight_mode_text": legacy_telemetry.get("flight_mode_text"),
        "is_offboard": legacy_telemetry.get("is_offboard"),
        "telemetry_enabled": bool(
            getattr(Parameters, "ENABLE_FOLLOWER_TELEMETRY", True)
        ),
        "legacy_payload_keys": legacy_keys,
        "health_issues": health_issues,
        "reason": status_snapshot["reason"],
        "claim_boundary": FOLLOWING_TELEMETRY_CLAIM_BOUNDARY,
        "timestamp": time.time(),
    }


def get_runtime_status_snapshot(owner: Any) -> Dict[str, Any]:
    """Return the canonical typed runtime snapshot used by /api/v1."""
    legacy_status = get_legacy_runtime_status_snapshot(owner)
    runtime_status, consumer_guidance, reason = classify_runtime_status(legacy_status)

    return {
        "schema_version": 1,
        "source": "pixeagle_runtime",
        "status": runtime_status,
        "consumer_guidance": consumer_guidance,
        "modes": {
            "smart_mode_active": legacy_status["smart_mode_active"],
            "tracking_started": legacy_status["tracking_started"],
            "segmentation_active": legacy_status["segmentation_active"],
            "following_active": legacy_status["following_active"],
        },
        "subsystems": {
            "video_status": legacy_status["video_status"],
            "offboard_commander": legacy_status["offboard_commander"],
            "offboard_commander_failure": legacy_status["offboard_commander_failure"],
            "px4_connection": legacy_status["px4_connection"],
            "mavlink_telemetry": legacy_status["mavlink_telemetry"],
            "smart_tracker_runtime": legacy_status["smart_tracker_runtime"],
        },
        "reason": reason,
        "claim_boundary": RUNTIME_STATUS_CLAIM_BOUNDARY,
        "timestamp": time.time(),
    }


def get_tracker_runtime_status_snapshot(
    owner: Any,
    tracker_output: Any = TRACKER_OUTPUT_UNSET,
) -> Dict[str, Any]:
    """Return the canonical tracker runtime snapshot used by API and guards."""
    app_controller = owner.app_controller
    configured_tracker = getattr(
        app_controller,
        "current_tracker_type",
        getattr(Parameters, "DEFAULT_TRACKING_ALGORITHM", None),
    )
    tracker_obj = getattr(app_controller, "tracker", None)
    tracker_type = tracker_obj.__class__.__name__ if tracker_obj else None
    smart_mode_active = bool(getattr(app_controller, "smart_mode_active", False))
    following_active = bool(getattr(app_controller, "following_active", False))

    if tracker_output is TRACKER_OUTPUT_UNSET:
        if not hasattr(app_controller, "get_tracker_output"):
            return tracker_runtime_unavailable_status(
                "Tracker output API not available.",
                configured_tracker=configured_tracker,
                tracker_type=tracker_type,
                smart_mode_active=smart_mode_active,
                following_active=following_active,
            )

        try:
            tracker_output = app_controller.get_tracker_output()
        except Exception as exc:
            return tracker_runtime_unavailable_status(
                f"Tracker output unavailable: {type(exc).__name__}: {exc}",
                configured_tracker=configured_tracker,
                tracker_type=tracker_type,
                smart_mode_active=smart_mode_active,
                following_active=following_active,
            )

    return evaluate_tracker_runtime_status(
        tracker_output,
        configured_tracker=configured_tracker,
        tracker_type=tracker_type,
        smart_mode_active=smart_mode_active,
        following_active=following_active,
    )


def _safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _normalize_catalog_entry(
    name: str,
    info: Dict[str, Any],
    *,
    source: str,
) -> Dict[str, Any]:
    ui_metadata = coerce_mapping(info.get("ui_metadata"))
    entry_name = str(name)
    display_name = (
        ui_metadata.get("display_name")
        or info.get("display_name")
        or info.get("name")
        or entry_name
    )
    factory_key = ui_metadata.get("factory_key") or info.get("factory_key")
    return {
        "name": entry_name,
        "display_name": display_name,
        "description": info.get("description"),
        "short_description": ui_metadata.get("short_description")
        or info.get("short_description"),
        "request_tracker_type": entry_name,
        "factory_key": factory_key,
        "data_type": info.get("data_type"),
        "smart_mode": bool(info.get("smart_mode", False)),
        "available": bool(info.get("available", True)),
        "unavailable_reason": info.get("unavailable_reason"),
        "source": source,
        "supported_schemas": _safe_list(info.get("supported_schemas")),
        "capabilities": _safe_list(info.get("capabilities")),
        "performance": coerce_mapping(info.get("performance")).copy(),
        "suitable_for": _safe_list(
            ui_metadata.get("suitable_for") or info.get("suitable_for")
        ),
        "icon": ui_metadata.get("icon") or info.get("icon"),
        "performance_category": ui_metadata.get("performance_category")
        or info.get("performance_category"),
    }


def _builtin_tracker_type_catalog() -> Dict[str, Dict[str, Any]]:
    catalog = {
        "CSRT": {
            "name": "CSRT",
            "display_name": "CSRT Tracker",
            "description": (
                "Channel and Spatial Reliability Tracker - Classical CV algorithm"
            ),
            "data_type": "POSITION_2D",
            "smart_mode": False,
            "suitable_for": [
                "Single target",
                "Stable tracking",
                "Classical computer vision",
            ],
        },
        "Gimbal": {
            "name": "Gimbal",
            "display_name": "Gimbal Tracker",
            "description": (
                "External gimbal input tracker - provider-specific angle data"
            ),
            "data_type": "GIMBAL_ANGLES",
            "smart_mode": False,
            "suitable_for": [
                "External gimbal",
                "Provider-normalized angles",
                "External observation integration",
            ],
        },
        "SmartTracker": {
            "name": "SmartTracker",
            "display_name": "Smart Tracker (AI)",
            "description": "AI-powered multi-backend smart tracking system",
            "data_type": "BBOX_CONFIDENCE",
            "smart_mode": True,
            "suitable_for": [
                "Multiple targets",
                "AI detection",
                "Association experiments",
            ],
            "available": AI_AVAILABLE,
            "unavailable_reason": (
                None
                if AI_AVAILABLE
                else "AI packages (ultralytics/torch) not installed"
            ),
        },
    }
    return {
        name: _normalize_catalog_entry(
            name,
            {
                **info,
                "available": info.get("available", True),
                "unavailable_reason": info.get("unavailable_reason"),
            },
            source="builtin_compatibility",
        )
        for name, info in catalog.items()
    }


def get_tracking_catalog_snapshot(owner: Any) -> Dict[str, Any]:
    """Return typed tracker catalog and current configuration metadata."""
    app_controller = owner.app_controller
    logger = getattr(owner, "logger", logging.getLogger(__name__))
    health_issues: List[str] = []
    ui_trackers: List[Dict[str, Any]] = []
    data_type_schemas: Dict[str, Dict[str, Any]] = {}

    try:
        from classes.schema_manager import get_schema_manager

        schema_manager = get_schema_manager()
        data_type_schemas = {
            str(name): coerce_mapping(schema).copy()
            for name, schema in coerce_mapping(
                getattr(schema_manager, "schemas", {})
            ).items()
        }
        classic_trackers = schema_manager.get_available_classic_trackers() or {}
        for name, info in coerce_mapping(classic_trackers).items():
            if isinstance(info, dict):
                ui_trackers.append(
                    _normalize_catalog_entry(
                        str(name),
                        info,
                        source="schema_manager",
                    )
                )
    except Exception as exc:
        logger.warning("Tracker schema-manager catalog unavailable: %s", exc)
        health_issues.append(f"schema_manager_unavailable: {type(exc).__name__}: {exc}")

    runtime_status = get_tracker_runtime_status_snapshot(owner)
    configured_tracker = getattr(
        app_controller,
        "current_tracker_type",
        getattr(Parameters, "DEFAULT_TRACKING_ALGORITHM", None),
    )
    tracker_obj = getattr(app_controller, "tracker", None)
    active_tracker = tracker_obj.__class__.__name__ if tracker_obj else None
    tracker_types = _builtin_tracker_type_catalog()

    if ui_trackers:
        status = "degraded" if health_issues else "available"
        consumer_guidance = "operator_attention" if health_issues else "selectable"
    elif health_issues:
        status = "degraded" if tracker_types else "unavailable"
        consumer_guidance = "schema_manager_unavailable"
    else:
        status = "unavailable"
        consumer_guidance = "operator_attention"
        health_issues.append("no_schema_manager_trackers_available")

    return {
        "schema_version": 1,
        "source": "tracking_catalog",
        "status": status,
        "consumer_guidance": consumer_guidance,
        "configured_tracker": configured_tracker,
        "active_tracker": active_tracker,
        "smart_mode_active": bool(getattr(app_controller, "smart_mode_active", False)),
        "tracking_started": bool(getattr(app_controller, "tracking_started", False)),
        "tracking_active": bool(
            tracker_obj is not None and getattr(app_controller, "tracking_active", False)
        ),
        "ui_trackers": ui_trackers,
        "tracker_types": tracker_types,
        "data_type_schemas": data_type_schemas,
        "total_trackers": len(ui_trackers),
        "runtime_status": runtime_status,
        "health_issues": health_issues,
        "claim_boundary": TRACKING_CATALOG_CLAIM_BOUNDARY,
        "timestamp": time.time(),
    }


def optional_float_list(
    value: Any,
    *,
    expected_length: Optional[int] = None,
    normalized: bool = False,
) -> Optional[List[float]]:
    """Return a JSON-friendly float list for tracker geometry arrays."""
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        if expected_length is not None and len(value) != expected_length:
            return None
        try:
            items = [float(item) for item in value]
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(item) for item in items):
            return None
        if normalized and any(item < 0.0 or item > 1.0 for item in items):
            return None
        return items
    return None


def sanitize_tracking_field_value(value: Any) -> Any:
    """Return JSON-safe tracker field values with non-finite numbers nulled."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(float(value)) else None
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return [sanitize_tracking_field_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): sanitized
            for key, item in value.items()
            if (sanitized := sanitize_tracking_field_value(item)) is not None
        }
    return value


def tracker_output_to_field_map(tracker_output: Any) -> Dict[str, Any]:
    """Serialize a TrackerOutput-like object into JSON-safe telemetry fields."""
    if tracker_output in (None, TRACKER_OUTPUT_UNSET):
        return {}

    if hasattr(tracker_output, "to_dict"):
        encoded = jsonable_encoder(tracker_output.to_dict())
    else:
        encoded = jsonable_encoder(getattr(tracker_output, "__dict__", {}))

    if not isinstance(encoded, dict):
        return {}

    return {
        key: sanitized
        for key, value in encoded.items()
        if (sanitized := sanitize_tracking_field_value(value)) is not None
    }


def position_3d_projection(value: Any) -> Optional[List[float]]:
    """Return the 2D projection of a 3D tracker coordinate if valid."""
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return list(value[:2])
    return None


def get_tracking_telemetry_snapshot(owner: Any) -> Dict[str, Any]:
    """Return typed tracker telemetry/geometry snapshot used by dashboard plots."""
    tracker_output = TRACKER_OUTPUT_UNSET
    app_controller = getattr(owner, "app_controller", None)
    if app_controller and hasattr(app_controller, "get_tracker_output"):
        try:
            tracker_output = app_controller.get_tracker_output()
        except Exception:
            tracker_output = TRACKER_OUTPUT_UNSET

    runtime_status = get_tracker_runtime_status_snapshot(
        owner,
        tracker_output=tracker_output,
    )
    output_fields = tracker_output_to_field_map(tracker_output)
    legacy_telemetry = (
        {} if output_fields else get_legacy_tracker_telemetry_snapshot(owner)
    )
    legacy_tracker_data = coerce_mapping(legacy_telemetry.get("tracker_data")).copy()
    tracker_data = output_fields.copy() or legacy_tracker_data.copy()

    if output_fields:
        center_candidate = first_present(
            output_fields.get("position_2d"),
            output_fields.get("center"),
            position_3d_projection(output_fields.get("position_3d")),
        )
        bbox_candidate = output_fields.get("normalized_bbox")
    else:
        center_candidate = first_present(
            legacy_telemetry.get("center"),
            legacy_tracker_data.get("position_2d"),
            legacy_tracker_data.get("center"),
            position_3d_projection(legacy_tracker_data.get("position_3d")),
        )
        bbox_candidate = first_present(
            legacy_telemetry.get("bounding_box"),
            legacy_tracker_data.get("normalized_bbox"),
        )

    center = optional_float_list(
        center_candidate,
        expected_length=2,
    )
    bounding_box = optional_float_list(
        bbox_candidate,
        expected_length=4,
        normalized=True,
    )

    if center is not None:
        tracker_data.setdefault("position_2d", center)
    if bounding_box is not None:
        tracker_data.setdefault("normalized_bbox", bounding_box)

    has_geometry = bool(center is not None or bounding_box is not None or tracker_data)
    if not has_geometry:
        field_source = "unavailable"
    elif output_fields:
        field_source = "tracker_output"
    else:
        field_source = "legacy_telemetry"

    active_tracking = bool(runtime_status["active_tracking"])
    legacy_tracker_started = legacy_telemetry.get("tracker_started")
    tracker_started = (
        legacy_tracker_started if isinstance(legacy_tracker_started, bool) else active_tracking
    )

    observed_at = time.time()
    measurement_timestamp = first_present(
        output_fields.get("last_measurement_timestamp"),
        output_fields.get("timestamp"),
        legacy_tracker_data.get("last_measurement_timestamp"),
        legacy_telemetry.get("timestamp"),
    )
    if (
        isinstance(measurement_timestamp, bool)
        or not isinstance(measurement_timestamp, (int, float))
        or not math.isfinite(float(measurement_timestamp))
        or float(measurement_timestamp) <= 0.0
    ):
        measurement_timestamp = observed_at

    return {
        "schema_version": 1,
        "source": "tracking_telemetry",
        "status": runtime_status["status"],
        "consumer_guidance": runtime_status["consumer_guidance"],
        "has_output": bool(runtime_status["has_output"]),
        "active_tracking": active_tracking,
        "tracking_active": active_tracking,
        "tracker_started": tracker_started,
        "usable_for_following": bool(runtime_status["usable_for_following"]),
        "data_is_stale": bool(runtime_status["data_is_stale"]),
        "center": center,
        "bounding_box": bounding_box,
        "fields": tracker_data.copy(),
        "tracker_data": tracker_data.copy(),
        "field_source": field_source,
        "runtime_status": runtime_status,
        "legacy_payload_keys": sorted(str(key) for key in legacy_telemetry.keys()),
        "reason": runtime_status.get("reason"),
        "claim_boundary": TRACKING_TELEMETRY_CLAIM_BOUNDARY,
        # `timestamp` remains the measurement/sample time used by plots. Poll
        # time is separate so stale geometry cannot look newly measured.
        "timestamp": float(measurement_timestamp),
        "observed_at": observed_at,
    }


def get_tracker_following_readiness(
    owner: Any,
    runtime_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate whether current tracker output can start autonomous following.

    The legacy command route and typed /api/v1 action both use this fail-closed
    guard before `connect_px4()` can activate Offboard.
    """
    normalized_runtime_status = (
        dict(runtime_status)
        if isinstance(runtime_status, dict)
        else get_tracker_runtime_status_snapshot(owner)
    )
    return evaluate_following_start_readiness(
        getattr(owner, "app_controller", None),
        runtime_status=normalized_runtime_status,
    )


__all__ = [
    "TRACKER_OUTPUT_UNSET",
    "classify_following_commander_degradation",
    "classify_inactive_following_commander_issue",
    "classify_runtime_status",
    "coerce_mapping",
    "first_present",
    "get_active_following_setpoint_handler",
    "get_circuit_breaker_snapshot",
    "get_following_command_publication_status",
    "get_command_preview_readiness",
    "get_following_profile_status",
    "get_following_status_snapshot",
    "get_following_telemetry_snapshot",
    "get_legacy_follower_telemetry_snapshot",
    "get_legacy_runtime_status_snapshot",
    "get_legacy_tracker_telemetry_snapshot",
    "get_runtime_status_snapshot",
    "get_tracker_following_readiness",
    "get_tracker_runtime_status_snapshot",
    "get_tracking_catalog_snapshot",
    "get_tracking_telemetry_snapshot",
    "optional_float_list",
    "position_3d_projection",
    "sanitize_tracking_field_value",
    "serialize_command_intent",
    "tracker_output_to_field_map",
]
