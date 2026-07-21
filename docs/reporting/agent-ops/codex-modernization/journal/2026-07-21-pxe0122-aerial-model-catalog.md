# PXE-0122 Journal: Aerial Model Catalog

**Date:** 2026-07-21 UTC

## Finding

PixEagle had robust local model admission guidance but no maintained selection
catalog. The AI backend guide also understated the work required to support
RT-DETR and generic exported runtimes.

## Result

Added an evidence-bounded catalog for general, aerial, oriented, maritime,
aircraft, and small-object use. Current support remains Ultralytics YOLO
`detect`/`obb`; alternate DETR, tiled, and runtime adapters are explicitly
deferred to benchmark-gated PXE-0123.

## Resume

Return to fresh VPS installer acceptance under PXE-0121/PXE-0074. Do not add a
new detector backend during that acceptance run.
