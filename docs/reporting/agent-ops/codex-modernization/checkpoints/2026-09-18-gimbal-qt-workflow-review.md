# PXE-0172: Official Qt tracking workflow and manual integration checkpoint

Date: 2026-09-18. Branch: `feat/optional-gimbal-control-bench`.
Status: manual integration implemented locally; stable camera target retention
remains unqualified. Camera AI integration remains a later slice.

## Official application findings

Reviewed the operator-supplied Qt source again with a protocol specialist,
including every tracking command, mouse event and timer. This is source review;
the official Windows executable was not run. Source paths below are relative
to the extracted `VideoPlayer qt5 mingw32/VideoPlayer/` directory.

| Stage | Official Qt behavior | PixEagle manual implementation |
| --- | --- | --- |
| Enable | `mainwindow.cpp:558`: one `TRC02`; local tracking flag immediately enabled. | Observe disabled, send `TRC02`, observe ready before selection. |
| Left click | `mainwindow.cpp:591`, `mainwindow.h:190`: one LOC with a 60×60 virtual-pixel box, wire size 62×111, descriptor bytes `00 09`. | One LOC with a 64×64 box, wire size 67×119, descriptor `00 00`; deliberately manual selection. |
| Right drag | `mainwindow.cpp:489`: dragged box center/dimensions converted to 1920×1080 reference; descriptor `00 01`. | Drag selection is not integrated in this slice. |
| Retarget | `mainwindow.cpp:479`: another LOC directly while locally enabled. | Cancel/disable/prepare barrier before the new LOC to separate sessions. |
| Cancel | `mainwindow.cpp:558`: active → `TRC01` → ready; another Track-button action sends `TRC00` to exit. | Cancel target performs both steps and observes disabled. |
| Polling | `mainwindow.cpp:371`: TRC every 200 ms while enabled; SD-card query every 2 s. No periodic LOC or tracking motion command. | Existing provider queries TRC every 500 ms; GAC and diagnostic GIC have independent schedules. |
| Loss | `mainwindow.cpp:625`: handles states 0, 1, 2, 4 but omits temporary-loss state 3. A 10-second response timer displays an anomaly on silence. No automatic restart/reacquisition algorithm. | Displays the actual temporary-loss state; fresh active state still does not prove identity of a reacquired target. |

Qt uses aspect-preserving video scaling and subtracts the letterbox offset
(`mainwindow.cpp:88,397,448,490`). Its selection path does not rotate the image.
PixEagle additionally reverses its own configured rotation and flip. Qt's small
integer truncation differences do not explain a box initially landing correctly
and subsequently drifting across the scene.

The supplied tracking PDF says `TRC02` activates recognition and displays
detection boxes. Descriptor bit 3 enables fuzzy selection of a nearby detection:
Qt click uses 9, Qt drag uses 1, and the PDF example uses 8. Lower descriptor bits
are documented as reserved, although Qt sets bit 0. The PDF's little-endian label
also conflicts with its `00 08` wire example. Manual descriptor 0 and Qt-drag
descriptor 1 trials therefore do **not** reproduce Qt's fuzzy left click.

Qt displays general/car/person mode names from replies but contains no command
selecting those three modes. The PDF says only click-to-track mode 0 is currently
supported. A mode-0 reply does not establish that camera recognition is disabled.
Do not add speculative person/car mode buttons to PixEagle.

The PDF requests TRA health queries every 1–3 seconds; Qt sends none. Its wording
describes a fault diagnostic, not a required keepalive. Previous live queries
returned `TRA11`, documented as abnormal, even while detection/ready output
existed. No missing mandatory initialization or continuous tracking update was
found in the supplied application. There is no evidence that adding TRA polling
would cure drift.

Source SHA-256 values:

- `mainwindow.cpp`: `b36e05d2cbbde0d4591e35b04b233d2e210f9ac3db7f373999c8c6abf4e851b7`
- `mainwindow.h`: `452a3198510b9687f1c6c65880d68f8fb6cee159b626ac408e24c9b66e29d03a`
- `gimbalcontrol.cpp`: `7c0821279eae958f53294f1d73d44b808b7ed0d2337c9a39aa4962b425acf142`

## What the hardware evidence establishes

The operator confirmed that the first selected box lands correctly and then
drifts. Recorded PixEagle LOC/OFT pairs support that distinction:

| LOC center, wire units | Expected 1920×1080 pixel center | First OFT center |
| --- | --- | --- |
| (−405, −389) | (571.2, 329.94) | (571, 329) |
| (462, −251) | (1403.52, 404.46) | (1403, 404) |

This supports initial mapping for these clicks, not all video modes or stable
tracking. Blindly reversing axes or adding a coordinate offset would undermine
the correct initial placement.

