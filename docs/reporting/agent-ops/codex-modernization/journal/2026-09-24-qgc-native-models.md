# 2026-09-24 — QGC slice 3b installed model contract

Resumed the interrupted backend native-model implementation. Completed typed
installed-model inventory, bounded class-label reads and guarded selection
through the existing dashboard executor. Fixed the session fixture to construct
the immutable user registry correctly, rechecked inventory after checkpoint
validation, kept source-observation locks short during model loading, offloaded
target-state reads, and invalidated shared target revision after dashboard
standby selection.

Focused gate: 249 passed. Broader CI Phase-0/auth gate: 372 passed and the known
pinned-base gimbal fixture hygiene failure. Schema 43/606, fatal lint, generated
candidate provenance, compilation and diff checks passed. Evidence is under
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-3b-2026-09-22/backend/`; the
execution timestamp is September 24. Model runtime and QGC screenshot/operator
checks are separate ongoing work. No physical control was performed.

See the [checkpoint](../checkpoints/2026-09-24-qgc-native-models.md) and
[API contract](../../../../apis/native-model-operations.md).

Later runtime review found that terminal Smart loss became an unexplained idle
native status. Added retained loss evidence without changing detection or
recovery policy; 260 combined tests and 35 final native-target cases passed.
See the [status addendum](../checkpoints/2026-09-24-qgc-smart-loss-status.md).
The first source manifest/archive remains preserved; `smart-loss-*` evidence
records the revised frozen source.
