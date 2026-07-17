# Phase 5 Bootstrap, Full, And Raspberry Pi Handoff Readiness

Date: 2026-07-16

Issues: PXE-0074, PXE-0099

Code commit: `6df1cb4e3b25b61f195dd64b801bffac90e85ee5`

Status: automated VPS gates complete; Raspberry Pi execution pending

## Scope

This slice closed the last concrete setup/runtime blockers found while preparing
the Raspberry Pi handoff. It did not change flight, follower, tracker, API,
dashboard, QGC, or field behavior.

The acceptance order is deliberately bounded:

1. Install and verify Core on a clean 64-bit Raspberry Pi OS host.
2. Run the authenticated LAN browser demo and inspect logs.
3. Add Full AI dependencies only after Core is accepted.
4. Add a separately trusted local model before claiming SmartTracker readiness.
5. Keep dlib, NCNN, custom OpenCV/GStreamer, service installation, PX4, and QGC
   outside the first board gate.

## Correctness Fixes

- The launcher now loads `Telemetry.WEBSOCK_PORT` from the same config contract
  used by the backend instead of retaining the default `5551` during lifecycle
  checks.
- Backend, telemetry, and MAVSDK ports use the shared canonical decimal
  validator. Zero, leading-zero/octal-looking values, oversized values, and
  values above `65535` fail before startup.
- The AI installer writes its machine-readable import result through private
  file descriptor 3. First-run Ultralytics settings output can remain visible
  without corrupting JSON verification or rolling back a valid Full install.
- Exact `-h` and `--help` requests for the PyTorch and AI installers bypass the
  exclusive mutation lock, so help remains available while PixEagle is running.
  Install and dry-run paths retain the existing lock policy.
- The clean-walkthrough manifest now stores portable `logs/...` references
  instead of host-specific absolute evidence paths.

## Runtime Evidence

The disposable Core checkout was installed under
`/tmp/pixeagle-core-acceptance-20260716` with service setup disabled. The Core
venv, dashboard dependencies, config lifecycle, and checksum-pinned MAVSDK
Server/MAVLink2REST binaries completed.

The same disposable environment then completed the Full CPU path with:

- PyTorch `2.6.0+cpu`
- torchvision `0.21.0+cpu`
- torchaudio `2.6.0+cpu`
- Ultralytics `8.4.95`
- lap `0.5.13`
- OpenCV `4.11.0`, preserved as the existing contrib provider

A deliberately empty Ultralytics settings directory caused the real first-run
notice to be emitted during the final verifier run. Imports still passed, the
OpenCV/PyTorch fingerprints remained valid, and the venv transaction committed.
The readiness report correctly says `model_required`; it does not claim model
load, inference, or tracking.

The candidate runtime then started the backend with configured ports `15077`
and `15551`. Typed telemetry health and media health returned HTTP `200`, video
file frames were active, and exact-run shutdown retained the unrelated public
dashboard listener on port `3040`.

Evidence:

- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-16-pxe0074-full-bootstrap-acceptance/`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-16-pxe0074-6df1cb4e-exact-clean-handoff/`

## ARM64 Preflight

The official PyTorch CPU indexes currently publish the matrix-selected CPython
3.12 Linux aarch64 artifacts for torch `2.6.0`, torchvision `0.21.0`, and
torchaudio `2.6.0`:

- <https://download.pytorch.org/whl/cpu/torch/>
- <https://download.pytorch.org/whl/cpu/torchvision/>
- <https://download.pytorch.org/whl/cpu/torchaudio/>

The cross-platform metadata preflight also found ARM64 wheels for the current
MAVSDK, OpenCV, lap, and primary numerical packages. `filterpy` is distributed
through a source package rather than a wheel in that strict binary-only probe;
the maintained initializer installs the required build tooling. Artifact
availability is not board execution evidence, so Raspberry Pi Full remains
pending.

## Validation

- Focused setup/runtime policy gate: `272 passed`
- Mandatory API/parameters gate: `72 passed`
- Setup handoff harness tests: `4 passed`
- Candidate regressions after review fixes: `7 passed`
- `bash scripts/check_schema.sh`: `40` sections, `540` parameters, current
- Bash syntax: passed for all touched shell scripts
- ShellCheck: passed with the existing sourced-file `SC2317` suppression
- `git diff --check`: passed
- Exact clean-checkout walkthrough: `26/26` commands passed
- Exact clean dashboard gate: `49/49` suites, `296/296` tests, build passed

