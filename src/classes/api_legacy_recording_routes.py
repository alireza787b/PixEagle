"""Legacy recording helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

import cv2
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse


def _recording_source_dimensions(
    handler: Any,
    *,
    default_fps: float | int = 30.0,
) -> tuple[float | int, int, int]:
    source_fps = default_fps
    source_w = 640
    source_h = 480
    video_handler = getattr(handler.app_controller, "video_handler", None)
    if video_handler:
        source_fps = getattr(video_handler, "fps", default_fps) or default_fps
        cap = getattr(video_handler, "cap", None)
        if cap:
            source_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
            source_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
    return source_fps, source_w, source_h


def _recording_unavailable_detail(handler: Any, fallback: str) -> str:
    app_controller = getattr(handler, "app_controller", None)
    getter = getattr(app_controller, "get_recording_unavailable_reason", None)
    if callable(getter):
        try:
            reason = getter()
        except Exception:
            reason = None
        if reason:
            return str(reason)[:500]
    return fallback


def _unavailable_storage_status(reason: Optional[str] = None) -> dict[str, Any]:
    status: dict[str, Any] = {
        "free_bytes": 0,
        "free_mb": 0,
        "free_gb": 0,
        "total_bytes": 0,
        "total_gb": 0,
        "used_percent": 0,
        "estimated_remaining_seconds": None,
        "warning_level": "error",
    }
    if reason:
        status["error"] = reason
    return status


def _get_recording_manager(handler: Any, detail: str = "Recording not available") -> Any:
    manager = getattr(handler.app_controller, "recording_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail=_recording_unavailable_detail(handler, detail),
        )
    return manager


async def start_recording(handler: Any) -> JSONResponse:
    """Start a new video recording."""
    try:
        manager = _get_recording_manager(
            handler,
            detail="Recording not available (ENABLE_RECORDING is false)",
        )
        source_fps, source_w, source_h = _recording_source_dimensions(handler)
        result = manager.start(source_fps, source_w, source_h)
        return JSONResponse(content={**result, "timestamp": time.time()})
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error starting recording: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def pause_recording(handler: Any) -> JSONResponse:
    """Pause the current recording."""
    try:
        manager = _get_recording_manager(handler)
        result = manager.pause()
        return JSONResponse(content={**result, "timestamp": time.time()})
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error pausing recording: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def resume_recording(handler: Any) -> JSONResponse:
    """Resume a paused recording."""
    try:
        manager = _get_recording_manager(handler)
        result = manager.resume()
        return JSONResponse(content={**result, "timestamp": time.time()})
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error resuming recording: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def stop_recording(handler: Any) -> JSONResponse:
    """Stop recording and finalize the file."""
    try:
        manager = _get_recording_manager(handler)
        result = manager.stop()
        return JSONResponse(content={**result, "timestamp": time.time()})
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error stopping recording: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_recording_status(handler: Any) -> JSONResponse:
    """Get current recording state and storage info."""
    try:
        manager = getattr(handler.app_controller, "recording_manager", None)
        storage = getattr(handler.app_controller, "storage_manager", None)
        unavailable_reason = None
        if manager is None:
            unavailable_reason = _recording_unavailable_detail(
                handler,
                "Recording subsystem unavailable",
            )
        storage_reason = unavailable_reason if storage is None else None
        return JSONResponse(
            content={
                "recording": manager.status if manager else {"state": "unavailable"},
                "storage": storage.status if storage else _unavailable_storage_status(storage_reason),
                "available": manager is not None,
                "storage_available": storage is not None,
                "reason": unavailable_reason,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting recording status: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def toggle_recording(handler: Any) -> JSONResponse:
    """Toggle recording on/off."""
    try:
        manager = _get_recording_manager(handler)
        if manager.is_active:
            result = manager.stop()
        else:
            source_fps, source_w, source_h = _recording_source_dimensions(
                handler,
                default_fps=30,
            )
            result = manager.start(source_fps, source_w, source_h)

        return JSONResponse(content={**result, "timestamp": time.time()})
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error toggling recording: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def list_recordings(handler: Any) -> JSONResponse:
    """List all recordings with metadata."""
    try:
        manager = getattr(handler.app_controller, "recording_manager", None)
        if manager is None:
            reason = _recording_unavailable_detail(
                handler,
                "Recording subsystem unavailable",
            )
            return JSONResponse(
                content={
                    "recordings": [],
                    "count": 0,
                    "available": False,
                    "reason": reason,
                    "timestamp": time.time(),
                }
            )
        recordings = manager.list_recordings()
        return JSONResponse(
            content={
                "recordings": recordings,
                "count": len(recordings),
                "available": True,
                "reason": None,
                "timestamp": time.time(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error listing recordings: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def download_recording(
    handler: Any,
    filename: str,
    request: Optional[Request] = None,
):
    """Download or stream a recording file with range request support."""
    try:
        manager = _get_recording_manager(handler)
        safe_name = Path(filename).name
        filepath = Path(manager._output_dir) / safe_name

        if not filepath.exists() or not filepath.is_file():
            raise HTTPException(status_code=404, detail=f"Recording not found: {safe_name}")

        file_size = filepath.stat().st_size
        suffix = filepath.suffix.lower()
        media_type = {
            ".mp4": "video/mp4",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
        }.get(suffix, "video/mp4")

        range_header = request.headers.get("range") if request else None
        if range_header:
            range_spec = range_header.replace("bytes=", "")
            parts = range_spec.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1

            def iter_range():
                with open(str(filepath), "rb") as recording_file:
                    recording_file.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = recording_file.read(min(65536, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            return StreamingResponse(
                iter_range(),
                status_code=206,
                media_type=media_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(length),
                },
            )

        return FileResponse(
            path=str(filepath),
            media_type=media_type,
            filename=safe_name,
            headers={"Accept-Ranges": "bytes"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error downloading recording: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def delete_recording_file(handler: Any, filename: str) -> JSONResponse:
    """Delete a recording file."""
    try:
        manager = _get_recording_manager(handler)
        result = manager.delete_recording(filename)
        if result["status"] == "error":
            status_code = 404 if "not found" in result["message"].lower() else 400
            raise HTTPException(status_code=status_code, detail=result["message"])
        return JSONResponse(content={**result, "timestamp": time.time()})
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error deleting recording: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_storage_status(handler: Any) -> JSONResponse:
    """Get disk space information."""
    try:
        storage = getattr(handler.app_controller, "storage_manager", None)
        reason = None
        if storage is None:
            reason = _recording_unavailable_detail(
                handler,
                "Storage monitoring subsystem unavailable",
            )
        return JSONResponse(
            content={
                "storage": storage.status if storage else _unavailable_storage_status(reason),
                "available": storage is not None,
                "reason": reason,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting storage status: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def set_recording_include_osd(handler: Any, enabled: str) -> JSONResponse:
    """Toggle whether OSD overlays are included in recordings."""
    try:
        manager = _get_recording_manager(handler)
        value = enabled.lower() in ("true", "1", "yes", "on")
        manager.set_include_osd(value)
        return JSONResponse(
            content={
                "status": "success",
                "include_osd": value,
                "message": f'OSD recording {"enabled" if value else "disabled"}',
                "timestamp": time.time(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error setting recording OSD: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
