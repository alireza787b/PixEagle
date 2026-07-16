#!/usr/bin/env python3
"""Bounded probe for local model loading and one deterministic inference."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SUPPORTED_SMART_TRACKER_TASKS = frozenset({"detect", "obb"})
SUPPORTED_RESULT_MODES = frozenset({"detect", "obb", "none"})
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_PROBE_RESULT_BYTES = 1024 * 1024
MAX_PROBE_DIAGNOSTIC_BYTES = 2000


def _read_tail(stream, limit: int = MAX_PROBE_DIAGNOSTIC_BYTES) -> str:
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(max(0, size - limit), os.SEEK_SET)
    return stream.read(limit).decode("utf-8", errors="replace")


def _read_probe_result(stream) -> dict[str, Any]:
    stream.seek(0, os.SEEK_SET)
    encoded = stream.read(MAX_PROBE_RESULT_BYTES + 1)
    if not encoded:
        raise ValueError("child emitted no private probe result")
    if len(encoded) > MAX_PROBE_RESULT_BYTES:
        raise ValueError("child private probe result exceeded its size limit")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("child private probe result was invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("child private probe result was not an object")
    return payload


def _write_probe_result(descriptor: int, payload: dict[str, Any]) -> None:
    if descriptor < 3:
        raise ValueError("private probe result descriptor is invalid")
    descriptor_stat = os.fstat(descriptor)
    if (
        not stat.S_ISREG(descriptor_stat.st_mode)
        or descriptor_stat.st_uid != os.geteuid()
    ):
        raise ValueError("private probe result descriptor is unsafe")
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_PROBE_RESULT_BYTES:
        raise ValueError("private probe result exceeded its size limit")
    os.lseek(descriptor, 0, os.SEEK_SET)
    os.ftruncate(descriptor, 0)
    offset = 0
    while offset < len(encoded):
        offset += os.write(descriptor, encoded[offset:])
    os.fsync(descriptor)


def _resolve(root: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else root / candidate


def _is_model_artifact(path: Path, *, models_root: Path) -> bool:
    """Recognize only canonical direct-child artifacts without symlink aliases."""
    candidate = Path(os.path.abspath(path))
    canonical_root = Path(os.path.abspath(models_root))
    try:
        if (
            candidate.resolve(strict=True) != candidate
            or canonical_root.resolve(strict=True) != canonical_root
            or candidate.parent != canonical_root
        ):
            return False
        candidate_stat = os.lstat(candidate)
    except OSError:
        return False
    if stat.S_ISREG(candidate_stat.st_mode):
        return candidate.suffix.lower() == ".pt" and candidate_stat.st_nlink == 1
    if not stat.S_ISDIR(candidate_stat.st_mode):
        return False
    has_param = False
    has_bin = False
    try:
        for entry in os.scandir(candidate):
            entry_stat = entry.stat(follow_symlinks=False)
            if not stat.S_ISREG(entry_stat.st_mode) or entry_stat.st_nlink != 1:
                continue
            has_param = has_param or entry.name.lower().endswith(".param")
            has_bin = has_bin or entry.name.lower().endswith(".bin")
    except OSError:
        return False
    return has_param and has_bin


def _cpu_candidate_paths(path: Path) -> list[Path]:
    if path.suffix.lower() == ".pt":
        return [path.with_name(f"{path.stem}_ncnn_model"), path]
    if path.name.endswith("_ncnn_model"):
        stem = path.name[: -len("_ncnn_model")]
        return [path, path.with_name(f"{stem}.pt")]
    return [path]


def configured_candidates(root: Path, smart_config: dict[str, Any]) -> list[Path]:
    use_gpu = bool(smart_config.get("SMART_TRACKER_USE_GPU", True))
    fallback = bool(smart_config.get("SMART_TRACKER_FALLBACK_TO_CPU", True))
    gpu_path = str(
        smart_config.get("SMART_TRACKER_GPU_MODEL_PATH", "models/yolo26n.pt")
    )
    cpu_path = str(
        smart_config.get(
            "SMART_TRACKER_CPU_MODEL_PATH", "models/yolo26n_ncnn_model"
        )
    )
    resolved_gpu = _resolve(root, gpu_path)
    resolved_cpu = _resolve(root, cpu_path)
    if use_gpu:
        candidates = [resolved_gpu]
        if fallback:
            candidates.extend(_cpu_candidate_paths(resolved_gpu))
            candidates.extend(_cpu_candidate_paths(resolved_cpu))
    else:
        candidates = _cpu_candidate_paths(resolved_cpu)
    return list(dict.fromkeys(candidates))


def _runtime_model_provenance(
    runtime: Any,
    *,
    trust_policy: str = "operator_ack_or_digest",
) -> tuple[bool, Any]:
    if not isinstance(runtime, dict):
        return False, None
    provenance = runtime.get("model_provenance")
    if not isinstance(provenance, dict):
        return False, provenance
    digest = str(provenance.get("sha256") or "").lower()
    ready = bool(
        provenance.get("verified") is True
        and provenance.get("artifact_type") in {"pt", "ncnn"}
        and SHA256_PATTERN.fullmatch(digest)
    )
    if ready and str(trust_policy).strip().lower() == "digest_required":
        artifact_type = provenance.get("artifact_type")
        source_digest = str(
            provenance.get("source_pt_sha256")
            if artifact_type == "ncnn"
            else digest
        ).lower()
        receipt = provenance.get("registration_receipt")
        ready = bool(
            SHA256_PATTERN.fullmatch(source_digest)
            and provenance.get("trust_method") == "expected_sha256"
            and provenance.get("observed_sha256") == source_digest
            and provenance.get("publisher_sha256") == source_digest
            and isinstance(receipt, dict)
            and receipt.get("publisher_digest_evidence_version") == 1
        )
    return ready, dict(provenance)


def probe_smart_tracker_model(
    root: Path,
    smart_config: dict[str, Any],
    *,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Load a local model and run one fixed-input inference in a child process."""

    root = root.resolve()
    candidates = configured_candidates(root, smart_config)
    models_root = root / "models"
    available = [
        path
        for path in candidates
        if _is_model_artifact(path, models_root=models_root)
    ]
    result: dict[str, Any] = {
        "attempted": False,
        "candidate_available": bool(available),
        "candidate_paths": [str(path) for path in candidates],
        "load_ready": False,
        "provenance_ready": False,
        "model_provenance": None,
        "inference_attempted": False,
        "first_inference_ready": False,
        "inference": None,
        "tracking_probe": {
            "attempted": False,
            "ready": None,
            "reason": "not_probed_no_offline_side_effect_contract",
        },
        "task": None,
        "runtime": None,
        "reason": "model_required" if not available else "not_attempted",
        "error": None,
        "timed_out": False,
    }
    if not available:
        return result

    request = {
        "root": str(root),
        "smart_config": smart_config,
    }
    with (
        tempfile.TemporaryFile(mode="w+b") as result_stream,
        tempfile.TemporaryFile(mode="w+b") as stdout_stream,
        tempfile.TemporaryFile(mode="w+b") as stderr_stream,
    ):
        result_descriptor = result_stream.fileno()
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--child",
                    "--result-fd",
                    str(result_descriptor),
                ],
                input=json.dumps(request),
                text=True,
                stdout=stdout_stream,
                stderr=stderr_stream,
                pass_fds=(result_descriptor,),
                cwd=root,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            result.update(
                attempted=True,
                reason="probe_timeout",
                error=f"model load or first inference exceeded {timeout_seconds:g}s",
                timed_out=True,
            )
            child_stdout = _read_tail(stdout_stream)
            child_stderr = _read_tail(stderr_stream)
            if child_stdout:
                result["child_stdout"] = child_stdout
            if child_stderr:
                result["child_stderr"] = child_stderr
            return result

        child_stdout = _read_tail(stdout_stream)
        child_stderr = _read_tail(stderr_stream)
        if child_stdout:
            result["child_stdout"] = child_stdout
        if child_stderr:
            result["child_stderr"] = child_stderr
        try:
            child = _read_probe_result(result_stream)
        except ValueError as exc:
            result.update(
                attempted=True,
                reason="probe_protocol_error",
                error=str(exc),
            )
            return result

    result["attempted"] = True
    result.update(child)
    result["attempted"] = True
    result["candidate_available"] = bool(available)
    result["candidate_paths"] = [str(path) for path in candidates]
    if completed.returncode != 0:
        result["first_inference_ready"] = False
    return result


