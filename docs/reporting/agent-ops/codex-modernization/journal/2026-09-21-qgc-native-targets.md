# 2026-09-21 — Native QGC target operations, backend slice 3

Implemented optional displayed-frame guards on existing target APIs, shared
target-state/revision observation, bounded original-frame/Smart-candidate
retention, authenticated actor audit and payload-bound idempotence. Native
tracking works without PX4 while both backend connections are disconnected.
Tracking Cancel is separate from following; native following and gimbal movement
remain disabled. Existing dashboard signatures remain compatible.

Client-agent review identified two concrete commit boundaries: source reset
could interleave validation and initialization, and durable audit could outlast
the capture deadline. Added shared source/telemetry transactions, retained
camera orientation and post-audit age revalidation. External final LOC is
guarded only after its awaited handshake; synchronous locks never span awaits.

Final focused backend gate: 1224 passes; schema 43/606, pinned fatal Python lint,
candidate generation and static checks pass. Real inhibited production replay
v3 passed seven target actions including stale rejection after a legacy-client
change, with aircraft disconnected throughout. A later demo-only asset choice
passed 11 preparation tests and produced separate clean recorded soccer-ball
footage for operator review; original snapshots remain unchanged. Paired simulated operator review also
identified an unexplained terminal loss-to-idle transition. The backend now
preserves `lost` after automatic recovery timeout until explicit Cancel or a new
selection/session. The clean demo suppresses only its private OSD layer, retaining
actual tracker feedback; this is not a production UI change.

The final menu review exposed mismatched schema/compatibility catalog aliases.
Both now share factory/request identities and actual prerequisite availability.
The scoped correction passed 51 focused and 59 route/candidate tests without
repeating the earlier 1224-case gate. A separate immutable clean-demo-v4 enables
CSRT/KCF/SparseFlow and honestly disables missing optional trackers; the active
older demo was not changed.

See [checkpoint](../checkpoints/2026-09-21-qgc-native-targets.md) and
[API contract](../../../../apis/native-target-operations.md). Evidence and exact
source hashes are in `reports/qgc-slice3/`. QGC screenshots/paired UI qualification
and real user feedback belong to the paired checkpoint; no hardware, real AI,
release, full-CI or human-feedback success is inferred from backend tests.
