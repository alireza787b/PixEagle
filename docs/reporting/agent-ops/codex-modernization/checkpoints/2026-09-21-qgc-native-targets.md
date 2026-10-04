# PXE-0176: Native QGC integration — guarded target operations

Date: 2026-09-21. Slice: 3. Branch: `feature/qgc-native-integration`.
Base: `989d9662173b364de03b307f4208e9d0ca96451f` plus local changes recorded in
`reports/qgc-slice3/source-manifest.json`. Slice-2 reports and prepared snapshots
remain immutable history; this checkpoint does not rewrite their evidence.

Status: **backend technical gate passed**. Paired QGC UI qualification and the
user's hands-on tracker review are recorded separately by the QGC owner. No
human feedback, deployed service, physical camera, aircraft, SITL, or release
qualification is claimed by these backend results.

## Behavior

The existing typed actions accept optional guarded `native_context`; a new
authenticated `GET /api/v1/integration/target-state` returns authoritative target
revision, tracker/mode, availability and a complete guard. Native point/rectangle
selection uses exact retained original analysis pixels. Smart uses candidates
from that same frame, tentatively, until a current detector observation confirms
the target. The WS JPEG metadata adds a separate `selection_geometry` sibling;
strict provenance v1 and its non-aircraft `geometry_verified:false` remain intact.

The 1500-ms capture-age limit is rechecked after pixel preparation and durable
audit. Retention is bounded by time, 90 publications and 128 MiB of retained
analysis/encoded pixel arrays. Eviction, unknown geometry, source replacement,
changed target revision and stale presentation fail explicitly without falling
back to latest pixels. Backend owner-loop/lifecycle/model barriers serialize
native and dashboard target changes. Synchronous commit also excludes telemetry
observer changes and source retirement. External camera handshakes hold no
synchronous lock across awaits; final LOC transmission rechecks under a short
source transaction using retained orientation.

Native Cancel changes tracking only and requires no fresh video. Every native
target mutation rejects active following. Companion-only target operations
require both backend aircraft connections disconnected; vehicle-bound requests
require verified identity and captured generations. Existing authorized
dashboard Stop/Abort retains its prior behavior. Idempotence is actor-scoped and
bound to the request body, with authenticated actor audit. No exclusive lease,
new flight command, native gimbal movement, or saved tracker preference is added.

See the exact request/response and error contract in
[native target operations](../../../../apis/native-target-operations.md).

## Files and validation

Core changes: `api_v1_native_targets.py`, typed contracts/actions/read routes,
route/security inventory, `FramePublisher`, `AppController`, `SmartTracker`, and
the existing gimbal final-send guard. Model replacement and tracker restart use
the same owner loop and invalidate the shared revision. Supporting changes cover
candidate inventory, tests, API documentation and isolated replay preparation.
No dashboard source files changed.

Evidence directory: `reports/qgc-slice3/`.

- Combined gate before the later catalog-alias correction:
  route/config/security/authentication/action/tracker/model/
  streaming/video/mocked connection-lifecycle selection: **1224 passed**,
  four warnings, in `final-backend.log` and `final-backend.xml`.
- Native target tests before that correction: **26 passed**, including original pixels after newer
  publication, metadata forgery, cache eviction/expiry, delayed audit,
  source-retirement concurrency, two authenticated actors, changed-body replay,
  stale shared revision, no-aircraft gating, tracking-only Cancel and retained
  Smart candidates. Included in the combined selection; `target-final.log/xml`
  records the earlier 25-case focused result; the terminal-loss regression was
  added afterward and passed with the 235-case lifecycle/Smart selection in
  `loss-status.log/xml`, then the final combined gate.
- Source/camera/replay focused gate before the final delayed-audit case:
  **108 passed**, `source-race-v2.log/xml`. Camera tests prove final-send guard
  placement, source transaction ownership and legacy mode generation changes;
  they are mocked, not physical-camera evidence.
- Schema: **43 sections / 606 parameters**, no drift, `final-schema.log`.
- Pinned `flake8==7.3.0` CI fatal selection `E9,F63,F7,F82`, candidate inventory,
  byte compilation and `git diff --check`: passed. Package versions and exact
  commands are recorded with the manifest.
- The later demo-tool-only addition supports bounded recorded-asset selection;
  **11 replay-preparation tests passed**, including two additional clean-asset
  cases, in `clean-demo-preparation.log/xml`. These overlap the nine preparation
  cases in the earlier 1221-case combined run; all 11 are included in the final
  1224-case run and are not additional unique backend cases.

The final paired menu review found a catalog alias defect: schema rows still
advertised Gimbal and optional dependencies as available while compatibility
rows correctly denied external selection. The scoped correction resolves all
rows by factory identity, emits the same canonical request key for duplicate
rows, and checks installed OpenCV APIs, dlib and verified model artifacts without
creating trackers. **51 focused tests passed** (32 native target, 11 preparation,
8 legacy tracker), plus **59 route/candidate tests**, fatal lint and static
checks (`catalog-*` artifacts). Six new regression cases cover aliases, missing
optional prerequisites and degraded schema-manager fallback. The earlier
1224-case suite was not repeated after this catalog-only correction; these
focused results qualify its final source. `clean-demo-v4-catalog-proof.json`
records real snapshot prerequisite results, not a running tracker or HTTP claim.

Development failures are retained: the first broad run had 1008 passes and two
expected candidate-inventory count failures, subsequently corrected; the first
source-transaction test run had one test-double bytes/string mismatch, corrected
without changing the camera algorithm. Passing final evidence supersedes these
runs without deleting them.

