# ByteTrack and BoT-SORT

> Multi-object tracking algorithms for detection association

ByteTrack and BoT-SORT are multi-object tracking (MOT) algorithms that associate detections across frames, assigning consistent track IDs.

---

## Overview

| Algorithm | Re-ID | Speed | Best For |
|-----------|-------|-------|----------|
| ByteTrack | No | Fast | Simple scenarios |
| BoT-SORT | No | Fast | Better occlusion handling |
| BoT-SORT + ReID | Yes | Medium | Re-identification after occlusion |

---

## ByteTrack

ByteTrack (ECCV 2022) associates detections using:

1. **High-confidence matching** - Match high-conf detections to tracks
2. **Low-confidence association** - Re-match remaining tracks with low-conf detections
3. **Kalman prediction** - Predict track positions for matching

### Key Features

- No appearance features (motion-only)
- Fast processing
- Good for short occlusions

### Configuration

```yaml
SmartTracker:
  TRACKER_TYPE: "bytetrack"

  # ByteTrack parameters
  BYTETRACK_MATCH_THRESHOLD: 0.8
  BYTETRACK_SECOND_MATCH_THRESHOLD: 0.5
  BYTETRACK_NEW_TRACK_THRESHOLD: 0.6
```

---

## BoT-SORT

BoT-SORT builds on ByteTrack with improvements:

1. **Better Kalman filter** - Camera motion compensation
2. **Improved association** - More robust matching
3. **Optional ReID** - Appearance-based re-identification

### Without ReID

```yaml
SmartTracker:
  TRACKER_TYPE: "botsort"
```

### With Native ReID (Recommended)

Requires Ultralytics >= 8.3.114:

```yaml
SmartTracker:
  TRACKER_TYPE: "botsort_reid"
```

BoT-SORT with ReID uses appearance features to:
- Re-identify targets after long occlusions
- Handle ID switches during crossings
- Improve tracking consistency

---

## Association Process

```
Frame N Detections
        ↓
┌───────────────────────────┐
│ 1. Predict track positions │ ← Kalman filter
└───────────────────────────┘
        ↓
┌───────────────────────────┐
│ 2. Compute cost matrix    │ ← IoU + (ReID features)
└───────────────────────────┘
        ↓
┌───────────────────────────┐
│ 3. Hungarian matching     │ ← Optimal assignment
└───────────────────────────┘
        ↓
┌───────────────────────────┐
│ 4. Handle unmatched       │
│    - New tracks           │
│    - Lost tracks          │
└───────────────────────────┘
        ↓
Updated Tracks with IDs
```

---

## Track Lifecycle

### Track States

```python
# Track states in ByteTrack/BoT-SORT
NEW        # Just created, needs confirmation
TRACKED    # Confirmed, actively tracking
LOST       # Temporarily lost, searching
REMOVED    # Deleted after timeout
```

### Track Confirmation

New detections become confirmed tracks after N frames:

```yaml
SmartTracker:
  # Frames before track is confirmed
  BOTSORT_NEW_TRACK_FRAMES: 3
```

### Track Deletion

Lost tracks are removed after timeout:

```yaml
SmartTracker:
  # Frames before lost track is deleted
  BOTSORT_LOST_TRACK_BUFFER: 30
```

---

## ReID Features

When using BoT-SORT with ReID, appearance features are extracted:

```python
# Appearance feature extraction (Ultralytics internal)
# 512-dimensional embedding per detection
features = model.extract_features(frame, detections)

# Association includes appearance similarity
cost = (1 - iou_cost) * alpha + (1 - appearance_similarity) * beta
```

### Custom ReID (Fallback)

For older Ultralytics versions, PixEagle provides custom ReID:

```yaml
SmartTracker:
  TRACKER_TYPE: "custom_reid"
  ENABLE_APPEARANCE_MODEL: true
```

This uses the `AppearanceModel` class for feature matching.

---

## Configuration Reference

```yaml
SmartTracker:
  # Tracker selection
  TRACKER_TYPE: "botsort_reid"  # botsort_reid, botsort, bytetrack, custom_reid

  # ByteTrack/BoT-SORT common
  TRACKER_MATCH_THRESHOLD: 0.8
  TRACKER_NEW_TRACK_THRESHOLD: 0.6

  # BoT-SORT specific
  BOTSORT_APPEARANCE_THRESHOLD: 0.25
  BOTSORT_PROXIMITY_THRESHOLD: 0.5
  BOTSORT_CAMERA_MOTION_COMP: true

  # Track management
  ID_LOSS_TOLERANCE_FRAMES: 5
```

---

## Selecting a Tracker

### ByteTrack

Choose when:
- Simple tracking scenarios
- No long occlusions expected
- Maximum speed required

### BoT-SORT

Choose when:
- Better occlusion handling needed
- Camera motion present
- No re-identification required

### BoT-SORT + ReID

Choose when:
- Targets frequently occluded
- Multiple similar-looking targets
- ID consistency is critical

---

## Related

- [YOLO Detection](yolo-detection.md) - Detection that feeds MOT
- [Motion Prediction](motion-prediction.md) - PixEagle's motion prediction
- [Appearance Model](appearance-model.md) - Custom ReID features
- [SmartTracker](../02-reference/smart-tracker.md) - Full integration
