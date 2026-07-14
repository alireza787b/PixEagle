# Model Download - User Experience Guide

## Overview
The `add_model.py` script provides a robust, user-friendly way to add detection models to PixEagle with automatic fallback mechanisms.

## User Experience Flow

### Scenario 1: Model Already Exists Locally ✅
**What the user sees:**
```
============================================================
  Model Manager - CLI
============================================================

[INFO] Models folder: 'models'
[INFO] Checking for model: 'yolo11n.pt'...
[INFO] ✅ Model file found locally: models\yolo11n.pt
[INFO] File size: 5.35 MB
[INFO] Skipping download - using existing model file.

[INFO] Validating model file...
[INFO] ✅ Model validation successful:
       Model Type: yolo11
       Classes: 80
       File Size: 5.35 MB

[INFO] Exporting model to NCNN format...
[INFO] ✅ NCNN export successful!
       NCNN Folder: models\yolo11n_ncnn_model
       Export Time: 12.34s

============================================================
  ✅ All operations completed successfully!
============================================================

[INFO] Model ready: models\yolo11n.pt
[INFO] NCNN export available: models\yolo11n_ncnn_model

[INFO] You can now use this model in PixEagle!
       • Use the web dashboard to switch models
       • Or configure it in config_default.yaml
============================================================
```

### Scenario 2: Automatic Download Success (YOLOv5) ✅
**What the user sees:**
```
[WARNING] Model file 'yolov5s.pt' not found locally.
Do you want to download the model? (y/n): y

[INFO] Attempting automatic download...
[INFO] Downloading yolov5s.pt from Ultralytics hub...
[INFO] ✅ Model downloaded: models\yolov5s.pt
[INFO] ✅ Model downloaded successfully: models\yolov5s.pt

[INFO] Validating model file...
[INFO] ✅ Model validation successful...
```

### Scenario 3: Automatic Download Success (YOLO11) ✅
**What the user sees:**
```
[WARNING] Model file 'yolo11n.pt' not found locally.
Do you want to download the model? (y/n): y

[INFO] Attempting automatic download...
[INFO] Downloading yolo11n.pt via Ultralytics YOLO class...
[INFO] ✅ Model downloaded from C:\Users\...\yolo11n.pt to models\yolo11n.pt
[INFO] ✅ Model downloaded successfully: models\yolo11n.pt
```

### Scenario 4: Automatic Download Failed - URL Suggestions 💡
**What the user sees:**
```
[WARNING] Model file 'yolo12n.pt' not found locally.
Do you want to download the model? (y/n): y

[INFO] Attempting automatic download...
[WARNING] Automatic download failed: Model loaded but file not found in expected cache locations.

[INFO] Don't worry! We'll help you get the model.

[INFO] 💡 Suggested download URLs (try these in order):
   1. https://github.com/ultralytics/assets/releases/download/v0.0.0/yolo12n.pt
   2. https://github.com/ultralytics/ultralytics/releases/download/v0.0.0/yolo12n.pt
   3. https://github.com/ultralytics/assets/releases/latest/download/yolo12n.pt

   Alternative: Try: python -c "from ultralytics import YOLO; YOLO('yolo12n')"

[INFO] Please provide a download URL for the model.
       You can:
       • Copy one of the URLs above and paste it here
       • Provide your own download URL
       • Press 'q' to quit and download manually

Enter download URL (or 'q' to quit): 
```

### Scenario 5: User Provides URL ✅
**What the user sees:**
```
Enter download URL (or 'q' to quit): https://github.com/ultralytics/assets/releases/download/v0.0.0/yolo12n.pt

[INFO] Downloading from provided URL: https://github.com/ultralytics/assets/releases/download/v0.0.0/yolo12n.pt
[INFO] This may take a few moments depending on file size...
[INFO] Downloading model from https://github.com/ultralytics/assets/releases/download/v0.0.0/yolo12n.pt...
[INFO] ✅ Download successful: models\yolo12n.pt
[INFO] ✅ Model downloaded successfully: models\yolo12n.pt
```

### Scenario 6: User Cancels Download
**What the user sees:**
```
Enter download URL (or 'q' to quit): q

[INFO] Download aborted. You can:
   1. Download the model manually and place it in the 'models' folder
   2. Run this script again with: --download_url <URL>
   3. Use the web dashboard to upload the model
```

### Scenario 7: User Provides Invalid URL
**What the user sees:**
```
Enter download URL (or 'q' to quit): invalid-url

[WARNING] URL doesn't start with http:// or https://. Trying anyway...

[INFO] Downloading from provided URL: invalid-url
[ERROR] Download failed: Invalid URL 'invalid-url': No scheme supplied.

[INFO] Troubleshooting tips:
   • Check if the URL is correct and accessible
   • Verify your internet connection
   • Try downloading the model manually from the Ultralytics website
   • Place the .pt file in the 'models' folder and run this script again
```

## Interactive Mode (No Arguments)

When run without arguments, the script provides helpful guidance:

```
============================================================
  Model Manager - CLI
============================================================

[INFO] Supported models:
  • YOLOv5: yolov5s.pt, yolov5m.pt, yolov5l.pt, yolov5x.pt
  • YOLO8:  yolov8n.pt, yolov8s.pt, yolov8m.pt, yolov8l.pt, yolov8x.pt
  • YOLO11: yolo11n.pt, yolo11s.pt, yolo11m.pt, yolo11l.pt, yolo11x.pt
  • Future versions (yolo12, yolo13, etc.) are also supported!

Please enter the model file name (e.g., yolo11n.pt):
```

## Command-Line Usage

### Basic Usage
```bash
python add_model.py --model_name yolo11n.pt
```

### With Custom URL
```bash
python add_model.py --model_name yolo12n.pt --download_url https://example.com/yolo12n.pt
```

### Skip NCNN Export
```bash
python add_model.py --model_name yolo11n.pt --skip_export
```

## Robust Fallback Chain

The script uses a smart fallback system:

1. **Local Check** → Uses existing model if found
2. **User URL** → Uses provided URL if available
3. **Auto-Download YOLOv5** → Uses torch.hub
4. **Auto-Download YOLO8/11+** → Uses Ultralytics YOLO class
5. **Known URLs** → Tries common GitHub release URLs
6. **URL Suggestions** → Shows helpful URLs to user
7. **Interactive Prompt** → Asks user for URL as last resort

## Future-Proof Design

The implementation automatically handles:
- ✅ YOLOv5 (current)
- ✅ YOLO8 (current)
- ✅ YOLO11 (current)
- ✅ YOLO12, YOLO13, etc. (future versions)
- ✅ Custom models (with manual URL)

## Integration with PixEagle

After adding a model:
- ✅ Model appears in web dashboard
- Can be switched through the compatibility API: `POST /api/models/switch`.
  Clear any selected tracking target first; model activation is refused while
  following or while a target remains selected. Inference, target mutation,
  and model replacement are serialized so one frame cannot use a partially
  replaced detector.
- ✅ Can be configured in `config_default.yaml`
- ✅ NCNN export available for CPU inference

## Error Handling

All error scenarios provide:
- Clear error messages
- Troubleshooting tips
- Alternative solutions
- Graceful exit with helpful guidance
