"""Typed /api/v1 runtime log route dispatchers."""

from __future__ import annotations

from collections import deque
import json
import threading
import time
from typing import Any, Optional

from fastapi import status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from classes.api_v1_contracts import APIFrontendErrorReportRequest
from classes.api_v1_paths import (
    API_V1_LOGS_FRONTEND_ERRORS_PATH,
    API_V1_LOGS_SESSION_EXPORT_PATH,
    API_V1_LOGS_SESSION_PATH,
    API_V1_LOGS_SESSIONS_PATH,
    API_V1_LOGS_STATUS_PATH,
)
from classes.runtime_logging import (
    DEFAULT_COMPONENT,
    DEFAULT_READ_LIMIT,
    MAX_READ_LIMIT,
    get_runtime_log_manager,
)


FRONTEND_LOG_COMPONENT = "frontend"
FRONTEND_ERROR_RATE_LIMIT = 30
FRONTEND_ERROR_RATE_WINDOW_SECONDS = 60
FRONTEND_ERROR_RATE_MAX_KEYS = 4096
MAX_FRONTEND_CONTEXT_BYTES = 4096
_FRONTEND_ERROR_BUCKETS: dict[str, deque[float]] = {}
_FRONTEND_ERROR_BUCKET_LOCK = threading.RLock()


def _log_route_error(owner: Any, route_name: str, error: Exception) -> None:
    logger = getattr(owner, "logger", None)
    if logger is not None:
        logger.error("Error in %s: %s", route_name, error)


def _request_principal_key(request: Any) -> str:
    principal = getattr(getattr(request, "state", None), "api_principal", None)
    subject = getattr(principal, "subject", None) or "unknown"
    role = getattr(principal, "role", None) or "no-role"
    kind = getattr(getattr(principal, "kind", None), "value", None) or getattr(
        principal,
        "kind",
        "unknown",
    )
    return f"{kind}:{role}:{subject}"[:240]


def _frontend_error_rate_limited(key: str, now: float | None = None) -> bool:
    current = now if now is not None else time.monotonic()
    cutoff = current - FRONTEND_ERROR_RATE_WINDOW_SECONDS
    with _FRONTEND_ERROR_BUCKET_LOCK:
        if key not in _FRONTEND_ERROR_BUCKETS and (
            len(_FRONTEND_ERROR_BUCKETS) >= FRONTEND_ERROR_RATE_MAX_KEYS
        ):
            for bucket_key, bucket_value in list(_FRONTEND_ERROR_BUCKETS.items()):
                while bucket_value and bucket_value[0] < cutoff:
                    bucket_value.popleft()
                if not bucket_value:
                    _FRONTEND_ERROR_BUCKETS.pop(bucket_key, None)
            if len(_FRONTEND_ERROR_BUCKETS) >= FRONTEND_ERROR_RATE_MAX_KEYS:
                return True
        bucket = _FRONTEND_ERROR_BUCKETS.setdefault(key, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= FRONTEND_ERROR_RATE_LIMIT:
            return True
        bucket.append(current)
        return False


def _bounded_frontend_context(context: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(context, ensure_ascii=True, default=str)
    except (TypeError, ValueError) as exc:
        raise ValueError("frontend error context must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > MAX_FRONTEND_CONTEXT_BYTES:
        raise ValueError(
            f"frontend error context exceeds {MAX_FRONTEND_CONTEXT_BYTES} bytes"
        )
    return context


def reset_frontend_error_rate_limiter_for_tests() -> None:
    """Clear process-local frontend report buckets for focused tests."""
    with _FRONTEND_ERROR_BUCKET_LOCK:
        _FRONTEND_ERROR_BUCKETS.clear()


async def get_logs_status(owner: Any) -> Any:
    """Return runtime log subsystem status."""
    try:
        return get_runtime_log_manager().status()
    except Exception as error:
        _log_route_error(owner, "get_logs_status", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="logs_status_error",
            detail=str(error),
            path=API_V1_LOGS_STATUS_PATH,
        )


async def get_log_sessions(owner: Any, limit: int = 50) -> Any:
    """Return durable runtime log sessions, newest first."""
    try:
        safe_limit = max(1, min(int(limit or 50), 200))
        manager = get_runtime_log_manager()
        return {
            "active_run_id": manager.run_id,
            "sessions": manager.list_sessions(limit=safe_limit),
        }
    except (TypeError, ValueError) as error:
        return owner._api_v1_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="logs_query_invalid",
            detail=str(error),
            path=API_V1_LOGS_SESSIONS_PATH,
        )
    except Exception as error:
        _log_route_error(owner, "get_log_sessions", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="logs_sessions_error",
            detail=str(error),
            path=API_V1_LOGS_SESSIONS_PATH,
        )


async def get_log_session_entries(
    owner: Any,
    run_id: str,
    component: str = DEFAULT_COMPONENT,
    level: Optional[str] = None,
    limit: int = DEFAULT_READ_LIMIT,
    offset: int = 0,
    since: Optional[str] = None,
) -> Any:
    """Return filtered JSONL entries for one runtime log session."""
    try:
        safe_limit = max(1, min(int(limit or DEFAULT_READ_LIMIT), MAX_READ_LIMIT))
        safe_offset = max(0, int(offset or 0))
        normalized_level = str(level).upper() if level is not None else None
        entries = get_runtime_log_manager().read_entries(
            run_id,
            component=component,
            level=normalized_level,
            limit=safe_limit,
            offset=safe_offset,
            since=since,
        )
        if entries is None:
            return owner._api_v1_error_response(
                status_code=status.HTTP_404_NOT_FOUND,
                code="log_session_not_found",
                detail={
                    "run_id": run_id,
                    "component": component,
                },
                path=API_V1_LOGS_SESSION_PATH,
            )
        return {
            "run_id": run_id,
            "component": component,
            "count": len(entries),
            "limit": safe_limit,
            "offset": safe_offset,
            "level": normalized_level,
            "since": since,
            "entries": entries,
        }
    except (TypeError, ValueError) as error:
        return owner._api_v1_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="logs_query_invalid",
            detail=str(error),
            path=API_V1_LOGS_SESSION_PATH,
        )
    except Exception as error:
        _log_route_error(owner, "get_log_session_entries", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="log_session_read_error",
            detail=str(error),
            path=API_V1_LOGS_SESSION_PATH,
        )


async def export_log_session_bundle(owner: Any, run_id: str) -> Any:
    """Return a sanitized tar.gz evidence bundle for one runtime log session."""
    try:
        export = get_runtime_log_manager().export_session_bundle(run_id)
        if export is None:
            return owner._api_v1_error_response(
                status_code=status.HTTP_404_NOT_FOUND,
                code="log_session_not_found",
                detail={"run_id": run_id},
                path=API_V1_LOGS_SESSION_EXPORT_PATH,
            )
        return FileResponse(
            path=str(export.path),
            media_type=export.media_type,
            filename=export.filename,
            background=BackgroundTask(export.cleanup),
            headers={
                "Cache-Control": "no-store",
                "X-PixEagle-Run-ID": export.run_id,
                "X-PixEagle-Log-Export-Sha256": export.sha256,
                "X-PixEagle-Log-Export-Size": str(export.size_bytes),
                "X-PixEagle-Claim-Boundary": export.claim_boundary,
            },
        )
    except (TypeError, ValueError) as error:
        return owner._api_v1_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="logs_query_invalid",
            detail=str(error),
            path=API_V1_LOGS_SESSION_EXPORT_PATH,
        )
    except Exception as error:
        _log_route_error(owner, "export_log_session_bundle", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="log_session_export_error",
            detail=str(error),
            path=API_V1_LOGS_SESSION_EXPORT_PATH,
        )


