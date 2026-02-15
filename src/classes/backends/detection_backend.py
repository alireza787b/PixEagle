"""
Abstract detection backend interface.

Defines the contract for all detection/inference backends used by SmartTracker.
Backends handle model loading, device management, inference, and result parsing.
SmartTracker consumes this interface exclusively — it never imports YOLO or any
other framework directly.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from classes.detection_adapter import NormalizedDetection


class DevicePreference(Enum):
    """Preferred compute device for model inference."""
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"


class DetectionBackend(ABC):
    """
    Abstract detection backend.

    Implementations handle:
    - Model lifecycle (load, unload, hot-swap)
    - Inference with optional built-in tracking
    - Device selection with fallback chains
    - Result normalization to NormalizedDetection
    """

    # ── Properties ──────────────────────────────────────────────────────

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether this backend's dependencies are installed and importable."""
        ...

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable backend identifier (e.g., 'ultralytics', 'onnxruntime')."""
        ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Whether a model is currently loaded and ready for inference."""
        ...

    # ── Lifecycle ───────────────────────────────────────────────────────

    @abstractmethod
    def load_model(
        self,
        model_path: str,
        device: DevicePreference = DevicePreference.AUTO,
        fallback_enabled: bool = True,
        context: str = "startup",
    ) -> Dict[str, Any]:
        """
        Load a model with optional GPU→CPU fallback.

        Args:
            model_path: Path to model file (e.g., "models/yolo11n.pt")
            device: Preferred compute device
            fallback_enabled: Allow GPU→CPU fallback on failure
            context: Loading context for diagnostics ("startup", "switch")

        Returns:
            RuntimeInfo dict with keys:
            - model_path, backend, effective_device, requested_device,
              fallback_occurred, fallback_reason, model_name, attempts, context
        """
        ...

    @abstractmethod
    def unload_model(self) -> None:
        """Release current model and free device memory."""
        ...

    @abstractmethod
    def switch_model(
        self,
        new_model_path: str,
        device: DevicePreference = DevicePreference.AUTO,
        fallback_enabled: bool = True,
    ) -> Dict[str, Any]:
        """
        Hot-swap to a different model. Returns RuntimeInfo dict.
        On failure, the previous model MUST remain active (atomic swap).
        """
        ...

    # ── Inference ───────────────────────────────────────────────────────

    @abstractmethod
    def detect(
        self,
        frame: np.ndarray,
        conf: float = 0.3,
        iou: float = 0.3,
        max_det: int = 20,
    ) -> Tuple[str, List[NormalizedDetection]]:
        """
        Run detection only (no multi-frame tracking).

        Returns:
            (mode, detections) where mode is "detect", "obb", or "none".
        """
        ...

    @abstractmethod
    def detect_and_track(
        self,
        frame: np.ndarray,
        conf: float = 0.3,
        iou: float = 0.3,
        max_det: int = 20,
        tracker_type: str = "bytetrack",
        tracker_args: Optional[Dict] = None,
    ) -> Tuple[str, List[NormalizedDetection]]:
        """
        Run detection with built-in multi-object tracking.

        Backends without built-in tracking should fall back to detect().

        Returns:
            (mode, detections) where mode is "detect", "obb", or "none".
        """
        ...

    # ── Metadata ────────────────────────────────────────────────────────

    @abstractmethod
    def get_model_labels(self) -> Dict[int, str]:
        """Return {class_id: class_name} mapping for the loaded model."""
        ...

    @abstractmethod
    def get_model_task(self) -> str:
        """Return model task string: 'detect', 'obb', 'segment', 'pose', etc."""
        ...

    @abstractmethod
    def supports_tracking(self) -> bool:
        """Whether this backend has built-in multi-object tracking."""
        ...

    @abstractmethod
    def supports_obb(self) -> bool:
        """Whether this backend supports oriented bounding boxes."""
        ...

    @abstractmethod
    def get_device_info(self) -> Dict[str, Any]:
        """
        Return runtime device information.

        Expected keys: device, backend, model_format, model_path, ...
        """
        ...
