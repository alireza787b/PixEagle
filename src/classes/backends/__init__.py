"""
Detection backend registry and factory.

Provides create_backend() to instantiate detection backends by name.
"""

import importlib
import logging
from typing import Optional

from classes.backends.detection_backend import DetectionBackend, DevicePreference

logger = logging.getLogger(__name__)

# Registry: backend_name -> (module_path, class_name)
AVAILABLE_BACKENDS = {
    'ultralytics': ('classes.backends.ultralytics_backend', 'UltralyticsBackend'),
    # Future backends:
    # 'onnxruntime': ('classes.backends.onnx_backend', 'ONNXRuntimeBackend'),
    # 'tensorrt':    ('classes.backends.tensorrt_backend', 'TensorRTBackend'),
    # 'openvino':    ('classes.backends.openvino_backend', 'OpenVINOBackend'),
}


def create_backend(
    backend_name: str = 'ultralytics',
    config: Optional[dict] = None,
) -> DetectionBackend:
    """
    Factory: create a detection backend by name.

    Args:
        backend_name: Backend identifier (e.g., 'ultralytics')
        config: Configuration dict (SmartTracker section from Parameters)

    Returns:
        DetectionBackend instance

    Raises:
        ValueError: If backend_name is not registered
        ImportError: If backend module cannot be imported
    """
    if backend_name not in AVAILABLE_BACKENDS:
        available = ", ".join(sorted(AVAILABLE_BACKENDS.keys()))
        raise ValueError(
            f"Unknown detection backend: '{backend_name}'. "
            f"Available backends: {available}"
        )

    module_path, class_name = AVAILABLE_BACKENDS[backend_name]

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(
            f"Detection backend '{backend_name}' could not be loaded. "
            f"Required package may not be installed. Error: {e}"
        ) from e

    backend_class = getattr(module, class_name)
    return backend_class(config or {})


__all__ = [
    'DetectionBackend',
    'DevicePreference',
    'AVAILABLE_BACKENDS',
    'create_backend',
]
