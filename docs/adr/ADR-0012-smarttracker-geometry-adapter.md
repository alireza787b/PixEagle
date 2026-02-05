# ADR-0012: SmartTracker Geometry Adapter (AABB + OBB)

## Status
Accepted

## Context
PixEagle SmartTracker originally assumed detect-model outputs (`results[0].boxes`).
OBB models provide oriented outputs (`results[0].obb`) and broke runtime assumptions.

## Decision
Use an adapter layer (`detection_adapter.py`) plus geometry helpers (`geometry_utils.py`) to normalize model outputs into a stable internal schema.

## Why this approach
- Zero-break for existing followers and telemetry (AABB always provided).
- No hardcoded model-name logic (capability-based behavior).
- Easy extension for future geometry types (segmentation/polygon/keypoints).

## Consequences
- Slight additional CPU overhead in adapter path.
- Better resilience with explicit malformed-geometry handling.
- Cleaner boundaries between model output and tracker logic.
