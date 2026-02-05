# Config Sync (Settings)

PixEagle includes a **Config Sync** dialog in Settings to safely reconcile your local `configs/config.yaml` with new `configs/config_default.yaml` updates.

## What it detects

- **New**: keys that exist in defaults/schema but are missing in your config.
- **Changed**: defaults that changed since the last saved defaults baseline snapshot.
- **Obsolete**: keys in your config that are no longer in schema.

## UX flow

1. Open Settings -> **Sync with Defaults**.
2. Select what to migrate:
   - New keys (preselected)
   - Changed defaults (opt-in)
   - Obsolete keys (preselected for archive+remove)
3. Click **Preview**.
4. Click **Apply Selected** to apply atomically.

## Safety model

- No value is overwritten unless explicitly selected.
- A config backup is created before apply.
- Obsolete keys are archived under `_ARCHIVED_OBSOLETE` before removal.
- Sync updates trigger `Parameters.reload_config()` after successful save.

## API endpoints

- `GET /api/config/defaults-sync`
- `POST /api/config/defaults-sync/plan`
- `POST /api/config/defaults-sync/apply`

## Notes

- Changed-default detection needs a baseline snapshot. On first sync scan, the baseline is initialized automatically and future upgrades are tracked.
