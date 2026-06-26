# 2026-06-24 Phase 4 QGC Authenticated Direct Media

## Phase / Slice

- Phase 4 API/security, streaming, and setup modernization
- Issue: PXE-0070 partial; PXE-0068 follow-up
- Scope: repair QGroundControl PR #13594 and add a guarded PixEagle profile
  for direct HTTPS/WSS media on a different GCS host.

## Summary

- Rebased the QGC feature branch onto upstream `master` and preserved generic
  anonymous HTTP/HTTPS MJPEG and WebSocket JPEG sources.
- Added generic, optional network-video controls to QGC rather than embedding
  PixEagle-specific behavior:
  - Basic or Bearer authentication only over HTTPS/WSS;
  - exact optional Origin;
  - strict TLS and optional custom CA trust;
  - session-only secret or owner-only credential file;
  - URL, GStreamer diagnostic, bus-error, and DOT-graph redaction;
  - bounded WebSocket messages and worker-thread ownership;
  - redirect denial for authenticated HTTP media;
  - MKV/MOV support and MP4 rejection for JPEG recording.
- Added QGC tests for URL validation/redaction, credential-file safety,
  authentication/transport policy, source construction, custom CA handling,
  WebSocket delivery/teardown, required plugins, and recording policy.
- Added the PixEagle `qgc_direct_media` setup profile:
  - backend remains on loopback behind an operator-managed HTTPS/WSS proxy;
  - exact public Host and Origin values are generated;
  - an owner-only, hashed `media:read` bearer record is generated;
  - plaintext is written only to a one-time owner-only handoff file;
  - rotation backs up only hashed credentials;
  - config, token, and handoff writes are transactional and rollback on error;
  - dry-run is side-effect free and does not claim proxy installation or QGC
    playback.
- Hardened PixEagle bearer/user credential loading against symlinks, hardlink
  aliases, non-regular files, wrong owner/mode, oversized files, and descriptor
  replacement races.
- Updated setup, API, configuration, onboarding, and media docs together with
  generated API/MCP provenance.
- On the 2026-06-25 resume review, PR #13594 was converted to draft because
  the branch is not yet user-tested end to end and the current upstream CI
  matrix is not fully green.

## QGC Revisions

- PR: <https://github.com/mavlink/qgroundcontrol/pull/13594>
- PR state: draft as of 2026-06-25 (`gh pr ready 13594 --undo`) until user
  validation, clean CI, and target receiver evidence are complete.
- Upstream base merged: `27065dcdd952a264face3210cfa4e37c8ffbb895`
- Main repair/review merge: `4c246ee4dc406dcbd2f9af289220afb7b0ca5940`
- Qt autogen GIO target-scope fix: `7c95b48a65663ec3b1729c1dfef4850b831fea1e`
- Qt/GIO macro and `-Wshadow` fixes: `04e20d7dc5789f3a6cc184f1afc24a5186a0a735`
- Test warning/incomplete-type fix: `d2025e08d`
- Descriptor-identity/CodeQL fix: `bdc4f85c0`
- WebSocket JPEG delivery CI timing/caps fix: `717f083c5`
- WebSocket JPEG delivery stabilization fix: `27e6f4a12`
- VideoSettings test fixture lifetime fix: `b2f6405a4`
- WebSocket JPEG source-thread delivery test fix: `d97e3f84e`
- WebSocket JPEG appsrc-pad delivery observation fix: `b98848b2c`
- Feature delta from upstream: 33 intended files; no unrelated merge
  resolutions or force-push.

## Files Changed And Evidence Paths

PixEagle-side files touched in this slice and follow-up reporting:

- `configs/config_default.yaml`
- `configs/config_schema.yaml`
- `scripts/setup/apply-setup-profile.py`
- `src/classes/api_auth_runtime.py`
- `src/classes/api_security_policy.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_paths.py`
- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/test_setup_profiles.py`
- `tests/unit/core_app/test_api_auth_runtime.py`
- `tests/test_api_route_inventory.py`
- `tests/test_docs_infrastructure_consistency.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/setup/setup-profiles.md`
- `docs/video/04-streaming/qgc-http-websocket-source-plan.md`
- `docs/video/04-streaming/remote-media-security.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-24-phase-4-qgc-authenticated-direct-media.md`
- `docs/reporting/agent-ops/codex-modernization/audits/2026-06-25-setup-bootstrap-clean-walkthrough-preflight.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

QGC-side branch and evidence:

- Repository: `/home/alireza/qgroundcontrol-pxe0070`
- PR: <https://github.com/mavlink/qgroundcontrol/pull/13594>
- Branch: `feature/http-websocket-video-streaming`
- Latest pushed head at this report point: `b98848b2c`
- Latest monitored GitHub run: `28184014057`, successful on 2026-06-25 UTC
- PR rollup checked on 2026-06-26 UTC: draft/open, all visible build/test
  checks successful, docs deploy jobs skipped, CodeQL/grype annotations neutral

