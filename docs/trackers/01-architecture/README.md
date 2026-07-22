# Tracker Architecture

> Core design patterns and components of the PixEagle tracker system

This section covers the foundational architecture of the tracker system, including the abstract base class, factory pattern, and output schema.

---

## Section Contents

| Document | Description |
|----------|-------------|
| [BaseTracker](base-tracker.md) | Abstract base class interface |
| [Factory Pattern](factory-pattern.md) | TrackerFactory registry |
| [TrackerOutput](tracker-output.md) | Unified output schema |

---

## Design Philosophy

The tracker system follows these key principles:

1. **Polymorphism** - All trackers implement the same interface via `BaseTracker`
2. **Factory Pattern** - Dynamic tracker creation without hardcoded dependencies
3. **Schema-Driven** - YAML-defined data types with validation
4. **Separation of Concerns** - Tracking logic decoupled from follower control

---

## Component Overview

### BaseTracker (Abstract Base Class)

The `BaseTracker` class in `src/classes/trackers/base_tracker.py` defines:

- **Abstract Methods**: `start_tracking()`, `update()` - must be implemented
- **Common Utilities**: Normalization, confidence computation, visualization
- **TrackerOutput Generation**: Standardized output via `get_output()`
- **Estimator Integration**: Optional Kalman filter support

### TrackerFactory

The `TrackerFactory` in `src/classes/trackers/tracker_factory.py`:

- **Registry Pattern**: Maps algorithm names to tracker classes
- **Simple API**: `create_tracker("CSRT", video_handler, detector, app_controller)`
- **Extensibility**: Add new trackers by updating the registry

### TrackerOutput

The `TrackerOutput` dataclass in `src/classes/tracker_output.py`:

- **8 Data Types**: POSITION_2D, POSITION_3D, ANGULAR, GIMBAL_ANGLES, etc.
- **Type Safety**: Validated fields with dataclass validation
- **Backwards Compatibility**: `create_legacy_tracker_output()` helper
- **Freshness Metadata**: `raw_data` and `metadata` identify whether data is
  command-usable, stale, cached-frame-derived, or prediction-only

---

## Class Hierarchy

```
BaseTracker (ABC)
├── CSRTTracker          - OpenCV CSRT correlation tracker
├── KCFKalmanTracker     - KCF + internal Kalman filter
├── DlibTracker          - dlib correlation filter with PSR
├── GimbalTracker        - External gimbal angle input
└── CustomTracker        - Template for custom implementations

SmartTracker             - Standalone YOLO + ByteTrack (not BaseTracker subclass)
```

---

## Data Flow

```
Video Frame
    │
    ▼
┌──────────────┐
│ Tracker      │ ◄─── BaseTracker.update(frame)
│ (CSRT, KCF,  │
│  dlib, etc.) │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ TrackerOutput│ ◄─── Normalized position, confidence, bbox
│ (dataclass)  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Follower     │ ◄─── Consumes tracker output for control
│ (MC, FW, GM) │
└──────────────┘
```

## Command Freshness

Tracker output can be useful for overlays and diagnostics even when it is not
safe to use for PX4 command generation. Vision trackers built on `BaseTracker`
mark outputs with:

- `measurement_source: measurement` and `usable_for_following: true` when the
  target was measured on a fresh frame;
- `measurement_source: prediction_only`, `data_is_stale: true`, and
  `usable_for_following: false` when the tracker is coasting on an estimator or
  last-known state.

`tracker_runtime_status.evaluate_tracker_command_freshness()` is the shared
decision for classic, Smart/AI, and external tracker output.
`AppController.follow_target()` enforces that decision, plus
`VideoHandler.get_frame_status()`, before follower dispatch. Cached frames and
prediction-only target states are converted into inactive fail-closed tracker
output. Followers must explicitly opt in through
`should_process_inactive_tracker_output()` before they can publish a stop,
hover, orbit, or other target-loss command.

`SmartTracker` applies the same contract to TrackingStateManager output:
confirmed detections are command-usable, while tentative or prediction-only
states remain visible for overlays but set `data_is_stale` and
`usable_for_following: false`. If other detections keep the output type as
`MULTI_TARGET`, inactive follower dispatch still uses only explicit stop, hold,
hover, or orbit target-loss commands. `GimbalTracker` keeps angle telemetry
visible only when provider data is fresh; a fresh angle packet without a fresh
tracking status clears internal active state so following cannot continue from
stale tracking status.

Freshness timing remains with the source that can interpret it correctly:
video input owns frame age, classic and Smart trackers own measurement versus
prediction state, and each external provider owns its packet timeout. Do not
add a second universal target-age threshold in a follower; it will conflict
with detector cadence, camera FPS, and provider packet rates.

---

## Key Interfaces

### BaseTracker Interface

```python
class BaseTracker(ABC):
    @abstractmethod
    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """Initialize tracking with frame and bounding box."""
        pass

    @abstractmethod
    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """Process new frame, return (success, bbox)."""
        pass

    def get_output(self) -> TrackerOutput:
        """Return standardized tracker output."""
        return TrackerOutput(...)
```

### TrackerFactory Interface

```python
def create_tracker(algorithm: str, video_handler=None, detector=None,
                   app_controller=None) -> BaseTracker:
    """
    Create tracker instance by algorithm name.

    Args:
        algorithm: "CSRT", "KCF", "dlib", or "Gimbal"

    Returns:
        BaseTracker instance
    """
```

---

## Related Sections

- [Tracker Reference](../02-reference/README.md) - Individual tracker details
- [Development Guide](../05-development/README.md) - Creating custom trackers
