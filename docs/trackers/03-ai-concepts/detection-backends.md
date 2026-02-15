# Detection Backends

> Architecture, supported backends, and guide to implementing new ones

PixEagle v4.0.0 introduced a **pluggable detection backend system**. SmartTracker never imports a framework directly — it consumes the `DetectionBackend` abstract interface. Adding a new backend (ONNX Runtime, TensorRT, RT-DETR, OpenVINO, etc.) means implementing one Python class and registering it.

---

## Architecture

```
SmartTracker
    │
    │  uses DetectionBackend ABC (never imports YOLO/ONNX/etc. directly)
    │
    ▼
┌─────────────────────────────────────────────┐
│           DetectionBackend (ABC)             │
│  src/classes/backends/detection_backend.py   │
│                                             │
│  Properties: is_available, backend_name,    │
│              is_loaded                      │
│  Lifecycle:  load_model, unload_model,      │
│              switch_model                   │
│  Inference:  detect, detect_and_track       │
│  Metadata:   get_model_labels,              │
│              get_model_task,                │
│              supports_tracking,             │
│              supports_obb,                  │
│              get_device_info                │
└────────────────┬────────────────────────────┘
                 │
        ┌────────┴────────────────┐
        ▼                         ▼
┌───────────────────┐   ┌─────────────────────┐
│ UltralyticsBackend│   │  YourNewBackend      │
│ (ultralytics_     │   │  (your_backend.py)   │
│  backend.py)      │   │                      │
│                   │   │  Implement the same   │
│ YOLO v5-v12, 11,  │   │  10 abstract methods  │
│ 26, OBB, etc.     │   │                      │
└───────────────────┘   └──────────────────────┘
        │                         │
        ▼                         ▼
  NormalizedDetection       NormalizedDetection
  (detection_adapter.py)    (same universal schema)
```

### Key Files

| File | Purpose |
|------|---------|
| `src/classes/backends/detection_backend.py` | Abstract base class — the contract |
| `src/classes/backends/ultralytics_backend.py` | Ultralytics YOLO implementation (~550 lines) |
| `src/classes/backends/__init__.py` | Backend registry + `create_backend()` factory |
| `src/classes/detection_adapter.py` | `NormalizedDetection` dataclass (backend-agnostic) |
| `src/classes/smart_tracker.py` | Consumer — calls `self.backend.detect_and_track()` |

### Data Flow

```
Frame (numpy array)
  → backend.detect_and_track(frame, conf, iou, max_det, tracker_type, tracker_args)
  → returns (mode: str, detections: List[NormalizedDetection])
  → SmartTracker processes NormalizedDetection list
  → TrackingStateManager matches targets
  → HUD renders results
```

---

## Currently Supported Backend

### Ultralytics (`ultralytics_backend.py`)

The default and only production backend. Supports:

- **All YOLO families**: YOLOv5, YOLOv8, YOLOv9, YOLOv10, YOLO11, YOLOv12, YOLO26
- **VisDrone/custom-trained**: Any `.pt` file trained via Ultralytics
- **OBB models**: `yolo11n-obb.pt`, etc. (DOTA dataset, oriented bounding boxes)
- **Formats**: PyTorch `.pt`, NCNN `_ncnn_model/` directories, ONNX `.onnx`
- **Tracking**: Built-in ByteTrack and BoT-SORT via `model.track()`
- **Device chain**: CUDA GPU → CPU (PyTorch) → NCNN (ARM-optimized) with automatic fallback
- **Export**: `model.export(format="ncnn")` for ARM edge deployment

**Models that work through Ultralytics `YOLO()` class:**

| Model | Auto-downloads? | `.track()` | NCNN Export | Notes |
|-------|----------------|-----------|------------|-------|
| `yolo26n.pt` – `yolo26x.pt` | Yes | Yes | Yes | Default, latest architecture |
| `yolo11n.pt` – `yolo11x.pt` | Yes | Yes | Yes | Proven stable |
| `yolov12n.pt` – `yolov12x.pt` | Yes | Yes | Caution | Attention layers may export poorly |
| `yolov8n.pt` – `yolov8x.pt` | Yes | Yes | Yes | Mature, widely tested |
| `yolo11n-obb.pt` | Yes | Yes | Yes | Oriented bounding boxes (DOTA) |
| VisDrone-trained `.pt` | Manual download | Yes | Yes | Aerial/drone detection |