After the operator confirmed normal orientation and a steady base, standalone
sessions `20260918T060352Z-point` (descriptor 0) and
`20260918T060456Z-point` (descriptor 1) used 128-pixel regions and both exhibited
active/lost transitions. The scene shifted between selections, so these are
not an exact same-target A/B experiment. Neither descriptor demonstrated a cure.

Session `20260918T060610Z-rotated-point` temporarily sent camera `ROT02` and
restored `ROT00`. Private video shows the scene becoming upright, but the
immediate ROT query reply was not captured; only the restored `ROT00` reply was
captured. Tracking still entered loss. This was not a controlled orientation
comparison and does not establish the firmware's tracker/servo coordinate
relationship. The next home session ended with tracking disabled.

Roll speed commands from the full UDP guide produced signed changes in GAC
roll during the earlier bounded probe. Integrated roll buttons now use the
same provider transport; this does not qualify angular accuracy or physical
direction labels. Buttons use minus/plus labels.

On this resume the camera was reachable and both TCP/UDP RTSP decoded at
1920×1080. The scene was a very close view of the operator's clothing/hand;
another loss experiment requires a suitable steady target. Room images and
vendor PDFs remain local in gitignored `reports/`, outside the review artifacts.

## Implemented slice

- `src/classes/gimbal_control.py`: optional provider-owned command adapter,
  inverse display transforms, fresh matching RTSP-source guard, fixed manual
  region, bounded pan/tilt/roll/zoom, home, cancel and stop. The active-to-ready
  cancel sequence follows the Qt source. Stop can interrupt an in-flight
  handshake; cleanup is best effort, not a hardware watchdog.
- Provider/interface/types: checksum and source validation, independent query
  scheduling, GAC authoritative body angles, GIA diagnostic only, no OFT-to-angle
  interpretation, and explicit unsupported state.
- Typed `/api/v1/gimbal/control` and `/api/v1/actions/gimbal-control` contracts,
  existing confirmation/idempotency/dry-run/audit/security rules, and generated
  route inventory. Manual changes are blocked while following, except movement
  Stop. Stop does not cancel an active tracked target; use Cancel target.
- Dashboard: capability-gated responsive controls, click/retarget handling using
  existing letterbox geometry, actual camera-state labels, roll buttons and
  Gimbal mode label. Classic/Smart interfaces remain the default.
- `GimbalTracker.CONTROL_ENABLED` defaults to false. Schema and
  [operator instructions](../../../../trackers/02-reference/gimbal-tracker.md)
  describe enabling it and its limits. No Qt runtime dependency.

The isolated local bench runtime uses command preview, the follower circuit
breaker and MAVLink disabled. No aircraft action, SITL or HIL was exercised.

## Validation on resume

- `PYTHONPATH=src .venv/bin/pytest -q tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_parameters_reload.py tests/unit/core_app/test_api_v1_gimbal_control.py tests/unit/trackers/test_gimbal_control.py tests/unit/trackers/test_gimbal_interface_protocol.py tests/unit/trackers/test_gimbal_interface_status_freshness.py tests/unit/trackers/test_gimbal_provider.py`: **178 passed**; one existing Starlette deprecation warning.
- `cd dashboard && CI=true npm test -- --watchAll=false --runInBand`:
  **61 suites, 426 tests passed**.
- `cd dashboard && npm run build`: passed.
- `bash scripts/check_schema.sh`: passed; intentional generated schema current.
- `git diff --check`: passed.

Local logs: `/tmp/gimbal-resume-{backend,frontend,build,schema}.log`; copies are
preserved in the packaged `manual-integration/` evidence.
Persistent camera evidence: `reports/gimbal-bench/` and
`reports/gimbal-manual-integration/` (wire packets, action results, isolated
configuration and runtime/probe scripts). Packaged historical sessions are in
[the evidence directory](../evidence/2026-09-17-gimbal-control-bench/README.md).

## Next bounded experiment and manufacturer questions

The exact Qt point format was exercised in session
`20260918T185503Z-qt-point`: wire center (0,0), size (62,111), descriptor
`00 09`; approximately 200 ms TRC polling plus GAC diagnostic queries.
States were disabled → ready → active → lost → ready → disabled. The first
active reply was at elapsed 2.676 s, first lost at 5.285 s (about 2.61 seconds
apart). First OFT center was (960.5,540.5), matching image center. The private
video shows nearby shirt fabric, followed by a large change of view. GAC yaw
spanned 26.54–81.12°, pitch −43.52–−3.01°. This demonstrates acceptance and loss,
not a controlled retention comparison or a diagnosed motor-direction fault.
No nearby AI candidate was verified. It does not justify changing manual
selection to fuzzy selection. The Qt-equivalent click did not demonstrate a cure.

The actual PixEagle browser path was also exercised twice: select, retarget,
then Cancel. Both LOC actions were accepted; the first reached active then lost,
the second was observed active over the short approximately one-second sample.
Cancel and final cleanup both returned disabled. These are command/state checks,
not retention qualification. Integrated API roll + then − produced GAC roll
−1.18° → −0.21° → −1.07°; actual base motion was not independently measured.
Operator-requested left pan moved reported yaw from +7.91° to −30.84° in bounded
pulses. Each sequence ended with movement stop.