Offline copies for maintainer review:

- `/home/alireza/PIXEAGLE_PXE0070_QGC_DIRECT_MEDIA_HANDOFF.md`
- `/home/alireza/PIXEAGLE_CURRENT_PHASE_SLICE_MAP.md`
- `/home/alireza/PIXEAGLE_CURRENT_ISSUE_REGISTER.md`
- `/home/alireza/PIXEAGLE_SETUP_BOOTSTRAP_CLEAN_WALKTHROUGH_PREFLIGHT.md`

## Validation

### PixEagle

- Focused auth/setup gate: 164 passed.
- Focused setup/security/docs/API gate: 244 passed.
- Phase 0 on the final implementation before reporting:
  - schema current: 41 sections and 549 parameters;
  - API/MCP candidate inventory current;
  - 372 passed with the existing Starlette/httpx `TestClient` deprecation
    warning.
- Full non-SITL suite:
  - 2340 passed;
  - 40 dlib-dependent skips;
  - 1 explicit deselection;
  - the same existing Starlette/httpx warning.
- Python compile, shell syntax, schema, generated inventory, and whitespace
  checks passed.

### QGroundControl

- 55 settings-generator/workflow Python tests passed locally.
- All 14 QML settings files regenerated successfully and settings JSON parsed.
- Feature-local formatting and whitespace checks passed.
- Source verification against GStreamer 1.28.1 confirmed `matroskamux` and
  `qtmux` accept JPEG while `mp4mux` does not.
- GitHub PR matrix for QGC head `bdc4f85c0` was mixed:
  - passed: PR title/files/size checks, check-links, docs, Doxygen docs,
    pre-commit, CodeQL actions/C-C++/Java-Kotlin/Python, custom plugin build,
    Linux release x64 and arm64, macOS release, iOS release, Android linux/mac/
    windows/linux-emulator, Docker Linux/Linux-22.04/Linux-aarch64/Android,
    grype, and Windows arm64/arm64-cross release builds;
  - failed: `Windows / Build win64_msvc2022_64 Release` during Build Setup
    and `Linux / Test + Coverage linux_gcc_64 Debug` during unit and
    integration test steps with exit code 8;
  - `gh run view` exposed the failed job/step boundaries in this session but
    did not return failed-step log bodies, so root cause is still unresolved.
- 2026-06-25 follow-up:
  - root cause triage found the Windows x64 failure happened before build while
    `aqtinstall` unpacked Qt (`Bad7zFile: lib/Qt6PositioningQuick.lib`), which
    is dependency/cache infrastructure until reproduced otherwise;
  - root cause triage found the Linux failure was in the QGC-added
    `GStreamerTest::_testWebSocketJpegDelivery()` sample wait;
  - pushed QGC commit `717f083c5` to add explicit `image/jpeg` caps to the test
    `appsrc` pipeline and replace fixed 3000 ms waits with QGC
    `TestTimeout::mediumMs()`;
  - the new head `717f083c5` cleared the prior Windows x64 Release failure, but
    Linux `Test + Coverage linux_gcc_64 Debug` still failed at the same
    WebSocket JPEG sample assertion;
  - pushed QGC commit `27e6f4a12` to align the test `appsrc` settings with the
    production source, wait for a usable GStreamer pipeline state, explicitly
    flush/wait for WebSocket bytes, and use a bounded appsink pull timeout;
  - the new head `27e6f4a12` no longer reported the WebSocket JPEG delivery
    test as the failing test, but Linux `Test + Coverage linux_gcc_64 Debug`
    still failed because `VideoSettingsTest::_testAuthenticatedTransportPolicy()`
    segfaulted during test fixture teardown after the `VideoSettings` owner had
    been destroyed;
  - pushed QGC commit `b2f6405a4` to keep `VideoSettings` alive until after
    `SettingsFixture` restores saved `Fact` values in the VideoSettings tests;
  - the new head `b2f6405a4` proved the `VideoSettingsTest` fixture-lifetime
    fix in CI (`100% tests passed, 0 tests failed out of 156` for that phase),
    but Linux `Test + Coverage linux_gcc_64 Debug` still failed in the
    integration `GStreamerTest::_testWebSocketJpegDelivery()` appsink sample
    assertion;
  - pushed QGC commit `d97e3f84e` to run the WebSocket JPEG delivery test on a
    dedicated source thread like production and add a source-side
    `jpegFramePushed` signal emitted only after `gst_app_src_push_buffer`
    succeeds;
  - the new head `d97e3f84e` still failed only in Linux integration
    `GStreamerTest::_testWebSocketJpegDelivery()` at the downstream appsink
    sample assertion; all visible platform builds/checks outside that Linux
    coverage job were green or neutral;
  - pushed QGC commit `b98848b2c` to remove the temporary production
    `jpegFramePushed` signal and assert WebSocket JPEG delivery by observing
    the exact JPEG bytes on the `appsrc` source pad instead of relying on the
    GitHub runner's appsink sample queue;
  - PR #13594 stayed draft and the new CI matrix for head `b98848b2c` was
    queued/in progress at the first report time;
  - on 2026-06-26 resume, PR #13594 was still draft/open and the visible PR
    rollup for head `b98848b2c` was green: Linux run `28184014057` completed
    `Release linux_gcc_64`, `Release linux_gcc_arm64`, and
    `Test + Coverage linux_gcc_64 Debug` successfully; Windows x64/arm64,
    macOS, iOS, Android, Docker, docs, Doxygen, pre-commit, and CodeQL checks
    visible in the rollup were successful, with docs deploy skipped and
    CodeQL/grype annotations neutral.