async def record_frontend_error(
    owner: Any,
    request: Any,
    report: APIFrontendErrorReportRequest,
) -> Any:
    """Append one bounded browser runtime error report to the active session."""
    try:
        rate_key = _request_principal_key(request)
        if _frontend_error_rate_limited(rate_key):
            return owner._api_v1_error_response(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="frontend_error_rate_limited",
                detail={
                    "limit": FRONTEND_ERROR_RATE_LIMIT,
                    "window_seconds": FRONTEND_ERROR_RATE_WINDOW_SECONDS,
                },
                path=API_V1_LOGS_FRONTEND_ERRORS_PATH,
            )

        manager = get_runtime_log_manager()
        extra = {
            "event": "frontend_error",
            "source": report.source,
            "name": report.name,
            "stack": report.stack,
            "url": report.url,
            "route": report.route,
            "user_agent": report.user_agent,
            "context": _bounded_frontend_context(report.context),
        }
        entry = manager.append_component_message(
            FRONTEND_LOG_COMPONENT,
            report.message,
            level=report.level,
            stream="browser",
            source=report.source,
            extra=extra,
        )
        return {
            "accepted": True,
            "run_id": manager.run_id,
            "component": FRONTEND_LOG_COMPONENT,
            "entry_ts": entry["ts"],
        }
    except (TypeError, ValueError) as error:
        return owner._api_v1_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="frontend_error_report_invalid",
            detail=str(error),
            path=API_V1_LOGS_FRONTEND_ERRORS_PATH,
        )
    except Exception as error:
        _log_route_error(owner, "record_frontend_error", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="frontend_error_report_failed",
            detail=str(error),
            path=API_V1_LOGS_FRONTEND_ERRORS_PATH,
        )


__all__ = [
    "export_log_session_bundle",
    "get_log_session_entries",
    "get_log_sessions",
    "get_logs_status",
    "record_frontend_error",
    "reset_frontend_error_rate_limiter_for_tests",
]
