"""Legacy detection-model route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.api_legacy_config_routes import (
    _assert_audit_source_unchanged,
    _config_mutation_transaction,
    _log_config_audit,
    _persist_config,
    _publish_runtime_config,
)
from classes.parameters import Parameters


def resolve_runtime_model_name(runtime_model_path: Optional[str]) -> Optional[str]:
    """Map runtime model paths to UI-compatible model filenames."""
    if not runtime_model_path:
        return None

    runtime_model_name = Path(runtime_model_path).name
    if runtime_model_name.endswith("_ncnn_model"):
        sibling_pt = Path(runtime_model_path).with_name(
            f"{runtime_model_name[:-len('_ncnn_model')]}.pt"
        )
        return sibling_pt.name if sibling_pt.exists() else runtime_model_name

    return runtime_model_name


def get_smart_tracker_runtime_context(
    handler: Any,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Return active runtime model filename and metadata when SmartTracker runs."""
    current_model = None
    smart_tracker_runtime = None

    smart_tracker = getattr(handler.app_controller, "smart_tracker", None)
    if smart_tracker is None:
        return current_model, smart_tracker_runtime

    if hasattr(smart_tracker, "get_runtime_info"):
        try:
            smart_tracker_runtime = smart_tracker.get_runtime_info()
            runtime_model_path = smart_tracker_runtime.get("model_path")
            current_model = resolve_runtime_model_name(runtime_model_path)
        except Exception as runtime_error:
            handler.logger.debug(
                f"Could not read smart tracker runtime info: {runtime_error}"
            )

    if hasattr(smart_tracker, "model") and not current_model:
        try:
            model_file = getattr(smart_tracker.model, "ckpt_path", None)
            if model_file:
                current_model = Path(model_file).name
        except Exception as model_error:
            handler.logger.debug(f"Could not determine current model: {model_error}")

    return current_model, smart_tracker_runtime


