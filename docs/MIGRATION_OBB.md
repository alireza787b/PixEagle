# SmartTracker OBB Migration Guide

## Compatibility promise
Existing detect-model workflows remain compatible by default.

## New SmartTracker config keys
- `SMART_TRACKER_MODEL_TASK_POLICY` (`auto|detect_only|allow_oriented`)
- `SMART_TRACKER_GEOMETRY_OUTPUT_MODE` (`legacy_aabb|hybrid|oriented_preferred`)
- `SMART_TRACKER_DRAW_ORIENTED` (`true|false`)
- `SMART_TRACKER_SELECTION_MODE` (`auto|aabb|oriented`)
- `SMART_TRACKER_MAX_ORIENTED_TRACKS` (int)
- `SMART_TRACKER_DISABLE_OBB_GLOBALLY` (bool)
- `SMART_TRACKER_OBB_AUTO_DISABLE_ERROR_RATE` (float)

## Safe defaults
Current defaults keep legacy behavior intact for detect models and enable additive OBB support when task is OBB.

## Rollback
Set:
```yaml
SMART_TRACKER_DISABLE_OBB_GLOBALLY: true
```
to force AABB-only behavior instantly.
