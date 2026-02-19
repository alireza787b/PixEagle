# YAML Config Comment Conventions

Comments in `configs/config_default.yaml` are parsed by `scripts/generate_schema.py`
to populate `configs/config_schema.yaml` automatically. Use the structured patterns
below so the generator can extract metadata for the dashboard UI.

---

## Supported Comment Patterns

### Options dropdown (pipe-separated — recommended)
```yaml
TARGET_LOSS_ACTION: hover  # Options: hover | orbit | stop | rtl | continue
MOUNT_TYPE: HORIZONTAL     # Options: HORIZONTAL | VERTICAL
```

### Options dropdown (comma-separated)
```yaml
PIPELINE_MODE: REALTIME    # Options: REALTIME, MAX_THROUGHPUT, DETERMINISTIC_REPLAY
```

### Options dropdown (with parenthetical descriptions)
```yaml
LATERAL_GUIDANCE: coordinated_turn  # Options: coordinated_turn (stable), sideslip (advanced)
```

### Units (trailing parenthetical — must be ≤15 chars, no `=` sign)
```yaml
MAX_VELOCITY: 10.0         # Maximum speed (m/s)
ORBIT_RADIUS: 150.0        # Loiter orbit radius (m)
BANK_ANGLE_MAX: 45.0       # Maximum bank angle (degrees)
CONFIDENCE: 0.5            # Detection confidence threshold (0-1)
```

### Recommended range (soft advisory, not a hard limit)
```yaml
JPEG_QUALITY: 80           # JPEG compression quality [50..95]
FPS: 30                    # Frame rate [15..60]
```

### Free-form description (no special structure)
```yaml
ENABLE_ALTITUDE_CONTROL: false  # Enable altitude hold. Set false for ground testing.
```

---

## What the Generator Does

1. **ruamel.yaml** loads the config and attaches inline comments to each mapping key.
2. **Comment text** is extracted and parsed for structured annotations.
3. **`SCHEMA_OVERRIDES` dict** (in `scripts/generate_schema.py`) applies semantic corrections
   with highest priority — range fixes, custom option lists, etc.
4. **`RECOMMENDED_RANGES` dict** adds soft advisory limits (warnings, not errors).

---

## What Is NOT Parsed as a Unit

Parenthetical phrases that look like explanations (not units) are ignored:

```yaml
CAPTURE_WIDTH: 640   # Width in pixels (lower = less CPU)
                     #                  ↑ has '=' → rejected as unit
                     #    'pixels' keyword → unit extracted as 'px' ✓

SOME_FLAG: 0         # Behaviour (0 = disabled)
                     #            ↑ has '=' → rejected as unit
                     #    no unit keyword → unit = None ✓
```

The unit validator requires the parenthetical to:
- Be ≤15 characters long
- Contain no `=` sign
- Start with a letter, `°`, or `%`

---

## SCHEMA_OVERRIDES — the Escape Hatch

When auto-inference gives a wrong result (e.g., a float in [0,1] that is actually
an angle in degrees), add an entry to `SCHEMA_OVERRIDES` in `scripts/generate_schema.py`:

```python
SCHEMA_OVERRIDES = {
    # Wrong: auto-inferred max=1.0 for a 0.25 default; correct max=180.0
    'MySection.SOME_ANGLE': {
        'min': -180.0, 'max': 180.0, 'step': 0.5, 'unit': 'deg',
        'description': 'Yaw offset in degrees',
    },
}
```

After editing `SCHEMA_OVERRIDES`, regenerate the schema:
```bash
python scripts/generate_schema.py
```

**Never edit `configs/config_schema.yaml` directly** — it is a generated file.

---

## Regenerating the Schema

```bash
# Regenerate after changing config_default.yaml or SCHEMA_OVERRIDES:
python scripts/generate_schema.py

# Verify schema is in sync (CI check):
bash scripts/check_schema.sh
```
