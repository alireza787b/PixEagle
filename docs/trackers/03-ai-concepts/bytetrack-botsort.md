# ByteTrack and BoT-SORT

> Multi-object tracking algorithms for detection association

ByteTrack and BoT-SORT are multi-object tracking (MOT) algorithms that associate detections across frames, assigning consistent track IDs.

---

## Overview

| PixEagle mode | Appearance matching | Speed | Best For |
|-----------|-------|-------|----------|
| ByteTrack | No | Fast | Simple scenarios |
| BoT-SORT | No | Fast | Better occlusion handling |
| Custom ReID | Color/HOG | Medium | Explicit appearance-assisted recovery |

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
3. **Camera-motion compensation** - Uses the installed Ultralytics defaults

```yaml
SmartTracker:
  TRACKER_TYPE: "botsort"
```

PixEagle does not enable native BoT-SORT ReID or generate a custom BoT-SORT
tracker YAML. Selecting `botsort` uses the installed Ultralytics
`botsort.yaml`; its effective settings belong to that pinned dependency.

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
│ 2. Compute cost matrix    │ ← Installed tracker policy
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

### Custom Appearance Matching

PixEagle's explicit custom mode combines ByteTrack IDs with its local
`AppearanceModel` and recovery logic:

```yaml
SmartTracker:
  TRACKER_TYPE: "custom_reid"
  ENABLE_APPEARANCE_MODEL: true
```

This is not neural ReID and is not a fallback selected by dependency version.
It must be chosen deliberately and validated against the intended scene.

---

## Configuration Reference

```yaml
SmartTracker:
  # Tracker selection
  TRACKER_TYPE: "botsort"  # botsort, bytetrack, custom_reid

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

### Custom ReID

Choose when:
- The target has visually distinctive color/gradient features
- Appearance-assisted recovery is needed and has scenario-specific evidence
- CPU cost and lighting sensitivity are acceptable

---

## Related

- [Detection Backends](detection-backends.md) - Detection that feeds MOT
- [Motion Prediction](motion-prediction.md) - PixEagle's motion prediction
- [Appearance Model](appearance-model.md) - Custom ReID features
- [SmartTracker](../02-reference/smart-tracker.md) - Full integration
