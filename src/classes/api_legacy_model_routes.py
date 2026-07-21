"""Legacy detection-model route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from starlette.formparsers import MultiPartException

from classes.api_legacy_config_routes import (
    _assert_audit_source_unchanged,
    _config_mutation_transaction,
    _log_config_audit,
    _persist_config,
)
from classes.bounded_multipart import (
    MultipartHeaderLimitExceeded,
    MultipartParseTimeout,
    MultipartSizeLimitExceeded,
    parse_bounded_multipart_form,
)
from classes.model_artifact_policy import (
    DEFAULT_MAX_EXPORT_BYTES,
    DEFAULT_MAX_MODEL_BYTES,
    ModelArtifactNotFoundError,
    ModelArtifactPolicyError,
    ModelIngestLease,
    ModelProvenanceStore,
    ModelRegistryCorruptionError,
    ModelStoreBusyError,
    ModelStoreLease,
    sha256_descriptor,
    validate_model_filename,
)
from classes.parameters import Parameters


MODEL_INGEST_DISK_RESERVE_BYTES = 256 * 1024 * 1024
MODEL_INGEST_ADMISSION_TIMEOUT_SECONDS = 0.05


class ModelIngestCapacityError(RuntimeError):
    """Raised before upload parsing when temporary storage is insufficient."""


def _require_model_ingest_capacity(
    models_root: Path,
    *,
    max_model_bytes: int,
    include_ncnn_export: bool,
) -> None:
    """Require headroom for multipart spool, staging, and optional export copies."""
    temporary_root = Path(tempfile.gettempdir()).resolve()
    model_root = Path(models_root).resolve()
    temporary_free = shutil.disk_usage(temporary_root).free
    model_free = shutil.disk_usage(model_root).free
    same_filesystem = os.stat(temporary_root).st_dev == os.stat(model_root).st_dev

    if include_ncnn_export:
        model_requirement = (
            (2 * max_model_bytes)
            + DEFAULT_MAX_EXPORT_BYTES
            + MODEL_INGEST_DISK_RESERVE_BYTES
        )
    else:
        model_requirement = max_model_bytes + MODEL_INGEST_DISK_RESERVE_BYTES

    if same_filesystem:
        required = max_model_bytes + model_requirement
        if model_free < required:
            raise ModelIngestCapacityError(
                f"model ingest requires {required} free bytes; {model_free} available"
            )
        return

    temporary_requirement = max_model_bytes + MODEL_INGEST_DISK_RESERVE_BYTES
    if temporary_free < temporary_requirement or model_free < model_requirement:
        raise ModelIngestCapacityError(
            "model ingest temporary/model filesystems lack required free-space headroom"
        )


def _model_registry_unavailable(handler: Any, exc: Exception) -> HTTPException:
    handler.logger.error("Model provenance registry unavailable: %s", exc)
    return HTTPException(
        status_code=503,
        detail={
            "error_code": "MODEL_PROVENANCE_UNAVAILABLE",
            "message": "Model inventory trust data is unavailable",
        },
    )


def _model_store_busy(handler: Any, exc: Exception) -> HTTPException:
    handler.logger.warning("Model store is busy: %s", exc)
    return HTTPException(
        status_code=409,
        detail={
            "error_code": "MODEL_STORE_BUSY",
            "message": "Model store is busy; stop the active model or retry later",
        },
    )


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

        models = await run_in_threadpool(
            handler.model_manager.discover_models,
            force_rescan,
        )

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

    except ModelRegistryCorruptionError as exc:
        raise _model_registry_unavailable(handler, exc) from exc
    except ModelStoreBusyError as exc:
        raise _model_store_busy(handler, exc) from exc
    except Exception as e:
        handler.logger.error(f"Error getting Detection models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_active_model(handler: Any) -> JSONResponse:
    """Get compact, UI-focused metadata for the active/configured model."""
    try:
        models = await run_in_threadpool(
            handler.model_manager.discover_models,
            False,
        )
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
    except ModelRegistryCorruptionError as exc:
        raise _model_registry_unavailable(handler, exc) from exc
    except ModelStoreBusyError as exc:
        raise _model_store_busy(handler, exc) from exc
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
        model_info, labels = await run_in_threadpool(
            handler.model_manager.get_model_labels,
            normalized_model_id,
            force_rescan,
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
    except ModelRegistryCorruptionError as exc:
        raise _model_registry_unavailable(handler, exc) from exc
    except ModelStoreBusyError as exc:
        raise _model_store_busy(handler, exc) from exc
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
    """Persist one coherent SmartTracker model/device selection."""
    device = (device or "auto").strip().lower()
    normalized_pt = str(model_path.as_posix())
    resolved_cpu = resolve_standby_cpu_model_path(model_path)

    updates: Dict[str, Any] = {
        "SMART_TRACKER_GPU_MODEL_PATH": normalized_pt,
        "SMART_TRACKER_CPU_MODEL_PATH": resolved_cpu,
    }
    if device == "gpu":
        updates["SMART_TRACKER_USE_GPU"] = True
    elif device == "cpu":
        updates["SMART_TRACKER_USE_GPU"] = False

    published_smart_tracker: Dict[str, Any] = {}
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
        runtime_config = service.get_applied_runtime_config()
        candidate = copy.deepcopy(runtime_config)
        smart_tracker_config = candidate.get("SmartTracker")
        if not isinstance(smart_tracker_config, dict):
            raise RuntimeError("Applied SmartTracker runtime config is unavailable")
        smart_tracker_config.update(copy.deepcopy(updates))
        service.publish_runtime_config_snapshot(
            candidate,
            source="model_api_selection_apply",
        )
        published_smart_tracker = copy.deepcopy(smart_tracker_config)

    effective_gpu = published_smart_tracker.get(
        "SMART_TRACKER_GPU_MODEL_PATH",
        normalized_pt,
    )
    effective_cpu = published_smart_tracker.get(
        "SMART_TRACKER_CPU_MODEL_PATH",
        resolved_cpu,
    )
    effective_use_gpu = bool(
        published_smart_tracker.get("SMART_TRACKER_USE_GPU", True)
    )

    return {
        "updated": updates,
        "configured_gpu_model_path": str(effective_gpu),
        "configured_cpu_model_path": str(effective_cpu),
        "configured_use_gpu": effective_use_gpu,
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

    validation = handler.model_manager.validate_model(
        full_path,
        allow_checkpoint_execution=True,
    )
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
                "configured_use_gpu": standby_result.get("configured_use_gpu"),
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
                "configured_use_gpu": standby_result.get("configured_use_gpu"),
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


async def download_model_file(handler: Any, model_id: str) -> StreamingResponse:
    """Stream a verified pinned descriptor after releasing the shared store lock."""
    descriptor = -1
    response_owns_resources = False
    try:
        def prepare_download():
            normalized_id = handler.model_manager.normalize_model_id(model_id)
            prepared_filename = validate_model_filename(f"{normalized_id}.pt")
            models_root = Path(handler.model_manager.models_folder)
            prepared_lease = ModelStoreLease(
                models_root,
                exclusive=False,
                timeout_seconds=0.1,
            )
            prepared_descriptor = -1
            prepared_lease.__enter__()
            try:
                max_bytes = int(
                    getattr(
                        handler.model_manager,
                        "max_model_bytes",
                        DEFAULT_MAX_MODEL_BYTES,
                    )
                )
                provenance = ModelProvenanceStore(models_root).verify_pt_locked(
                    models_root / prepared_filename,
                    prepared_lease,
                    max_bytes=max_bytes,
                )
                prepared_descriptor = prepared_lease.open_model(prepared_filename)
                observed_digest, prepared_stat = sha256_descriptor(
                    prepared_descriptor,
                    expected_uid=prepared_lease.expected_uid,
                    max_bytes=max_bytes,
                )
                if observed_digest != provenance["sha256"]:
                    raise ModelArtifactPolicyError(
                        "Model changed while its download descriptor was opened"
                    )
                prepared_lease.assert_descriptor_binding(
                    prepared_filename,
                    prepared_descriptor,
                )
                return (
                    prepared_descriptor,
                    prepared_filename,
                    observed_digest,
                    prepared_stat,
                )
            except BaseException:
                if prepared_descriptor >= 0:
                    os.close(prepared_descriptor)
                raise
            finally:
                prepared_lease.close()

        descriptor, filename, observed, artifact_stat = await run_in_threadpool(
            prepare_download
        )

        def stream_descriptor():
            nonlocal descriptor
            digest = hashlib.sha256()
            remaining = artifact_stat.st_size
            try:
                while remaining:
                    chunk = os.read(descriptor, min(1024 * 1024, remaining))
                    if not chunk:
                        raise RuntimeError(
                            "Verified model descriptor became shorter during download"
                        )
                    remaining -= len(chunk)
                    digest.update(chunk)
                    yield chunk
                if os.read(descriptor, 1):
                    raise RuntimeError(
                        "Verified model descriptor became larger during download"
                    )
                if digest.hexdigest() != observed:
                    raise RuntimeError(
                        "Verified model descriptor mutated during download"
                    )
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                    descriptor = -1

        response_owns_resources = True
        return StreamingResponse(
            stream_descriptor(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(artifact_stat.st_size),
                "X-Artifact-SHA256": observed,
            },
        )
    except ModelRegistryCorruptionError as exc:
        raise _model_registry_unavailable(handler, exc) from exc
    except (ModelArtifactNotFoundError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Trusted model not found") from exc
    except ModelStoreBusyError as exc:
        raise _model_store_busy(handler, exc) from exc
    except ModelArtifactPolicyError as exc:
        handler.logger.error("Model download trust verification failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "MODEL_ARTIFACT_TRUST_FAILURE",
                "message": "Model artifact trust verification failed",
            },
        ) from exc
    except Exception as exc:
        handler.logger.exception("Error preparing trusted model download")
        raise HTTPException(status_code=500, detail="Model download failed") from exc
    finally:
        if not response_owns_resources:
            if descriptor >= 0:
                os.close(descriptor)


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
    form = None
    semaphore = getattr(handler, "model_ingest_semaphore", None)
    if semaphore is None:
        semaphore = asyncio.Semaphore(1)
        handler.model_ingest_semaphore = semaphore
    acquired = False
    ingest_lease = None
    try:
        max_model_bytes = int(
            getattr(handler.model_manager, "max_model_bytes", DEFAULT_MAX_MODEL_BYTES)
        )
        try:
            await asyncio.wait_for(
                semaphore.acquire(),
                timeout=MODEL_INGEST_ADMISSION_TIMEOUT_SECONDS,
            )
            acquired = True
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=429,
                content={
                    "status": "error",
                    "action": "upload_failed",
                    "error": "Another model ingest transaction is active",
                    "error_code": "MODEL_UPLOAD_BUSY",
                },
            )

        try:
            ingest_lease = ModelIngestLease(
                Path(handler.model_manager.models_folder),
                timeout_seconds=0.0,
            )
            ingest_lease.__enter__()
        except ModelStoreBusyError:
            return JSONResponse(
                status_code=429,
                content={
                    "status": "error",
                    "action": "upload_failed",
                    "error": "Another model ingest transaction is active",
                    "error_code": "MODEL_UPLOAD_BUSY",
                },
            )

        _require_model_ingest_capacity(
            Path(handler.model_manager.models_folder),
            max_model_bytes=max_model_bytes,
            include_ncnn_export=False,
        )
        form = await parse_bounded_multipart_form(
            request,
            max_file_bytes=max_model_bytes,
        )
        file = form.get("file")

        if not file or not hasattr(file, "filename"):
            raise HTTPException(status_code=400, detail="No file provided")

        filename = str(file.filename or "")
        auto_export = str(form.get("auto_export_ncnn", "false")).lower() == "true"
        trust_model = str(form.get("trust_model", "false")).lower() == "true"
        expected_sha256 = str(form.get("expected_sha256", "")).strip() or None
        display_name = str(form.get("display_name", "")).strip() or None

        if auto_export:
            _require_model_ingest_capacity(
                Path(handler.model_manager.models_folder),
                max_model_bytes=max_model_bytes,
                include_ncnn_export=True,
            )

        result = await handler.model_manager.upload_model_file(
            upload_file=file,
            filename=filename,
            auto_export_ncnn=auto_export,
            expected_sha256=expected_sha256,
            trust_model=trust_model,
            source="dashboard_or_api_upload",
            display_name=display_name,
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
                    "artifact_sha256": result.get("artifact_sha256"),
                    "observed_sha256": result.get("observed_sha256"),
                    "publisher_sha256": result.get("publisher_sha256"),
                    "trust_method": result.get("trust_method"),
                    "registration_action_id": result.get(
                        "registration_action_id"
                    ),
                    "registration_receipt": result.get(
                        "registration_receipt"
                    ),
                    "ncnn_exported": result.get("ncnn_exported", False),
                    "ncnn_export": result.get("ncnn_export"),
                }
            )

        error_msg = result.get("error", "Unknown error during upload")
        handler.logger.error(f"Detection model upload failed: {error_msg}")
        status_code = int(result.get("status_code", 422))
        if status_code == 503:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "action": "upload_failed",
                    "filename": filename,
                    "error": "Model inventory trust data is unavailable",
                    "error_code": "MODEL_PROVENANCE_UNAVAILABLE",
                },
            )
        if status_code == 409:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "error",
                    "action": "upload_failed",
                    "filename": filename,
                    "error": "Model store is busy; stop the active model or retry later",
                    "error_code": "MODEL_STORE_BUSY",
                },
            )

        return JSONResponse(
            content={
                "status": "error",
                "action": "upload_failed",
                "filename": filename,
                "error": error_msg,
            },
            status_code=status_code,
        )

    except ModelIngestCapacityError as exc:
        handler.logger.warning("Model upload rejected for storage headroom: %s", exc)
        return JSONResponse(
            status_code=507,
            content={
                "status": "error",
                "action": "upload_failed",
                "error": "Insufficient temporary storage for a bounded model ingest",
                "error_code": "MODEL_UPLOAD_STORAGE_UNAVAILABLE",
            },
        )
    except MultipartSizeLimitExceeded as exc:
        return JSONResponse(
            status_code=413,
            content={
                "status": "error",
                "action": "upload_failed",
                "error": str(exc),
                "error_code": "MODEL_UPLOAD_SIZE_LIMIT_EXCEEDED",
            },
        )
    except MultipartHeaderLimitExceeded as exc:
        return JSONResponse(
            status_code=431,
            content={
                "status": "error",
                "action": "upload_failed",
                "error": str(exc),
                "error_code": "MODEL_UPLOAD_HEADER_LIMIT_EXCEEDED",
            },
        )
    except MultipartParseTimeout as exc:
        return JSONResponse(
            status_code=408,
            content={
                "status": "error",
                "action": "upload_failed",
                "error": str(exc),
                "error_code": "MODEL_UPLOAD_TIMEOUT",
            },
        )
    except MultiPartException as exc:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "action": "upload_failed",
                "error": str(exc),
                "error_code": "MODEL_UPLOAD_MULTIPART_INVALID",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        handler.logger.error(f"Error uploading Detection model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            close_form = getattr(form, "close", None)
            if callable(close_form):
                await close_form()
        finally:
            try:
                if ingest_lease is not None:
                    ingest_lease.close()
            finally:
                if acquired:
                    semaphore.release()


async def delete_model(handler: Any, model_id: str) -> JSONResponse:
    """Delete a Detection model file."""
    try:
        result = await run_in_threadpool(
            handler.model_manager.delete_model,
            model_id,
            True,
        )

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
        status_code = int(result.get("status_code", 500))
        if status_code == 503:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "action": "deletion_failed",
                    "model_id": model_id,
                    "error": "Model inventory trust data is unavailable",
                    "error_code": "MODEL_PROVENANCE_UNAVAILABLE",
                },
            )
        if status_code == 409:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "error",
                    "action": "deletion_failed",
                    "model_id": model_id,
                    "error": "Model store is busy; stop the active model or retry later",
                    "error_code": "MODEL_STORE_BUSY",
                },
            )

        return JSONResponse(
            content={
                "status": "error",
                "action": "deletion_failed",
                "model_id": model_id,
                "error": error_msg,
            },
            status_code=(
                404 if "not found" in error_msg.lower() else status_code
            ),
        )

    except Exception as e:
        handler.logger.error(f"Error deleting Detection model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