The browser run exposed an inconsistent top status chip: generic tracker
monitoring could say Active while the camera panel reported Disabled. The top
chip now uses actual camera state only when the optional integration is enabled;
disconnection is explicit. Focused status/panel tests: **27 passed**, production
build passed again. Full 426-test run above preceded this final narrow correction.

Remaining useful experiment: repeat on a rigid, correctly configured mounting
base with a distinct stationary target at working distance, ideally comparing
the official executable and PixEagle on the same scene. The source alone cannot
explain the onboard visual algorithm's loss reason.

Correct initial placement still loses the target in these scenes. Send the manufacturer
these narrow questions with firmware `1.6.26.R.D` and the recorded byte examples:

1. For this firmware, what do descriptor bytes `00 00`, `00 01`, `00 08`, and
   `00 09` mean? Is bit 0 required, and what happens when fuzzy click finds no
   nearby detection?
2. `TRA11` is documented as a tracker fault but occurs alongside ready/detection
   output. What does it mean on this firmware, and which diagnostic/version
   query identifies the tracking processor and its failure reason?
3. What mounting/image-orientation configuration is required? Does `ROT02`
   rotate only video, or also the LOC/OFT and internal motor-control coordinates?
   Is the supplied Qt application/protocol version matched to this camera?

Target retention remains an open acceptance gate. Do not hide loss, claim
reacquisition of the original target from TRC02 alone, or add an automatic retry
loop to mask the unresolved camera behavior.


## Operator repeat: evidence of movement away from the target

After the preceding checkpoint, the operator repeated manual selection while
passive native video and the existing application wire logger ran. Session
`20260918T190007Z-user-manual-observe` captured selection of wall switches beside
a door. The recorder sent no camera commands. Native images were saved at
960×540, approximately 5 fps; wire coordinates remain referenced to 1920×1080.
Host video-receipt and UDP-receipt timestamps have different latency and must
not be treated as camera exposure timestamps.

LOC at elapsed 25.4675 s contained center (−484,320), size (67,119), descriptor
0. First OFT arrived about 0.11 s later, center (490,702.5) pixels versus commanded
(495.36,712.8); this is an already-updating tracker box, not the earlier
within-one-pixel examples. TRC was active at 25.6956 s, lost at 27.7015 s,
briefly active again, then lost; operator cancellation ended at disabled around
29.55 s. Later active state did not establish reacquisition of the switches.

The useful distinction is visual: at 26.00 s the camera-rendered brackets still
surround the wall switches, but the switches have moved farther left and down
instead of toward the image center. The subsequent view sweeps to the floor.
A fixed template of the three switches supports the first displacement:

| Native video receipt, seconds | Switch-group center, saved 960×540 pixels | Distance from image center | Nearest GAC yaw/pitch |
| --- | --- | --- | --- |
| 25.573 | (233.5,353) | 260.1 px | (−12.83°,11.51°) |
| 26.001 | (184.5,380) | 315.3 px | (−17.13°,13.51°) |

The template score declines from 1.0 to 0.524 as motion blur increases; later
low-confidence matches are not used as position evidence. Human inspection
confirms the early switch displacement and brackets. This supports an
**image-to-motor direction/orientation mismatch hypothesis**, rather than an
initial click offset, for this repeat. It does not isolate camera firmware,
mounting configuration, image rotation, or independent base motion as the cause.
The native video is inverted while PixEagle applies a display-side 180° rotation.

The next bounded comparison is camera `ROT02` with PixEagle display rotation 0,
so the upright displayed view is preserved while changing camera-side image
orientation. Coordinate mapping must follow the actual new stream. This change
was prepared but **not performed**: coordination with the operator's active
manual test was requested, and the camera subsequently became unreachable.
Do not rotate either side during an operator selection. Restore/query the
original camera setting after an inconclusive comparison.

During this repeat the operator saved display rotation 180 in their own config
and requested backend Restart. The temporary direct bench launcher had no
restart supervisor; the backend exited with restart code 42 after a shutdown
timeout. It was relaunched with the existing isolated bench configuration;
operator configuration edits were preserved. The separate native video recorder
continued independently. A second passive session
`20260918T190227Z-user-manual-observe` records stream loss/reconnect attempts;
by 19:04:56 UTC the camera also failed ping. Camera-side rotation has not been
changed during these operator repeats.

Correlated wire/box/angle records, the template-analysis result and passive
recorder/analyzer scripts are retained with the session evidence. Room frames
remain private under `reports/gimbal-bench/`. Logging continuity has explicit
gaps: the first RTSP decoder ended at about 58 s, and a reconnecting recorder
started at 19:02:27 UTC. Runtime wire logging also stopped during backend restart.
