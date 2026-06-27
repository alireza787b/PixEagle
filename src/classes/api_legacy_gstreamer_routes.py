"""Legacy GStreamer route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from classes.parameters import Parameters


def _new_gstreamer_handler() -> Any:
    from classes.gstreamer_handler import GStreamerHandler

    return GStreamerHandler()


def _is_gstreamer_active(handler: Any | None) -> bool:
    return (
        handler is not None
        and handler.out is not None
        and handler.out.isOpened()
    )


def _qgc_setup_hint() -> str:
    return (
        "In QGC: Application Settings > Video > UDP Video Stream, port "
        + str(int(getattr(Parameters, "GSTREAMER_PORT", 5600)))
    )


async def get_gstreamer_status(handler: Any) -> JSONResponse:
    """Get GStreamer QGC output stream status and configuration."""
    try:
        gstreamer_handler = getattr(handler.app_controller, "gstreamer_handler", None)
        is_active = _is_gstreamer_active(gstreamer_handler)

        return JSONResponse(
            content={
                "available": True,
                "enabled": is_active,
                "config_enabled": bool(
                    getattr(Parameters, "ENABLE_GSTREAMER_STREAM", False)
                ),
                "encoder": (
                    gstreamer_handler.encoder_info.encoder
                    if gstreamer_handler
                    else None
                ),
                "hardware_accelerated": (
                    gstreamer_handler.encoder_info.hardware
                    if gstreamer_handler
                    else False
                ),
                "host": str(getattr(Parameters, "GSTREAMER_HOST", "127.0.0.1")),
                "port": int(getattr(Parameters, "GSTREAMER_PORT", 5600)),
                "resolution": (
                    f"{getattr(Parameters, 'GSTREAMER_WIDTH', 1280)}x"
                    f"{getattr(Parameters, 'GSTREAMER_HEIGHT', 720)}"
                ),
                "framerate": int(getattr(Parameters, "GSTREAMER_FRAMERATE", 15)),
                "bitrate_kbps": int(getattr(Parameters, "GSTREAMER_BITRATE", 2000)),
                "qgc_setup_hint": _qgc_setup_hint(),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting GStreamer status: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def toggle_gstreamer(handler: Any) -> JSONResponse:
    """Toggle GStreamer QGC output stream on or off at runtime."""
    try:
        gstreamer_handler = getattr(handler.app_controller, "gstreamer_handler", None)
        was_active = _is_gstreamer_active(gstreamer_handler)

        if was_active:
            gstreamer_handler.release()
            handler.logger.info("GStreamer QGC output stopped via API")
            Parameters.ENABLE_GSTREAMER_STREAM = False
            return JSONResponse(
                content={
                    "status": "success",
                    "enabled": False,
                    "action": "stopped",
                    "message": "GStreamer QGC output stream stopped",
                    "timestamp": time.time(),
                }
            )

        if gstreamer_handler is None:
            gstreamer_handler = _new_gstreamer_handler()
            handler.app_controller.gstreamer_handler = gstreamer_handler
        gstreamer_handler.initialize_stream()
        Parameters.ENABLE_GSTREAMER_STREAM = True

        is_open = (
            gstreamer_handler.out is not None
            and gstreamer_handler.out.isOpened()
        )
        if is_open:
            handler.logger.info(
                f"GStreamer QGC output started via API "
                f"(encoder={gstreamer_handler.encoder_info.encoder}, "
                f"hardware={'yes' if gstreamer_handler.encoder_info.hardware else 'no'})"
            )
            return JSONResponse(
                content={
                    "status": "success",
                    "enabled": True,
                    "action": "started",
                    "encoder": gstreamer_handler.encoder_info.encoder,
                    "hardware_accelerated": gstreamer_handler.encoder_info.hardware,
                    "message": (
                        "GStreamer QGC output started "
                        f"({gstreamer_handler.encoder_info.encoder})"
                    ),
                    "qgc_setup_hint": _qgc_setup_hint(),
                    "timestamp": time.time(),
                }
            )

        handler.logger.warning("GStreamer pipeline failed to open")
        Parameters.ENABLE_GSTREAMER_STREAM = False
        return JSONResponse(
            content={
                "status": "error",
                "enabled": False,
                "action": "failed",
                "message": (
                    "GStreamer pipeline failed to open. "
                    "Check GStreamer installation."
                ),
                "timestamp": time.time(),
            },
            status_code=500,
        )

    except Exception as exc:
        handler.logger.error(f"Error toggling GStreamer: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
