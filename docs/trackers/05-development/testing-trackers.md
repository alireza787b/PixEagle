# Testing Trackers

> Testing strategies, fixtures, and best practices for tracker development

This guide covers testing approaches for tracker implementations.

---

## Test Structure

```
tests/
├── unit/
│   ├── test_tracker_output.py     # TrackerOutput tests
│   ├── test_base_tracker.py       # BaseTracker utilities
│   └── test_my_tracker.py         # Custom tracker tests
├── integration/
│   └── test_tracker_factory.py    # Factory pattern tests
├── fixtures/
│   ├── mock_tracker.py            # TrackerOutput factory
│   ├── mock_px4.py               # Mock PX4Controller
│   └── mock_safety.py            # Mock SafetyManager
└── conftest.py                   # Shared fixtures
```

---

## Running Tests

```bash
# Fast tracker contract tests
PYTHONPATH=src pytest tests/unit/trackers -m "not sitl and not px4 and not e2e and not hardware and not manual" -v

# Deterministic tracker-in-loop validation
PYTHONPATH=src pytest tests/unit/trackers/test_tracker_in_loop_validation.py -v

# Specific test
pytest tests/unit/test_my_tracker.py::TestMyTracker::test_start_tracking -v

# Skip slow tests
pytest tests/unit/ -m "not slow"
```

---

## Test Fixtures

### TrackerOutputFactory

```python
# tests/fixtures/mock_tracker.py
from classes.tracker_output import TrackerOutput, TrackerDataType
import time

class TrackerOutputFactory:
    """Factory for creating test TrackerOutput instances."""

    @staticmethod
    def create_centered() -> TrackerOutput:
        """Create output with target at frame center."""
        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.0, 0.0),
            confidence=1.0,
            bbox=(295, 215, 50, 50)
        )

    @staticmethod
    def create_offset(x: float, y: float) -> TrackerOutput:
        """Create output with specific offset."""
        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(x, y),
            confidence=0.9
        )

    @staticmethod
    def create_lost() -> TrackerOutput:
        """Create output for lost target."""
        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=False,
            confidence=0.0
        )

    @staticmethod
    def create_gimbal(yaw: float, pitch: float, roll: float) -> TrackerOutput:
        """Create gimbal angle output."""
        return TrackerOutput(
            data_type=TrackerDataType.GIMBAL_ANGLES,
            timestamp=time.time(),
            tracking_active=True,
            angular=(yaw, pitch, roll),
            confidence=0.95
        )
```

### Mock VideoHandler

```python
# tests/fixtures/mock_video.py
class MockVideoHandler:
    """Mock video handler for testing."""

    def __init__(self, width=640, height=480):
        self.width = width
        self.height = height

    def get_frame(self):
        return np.zeros((self.height, self.width, 3), dtype=np.uint8)
```

### Deterministic Tracker-In-Loop Fixtures

Use `tests/fixtures/synthetic_tracker_scene.py` when a test must prove the
actual tracker contract from pixels or replayed gimbal data, not only a mocked
`TrackerOutput`.

The fixture provides:

- `SyntheticTargetScene`: generated BGR frames with known target bboxes and
  expected normalized centers
- text-based clip manifests under `tests/fixtures/tracker_clips/` for
  repeatable recorded/simulated sequences without large binary media files
- `ColorBlobTrackerProbe`: a test-only `BaseTracker` subclass that converts the
  synthetic frames into real `TrackerOutput`
- `GimbalReplaySample`: deterministic gimbal-angle samples with explicit
  `has_output`, `data_is_stale`, and `usable_for_following` metadata

Tracker-in-loop tests must assert these four states separately:

- `has_output`: the tracker has any target-like data to display or inspect
- `tracking_active`: the tracker believes a target is selected or active
- `data_is_stale` / `freshness_reason`: the output is a measurement or
  prediction/stale replay
- `usable_for_following`: the output is allowed to drive follower command math

Do not let cached, predicted, stale, or status-only output look command-safe
just because it still contains a bbox or gimbal angle.

This fixture layer is L3 tracker-in-loop validation. It proves deterministic
tracker/follower contracts only. It does not prove full visual SITL, PX4 SITL,
HIL, field behavior, real detector accuracy, camera latency, or real gimbal
protocol behavior; those require the operator-gated evidence workflows in the
SITL and field-validation plans.

### Normalized Trace Artifacts

Use `classes.tracker_trace` when a tracker/follower smoke needs portable JSONL
evidence for SITL or review packages. The helpers do not publish commands or
mutate runtime state; they serialize already-produced `TrackerOutput` and
`CommandIntent` snapshots.

For validation runs, `AppController.configure_tracker_trace_artifacts(...)`
enables append-only runtime capture at the normal
`_dispatch_tracker_output_to_follower()` boundary. This hook is inert unless
configured. When enabled, it writes a tracker-command record for each dispatch
attempt and an Offboard publish record whenever a command intent exists. It
does not start PX4, change follow mode, install services, mutate routing, or
publish commands by itself.

Expected artifacts:

- `trace/tracker_command_trace.jsonl`
- `trace/offboard_publish_trace.jsonl`

Each tracker-command record includes:

- `schema_version` and `record_type`
- `timestamp`, `frame_index`, and `source`
- tracker ID, data type, bbox/angles/position, confidence, freshness fields,
  `has_output`, `tracking_active`, and `usable_for_following`
- command intent profile, control type, reason, source, UTC creation time, and
  fields
- optional video frame status and OffboardCommander status
- a claim boundary that prevents treating the trace as PX4, SITL, HIL, field,
  or real-aircraft evidence

Each Offboard publish record includes the command intent summary and the
publication status snapshot available to the caller. A deterministic test in
`tests/unit/trackers/test_tracker_in_loop_validation.py` configures the
AppController trace hook, then writes both JSONL artifacts from a generated
green-target clip through `AppController`, the position follower,
`CommandIntent`, and a capturing Offboard commander.

The Gazebo/SITL harness validates these JSONL records by schema. Arbitrary
JSONL with only timestamps is not accepted for visual evidence: tracker-command
records must include `record_type=tracker_command`, `schema_version=1`,
`frame_index`, tracker geometry or position, freshness metadata, and a command
intent with `reason` plus non-empty `fields`; Offboard records must include
`record_type=offboard_publish`, `schema_version=1`, `sequence`, command intent
reason/fields, and publication status.

---

## Unit Test Examples

### Testing Initialization

```python
class TestMyTracker:
    @pytest.fixture
    def tracker(self):
        return MyTracker()

    def test_initialization_sets_name(self, tracker):
        assert tracker.tracker_name == "MyTracker"

    def test_initialization_not_started(self, tracker):
        assert not tracker.tracking_started
        assert not tracker.is_initialized

    def test_initialization_with_config(self, tracker):
        assert tracker.confidence_threshold > 0
```

### Testing start_tracking()

```python
    def test_start_tracking_sets_bbox(self, tracker):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        bbox = (100, 200, 50, 60)

        tracker.start_tracking(frame, bbox)

        assert tracker.bbox == bbox
        assert tracker.tracking_started
        assert tracker.is_initialized

    def test_start_tracking_computes_center(self, tracker):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        bbox = (100, 200, 50, 60)

        tracker.start_tracking(frame, bbox)

        expected_center = (125, 230)  # x + w/2, y + h/2
        assert tracker.center == expected_center

    def test_start_tracking_normalizes(self, tracker, mock_video_handler):
        tracker.video_handler = mock_video_handler
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        bbox = (100, 200, 50, 60)

        tracker.start_tracking(frame, bbox)

        assert tracker.normalized_center is not None
        assert -1 <= tracker.normalized_center[0] <= 1
```

### Testing update()

```python
    def test_update_returns_success(self, tracker):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracker.start_tracking(frame, (100, 200, 50, 60))

        success, bbox = tracker.update(frame)

        assert success is True
        assert bbox is not None

    def test_update_not_initialized_fails(self, tracker):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        success, bbox = tracker.update(frame)

        assert success is False

    def test_update_updates_center(self, tracker):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracker.start_tracking(frame, (100, 200, 50, 60))

        initial_center = tracker.center
        tracker.update(frame)

        # Center may or may not change depending on implementation
        assert tracker.center is not None
```

### Testing get_output()

```python
    def test_get_output_returns_tracker_output(self, tracker):
        from classes.tracker_output import TrackerOutput

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracker.start_tracking(frame, (100, 200, 50, 60))

        output = tracker.get_output()

        assert isinstance(output, TrackerOutput)

    def test_get_output_has_correct_data_type(self, tracker):
        from classes.tracker_output import TrackerDataType

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracker.start_tracking(frame, (100, 200, 50, 60))

        output = tracker.get_output()

        assert output.data_type == TrackerDataType.POSITION_2D

    def test_get_output_tracking_active(self, tracker):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracker.start_tracking(frame, (100, 200, 50, 60))

        output = tracker.get_output()

        assert output.tracking_active is True
```

---

## Integration Test Examples

### Factory Tests

```python
class TestTrackerFactory:
    def test_create_tracker_returns_instance(self):
        from classes.trackers.tracker_factory import create_tracker

        tracker = create_tracker("CSRT", None, None, None)

        assert tracker is not None

    def test_unknown_tracker_raises(self):
        from classes.trackers.tracker_factory import create_tracker

        with pytest.raises(ValueError):
            create_tracker("unknown_tracker", None, None, None)
```

---

## Performance Tests

```python
@pytest.mark.slow
class TestTrackerPerformance:
    def test_update_fps(self, tracker):
        import time

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracker.start_tracking(frame, (100, 200, 50, 60))

        num_frames = 100
        start = time.time()

        for _ in range(num_frames):
            tracker.update(frame)

        elapsed = time.time() - start
        fps = num_frames / elapsed

        assert fps > 15  # Minimum acceptable FPS
```

---

## Test Markers

```python
# pytest.ini
[pytest]
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow tests
    requires_gpu: Requires GPU
```

Usage:

```python
@pytest.mark.unit
def test_initialization():
    pass

@pytest.mark.slow
def test_performance():
    pass
```

---

## Related

- [Creating Trackers](creating-trackers.md) - Implementation guide
- [Best Practices](best-practices.md) - Design guidelines
