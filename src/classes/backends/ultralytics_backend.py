"""
Ultralytics (YOLO) detection backend.

Primary backend for PixEagle SmartTracker. Wraps the Ultralytics YOLO library
for object detection, tracking, and OBB support with GPU/CPU/NCNN device
management and automatic fallback.
"""

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from classes.backends.detection_backend import DetectionBackend, DevicePreference
from classes.detection_adapter import NormalizedDetection
from classes.geometry_utils import obb_xywhr_to_aabb, validate_obb_xywhr
from classes.model_artifact_policy import (
    canonical_ncnn_manifest_descriptor,
    DEFAULT_MAX_MODEL_BYTES,
    DEFAULT_MODELS_ROOT,
    HARD_MAX_MODEL_BYTES,
    ModelArtifactPolicyError,
    ModelProvenanceStore,
    ModelStoreLease,
    normalize_sha256,
    sha256_descriptor,
    validate_models_root,
)

# ── Conditional AI imports ──────────────────────────────────────────────
# Allows app to run without ultralytics/torch installed.
try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False
    logging.warning(
        "Ultralytics/lap not installed - SmartTracker disabled. "
        "Install with: bash scripts/setup/setup-pytorch.sh --mode auto && "
        "bash scripts/setup/install-ai-deps.sh"
    )
except Exception as e:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False
    logging.warning(f"Ultralytics import failed: {e} - SmartTracker disabled")

logger = logging.getLogger(__name__)
DEFAULT_CPU_MODEL_PATH = "models/yolo26n_ncnn_model"
DEFAULT_GPU_MODEL_PATH = "models/yolo26n.pt"
DEFAULT_TRACKER_TYPE = "botsort"


