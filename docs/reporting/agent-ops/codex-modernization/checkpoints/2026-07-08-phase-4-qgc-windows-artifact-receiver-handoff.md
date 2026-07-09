# 2026-07-08 Phase 4 QGC Windows Artifact And Receiver Handoff

## Phase / Slice

- Phase 4 QGC direct-media compatibility
- Issue: PXE-0070 remains in progress
- Scope: produce a fresh Windows AMD64 installer for draft QGC PR #13594,
  verify package installation, publish a receiver-test runbook, and preserve
  exact resume evidence.

## Outcome

- QGC PR #13594 remains open and draft.
- QGC feature branch remained unchanged at
  `b98848b2c5e9afb5109bd49200c1d9aaa0185e5c`.
- The expired upstream Windows artifacts could not be rerun or dispatched by
  the fork owner because upstream Actions requires maintainer permissions.
- A temporary manual-only workflow was added to the fork default branch,
  repaired after its first run exposed a PowerShell summary parser error,
  removed after the first artifact was secured, then restored for corrected
  package-verification evidence.
- Fresh run `28971178285` completed successfully:
  - Windows AMD64 Release configure/build passed;
  - pre-install executable verification passed;
  - NSIS installer creation passed;
  - silent clean-directory install passed;
  - 28 bundled GStreamer plugin DLLs were found;
  - its installed executable verification step passed, but later review found
    that slash-style mismatch left the build GStreamer SDK in PATH;
  - artifact upload passed.
- The installer was downloaded to:
  `/home/alireza/qgc-pr13594-windows-artifacts/run-28971178285/QGroundControl-installer-AMD64.exe`
- Installer size: `144014734` bytes.
- Installer SHA-256:
  `3fff77fb0eb63c683a501856e7bc4e7389c365a4c3d955b7a75faacfd7f98856`.
- GitHub artifact:
  `QGroundControl-installer-AMD64-pr13594`, ID `8180855876`, retained until
  2026-07-22 UTC.
- Run URL:
  <https://github.com/alireza787b/qgroundcontrol/actions/runs/28971178285>

Independent review on 2026-07-09 therefore rejected the packaged-runtime claim
from run `28971178285`. The workflow was restored to canonicalize PATH entries
case-insensitively and fail closed when the build SDK bin is present.
Corrective run `28993788648` failed that guard because GitHub re-injected the
build SDK path between steps. Fork commit `0952f43f2` moved installed
verification into one sanitized PowerShell process, and rerun `28998523729` is
the active package-verification gate:

<https://github.com/alireza787b/qgroundcontrol/actions/runs/28998523729>

## QGC Fork Workflow History

- `129fb4018`: added the temporary artifact workflow.
- First run `28969299585`: QGC build, installer, clean install, plugin check,
  and installed-executable verification passed; only the helper's PowerShell
  summary line failed before upload.
- `6319f75e9`: fixed summary writing and aligned upload-artifact with the QGC
  workflow convention.
- Run `28971178285`: passed and uploaded the installer.
- `63fc784f3`: removed the temporary workflow from the fork default branch.
- `5ed773b99`: restored the temporary workflow with canonical PATH filtering
  and an explicit SDK-absence assertion for corrective run `28993788648`.
- Run `28993788648`: failed the new SDK-absence guard because GitHub
  re-injected the SDK path between steps.
- `0952f43f2`: moved installed-executable verification into the same
  PowerShell process that overwrites `PATH`; corrective run `28998523729` is
  active.

These fork-default-branch commits did not modify the PR feature branch.

## Maintained Test Contract

Added
`docs/video/04-streaming/qgc-windows-receiver-test.md` with four independent
lanes:

1. generic anonymous HTTP MJPEG;
2. generic anonymous WebSocket JPEG;
3. same-host PixEagle loopback;
4. authenticated remote PixEagle HTTPS/WSS using the generated
   `media:read` Bearer credential, HTTP wrong-Origin checks, and WSS exact
   Origin enforcement.

