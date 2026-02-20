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
        "Install with: source venv/bin/activate && pip install --prefer-binary ultralytics lap"
    )
except Exception as e:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False
    logging.warning(f"Ultralytics import failed: {e} - SmartTracker disabled")

logger = logging.getLogger(__name__)


class UltralyticsBackend(DetectionBackend):
    """
    Ultralytics YOLO detection backend.

    Handles:
    - Model loading with GPU→CPU→NCNN fallback chain
    - Inference via model.track() and model.predict()
    - Result parsing from Ultralytics Results objects to NormalizedDetection
    - Tracker type selection (ByteTrack, BoT-SORT, BoT-SORT+ReID, Custom ReID)
    - CUDA cache management
    """

    def __init__(self, config: dict):
        self._config = config
        self._model = None
        self._runtime_info: Dict[str, Any] = {}

        # Tracker type selection (Ultralytics-specific: depends on version)
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

        def attempt_load(candidate: Dict[str, str]):
            try:
                model = self._load_candidate(candidate)
                attempts.append({
                    "path": candidate["path"],
                    "backend": candidate["backend"],
                    "source": candidate["source"],
                    "success": True,
                })
                return model
            except Exception as exc:
                attempts.append({
                    "path": candidate["path"],
                    "backend": candidate["backend"],
                    "source": candidate["source"],
                    "success": False,
                    "error": str(exc),
                })
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

        self._model = model
        effective_device = "cuda" if primary["backend"] == "cuda" else "cpu"
        self._runtime_info = {
            "requested_device": device_str,
            "effective_device": effective_device,
            "backend": primary["backend"],
            "model_path": primary["path"],
            "model_name": Path(primary["path"]).name,
            "fallback_enabled": bool(fallback_enabled),
            "fallback_occurred": fallback_occurred,
            "fallback_reason": fallback_reason,
            "resolution_source": primary["source"],
            "context": context,
            "attempts": attempts,
        }
        return dict(self._runtime_info)

    def unload_model(self) -> None:
        if self._model is not None:
            del self._model
            self._model = None
        self._clear_torch_cuda_cache()
        self._runtime_info = {}

    def switch_model(
        self,
        new_model_path: str,
        device: DevicePreference = DevicePreference.AUTO,
        fallback_enabled: bool = True,
    ) -> Dict[str, Any]:
        old_model = self._model
        old_runtime = dict(self._runtime_info)
        try:
            runtime_info = self.load_model(
                new_model_path, device, fallback_enabled, context="switch"
            )
            # Clean up old model after successful load
            try:
                del old_model
            except Exception:
                pass
            self._clear_torch_cuda_cache()
            return runtime_info
        except Exception:
            # Restore old model on failure (atomic swap guarantee)
            self._model = old_model
            self._runtime_info = old_runtime
            raise

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
        Select and validate tracker type based on config and Ultralytics version.

        Returns:
            (tracker_name_for_ultralytics, use_custom_reid_flag)
        """
        requested_type = self._config.get('TRACKER_TYPE', 'botsort_reid')

        # Validate BoT-SORT ReID requirements
        if requested_type == 'botsort_reid':
            try:
                import ultralytics
                version_str = ultralytics.__version__
                version_parts = version_str.split('.')
                major = int(version_parts[0])
                minor = int(version_parts[1]) if len(version_parts) > 1 else 0
                patch = int(version_parts[2]) if len(version_parts) > 2 else 0
                version_tuple = (major, minor, patch)

                if version_tuple >= (8, 3, 114):
                    logger.info(f"[SmartTracker] Using BoT-SORT with native ReID (Ultralytics {version_str})")
                    return "botsort", False
                else:
                    logger.warning(
                        f"[SmartTracker] BoT-SORT ReID requires Ultralytics >=8.3.114, "
                        f"found {version_str}. Falling back to custom_reid."
                    )
                    requested_type = 'custom_reid'
            except Exception as e:
                logger.warning(
                    f"[SmartTracker] Could not verify Ultralytics version: {e}. "
                    "Falling back to custom_reid."
                )
                requested_type = 'custom_reid'

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
            logger.warning(f"[SmartTracker] Unknown tracker type '{requested_type}', using bytetrack")
            return "bytetrack", False

    def _build_tracker_args(self) -> dict:
        """
        Build tracker arguments for model.track().

        NOTE: Ultralytics does NOT accept tracker parameters directly in model.track()!
        Tracker params must be in the YAML file. Only persist and verbose are allowed.
        """
        args = {"persist": True, "verbose": False}
        logger.debug(f"[SmartTracker] Tracker args: {args}")
        logger.info(f"[SmartTracker] Using Ultralytics default {self.tracker_type_str}.yaml config")
        logger.info("[SmartTracker] Note: To customize tracker params, edit Ultralytics tracker YAML files")
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
            self._config.get('SMART_TRACKER_CPU_MODEL_PATH', 'models/yolo26n_ncnn_model')
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

        # Hard fallback — legacy default
        return {
            "path": "models/yolo26n_ncnn_model",
            "backend": "cpu_ncnn",
            "source": "hardcoded_default",
        }

    def _pick_gpu_model_candidate(self, requested_model_path: str) -> Dict[str, str]:
        """Choose best GPU candidate (.pt), with deterministic fallback to configured GPU path."""
        requested = self._normalize_model_path(requested_model_path)
        gpu_config_path = self._normalize_model_path(
            self._config.get('SMART_TRACKER_GPU_MODEL_PATH', 'models/yolo26n.pt')
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
            "path": "models/yolo26n.pt",
            "backend": "cuda",
            "source": "hardcoded_default",
        }

    def _load_candidate(self, candidate: Dict[str, str]):
        """Load a single model candidate and move to target device if needed."""
        model = YOLO(candidate["path"])
        if candidate["backend"] == "cuda":
            model.to('cuda')
        return model

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
