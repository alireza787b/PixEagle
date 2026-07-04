"""Typed /api/v1 runtime log route dispatchers."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import status

from classes.api_v1_paths import (
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


def _log_route_error(owner: Any, route_name: str, error: Exception) -> None:
    logger = getattr(owner, "logger", None)
    if logger is not None:
        logger.error("Error in %s: %s", route_name, error)


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


__all__ = [
    "get_log_session_entries",
    "get_log_sessions",
    "get_logs_status",
]
