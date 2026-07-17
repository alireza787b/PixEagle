"""Legacy OSD route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from classes.parameters import Parameters


async def get_osd_status(handler: Any) -> JSONResponse:
    """Get current OSD status and configuration."""
    try:
        if not hasattr(handler.app_controller, "osd_handler"):
            return JSONResponse(
                content={
                    "available": False,
                    "error": "OSD system not available",
                }
            )

        osd_handler = handler.app_controller.osd_handler

        is_enabled = (
            osd_handler.is_enabled()
            if hasattr(osd_handler, "is_enabled")
            else Parameters.OSD_ENABLED
        )

        perf_stats = {}
        if hasattr(osd_handler, "get_performance_stats"):
            perf_stats = osd_handler.get_performance_stats()

        pipeline_stats = {}
        if hasattr(handler.app_controller, "osd_pipeline"):
            pipeline_stats = handler.app_controller.osd_pipeline.get_stats()

        current_preset = getattr(Parameters, "OSD_PRESET", "professional")

        mgr = getattr(handler.app_controller, "osd_mode_manager", None)
        color_mode = mgr.color_mode if mgr else "day"

        return JSONResponse(
            content={
                "available": True,
                "enabled": is_enabled,
                "status": "active" if is_enabled else "disabled",
                "configuration": {
                    "enabled_parameter": Parameters.OSD_ENABLED,
                    "current_preset": current_preset,
                    "color_mode": color_mode,
                    "presets_location": "configs/osd_presets/",
                    "pipeline_mode": getattr(
                        Parameters,
                        "OSD_PIPELINE_MODE",
                        "layered_realtime",
                    ),
                    "target_resolution": getattr(
                        Parameters,
                        "OSD_TARGET_LAYER_RESOLUTION",
                        "stream",
                    ),
                    "dynamic_fps": getattr(Parameters, "OSD_DYNAMIC_FPS", 10),
                    "datetime_fps": getattr(Parameters, "OSD_DATETIME_FPS", 1),
                },
                "performance": perf_stats,
                "pipeline": pipeline_stats,
                "message": (
                    "OSD overlay active on video feed"
                    if is_enabled
                    else "OSD overlay disabled"
                ),
                "timestamp": time.time(),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error getting OSD status: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def toggle_osd(handler: Any) -> JSONResponse:
    """Toggle OSD on/off."""
    try:
        if not hasattr(handler.app_controller, "osd_handler"):
            raise HTTPException(status_code=503, detail="OSD system not available")

        osd_handler = handler.app_controller.osd_handler

        old_state = (
            osd_handler.is_enabled()
            if hasattr(osd_handler, "is_enabled")
            else Parameters.OSD_ENABLED
        )

        new_state = not old_state
        if hasattr(osd_handler, "set_enabled"):
            osd_handler.set_enabled(new_state)
        if hasattr(handler.app_controller, "osd_pipeline"):
            handler.app_controller.osd_pipeline.invalidate_cache("toggle_osd")

        Parameters.OSD_ENABLED = new_state

        handler.logger.info(f"OSD {'enabled' if new_state else 'disabled'} via API")

        return JSONResponse(
            content={
                "status": "success",
                "action": "enabled" if new_state else "disabled",
                "enabled": new_state,
                "old_state": old_state,
                "new_state": new_state,
                "message": f"OSD overlay {'enabled' if new_state else 'disabled'}",
                "timestamp": time.time(),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error toggling OSD: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_osd_presets(handler: Any) -> JSONResponse:
    """Get available OSD presets."""
    try:
        presets_dir = Path("configs/osd_presets")

        if not presets_dir.exists():
            return JSONResponse(
                content={
                    "available": False,
                    "error": "OSD presets directory not found",
                    "presets": [],
                }
            )

        presets = []
        for preset_file in presets_dir.glob("*.yaml"):
            if preset_file.name.lower() != "readme.md":
                presets.append(preset_file.stem)

        presets.sort(key=lambda value: (value != "professional", value))

        current_preset = (
            getattr(Parameters, "OSD_PRESET", "professional")
            if hasattr(Parameters, "OSD_PRESET")
            else "professional"
        )

        return JSONResponse(
            content={
                "available": True,
                "presets": presets,
                "current": current_preset,
                "presets_directory": str(presets_dir),
                "total_presets": len(presets),
                "timestamp": time.time(),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error getting OSD presets: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def load_osd_preset(handler: Any, preset_name: str) -> JSONResponse:
    """Load an OSD preset configuration."""
    try:
        allowed_chars = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        if not all(char in allowed_chars for char in preset_name):
            raise HTTPException(status_code=400, detail="Invalid preset name")

        preset_path = Path(f"configs/osd_presets/{preset_name}.yaml")

        if not preset_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Preset '{preset_name}' not found",
            )

        with preset_path.open("r", encoding="utf-8") as preset_file:
            preset_config = yaml.safe_load(preset_file)

        element_count = len(preset_config.get("ELEMENTS", {}))

        old_preset = getattr(Parameters, "OSD_PRESET", "professional")
        Parameters.OSD_PRESET = preset_name

        if hasattr(handler.app_controller, "osd_handler"):
            try:
                from classes.osd_renderer import OSDRenderer

                handler.app_controller.osd_handler.renderer = OSDRenderer(
                    handler.app_controller
                )
                if hasattr(handler.app_controller, "osd_pipeline"):
                    handler.app_controller.osd_pipeline.invalidate_cache(
                        "preset_switch"
                    )
                handler.logger.info(
                    f"OSD renderer reinitialized with preset '{preset_name}'"
                )
            except Exception as exc:
                handler.logger.error(f"Failed to reinitialize OSD renderer: {exc}")

        handler.logger.info(
            f"OSD preset switched: '{old_preset}' \u2192 '{preset_name}'"
        )

        return JSONResponse(
            content={
                "status": "success",
                "action": "preset_loaded",
                "old_preset": old_preset,
                "new_preset": preset_name,
                "preset_file": str(preset_path),
                "configuration_updated": True,
                "element_count": element_count,
                "message": (
                    f'OSD preset switched to "{preset_name}" and applied immediately.'
                ),
                "requires_restart": False,
                "timestamp": time.time(),
            }
        )

    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error loading OSD preset: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_osd_color_modes(handler: Any) -> JSONResponse:
    """Get available OSD color modes and current selection."""
    try:
        mgr = getattr(handler.app_controller, "osd_mode_manager", None)
        if mgr is None:
            raise HTTPException(
                status_code=503,
                detail="OSD mode manager not available",
            )

        from classes.osd_colors import VALID_COLOR_MODES

        return JSONResponse(
            content={
                "available_modes": VALID_COLOR_MODES,
                "current": mgr.color_mode,
                "timestamp": time.time(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error getting OSD color modes: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def set_osd_color_mode(handler: Any, mode: str) -> JSONResponse:
    """Switch OSD color mode."""
    try:
        mgr = getattr(handler.app_controller, "osd_mode_manager", None)
        if mgr is None:
            raise HTTPException(
                status_code=503,
                detail="OSD mode manager not available",
            )

        from classes.osd_colors import VALID_COLOR_MODES

        if mode not in VALID_COLOR_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid color mode '{mode}'. Valid: {VALID_COLOR_MODES}",
            )

        old_mode = mgr.color_mode
        success = mgr.switch_color_mode(mode)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to switch color mode")

        handler.logger.info(f"OSD color mode switched: '{old_mode}' -> '{mode}'")

        return JSONResponse(
            content={
                "status": "success",
                "old_mode": old_mode,
                "new_mode": mode,
                "message": f"Color mode switched to '{mode}'",
                "timestamp": time.time(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error setting OSD color mode: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_osd_modes(handler: Any) -> JSONResponse:
    """Get full OSD mode status."""
    try:
        mgr = getattr(handler.app_controller, "osd_mode_manager", None)
        if mgr is None:
            raise HTTPException(
                status_code=503,
                detail="OSD mode manager not available",
            )

        return JSONResponse(
            content={
                "status": "success",
                **mgr.get_status(),
                "timestamp": time.time(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error getting OSD modes: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
