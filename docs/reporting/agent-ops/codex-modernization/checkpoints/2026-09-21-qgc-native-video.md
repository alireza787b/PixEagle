# PXE-0175: Native QGC integration — backend frame provenance

Date: 2026-09-21. Slice: 2, authenticated JPEG video and read-only status.
Branch: `feature/qgc-native-integration`.
Base: `989d9662173b364de03b307f4208e9d0ca96451f`, plus the local source changes
inventoried in `reports/qgc-slice2/source-manifest.json`.

Status: **backend and paired Linux read-only video technical gates passed**.
The paired QGC checkpoint records final fullscreen affordance checks; real user
feedback remains pending. This is local branch evidence, not remote full-CI,
Windows/Android release, camera, SITL or aircraft qualification.

## Result and scope

Authenticated `/ws/video_feed` frames now carry strict versioned provenance
bound to immutable published pixels: process/instance, publisher and source
epochs, lossless publication/capture IDs, exact encoded dimensions, output
variant, and separate capture/publication ages. Camera receipt timestamps are
preserved through processing, async capture, prefetched file frames and cached
frames. Source replacement/release invalidates old publication and pending
encode work; variants and encoder cache entries cannot inherit old pixels.

JSON/JPEG pairs share a send lock with pong responses. Partial or cancelled
pairs clear outstanding ACK state and retire the socket. Optional bounded
delivery tokens echo an accepted client challenge, allowing a native client
to conservatively bound transit age without synchronized clocks. Legacy
clients and integer ACK IDs remain compatible. Authentication, Origin/Host,
query-credential rejection, logout and expiry gates remain active.

The existing context advertises the media capability only when enabled and
also advertises the existing read-only tracker-runtime route. Geometry remains
unverified; polled tracker state cannot be joined to a displayed frame for
selection or following. No new flight, target, tracker or media-control route
was added. The contract is documented in
[native frame provenance](../../../../apis/native-frame-provenance.md).

Changed operational files: `frame_publisher.py`, `video_handler.py`,
`app_controller.py`, `fastapi_handler.py`, `api_legacy_media_routes.py`,
`api_v1_contracts.py`, `api_v1_integration.py`, and shared `runtime_identity.py`.
Tests cover provenance and existing streaming/lifecycle behavior. The fixture,
domain documentation and generated API-candidate provenance are also updated.
Existing slice-1 changes remain in the same uncommitted integration worktree;
the manifest records the full local source state rather than claiming a new
commit or remote CI run.

## No-aircraft demo contract

The camera-free fixture uses production authentication, publisher, encoder,
WebSocket, context and status routes around synthetic observations. Its
`--no-aircraft` mode emits video labelled `NO AIRCRAFT`, with command/telemetry
disconnected and identity unknown, even after observational discovery. It
rejects mixed synthetic aircraft options. Authenticated video/status continue
without creating any AppController, camera, tracker, MAVSDK, flight runtime,
service or persistent user account.

```bash
.venv/bin/python tools/native_integration_fixture.py \
  --port 8093 --instance-id fixture-no-aircraft --no-aircraft \
  --media-control-file /tmp/pixeagle-fixture-no-aircraft.json
```

The test-only login is `operator` / `fixture-only`. Stop the fixture after
validation. File controls exercise live/freeze/drop, source/stream resets,
resolution and raw/OSD changes. Visible frame numbers and a JPEG-safe 64-bit
pixel pattern allow exact pixel-to-metadata comparison. QGC may expose this as
a companion preview; it must not label it a verified aircraft video feed.

## Real PixEagle startup without PX4 — inspected, not launched

The real application also separates capture from aircraft connection.
`AppController.__init__` constructs the PX4 interface in a disconnected state;
installed MAVSDK 3.15.3 `System.__init__` stores connection parameters but does
not start its server or connect. Those actions happen in explicit `connect()`.
`FlowController` starts its idle flight-owner event loop and HTTP API before
opening the configured input, then continues degraded when input is unavailable.
GET context, read-only tracker status and media do not call connection discovery.
This supports video without PX4; it is source inspection, not a recorded real
application startup or camera test.

