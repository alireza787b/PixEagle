# Detection Backends

> Architecture, supported backends, and guide to implementing new ones

SmartTracker consumes the `DetectionBackend` abstract interface rather than
importing an inference framework directly. A new backend starts with an
adapter and registry entry, but it is not product-supported until artifact
trust, model management, schema/API behavior, resource limits, tracking, and
target-hardware evidence are integrated.

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
│ YOLO detect/OBB   │   │  backend contract    │
│ task policy       │   │                      │
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
| `src/classes/backends/ultralytics_backend.py` | Current Ultralytics YOLO implementation |
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

The default and currently registered backend. Inference readiness depends on
the installed Ultralytics version, a trusted local artifact, and the bounded
runtime probe. The supported SmartTracker task policy is `detect` or `obb`.

- **Local model artifacts**: Ultralytics-loadable `.pt` files and complete NCNN
  `_ncnn_model/` directories that pass the current task policy
- **Tracking**: installed Ultralytics ByteTrack or BoT-SORT defaults via
  `model.track()`; native BoT-SORT ReID is not enabled
- **Optional local appearance matching**: `custom_reid` combines ByteTrack IDs
  with PixEagle's AppearanceModel
- **Device policy**: configured CUDA or CPU selection with explicit CPU fallback
- **Optional export**: NCNN tooling is installed and invoked only on request

Runtime never relies on an Ultralytics implicit model download. Missing local
files, missing provenance records, and digest changes fail closed before
`YOLO(...)` executes. Verified provenance is included in backend `RuntimeInfo`
and in the bounded readiness report. Add and validate a model through
[Model Setup](../../MODEL_SETUP.md), then run
`check-ai-runtime.sh --require-smart-tracker` on the target host.