class UltralyticsBackend(DetectionBackend):
    """
    Ultralytics YOLO detection backend.

    Handles:
    - Model loading with GPU→CPU→NCNN fallback chain
    - Inference via model.track() and model.predict()
    - Result parsing from Ultralytics Results objects to NormalizedDetection
    - Tracker type selection (ByteTrack, BoT-SORT, Custom ReID)
    - CUDA cache management
    """

    def __init__(self, config: dict, *, models_root: Optional[Path] = None):
        self._config = config
        self._models_root = validate_models_root(
            Path(models_root or DEFAULT_MODELS_ROOT),
            create=True,
        )
        self._max_model_bytes = int(
            config.get("SMART_TRACKER_MODEL_MAX_BYTES", DEFAULT_MAX_MODEL_BYTES)
        )
        if not 0 < self._max_model_bytes <= HARD_MAX_MODEL_BYTES:
            raise ValueError(
                "SMART_TRACKER_MODEL_MAX_BYTES is outside the supported safety range"
            )
        self._trust_policy = str(
            config.get(
                "SMART_TRACKER_MODEL_TRUST_POLICY",
                "operator_ack_or_digest",
            )
            or ""
        ).strip().lower()
        if self._trust_policy not in {"operator_ack_or_digest", "digest_required"}:
            raise ValueError(
                "SMART_TRACKER_MODEL_TRUST_POLICY must be "
                "operator_ack_or_digest or digest_required"
            )
        self._model = None
        self._model_store_lease: Optional[ModelStoreLease] = None
        self._runtime_info: Dict[str, Any] = {}

        # Tracker type selection for the supported PixEagle modes.
        self.tracker_type_str, self.use_custom_reid = self._select_tracker_type()
        self.tracker_args = self._build_tracker_args()

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        return ULTRALYTICS_AVAILABLE

    @property
    def backend_name(self) -> str:
        return "ultralytics"

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    # ── Lifecycle ───────────────────────────────────────────────────────

    @staticmethod
    def _close_lease(lease: Optional[ModelStoreLease]) -> None:
        if lease is None:
            return
        try:
            lease.close()
        except Exception as exc:
            logger.error("Failed to release model-store lease: %s", exc)

    @classmethod
    def _discard_candidate_resources(cls, candidate: Dict[str, Any]) -> None:
        lease = candidate.pop("_model_store_lease", None)
        candidate.pop("_verified_record", None)
        candidate.pop("_verified_descriptor", None)
        if isinstance(lease, ModelStoreLease):
            cls._close_lease(lease)

    def load_model(
        self,
        model_path: str,
        device: DevicePreference = DevicePreference.AUTO,
        fallback_enabled: bool = True,
        context: str = "startup",
    ) -> Dict[str, Any]:
        device_str = self._normalize_device_preference(device.value if isinstance(device, DevicePreference) else device)
        model_path = self._normalize_model_path(model_path)

        attempts: List[Dict[str, Any]] = []
        fallback_reason = None
        fallback_occurred = False

        def attempt_load(candidate: Dict[str, Any]):
            try:
                model = self._load_candidate(candidate)
                attempt: Dict[str, Any] = {
                    "path": candidate["path"],
                    "backend": candidate["backend"],
                    "source": candidate["source"],
                    "success": True,
                }
                if isinstance(candidate.get("model_provenance"), dict):
                    attempt["model_provenance"] = dict(
                        candidate["model_provenance"]
                    )
                attempts.append(attempt)
                return model
            except Exception as exc:
                self._discard_candidate_resources(candidate)
                attempt = {
                    "path": candidate["path"],
                    "backend": candidate["backend"],
                    "source": candidate["source"],
                    "success": False,
                    "error": str(exc),
                }
                if isinstance(candidate.get("model_provenance"), dict):
                    attempt["model_provenance"] = dict(
                        candidate["model_provenance"]
                    )
                attempts.append(attempt)
                return None

        # Select primary candidate based on device preference
        if device_str == "cpu":
            primary = self._pick_cpu_model_candidate(model_path)
        elif device_str == "gpu":
            primary = self._pick_gpu_model_candidate(model_path)
        else:
            # auto
            primary = (
                self._pick_gpu_model_candidate(model_path)
                if self._cuda_available()
                else self._pick_cpu_model_candidate(model_path)
            )

        logger.info(
            "[SmartTracker] Model load request: "
            f"device={device_str} path={model_path} primary={primary['path']} ({primary['backend']})"
        )
        model = attempt_load(primary)

        # GPU→CPU fallback
        should_try_cpu_fallback = (
            model is None
            and primary["backend"] == "cuda"
            and fallback_enabled
        )
        if should_try_cpu_fallback:
            fallback_candidate = self._pick_cpu_model_candidate(model_path)
            logger.warning(
                "[SmartTracker] GPU load failed, attempting CPU fallback: "
                f"{fallback_candidate['path']} ({fallback_candidate['backend']})"
            )
            model = attempt_load(fallback_candidate)
            fallback_occurred = model is not None
            if fallback_occurred:
                fallback_reason = attempts[-2].get("error") if len(attempts) >= 2 else "unknown"
                primary = fallback_candidate

        if model is None:
            joined_errors = "; ".join(
                f"{a.get('backend')}:{a.get('path')} -> {a.get('error')}"
                for a in attempts if not a.get("success")
            )
            raise RuntimeError(
                "No compatible model candidate could be loaded. "
                f"attempts={len(attempts)} errors={joined_errors}"
            )

        new_lease = primary.pop("_model_store_lease", None)
        primary.pop("_verified_record", None)
        primary.pop("_verified_descriptor", None)
        try:
            if not isinstance(new_lease, ModelStoreLease):
                raise RuntimeError("Model load completed without a model-store lease")
            effective_device = "cuda" if primary["backend"] == "cuda" else "cpu"
            model_provenance = dict(primary.get("model_provenance") or {})
            new_runtime_info = {
                "requested_device": device_str,
                "effective_device": effective_device,
                "backend": primary["backend"],
                "model_path": primary["path"],
                "model_name": Path(primary["path"]).name,
                "fallback_enabled": bool(fallback_enabled),
                "fallback_occurred": fallback_occurred,
                "fallback_reason": fallback_reason,
                "resolution_source": primary["source"],
                "model_provenance": model_provenance,
                "artifact_sha256": model_provenance.get("sha256"),
                "trust_method": model_provenance.get("trust_method"),
                "context": context,
                "attempts": attempts,
            }
        except Exception:
            self._close_lease(new_lease if isinstance(new_lease, ModelStoreLease) else None)
            model = None
            raise

        previous_lease = self._model_store_lease
        previous_model = self._model
        self._model = model
        self._model_store_lease = new_lease
        self._runtime_info = new_runtime_info
        previous_model = None
        self._close_lease(previous_lease)
        return dict(self._runtime_info)

    def unload_model(self) -> None:
        model = self._model
        lease = self._model_store_lease
        self._model = None
        self._model_store_lease = None
        self._runtime_info = {}
        model = None
        try:
            self._close_lease(lease)
        finally:
            self._clear_torch_cuda_cache()

    close = unload_model

    def __del__(self) -> None:
        try:
            self.unload_model()
        except Exception:
            pass

    def switch_model(
        self,
        new_model_path: str,
        device: DevicePreference = DevicePreference.AUTO,
        fallback_enabled: bool = True,
    ) -> Dict[str, Any]:
        # Fail before replacement if local cleanup itself is unavailable. The
        # load transaction does not publish or release the prior lease on error.
        self._clear_torch_cuda_cache()
        return self.load_model(
            new_model_path,
            device,
            fallback_enabled,
            context="switch",
        )

    # ── Inference ───────────────────────────────────────────────────────

    def detect(
        self,
        frame: np.ndarray,
        conf: float = 0.3,
        iou: float = 0.3,
        max_det: int = 20,
    ) -> Tuple[str, List[NormalizedDetection]]:
        results = self._model.predict(
            frame,
            conf=conf,
            iou=iou,
            max_det=max_det,
            verbose=False,
        )
        return self._normalize_results(results)

    def detect_and_track(
        self,
        frame: np.ndarray,
        conf: float = 0.3,
        iou: float = 0.3,
        max_det: int = 20,
        tracker_type: str = "bytetrack",
        tracker_args: Optional[Dict] = None,
    ) -> Tuple[str, List[NormalizedDetection]]:
        args = tracker_args if tracker_args is not None else self.tracker_args
        results = self._model.track(
            frame,
            conf=conf,
            iou=iou,
            max_det=max_det,
            tracker=f"{tracker_type}.yaml",
            **args,
        )
        return self._normalize_results(results)

    # ── Metadata ────────────────────────────────────────────────────────

    def get_model_labels(self) -> Dict[int, str]:
        if self._model and hasattr(self._model, 'names'):
            return dict(self._model.names)
        return {}

    def get_model_task(self) -> str:
        return getattr(self._model, "task", "detect") if self._model else "detect"

    def supports_tracking(self) -> bool:
        return True  # Ultralytics supports ByteTrack/BoT-SORT

    def supports_obb(self) -> bool:
        return True  # Ultralytics supports OBB models

    def get_device_info(self) -> Dict[str, Any]:
        return dict(self._runtime_info)

    # ── Tracker Type Selection (Ultralytics-specific) ───────────────────

    def _select_tracker_type(self) -> Tuple[str, bool]:
        """
        Select and validate the configured tracker type.

        Returns:
            (tracker_name_for_ultralytics, use_custom_reid_flag)
        """
        requested_type = str(
            self._config.get('TRACKER_TYPE', DEFAULT_TRACKER_TYPE)
        ).strip().lower()

        # Map tracker types to Ultralytics tracker names
        if requested_type == 'bytetrack':
            logger.info("[SmartTracker] Using ByteTrack (fast, no ReID)")
            return "bytetrack", False
        elif requested_type == 'botsort':
            logger.info("[SmartTracker] Using BoT-SORT (better persistence, no ReID)")
            return "botsort", False
        elif requested_type == 'custom_reid':
            logger.info("[SmartTracker] Using ByteTrack + custom lightweight ReID")
            return "bytetrack", True
        else:
            logger.warning(
                f"[SmartTracker] Unsupported tracker type '{requested_type}', "
                "using supported default 'botsort' without ReID"
            )
            return "botsort", False

    def _build_tracker_args(self) -> dict:
        """
        Build tracker arguments for model.track().

        NOTE: Ultralytics does NOT accept tracker parameters directly in model.track()!
        PixEagle currently uses the tracker YAML bundled with the installed
        Ultralytics release. Only persist and verbose are passed here.
        """
        args = {"persist": True, "verbose": False}
        logger.debug(f"[SmartTracker] Tracker args: {args}")
        logger.info(f"[SmartTracker] Using Ultralytics default {self.tracker_type_str}.yaml config")
        return args

    # ── Device / Model Candidate Selection ──────────────────────────────

    @staticmethod
    def _cuda_available() -> bool:
        """Check CUDA availability safely."""
        try:
            import torch
            return bool(torch.cuda.is_available())
        except Exception:
            return False

    @staticmethod
    def _clear_torch_cuda_cache():
        """Clear CUDA cache if available; no-op otherwise."""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            return

    @staticmethod
    def _normalize_device_preference(device: str) -> str:
        normalized = (device or "auto").strip().lower()
        if normalized == "cuda":
            return "gpu"
        return normalized if normalized in ("auto", "gpu", "cpu") else "auto"

    @staticmethod
    def _normalize_model_path(model_path: str) -> str:
        # Replace Windows backslashes before Path() so Linux doesn't treat
        # them as literal filename characters.
        return str(Path(model_path.replace("\\", "/")).as_posix())

    @staticmethod
    def _is_valid_ncnn_dir(model_path: str) -> bool:
        path_obj = Path(model_path)
        if not path_obj.exists() or not path_obj.is_dir():
            return False
        return any(path_obj.glob("*.bin")) and any(path_obj.glob("*.param"))

    @staticmethod
    def _looks_like_ncnn_path(model_path: str) -> bool:
        path_obj = Path(model_path)
        return path_obj.suffix == "" and (
            path_obj.name.endswith("_ncnn_model") or UltralyticsBackend._is_valid_ncnn_dir(model_path)
        )

    @staticmethod
    def _derive_ncnn_path(pt_model_path: str) -> Optional[str]:
        pt_path = Path(pt_model_path)
        if pt_path.suffix.lower() != ".pt":
            return None
        return str((pt_path.parent / f"{pt_path.stem}_ncnn_model").as_posix())

    @staticmethod
    def _derive_pt_from_ncnn_path(ncnn_model_path: str) -> Optional[str]:
        ncnn_path = Path(ncnn_model_path)
        base_name = ncnn_path.name
        if base_name.endswith("_ncnn_model"):
            stem = base_name[:-len("_ncnn_model")]
            return str((ncnn_path.parent / f"{stem}.pt").as_posix())
        return None

    def _pick_cpu_model_candidate(self, requested_model_path: str) -> Dict[str, str]:
        """Choose best CPU candidate, preferring NCNN when available."""
        requested = self._normalize_model_path(requested_model_path)
        cpu_config_path = self._normalize_model_path(
            self._config.get('SMART_TRACKER_CPU_MODEL_PATH', DEFAULT_CPU_MODEL_PATH)
        )

        candidates: List[Dict[str, str]] = []

        def add_candidate(path: Optional[str], source: str):
            if not path:
                return
            normalized = self._normalize_model_path(path)
            backend = "cpu_ncnn" if self._looks_like_ncnn_path(normalized) else "cpu_torch"
            candidates.append({
                "path": normalized,
                "backend": backend,
                "source": source,
            })

        # First priority: requested path (if already NCNN)
        if self._looks_like_ncnn_path(requested):
            add_candidate(requested, "requested_ncnn")
            derived_pt = self._derive_pt_from_ncnn_path(requested)
            add_candidate(derived_pt, "derived_pt_from_requested_ncnn")
        elif requested.endswith(".pt"):
            derived_ncnn = self._derive_ncnn_path(requested)
            add_candidate(derived_ncnn, "derived_ncnn_from_requested_pt")
            add_candidate(requested, "requested_pt")
        else:
            add_candidate(requested, "requested_generic")

        # Second priority: configured CPU path
        if cpu_config_path != requested:
            add_candidate(cpu_config_path, "configured_cpu")
            if cpu_config_path.endswith(".pt"):
                add_candidate(self._derive_ncnn_path(cpu_config_path), "derived_ncnn_from_configured_cpu_pt")

        # Prefer existing paths first
        for candidate in candidates:
            candidate_path = Path(candidate["path"])
            if candidate["backend"] == "cpu_ncnn":
                if self._is_valid_ncnn_dir(candidate["path"]):
                    return candidate
            elif candidate_path.exists() and candidate_path.is_file():
                return candidate

        if candidates:
            return candidates[0]

        # Defensive fallback when both request and configured path are empty.
        return {
            "path": DEFAULT_CPU_MODEL_PATH,
            "backend": "cpu_ncnn",
            "source": "canonical_default",
        }

    def _pick_gpu_model_candidate(self, requested_model_path: str) -> Dict[str, str]:
        """Choose best GPU candidate (.pt), with deterministic fallback to configured GPU path."""
        requested = self._normalize_model_path(requested_model_path)
        gpu_config_path = self._normalize_model_path(
            self._config.get('SMART_TRACKER_GPU_MODEL_PATH', DEFAULT_GPU_MODEL_PATH)
        )

        candidates: List[Dict[str, str]] = []

        def add_candidate(path: Optional[str], source: str):
            if not path:
                return
            normalized = self._normalize_model_path(path)
            candidates.append({
                "path": normalized,
                "backend": "cuda",
                "source": source,
            })

        if requested.endswith(".pt"):
            add_candidate(requested, "requested_pt")
        elif self._looks_like_ncnn_path(requested):
            add_candidate(self._derive_pt_from_ncnn_path(requested), "derived_pt_from_requested_ncnn")
        else:
            add_candidate(requested if requested.endswith(".pt") else None, "requested_generic")

        if gpu_config_path != requested:
            add_candidate(gpu_config_path if gpu_config_path.endswith(".pt") else None, "configured_gpu")

        for candidate in candidates:
            path_obj = Path(candidate["path"])
            if path_obj.exists() and path_obj.is_file() and candidate["path"].endswith(".pt"):
                return candidate

        if candidates:
            return candidates[0]

        return {
            "path": DEFAULT_GPU_MODEL_PATH,
            "backend": "cuda",
            "source": "canonical_default",
        }

    def _verify_candidate_provenance(
        self,
        candidate: Dict[str, Any],
        candidate_path: Path,
        lease: ModelStoreLease,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
        """Verify one direct-child artifact against the canonical model registry."""
        expected_path = self._models_root / candidate_path.name
        if candidate_path != expected_path:
            raise ModelArtifactPolicyError(
                "Runtime model artifacts must use the canonical direct-child path "
                f"under PixEagle's configured models root: {self._models_root}"
            )
        store = ModelProvenanceStore(self._models_root)
        if candidate["backend"] == "cpu_ncnn":
            record, descriptor = store.verify_ncnn_pinned_locked(
                candidate_path,
                lease,
                max_source_bytes=self._max_model_bytes,
            )
            artifact_type = "ncnn"
        else:
            record, _, descriptor = store.verify_pt_pinned_locked(
                candidate_path,
                lease,
                max_bytes=self._max_model_bytes,
            )
            artifact_type = "pt"

        digest = normalize_sha256(record.get("sha256"), required=True)
        receipt = record.get("registration_receipt")
        publisher_bound = bool(
            record.get("trust_method") == "expected_sha256"
            and record.get("observed_sha256") == (
                record.get("source_pt_sha256") if artifact_type == "ncnn" else digest
            )
            and record.get("publisher_sha256") == (
                record.get("source_pt_sha256") if artifact_type == "ncnn" else digest
            )
            and isinstance(receipt, dict)
            and receipt.get("schema_version") == 1
            and isinstance(receipt.get("action_id"), str)
            and receipt["action_id"].startswith("model-registration-v1:")
        )
        if self._trust_policy == "digest_required" and not publisher_bound:
            lease.release_descriptor(descriptor)
            raise ModelArtifactPolicyError(
                "This deployment requires descriptor-bound publisher-digest "
                "provenance for runtime models"
            )

        provenance: Dict[str, Any] = {
            "verified": True,
            "artifact_type": artifact_type,
            "sha256": record["sha256"],
            "models_root": str(store.models_root),
            "registry_path": str(store.registry_path),
        }
        for key in (
            "size_bytes",
            "file_count",
            "source",
            "trust_method",
            "recorded_at",
            "source_pt_sha256",
            "manifest_schema_version",
            "observed_sha256",
            "publisher_sha256",
            "registration_receipt",
        ):
            if record.get(key) is not None:
                provenance[key] = record[key]
        return provenance, record, descriptor

    def _load_candidate(self, candidate: Dict[str, Any]):
        """Verify and load one local model candidate on its target device."""
        candidate_path = Path(candidate["path"]).expanduser()
        if not candidate_path.is_absolute():
            candidate_path = Path.cwd() / candidate_path
        lease = ModelStoreLease(self._models_root, exclusive=False)
        lease.__enter__()
        try:
            if candidate["backend"] == "cpu_ncnn":
                if not self._looks_like_ncnn_path(str(candidate_path)):
                    raise ValueError(
                        "UltralyticsBackend accepts only canonical NCNN export directories"
                    )
            elif candidate_path.suffix.lower() != ".pt":
                raise ValueError(
                    "UltralyticsBackend accepts only trusted .pt files or "
                    "canonical NCNN export directories"
                )

            provenance, verified_record, descriptor = self._verify_candidate_provenance(
                candidate,
                candidate_path,
                lease,
            )
            candidate["model_provenance"] = provenance
            candidate["_verified_record"] = verified_record
            candidate["_verified_descriptor"] = descriptor
            loader_binding = lease.loader_binding(
                descriptor,
                candidate_path.name,
                directory=candidate["backend"] == "cpu_ncnn",
            )
            model = YOLO(str(loader_binding.verified_path()))
            loader_binding.verified_path()
            if candidate["backend"] == "cuda":
                model.to('cuda')
            if candidate["backend"] == "cpu_ncnn":
                lease.assert_descriptor_binding(
                    candidate_path.name,
                    descriptor,
                    directory=True,
                )
                observed = canonical_ncnn_manifest_descriptor(
                    descriptor,
                    expected_uid=lease.expected_uid,
                )
                if (
                    observed["manifest_sha256"] != verified_record.get("sha256")
                    or observed["manifest"] != verified_record.get("manifest")
                ):
                    raise ModelArtifactPolicyError(
                        "NCNN export changed while the runtime loader was executing"
                    )
            else:
                lease.assert_descriptor_binding(candidate_path.name, descriptor)
                observed, _ = sha256_descriptor(
                    descriptor,
                    expected_uid=lease.expected_uid,
                    max_bytes=self._max_model_bytes,
                )
                if observed != verified_record.get("sha256"):
                    raise ModelArtifactPolicyError(
                        "Model changed while the runtime loader was executing"
                    )
            candidate["_model_store_lease"] = lease
            return model
        except BaseException:
            candidate.pop("_verified_record", None)
            candidate.pop("_verified_descriptor", None)
            lease.close()
            raise

    # ── Result Parsing (extracted from detection_adapter.py) ────────────

    @staticmethod
    def _to_list(value: Any) -> List[Any]:
        """Convert torch/numpy-like object to a Python list safely."""
        if value is None:
            return []
        try:
            if hasattr(value, "detach"):
                value = value.detach()
            if hasattr(value, "cpu"):
                value = value.cpu()
            if hasattr(value, "numpy"):
                value = value.numpy()
            if hasattr(value, "tolist"):
                return value.tolist()
        except Exception:
            pass
        if isinstance(value, list):
            return value
        return []

    @staticmethod
    def _detect_result_mode(result: Any) -> str:
        """
        Return result mode for a single Ultralytics result item.

        Returns: "detect", "obb", "mixed", or "none"
        """
        has_boxes = (
            getattr(result, "boxes", None) is not None
            and len(getattr(result.boxes, "data", [])) > 0
        )
        has_obb = (
            getattr(result, "obb", None) is not None
            and len(getattr(result.obb, "data", [])) > 0
        )
        if has_boxes and has_obb:
            return "mixed"
        if has_obb:
            return "obb"
        if has_boxes:
            return "detect"
        return "none"

    @classmethod
    def _parse_boxes(cls, result: Any) -> List[NormalizedDetection]:
        """Parse Ultralytics boxes result."""
        boxes = result.boxes
        if boxes is None:
            return []

        xyxy = cls._to_list(getattr(boxes, "xyxy", None))
        confs = cls._to_list(getattr(boxes, "conf", None))
        classes = cls._to_list(getattr(boxes, "cls", None))
        ids = cls._to_list(getattr(boxes, "id", None))

        n = min(len(xyxy), len(confs), len(classes))
        out: List[NormalizedDetection] = []
        for i in range(n):
            x1, y1, x2, y2 = xyxy[i]
            if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                continue
            aabb = (int(x1), int(y1), int(x2), int(y2))
            center = ((aabb[0] + aabb[2]) // 2, (aabb[1] + aabb[3]) // 2)
            track_id = int(ids[i]) if i < len(ids) and ids[i] is not None else -(i + 1)
            out.append(
                NormalizedDetection(
                    track_id=track_id,
                    class_id=int(classes[i]),
                    confidence=float(confs[i]),
                    aabb_xyxy=aabb,
                    center_xy=center,
                    geometry_type="aabb",
                )
            )
        return out

    @classmethod
    def _parse_obb(cls, result: Any) -> List[NormalizedDetection]:
        """Parse Ultralytics OBB result."""
        obb = result.obb
        if obb is None:
            return []

        xywhr = cls._to_list(getattr(obb, "xywhr", None))
        confs = cls._to_list(getattr(obb, "conf", None))
        classes = cls._to_list(getattr(obb, "cls", None))
        ids = cls._to_list(getattr(obb, "id", None))
        polys = cls._to_list(getattr(obb, "xyxyxyxy", None))

        n = min(len(xywhr), len(confs), len(classes))
        out: List[NormalizedDetection] = []
        for i in range(n):
            vals = xywhr[i]
            if len(vals) < 5:
                continue
            cx, cy, w, h, r = map(float, vals[:5])
            obb_xywhr = (cx, cy, w, h, r)
            if not validate_obb_xywhr(obb_xywhr):
                logger.warning("[DetectionAdapter] Skipping invalid OBB geometry")
                continue
            try:
                aabb = obb_xywhr_to_aabb(obb_xywhr)
            except Exception:
                logger.warning("[DetectionAdapter] OBB->AABB conversion failed, skipping detection")
                continue
            center = ((aabb[0] + aabb[2]) // 2, (aabb[1] + aabb[3]) // 2)
            poly = None
            if i < len(polys) and isinstance(polys[i], list) and len(polys[i]) == 4:
                poly = [(float(p[0]), float(p[1])) for p in polys[i]]
            track_id = int(ids[i]) if i < len(ids) and ids[i] is not None else -(i + 1)
            out.append(
                NormalizedDetection(
                    track_id=track_id,
                    class_id=int(classes[i]),
                    confidence=float(confs[i]),
                    aabb_xyxy=aabb,
                    center_xy=center,
                    geometry_type="obb",
                    obb_xywhr=obb_xywhr,
                    polygon_xy=poly,
                    rotation_deg=float(math.degrees(r)),
                )
            )
        return out

    @classmethod
    def _normalize_results(
        cls,
        results: Any,
        allow_mixed: bool = False,
    ) -> Tuple[str, List[NormalizedDetection]]:
        """
        Normalize Ultralytics result frame to (mode, detections).

        Raises ValueError on mixed-mode when allow_mixed=False.
        """
        if not results:
            return "none", []

        result = results[0]
        mode = cls._detect_result_mode(result)

        if mode == "mixed" and not allow_mixed:
            raise ValueError("mixed_detect_obb_output_not_supported")
        if mode == "obb":
            return mode, cls._parse_obb(result)
        if mode == "detect":
            return mode, cls._parse_boxes(result)
        if mode == "mixed":
            dets = cls._parse_obb(result)
            if not dets:
                dets = cls._parse_boxes(result)
            return mode, dets
        return "none", []