def get_configured_yolo_models(
    handler: Any,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return configured default model filenames from Parameters."""
    configured_model = None
    configured_gpu_model = None
    configured_cpu_model = None

    try:
        gpu_model_path = Parameters.SmartTracker.get(
            "SMART_TRACKER_GPU_MODEL_PATH",
            "models/yolo26n.pt",
        )
        cpu_model_path = Parameters.SmartTracker.get(
            "SMART_TRACKER_CPU_MODEL_PATH",
            "models/yolo26n_ncnn_model",
        )
        configured_gpu_model = Path(gpu_model_path).name
        configured_cpu_model = Path(cpu_model_path).name

        use_gpu = Parameters.SmartTracker.get("SMART_TRACKER_USE_GPU", True)
        configured_model = configured_gpu_model if use_gpu else configured_cpu_model
    except Exception as config_error:
        handler.logger.debug(f"Could not determine configured model: {config_error}")

    return configured_model, configured_gpu_model, configured_cpu_model


def resolve_model_entry(
    model_manager: Any,
    models: Dict[str, Dict[str, Any]],
    model_identifier: Optional[str],
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Resolve a discovered model entry from model id, filename, or path."""
    normalized_model_id = model_manager.normalize_model_id(model_identifier)
    if normalized_model_id and normalized_model_id in models:
        return normalized_model_id, models[normalized_model_id]

    if model_identifier:
        model_name = Path(str(model_identifier)).name
        for candidate_id, candidate_info in models.items():
            candidate_path = str(candidate_info.get("path", ""))
            if candidate_path.endswith(model_name):
                return candidate_id, candidate_info

    return None, None


def build_active_model_summary(
    model_id: Optional[str],
    model_info: Optional[Dict[str, Any]],
    runtime: Optional[Dict[str, Any]],
    source: str,
    label_preview_limit: int = 8,
) -> Optional[Dict[str, Any]]:
    """Build summary payload for compact UI display."""
    if not model_id or not model_info:
        return None

    labels = [str(label) for label in (model_info.get("class_names") or [])]
    num_labels = int(model_info.get("num_classes") or len(labels))
    label_preview = labels[: max(label_preview_limit, 0)]
    runtime = runtime or {}

    return {
        "model_id": model_id,
        "model_name": model_info.get("name") or model_id,
        "model_path": model_info.get("path"),
        "task": runtime.get("model_task") or model_info.get("task") or "unknown",
        "geometry_mode": (
            runtime.get("geometry_mode")
            or model_info.get("output_geometry")
            or "aabb"
        ),
        "backend": runtime.get("backend"),
        "device": runtime.get("effective_device"),
        "fallback_occurred": bool(runtime.get("fallback_occurred", False)),
        "fallback_reason": runtime.get("fallback_reason"),
        "num_labels": num_labels,
        "label_preview": label_preview,
        "has_more_labels": len(labels) > len(label_preview),
        "is_custom": bool(model_info.get("is_custom", False)),
        "has_ncnn": bool(model_info.get("has_ncnn", False)),
        "size_mb": model_info.get("size_mb"),
        "smarttracker_supported": bool(model_info.get("smarttracker_supported", True)),
        "compatibility_notes": model_info.get("compatibility_notes", []),
        "source": source,
    }


async def get_models(handler: Any, request: Optional[Request] = None) -> JSONResponse:
    """Get list of available detection models."""
    try:
        force_rescan = False
        if request is not None:
            query_params = dict(request.query_params)
            force_rescan = (
                (query_params.get("force_rescan") or "false").strip().lower()
                == "true"
            )

        models = handler.model_manager.discover_models(force_rescan=force_rescan)

        current_model, smart_tracker_runtime = get_smart_tracker_runtime_context(handler)
        configured_model, configured_gpu_model, configured_cpu_model = (
            get_configured_yolo_models(handler)
        )

        active_model_source = (
            "runtime" if current_model else ("configured" if configured_model else "none")
        )
        active_model_identifier = current_model or configured_model
        active_model_id, active_model_info = resolve_model_entry(
            handler.model_manager,
            models,
            active_model_identifier,
        )
        active_model_summary = build_active_model_summary(
            active_model_id,
            active_model_info,
            smart_tracker_runtime if active_model_source == "runtime" else None,
            source=active_model_source,
        )

        return JSONResponse(
            content={
                "status": "success",
                "models": models,
                "current_model": current_model,
                "configured_model": configured_model,
                "configured_gpu_model": configured_gpu_model,
                "configured_cpu_model": configured_cpu_model,
                "runtime": smart_tracker_runtime,
                "total_count": len(models),
                "active_model_id": active_model_id,
                "active_model_source": active_model_source,
                "active_model_summary": active_model_summary,
                "schema_version": "1.0",
            }
        )

    except Exception as e:
        handler.logger.error(f"Error getting Detection models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_active_model(handler: Any) -> JSONResponse:
    """Get compact, UI-focused metadata for the active/configured model."""
    try:
        models = handler.model_manager.discover_models(force_rescan=False)
        current_model, smart_tracker_runtime = get_smart_tracker_runtime_context(handler)
        configured_model, configured_gpu_model, configured_cpu_model = (
            get_configured_yolo_models(handler)
        )

        active_model_source = (
            "runtime" if current_model else ("configured" if configured_model else "none")
        )
        active_model_identifier = current_model or configured_model
        active_model_id, active_model_info = resolve_model_entry(
            handler.model_manager,
            models,
            active_model_identifier,
        )

        active_model_summary = build_active_model_summary(
            active_model_id,
            active_model_info,
            smart_tracker_runtime if active_model_source == "runtime" else None,
            source=active_model_source,
        )

        return JSONResponse(
            content={
                "status": "success",
                "available": bool(active_model_summary),
                "active_model_source": active_model_source,
                "active_model_summary": active_model_summary,
                "runtime": smart_tracker_runtime,
                "configured_model": configured_model,
                "configured_gpu_model": configured_gpu_model,
                "configured_cpu_model": configured_cpu_model,
                "schema_version": "1.0",
                "timestamp": time.time(),
            }
        )
    except Exception as e:
        handler.logger.error(f"Error getting active Detection model metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_model_labels(
    handler: Any,
    model_id: str,
    request: Request,
) -> JSONResponse:
    """Get paginated/searchable labels for a specific Detection model."""
    try:
        query_params = request.query_params
        search = (query_params.get("search") or "").strip()
        force_rescan = (
            (query_params.get("force_rescan") or "false").strip().lower() == "true"
        )

        try:
            offset = int(query_params.get("offset", "0"))
            limit = int(query_params.get("limit", "200"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="offset and limit must be integers")

        if offset < 0:
            raise HTTPException(status_code=400, detail="offset must be >= 0")
        if limit <= 0:
            raise HTTPException(status_code=400, detail="limit must be > 0")

        limit = min(limit, 500)

        normalized_model_id = handler.model_manager.normalize_model_id(model_id)
        model_info, labels = handler.model_manager.get_model_labels(
            model_identifier=normalized_model_id,
            force_rescan=force_rescan,
        )
        if model_info is None:
            raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

        indexed_labels = list(enumerate(labels))
        if search:
            search_lower = search.lower()
            indexed_labels = [
                (class_id, label_name)
                for class_id, label_name in indexed_labels
                if search_lower in label_name.lower()
            ]

        filtered_count = len(indexed_labels)
        page_labels = indexed_labels[offset : offset + limit]

        return JSONResponse(
            content={
                "status": "success",
                "model_id": normalized_model_id,
                "model_name": model_info.get("name") or normalized_model_id,
                "total_labels": len(labels),
                "filtered_count": filtered_count,
                "returned_count": len(page_labels),
                "offset": offset,
                "limit": limit,
                "has_more": (offset + len(page_labels)) < filtered_count,
                "labels": [
                    {"class_id": class_id, "label": label_name}
                    for class_id, label_name in page_labels
                ],
                "search": search,
                "schema_version": "1.0",
                "timestamp": time.time(),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        handler.logger.error(f"Error getting Detection model labels for '{model_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


def resolve_standby_cpu_model_path(model_path: Path) -> str:
    """Prefer sibling NCNN export for standby CPU path, fallback to .pt."""
    ncnn_dir = model_path.with_name(f"{model_path.stem}_ncnn_model")
    has_ncnn_files = (
        ncnn_dir.exists()
        and ncnn_dir.is_dir()
        and any(ncnn_dir.glob("*.bin"))
        and any(ncnn_dir.glob("*.param"))
    )
    if has_ncnn_files:
        return str(ncnn_dir.as_posix())
    return str(model_path.as_posix())


def persist_standby_model_selection(
    handler: Any,
    model_path: Path,
    device: str,
) -> Dict[str, Any]:
    """Persist standby SmartTracker model paths in config.yaml."""
    device = (device or "auto").strip().lower()
    normalized_pt = str(model_path.as_posix())
    resolved_cpu = resolve_standby_cpu_model_path(model_path)

    updates: Dict[str, str] = {}
    if device in ("auto", "gpu"):
        updates["SMART_TRACKER_GPU_MODEL_PATH"] = normalized_pt
    if device in ("auto", "cpu"):
        updates["SMART_TRACKER_CPU_MODEL_PATH"] = resolved_cpu

    with _config_mutation_transaction(handler) as (service, transaction):
        old_values = {
            parameter: service.get_parameter("SmartTracker", parameter)
            for parameter in updates
        }
        for parameter, value in updates.items():
            validation = service.set_parameter(
                "SmartTracker",
                parameter,
                value,
                audit=False,
            )
            if not validation.valid:
                errors = "; ".join(
                    validation.errors or validation.warnings or ["validation failed"]
                )
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Failed to persist SmartTracker standby model "
                        f"({parameter}): {errors}"
                    ),
                )

        _persist_config(service, transaction)
        _assert_audit_source_unchanged(service, transaction)
        for parameter, value in updates.items():
            _log_config_audit(
                service,
                transaction,
                action="update",
                section="SmartTracker",
                parameter=parameter,
                old_value=old_values[parameter],
                new_value=value,
                source="model_api",
            )
        _publish_runtime_config()

    effective_gpu = Parameters.SmartTracker.get(
        "SMART_TRACKER_GPU_MODEL_PATH",
        normalized_pt,
    )
    effective_cpu = Parameters.SmartTracker.get(
        "SMART_TRACKER_CPU_MODEL_PATH",
        resolved_cpu,
    )

    return {
        "updated": updates,
        "configured_gpu_model_path": str(effective_gpu),
        "configured_cpu_model_path": str(effective_cpu),
    }


def _runtime_device_preference(runtime: Dict[str, Any]) -> str:
    """Map runtime device metadata back to a SmartTracker switch preference."""
    effective_device = str(runtime.get("effective_device") or "").lower()
    requested_device = str(runtime.get("requested_device") or "").lower()
    for candidate in (effective_device, requested_device):
        if candidate.startswith("cuda") or candidate == "gpu":
            return "gpu"
        if candidate == "cpu" or candidate.startswith("cpu_"):
            return "cpu"
    return "auto"


def _capture_runtime_model(smart_tracker: Any) -> Dict[str, Any]:
    """Capture enough verified runtime state to reverse a live model switch."""
    if not hasattr(smart_tracker, "get_runtime_info"):
        raise HTTPException(
            status_code=409,
            detail=(
                "Current SmartTracker runtime model cannot be verified; "
                "model switch refused"
            ),
        )

    try:
        runtime = smart_tracker.get_runtime_info()
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "Current SmartTracker runtime model cannot be verified; "
                "model switch refused"
            ),
        ) from exc

    if not isinstance(runtime, dict) or not runtime.get("model_path"):
        raise HTTPException(
            status_code=409,
            detail=(
                "Current SmartTracker runtime model cannot be verified; "
                "model switch refused"
            ),
        )

    return {
        "model_path": str(runtime["model_path"]),
        "device": _runtime_device_preference(runtime),
        "effective_device": str(runtime.get("effective_device") or "").lower(),
    }


def _normalized_model_path(model_path: Any) -> str:
    """Normalize one local model path for post-rollback comparison."""
    return str(Path(str(model_path)).expanduser().resolve(strict=False))


def _restore_runtime_model(
    smart_tracker: Any,
    prior_runtime: Dict[str, Any],
) -> None:
    """Restore and verify the live model after persistence fails."""
    rollback = smart_tracker.switch_model(
        prior_runtime["model_path"],
        device=prior_runtime["device"],
    )
    if not isinstance(rollback, dict) or not rollback.get("success", False):
        message = rollback.get("message") if isinstance(rollback, dict) else None
        raise RuntimeError(message or "SmartTracker rejected model rollback")

    restored_runtime = smart_tracker.get_runtime_info()
    if not isinstance(restored_runtime, dict) or not restored_runtime.get("model_path"):
        raise RuntimeError("SmartTracker did not report runtime state after rollback")

    if _normalized_model_path(restored_runtime["model_path"]) != _normalized_model_path(
        prior_runtime["model_path"]
    ):
        raise RuntimeError("SmartTracker rollback restored a different model path")

    prior_device = prior_runtime.get("effective_device")
    restored_device = str(restored_runtime.get("effective_device") or "").lower()
    if prior_device and restored_device and prior_device != restored_device:
        raise RuntimeError("SmartTracker rollback restored a different device")


def _switch_model_while_following_response() -> JSONResponse:
    """Return the explicit fail-closed policy for live model changes."""
    return JSONResponse(
        status_code=409,
        content={
            "status": "error",
            "action": "switch_blocked",
            "error": "Cannot switch detection model while following is active",
            "error_code": "MODEL_SWITCH_FOLLOWING_ACTIVE",
            "requires_disconnect": True,
        },
    )


def _switch_model_while_tracking_response() -> JSONResponse:
    """Require target deselection before changing detector label semantics."""
    return JSONResponse(
        status_code=409,
        content={
            "status": "error",
            "action": "switch_blocked",
            "error": "Clear the selected tracking target before switching models",
            "error_code": "MODEL_SWITCH_TRACKING_ACTIVE",
            "requires_target_clear": True,
        },
    )


def _switch_model_target_barrier_unavailable_response() -> JSONResponse:
    """Refuse model replacement without target-selection serialization."""
    return JSONResponse(
        status_code=503,
        content={
            "status": "error",
            "action": "switch_blocked",
            "error": "Tracker/model state barrier is unavailable",
            "error_code": "MODEL_SWITCH_TARGET_BARRIER_UNAVAILABLE",
        },
    )


def _smart_tracker_has_target_selection(smart_tracker: Any) -> bool:
    """Detect target ownership in either SmartTracker compatibility state."""
    if getattr(smart_tracker, "selected_object_id", None) is not None:
        return True
    tracking_manager = getattr(smart_tracker, "tracking_manager", None)
    return getattr(tracking_manager, "selected_track_id", None) is not None


def _switch_model_under_follower_guard(
    handler: Any,
    model_path: str,
    device: str,
    *,
    target_lock_acquired: bool = False,
) -> JSONResponse:
    """Validate and switch a model while follower state cannot transition."""
    app_controller = handler.app_controller
    if bool(getattr(app_controller, "following_active", False)):
        return _switch_model_while_following_response()

    if not target_lock_acquired:
        target_lock = getattr(app_controller, "_tracker_model_state_lock", None)
        if target_lock is None:
            return _switch_model_target_barrier_unavailable_response()
        with target_lock:
            return _switch_model_under_follower_guard(
                handler,
                model_path,
                device,
                target_lock_acquired=True,
            )

    full_path = Path(model_path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Model file not found: {model_path}")

    smart_tracker = getattr(app_controller, "smart_tracker", None)
    if smart_tracker is not None and _smart_tracker_has_target_selection(smart_tracker):
        return _switch_model_while_tracking_response()

    validation = handler.model_manager.validate_model(full_path)
    if not validation.get("valid", False):
        raise HTTPException(
            status_code=400,
            detail=(
                "Model validation failed: "
                f"{validation.get('error', 'unknown error')}"
            ),
        )
    if not validation.get("smarttracker_supported", True):
        raise HTTPException(
            status_code=400,
            detail=(
                "Model task is not supported by SmartTracker. "
                f"Task={validation.get('task', 'unknown')}. "
                f"Notes={validation.get('compatibility_notes', [])}"
            ),
        )
    if smart_tracker is not None and _smart_tracker_has_target_selection(smart_tracker):
        return _switch_model_while_tracking_response()

    if smart_tracker is None:
        standby_result = persist_standby_model_selection(handler, full_path, device)
        handler.logger.info(
            f"Standby model configured via API: {model_path} (device={device})"
        )
        return JSONResponse(
            content={
                "status": "success",
                "action": "model_configured",
                "model_path": model_path,
                "device": device,
                "message": (
                    "SmartTracker is currently off. Standby model selection saved "
                    "and will be used the next time Smart Mode starts."
                ),
                "model_info": {
                    "path": model_path,
                    "device": device,
                    "backend": "standby_config",
                },
                "runtime": None,
                "configured_gpu_model_path": standby_result.get(
                    "configured_gpu_model_path"
                ),
                "configured_cpu_model_path": standby_result.get(
                    "configured_cpu_model_path"
                ),
            }
        )

    prior_runtime = _capture_runtime_model(smart_tracker)
    result = smart_tracker.switch_model(str(full_path), device=device)

    if result.get("success", False):
        try:
            standby_result = persist_standby_model_selection(
                handler,
                full_path,
                device,
            )
        except Exception as persist_error:
            try:
                _restore_runtime_model(smart_tracker, prior_runtime)
            except Exception as rollback_error:
                handler.logger.critical(
                    "Standby model persistence failed and live model rollback failed: %s",
                    rollback_error,
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Model configuration failed and the prior live model could not "
                        "be restored; operator recovery is required"
                    ),
                ) from persist_error

            handler.logger.error(
                "Live model switch rolled back because standby persistence failed: %s",
                persist_error,
            )
            status_code = (
                persist_error.status_code
                if isinstance(persist_error, HTTPException)
                else 500
            )
            raise HTTPException(
                status_code=status_code,
                detail=(
                    "Model switch was rolled back because standby configuration "
                    "could not be persisted"
                ),
            ) from persist_error

        handler.logger.info(
            f"Detection model switched via API: {model_path} (device={device})"
        )
        return JSONResponse(
            content={
                "status": "success",
                "action": "model_switched",
                "model_path": model_path,
                "device": device,
                "message": result["message"],
                "model_info": result.get("model_info"),
                "runtime": (result.get("model_info") or {}).get("runtime"),
                "configured_gpu_model_path": standby_result.get(
                    "configured_gpu_model_path"
                ),
                "configured_cpu_model_path": standby_result.get(
                    "configured_cpu_model_path"
                ),
                "config_persist_warning": None,
            }
        )

    error_msg = result.get("message", "Unknown error during model switch")
    handler.logger.error(f"Detection model switch failed: {error_msg}")
    return JSONResponse(
        content={
            "status": "error",
            "action": "switch_failed",
            "requested_model": model_path,
            "error": error_msg,
        },
        status_code=500,
    )


async def download_model_file(handler: Any, model_id: str) -> FileResponse:
    """Download a model's .pt file from the device."""
    try:
        models = handler.model_manager.discover_models(force_rescan=False)
        if model_id not in models:
            raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

        model_info = models[model_id]
        model_path = Path(model_info.get("path", ""))
        if not model_path.is_absolute():
            model_path = Path(handler.model_manager.folder) / model_path.name
            if not model_path.exists():
                model_path = Path(model_info.get("path", ""))

        if not model_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Model file not found on disk: {model_path}",
            )

        return FileResponse(
            path=str(model_path),
            filename=model_path.name,
            media_type="application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        handler.logger.error(f"Error downloading model file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def switch_model(handler: Any, request: Request) -> JSONResponse:
    """Switch detection model in SmartTracker without restart."""
    try:
        data = await request.json()
        model_path = data.get("model_path")
        device = data.get("device", "auto")

        if not model_path:
            raise HTTPException(status_code=400, detail="model_path is required")

        if device not in ["auto", "gpu", "cpu"]:
            raise HTTPException(
                status_code=400,
                detail="device must be 'auto', 'gpu', or 'cpu'",
            )

        follower_lock = getattr(
            getattr(handler, "app_controller", None),
            "_follower_state_lock",
            None,
        )
        if follower_lock is None:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "action": "switch_blocked",
                    "error": (
                        "Follower state barrier is unavailable; model switch refused"
                    ),
                    "error_code": "MODEL_SWITCH_STATE_BARRIER_UNAVAILABLE",
                },
            )

        async with follower_lock:
            return await run_in_threadpool(
                _switch_model_under_follower_guard,
                handler,
                model_path,
                device,
            )

    except HTTPException:
        raise
    except Exception as e:
        handler.logger.error(f"Error switching Detection model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def upload_model(handler: Any, request: Request) -> JSONResponse:
    """Upload a new Detection model file."""
    try:
        form = await request.form()
        file = form.get("file")

        if not file or not hasattr(file, "filename"):
            raise HTTPException(status_code=400, detail="No file provided")

        filename = file.filename
        if not filename.endswith(".pt"):
            raise HTTPException(status_code=400, detail="Only .pt files are allowed")

        file_data = await file.read()
        auto_export = form.get("auto_export_ncnn", "true").lower() == "true"

        result = await handler.model_manager.upload_model(
            file_data=file_data,
            filename=filename,
            auto_export_ncnn=auto_export,
        )

        if result["success"]:
            handler.logger.info(f"Detection model uploaded via API: {filename}")

            return JSONResponse(
                content={
                    "status": "success",
                    "action": "model_uploaded",
                    "filename": filename,
                    "message": result.get("message", "Model uploaded successfully"),
                    "model_info": result.get("model_info"),
                    "ncnn_exported": result.get("ncnn_exported", False),
                    "ncnn_export": result.get("ncnn_export"),
                }
            )

        error_msg = result.get("error", "Unknown error during upload")
        handler.logger.error(f"Detection model upload failed: {error_msg}")

        return JSONResponse(
            content={
                "status": "error",
                "action": "upload_failed",
                "filename": filename,
                "error": error_msg,
            },
            status_code=500,
        )

    except HTTPException:
        raise
    except Exception as e:
        handler.logger.error(f"Error uploading Detection model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def download_model(handler: Any, request: Request) -> JSONResponse:
    """Download a Detection model by name or URL."""
    try:
        body = await request.json()
        model_name = body.get("model_name", "").strip()
        download_url = body.get("download_url", "").strip() or None
        auto_export_ncnn = body.get("auto_export_ncnn", True)

        if not model_name:
            raise HTTPException(status_code=400, detail="model_name is required")
        if not model_name.endswith(".pt"):
            model_name += ".pt"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            handler.model_manager.download_model,
            model_name,
            download_url,
        )

        if result["success"]:
            ncnn_result = None
            if auto_export_ncnn:
                try:
                    ncnn_result = await handler.model_manager._export_async(
                        Path(result["path"])
                    )
                except Exception as e:
                    handler.logger.warning(f"NCNN export after download failed: {e}")
                    ncnn_result = {"success": False, "error": str(e)}

            handler.logger.info(f"Detection model downloaded via API: {model_name}")

            return JSONResponse(
                content={
                    "status": "success",
                    "action": "model_downloaded",
                    "model_name": model_name,
                    "path": result["path"],
                    "message": result.get(
                        "message",
                        f"{model_name} downloaded successfully",
                    ),
                    "ncnn_exported": bool(
                        ncnn_result and ncnn_result.get("success")
                    ),
                    "ncnn_export": ncnn_result,
                }
            )

        error_msg = result.get("error", "Download failed")
        handler.logger.warning(
            f"Detection model download failed for {model_name}: {error_msg}"
        )

        return JSONResponse(
            content={
                "status": "error",
                "action": "download_failed",
                "model_name": model_name,
                "error": error_msg,
                "suggested_urls": result.get("suggested_urls", []),
            },
            status_code=422,
        )

    except HTTPException:
        raise
    except Exception as e:
        handler.logger.error(f"Error downloading Detection model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def delete_model(handler: Any, model_id: str) -> JSONResponse:
    """Delete a Detection model file."""
    try:
        result = handler.model_manager.delete_model(model_id, delete_ncnn=True)

        if result["success"]:
            handler.logger.info(f"Detection model deleted via API: {model_id}")

            return JSONResponse(
                content={
                    "status": "success",
                    "action": "model_deleted",
                    "model_id": model_id,
                    "message": result.get("message", "Model deleted successfully"),
                }
            )

        error_msg = result.get("error", "Unknown error during deletion")
        handler.logger.error(f"Detection model deletion failed: {error_msg}")

        return JSONResponse(
            content={
                "status": "error",
                "action": "deletion_failed",
                "model_id": model_id,
                "error": error_msg,
            },
            status_code=404 if "not found" in error_msg.lower() else 500,
        )

    except Exception as e:
        handler.logger.error(f"Error deleting Detection model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
