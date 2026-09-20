# PXE-0172: Standalone gimbal control investigation

2026-09-17 — Source review and operator-authorized camera bench tests precede
optional dashboard integration. The work uses a separate feature branch and
does not change PixEagle runtime code or configuration.

Reviewed the supplied Qt application with protocol, backend and dashboard
specialist agents. Verified live video, status queries and ready/disabled
transitions; observed zoom, pan, tilt after restart, and home response. Center
point/box and off-center box selection reached active tracking, and camera
video contained tracking markers. The earlier inverted tilt limitation remains
a mounting/firmware question. Preserved exact protocol captures and identified
query starvation, GIA incompatibility, checksum validation gaps and unsafe
OFT-to-angle interpretation offline. Final read-only status confirmed tracking
disabled; all probe processes exited.

See the [bench checkpoint](../checkpoints/2026-09-17-phase-5-gimbal-control-bench.md)
for exact scope, evidence, limitations and the next slice. Room images remain
local under the gitignored `reports/gimbal-bench/` directory.

PDF-guided follow-up: preserved the camera/tracking manuals locally; documented
FED/ODR, manual versus fuzzy LOC, OFT box semantics and the TRA discrepancy.
Manual descriptor-0 chair selection reached active but did not hold the chair;
repeated temporary loss and changed scene were recorded before cancellation.
AI candidate selection was rejected for stale evidence, not claimed successful.
See [follow-up](../checkpoints/2026-09-17-gimbal-pdf-followup.md). The operator then
prioritized manual click/retarget/cancel and compact camera controls in PixEagle;
AI integration is explicitly deferred to a later slice.

2026-09-18 — Implemented the default-off manual control slice, telemetry fixes,
typed guarded APIs and responsive dashboard controls including roll. Revisited
the complete official Qt tracking workflow: click is fuzzy descriptor 9, drag
is descriptor 1, and temporary-loss state 3 is omitted from its display logic.
No hidden mandatory initialization or continuous tracking refresh was found.
Recorded initial click geometry agrees within one pixel; subsequent drift
remains unresolved. Resume checks passed 178 backend tests, 426 dashboard tests,
build and schema. See the [implementation/source-review checkpoint](../checkpoints/2026-09-18-gimbal-qt-workflow-review.md).

2026-09-19 — Operator reported camera-side rotation correcting the same tracking
failure in the official app; a read-only query confirmed ROT02. Finished the
requested camera Smart/fuzzy selection path behind the existing default-off
provider capability. Fixed the restart lifecycle-lock deadlock, blocked new
follow/target starts during shutdown and added external-provider cleanup. The
new isolated bench supervisor keeps Settings and startup on the same config.
Actual file-video API save/restart returned with a new PID and the saved rotation;
zero camera packets, user config unchanged. Offline checks: 399 backend tests,
433 dashboard tests, build, schema and compilation passed. Camera is disconnected
while operator is away; retention and AI candidate identity remain pending.
See the [offline Smart/restart checkpoint](../checkpoints/2026-09-19-gimbal-smart-restart.md).

2026-09-19 — Connected follow-up confirmed upright native ROT02 video; bench
rotation 180→0 and supervised restart returned successfully. Short Classic
retention, browser retarget and Cancel passed; later operator selections included
losses, and actual AI candidate identity remains pending. Preserved bounded wire,
action and private-image hash evidence. Added Classic drag rectangles with
rotation-aware center/dimension mapping, Qt descriptor 1, typed validation and
pointer cancellation/duplicate-click protection. 213 backend and 443 dashboard
tests, production build, schema and compilation passed. Bench runtime reloaded;
following off, camera currently disconnected. Mounting specialist review found
existing vertical presets insufficient to claim this installation; only two
installation profiles remain in scope. Next: operator powers camera in intended
vertical orientation for recorded standalone characterization, before any
follower mapping changes. See [drag/bench checkpoint](../checkpoints/2026-09-19-gimbal-drag-selection.md)
and [mounting audit](../checkpoints/2026-09-19-gimbal-mounting-audit.md).

2026-09-20 — Finished provider-advertised Fine/Normal/Fast movement presets,
custom speed/duration dialog and serialized mouse/touch/keyboard hold-to-repeat.
A tap completes one step; release ends repeats, and abort/focus/authority changes
request Stop. Defaults and ordinary tracker UI remain unchanged. Invalid GM
mount settings now reject initialization instead of silently selecting Vertical;
valid mappings remain unchanged pending hardware measurement. 491 backend tests,
471 dashboard tests, production build, schema and compilation passed. Offline
production-browser desktop/mobile checks intercepted all actions and passed.
Camera is off at operator request; updated isolated bench is running. Next test
starts with the known horizontal installation, then the intended base-pitched-up
90° arrangement. See [movement checkpoint](../checkpoints/2026-09-20-gimbal-movement-controls.md).

2026-09-20 — The operator paused hardware testing after a partial horizontal
session. Limited live browser pan/hold/release evidence is preserved in the
[horizontal checkpoint](../checkpoints/2026-09-20-gimbal-horizontal-acceptance.md);
rectangle acceptance and vertical mapping remain pending. Following was off.

2026-09-20 — Applied the requested UI/frontend consultation: compact pan/tilt
pad with Center, separate roll pair and vertical zoom rocker, compact Classic/
Smart selection, less persistent instruction text, labeled Cancel target/Stop.
Provider capability gating, 44-pixel buttons and existing hold behavior remain.
471 dashboard tests, production build and intercepted production-browser checks
at 320/390/768/1280 pixels passed. No camera actions were forwarded. See the
[remote-layout checkpoint](../checkpoints/2026-09-20-gimbal-remote-layout.md).

2026-09-20 — Final user-requested placement moves the optional remote card above
Command in the desktop sidebar, with video-first stacking on mobile. Added
concise opt-in setup and future-provider development guide. Incorporated upstream
CSI auto-open changes at f30dce2 and fixed selection source identity on every
capture-open path; unrelated-video selection regression passes. Final 659 backend
and 471 dashboard tests, build/schema, and intercepted five-width browser checks
passed. Implementation handed off; vertical/AI/full hardware acceptance remains
explicitly pending. Author identity supplied; remote push authentication failed.
See [handoff](../checkpoints/2026-09-20-gimbal-feature-handoff.md).
