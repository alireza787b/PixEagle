# OBB Operations Runbook

## Symptoms and checks
1. **OBB not drawing**
   - Check `/api/video/health` -> `obb_pipeline.geometry_mode`
   - Verify `SMART_TRACKER_DRAW_ORIENTED: true`
2. **Model refuses to switch**
   - Check `/api/models/models` metadata: `task`, `smarttracker_supported`
3. **Tracking unstable in OBB**
   - Inspect SmartTracker quality metrics:
     - `geometry_error_rate`
     - `frame_error_rate`
   - If error rate is high, OBB auto-fallback may activate.

## Emergency rollback
Set:
```yaml
SMART_TRACKER_DISABLE_OBB_GLOBALLY: true
```
Then restart tracker.

## Debug logging focus
- `[SmartTracker] Detection normalization failure`
- `[SmartTracker] OBB auto-disabled due to error budget breach`
- Model validation errors from `ModelManager`
