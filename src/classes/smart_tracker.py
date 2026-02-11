# src\classes\smart_tracker.py
import cv2
import numpy as np
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Conditional AI imports - allows app to run without ultralytics/torch
# Catches ImportError (not installed) and any other errors (incompatible torch on ARM, etc.)
try:
    from ultralytics import YOLO
    # Quick sanity check that YOLO is actually usable
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False
    logging.warning(
        "Ultralytics/lap not installed - SmartTracker disabled. "
        "Install with: source venv/bin/activate && pip install --prefer-binary ultralytics lap"
    )
except Exception as e:
    # Catches RuntimeError, OSError, or other issues (e.g., incompatible torch on ARM)
    YOLO = None
    ULTRALYTICS_AVAILABLE = False
    logging.warning(f"Ultralytics import failed: {e} - SmartTracker disabled")

from classes.parameters import Parameters
from classes.detection_adapter import (
    NormalizedDetection,
    normalize_results,
    to_tracking_state_rows,
)
from classes.geometry_utils import point_in_polygon
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.tracking_state_manager import TrackingStateManager
from classes.motion_predictor import MotionPredictor
from classes.appearance_model import AppearanceModel

logger = logging.getLogger(__name__)


class HUDColors:
    """Military/surveillance HUD color palette (BGR)."""
    ACTIVE_PRIMARY     = (0, 255, 100)    # Bright green - tracked target box
    ACTIVE_RETICLE     = (0, 230, 90)     # Green - reticle tick marks
    ACTIVE_LABEL_TEXT  = (0, 255, 100)    # Green label text
    ACTIVE_LABEL_BG    = (20, 20, 20)     # Near-black label plate
    ACTIVE_FILL        = (0, 60, 25)      # Dark green tint - active box interior
    PASSIVE_BOX        = (140, 140, 140)  # Mid-grey - untracked boxes
    PASSIVE_LABEL_TEXT = (200, 200, 200)  # Bright grey label text (more readable)
    PASSIVE_LABEL_BG   = (30, 30, 30)    # Dark grey plate
    PASSIVE_FILL       = (40, 40, 40)     # Dark grey tint - passive box interior
    LOST_PRIMARY       = (0, 180, 255)    # Amber - lost target