**Models that require a DIFFERENT Ultralytics class (NOT supported yet):**

| Model | Required Class | Why Not Supported |
|-------|---------------|-------------------|
| RT-DETR | `RTDETR("rtdetr-l.pt")` | Different pre/post-processing pipeline |
| YOLO-NAS | `NAS("yolo_nas_s.pt")` | Different class, inference-only |
| YOLO-World | `YOLOWorld("yolov8s-world.pt")` | Open-vocab, limited tracking |
| SAM / SAM2 | `SAM("sam2_b.pt")` | Segmentation, not detection |

These could be added as new backends or as extensions to UltralyticsBackend.

---

## NormalizedDetection — The Universal Schema

Every backend must produce `NormalizedDetection` instances. This is the contract between detection and tracking:

```python
@dataclass
class NormalizedDetection:
    track_id: int                    # -1 if backend doesn't assign IDs
    class_id: int                    # Integer class index
    confidence: float                # 0.0 – 1.0
    aabb_xyxy: Tuple[int, int, int, int]  # Axis-aligned bounding box (x1, y1, x2, y2)
    center_xy: Tuple[int, int]       # Center point (cx, cy)
    geometry_type: str = "aabb"      # "aabb" or "obb"
    obb_xywhr: Optional[Tuple] = None     # Oriented BB (cx, cy, w, h, rotation_rad)
    polygon_xy: Optional[List] = None      # Corner polygon for OBB
    rotation_deg: Optional[float] = None   # Rotation in degrees
```

**Rules:**
- `aabb_xyxy` and `center_xy` are always required (even for OBB, provide the enclosing AABB)
- `track_id` = -1 when the backend doesn't do its own tracking (SmartTracker's TrackingStateManager will assign IDs)
- Coordinates are pixel-space integers relative to the input frame
- OBB fields are optional — only set when `geometry_type == "obb"`

---

## How to Implement a New Backend

### Step 1: Create the Backend File

Create `src/classes/backends/your_backend.py`:

```python
"""
YourFramework detection backend for PixEagle SmartTracker.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from classes.backends.detection_backend import DetectionBackend, DevicePreference
from classes.detection_adapter import NormalizedDetection

# Conditional import — app must work without this dependency
try:
    import your_framework
    YOUR_FRAMEWORK_AVAILABLE = True
except ImportError:
    YOUR_FRAMEWORK_AVAILABLE = False

logger = logging.getLogger(__name__)


class YourBackend(DetectionBackend):

    def __init__(self, config: dict):
        self._config = config
        self._model = None
        self._labels: Dict[int, str] = {}
        self._device = "cpu"

    # ── Properties ──────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        return YOUR_FRAMEWORK_AVAILABLE

    @property
    def backend_name(self) -> str:
        return "your_framework"

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    # ── Lifecycle ───────────────────────────────────────────────

    def load_model(self, model_path, device=DevicePreference.AUTO,
                   fallback_enabled=True, context="startup") -> Dict[str, Any]:
        """
        Load the model file. Handle GPU/CPU selection and fallback.

        MUST return a RuntimeInfo dict with at least:
        {
            "model_path": str,
            "backend": self.backend_name,
            "effective_device": "cuda:0" or "cpu",
            "requested_device": device.value,
            "fallback_occurred": bool,
            "fallback_reason": str or None,
            "model_name": str,
            "attempts": int,
            "context": context,
        }
        """
        # Your model loading logic here
        self._model = your_framework.load(model_path)
        self._labels = self._model.get_labels()

        return {
            "model_path": model_path,
            "backend": self.backend_name,
            "effective_device": self._device,
            "requested_device": device.value,
            "fallback_occurred": False,
            "fallback_reason": None,
            "model_name": Path(model_path).stem,
            "attempts": 1,
            "context": context,
        }

    def unload_model(self) -> None:
        self._model = None
        self._labels = {}

    def switch_model(self, new_model_path, device=DevicePreference.AUTO,
                     fallback_enabled=True) -> Dict[str, Any]:
        """
        CRITICAL: If loading the new model fails, the OLD model must remain
        active. This is an atomic swap requirement.
        """
        old_model = self._model
        old_labels = self._labels
        try:
            return self.load_model(new_model_path, device, fallback_enabled,
                                   context="switch")
        except Exception:
            # Restore previous model on failure
            self._model = old_model
            self._labels = old_labels
            raise

    # ── Inference ───────────────────────────────────────────────

    def detect(self, frame, conf=0.3, iou=0.3, max_det=20
               ) -> Tuple[str, List[NormalizedDetection]]:
        """
        Run detection on a single frame.

        MUST return: (mode_string, list_of_NormalizedDetection)
        - mode_string: "detect", "obb", or "none"
        - Each NormalizedDetection must have all required fields populated
        """
        raw_results = self._model.predict(frame, confidence=conf)

        detections = []
        for r in raw_results:
            x1, y1, x2, y2 = int(r.x1), int(r.y1), int(r.x2), int(r.y2)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            detections.append(NormalizedDetection(
                track_id=-1,          # No tracking — SmartTracker will assign
                class_id=r.class_id,
                confidence=r.score,
                aabb_xyxy=(x1, y1, x2, y2),
                center_xy=(cx, cy),
            ))

        mode = "detect" if detections else "none"
        return mode, detections

    def detect_and_track(self, frame, conf=0.3, iou=0.3, max_det=20,
                         tracker_type="bytetrack", tracker_args=None
                         ) -> Tuple[str, List[NormalizedDetection]]:
        """
        If your framework has built-in tracking, use it here.
        If not, just call self.detect() — SmartTracker's TrackingStateManager
        will handle ID assignment.
        """
        # Frameworks without built-in tracking:
        return self.detect(frame, conf, iou, max_det)

    # ── Metadata ────────────────────────────────────────────────

    def get_model_labels(self) -> Dict[int, str]:
        return dict(self._labels)

    def get_model_task(self) -> str:
        return "detect"  # or "obb" if your model does oriented boxes

    def supports_tracking(self) -> bool:
        return False  # True only if framework has built-in MOT

    def supports_obb(self) -> bool:
        return False  # True if model outputs oriented bounding boxes

    def get_device_info(self) -> Dict[str, Any]:
        return {
            "device": self._device,
            "backend": self.backend_name,
            "model_format": "your_format",
            "model_path": str(getattr(self._model, 'path', 'unknown')),
        }
```

### Step 2: Register in `__init__.py`

Edit `src/classes/backends/__init__.py`:

```python
AVAILABLE_BACKENDS = {
    'ultralytics': ('classes.backends.ultralytics_backend', 'UltralyticsBackend'),
    'your_framework': ('classes.backends.your_backend', 'YourBackend'),  # ADD THIS
}
```

### Step 3: Set Config

In `configs/config.yaml` (and `config_default.yaml`):

```yaml
SmartTracker:
  DETECTION_BACKEND: "your_framework"   # was: "ultralytics"
  SMART_TRACKER_GPU_MODEL_PATH: "models/your_model.onnx"
  SMART_TRACKER_CPU_MODEL_PATH: "models/your_model.onnx"
```

### Step 4: Install Dependencies

Add your framework's packages. PixEagle uses conditional imports so the app still works without them:

```bash
pip install your-framework
```

### Step 5: Test

```bash
# Run existing tests (must still pass)
pytest tests/ -x --tb=short

# Add backend-specific tests
# tests/unit/core_app/test_your_backend.py
```

**That's it.** SmartTracker, the API, the dashboard, model management — everything works automatically through the `DetectionBackend` interface.

---

## Concrete Example: Adding RT-DETR Support

RT-DETR (Real-Time Detection Transformer) is supported by Ultralytics but uses a different class (`RTDETR` instead of `YOLO`). Here's how you'd add it:

### Option A: Extend UltralyticsBackend (Recommended)

The simplest path — RT-DETR uses the same Ultralytics result format:

```python
# src/classes/backends/rtdetr_backend.py

from classes.backends.ultralytics_backend import UltralyticsBackend, ULTRALYTICS_AVAILABLE

try:
    from ultralytics import RTDETR
    RTDETR_AVAILABLE = ULTRALYTICS_AVAILABLE
except ImportError:
    RTDETR = None
    RTDETR_AVAILABLE = False


class RTDETRBackend(UltralyticsBackend):
    """RT-DETR backend — extends UltralyticsBackend with RTDETR loader."""

    @property
    def backend_name(self) -> str:
        return "rtdetr"

    def _load_candidate(self, model_path: str, device_str: str):
        """Override to use RTDETR() instead of YOLO()."""
        model = RTDETR(model_path)
        if device_str and device_str != "cpu":
            model.to(device_str)
        return model

    def supports_tracking(self) -> bool:
        # RT-DETR .track() has known regressions for small objects
        return False

    def supports_obb(self) -> bool:
        return False
```

Register it:
```python
AVAILABLE_BACKENDS = {
    'ultralytics': ('classes.backends.ultralytics_backend', 'UltralyticsBackend'),
    'rtdetr': ('classes.backends.rtdetr_backend', 'RTDETRBackend'),
}
```

Since `supports_tracking()` returns `False`, SmartTracker will use `detect()` instead of `detect_and_track()`, and its own `TrackingStateManager` handles ID assignment.

### Option B: ONNX Runtime Backend (Framework-Independent)

For running exported `.onnx` models without Ultralytics:

```python
# src/classes/backends/onnx_backend.py

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ort = None
    ONNX_AVAILABLE = False


class ONNXRuntimeBackend(DetectionBackend):

    @property
    def backend_name(self) -> str:
        return "onnxruntime"

    def load_model(self, model_path, device=DevicePreference.AUTO, ...):
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        if device == DevicePreference.CPU:
            providers = ['CPUExecutionProvider']
        self._session = ort.InferenceSession(model_path, providers=providers)
        # ... parse model metadata for labels

    def detect(self, frame, conf=0.3, iou=0.3, max_det=20):
        # Preprocess frame to model input format
        input_tensor = self._preprocess(frame)
        # Run inference
        outputs = self._session.run(None, {self._input_name: input_tensor})
        # Parse outputs to NormalizedDetection list
        detections = self._postprocess(outputs, conf, iou, max_det, frame.shape)
        return ("detect", detections)

    def supports_tracking(self) -> bool:
        return False  # ONNX Runtime has no built-in tracker
```

---

## What SmartTracker Does With Backend Output

Understanding this helps you build correct backends:

1. **`detect_and_track()`** is called when the backend has built-in tracking (`supports_tracking() == True`). The returned `NormalizedDetection.track_id` values are used directly.

2. **`detect()`** is called when the backend doesn't track. `track_id` should be `-1`. SmartTracker's `TrackingStateManager` then:
   - Matches detections to existing targets (IoU, distance, appearance)
   - Assigns stable IDs across frames
   - Handles occlusion, re-acquisition, class flickering

3. **OBB results** (`geometry_type == "obb"`) are handled when `supports_obb() == True`. The `obb_xywhr` field is used for rotation-aware drawing and IoU.

4. **Labels** from `get_model_labels()` are used for HUD display and class filtering.

5. **RuntimeInfo** from `load_model()` / `switch_model()` is exposed via the `/api/models/active` API endpoint and displayed in the dashboard.

---

## API and Dashboard Integration

Once registered, your backend automatically works with:

| Component | How It Uses Your Backend |
|-----------|------------------------|
| **`/api/models/active`** | Shows `backend_name`, device, model info from `get_device_info()` |
| **`/api/models/switch`** | Calls `switch_model()` with new path + device |
| **Dashboard ModelQuickControl** | Displays backend chip, device chip, label count |
| **ModelsPage** | Lists models, shows backend info, activate/switch |
| **Config schema** | `DETECTION_BACKEND` dropdown populated from `AVAILABLE_BACKENDS` |

No frontend changes needed — the dashboard reads `backend_name` from the API response dynamically.

---

## Model Compatibility Quick Reference

### Works Now (Ultralytics Backend)

