# Selection Assist And Segmentation

PixEagle currently has two separate AI geometry paths. Their names and
capabilities should not be mixed.

## Classic Selection Assist

The dashboard **Selection Assist** action is available only in Classic tracker
mode. When configured, the optional `Segmentor` runs an Ultralytics
segmentation model, draws its result for the operator, and provides detected
regions for click-assisted target initialization. The selected region is then
tracked by the active Classic tracker.

This feature:

- is disabled by default
- requires the optional AI runtime
- reports runtime availability before the action is enabled
- does not prove identity or preserve a target through an occlusion
- requires a restart after changing its configured model

The canonical model list is `configs/segmentation_models.yaml`. Configure only
the selected value:

```yaml
Segmentation:
  DEFAULT_SEGMENTATION_ALGORITHM: yolo11n-seg
```

## SmartTracker Model Tasks

SmartTracker currently accepts Ultralytics `detect` and `obb` artifacts.
Uploaded `segment` models are rejected by model validation rather than silently
treated as bounding-box models. Adding normalized mask/polygon output to the
Smart backend, association, target selection, overlay, API, and tests is
deferred under `PXE-0143`.

## Operator Guidance

Use **Selection Assist** when a segmentation overlay makes a Classic target
easier to select. Use **Smart (AI)** for detector-based multi-object
association. The dashboard blocks Selection Assist while Smart mode is active,
so one pipeline owns target selection at a time.