## Real production replay evidence

The production `src/main.py`/capture/CSRT/publisher/session-auth/API path was
started in a dedicated Docker harness with `--network none`, no host ports,
devices or real services. Image:
`sha256:ecfaf2358be090447ff9948397075ce76cefff3a152fbfab006a2d26495ea14b`.

`real-replay-api-proof.py` exercised seven authenticated actions on v3:
Classic point, rectangle retarget, point retarget, existing dashboard-style
tracking-stop, rejected stale native selection, a new point and native Cancel.
The legacy action advanced the shared revision; the old gesture returned 409
`target_revision_stale`. Final revision was `"6"`; tracking/following were
inactive and command/telemetry remained disconnected. See
`real-replay-v3-runtime-proof.json` and `real-replay-v3.log`. The dedicated
backend harness was stopped and removed after this proof. Its shutdown log
records graceful app/server completion without a new fatal trace.

Prepared private snapshots live under
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-3-2026-09-21/`:

- `real-replay-v1`: initial passing target proof, before source transaction fix.
- `real-replay-v2`: source transaction and retained orientation proof.
- `real-replay-v3`: production code including post-audit age recheck, before the
  later terminal-loss status improvement.
- `clean-demo-v1`: v3 production code, operator role, clean bundled
  `resources/test1.mp4` for paired UI/user review. `test4.mp4` remains the default
  and technical proof recording. The asset path and checksum are in each new
  manifest. The clean clip avoids the earlier recording's burned-in tracking
  box/OSD being mistaken for current native target state.
- `clean-demo-v2`: preserves the authoritative terminal Classic loss reason after
  recovery timeout; seven-action production proof passed again on the clean clip
  (`clean-demo-v2-runtime-proof.json`, `clean-demo-v2.log`). Explicit Cancel/new
  session clears the loss reason. This follows the paired simulated operator
  review of the earlier unexplained transition from lost to idle.
- `clean-demo-v3`: final production source identical to clean-demo-v2, with only
  the private clean-recording OSD layer disabled. AppController tracker feedback
  remains before OSD composition. Eleven preparation tests and all snapshot
  validators pass; paired QGC owns its visual tracker-overlay qualification.

An independent read-only probe of clean-demo-v3 authenticated successfully and
received fresh selectable JPEGs with OSD disabled. The exact latest-frame ACK
handshake then delivered **820 valid JPEG pairs in 43.01 seconds**, including
819 fresh and one truthfully cached capture, across two source epochs at a
recording-loop boundary. No target action was sent. See
`clean-demo-v3-readonly-probe.json` and `clean-demo-v3-ack-loop-probe.json`.
The initial diagnostic wrongly required every replay publication to be fresh;
its preserved assertion is a probe assumption, not a backend failure. Context
`video.capture_state="unknown"` is intentional: only stamped JPEG metadata
states capture freshness; a context without pixels reports `"unavailable"`.
The paired owner isolated the initial waiting display to QGC receiver startup,
with no backend change required by these observations.

The final prepared snapshot is **`clean-demo-v4`**, preserving the same operator,
clean test1 recording and OSD-off configuration while adding the catalog fix.
Its production catalog enables CSRT, KCF and SparseFlow; dlib, VitTrack,
DaSiamRPN, Smart and external-camera rows are unavailable with specific reasons.
Old snapshots and their runtime evidence remain unchanged. Paired QGC owns the
v4 server launch and menu/video interaction proof.

Each snapshot has private mode-0600 credentials and mode-0700 directory,
browser-session operator authentication, loopback API and exact Origin,
COMMAND_PREVIEW plus circuit breaker, disabled MAVLink/telemetry/gimbal/recording,
and no camera or embedded MAVSDK server startup. The configured external MAVSDK
port is occupied by its own HTTP API, preventing accidental observational
discovery of a real sidecar. Preparation does not launch anything or modify
normal accounts/configuration; old snapshots are never overwritten.

Reproduce preparation from the worktree:

```bash
PYTHONPATH=src .venv/bin/python tools/native_replay_demo.py prepare \
  --directory /absolute/new/private/demo --role operator --video test1.mp4 --port 8093
PYTHONPATH=src .venv/bin/python tools/native_replay_demo.py validate \
  --directory /absolute/new/private/demo
```

Run the snapshot only in the separately documented isolated validation/demo
harness. Credentials stay in its private `credentials.json`, never in source,
screenshots, command lines or published evidence. QGC owns paired UI screenshots,
raw simulated operator feedback, and actual user feedback collection.

## Remaining boundaries

The Core replay deliberately reports local Smart unavailable: Full AI runtime
and a compatible trusted model are prerequisites for real detector inference.
External camera selection requires its configured supported provider and
matching full-frame RTSP source; replay reports it unavailable. Smart and camera
guards have mocked tests, not inference-performance or hardware qualification.
An independently transformed camera-internal image, physical mounting and
target retention remain unqualified.

No dashboard source changed from the exact pinned base. The prior baseline
records 471 local dashboard test passes and build success, four existing
dashboard lint failures, exact-base CI lint failure/build skip, and the existing
backend test-hygiene failure. This focused gate is not a green full-CI claim.
Windows/Android, deployment and hardware remain later release work. Following
start/stop/abort UX and bounded gimbal movement remain slice 4. User tracker
feedback is pending at the end of the paired slice-3 demo.