The current worktree has Python 3.12.3, OpenCV 4.11 with CSRT, the bundled
`resources/test4.mp4`, tmux and the baseline dashboard build. No local
`configs/config.yaml` exists. The file and package checks are recorded in
`real-runtime-prerequisites.json`; the video was not opened. A first real
pipeline demo should use that recorded file before any hardware camera.

Before launch, prepare and inspect an isolated runtime configuration with
`VIDEO_FILE`, `COMMAND_PREVIEW`, active `FOLLOWER_CIRCUIT_BREAKER`,
`MAVLINK_ENABLED:false`, disabled GStreamer output and external gimbal control,
loopback API binding and a real `browser_session` viewer account. The native
client requires actual authentication. In particular, `make demo` applies
`beginner_lab` and resets auth to `local_compat`; it cannot be the last setup
step for this native demo. The existing loopback `demo_lan_browser` profile can
apply browser auth after the replay profile. A normal launcher must explicitly
skip MAVLink2REST and MAVSDK (`-m -k`); `--no-dashboard` also skips the browser
frontend when only QGC is needed. Keep original main-checkout settings and
credentials isolated. Then collect real startup, decoded video, session/status
and clean-stop logs before asking an operator to assess the real preview.
No such configuration, account, service or runtime was created during that audit.

### Prepared real Core replay

The operator subsequently chose bundled recorded video for the first real
PixEagle demo. `tools/native_replay_demo.py` now provides separate `prepare`,
`validate` and `run` actions. Preparation copies the actual Core source,
configuration definitions, `test4.mp4` and fonts into a new private directory;
the real runtime therefore resolves its own config/data paths without touching
either checkout. It creates a generated test-only viewer login, saves the
handoff in a mode-0600 `credentials.json`, and records the file hashes and base
revision in `demo-manifest.json`. It does not print the password.

The corrected prepared directory is
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-2-2026-09-21/real-replay-v2`.
It has passed snapshot/permission/profile checks and full configuration-schema
validation. `run` validates the snapshot again and execs the copied production
`src/main.py`, using the current isolated worktree Python environment. It runs
real Core capture, tracker construction, OSD, publisher, auth and API paths;
the synthetic fixture is not involved. Source, definitions and config edits
after preparation invalidate the snapshot check.

```bash
# For a new snapshot, choose a new empty destination:
.venv/bin/python tools/native_replay_demo.py prepare \
  --directory /absolute/private/new-demo-directory --port 8093
.venv/bin/python tools/native_replay_demo.py validate \
  --directory /absolute/private/new-demo-directory
# Run only inside the selected isolated validation harness:
.venv/bin/python tools/native_replay_demo.py run \
  --directory /absolute/private/new-demo-directory
```

The prepared profile binds only `127.0.0.1:8093`, allows that exact Origin and
the loopback hostname `127.0.0.1`,
and disables MAVLink polling, UDP telemetry, gimbal activity, recording,
GStreamer output and the OpenCV window. It uses command-preview with the
circuit breaker active. Its external-only MAVSDK address points to its own
HTTP port, so an accidental observational discovery cannot connect to a real
MAVSDK sidecar or spawn an embedded one. The idle flight-loop owner remains part
of the actual Core app. Use a network-isolated harness for validation.

The runner does not manage services or launch a dashboard. Initial preparation
and tests did not start this real application or open its video. Subsequent
authorized validation did run the actual Core app in the existing
`pixeagle-slice1-ui` container with Docker network mode `none`; it was retained
for the paired QGC owner's GUI acceptance and later stopped.

The first launch failed before serving HTTP: `local_only` exposure policy
rejects `API_ALLOWED_HOSTS: [127.0.0.1:8093]`, although the field schema accepted
it. That original `real-replay` snapshot and `real-pixeagle.log` are preserved.
The runner now uses the hostname without a port and calls the production
exposure-policy resolver during both preparation and validation. A regression
test covers the stricter runtime rule; no production policy was loosened.

The corrected v2 snapshot started actual FastAPI, OpenCV file capture, CSRT
construction, OSD, publisher and JPEG encoding. An authenticated probe decoded
two distinct 640×480 JPEGs with different capture IDs, matching runtime/instance
provenance and delivery challenge. Anonymous context returned 401; signed-in
context and tracker status returned 200, with command and telemetry disconnected,
association unverified and following inactive. The probe logged out its own
session. Startup logs subsequently recorded a complete file loop and continued
processing with MAVLink disabled/PX4 disconnected. No real camera, aircraft,
target action or flight path was exercised.

Start command used after preparation:

```bash
docker exec -d -w /home/alireza/PixEagle-qgc-integration pixeagle-slice1-ui \
  bash -c 'exec .venv/bin/python tools/native_replay_demo.py run \
  --directory /home/alireza/.cache/pixeagle-qgc-baseline/slice-2-2026-09-21/real-replay-v2 \
  > /home/alireza/.cache/pixeagle-qgc-baseline/slice-2-2026-09-21/real-replay-ui/ui/real-pixeagle-v2.log 2>&1'