| Use Case | Model | How to Get It |
|----------|-------|---------------|
| General detection (COCO) | `yolo26n.pt` – `yolo26x.pt` | Auto-downloads via `YOLO("yolo26n.pt")` |
| Aerial/drone (VisDrone) | `yolov8s-visdrone.pt` | [HuggingFace](https://huggingface.co/mshamrai/yolov8s-visdrone) |
| Rotated objects (DOTA) | `yolo11n-obb.pt` | Auto-downloads |
| Edge/ARM deployment | Any model + NCNN export | `model.export(format="ncnn")` |

### Would Need New Backend

| Use Case | Model | Backend Needed | Effort |
|----------|-------|---------------|--------|
| RT-DETR | `rtdetr-l.pt` | `RTDETRBackend` (extend Ultralytics) | Low — ~50 lines |
| ONNX models | `.onnx` files | `ONNXRuntimeBackend` | Medium — ~300 lines |
| TensorRT | `.engine` files | `TensorRTBackend` | Medium — ~350 lines |
| OpenVINO | `.xml` + `.bin` | `OpenVINOBackend` | Medium — ~300 lines |
| HuggingFace DETR | HF model ID | `HuggingFaceBackend` | High — ~500 lines, different paradigm |
| RF-DETR (Roboflow) | Roboflow model | `RFDETRBackend` | High — separate library |

### Will Never Work (Incompatible)

| Model | Why |
|-------|-----|
| Classification-only models | No bounding box output |
| Generative models (Stable Diffusion, etc.) | Wrong task entirely |
| Models requiring custom C++ inference | Can't wrap in Python easily |

---

## Testing Your Backend

### Required Tests

Create `tests/unit/core_app/test_your_backend.py`:

```python
def test_backend_name():
    backend = YourBackend({})
    assert backend.backend_name == "your_framework"

def test_is_available():
    # True if framework installed, False otherwise
    backend = YourBackend({})
    assert isinstance(backend.is_available, bool)

def test_detect_returns_correct_format():
    backend = YourBackend({})
    backend.load_model("path/to/test/model")
    mode, detections = backend.detect(fake_frame)
    assert mode in ("detect", "obb", "none")
    for d in detections:
        assert isinstance(d, NormalizedDetection)
        assert len(d.aabb_xyxy) == 4
        assert 0.0 <= d.confidence <= 1.0

def test_switch_model_atomic():
    """If switch fails, old model must still be loaded."""
    backend = YourBackend({})
    backend.load_model("models/good_model.pt")
    try:
        backend.switch_model("models/nonexistent.pt")
    except Exception:
        pass
    assert backend.is_loaded  # Old model still active

def test_labels_dict():
    backend = YourBackend({})
    backend.load_model("path/to/model")
    labels = backend.get_model_labels()
    assert isinstance(labels, dict)
    for k, v in labels.items():
        assert isinstance(k, int)
        assert isinstance(v, str)
```

### Run Full Suite

```bash
# All existing tests must still pass
pytest tests/ -x --tb=short

# Dashboard must build
cd dashboard && npm run build
```

---

## Checklist for New Backend PRs

- [ ] Backend class implements all 10 abstract methods from `DetectionBackend`
- [ ] Conditional import — app works without the framework installed
- [ ] Registered in `AVAILABLE_BACKENDS` dict in `__init__.py`
- [ ] `DETECTION_BACKEND` key documented in `config_default.yaml`
- [ ] `switch_model()` is atomic — restores old model on failure
- [ ] `detect()` returns `(mode, List[NormalizedDetection])` with correct types
- [ ] `track_id = -1` when backend doesn't do its own tracking
- [ ] `load_model()` returns complete RuntimeInfo dict
- [ ] Unit tests covering: instantiation, detect format, atomic switch, labels
- [ ] Full test suite passes: `pytest tests/ -x`
- [ ] Dashboard builds: `cd dashboard && npm run build`
- [ ] Config schema updated if new parameters needed

---

## Related

- [SmartTracker Reference](../02-reference/smart-tracker.md) — How SmartTracker consumes backends
- [ByteTrack/BoT-SORT](bytetrack-botsort.md) — Multi-object tracking (used when backend lacks built-in tracking)
- [Appearance Model](appearance-model.md) — ReID for re-acquisition after occlusion
- [Configuration](../04-configuration/README.md) — Parameter tuning
