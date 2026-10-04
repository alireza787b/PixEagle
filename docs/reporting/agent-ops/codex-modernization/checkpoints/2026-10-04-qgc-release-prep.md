# QGC integration release-preparation checkpoint — 2026-10-04

## Position

The native PixEagle integration and camera-free release preparation remain on
`feature/qgc-native-integration`. No public PixEagle `main` change, customized
QGC release, installer, or hardware deployment was made.

The QGC worktree records the corresponding integration commits; this checkpoint
records the backend-side validation for the same boundary. Credentials, private
addresses, and operator log contents are intentionally excluded.

## Validation

- `bash scripts/check_schema.sh`: passed; schema contains 43 sections and 604
  parameters.
- `tools/generate_api_tool_candidates.py --check`: passed.
- Phase 0/API/docs/config guard suite: **154 passed**.
- Backend Unit suite with the CI exclusions: **3,467 passed, 41 skipped**
  because dlib is not installed, 13 warnings, 14 subtests passed.
- Backend Integration suite with the CI exclusions: **196 passed, 2 warnings**.
- Focused restart/default/replay/engine/altitude/fixed-wing suite: **142 passed**.
- Shared-link production fixture: **1 passed**, 60 authenticated control
  renewals and 60 JPEG WebSocket frames sharing the 128 KiB/s loopback relay.
- SIH evidence harness tests: **14 passed**.
- Focused recovery/transport suite: **226 passed**, covering runtime ownership,
  SIH validation contracts, backend supervision, streaming lifecycle, WebSocket
  reconnects, and video-stream integration.
- Dashboard: **491 tests passed**, lint passed, production build passed.
- Python AST parsing: 437 sources parsed successfully.
- Selected Ruff checks: passed from the locked tool environment.

Evidence logs and manifests are under
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-04/`.

## Limits still open

The software relay is not a radio or Raspberry Pi qualification. Camera UDP
motor-stop behavior, process death, QGC application suspension under load,
actual constrained-link throughput, and hardware camera acceptance remain open.
The Linux DEB package still requires host `libxcb-cursor-dev`; Windows and
Android artifacts have not been built. Fixed-wing sensorless guidance and the
measured multicopter attitude-envelope issue remain release blockers. No gains
were changed to conceal those findings.

The next unblocked work is portable release harness preparation and failure
recovery documentation. Camera reconnection is required only for the deferred
physical camera/failure retest and later Pi/router/PX4 ground checkpoint.