```

`reports/qgc-slice2/real-replay-v2-runtime-proof.json` records the context/status
and decoded frame checks; `real-replay-first-frame.jpg` and its metadata retain
a sample. Logs under the paired cache's `real-replay-ui/ui/` preserve the failed
first launch and successful second launch. Backend delivery alone does not
prove native rendering or usability. Subsequent paired evidence is recorded
below; a real operator walkthrough remains pending.

## Validation and reproduction

Evidence: `/home/alireza/PixEagle-qgc-integration/reports/qgc-slice2/`.
Python 3.12.3, isolated worktree `.venv`; installed packages are captured in
`packages.txt`. Run from the backend worktree:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/streaming \
  tests/unit/video/test_video_handler.py \
  tests/unit/video/test_video_capture_creation.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/unit/core_app/test_api_v1_integration.py \
  tests/unit/core_app/test_api_auth_runtime.py \
  tests/unit/core_app/test_api_exposure_policy.py \
  tests/unit/core_app/test_api_security_audit.py \
  tests/unit/core_app/test_api_legacy_media_routes.py \
  tests/unit/core_app/test_api_v1_streams.py \
  tests/unit/drone_interface/test_px4_interface_manager.py \
  tests/unit/drone_interface/test_mavlink_data_manager.py \
  tests/test_api_route_inventory.py tests/test_api_tool_candidates.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/test_docs_infrastructure_consistency.py \
  -ra --tb=short --strict-config -o addopts= \
  --junitxml=reports/qgc-slice2/final-backend.xml
PYTHON=.venv/bin/python bash scripts/check_schema.sh
.venv/bin/python tools/generate_api_tool_candidates.py --check
```

- **948 passed**, zero failures/errors/skips, four existing Starlette
  deprecation warnings; `final-backend.log` and `final-backend.xml`.
- Provenance-focused development gate: **36 passed**, including authenticated
  no-aircraft live video and unchanged disconnected context before/after
  discovery; `no-aircraft-development.log/xml`. These tests are included in
  the 948 total, not additional distinct coverage.
- Existing no-PX4 startup/preview contracts: **26 passed** in the FlowController
  lifecycle/freshness, command-preview and two replay-profile tests;
  `no-px4-existing-contracts.log/xml`. No real app or aircraft was started.
- Real replay preparation v2: **8 passed**, including exact Core/video copy,
  private account/permissions, full schema validation, inhibited routing,
  modified-source rejection, preserving existing directories and the runtime
  exposure-policy regression; `real-replay-preparation-v2.log/xml`. The earlier
  seven-test preparation gate did not catch the runtime policy failure and is
  preserved as development evidence.
- Schema: **43 sections / 606 parameters**, no drift; `final-schema.log`.
- API candidate check, touched-module byte compilation/import coverage,
  `git diff --check`: passed; `final-static.log`.