The runbook records Windows session-credential behavior, source-host firewall
ownership, port boundaries, MKV/MOV recording, negative auth/Origin/TLS cases,
redaction requirements, and evidence/non-claim boundaries.

The current public PixEagle browser demo is not a QGC native-video test target:
it uses browser-session authentication, while QGC network video uses
None/Basic/Bearer.

## Disk Recovery

The host began at 99% filesystem use with about 1.2 GiB free. Safe cleanup
removed only regenerated or temporary material:

- pip/npm/browser automation caches;
- Gradle caches/daemon/native state, retaining the wrapper;
- named prior `/tmp` scratch environments and generated inspection output;
- Python `__pycache__`, pytest, mypy, and ruff caches under PixEagle and QGC.

Preserved:

- source repositories and git metadata;
- PixEagle reports/evidence and home handoff files;
- `.codex`, credentials, project virtual environments, and dashboard build;
- active Docker images, containers, and volumes for MDS SITL, Freqtrade, and
  Caddy.

After cleanup and installer download, the filesystem is at 91% use with about
7.0 GiB free. This is enough for the current artifact/reporting slice but still
requires monitoring before another large local QGC/Gazebo build.

## Independent Review

- QGC/Qt/GStreamer receiver review confirmed the four test lanes and required
  evidence. It highlighted Windows session-only credentials, source-host
  firewall ownership, MKV/MOV recording, TLS/Origin/token negative tests, and
  claims that remain unproven.
- Release/DevOps review confirmed the cleanup preserved project state and
  identified the need to record the exact artifact resume point and cleanup
  inventory. One proposed Offboard contradiction was rejected after direct
  verification because the phase map already records the later alias
  retirement.
- A final resumed review found the installed-verification PATH defect, clarified
  HTTP versus WebSocket Origin expectations, identified a shell-unsafe example
  placeholder, required explicit changed-file and validation inventories, and
  separated QGC session storage from PixEagle token lifetime. The documentation
  findings were corrected and the package claim remains open pending the
  corrective run.

## Files Changed

- `docs/video/04-streaming/qgc-windows-receiver-test.md`
- `docs/video/04-streaming/qgc-http-websocket-source-plan.md`
- `docs/video/04-streaming/http-mjpeg.md`
- `docs/video/04-streaming/websocket.md`
- `docs/video/04-streaming/README.md`
- `docs/video/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-07-08-phase-4-qgc-windows-artifact-receiver-handoff.md`

## Validation

- `git diff --check`: passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py -q`:
  23 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q`:
  54 passed.
- `bash scripts/check_schema.sh`: schema current, 41 sections and 549
  parameters.
- `sha256sum -c SHA256SUMS`: prior downloaded installer passed.
- QGC PR state: open/draft at
  `b98848b2c5e9afb5109bd49200c1d9aaa0185e5c`.

## Remaining PXE-0070 Gates

- User Windows playback and recording for generic HTTP MJPEG and WebSocket
  JPEG.
- Target PixEagle HTTPS/WSS proxy playback with the generated scoped Bearer
  token.
- Missing/wrong token rejection.
- HTTP missing-Origin allowance and wrong supplied-Origin rejection.
- Remote WebSocket missing/wrong-Origin rejection.
- TLS failure and private-CA validation.
- Credential/URL/log redaction.
- Reconnect, token rotation, bounded WebSocket payload, and sustained playback
  evidence.
- Operator acceptance before changing the PR from draft.

No QGC receiver playback, PixEagle remote HTTPS/WSS interoperability, PX4,
SITL, HIL, field, or real-aircraft success is claimed by this artifact build.

## Next Slices

After user receiver evidence:

1. close or iterate PXE-0070 while keeping the PR draft until accepted;
2. complete public-demo credential/firewall cleanup when the current test
   session ends;
3. collect target deployment evidence for PXE-0064/PXE-0068;
4. continue API/dashboard modernization and final no-legacy cleanup;
5. rerun exact-release-branch handoff gates before tag/release.