The bounded independent review initially identified the missing real Full run,
stale evidence identity, and octal-looking port edge case. The real Full run,
portable exact-commit evidence, shared port fix, and regression coverage closed
those findings. Final verdict: `GO` for the Raspberry Pi operator gate.

## Exact Handoff Refresh

After the public VPS restart gate passed, the final pushed candidate
`a25b104b4b74ac8e8fda2da70ac07a7cf5f04c2f` was rechecked through the clean
setup handoff harness. The first run passed 20 commands and correctly refused
`scripts/update.sh --dry-run` because the accepted public demo still owned ports
`3040` and `5077`; this was retained as fail-closed lifecycle evidence, not
misreported as updater success.

A second run used the harness's explicit `--skip-update-check` boundary rather
than stopping the tester bench or weakening lifecycle detection. It passed
`23/23` current clean-clone commands: all required files, clean initial/final
Git state, setup shell syntax, binary plan, local/QGC/browser/production profile
dry-runs, quick-demo/cleanup dry-runs, schema `40/540`, and `72` minimum
backend/API tests.

The final exact-candidate refresh added the dashboard lane from a separate clean
worktree pinned to `a25b104b`. It passed `26/26` commands with clean initial and
final source state, including `npm ci`, `49/49` dashboard suites, `297/297`
tests, and a production build. The earlier exact stopped-runtime updater and
Full evidence remain valid; repeat the updater dry-run after the public demo is
intentionally stopped and before tag/release.

The previously referenced owner handoff now exists at mode `0600`:

`/home/alireza/PIXEAGLE_RPI5_CORE_FIRST_TEST_HANDOFF_2026-07-16.md`

It pins the exact candidate, separates Core/browser/restart acceptance from
Full AI and trusted-model gates, forbids implicit model downloads and ad hoc
workarounds, and requires stop-on-first-failure target evidence.

A final local command audit corrected three handoff defects before publication:
the installer pipeline's failure could be masked by temporary-file cleanup,
`make logs` is an interactive attach command rather than a bounded evidence
capture, and generic `target.pt` examples did not select the schema-backed
default SmartTracker model path. The owner guide now preserves the installer
status, reads bounded component JSONL logs directly, and uses `yolo26n.pt` only
when that is the trusted artifact's intended filename. The maintained model
guide makes the same default/custom-path distinction.

The separate refresh reviewer could not start because its external agent quota
was exhausted, so no new independent verdict is claimed for these documentation
changes. This does not replace the earlier bounded independent `GO` on the setup
code and Full evidence. The exact clean harness, focused local tests, command
audit, and the physical target gates below remain the acceptance basis.

Documentation/evidence commit
`247b125ee393f6cf0f1e85f95c1f5935fa315f0e` contains the corrected model guide
and complete preflight artifacts without changing setup, runtime, or dashboard
code from clean-harness candidate `a25b104b`. The owner handoff pins `247b125e`
so the Raspberry Pi checkout includes those maintained instructions.

Refresh evidence:

- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-16-pxe0074-a25b104b-rpi-handoff-preflight/manifest.json`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-16-pxe0074-a25b104b-rpi-handoff-preflight/active-runtime-update-refusal.json`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-16-pxe0074-a25b104b-rpi-handoff-preflight/logs/`

## Claim Boundary

This checkpoint proves setup/runtime behavior on the x86_64 VPS and exact clean
source checks through candidate `a25b104b`. It does not prove Raspberry Pi execution,
SmartTracker model inference, custom OpenCV/GStreamer, dlib, NCNN, QGC playback,
PX4, SIH, SITL, HIL, field, production deployment, or real-aircraft behavior.

## Next Gate

Follow the owner-only Raspberry Pi handoff in
`/home/alireza/PIXEAGLE_RPI5_CORE_FIRST_TEST_HANDOFF_2026-07-16.md`. Preserve
terminal output and generated setup evidence. Stop and report the first failed
command; do not compensate with undocumented package or config changes.
