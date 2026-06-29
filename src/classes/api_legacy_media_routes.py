"""Legacy media route helpers."""

from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from classes.parameters import Parameters


async def get_streaming_status(handler: Any) -> JSONResponse:
    """Report current legacy streaming method, quality, and config state."""
    quality_states = handler.quality_engine.get_all_states()
    webrtc_count = (
        len(handler.webrtc_manager.peer_connections)
        if hasattr(handler.webrtc_manager, "peer_connections")
        else 0
    )

    gstreamer_info = None
    if (
        hasattr(handler.app_controller, "gstreamer_handler")
        and handler.app_controller.gstreamer_handler
    ):
        gstreamer_info = handler.app_controller.gstreamer_handler.encoder_status

    pipeline_metrics = getattr(handler.app_controller, "_pipeline_metrics", {})

    return JSONResponse(
        content={
            "active_method": (
                "webrtc"
                if webrtc_count > 0
                else (
                    "websocket"
                    if handler.ws_connections
                    else "http" if handler.http_connections else "none"
                )
            ),
            "http_clients": len(handler.http_connections),
            "websocket_clients": len(handler.ws_connections),
            "webrtc_clients": webrtc_count,
            "adaptive_quality_enabled": getattr(
                Parameters,
                "ENABLE_ADAPTIVE_QUALITY",
                True,
            ),
            "quality_engine": quality_states,
            "gstreamer": gstreamer_info,
            "pipeline": pipeline_metrics,
            "config": {
                "stream_fps": Parameters.STREAM_FPS,
                "stream_width": Parameters.STREAM_WIDTH,
                "stream_height": Parameters.STREAM_HEIGHT,
                "min_quality": getattr(Parameters, "MIN_QUALITY", 20),
                "max_quality": getattr(Parameters, "MAX_QUALITY", 95),
                "default_protocol": getattr(Parameters, "DEFAULT_PROTOCOL", "auto"),
                "pipeline_mode": getattr(Parameters, "PIPELINE_MODE", "REALTIME"),
            },
            "timestamp": time.time(),
        }
    )


async def get_streaming_stats(handler: Any) -> JSONResponse:
    """Get current legacy streaming statistics."""
    ws_clients_info = []
    async with handler.connection_lock:
        for client in handler.ws_connections.values():
            ws_clients_info.append(
                {
                    "id": client.id,
                    "connected_duration": time.time() - client.connected_at,
                    "quality": client.quality,
                    "frame_drops": client.frame_drops,
                    "bandwidth_kbps": client.bandwidth_estimate * 8 / 1024,
                }
            )

    osd_pipeline_stats = {}
    if hasattr(handler.app_controller, "osd_pipeline"):
        try:
            osd_pipeline_stats = handler.app_controller.osd_pipeline.get_stats()
        except Exception as exc:
            handler.logger.debug(f"Could not read OSD pipeline stats: {exc}")

    return JSONResponse(
        content={
            "frames_sent": handler.stats["frames_sent"],
            "frames_dropped": handler.stats["frames_dropped"],
            "total_bandwidth_mb": handler.stats["total_bandwidth"] / 1024 / 1024,
            "http_connections": len(handler.http_connections),
            "websocket_connections": len(handler.ws_connections),
            "websocket_clients": ws_clients_info,
            "cache_size": len(handler.stream_optimizer.frame_cache),
            "uptime": (
                time.time()
                - (handler.server.started if handler.server else time.time())
            ),
            "osd_pipeline": osd_pipeline_stats,
        }
    )


async def get_video_health(handler: Any) -> JSONResponse:
    """Get legacy video subsystem health for degraded-mode observability."""
    try:
        health = (
            handler.video_handler.get_connection_health()
            if handler.video_handler
            else {"status": "unavailable"}
        )
        smart = getattr(handler.app_controller, "smart_tracker", None)
        obb_health = {
            "model_loaded": bool(smart and hasattr(smart, "model")),
            "adapter_initialized": bool(smart and hasattr(smart, "last_detections")),
            "geometry_utils_available": bool(
                smart and hasattr(smart, "current_geometry_mode")
            ),
            "geometry_mode": getattr(smart, "current_geometry_mode", None),
            "model_task": getattr(smart, "model_task", None),
        }
        return JSONResponse(
            content={
                "success": True,
                "video": health,
                "obb_pipeline": obb_health,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error in get_video_health: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def reconnect_video(handler: Any) -> JSONResponse:
    """Manually trigger a legacy video reconnection attempt."""
    try:
        if not handler.video_handler:
            raise HTTPException(status_code=503, detail="Video handler not initialized")

        success = handler.video_handler.force_recovery()
        health = handler.video_handler.get_connection_health()

        return JSONResponse(
            content={
                "success": success,
                "message": (
                    "Video reconnect succeeded"
                    if success
                    else "Video reconnect attempted but source still unavailable"
                ),
                "video": health,
                "timestamp": time.time(),
            },
            status_code=200 if success else 503,
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error in reconnect_video: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