## Independent Review

- QGC/Qt/GStreamer review found global plugin over-requirement, unsupported MP4
  recording, insufficient thread tests, and later CMake/compile-policy defects.
  All proven defects were fixed and regressed.
- Setup review found boolean rotation ambiguity, plaintext backup risk, and
  incomplete rollback/runtime boundaries. All were fixed.
- Security review found credential leakage through GStreamer diagnostics/DOT,
  an invalid HTTP custom-CA property, weak PixEagle auth-file loading, raw bus
  errors, and QGC credential-file TOCTOU. All were fixed.
- CodeQL then identified that wrapping the validated QGC descriptor in `QFile`
  obscured descriptor identity. QGC now performs the bounded read directly on
  the `fstat`-validated descriptor.
- Maintainer review found one raw pipeline URI log and ambiguous Basic usernames.
  Both were fixed; Basic usernames now reject colon, NUL, CR, and LF.
- Closure review reported no remaining proven defect in the reviewed findings.
- 2026-06-25 resume review found reporting consistency issues: PXE-0070 was
  effectively active while the issue register still said `open`, the phase map
  listed the partial checkpoint as `done/incomplete`, and the active-slice note
  still said to finish a PixEagle-side reporting commit that had already
  landed. These reporting issues were corrected without changing runtime code.
- 2026-06-25 setup/bootstrap preflight found remaining PXE-0068/PXE-0074 risks:
  macOS is advertised while init is apt-oriented, `venv` and `.venv` are mixed,
  `make` and `nc` prerequisites are missing from beginner docs, manual dashboard
  dotenv generation can copy YAML into `.env`, manual full-requirements install
  bypasses the core/AI split, setup summaries can mask skipped dashboard or
  binary work, run startup can terminate unrelated port occupants, and the
  verification guide is weaker than the final release/handoff evidence gate.
  The findings are tracked in
  `docs/reporting/agent-ops/codex-modernization/audits/2026-06-25-setup-bootstrap-clean-walkthrough-preflight.md`.

## Evidence Boundary

- The checked-in code and tests establish configuration, authorization,
  credential handling, redaction, source construction, and build-contract
  behavior only.
- This slice does not prove target QGC-to-PixEagle playback, a deployed trusted
  TLS proxy, custom-CA behavior on each target OS, external reachability, or
  operator acceptance.
- This slice now has a successful visible QGC PR rollup on head `b98848b2c`,
  including Linux release x64/arm64 and `Test + Coverage linux_gcc_64 Debug`
  run `28184014057`. PR #13594 remains draft until the user-run receiver suite
  validates the branch. The prior Windows x64 dependency failure did not
  reproduce on head `717f083c5`; the Linux WebSocket JPEG delivery failure was
  replaced by a VideoSettings test-fixture lifetime failure on `27e6f4a12`,
  patched in `b2f6405a4`, then the WebSocket delivery failure recurred in the
  integration phase and was patched again in `d97e3f84e` and `b98848b2c`.
- No service installation, reverse-proxy/firewall mutation, camera/tracker/
  follower run, Docker/PX4/SITL/HIL, field test, or real-aircraft action was
  performed or claimed.
- PXE-0070 therefore remains in progress until target playback evidence covers
  strict TLS/custom CA, positive and negative auth/Origin cases, and MKV/MOV
  recording.

## Next Gate

1. Keep PR #13594 in draft while the branch is not user-tested end to end.
2. Install a CI-built QGC artifact on selected target GCS platforms.
3. Deploy the documented external HTTPS/WSS proxy on a non-aircraft test host.
4. Exercise anonymous generic sources and authenticated PixEagle sources,
   including wrong/missing token, wrong/missing Origin, TLS failure, custom CA,
   URL/log redaction, reconnect, bounded WebSocket payload, and MKV/MOV record.
5. Capture exact versions, configs, logs, and sanitized playback artifacts.
6. Close PXE-0070 only after operator review accepts that evidence.
