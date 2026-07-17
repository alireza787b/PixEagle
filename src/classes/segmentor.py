from .parameters import Parameters
import logging
from math import isfinite
from pathlib import Path
from typing import Any, List, Sequence, Tuple

import yaml

# Conditional AI imports - segmentor uses Ultralytics directly for inference
try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False
except Exception as e:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False
    logging.warning(f"Ultralytics import failed: {e}")

logger = logging.getLogger(__name__)

XYXYBox = Tuple[float, float, float, float]


def _load_segmentation_catalog() -> dict:
    """Load and validate the one runtime/schema model catalog."""
    path = Path(__file__).resolve().parents[2] / "configs" / "segmentation_models.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    models = loaded.get("models")
    if not isinstance(models, dict) or "disabled" not in models:
        raise ValueError("segmentation_models.yaml must define models.disabled")
    for name, metadata in models.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(metadata, dict):
            raise ValueError("segmentation model entries must be named objects")
        artifact = metadata.get("artifact")
        if name == "disabled":
            if artifact is not None:
                raise ValueError("the disabled segmentation entry cannot have an artifact")
        elif not isinstance(artifact, str) or not artifact.endswith(".pt"):
            raise ValueError(f"segmentation model {name!r} requires a .pt artifact")
    return models


SEGMENTATION_MODELS = _load_segmentation_catalog()
DISABLED_SEGMENTATION_ALGORITHM = "disabled"

class Segmentor:
    DISABLED_ALGORITHM = DISABLED_SEGMENTATION_ALGORITHM
    SUPPORTED_ALGORITHMS = tuple(
        name
        for name in SEGMENTATION_MODELS
        if name != DISABLED_SEGMENTATION_ALGORITHM
    )

    def __init__(self, algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM):
        """
        Initializes the Segmentor with a specified segmentation algorithm.
        """
        self.requested_algorithm = self._normalize_algorithm(algorithm)
        self.algorithm = self.DISABLED_ALGORITHM
        self.model = None
        self.unavailable_reason = "disabled_by_config"
        self._last_detections: List[XYXYBox] = []

        if self.requested_algorithm == self.DISABLED_ALGORITHM:
            return
        if self.requested_algorithm not in self.SUPPORTED_ALGORITHMS:
            self.unavailable_reason = "unsupported_algorithm"
            logger.error(
                "Unsupported segmentation algorithm %r; supported values are %s",
                self.requested_algorithm,
                ", ".join(self.SUPPORTED_ALGORITHMS),
            )
            return
        if not ULTRALYTICS_AVAILABLE:
            self.unavailable_reason = "ultralytics_unavailable"
            logger.warning(
                "Segmentation model %s requires the optional AI dependencies",
                self.requested_algorithm,
            )
            return

        try:
            self.model = YOLO(
                SEGMENTATION_MODELS[self.requested_algorithm]["artifact"]
            )
        except Exception as exc:
            self.unavailable_reason = "model_load_failed"
            logger.error(
                "Failed to load segmentation model %s: %s",
                self.requested_algorithm,
                exc,
            )
            return

        self.algorithm = self.requested_algorithm
        self.unavailable_reason = None

    @staticmethod
    def _normalize_algorithm(algorithm: Any) -> str:
        normalized = str(algorithm or "").strip().lower()
        if normalized.endswith(".pt"):
            normalized = normalized[:-3]
        return normalized or Segmentor.DISABLED_ALGORITHM

    @property
    def available(self) -> bool:
        return self.model is not None and self.unavailable_reason is None

    def get_capability_status(self) -> dict:
        """Return truthful segmentation readiness for actions and diagnostics."""
        return {
            "available": self.available,
            "requested_algorithm": self.requested_algorithm,
            "active_algorithm": self.algorithm,
            "unavailable_reason": self.unavailable_reason,
            "supported_algorithms": list(self.SUPPORTED_ALGORITHMS),
            "ultralytics_available": bool(ULTRALYTICS_AVAILABLE),
        }

    def segment_frame(self, frame):
        """
        Analyze one clean frame and return a separate annotated display frame.

        The input is never intentionally annotated in place. Tracker and
        detector consumers must continue using their clean analysis snapshot.
        """
        if self.available:
            return self.yolov8_segmentation(frame)
        self._last_detections = []
        return frame.copy()

    def yolov8_segmentation(self, frame):
        """
        Segments the frame using YOLOv8 and returns an annotated frame.
        """
        try:
            results = self.model(frame)
            annotated_frame = results[0].plot()
            current_detections = self.extract_detections(
                results,
                frame_shape=frame.shape,
            )
            self._last_detections = current_detections
            return annotated_frame
        except Exception as e:
            logger.error(f"Error during YOLOv8 segmentation: {e}")
            self._last_detections = []
            return frame.copy()

    def extract_detections(
        self,
        results: Any,
        *,
        frame_shape: Sequence[int] | None = None,
    ) -> List[XYXYBox]:
        """
        Extract valid YOLO ``xyxy`` boxes using one explicit internal contract.
        """
        try:
            detections: List[XYXYBox] = []
            frame_height = int(frame_shape[0]) if frame_shape is not None else None
            frame_width = int(frame_shape[1]) if frame_shape is not None else None
            for det in results[0].boxes.xyxy.tolist():
                if not isinstance(det, (list, tuple)) or len(det) < 4:
                    logger.warning("Ignoring malformed segmentation detection: %r", det)
                    continue
                try:
                    x1, y1, x2, y2 = (float(value) for value in det[:4])
                except (TypeError, ValueError):
                    logger.warning("Ignoring non-numeric segmentation detection: %r", det)
                    continue
                if not all(isfinite(value) for value in (x1, y1, x2, y2)):
                    logger.warning("Ignoring non-finite segmentation detection: %r", det)
                    continue
                if frame_width is not None and frame_height is not None:
                    x1 = min(max(x1, 0.0), float(frame_width))
                    x2 = min(max(x2, 0.0), float(frame_width))
                    y1 = min(max(y1, 0.0), float(frame_height))
                    y2 = min(max(y2, 0.0), float(frame_height))
                if x2 <= x1 or y2 <= y1:
                    logger.warning("Ignoring empty segmentation detection: %r", det)
                    continue
                detections.append((x1, y1, x2, y2))
            return detections
        except Exception as e:
            logger.error(f"Error extracting detections: {e}")
            return []

    def get_last_detections(self):
        """
        Return a copy of the last valid ``xyxy`` detections.
        """
        return list(self._last_detections)
