# Motion Prediction

> Trajectory prediction during detection loss

The MotionPredictor component predicts target position during brief YOLO detection failures, enabling smooth tracking through temporary occlusions.

---

## Overview

Located at `src/classes/motion_predictor.py`, MotionPredictor provides:

- **Position history tracking** - Stores recent positions
- **Velocity estimation** - Computes instantaneous velocity
- **Position prediction** - Extrapolates during detection loss
- **Confidence decay** - Reduces confidence over prediction time

---

## When It's Used

```
Detection Success
      ↓
┌─────────────────┐
│ Update position │ ← Normal tracking
│ Update velocity │
└─────────────────┘
      ↓
Detection Failure (1-N frames)
      ↓
┌─────────────────┐
│ Predict position│ ← MotionPredictor takes over
│ Apply velocity  │
└─────────────────┘
      ↓
Detection Restored
      ↓
┌─────────────────┐
│ Resume normal   │
│ Update history  │
└─────────────────┘
```

---

## Algorithm

### Position History

```python
class MotionPredictor:
    def __init__(self, history_size=5, velocity_alpha=0.7):
        self.history_size = history_size
        self.position_history = deque(maxlen=history_size)
        self.velocity_alpha = velocity_alpha  # EMA smoothing
```

### Velocity Estimation

```python
def update(self, center, bbox, timestamp):
    """Update with new detection."""
    self.position_history.append({
        'center': center,
        'bbox': bbox,
        'timestamp': timestamp
    })

    # Compute velocity from recent positions
    if len(self.position_history) >= 2:
        dt = timestamp - self.position_history[-2]['timestamp']
        dx = center[0] - self.position_history[-2]['center'][0]
        dy = center[1] - self.position_history[-2]['center'][1]

        # EMA smoothing
        new_vel = (dx/dt, dy/dt)
        self.velocity = (
            self.velocity_alpha * new_vel[0] + (1-alpha) * self.velocity[0],
            self.velocity_alpha * new_vel[1] + (1-alpha) * self.velocity[1]
        )
```

### Position Prediction

```python
def predict(self, elapsed_time):
    """Predict position after elapsed_time since last update."""
    if not self.position_history:
        return None, None

    last = self.position_history[-1]
    last_center = last['center']
    last_bbox = last['bbox']

    # Extrapolate position
    pred_x = last_center[0] + self.velocity[0] * elapsed_time
    pred_y = last_center[1] + self.velocity[1] * elapsed_time

    # Maintain bbox size (no scale prediction)
    pred_bbox = (pred_x - last_bbox[2]/2, pred_y - last_bbox[3]/2,
                 last_bbox[2], last_bbox[3])

    return (pred_x, pred_y), pred_bbox
```

---

## Configuration

```yaml
SmartTracker:
  # Enable motion prediction
  ENABLE_PREDICTION_BUFFER: true

  # Frames to tolerate detection loss
  ID_LOSS_TOLERANCE_FRAMES: 5

  # Velocity smoothing (0=no smoothing, 1=no update)
  MOTION_VELOCITY_ALPHA: 0.7
```

---

## Integration with TrackingStateManager

```python
class TrackingStateManager:
    def _handle_detection_loss(self, frame_time):
        """Handle missing detection using motion prediction."""
        if not self.motion_predictor:
            return None

        # Check if within tolerance
        if self.frames_since_detection > self.tolerance_frames:
            return None

        # Get prediction
        elapsed = frame_time - self.last_detection_time
        predicted_center, predicted_bbox = self.motion_predictor.predict(elapsed)

        if predicted_center:
            # Use prediction with reduced confidence
            confidence = self._compute_prediction_confidence(elapsed)
            return {
                'center': predicted_center,
                'bbox': predicted_bbox,
                'confidence': confidence,
                'source': 'motion_prediction'
            }

        return None
```

---

## Confidence Decay

Prediction confidence decreases over time:

```python
def _compute_prediction_confidence(self, elapsed_frames):
    """Compute confidence based on prediction duration."""
    # Linear decay
    base_confidence = 0.8
    decay_rate = 0.15  # Per frame

    confidence = base_confidence - (decay_rate * elapsed_frames)
    return max(0.1, confidence)

# Frame 1: 0.65 confidence
# Frame 2: 0.50 confidence
# Frame 3: 0.35 confidence
# Frame 4: 0.20 confidence
# Frame 5: 0.10 confidence (minimum)
```

---

## Limitations

1. **Linear motion only** - No acceleration modeling
2. **No scale prediction** - Bbox size remains constant
3. **Short duration** - Designed for 1-5 frames
4. **No appearance** - Pure motion, no visual verification

For longer occlusions, use AppearanceModel for re-identification.

---

## Usage Example

```python
from classes.motion_predictor import MotionPredictor

predictor = MotionPredictor(history_size=5, velocity_alpha=0.7)

# During normal tracking
for detection in detections:
    predictor.update(detection['center'], detection['bbox'], time.time())

# During detection loss
elapsed = time.time() - last_detection_time
predicted_center, predicted_bbox = predictor.predict(elapsed)

if predicted_center:
    # Use prediction
    tracker_output.position_2d = normalize(predicted_center)
    tracker_output.metadata['source'] = 'motion_prediction'
```

---

## Related

- [AppearanceModel](appearance-model.md) - For longer occlusion recovery
- [ByteTrack/BoT-SORT](bytetrack-botsort.md) - Track-level Kalman filtering
- [SmartTracker](../02-reference/smart-tracker.md) - Full integration
