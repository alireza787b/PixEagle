# SmartTracker - Complete Guide

## Table of Contents

1. [Overview](#overview)
2. [How SmartTracker Works](#how-smarttracker-works)
3. [Integration with PixEagle](#integration-with-pixeagle)
4. [Tracker Modes](#tracker-modes)
5. [Getting Started](#getting-started)
6. [Changing YOLO Models](#changing-yolo-models)
7. [Configuration Reference](#configuration-reference)
8. [Advanced Tuning](#advanced-tuning)
9. [Developer Reference](#developer-reference)
10. [Troubleshooting](#troubleshooting)

---

## Overview

**SmartTracker** is PixEagle's AI-powered tracking system that uses **YOLO (You Only Look Once)** deep learning models for real-time object detection and tracking. It provides robust, intelligent tracking capabilities for autonomous drone following missions.

### Key Features

- ✅ **AI-Powered Detection** - Uses state-of-the-art YOLO models for object recognition
- ✅ **Click-to-Track** - Simple user interface for target selection
- ✅ **Multi-Object Awareness** - Detects and tracks multiple objects simultaneously
- ✅ **GPU Acceleration** - CUDA support for high-performance tracking (60+ FPS)
- ✅ **CPU Fallback** - Automatic CPU mode for embedded systems (15-30 FPS)
- ✅ **Custom Models** - Use any YOLO model (v8, v11, custom-trained)
- ✅ **Multiple Tracker Modes** - Choose between ByteTrack, BoT-SORT, or custom ReID
- ✅ **Robust Recovery** - Automatic re-identification after occlusions
- ✅ **PX4 Integration** - Seamless integration with PixEagle follower modes

### When to Use SmartTracker

**Use SmartTracker for:**
- 🎯 Person following (hikers, athletes, search & rescue)
- 🚗 Vehicle tracking (cars, boats, drones)
- 🐾 Animal tracking (wildlife monitoring)
- 📦 Object tracking (packages, equipment)
- 🎥 Cinematic shots with intelligent framing

**Use Classic Tracker (CSRT/KCF) for:**
- Simple scenarios with no occlusions
- When you don't have YOLO models installed
- Ultra low-power systems (Raspberry Pi Zero)

---

## How SmartTracker Works

SmartTracker combines three powerful technologies:

### 1. YOLO Object Detection

YOLO (You Only Look Once) is a real-time object detection system that:
- Detects 80 object classes (person, car, dog, etc.)
- Provides bounding boxes and confidence scores
- Runs at 30-60+ FPS on modern hardware

### 2. Multi-Object Tracking (MOT)

SmartTracker uses advanced tracking algorithms:

| Algorithm | Speed | Accuracy | ReID | Use Case |
|-----------|-------|----------|------|----------|
| **ByteTrack** | Fastest | Good | ❌ | Maximum FPS, simple scenarios |
| **BoT-SORT** | Fast | Better | ❌ | Balanced performance |
| **BoT-SORT+ReID** | Medium | Excellent | ✅ | Long occlusions, crowded scenes |
| **Custom ReID** | Medium | Very Good | ✅ | Offline/embedded systems |

### 3. Re-Identification (ReID)

When objects are temporarily occluded (hidden behind obstacles), ReID helps recover tracking by:
- **Visual Features** - Remembers object appearance (color, shape)
- **Similarity Matching** - Compares features when object reappears
- **ID Recovery** - Restores original track ID after occlusion

**Example Scenario:**
```
Frame 0: Person detected (ID: 5) - Walking
Frame 50: Person goes behind tree - Lost track
Frame 80: Person emerges from tree with new YOLO ID: 12
         ↓ ReID activates
Frame 81: SmartTracker recognizes same person
         ↓ ID restored to 5
Tracking continues seamlessly!
```

---

## Integration with PixEagle

SmartTracker integrates with PixEagle's architecture as an alternative tracker implementation:

```
┌─────────────────────────────────────────────────┐
│              PixEagle Main App                  │
│                                                 │
│  ┌──────────────┐         ┌─────────────────┐ │
│  │   Video      │────────▶│  Tracker        │ │
│  │   Handler    │         │  Selection      │ │
│  └──────────────┘         └─────────────────┘ │
│                                 │               │
│                    ┌────────────┴────────────┐ │
│                    ▼                         ▼ │
│          ┌──────────────────┐    ┌──────────────┐
│          │  SmartTracker    │    │ Classic      │
│          │  (YOLO+MOT)      │    │ Tracker      │
│          │                  │    │ (CSRT/KCF)   │
│          └──────────────────┘    └──────────────┘
│                    │                         │   │
│                    └────────────┬────────────┘   │
│                                 ▼                │
│                        ┌─────────────────┐       │
│                        │ Follower Mode   │       │
│                        │ (PX4 Commands)  │       │
│                        └─────────────────┘       │
└─────────────────────────────────────────────────┘
```

### Data Flow

1. **Video Input** → Video Handler captures frames
2. **Detection** → SmartTracker runs YOLO on each frame
3. **Tracking** → MOT algorithm assigns IDs and tracks objects
4. **User Selection** → User clicks on object to track
5. **Position Output** → Normalized position sent to Follower
6. **Drone Control** → Follower generates PX4 velocity commands

### TrackerOutput Schema

SmartTracker outputs data in PixEagle's unified `TrackerOutput` schema:

```python
TrackerOutput(
    data_type=TrackerDataType.MULTI_TARGET,
    tracking_active=True,
    position_2d=(norm_x, norm_y),         # Normalized [-1, 1]
    bbox=(x, y, width, height),            # Pixel coordinates
    confidence=0.87,                       # Detection confidence
    target_id=5,                           # Track ID
    targets=[...],                         # All detected objects
    quality_metrics={'fps': 28, ...},
    metadata={'tracker_algorithm': 'YOLO + BoT-SORT', ...}
)
```

---

## Tracker Modes

SmartTracker supports four tracking modes, each optimized for different scenarios:

### 🚀 ByteTrack (Fast)

**Best for:** Maximum speed, simple scenarios, high FPS requirements

```yaml
SmartTracker:
  TRACKER_TYPE: "bytetrack"
```

**Characteristics:**
- ✅ Fastest mode (0% FPS impact vs detection-only)
- ✅ Simple IoU-based matching
- ❌ No re-identification after occlusions
- ✅ Works offline (no internet needed)
- ✅ Runs on any hardware (CPU/GPU)

**Performance:** 60+ FPS on GPU, 25+ FPS on CPU

---

### ⚡ BoT-SORT (Balanced)

**Best for:** Better persistence than ByteTrack, balanced performance

```yaml
SmartTracker:
  TRACKER_TYPE: "botsort"
```

**Characteristics:**
- ✅ Better track persistence than ByteTrack
- ✅ Improved association logic
- ❌ Minimal re-identification capability
- ✅ Works offline
- ✅ Low FPS impact (-3-5%)

**Performance:** 55+ FPS on GPU, 22+ FPS on CPU

---

### 🎯 BoT-SORT + Native ReID (Professional)

**Best for:** GPU systems, long occlusions, crowded scenes, maximum accuracy

```yaml
SmartTracker:
  TRACKER_TYPE: "botsort_reid"
```

**Characteristics:**
- ✅ Ultralytics native ReID implementation
- ✅ Uses YOLO model's own features (zero overhead)
- ✅ Excellent re-identification accuracy (~92%)
- ✅ Camera motion compensation (optical flow)
- ⚠️ Requires Ultralytics ≥ v8.3.114
- ⚠️ Needs internet for first-time setup
- ✅ GPU recommended for best performance

**Performance:** 50+ FPS on GPU, 18+ FPS on CPU

**Requirements:**
```bash
# Check your Ultralytics version
python -c "import ultralytics; print(ultralytics.__version__)"

# Upgrade if needed
pip install --upgrade ultralytics
```

---

### 🏕️ Custom ReID (Offline/Embedded)

**Best for:** CPU-only systems, Raspberry Pi, air-gapped drones, offline operation

```yaml
SmartTracker:
  TRACKER_TYPE: "custom_reid"
```

**Characteristics:**
- ✅ Fully offline (no internet needed)
- ✅ Lightweight histogram/HOG features
- ✅ Configurable feature extraction
- ✅ Built-in performance profiling
- ✅ Good re-identification accuracy (~78-88%)
- ⚠️ Higher CPU usage (-8-12% FPS)

**Performance:** 45+ FPS on GPU, 15+ FPS on CPU

**Feature Modes:**
- `histogram` - Color-based (fastest, 2-3ms/object)
- `hog` - Shape-based (moderate, 5-7ms/object)
- `hybrid` - Combined (best accuracy, 8-10ms/object)

---

### Mode Comparison Table

| Mode | FPS Impact | ReID Quality | Offline | GPU Needed | Min Ultralytics |
|------|-----------|-------------|---------|-----------|----------------|
| `bytetrack` | 0% | None | ✓ | No | Any |
| `botsort` | -3-5% | Low | ✓ | No | Any |
| `botsort_reid` | -5-8% | Excellent | ✗ | Recommended | v8.3.114+ |
| `custom_reid` | -8-12% | Very Good | ✓ | No | Any |

---

## Getting Started

### Prerequisites

1. **Python 3.9+** with virtual environment
2. **PyTorch** installed (GPU version recommended)
3. **Ultralytics YOLO** package
4. **CUDA** (optional, for GPU acceleration)

### Quick Start

#### 1. Activate PixEagle Virtual Environment

**Important:** Always use PixEagle's virtual environment to ensure correct dependencies:

```bash
cd ~/PixEagle
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate     # Windows
```

⚠️ **You must activate the virtual environment before running any Python commands or PixEagle components.**

#### 2. Install/Verify PyTorch

For GPU (CUDA 12.4):
```bash
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
```

For CPU:
```bash
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
```

#### 3. Download a YOLO Model

Use PixEagle's model downloader:
```bash
python add_yolo_model.py
```

Or manually download:
```bash
# For GPU
wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt -O yolo/yolo11n.pt

# For CPU (NCNN format - faster on CPU)
python -c "from ultralytics import YOLO; YOLO('yolo11n.pt').export(format='ncnn')"
```

#### 4. Configure SmartTracker

Edit `configs/config.yaml`:

```yaml
SmartTracker:
  # Enable SmartTracker
  SMART_TRACKER_ENABLED: true

  # Hardware selection
  SMART_TRACKER_USE_GPU: true              # true = GPU, false = CPU
  SMART_TRACKER_FALLBACK_TO_CPU: true      # Auto-fallback if GPU fails

  # Model paths
  SMART_TRACKER_GPU_MODEL_PATH: "yolo/yolo11n.pt"
  SMART_TRACKER_CPU_MODEL_PATH: "yolo/yolo11n_ncnn_model"

  # Tracker mode (choose one)
  TRACKER_TYPE: "botsort_reid"  # Options: bytetrack, botsort, botsort_reid, custom_reid

  # Detection parameters
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.3   # Min detection confidence
  SMART_TRACKER_IOU_THRESHOLD: 0.3          # NMS overlap threshold
  SMART_TRACKER_MAX_DETECTIONS: 20          # Max objects per frame
```

#### 5. Run PixEagle

```bash
bash run_pixeagle.sh
```

#### 6. Use SmartTracker

1. Open dashboard: `http://localhost:3000`
2. Enable SmartTracker mode in UI
3. Wait for video feed to appear
4. **Click on any object** to start tracking
5. Drone will follow the selected object

---

## Changing YOLO Models

SmartTracker supports any Ultralytics YOLO model. Here's how to use different models:

### Option 1: Use Built-in Downloader

```bash
python add_yolo_model.py
```

Follow the interactive prompts to:
- Select model size (n, s, m, l, x)
- Choose export format (PyTorch, NCNN, ONNX)
- Auto-configure `config.yaml`

### Option 2: Manual Model Setup

#### A. Using Ultralytics Hub Models

```bash
# Download any model from Ultralytics
wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt -O yolo/yolo11s.pt
```

Update `config.yaml`:
```yaml
SMART_TRACKER_GPU_MODEL_PATH: "yolo/yolo11s.pt"
```

#### B. Using Custom-Trained Models

If you've trained a custom YOLO model:

```bash
# Place your model in the yolo directory
cp /path/to/your/custom_model.pt yolo/my_custom_model.pt
```

Update `config.yaml`:
```yaml
SMART_TRACKER_GPU_MODEL_PATH: "yolo/my_custom_model.pt"
```

#### C. Optimizing for CPU (NCNN Export)

For better CPU performance, export to NCNN format:

```python
from ultralytics import YOLO

# Load your model
model = YOLO('yolo/yolo11n.pt')

# Export to NCNN (optimized for CPU)
model.export(format='ncnn')
```

Update `config.yaml`:
```yaml
SMART_TRACKER_CPU_MODEL_PATH: "yolo/yolo11n_ncnn_model"
```

### Model Size Guide

| Model | Size | Speed (GPU) | Speed (CPU) | Accuracy | Use Case |
|-------|------|------------|------------|----------|----------|
| yolo11n | 2.6 MB | 60+ FPS | 25+ FPS | Good | Raspberry Pi, embedded |
| yolo11s | 9.4 MB | 55+ FPS | 20+ FPS | Better | Jetson Nano, balanced |
| yolo11m | 20 MB | 45+ FPS | 12+ FPS | Very Good | Jetson Xavier, powerful systems |
| yolo11l | 25 MB | 35+ FPS | 8+ FPS | Excellent | Desktop GPU |
| yolo11x | 68 MB | 25+ FPS | 4+ FPS | Best | High-end GPU, accuracy critical |

**Recommendation:**
- **Raspberry Pi:** yolo11n (NCNN format)
- **Jetson Nano:** yolo11s or yolo11n
- **Jetson Xavier:** yolo11m
- **Desktop GPU:** yolo11s or yolo11m
- **High-end GPU:** yolo11l

---

## Configuration Reference

### Core Settings

```yaml
SmartTracker:
  # === System Configuration ===
  SMART_TRACKER_ENABLED: true              # Enable/disable SmartTracker
  SMART_TRACKER_USE_GPU: true              # GPU acceleration
  SMART_TRACKER_FALLBACK_TO_CPU: true      # Auto-fallback to CPU

  # === Model Paths ===
  SMART_TRACKER_GPU_MODEL_PATH: "yolo/yolo11n.pt"
  SMART_TRACKER_CPU_MODEL_PATH: "yolo/yolo11n_ncnn_model"

  # === Detection Parameters ===
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.3  # Min confidence (0.0-1.0)
  SMART_TRACKER_IOU_THRESHOLD: 0.3         # NMS threshold (0.0-1.0)
  SMART_TRACKER_MAX_DETECTIONS: 20         # Max objects per frame

  # === Visualization ===
  SMART_TRACKER_COLOR: [0, 255, 255]       # BGR color (Yellow)
  SMART_TRACKER_SHOW_FPS: false            # Show FPS counter
```

### Tracker Type Selection

```yaml
  # === Tracker Mode ===
  TRACKER_TYPE: "botsort_reid"
  # Options:
  # - "bytetrack"     : Fast, no ReID (max FPS)
  # - "botsort"       : Better persistence, no ReID
  # - "botsort_reid"  : Ultralytics native ReID (best accuracy)
  # - "custom_reid"   : Lightweight offline ReID
```

### BoT-SORT ReID Configuration

Only used when `TRACKER_TYPE: "botsort_reid"`:

```yaml
  # === BoT-SORT ReID Settings ===
  BOTSORT_REID_MODEL: "auto"               # "auto" = YOLO features, or path to ReID model
  BOTSORT_APPEARANCE_THRESH: 0.25          # Lower = stricter (0.20-0.30 recommended)
  BOTSORT_PROXIMITY_THRESH: 0.5            # IoU threshold (0.4-0.6 recommended)
  BOTSORT_TRACK_BUFFER: 60                 # Memory frames (30=1s, 60=2s at 30 FPS)
  BOTSORT_MATCH_THRESH: 0.8                # IoU matching threshold
  BOTSORT_TRACK_HIGH_THRESH: 0.25          # High confidence detections
  BOTSORT_TRACK_LOW_THRESH: 0.1            # Low confidence recovery
  BOTSORT_NEW_TRACK_THRESH: 0.25           # New track creation threshold
  BOTSORT_FUSE_SCORE: true                 # Combine confidence with IoU
  BOTSORT_CMC_METHOD: "sparseOptFlow"      # Camera motion compensation
```

### Custom ReID Configuration

Only used when `TRACKER_TYPE: "custom_reid"`:

```yaml
  # === Custom ReID Settings ===
  ENABLE_APPEARANCE_MODEL: true            # Enable re-identification
  APPEARANCE_MATCH_THRESHOLD: 0.7          # Higher = stricter (0.6-0.7 recommended)
  APPEARANCE_FEATURE_TYPE: "histogram"     # "histogram", "hog", or "hybrid"
  MAX_REIDENTIFICATION_FRAMES: 30          # Memory window (frames)

  # Adaptive learning
  APPEARANCE_ADAPTIVE_LEARNING: true       # Adapt to appearance changes
  APPEARANCE_LEARNING_RATE: 0.1            # Learning speed (0.05-0.15)

  # HOG parameters (for "hog" or "hybrid" mode)
  HOG_WIN_SIZE: [64, 64]                   # Window size
  HOG_BLOCK_SIZE: [16, 16]                 # Block size
  HOG_BLOCK_STRIDE: [8, 8]                 # Stride
  HOG_CELL_SIZE: [8, 8]                    # Cell size
  HOG_NBINS: 9                             # Orientation bins

  # Histogram parameters (for "histogram" or "hybrid" mode)
  HIST_H_BINS: 30                          # Hue bins
  HIST_S_BINS: 32                          # Saturation bins

  # Performance profiling
  ENABLE_APPEARANCE_PROFILING: false       # Log timing metrics
```

### Tracking Robustness Settings

Works with ALL tracker types:

```yaml
  # === Tracking Strategy ===
  TRACKING_STRATEGY: "hybrid"              # "id_only", "spatial_only", or "hybrid"
  ID_LOSS_TOLERANCE_FRAMES: 5              # Frames to maintain tracking after ID loss
  SPATIAL_IOU_THRESHOLD: 0.35              # IoU threshold for spatial matching
  ENABLE_PREDICTION_BUFFER: true           # Motion prediction during occlusion
  CONFIDENCE_SMOOTHING_ALPHA: 0.8          # Confidence EMA smoothing
```

---

## Advanced Tuning

### Performance Optimization

#### For Maximum FPS

```yaml
TRACKER_TYPE: "bytetrack"
SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.4   # Higher = fewer detections
SMART_TRACKER_MAX_DETECTIONS: 10          # Limit processing
TRACKING_STRATEGY: "id_only"              # Skip spatial matching
```

#### For Maximum Accuracy

```yaml
TRACKER_TYPE: "botsort_reid"
SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.2   # Lower = more detections
BOTSORT_APPEARANCE_THRESH: 0.20           # Stricter ReID matching
BOTSORT_TRACK_BUFFER: 90                  # Longer memory (3 seconds)
TRACKING_STRATEGY: "hybrid"
```

#### For Embedded Systems (Raspberry Pi)

```yaml
TRACKER_TYPE: "custom_reid"
SMART_TRACKER_USE_GPU: false
SMART_TRACKER_CPU_MODEL_PATH: "yolo/yolo11n_ncnn_model"
APPEARANCE_FEATURE_TYPE: "histogram"      # Fastest ReID mode
MAX_REIDENTIFICATION_FRAMES: 20           # Less memory
SMART_TRACKER_MAX_DETECTIONS: 10
```

### Scenario-Specific Tuning

#### Crowded Scenes (Many Objects)

```yaml
TRACKER_TYPE: "botsort_reid"
BOTSORT_MATCH_THRESH: 0.85                # Stricter matching
SPATIAL_IOU_THRESHOLD: 0.4                # Higher threshold
SMART_TRACKER_MAX_DETECTIONS: 30          # Track more objects
```

#### Fast-Moving Objects

```yaml
ID_LOSS_TOLERANCE_FRAMES: 10              # More tolerance
ENABLE_PREDICTION_BUFFER: true            # Use motion prediction
BOTSORT_TRACK_BUFFER: 100                 # Longer memory
```

#### Long Occlusions (Objects Hiding)

```yaml
TRACKER_TYPE: "botsort_reid"              # Or "custom_reid"
BOTSORT_TRACK_BUFFER: 120                 # 4 seconds at 30 FPS
BOTSORT_APPEARANCE_THRESH: 0.30           # More lenient ReID
MAX_REIDENTIFICATION_FRAMES: 60           # Custom ReID memory
```

#### Similar-Looking Objects

```yaml
APPEARANCE_FEATURE_TYPE: "hybrid"         # Use both color and shape
BOTSORT_APPEARANCE_THRESH: 0.20           # Very strict matching
APPEARANCE_MATCH_THRESHOLD: 0.85          # High similarity required
```

---

## Developer Reference

### SmartTracker Class API

#### Initialization

```python
from classes.smart_tracker import SmartTracker

tracker = SmartTracker(app_controller)
```

#### Key Methods

```python
# Select object by click
tracker.select_object_by_click(x, y)

# Run tracking on frame
annotated_frame = tracker.track_and_draw(frame)

# Get tracker output
output = tracker.get_output()

# Clear selection
tracker.clear_selection()

# Get capabilities
caps = tracker.get_capabilities()
```

#### TrackerOutput Schema

```python
@dataclass
class TrackerOutput:
    data_type: TrackerDataType
    timestamp: float
    tracking_active: bool
    tracker_id: str

    # Primary target
    position_2d: Optional[Tuple[float, float]]  # Normalized [-1, 1]
    bbox: Optional[Tuple[int, int, int, int]]   # (x, y, width, height)
    normalized_bbox: Optional[Tuple[float, float, float, float]]
    confidence: Optional[float]

    # Multi-target data
    target_id: Optional[int]
    targets: Optional[List[Dict]]

    # Metrics and metadata
    quality_metrics: Dict
    raw_data: Dict
    metadata: Dict
```

### Architecture Components

```
SmartTracker
├── __init__()                    # Initialize YOLO, select tracker type
├── _select_tracker_type()        # Version detection, fallback logic
├── _build_tracker_args()         # Build Ultralytics tracker args
├── select_object_by_click()      # Handle user selection
├── track_and_draw()              # Main tracking loop
├── get_output()                  # Return TrackerOutput
└── clear_selection()             # Clear tracking state

TrackingStateManager (Robustness Layer)
├── start_tracking()              # Initialize tracking
├── update_tracking()             # Update with new detections
├── _match_by_id()                # ID-based matching
├── _match_by_spatial()           # IoU-based matching
├── _match_by_appearance()        # ReID-based matching
└── clear()                       # Clear state

AppearanceModel (Custom ReID)
├── extract_features()            # Extract visual features
├── _extract_histogram()          # Color histogram (HSV)
├── _extract_hog()                # HOG features
├── compute_similarity()          # Cosine similarity
├── register_object()             # Store appearance
├── mark_as_lost()                # Start memory countdown
├── find_best_match()             # Re-identify object
└── get_profiling_stats()         # Performance metrics
```

### Adding Custom Trackers

To add a new tracker mode:

1. **Update `_select_tracker_type()` in SmartTracker:**

```python
elif requested_type == 'my_tracker':
    logging.info("[SmartTracker] Using My Custom Tracker")
    return "mytracker", False  # (tracker_name, use_custom_reid)
```

2. **Add configuration parameters:**

```yaml
SmartTracker:
  TRACKER_TYPE: "my_tracker"
  MY_TRACKER_PARAM1: value1
  MY_TRACKER_PARAM2: value2
```

3. **Test and validate:**

```bash
python -c "from classes.smart_tracker import SmartTracker; print('Import OK')"
```

---

## Troubleshooting

### Common Issues

#### "Model not found" Error

**Symptom:** `FileNotFoundError: yolo/yolo11n.pt not found`

**Solution:**
```bash
# Download model
python add_yolo_model.py

# Or manually
wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt -O yolo/yolo11n.pt
```

#### GPU Not Working

**Symptom:** "CUDA not available, falling back to CPU"

**Solution:**
```bash
# Check CUDA
python -c "import torch; print(torch.cuda.is_available())"

# Reinstall PyTorch with CUDA
pip uninstall torch torchvision
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
```

#### Low FPS

**Symptom:** FPS < 15 on capable hardware

**Solutions:**
1. Use lighter model: `yolo11n.pt` instead of `yolo11x.pt`
2. Enable GPU: `SMART_TRACKER_USE_GPU: true`
3. Reduce detections: `SMART_TRACKER_MAX_DETECTIONS: 10`
4. Switch tracker: `TRACKER_TYPE: "bytetrack"`

#### Tracking Lost Frequently

**Symptom:** Loses track after brief occlusions

**Solutions:**
```yaml
# Increase tolerance
ID_LOSS_TOLERANCE_FRAMES: 10

# Enable motion prediction
ENABLE_PREDICTION_BUFFER: true

# Use ReID-capable tracker
TRACKER_TYPE: "botsort_reid"  # or "custom_reid"

# Increase memory buffer
BOTSORT_TRACK_BUFFER: 90
```

#### Wrong Object Tracked After Occlusion

**Symptom:** Tracks different object when original reappears

**Solutions:**
```yaml
# Stricter ReID matching
BOTSORT_APPEARANCE_THRESH: 0.15   # For BoT-SORT
APPEARANCE_MATCH_THRESHOLD: 0.85  # For Custom ReID

# Use hybrid features
APPEARANCE_FEATURE_TYPE: "hybrid"

# Disable adaptive learning
APPEARANCE_ADAPTIVE_LEARNING: false
```

#### BoT-SORT ReID Not Available

**Symptom:** "BoT-SORT ReID requires Ultralytics >=8.3.114"

**Solution:**
```bash
# Check version
python -c "import ultralytics; print(ultralytics.__version__)"

# Upgrade
pip install --upgrade ultralytics

# Or use custom ReID instead
# In config.yaml:
TRACKER_TYPE: "custom_reid"
```

### Performance Benchmarks

**Test System:** Jetson Xavier NX, YOLO11n, 640x480 resolution

| Tracker Mode | FPS | CPU % | GPU % | Memory |
|-------------|-----|-------|-------|--------|
| bytetrack | 58 | 45% | 65% | 1.2 GB |
| botsort | 55 | 48% | 68% | 1.3 GB |
| botsort_reid | 52 | 52% | 72% | 1.5 GB |
| custom_reid (histogram) | 48 | 58% | 65% | 1.4 GB |
| custom_reid (hog) | 44 | 65% | 65% | 1.5 GB |
| custom_reid (hybrid) | 40 | 72% | 65% | 1.6 GB |

### Debug Logging

Enable detailed logging:

```python
# In src/main.py or your startup script
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

Key log messages:
```
[SmartTracker] Using BoT-SORT with native ReID (Ultralytics 8.3.114)
[SmartTracker] Tracker: BOTSORT
[SMART] Tracking started: person ID:5 (conf=0.87)
[TrackingStateManager] ID switch: 5→8 (IoU=0.67)
[AppearanceModel] Match found: new ID:12→recovered ID:5 (similarity=0.825)
```

### Support

- 📖 **Documentation:** [PixEagle Docs](../README.md)
- 🐛 **Issues:** [GitHub Issues](https://github.com/alireza787b/PixEagle/issues)
- 💬 **Community:** Join discussions on GitHub
- 📺 **Videos:** [YouTube Playlist](https://www.youtube.com/watch?v=nMThQLC7nBg&list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)

---

## Quick Reference Card

### Essential Commands

```bash
# Download YOLO model
python add_yolo_model.py

# Start PixEagle
bash run_pixeagle.sh

# Check GPU support
python -c "import torch; print(torch.cuda.is_available())"

# Test SmartTracker
python src/test_Ver.py
```

### Configuration Quick Start

```yaml
# Minimum config
SmartTracker:
  SMART_TRACKER_ENABLED: true
  SMART_TRACKER_USE_GPU: true
  SMART_TRACKER_GPU_MODEL_PATH: "yolo/yolo11n.pt"
  TRACKER_TYPE: "botsort_reid"
```

### Tracker Mode Quick Select

```yaml
# Maximum speed
TRACKER_TYPE: "bytetrack"

# Balanced performance
TRACKER_TYPE: "botsort"

# Best accuracy (requires v8.3.114+)
TRACKER_TYPE: "botsort_reid"

# Offline/embedded
TRACKER_TYPE: "custom_reid"
```

---

**Document Version:** 2.2
**Last Updated:** 2025-10-09
**Author:** PixEagle Team