That command proves required module imports, local model loading, task/device
policy, and one `detect()` call against a fixed 64x64 zero-valued frame. It does
not call `model.track()` and does not claim tracker initialization, association
quality, camera-pipeline behavior, latency, or field readiness. Tracking needs
a separate offline scenario test with retained evidence.

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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from classes.backends.detection_backend import DetectionBackend, DevicePreference
from classes.detection_adapter import NormalizedDetection
from classes.model_artifact_policy import ModelProvenanceStore

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
            "effective_device": "cuda" or "cpu",
            "requested_device": device.value,
            "fallback_occurred": bool,
            "fallback_reason": str or None,
            "model_name": str,
            "attempts": list,
            "model_provenance": {
                "verified": bool,
                "artifact_type": "pt" or "ncnn",
                "sha256": str,
            },
            "context": context,
        }
        """
        artifact = Path(model_path).expanduser()
        if not artifact.is_absolute():
            artifact = Path.cwd() / artifact
        store = ModelProvenanceStore(artifact.parent)
        if artifact.is_dir():
            record = store.verify_ncnn(artifact)
            artifact_type = "ncnn"
        elif artifact.suffix.lower() == ".pt":
            record = store.verify_pt(artifact)
            artifact_type = "pt"
        else:
            raise ValueError("Only trusted .pt and NCNN artifacts are supported")

        provenance = {
            "verified": True,
            "artifact_type": artifact_type,
            "sha256": record["sha256"],
            "models_root": str(store.models_root),
            "registry_path": str(store.registry_path),
        }
        # Verification must complete before the executable framework load.
        self._model = your_framework.load(str(artifact))
        self._labels = self._model.get_labels()

        return {
            "model_path": str(artifact),
            "backend": self.backend_name,
            "effective_device": self._device,
            "requested_device": device.value,
            "fallback_occurred": False,
            "fallback_reason": None,
            "model_name": artifact.name,
            "attempts": [{
                "path": str(artifact),
                "backend": self.backend_name,
                "source": "requested",
                "success": True,
                "model_provenance": provenance,
            }],
            "model_provenance": provenance,
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

Backend registration only makes the class constructible. A production backend
also needs an explicit artifact trust policy, model-management validation,
configuration schema support, API behavior review, and retained load/inference
tests. Those integrations are not automatic.

---

## Planned Backend Expansion

RT-DETR, RF-DETR, SAHI, YOLOX P2, ONNX Runtime, TensorRT, and OpenVINO are not
registered PixEagle backends. In particular, Ultralytics RT-DETR loads through
`RTDETR(...)`, not the current `YOLO(...)` path. A code sketch is insufficient
because model admission, safe loading, normalized outputs, device fallback,
tracking behavior, frame-age limits, configuration, API state, cleanup, and
target-host evidence must agree.

PXE-0123 uses a benchmark-first gate: compare an unsupported candidate with a
supported YOLO detect/OBB baseline on representative aerial video and the
target computer. Implement a backend only when the measured benefit justifies
the new dependency and lifecycle surface. See the
[Detection Model Catalog](../../MODEL_CATALOG.md) for the current candidate
matrix and selection evidence.

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

5. **RuntimeInfo** from `load_model()` / `switch_model()` is included in
   `GET /api/v1/runtime/status` as
   `subsystems.smart_tracker_runtime`. For Ultralytics it includes the verified
   runtime artifact digest and provenance metadata.

---

## API and Dashboard Integration

The current Ultralytics backend participates in these integrations:

| Component | How It Uses Your Backend |
|-----------|------------------------|
| **`GET /api/v1/runtime/status`** | Exposes active SmartTracker runtime metadata, including verified model provenance |
| **Legacy model routes** | Remain Ultralytics/model-manager compatibility APIs; a new backend needs separate review |
| **Dashboard ModelQuickControl** | Displays backend chip, device chip, label count |
| **ModelsPage** | Lists models, shows backend info, activate/switch |
| **Config schema** | Must be updated explicitly; `AVAILABLE_BACKENDS` does not populate it |

Do not assume a new registry entry is sufficient for dashboard or model-route
support. Those surfaces currently depend on model-manager contracts beyond the
`DetectionBackend` ABC.

Model activation is refused while following is active or while SmartTracker or
its tracking-state manager owns a selected target. Clear the target first so a
model/label-space change cannot silently rebind an active track. Target
selection, target clearing, SmartTracker inference/lifecycle, and model
replacement share a process-local state barrier. The selection state is
rechecked after model validation before replacement. A
successful switch persists the selected model, writes the redacted config audit
record, and publishes one strict runtime config generation. A failure restores
both the previous runtime model and transaction-owned config state; incomplete
rollback is reported as requiring operator recovery.

---

## Model Compatibility Quick Reference

### Supported Contract

| Use Case | Required evidence |
|----------|-------------------|
| General or custom detection | Trusted local `detect` model, recorded origin/digest, bounded first inference, and scenario test |
| Oriented detection | Trusted local `obb` model, bounded first inference and geometry scenario test |
| Edge/ARM NCNN | Explicit NCNN install/export plus target-board load, accuracy, latency, and thermal evidence |

### Requires A New Reviewed Backend Or Inference Pipeline

| Candidate | Additional contract |
|----------|---------------------|
| RT-DETR | Separate Ultralytics loader, task/provenance policy, normalized output, association, and target-host evidence |
| RF-DETR | Separate package/license/export lifecycle plus adapter and evaluation |
| SAHI | Tiling/merge pipeline with bounded frame age, duplicate handling, and resource evidence |
| YOLOX P2 | YOLOX artifact/runtime and association adapter |
| ONNX, TensorRT, or OpenVINO | Runtime-specific metadata, provider/device, preprocessing/postprocessing, and artifact policy |

### Rejected By The Current Detector Contract

| Model | Why |
|-------|-----|
| Classification-only models | No bounding box output |
| Generative models (Stable Diffusion, etc.) | Wrong task entirely |
| Models with no supported Python or supervised IPC adapter | No bounded lifecycle or normalized result contract |

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
- [ ] Executable artifacts are provenance-verified before framework loading
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
