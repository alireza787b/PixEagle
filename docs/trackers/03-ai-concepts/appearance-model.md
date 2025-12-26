# Appearance Model

> Visual feature matching for target re-identification

The AppearanceModel component stores and matches visual features to re-identify targets after long occlusions or track ID changes.

---

## Overview

Located at `src/classes/appearance_model.py`, AppearanceModel provides:

- **Feature extraction** - Extracts visual features from target crops
- **Feature storage** - Maintains feature bank for selected target
- **Feature matching** - Finds best match among current detections
- **Confidence scoring** - Computes match confidence

---

## When It's Used

AppearanceModel is used for **custom ReID** when:

1. BoT-SORT native ReID is not available (Ultralytics < 8.3.114)
2. Track ID changes after long occlusion
3. Motion prediction fails to recover target

```yaml
SmartTracker:
  TRACKER_TYPE: "custom_reid"
  ENABLE_APPEARANCE_MODEL: true
```

---

## Feature Extraction

### Color Histogram

```python
def extract_features(self, frame, bbox):
    """Extract appearance features from crop."""
    x, y, w, h = bbox
    crop = frame[y:y+h, x:x+w]

    # Resize for consistent feature size
    crop_resized = cv2.resize(crop, (64, 128))

    # HSV color histogram
    hsv = cv2.cvtColor(crop_resized, cv2.COLOR_BGR2HSV)
    hist_h = cv2.calcHist([hsv], [0], None, [30], [0, 180])
    hist_s = cv2.calcHist([hsv], [1], None, [32], [0, 256])
    hist_v = cv2.calcHist([hsv], [2], None, [32], [0, 256])

    # Normalize and concatenate
    features = np.concatenate([
        cv2.normalize(hist_h, hist_h).flatten(),
        cv2.normalize(hist_s, hist_s).flatten(),
        cv2.normalize(hist_v, hist_v).flatten()
    ])

    return features
```

### Feature Bank

```python
class AppearanceModel:
    def __init__(self, config):
        self.feature_bank = []
        self.max_features = config.get('MAX_APPEARANCE_FEATURES', 10)
        self.update_interval = config.get('APPEARANCE_UPDATE_INTERVAL', 5)

    def update(self, frame, bbox, track_id):
        """Update feature bank with new observation."""
        features = self.extract_features(frame, bbox)

        # Add to bank, remove oldest if full
        self.feature_bank.append(features)
        if len(self.feature_bank) > self.max_features:
            self.feature_bank.pop(0)
```

---

## Feature Matching

### Similarity Computation

```python
def compute_similarity(self, query_features, stored_features):
    """Compute cosine similarity between feature vectors."""
    # Cosine similarity
    dot_product = np.dot(query_features, stored_features)
    norm_q = np.linalg.norm(query_features)
    norm_s = np.linalg.norm(stored_features)

    if norm_q == 0 or norm_s == 0:
        return 0.0

    return dot_product / (norm_q * norm_s)
```

### Best Match Selection

```python
def find_match(self, frame, detections, threshold=0.6):
    """Find best matching detection from feature bank."""
    if not self.feature_bank or not detections:
        return None

    best_match = None
    best_score = threshold  # Minimum threshold

    for detection in detections:
        det_features = self.extract_features(frame, detection['bbox'])

        # Compare to all stored features
        similarities = [
            self.compute_similarity(det_features, stored)
            for stored in self.feature_bank
        ]

        # Use maximum similarity (best match to any stored)
        max_similarity = max(similarities) if similarities else 0

        if max_similarity > best_score:
            best_score = max_similarity
            best_match = detection
            best_match['appearance_score'] = max_similarity

    return best_match
```

---

## Configuration

```yaml
SmartTracker:
  # Enable custom appearance model
  ENABLE_APPEARANCE_MODEL: true

  # Feature bank settings
  MAX_APPEARANCE_FEATURES: 10
  APPEARANCE_UPDATE_INTERVAL: 5

  # Matching thresholds
  APPEARANCE_MATCH_THRESHOLD: 0.6
  APPEARANCE_HIGH_CONFIDENCE: 0.8
```

---

## Integration with TrackingStateManager

```python
class TrackingStateManager:
    def _try_appearance_reidentification(self, frame, detections):
        """Attempt to re-identify target using appearance."""
        if not self.appearance_model:
            return None

        match = self.appearance_model.find_match(
            frame,
            detections,
            threshold=self.config.get('APPEARANCE_MATCH_THRESHOLD', 0.6)
        )

        if match:
            # Found re-identification match
            self.selected_track_id = match.get('track_id')
            return match

        return None
```

---

## When to Use

### Use Custom ReID

- Ultralytics version < 8.3.114
- Need explicit control over ReID process
- Custom feature extraction required

### Use BoT-SORT Native ReID

- Ultralytics >= 8.3.114
- Better performance (GPU-accelerated)
- More robust deep features

```python
# Check version and select
import ultralytics
if ultralytics.__version__ >= "8.3.114":
    tracker_type = "botsort_reid"  # Native ReID
else:
    tracker_type = "custom_reid"   # PixEagle AppearanceModel
```

---

## Limitations

1. **Color-based features** - Sensitive to lighting changes
2. **No deep learning** - Less robust than neural ReID
3. **Single target** - One feature bank per target
4. **CPU only** - No GPU acceleration

For production use, prefer BoT-SORT with native ReID when available.

---

## Example Usage

```python
from classes.appearance_model import AppearanceModel

config = {
    'MAX_APPEARANCE_FEATURES': 10,
    'APPEARANCE_UPDATE_INTERVAL': 5
}
appearance_model = AppearanceModel(config)

# During normal tracking - update features
if tracking_active:
    appearance_model.update(frame, selected_bbox, track_id)

# After track loss - attempt re-identification
if track_lost and detections:
    match = appearance_model.find_match(frame, detections)
    if match:
        # Re-identified target
        new_track_id = match['track_id']
        selected_bbox = match['bbox']
```

---

## Related

- [Motion Prediction](motion-prediction.md) - Short-term prediction
- [ByteTrack/BoT-SORT](bytetrack-botsort.md) - Native ReID option
- [SmartTracker](../02-reference/smart-tracker.md) - Full integration
