# Phase 4 Exact-Candidate VPS Handoff

Date: 2026-07-16

## Status

Automated VPS migration and public lab smoke are complete. Exact pushed source
`9b1b6f6ce74106a93e4ee3d12872950c89dc6cca` is running and ready for the
maintainer's authenticated browser review. This is not a tag, release,
production deployment, Raspberry Pi, PX4, QGC receiver, or field claim.

## State Preservation

- Confirmed no old manual/service PixEagle runtime or listener was active before
  migration; no unknown process was stopped.
- Created owner-only backup
  `/home/alireza/pixeagle-vps-backups/20260716T151554Z-pre-f7615ac9`.
- The backup `SHA256SUMS` digest is
  `46666cff632db6dae387591ccf9f5703b260c334c7703a4d69464b9e94aa6959`.
- Preserved the existing `pixeagle-demo` admin password. Browser-user and QGC
  token files remained byte-identical; no plaintext credential was recorded.

## Config Migration

The supported contract-v2 preview/apply path, not direct YAML editing, applied
the complete reviewed plan:

- 9 new current parameters;
- 1 changed tracker default adopted (`botsort_reid` to `botsort`);
- 11 explicitly registered retirements removed;
- 21 requested, 21 applied, 0 skipped, 0 unknown extensions;
- managed backup `config_20260716_152424_609171_zfc9tq8a` created;
- post-report: 0 new, changed, retired, extensions, or actionable paths.

The final runtime config remains owner-only mode `0600`. The update dry-run
passed before launch with no active runtime and no source/environment changes.

## Live Startup Findings

The first exact-candidate launch found three narrow launcher defects:

1. the orphan inventory could observe its own short-lived `paste` helper after
   runtime ownership variables were exported;
2. runtime log preparation requested a nested venv lock from an existing
   lifecycle-lock context and printed a false fallback warning;
3. the advisory `cv2`/`numpy` probe made the same nested request and printed a
   false dependency warning.

The fixes are deliberately small: shell-native PID joining, standard-library
log pre-creation with the launcher Python, and a direct advisory import. Actual
runtime components still acquire their shared source/venv locks. Dedicated
regressions execute the real functions. A bounded independent reviewer was
asked to report only reproducible release blockers and returned `GO`.

## Validation

- `tests/test_runtime_process_ownership.py`: 39 passed.
- Ownership plus runtime-log focused gate: 54 passed.
- `tests/test_setup_profiles.py`: 150 passed.
- Bash syntax, ShellCheck (excluding only repository-standard `SC1091`), and
  `git diff --check`: passed.
- Prior exact candidate broad gate remains valid: 3275 passed, 48 expected
  skips, 1 deliberate deselection, zero failures; dashboard 49 suites/296 tests
  and production build passed.

## Exact Public Run

- Commit: `9b1b6f6ce74106a93e4ee3d12872950c89dc6cca`.
- Run: `pixeagle_manual_97590a57-ba07-4781-a99e-5acf76e0d456`.
- Expected/healthy components: `Dashboard`, `MainApp`.
- MAVLink2REST and MAVSDK Server were intentionally skipped (`-m -k`).
- Dashboard: `http://204.168.181.45:3040/` returned `200`.
- Unauthenticated typed telemetry API returned `401`.
- Anonymous lab MJPEG returned multipart data containing complete JPEG frames.
- Anonymous lab WebSocket returned frame metadata plus a complete 19614-byte
  JPEG; unauthorized Origin was rejected with `403`.
- Desktop `1440x900` and mobile `390x844` login views rendered without visible
  overflow. Durable screenshots and the redacted manifest are under
  `../evidence/2026-07-16-pxe0098-vps-handoff/`.
- Owner-only maintainer checklist:
  `/home/alireza/PIXEAGLE_VPS_TEST_HANDOFF_2026-07-16.md` (SHA-256
  `09d1173e0f20ba5d4e198cfa64fc108b8d52fced25b47806564799dbcb0a890a`).

Expected lab-only log signals remain explicit: MAVLink2REST is disconnected
because it was skipped, the 1280x720 demo file differs from the configured
640x480 capture hint, OSD may auto-degrade on the VPS, and public plain HTTP is
reported as non-production exposure. No unexpected model-cache/startup error
remains.

## Next Gate

1. Maintainer performs the authenticated dashboard/action checklist with the
   unchanged password and reports page/action/time plus screenshots for defects.
2. After acceptance, execute the documented fresh Raspberry Pi 5 Core path,
   then optional Full AI/OpenCV-GStreamer target paths only when selected.
3. Keep anonymous media and public HTTP limited to this lab. Production requires
   reviewed TLS/firewall/private-transport deployment and cleanup evidence.
4. Resume QGC PR/manual Windows receiver work only after PixEagle acceptance.
5. Tag/release only after the target walkthrough and acceptance gates pass.

## Claim Boundary

No PX4, SIH/SITL, HIL, follower response, real aircraft, Raspberry Pi, target
AI/GStreamer, QGC playback/recording, production TLS/firewall, tag, or release
success is claimed here.