- CI-equivalent fatal Python lint selection `E9,F63,F7,F82`: passed with
  `flake8==7.3.0`, invoked using `uv tool run --from flake8==7.3.0 flake8` on
  touched slice-2 modules and test/fixture; `final-python-lint.log`.
  The worktree environment did not include flake8 initially; the separate
  pinned tool environment avoids changing runtime requirements.

The earlier interrupted run's 793 regression passes and 532 lifecycle passes
remain historical development evidence, superseded by the final combined
selection. The exact final artifact/source hashes are in
`source-manifest.json`; reports are local evidence, not checked-in binaries.

## Paired video gate and shutdown observation

The paired `qgroundcontrol-pixeagle/custom-pixeagle/SLICE-2.md` now records all
four stock/custom Debug/Release builds passing, custom Unit/Integration
**407/407**, stock **405/405**, standard `Flaky|Network` exclusions, and retained
StockUI coverage. The native composed transport-to-presentation tests passed
**40 cases with software rendering and 40 with threaded OpenGL**. The real Core
recorded replay reached QGC Release without PX4; no-aircraft fullscreen, source
restoration and vehicle/session isolation were exercised. Raw simulated operator
feedback and its disposition are retained there. Its final fullscreen button
affordance checks remain documented by the paired owner. An intermediate
ObjectListModelBaseTest shutdown timeout is preserved with the later passing
focused/repeated/full runs; it was not diagnosed or relabelled as a baseline bug.

The host desktop demo later exited, and its launcher stopped its own backend.
`desktop-completed-pixeagle.log` records application shutdown, video release,
FastAPI shutdown and server-thread completion, followed by:

```text
Exception ignored in: <function System.__del__ ...>
ImportError: sys.meta_path is None, Python is likely shutting down
```

This is classified as a **reproduced external MAVSDK interpreter-teardown
warning**, not an introduced native-video failure or a clean-log pass. Installed
MAVSDK is 3.15.3, matching the slice-0 package record. Its `system.py` matches
the installed distribution RECORD hash. `System.__del__` calls
`_stop_mavsdk_server`, which imports `subprocess` even for an unconnected object
with no child server. A dependency-only subprocess retaining an unconnected
`System` in `builtins` until final interpreter teardown produces the identical
warning and exits zero; ordinary earlier cleanup produces no warning and also
exits zero. Neither probe imports PixEagle or calls `connect()`.

SDK construction and `PX4InterfaceManager.stop()` are unchanged from the pinned
PixEagle base. The full untouched baseline app was not relaunched, so the
dependency-only reproduction does not claim an identical baseline-app shutdown
trace. No production or dependency patch was made. This warning does not
explain the separate QGC exit code; the paired owner retains that desktop log
and its geoclue/map-network qualifiers.

Evidence: `reports/qgc-slice2/mavsdk-shutdown-only-repro.log` contains exact probe
scripts/output; `mavsdk-shutdown-classification.json` records dependency hashes,
baseline comparisons and the bounded process audit. The prepared v2 snapshot
still passes hash/profile/runtime-policy validation. At inspection, host port
8093 had no listener and completed desktop backend PID 88857 was absent. The
only demo Core process was in the intentionally active `pixeagle-slice2-click`
container for final GUI checks; it was not a residual host desktop server and
was not stopped by this audit. Process state is evidence at inspection time,
not a promise about later operator launches.

## Remaining boundaries and next gate

No dashboard files changed relative to the exact base. Slice-0 evidence remains
the dashboard result: 471 local test passes and production build success, with
four existing lint errors; exact-base dashboard CI failed lint and skipped
build. The existing backend test-hygiene guardrail failure also remains recorded
in the [baseline checkpoint](2026-09-21-qgc-native-baseline.md). Neither is a new
slice-2 failure, and this is not a green full-CI claim.

Technical displayed-pixel provenance, freshness/queue/reconnect/TLS, stock UI,
mock/no-aircraft smoke and simulated-review gates have paired evidence. Actual
user feedback is pending. No physical display scanout, real camera, deployed
runtime, SITL, hardware, field, Windows or Android qualification is claimed here.
Target controls belong to slice 3 after the full slice-2 gate; following remains
disabled and requires the later association/geometry and safety gates.