def _run_child(result_descriptor: int) -> int:
    request = json.load(sys.stdin)
    root = Path(request["root"]).resolve()
    smart_config = request.get("smart_config") or {}
    os.chdir(root)
    sys.path.insert(0, str(root / "src"))

    payload: dict[str, Any] = {
        "load_ready": False,
        "provenance_ready": False,
        "model_provenance": None,
        "inference_attempted": False,
        "first_inference_ready": False,
        "inference": None,
        "tracking_probe": {
            "attempted": False,
            "ready": None,
            "reason": "not_probed_no_offline_side_effect_contract",
        },
        "task": None,
        "runtime": None,
        "reason": "model_load_failed",
        "error": None,
        "timed_out": False,
    }
    backend = None
    try:
        import numpy as np

        from classes.backends import DevicePreference, create_backend

        backend_name = str(smart_config.get("DETECTION_BACKEND", "ultralytics"))
        use_gpu = bool(smart_config.get("SMART_TRACKER_USE_GPU", True))
        fallback = bool(
            smart_config.get("SMART_TRACKER_FALLBACK_TO_CPU", True)
        )
        model_key = (
            "SMART_TRACKER_GPU_MODEL_PATH"
            if use_gpu
            else "SMART_TRACKER_CPU_MODEL_PATH"
        )
        default_model = (
            "models/yolo26n.pt" if use_gpu else "models/yolo26n_ncnn_model"
        )
        model_path = str(smart_config.get(model_key, default_model))
        device = DevicePreference.CUDA if use_gpu else DevicePreference.CPU
        backend = create_backend(backend_name, config=smart_config)
        if not backend.is_available:
            raise RuntimeError(f"detection backend '{backend_name}' is unavailable")
        runtime = backend.load_model(
            model_path=model_path,
            device=device,
            fallback_enabled=fallback,
            context="readiness_probe",
        )
        task = str(backend.get_model_task() or "unknown").lower()
        provenance_ready, model_provenance = _runtime_model_provenance(
            runtime,
            trust_policy=str(
                smart_config.get(
                    "SMART_TRACKER_MODEL_TRUST_POLICY",
                    "operator_ack_or_digest",
                )
            ),
        )
        payload["load_ready"] = True
        payload["runtime"] = runtime
        payload["task"] = task
        payload["provenance_ready"] = provenance_ready
        payload["model_provenance"] = model_provenance
        if task not in SUPPORTED_SMART_TRACKER_TASKS:
            payload.update(
                reason="unsupported_model_task",
                error=f"SmartTracker supports detect/obb models, got '{task}'",
            )
        elif not provenance_ready:
            payload.update(
                reason="model_provenance_unverified",
                error=(
                    "Detection backend did not report verified runtime model "
                    "provenance"
                ),
            )
        elif use_gpu and not fallback and runtime.get("effective_device") != "cuda":
            payload.update(
                reason="gpu_required_unavailable",
                error="GPU-only policy did not produce a CUDA runtime",
            )
        else:
            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            payload["inference_attempted"] = True
            result_mode, detections = backend.detect(
                frame,
                conf=0.99,
                iou=0.3,
                max_det=1,
            )
            if not isinstance(result_mode, str):
                raise TypeError("backend.detect() returned a non-string result mode")
            if result_mode not in SUPPORTED_RESULT_MODES:
                raise ValueError(
                    "backend.detect() returned unsupported result mode "
                    f"'{result_mode}'"
                )
            if not isinstance(detections, list):
                raise TypeError("backend.detect() returned a non-list detection collection")
            payload.update(
                first_inference_ready=True,
                inference={
                    "method": "detect",
                    "input_shape": [64, 64, 3],
                    "input_fill": 0,
                    "confidence": 0.99,
                    "iou": 0.3,
                    "max_detections": 1,
                    "result_mode": result_mode,
                    "detection_count": len(detections),
                },
                reason="first_inference_succeeded",
            )
    except Exception as exc:  # Runtime diagnostic boundary.
        if payload["inference_attempted"]:
            payload["reason"] = "first_inference_failed"
        payload["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if backend is not None:
            try:
                backend.unload_model()
            except Exception:
                pass

    try:
        _write_probe_result(result_descriptor, payload)
    finally:
        os.close(result_descriptor)
    return 0 if payload["first_inference_ready"] else 2


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--result-fd", type=int)
    args = parser.parse_args()
    if not args.child or args.result_fd is None:
        parser.error("this helper is invoked by check-ai-runtime.sh")
    return _run_child(args.result_fd)


if __name__ == "__main__":
    raise SystemExit(main())
