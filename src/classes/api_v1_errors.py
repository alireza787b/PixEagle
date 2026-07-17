"""Typed /api/v1 error envelope helpers."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi.responses import JSONResponse

from classes.api_v1_contracts import APIErrorResponse
from classes.api_v1_paths import (
    SITL_TRACKER_OUTPUT_INJECTION_PATH,
    api_v1_request_id_prefix,
)


def build_api_v1_error_response(
    *,
    status_code: int,
    code: str,
    detail: Any,
    path: str = SITL_TRACKER_OUTPUT_INJECTION_PATH,
) -> JSONResponse:
    """Build a typed /api/v1 error envelope without touching runtime state."""
    request_id_prefix = api_v1_request_id_prefix(path)
    payload = APIErrorResponse(
        error=code,
        code=code,
        detail=detail,
        timestamp=int(time.time() * 1000),
        path=path,
        request_id=f"{request_id_prefix}-{uuid.uuid4()}",
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump() if hasattr(payload, "model_dump") else payload.dict(),
    )


def build_sitl_error_response(
    *,
    status_code: int,
    code: str,
    detail: Any,
    path: str = SITL_TRACKER_OUTPUT_INJECTION_PATH,
) -> JSONResponse:
    """Build the same typed envelope for validation-only SITL routes."""
    return build_api_v1_error_response(
        status_code=status_code,
        code=code,
        detail=detail,
        path=path,
    )


__all__ = [
    "build_api_v1_error_response",
    "build_sitl_error_response",
]
