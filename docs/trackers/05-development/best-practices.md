# Tracker Development Best Practices

> Design patterns, coding guidelines, and architectural recommendations

---

## Design Patterns

### Follow the BaseTracker Interface

Always extend `BaseTracker` and implement required methods:

```python
class MyTracker(BaseTracker):
    def start_tracking(self, frame, bbox):
        # Required
        pass

    def update(self, frame):
        # Required
        pass
```

### Use Factory Pattern

Register trackers in `TrackerFactory` instead of direct instantiation:

```python
# Good
tracker = create_tracker("CSRT", video_handler, detector, app_controller)

# Avoid
from classes.trackers.csrt_tracker import CSRTTracker
tracker = CSRTTracker(video_handler, detector, app_controller)
```

### Produce TrackerOutput

Always generate standardized output:

```python
def get_output(self) -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=self.tracking_started,
        # ...
    )
```

---

## State Management

### Always Set tracking_started

```python
def start_tracking(self, frame, bbox):
    # ... initialization logic ...
    self.tracking_started = True  # Required

def reset(self):
    self.tracking_started = False  # Required
```

### Use set_center() and normalize_bbox()

```python
def update(self, frame):
    # After getting new bbox
    self.set_center((new_x, new_y))  # Triggers normalization
    self.normalize_bbox()
```

### Maintain Center History

```python
def update(self, frame):
    # After successful update
    self.center_history.append(self.center)
```

---

## Configuration

### Load from Parameters

```python
def __init__(self, ...):
    my_config = getattr(Parameters, 'MyTracker', {})
    self.threshold = my_config.get('threshold', 0.5)  # With default
```

### Provide Sensible Defaults

```python
self.confidence_threshold = my_config.get('confidence_threshold', 0.5)
self.failure_threshold = my_config.get('failure_threshold', 5)
```

---

## Logging

### Use Module Logger

```python
import logging
logger = logging.getLogger(__name__)

# Initialization
logger.info(f"{self.tracker_name} initialized")

# Debug information
logger.debug(f"Confidence: {confidence:.2f}, bbox: {bbox}")

# Warnings
logger.warning(f"Tracking lost after {failures} failures")

# Errors
logger.error(f"Failed to initialize: {e}")
```

### Log Sparingly in update()

Avoid logging every frame:

```python
def update(self, frame):
    # Log only significant events
    if self.frame_count % 30 == 0:
        logger.info(f"FPS: {fps:.1f}, confidence: {conf:.2f}")

    # Log state changes
    if tracking_lost and not self.was_lost:
        logger.warning("Target lost")
```

---

## Error Handling

### Graceful Degradation

```python
def update(self, frame):
    try:
        success, bbox = self._do_tracking(frame)
    except Exception as e:
        logger.error(f"Tracking error: {e}")
        success = False
        bbox = self.prev_bbox  # Use last known

    return success, bbox
```

### Validate Inputs

```python
def start_tracking(self, frame, bbox):
    if frame is None:
        logger.error("Frame is None")
        return

    x, y, w, h = bbox
    if w <= 0 or h <= 0:
        logger.error(f"Invalid bbox dimensions: {bbox}")
        return
```

---

## Performance

### Avoid Memory Leaks

```python
def __init__(self, ...):
    # Use fixed-size queues
    self.center_history = deque(maxlen=50)
    self.confidence_history = deque(maxlen=10)
```

### Cache Expensive Computations

```python
def update(self, frame):
    # Don't recompute if unchanged
    if not self._needs_normalization():
        return self._cached_normalized_center
```

### Profile Critical Paths

```python
def update(self, frame):
    start = time.time()
    # ... tracking logic ...
    elapsed = time.time() - start

    if elapsed > 0.1:  # 100ms warning
        logger.warning(f"Update took {elapsed*1000:.1f}ms")
```

---

## Integration

### Support SmartTracker Override

```python
def update(self, frame):
    if self.override_active:
        return self._handle_override(frame)
```

### Support Estimators

```python
def update(self, frame):
    if self.estimator_enabled and self.position_estimator:
        self.position_estimator.set_dt(dt)
        self.position_estimator.predict_and_update(np.array(self.center))
```

### Handle Boundary Cases

```python
def update(self, frame):
    if self.is_near_boundary():
        penalty = self.compute_boundary_confidence_penalty()
        self.confidence *= penalty
```

---

## Testing

### Write Unit Tests First

```python
def test_start_tracking_initializes_state(self):
    tracker.start_tracking(frame, bbox)
    assert tracker.tracking_started
    assert tracker.bbox == bbox
```

### Test Edge Cases

```python
def test_update_before_start_returns_false(self):
    success, _ = tracker.update(frame)
    assert not success

def test_empty_bbox_handled(self):
    tracker.start_tracking(frame, (0, 0, 0, 0))
    # Should handle gracefully
```

### Test Integration

```python
def test_works_with_factory(self):
    tracker = create_tracker("MyTracker", ...)
    tracker.start_tracking(frame, bbox)
    success, _ = tracker.update(frame)
    assert success
```

---

## Documentation

### Document Class Purpose

```python
class MyTracker(BaseTracker):
    """
    Custom tracker for [specific use case].

    Implements [algorithm] with [key features].

    Attributes:
        tracker_name (str): Tracker identifier
        ...
    """
```

### Document Configuration

```yaml
# Add to docs/trackers/04-configuration/parameter-reference.md
MyTracker:
  threshold: 0.5  # Description of threshold
  ...
```

---

## Checklist

- [ ] Extends BaseTracker
- [ ] Implements start_tracking() and update()
- [ ] Uses set_center() and normalize_bbox()
- [ ] Sets tracking_started appropriately
- [ ] Returns TrackerOutput via get_output()
- [ ] Handles errors gracefully
- [ ] Logs appropriately
- [ ] Has unit tests
- [ ] Is registered in factory
- [ ] Has configuration section
- [ ] Is documented

---

## Related

- [Creating Trackers](creating-trackers.md) - Implementation guide
- [Testing Trackers](testing-trackers.md) - Testing strategies