class SmartTracker:
    def __init__(self, app_controller):
        """
        Initializes the YOLO model (supports GPU/CPU config + optional fallback).
        Model path is selected based on config flags.

        Raises:
            RuntimeError: If ultralytics/torch is not installed
        """
        # Check if AI packages are available
        if not ULTRALYTICS_AVAILABLE:
            raise RuntimeError(
                "SmartTracker requires ultralytics package. "
                "Install with: source venv/bin/activate && pip install --prefer-binary ultralytics lap\n"
                "Or re-run 'make init' and select 'Full' profile."
            )

        self.app_controller = app_controller
        use_gpu = Parameters.SmartTracker.get('SMART_TRACKER_USE_GPU', True)
        fallback_enabled = Parameters.SmartTracker.get('SMART_TRACKER_FALLBACK_TO_CPU', True)

        # Load SmartTracker configuration
        self.config = Parameters.SmartTracker

        # === Validate and Select Tracker Type ===
        self.tracker_type_str, self.use_custom_reid = self._select_tracker_type()

        self.model_task_policy = self.config.get("SMART_TRACKER_MODEL_TASK_POLICY", "auto")
        self.geometry_output_mode = self.config.get("SMART_TRACKER_GEOMETRY_OUTPUT_MODE", "hybrid")
        self.draw_oriented = self.config.get("SMART_TRACKER_DRAW_ORIENTED", True)
        self.selection_mode = self.config.get("SMART_TRACKER_SELECTION_MODE", "auto")
        self.max_oriented_tracks = int(self.config.get("SMART_TRACKER_MAX_ORIENTED_TRACKS", 100))
        self.disable_obb_globally = bool(self.config.get("SMART_TRACKER_DISABLE_OBB_GLOBALLY", False))
        self.obb_error_budget = float(self.config.get("SMART_TRACKER_OBB_AUTO_DISABLE_ERROR_RATE", 0.001))

        requested_device = "gpu" if use_gpu else "cpu"
        requested_model_path = (
            self.config.get('SMART_TRACKER_GPU_MODEL_PATH', 'yolo/yolo26n.pt')
            if use_gpu else
            self.config.get('SMART_TRACKER_CPU_MODEL_PATH', 'yolo/yolo26n_ncnn_model')
        )
        self.runtime_info: Dict[str, Any] = {}

        try:
            self.model, runtime_info = self._load_model_with_runtime_fallback(
                requested_model_path=requested_model_path,
                requested_device=requested_device,
                fallback_enabled=fallback_enabled,
                context="startup",
            )
            self.runtime_info = runtime_info
            logger.info(
                "[SmartTracker] YOLO loaded: "
                f"path={runtime_info.get('model_path')} backend={runtime_info.get('backend')} "
                f"requested={runtime_info.get('requested_device')} effective={runtime_info.get('effective_device')}"
            )
        except Exception as exc:
            logger.error(f"[SmartTracker] Failed to load YOLO model: {exc}")
            raise RuntimeError("YOLO model loading failed.") from exc

        # === Detection Parameters ===
        self.conf_threshold = self.config.get('SMART_TRACKER_CONFIDENCE_THRESHOLD', 0.3)
        self.iou_threshold = self.config.get('SMART_TRACKER_IOU_THRESHOLD', 0.3)
        self.max_det = self.config.get('SMART_TRACKER_MAX_DETECTIONS', 20)
        self.show_fps = self.config.get('SMART_TRACKER_SHOW_FPS', False)
        self.hud_style = self.config.get('SMART_TRACKER_HUD_STYLE', 'military')

        # === Build Tracker Arguments Based on Selected Type ===
        self.tracker_args = self._build_tracker_args()

        self.labels = self.model.names if hasattr(self.model, 'names') else {}
        self.model_task = getattr(self.model, "task", "detect")
        self.allow_mixed_outputs = False
        self.current_geometry_mode = "aabb"
        self.last_detections: List[NormalizedDetection] = []
        self.selected_oriented_bbox: Optional[Tuple[float, float, float, float, float]] = None
        self.selected_polygon: Optional[List[Tuple[float, float]]] = None

        self._frame_count = 0
        self._frame_errors = 0
        self._geometry_errors = 0
        self._obb_auto_disabled = False

        # Pre-allocated buffer for box fills / label plates (avoids per-detection np.full_like)
        self._fill_buf = np.zeros((600, 600, 3), dtype=np.uint8)

        self._apply_model_task_policy()

        # === Tracking state (maintained for backward compatibility and output)
        self.selected_object_id = None
        self.selected_class_id = None
        self.selected_bbox = None
        self.selected_center = None
        self.selected_oriented_bbox = None
        self.selected_polygon = None
        self.last_results = None
        # === Motion Predictor (for occlusion handling)
        # Predicts object position during brief detection loss
        prediction_enabled = self.config.get('ENABLE_PREDICTION_BUFFER', True)
        self.motion_predictor = MotionPredictor(
            history_size=self.config.get('ID_LOSS_TOLERANCE_FRAMES', 5),
            velocity_alpha=0.7  # Balanced responsiveness
        ) if prediction_enabled else None

        # === Appearance Model (for custom re-identification after long occlusions)
        # Only used when TRACKER_TYPE = "custom_reid"
        # When using "botsort_reid", Ultralytics handles ReID natively
        if self.use_custom_reid:
            appearance_enabled = self.config.get('ENABLE_APPEARANCE_MODEL', True)
            self.appearance_model = AppearanceModel(
                config=self.config
            ) if appearance_enabled else None
        else:
            self.appearance_model = None  # Not needed for Ultralytics ReID

        # === Robust Tracking State Manager
        # Handles ID matching, spatial fallback, motion prediction, and appearance re-identification
        self.tracking_manager = TrackingStateManager(
            config=self.config,
            motion_predictor=self.motion_predictor,
            appearance_model=self.appearance_model
        )

        self.fps_counter, self.fps_timer, self.fps_display = 0, time.time(), 0

        logger.info("[SmartTracker] Initialization complete.")
        logger.info(f"[SmartTracker] Tracker: {self.tracker_type_str.upper()}")
        logger.info(
            f"[SmartTracker] Inference backend: {self.runtime_info.get('backend')} "
            f"({self.runtime_info.get('effective_device')}) model={self.runtime_info.get('model_path')}"
        )
        if self.runtime_info.get("fallback_occurred"):
            logger.warning(
                f"[SmartTracker] Startup fallback occurred: {self.runtime_info.get('fallback_reason')}"
            )
        logger.info(f"[SmartTracker] Model task: {self.model_task}")
        logger.info(f"[SmartTracker] Geometry mode: {self.current_geometry_mode}")
        if self.use_custom_reid:
            logger.info(f"[SmartTracker] Custom ReID: {'enabled' if self.appearance_model else 'disabled'}")
        logger.info(f"[SmartTracker] Tracking strategy: {self.config.get('TRACKING_STRATEGY', 'hybrid')}")
        logger.info(f"[SmartTracker] Motion prediction: {'enabled' if self.motion_predictor else 'disabled'}")

    def _hud_scale(self, fh: int) -> dict:
        """Compute resolution-relative dimensions for HUD elements (480p-4K)."""
        def s(factor, minimum=1):
            return max(int(fh * factor), minimum)
        plate_alpha = float(self.config.get('SMART_TRACKER_LABEL_PLATE_OPACITY', 0.75))
        return {
            'bracket_length':            s(0.025, 8),
            'bracket_thickness':         s(0.003, 1),
            'bracket_thickness_active':  s(0.005, 2),
            'tick_length':               s(0.015, 5),
            'tick_gap':                  s(0.008, 3),
            'tick_thickness':            s(0.0025, 1),
            'crosshair_arm':             s(0.007, 3),
            'crosshair_thickness':       s(0.002, 1),
            'label_font_scale':          max(fh * 0.001, 0.40),
            'label_padding_h':           s(0.008, 5),
            'label_padding_v':           s(0.005, 4),
            'label_offset_y':            s(0.008, 4),
            'dash_length':               s(0.012, 6),
            'dash_gap':                  s(0.008, 4),
            'label_plate_alpha':         plate_alpha,
            'passive_label_plate_alpha': plate_alpha * 0.85,
            'active_fill_alpha':         0.10,
            'passive_fill_alpha':        0.08,
        }

    def _select_tracker_type(self) -> Tuple[str, bool]:
        """
        Select and validate tracker type based on config and Ultralytics version.

        Returns:
            Tuple[str, bool]: (tracker_name_for_ultralytics, use_custom_reid_flag)
        """
        requested_type = self.config.get('TRACKER_TYPE', 'botsort_reid')

        # Validate BoT-SORT ReID requirements
        if requested_type == 'botsort_reid':
            try:
                import ultralytics
                version_str = ultralytics.__version__
                # Parse version (e.g., "8.3.114" -> (8, 3, 114))
                version_parts = version_str.split('.')
                major = int(version_parts[0])
                minor = int(version_parts[1]) if len(version_parts) > 1 else 0
                patch = int(version_parts[2]) if len(version_parts) > 2 else 0
                version_tuple = (major, minor, patch)

                if version_tuple >= (8, 3, 114):
                    logger.info(f"[SmartTracker] Using BoT-SORT with native ReID (Ultralytics {version_str})")
                    return "botsort", False  # Use Ultralytics BoT-SORT with ReID
                else:
                    logger.warning(f"[SmartTracker] BoT-SORT ReID requires Ultralytics >=8.3.114, "
                                  f"found {version_str}. Falling back to custom_reid.")
                    requested_type = 'custom_reid'
            except Exception as e:
                logger.warning(f"[SmartTracker] Could not verify Ultralytics version: {e}. "
                              "Falling back to custom_reid.")
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
            return "bytetrack", True  # Use ByteTrack as base, add our custom ReID
        else:
            logger.warning(f"[SmartTracker] Unknown tracker type '{requested_type}', using bytetrack")
            return "bytetrack", False

    def _build_tracker_args(self) -> dict:
        """
        Build tracker arguments dict based on selected tracker type and config.

        NOTE: Ultralytics does NOT accept tracker parameters directly in model.track()!
        Tracker params must be in the YAML file. We only pass persist and verbose here.

        Returns:
            dict: Arguments to pass to model.track() (only persist/verbose allowed)
        """
        # ONLY persist and verbose are allowed here
        # All other tracker params must be in bytetrack.yaml or botsort.yaml
        args = {
            "persist": True,
            "verbose": False
        }

        logger.debug(f"[SmartTracker] Tracker args: {args}")
        logger.info(f"[SmartTracker] Using Ultralytics default {self.tracker_type_str}.yaml config")
        logger.info(f"[SmartTracker] Note: To customize tracker params, edit Ultralytics tracker YAML files")

        return args

    def _apply_model_task_policy(self):
        """Apply task/geometry policy and determine effective mode."""
        task = (self.model_task or "detect").lower()
        if self.model_task_policy == "detect_only" and self.geometry_output_mode == "oriented_preferred":
            logger.warning(
                "[SmartTracker] Invalid policy combo detect_only+oriented_preferred; coercing to legacy_aabb"
            )
            self.geometry_output_mode = "legacy_aabb"

        if self.disable_obb_globally:
            self.current_geometry_mode = "aabb"
            return

        if self.model_task_policy == "detect_only":
            self.current_geometry_mode = "aabb"
            return

        if task == "obb" and self.model_task_policy in ("auto", "allow_oriented"):
            self.current_geometry_mode = "obb"
            return

        self.current_geometry_mode = "aabb"

    def _should_run_track_api(self) -> bool:
        """Use track API for detection models only; OBB uses predict + local continuity."""
        return self.current_geometry_mode != "obb"

    def _cuda_available(self) -> bool:
        """Check CUDA availability safely (works even if torch import is fragile)."""
        try:
            import torch
            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def _clear_torch_cuda_cache(self):
        """Clear CUDA cache if available; no-op otherwise."""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            return

    def _normalize_device_preference(self, device: str) -> str:
        normalized = (device or "auto").strip().lower()
        return normalized if normalized in ("auto", "gpu", "cpu") else "auto"

    def _normalize_model_path(self, model_path: str) -> str:
        return str(Path(model_path).as_posix())

    def _is_valid_ncnn_dir(self, model_path: str) -> bool:
        path_obj = Path(model_path)
        if not path_obj.exists() or not path_obj.is_dir():
            return False
        return any(path_obj.glob("*.bin")) and any(path_obj.glob("*.param"))

    def _looks_like_ncnn_path(self, model_path: str) -> bool:
        path_obj = Path(model_path)
        return path_obj.suffix == "" and (
            path_obj.name.endswith("_ncnn_model") or self._is_valid_ncnn_dir(model_path)
        )

    def _derive_ncnn_path(self, pt_model_path: str) -> Optional[str]:
        pt_path = Path(pt_model_path)
        if pt_path.suffix.lower() != ".pt":
            return None
        return str((pt_path.parent / f"{pt_path.stem}_ncnn_model").as_posix())

    def _derive_pt_from_ncnn_path(self, ncnn_model_path: str) -> Optional[str]:
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
            self.config.get('SMART_TRACKER_CPU_MODEL_PATH', 'yolo/yolo26n_ncnn_model')
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

        # Prefer existing paths first; if none exist, keep first candidate and let loader error with clear message.
        for candidate in candidates:
            candidate_path = Path(candidate["path"])
            if candidate["backend"] == "cpu_ncnn":
                if self._is_valid_ncnn_dir(candidate["path"]):
                    return candidate
            elif candidate_path.exists() and candidate_path.is_file():
                return candidate

        if candidates:
            return candidates[0]

        # Hard fallback - legacy default.
        return {
            "path": "yolo/yolo26n_ncnn_model",
            "backend": "cpu_ncnn",
            "source": "hardcoded_default",
        }

    def _pick_gpu_model_candidate(self, requested_model_path: str) -> Dict[str, str]:
        """Choose best GPU candidate (.pt), with deterministic fallback to configured GPU path."""
        requested = self._normalize_model_path(requested_model_path)
        gpu_config_path = self._normalize_model_path(
            self.config.get('SMART_TRACKER_GPU_MODEL_PATH', 'yolo/yolo26n.pt')
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
            "path": "yolo/yolo26n.pt",
            "backend": "cuda",
            "source": "hardcoded_default",
        }

    def _load_candidate(self, candidate: Dict[str, str]) -> YOLO:
        """Load a single model candidate and move to target device if needed."""
        model = YOLO(candidate["path"])
        if candidate["backend"] == "cuda":
            model.to('cuda')
        return model

    def _load_model_with_runtime_fallback(
        self,
        requested_model_path: str,
        requested_device: str,
        fallback_enabled: bool,
        context: str,
    ) -> Tuple[YOLO, Dict[str, Any]]:
        """
        Resolve/load model deterministically.
        - CPU requests prefer NCNN directories.
        - GPU/auto requests prefer .pt on CUDA.
        - GPU failures can fall back to CPU when configured.
        """
        requested_device = self._normalize_device_preference(requested_device)
        requested_model_path = self._normalize_model_path(requested_model_path)

        attempts: List[Dict[str, Any]] = []
        fallback_reason = None
        fallback_occurred = False

        def attempt_load(candidate: Dict[str, str]) -> Optional[YOLO]:
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

        if requested_device == "cpu":
            primary = self._pick_cpu_model_candidate(requested_model_path)
        elif requested_device == "gpu":
            primary = self._pick_gpu_model_candidate(requested_model_path)
        else:
            # auto
            primary = (
                self._pick_gpu_model_candidate(requested_model_path)
                if self._cuda_available()
                else self._pick_cpu_model_candidate(requested_model_path)
            )

        logger.info(
            "[SmartTracker] Model load request: "
            f"device={requested_device} path={requested_model_path} primary={primary['path']} ({primary['backend']})"
        )
        model = attempt_load(primary)

        should_try_cpu_fallback = (
            model is None
            and primary["backend"] == "cuda"
            and fallback_enabled
        )
        if should_try_cpu_fallback:
            fallback_candidate = self._pick_cpu_model_candidate(requested_model_path)
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

        effective_device = "cuda" if primary["backend"] == "cuda" else "cpu"
        runtime_info = {
            "requested_device": requested_device,
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

        return model, runtime_info

    def get_runtime_info(self) -> Dict[str, Any]:
        """Expose current SmartTracker runtime info for API/UI status."""
        info = dict(self.runtime_info or {})
        info.update({
            "model_task": getattr(self, "model_task", None),
            "geometry_mode": getattr(self, "current_geometry_mode", None),
        })
        return info

    def switch_model(self, new_model_path: str, device: str = "auto") -> dict:
        """
        Hot-swap YOLO model without restarting SmartTracker.

        This method allows dynamic model switching at runtime, useful for:
        - Switching between different YOLO versions (e.g., yolo26n -> yolov8s)
        - Changing between GPU (.pt) and CPU (NCNN) models
        - Switching to custom-trained models with different classes

        Args:
            new_model_path (str): Path to the new model file (e.g., "yolo/yolo26n.pt" or "yolo/custom_model.pt")
            device (str): Device preference - "auto" (default), "gpu", or "cpu"

        Returns:
            dict: {
                "success": bool,
                "message": str,
                "model_info": {
                    "path": str,
                    "device": str,
                    "num_classes": int,
                    "class_names": dict
                }
            }
        """
        try:
            device = self._normalize_device_preference(device)
            new_model_path = self._normalize_model_path(new_model_path)
            logger.info(f"[SmartTracker] Switching model to: {new_model_path} (device={device})")

            # 1. Backup current tracking state
            backup_state = {
                "was_tracking": self.selected_object_id is not None,
                "object_id": self.selected_object_id,
                "class_id": self.selected_class_id,
                "bbox": self.selected_bbox,
                "center": self.selected_center
            }

            # 2. Clear current tracking state (will attempt restore later if compatible)
            self.clear_selection()

            old_model = self.model
            old_runtime = dict(self.runtime_info or {})
            old_device = old_runtime.get("effective_device", "unknown")

            # 3. Resolve/load new model with deterministic fallback policy
            fallback_enabled = bool(self.config.get('SMART_TRACKER_FALLBACK_TO_CPU', True))
            new_model, new_runtime = self._load_model_with_runtime_fallback(
                requested_model_path=new_model_path,
                requested_device=device,
                fallback_enabled=fallback_enabled,
                context="switch",
            )

            # 4. Switch active model
            self.model = new_model
            self.runtime_info = new_runtime

            # 5. Release old model resources after successful switch
            try:
                del old_model
            except Exception:
                pass
            self._clear_torch_cuda_cache()

            # 6. Update labels and task metadata
            self.labels = self.model.names if hasattr(self.model, 'names') else {}
            self.model_task = getattr(self.model, "task", "detect")
            self._apply_model_task_policy()
            num_classes = len(self.labels)

            # 7. Attempt to restore tracking if classes are compatible
            restore_info = ""
            tracking_restored = False
            if backup_state["was_tracking"]:
                # Check if the class ID is valid in the new model
                if backup_state["class_id"] is not None and backup_state["class_id"] < num_classes:
                    # Restore tracking state (tracking manager will re-acquire on next frame)
                    self.selected_object_id = backup_state["object_id"]
                    self.selected_class_id = backup_state["class_id"]
                    self.selected_bbox = backup_state["bbox"]
                    self.selected_center = backup_state["center"]
                    self.selected_oriented_bbox = None
                    self.selected_polygon = None

                    # Reinitialize tracking manager with backed up state
                    if self.selected_bbox and self.selected_center:
                        self.tracking_manager.start_tracking(
                            track_id=self.selected_object_id,
                            class_id=self.selected_class_id,
                            bbox=self.selected_bbox,
                            confidence=0.5,  # Placeholder confidence
                            center=self.selected_center
                        )

                    old_class_name = self.labels.get(backup_state["class_id"], "Unknown")
                    restore_info = f" Tracking restored for class '{old_class_name}'."
                    tracking_restored = True
                    logger.info(f"[SmartTracker] Tracking state restored (class {backup_state['class_id']})")
                else:
                    restore_info = f" Previous tracking cleared (class ID {backup_state['class_id']} not in new model with {num_classes} classes)."
                    logger.warning(f"[SmartTracker] Cannot restore tracking - class mismatch")

            # 8. Log success
            logger.info(
                f"[SmartTracker] Model switched successfully: "
                f"{old_device} -> {self.runtime_info.get('effective_device')} "
                f"({self.runtime_info.get('backend')})"
            )
            logger.info(f"[SmartTracker] Classes: {num_classes}")

            backend = self.runtime_info.get("backend", "unknown")
            fallback_flag = self.runtime_info.get("fallback_occurred", False)
            fallback_note = (
                f" CPU fallback triggered: {self.runtime_info.get('fallback_reason')}"
                if fallback_flag else ""
            )

            return {
                "success": True,
                "message": (
                    f"Model switched successfully to {self.runtime_info.get('model_path')} "
                    f"using backend '{backend}'.{restore_info}{fallback_note}"
                ),
                "model_info": {
                    "path": self.runtime_info.get("model_path"),
                    "device": self.runtime_info.get("effective_device"),
                    "backend": backend,
                    "num_classes": num_classes,
                    "class_names": self.labels,
                    "model_task": self.model_task,
                    "geometry_mode": self.current_geometry_mode,
                    "tracking_restored": tracking_restored,
                    "runtime": self.get_runtime_info(),
                }
            }

        except FileNotFoundError:
            error_msg = f"Model file not found: {new_model_path}"
            logger.error(f"[SmartTracker] {error_msg}")
            return {"success": False, "message": error_msg, "model_info": None}

        except Exception as e:
            # Keep currently active model/runtime if switch failed.
            logger.warning("[SmartTracker] Model switch failed, keeping previous active model.")
            try:
                if 'old_model' in locals() and old_model is not None and self.model is not old_model:
                    self.model = old_model
                    if 'old_runtime' in locals():
                        self.runtime_info = old_runtime
            except Exception:
                pass
            try:
                if 'backup_state' in locals() and backup_state.get("was_tracking"):
                    class_id = backup_state.get("class_id")
                    if class_id is not None and class_id < len(self.labels):
                        self.selected_object_id = backup_state.get("object_id")
                        self.selected_class_id = class_id
                        self.selected_bbox = backup_state.get("bbox")
                        self.selected_center = backup_state.get("center")
                        self.selected_oriented_bbox = None
                        self.selected_polygon = None
                        if self.selected_bbox and self.selected_center:
                            self.tracking_manager.start_tracking(
                                track_id=self.selected_object_id,
                                class_id=self.selected_class_id,
                                bbox=self.selected_bbox,
                                confidence=0.5,
                                center=self.selected_center
                            )
            except Exception:
                pass
            error_msg = f"Failed to switch model: {str(e)}"
            logger.error(f"[SmartTracker] {error_msg}")
            logger.exception(e)
            return {"success": False, "message": error_msg, "model_info": None}

    def get_center(self, x1: int, y1: int, x2: int, y2: int) -> Tuple[int, int]:
        """Calculate center point from bounding box corners."""
        return (x1 + x2) // 2, (y1 + y2) // 2

    def compute_iou(self, box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]) -> float:
        """Computes Intersection-over-Union between two boxes."""
        x1, y1, x2, y2 = box1
        x1_p, y1_p, x2_p, y2_p = box2
        xi1, yi1 = max(x1, x1_p), max(y1, y1_p)
        xi2, yi2 = min(x2, x2_p), min(y2, y2_p)
        inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        box1_area = (x2 - x1) * (y2 - y1)
        box2_area = (x2_p - x1_p) * (y2_p - y1_p)
        union_area = box1_area + box2_area - inter_area
        return inter_area / union_area if union_area > 0 else 0

    # === HUD Drawing Methods ===

    def draw_corner_brackets(self, frame, x1, y1, x2, y2, color, thickness, bracket_len):
        """Draw 4 L-shaped corner brackets instead of a full rectangle."""
        bl = min(bracket_len, (x2 - x1) // 4, (y2 - y1) // 4)
        bl = max(bl, 4)
        # Top-left
        cv2.line(frame, (x1, y1), (x1 + bl, y1), color, thickness, cv2.LINE_AA)
        cv2.line(frame, (x1, y1), (x1, y1 + bl), color, thickness, cv2.LINE_AA)
        # Top-right
        cv2.line(frame, (x2, y1), (x2 - bl, y1), color, thickness, cv2.LINE_AA)
        cv2.line(frame, (x2, y1), (x2, y1 + bl), color, thickness, cv2.LINE_AA)
        # Bottom-left
        cv2.line(frame, (x1, y2), (x1 + bl, y2), color, thickness, cv2.LINE_AA)
        cv2.line(frame, (x1, y2), (x1, y2 - bl), color, thickness, cv2.LINE_AA)
        # Bottom-right
        cv2.line(frame, (x2, y2), (x2 - bl, y2), color, thickness, cv2.LINE_AA)
        cv2.line(frame, (x2, y2), (x2, y2 - bl), color, thickness, cv2.LINE_AA)

    def draw_box_fill(self, frame, x1, y1, x2, y2, color, alpha):
        """Draw a very subtle transparent color fill inside a bounding box."""
        bx1, by1 = max(0, x1), max(0, y1)
        bx2, by2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        h, w = by2 - by1, bx2 - bx1
        if h > 0 and w > 0:
            roi = frame[by1:by2, bx1:bx2]
            # Grow pre-allocated buffer if needed (rare, only on first large detection)
            if h > self._fill_buf.shape[0] or w > self._fill_buf.shape[1]:
                self._fill_buf = np.zeros((max(h, self._fill_buf.shape[0]),
                                           max(w, self._fill_buf.shape[1]), 3), dtype=np.uint8)
            buf = self._fill_buf[:h, :w]
            buf[:] = color
            cv2.addWeighted(buf, alpha, roi, 1.0 - alpha, 0, roi)

    def draw_hud_label(self, frame, text, x1, y1, color_text, color_bg, bg_alpha, s):
        """Draw a label with semi-transparent dark plate above the bounding box."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = s['label_font_scale']
        thickness = max(1, int(font_scale * 2.5))
        ph, pv = s['label_padding_h'], s['label_padding_v']
        (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)

        # Position above the box; fall back to below-top-edge if near frame top
        label_y = y1 - s['label_offset_y']
        if label_y - th - pv * 2 < 0:
            label_y = y1 + th + pv * 2 + s['label_offset_y']

        plate_x1 = max(0, x1)
        plate_y1 = max(0, label_y - th - pv * 2)
        plate_x2 = min(frame.shape[1], plate_x1 + tw + ph * 2)
        plate_y2 = min(frame.shape[0], label_y + pv)

        # Semi-transparent plate via small ROI blend (reuses pre-allocated buffer)
        ph_roi = plate_y2 - plate_y1
        pw_roi = plate_x2 - plate_x1
        if ph_roi > 0 and pw_roi > 0:
            roi = frame[plate_y1:plate_y2, plate_x1:plate_x2]
            if ph_roi > self._fill_buf.shape[0] or pw_roi > self._fill_buf.shape[1]:
                self._fill_buf = np.zeros((max(ph_roi, self._fill_buf.shape[0]),
                                           max(pw_roi, self._fill_buf.shape[1]), 3), dtype=np.uint8)
            buf = self._fill_buf[:ph_roi, :pw_roi]
            buf[:] = color_bg
            cv2.addWeighted(buf, bg_alpha, roi, 1.0 - bg_alpha, 0, roi)

        # Text with dark outline for contrast
        text_x = plate_x1 + ph
        text_y = label_y - pv
        cv2.putText(frame, text, (text_x, text_y), font, font_scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
        cv2.putText(frame, text, (text_x, text_y), font, font_scale, color_text, thickness, cv2.LINE_AA)

    def draw_tracking_reticle(self, frame, bbox, color, s):
        """Draw 4 short tick marks at box midpoints + center crosshair."""
        x1, y1, x2, y2 = bbox
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        tl = s['tick_length']
        tg = s['tick_gap']
        tt = s['tick_thickness']
        ca = s['crosshair_arm']
        ct = s['crosshair_thickness']

        # Tick marks extending outward from box midpoints
        cv2.line(frame, (cx, y1 - tg), (cx, y1 - tg - tl), color, tt, cv2.LINE_AA)  # top
        cv2.line(frame, (cx, y2 + tg), (cx, y2 + tg + tl), color, tt, cv2.LINE_AA)  # bottom
        cv2.line(frame, (x1 - tg, cy), (x1 - tg - tl, cy), color, tt, cv2.LINE_AA)  # left
        cv2.line(frame, (x2 + tg, cy), (x2 + tg + tl, cy), color, tt, cv2.LINE_AA)  # right

        # Center crosshair
        cv2.line(frame, (cx - ca, cy), (cx + ca, cy), color, ct, cv2.LINE_AA)
        cv2.line(frame, (cx, cy - ca), (cx, cy + ca), color, ct, cv2.LINE_AA)

    def draw_dashed_box(self, frame, x1, y1, x2, y2, color, thickness, dash_len, gap):
        """Draw a dashed rectangle along all 4 edges."""
        edges = [
            ((x1, y1), (x2, y1)),  # top
            ((x2, y1), (x2, y2)),  # right
            ((x2, y2), (x1, y2)),  # bottom
            ((x1, y2), (x1, y1)),  # left
        ]
        for (ex1, ey1), (ex2, ey2) in edges:
            dx, dy = ex2 - ex1, ey2 - ey1
            length = max(1, int((dx**2 + dy**2) ** 0.5))
            step = dash_len + gap
            for i in range(0, length, step):
                t0 = i / length
                t1 = min((i + dash_len) / length, 1.0)
                pt1 = (int(ex1 + dx * t0), int(ey1 + dy * t0))
                pt2 = (int(ex1 + dx * t1), int(ey1 + dy * t1))
                cv2.line(frame, pt1, pt2, color, thickness, cv2.LINE_AA)

    def select_object_by_click(self, x, y):
        """
        User selects an object by clicking on it.
        Initializes tracking_manager with the selected object.
        """
        if self.last_results is None:
            logger.warning("[SmartTracker] No YOLO results yet, click ignored.")
            return

        min_area = float('inf')
        best_match = None

        # Find smallest matching detection, oriented first if configured.
        for det in self.last_detections:
            x1, y1, x2, y2 = det.aabb_xyxy
            contains = False
            if self.selection_mode in ("auto", "oriented") and det.polygon_xy:
                contains = point_in_polygon((x, y), det.polygon_xy)
            if not contains and self.selection_mode in ("auto", "aabb"):
                contains = (x1 <= x <= x2 and y1 <= y <= y2)
            if not contains:
                continue

            area = max(1, (x2 - x1) * (y2 - y1))
            if area < min_area:
                min_area = area
                best_match = (
                    det.track_id,
                    det.class_id,
                    det.aabb_xyxy,
                    det.confidence,
                    det.obb_xywhr,
                    det.polygon_xy,
                )

        if best_match:
            track_id, class_id, bbox, confidence, oriented_bbox, polygon_xy = best_match
            center = self.get_center(*bbox)

            # Update local state (for backward compatibility)
            self.selected_object_id = track_id
            self.selected_class_id = class_id
            self.selected_bbox = bbox
            self.selected_center = center
            self.selected_oriented_bbox = oriented_bbox
            self.selected_polygon = polygon_xy

            # Initialize tracking manager with robust tracking
            self.tracking_manager.start_tracking(
                track_id=track_id,
                class_id=class_id,
                bbox=bbox,
                confidence=confidence,
                center=center
            )

            label = self.labels.get(class_id, str(class_id))
            logger.info(f"[SMART] Tracking started: {label} ID:{track_id} (conf={confidence:.2f})")
        else:
            logger.info("[SmartTracker] No object matched click location.")

    def clear_selection(self):
        """
        Clears the currently selected object for tracking.
        Also clears tracking_manager state.
        """
        self.selected_object_id = None
        self.selected_class_id = None
        self.selected_bbox = None
        self.selected_center = None
        self.selected_oriented_bbox = None
        self.selected_polygon = None

        # Clear tracking manager state
        self.tracking_manager.clear()

        logger.info("[SmartTracker] Tracking cleared")

    def track_and_draw(self, frame: np.ndarray) -> np.ndarray:
        """
        Runs YOLO detection + tracking, draws overlays, and returns the annotated frame.
        Uses TrackingStateManager for robust ID tracking with spatial fallback.
        """
        self._frame_count += 1
        t0 = time.perf_counter()
        try:
            if self._should_run_track_api():
                results = self.model.track(
                    frame,
                    conf=self.conf_threshold,
                    iou=self.iou_threshold,
                    max_det=self.max_det,
                    tracker=f"{self.tracker_type_str}.yaml",
                    **self.tracker_args
                )
            else:
                results = self.model.predict(
                    frame,
                    conf=self.conf_threshold,
                    iou=self.iou_threshold,
                    max_det=self.max_det,
                    verbose=False,
                )
            self.last_results = results
        except Exception as exc:
            self._frame_errors += 1
            logger.error(f"[SmartTracker] Inference failure: {exc}")
            return frame

        try:
            _, self.last_detections = normalize_results(results, allow_mixed=self.allow_mixed_outputs)
        except Exception as exc:
            self._frame_errors += 1
            self._geometry_errors += 1
            logger.error(f"[SmartTracker] Detection normalization failure: {exc}")
            self.last_detections = []

        if self.current_geometry_mode == "obb" and len(self.last_detections) > self.max_oriented_tracks:
            self.last_detections = self.last_detections[:self.max_oriented_tracks]

        if self.current_geometry_mode == "obb" and self._frame_count > 0:
            err_rate = self._geometry_errors / float(self._frame_count)
            if err_rate > self.obb_error_budget and not self._obb_auto_disabled:
                logger.warning(
                    f"[SmartTracker] OBB auto-disabled due to error budget breach: {err_rate:.4f}"
                )
                self._obb_auto_disabled = True
                self.current_geometry_mode = "aabb"

        # === Use TrackingStateManager for robust tracking ===
        detections_list = to_tracking_state_rows(self.last_detections)

        # Update tracking state using TrackingStateManager (handles ID + spatial + appearance matching)
        is_tracking_active, selected_detection = self.tracking_manager.update_tracking(
            detections_list,
            self.compute_iou,
            frame  # Pass frame for appearance matching
        )

        # Bridge TrackingStateManager result schema to local drawing logic safely.
        # Some manager states (e.g., terminal loss reports) intentionally omit track_id.
        selected_track_id: Optional[int] = None
        if isinstance(selected_detection, dict):
            raw_selected_track_id = selected_detection.get('track_id')
            if raw_selected_track_id is not None:
                try:
                    selected_track_id = int(raw_selected_track_id)
                except (TypeError, ValueError):
                    logger.warning(
                        f"[SMART] Ignoring invalid selected track id value: {raw_selected_track_id}"
                    )

            if selected_detection.get('need_reselection'):
                loss_reason = selected_detection.get('loss_reason', 'unknown')
                logger.info(f"[SMART] Tracking exhausted; reselection required (reason={loss_reason})")
                self.tracking_manager.clear()
                selected_track_id = None
                is_tracking_active = False

        # Compute HUD scale factors once per frame
        s = self._hud_scale(frame.shape[0])
        show_passive_labels = self.config.get('SMART_TRACKER_SHOW_PASSIVE_LABELS', True)

        # --- Pass 1: Draw passive (untracked) detections first (back layer) ---
        for det in self.last_detections:
            x1, y1, x2, y2 = det.aabb_xyxy
            track_id = int(det.track_id)
            class_id = int(det.class_id)

            is_selected = (selected_track_id is not None and track_id == selected_track_id)
            if is_selected:
                continue  # Draw active target in pass 2

            label_name = self.labels.get(class_id, str(class_id))

            # Subtle interior shading
            self.draw_box_fill(frame, x1, y1, x2, y2, HUDColors.PASSIVE_FILL, s['passive_fill_alpha'])

            if self.draw_oriented and det.polygon_xy:
                pts = np.array([[int(px), int(py)] for px, py in det.polygon_xy], dtype=np.int32)
                cv2.polylines(frame, [pts], isClosed=True, color=HUDColors.PASSIVE_BOX,
                              thickness=s['bracket_thickness'])
            else:
                self.draw_dashed_box(frame, x1, y1, x2, y2, HUDColors.PASSIVE_BOX,
                                     s['bracket_thickness'], s['dash_length'], s['dash_gap'])

            if show_passive_labels:
                passive_label = f"{label_name.upper()} {track_id:02d}"
                self.draw_hud_label(frame, passive_label, x1, y1,
                                    HUDColors.PASSIVE_LABEL_TEXT, HUDColors.PASSIVE_LABEL_BG,
                                    s['passive_label_plate_alpha'], s)

        # --- Pass 2: Draw active tracked target on top ---
        for det in self.last_detections:
            x1, y1, x2, y2 = det.aabb_xyxy
            track_id = int(det.track_id)
            class_id = int(det.class_id)
            conf = float(det.confidence)

            is_selected = (selected_track_id is not None and track_id == selected_track_id)
            if not is_selected:
                continue

            label_name = self.labels.get(class_id, str(class_id))

            # Update local state (for backward compatibility)
            self.selected_object_id = track_id
            self.selected_class_id = class_id
            self.selected_bbox = (x1, y1, x2, y2)
            self.selected_center = self.get_center(x1, y1, x2, y2)
            self.selected_oriented_bbox = det.obb_xywhr
            self.selected_polygon = det.polygon_xy

            # Continuously update classic tracker's override with latest detection
            if self.app_controller.tracker and hasattr(self.app_controller.tracker, 'set_external_override'):
                self.app_controller.tracker.set_external_override(
                    self.selected_bbox,
                    self.selected_center
                )

            # Subtle interior shading (green tint for active)
            self.draw_box_fill(frame, x1, y1, x2, y2, HUDColors.ACTIVE_FILL, s['active_fill_alpha'])

            # Draw OBB polygon or corner brackets
            if self.draw_oriented and det.polygon_xy:
                pts = np.array([[int(px), int(py)] for px, py in det.polygon_xy], dtype=np.int32)
                cv2.polylines(frame, [pts], isClosed=True, color=HUDColors.ACTIVE_PRIMARY,
                              thickness=s['bracket_thickness_active'])
            else:
                self.draw_corner_brackets(frame, x1, y1, x2, y2, HUDColors.ACTIVE_PRIMARY,
                                          s['bracket_thickness_active'], s['bracket_length'])

            # Reticle tick marks + center crosshair
            self.draw_tracking_reticle(frame, (x1, y1, x2, y2), HUDColors.ACTIVE_RETICLE, s)

            # Active label plate
            active_label = f"{label_name.upper()} {track_id:02d} | {conf:.0%}"
            self.draw_hud_label(frame, active_label, x1, y1,
                                HUDColors.ACTIVE_LABEL_TEXT, HUDColors.ACTIVE_LABEL_BG,
                                s['label_plate_alpha'], s)

        # Update app controller tracking status
        self.app_controller.tracking_started = is_tracking_active

        # If tracking is lost, clear local state AND classic tracker override
        if not is_tracking_active and (self.selected_object_id is not None):
            logger.info(f"[SMART] Track lost: ID:{self.selected_object_id}")
            self.selected_object_id = None
            self.selected_class_id = None
            self.selected_bbox = None
            self.selected_center = None
            self.selected_oriented_bbox = None
            self.selected_polygon = None

            # Clear classic tracker override to remove visual scope
            if self.app_controller.tracker and hasattr(self.app_controller.tracker, 'clear_external_override'):
                self.app_controller.tracker.clear_external_override()

        # FPS Counter
        if self.show_fps:
            self.fps_counter += 1
            if time.time() - self.fps_timer >= 1.0:
                self.fps_display = self.fps_counter
                self.fps_counter = 0
                self.fps_timer = time.time()
            self.draw_hud_label(frame, f"FPS {self.fps_display}", 10, 30,
                                HUDColors.ACTIVE_LABEL_TEXT, HUDColors.ACTIVE_LABEL_BG,
                                s['label_plate_alpha'], s)

        self.last_frame_processing_ms = (time.perf_counter() - t0) * 1000.0
        return frame

    def get_output(self) -> TrackerOutput:
        """
        Returns SmartTracker output in the new flexible schema format.

        Returns:
            TrackerOutput: YOLO-based tracker data with multi-target support
        """
        # Check if we have an active selection
        tracking_active = (self.selected_object_id is not None and
                          self.selected_bbox is not None and
                          self.selected_center is not None)

        # Prepare multi-target data if available
        targets = []
        for det in self.last_detections:
            x1, y1, x2, y2 = det.aabb_xyxy
            target_data = {
                'target_id': det.track_id,
                'class_id': det.class_id,
                'class_name': self.labels.get(det.class_id, str(det.class_id)),
                'bbox': (x1, y1, x2 - x1, y2 - y1),  # x,y,w,h (legacy-safe)
                'center': self.get_center(x1, y1, x2, y2),
                'confidence': det.confidence,
                'is_selected': det.track_id == self.selected_object_id,
                'geometry_type': det.geometry_type,
            }
            if det.obb_xywhr:
                cx, cy, w, h, r = det.obb_xywhr
                target_data['oriented_bbox'] = (cx, cy, w, h, float(np.degrees(r)))
            if det.polygon_xy:
                target_data['polygon'] = det.polygon_xy
                target_data['normalized_polygon'] = self._normalize_polygon(det.polygon_xy)
            targets.append(target_data)

        # Use MULTI_TARGET only if we have detections, otherwise use POSITION_2D to avoid schema error
        data_type = TrackerDataType.MULTI_TARGET if len(targets) > 0 else TrackerDataType.POSITION_2D

        return TrackerOutput(
            data_type=data_type,
            timestamp=time.time(),
            tracking_active=tracking_active,
            tracker_id=f"SmartTracker_{id(self)}",

            # Primary target data (selected object)
            position_2d=self._normalize_center(self.selected_center) if self.selected_center else None,
            bbox=self._convert_bbox_format(self.selected_bbox) if self.selected_bbox else None,
            normalized_bbox=self._normalize_bbox(self.selected_bbox) if self.selected_bbox else None,
            geometry_type="obb" if self.selected_oriented_bbox else "aabb",
            oriented_bbox=self._get_selected_oriented_bbox_degrees(),
            polygon=self.selected_polygon,
            normalized_polygon=self._normalize_polygon(self.selected_polygon) if self.selected_polygon else None,
            confidence=self._get_selected_confidence(),

            # Multi-target data (only included if we have targets)
            target_id=self.selected_object_id,
            targets=targets if len(targets) > 0 else None,  # Set to None if empty to pass validation

            quality_metrics={
                'detection_count': len(targets),
                'fps': self.fps_display,
                'model_confidence_threshold': self.conf_threshold,
                'frame_processing_ms': getattr(self, "last_frame_processing_ms", 0.0),
                'frame_error_rate': (self._frame_errors / self._frame_count) if self._frame_count else 0.0,
                'geometry_error_rate': (self._geometry_errors / self._frame_count) if self._frame_count else 0.0,
            },

            raw_data={
                'yolo_results': [
                    {
                        'track_id': d.track_id,
                        'class_id': d.class_id,
                        'confidence': d.confidence,
                        'aabb_xyxy': d.aabb_xyxy,
                        'geometry_type': d.geometry_type,
                    } for d in self.last_detections
                ],
                'selected_class_id': self.selected_class_id,
                'tracker_type': self.tracker_type_str,
                'device': self.runtime_info.get('effective_device')
                          if isinstance(self.runtime_info, dict)
                          else (str(self.model.device) if hasattr(self.model, 'device') else 'unknown'),
                'backend': self.runtime_info.get('backend') if isinstance(self.runtime_info, dict) else 'unknown',
                'model_path': self.runtime_info.get('model_path') if isinstance(self.runtime_info, dict) else None,
                'fallback_occurred': self.runtime_info.get('fallback_occurred', False)
                                     if isinstance(self.runtime_info, dict) else False,
                'fallback_reason': self.runtime_info.get('fallback_reason')
                                   if isinstance(self.runtime_info, dict) else None,
                'model_task': self.model_task,
                'geometry_mode': self.current_geometry_mode,
                'obb_auto_disabled': self._obb_auto_disabled,
            },

            metadata={
                'tracker_class': self.__class__.__name__,
                'tracker_algorithm': 'YOLO + ByteTrack',
                'model_type': 'YOLO',
                'supports_multi_target': True,
                'supports_classification': True,
                'real_time': True,
                'detection_classes': list(self.labels.keys()) if self.labels else [],
                'geometry_output_mode': self.geometry_output_mode,
                'model_task_policy': self.model_task_policy,
            }
        )

    def get_capabilities(self) -> dict:
        """
        Returns SmartTracker capabilities.
        
        Returns:
            dict: SmartTracker-specific capabilities
        """
        return {
            'data_types': [TrackerDataType.MULTI_TARGET.value],
            'supports_confidence': True,
            'supports_velocity': False,  # YOLO doesn't directly provide velocity
            'supports_bbox': True,
            'supports_normalization': True,
            'supports_multi_target': True,
            'supports_classification': True,
            'supports_oriented_bbox': True,
            'estimator_available': False,
            'multi_target': True,
            'real_time': True,
            'tracker_algorithm': 'YOLO + ByteTrack',
            'accuracy_rating': 'very_high',
            'speed_rating': 'high' if hasattr(self.model, 'device') and 'cuda' in str(self.model.device) else 'medium',
            'detection_classes': len(self.labels) if self.labels else 0,
            'geometry_mode': self.current_geometry_mode,
        }

    def _normalize_center(self, center):
        """Normalize center coordinates to [-1, 1] range."""
        if not center or not hasattr(self.app_controller, 'video_handler'):
            return None
        
        video_handler = self.app_controller.video_handler
        if not video_handler:
            return None
            
        frame_width, frame_height = video_handler.width, video_handler.height
        x, y = center
        norm_x = (x - frame_width / 2) / (frame_width / 2)
        norm_y = (y - frame_height / 2) / (frame_height / 2)
        return (norm_x, norm_y)

    def _normalize_bbox(self, bbox):
        """Normalize bounding box coordinates."""
        if not bbox or not hasattr(self.app_controller, 'video_handler'):
            return None
            
        video_handler = self.app_controller.video_handler
        if not video_handler:
            return None
            
        frame_width, frame_height = video_handler.width, video_handler.height
        x1, y1, x2, y2 = bbox
        w, h = x2 - x1, y2 - y1
        x, y = x1, y1
        
        norm_x = (x - frame_width / 2) / (frame_width / 2)
        norm_y = (y - frame_height / 2) / (frame_height / 2)
        norm_w = w / frame_width
        norm_h = h / frame_height
        return (norm_x, norm_y, norm_w, norm_h)

    def _convert_bbox_format(self, bbox):
        """Convert x1,y1,x2,y2 to x,y,w,h format."""
        if not bbox:
            return None
        x1, y1, x2, y2 = bbox
        return (x1, y1, x2 - x1, y2 - y1)

    def _normalize_polygon(self, polygon):
        """Normalize polygon coordinates to [-1, 1]."""
        if not polygon or not hasattr(self.app_controller, 'video_handler'):
            return None
        video_handler = self.app_controller.video_handler
        if not video_handler:
            return None
        frame_width, frame_height = video_handler.width, video_handler.height
        out = []
        for x, y in polygon:
            nx = (x - frame_width / 2) / (frame_width / 2)
            ny = (y - frame_height / 2) / (frame_height / 2)
            out.append((nx, ny))
        return out

    def _get_selected_oriented_bbox_degrees(self):
        """Return selected oriented bbox in degree representation."""
        if not self.selected_oriented_bbox:
            return None
        cx, cy, w, h, r = self.selected_oriented_bbox
        return (cx, cy, w, h, float(np.degrees(r)))

    def _get_selected_confidence(self):
        """Get confidence of the selected object."""
        if self.selected_object_id is None:
            return None
        for det in self.last_detections:
            if det.track_id == self.selected_object_id:
                return float(det.confidence)
        return None
