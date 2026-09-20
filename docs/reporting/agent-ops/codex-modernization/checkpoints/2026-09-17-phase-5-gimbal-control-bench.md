# Phase 5 Checkpoint: Optional Gimbal Control Bench Investigation

Date: 2026-09-17
Issue: PXE-0172
Branch: `feat/optional-gimbal-control-bench`
Runtime baseline: `463fbbc5acbc107d32cffc6c85cc3670923016ee`
Status: initial and PDF-guided bench passes recorded; integration and tracking qualification open

## Purpose and boundary

Establish which controls from the manufacturer's Qt sample work with the
operator's existing PixEagle-compatible gimbal before adding optional dashboard
controls. The operator authorized standalone camera tests, confirmed clearance,
and reported holding the gimbal initially, then restarting it upside down.
After failed tilt tests, the operator restarted again following a request to
return it upright; tilt subsequently responded. The exact mounting angle was
not independently measured.
No PixEagle application, PX4/MAVSDK control, aircraft test, service installation,
firmware update, factory reset, or persistent configuration command was run.

The first integration remains opt-in, with no default UI changes. Agreed scope:
point/box selection, prepare/cancel/disable tracking, pan/tilt, zoom and home.
Manual target/camera changes must require stopping following first. The later
manufacturer tracking PDF confirms AI-assisted and manual selection within the
same camera tracker; include both interactions in the opt-in design. Independent
detector-mode switching, roll, automatic reacquisition policy, capture/recording
and PIP remain deferred. See the [PDF-guided follow-up](2026-09-17-gimbal-pdf-followup.md)
for the latest tests and remaining limitations.

## Evidence and reproduction

- Manufacturer archive: `VideoPlayer qt5 mingw32 (1).rar`.
- Archive SHA-256: `7d8f55a7f480760edb54df668b58a2127f83d33ea80b23e2771ef0d18503317d`.
- App sources and `Documentation.docx` inspected after extraction to
  `/tmp/pixeagle-vendor-review-n764alrk`; no vendor executable was run.
- Camera: `192.168.0.108`, UDP command port `9003`, RTSP
  `rtsp://192.168.0.108:554/stream=0`. Exact model/firmware remain unknown.
- Host route: wired interface `enp130s0`, source `192.168.0.167`.
- Probe: standalone Python 3.12.3; video decoding: PyAV 17.1.0.
- Raw evidence and private room images: `reports/gimbal-bench/` (gitignored).
- Reviewable protocol evidence: sibling evidence directory
  `../evidence/2026-09-17-gimbal-control-bench/`.

Each session records UTC and monotonic elapsed time, exact transmitted/received
bytes, local/remote ports, checksum results, and its probe source hash. The
evidence manifest identifies the exact script revision for each session.
Image hashes preserve the link to local visual evidence; room images are not
included in Git. Device RTSP dates report 1970 and must not be used as wall time.

Read-only commands used:

```bash
ip route get 192.168.0.108
ping -c 2 -W 2 192.168.0.108
.venv/bin/python /tmp/pixeagle_gimbal_bench.py queries
.venv/bin/python /tmp/pixeagle_gimbal_bench.py routing
.venv/bin/python /tmp/pixeagle_gimbal_bench.py describe
.venv/bin/python /tmp/pixeagle_gimbal_bench.py video
```

Control sessions used explicit `--execute-standalone-bench`, required a disabled
tracking baseline, used short pulses and repeated stop commands, and cleaned up
with movement stop, zoom stop and tracking disable. A separate thread provided
a best-effort eight-second stop deadline. This does **not** prove a hardware
watchdog or stopping after host/process/network failure. Probe scripts are
investigation artifacts, not production control services.

## Bench results

| Capability | Observation | Evidence limit |
| --- | --- | --- |
| Network | Two ping replies, approximately 0.8 ms each | Connectivity only |
| Video | H.264, decoded 1920×1080 frames over TCP and UDP; initial stream metadata 30 fps | Short capture, not sustained latency/reliability acceptance |
| Status | `TRC00` disabled; prepare produced `TRC01`; cancel stayed ready; disable returned `TRC00` | Query observations, not correlated command ACKs |
| Point selection | Center-point command reached `TRC02`; cancel returned `TRC01`; disable returned `TRC00` | Short stationary indoor scene; not moving-target accuracy proof |
| Box selection | Center and normalized `(0.4, 0.4)` boxes reached `TRC02`, then cancelled/disabled successfully | Edge limits, arbitrary resolutions and transformed video remain untested |
| Tracking overlay | White target-corner markers visible directly in decoded RTSP frames | Camera draws them; no Qt/PixEagle overlay process was running |
| Body angles | `GAC` replies contain three signed centidegree fields accepted by existing parser | Physical frame/axis calibration unproven |
| Spatial query | `GIC` requests consistently received `GIA` replies | `GIA` frame semantics not established; current parser rejects it |
| Zoom | 150 ms zoom-in/out pulses changed camera-rendered OSD from 1.0× to 1.5× and back to 1.0× | No dedicated `ZMP` reply observed in this test |
| Pan | Brief positive/negative commands produced measurable yaw changes | Handheld/inverted setup prevents calibrated rate/sign claim |
| Home | In inverted setup only yaw responded; after restart yaw moved about −9.6° to 0.3°, pitch −5.5° to 3.4° | Response confirmed; not calibrated zero or full three-axis recentering |
| Tilt | In inverted setup ±20/500 ms and ±50/250 ms produced no material pitch change; after restart ±20/250 ms moved pitch about 4.9° → 7.0° → 4.7° | Commands work in the later setup; cause of inverted-start limitation unresolved |
| Stop | Documented stop frames transmitted repeatedly; no dedicated stop ACK seen | Network-loss stop/watchdog not tested |

During the zoom test the device also emitted checksum-valid, binary `ODZ`
frames containing ten zero payload bytes. Their meaning is unknown. Preserve
them as bytes; do not interpret them as zoom confirmation or tracking boxes.

### Selection timeline and geometry

| Session | Selection | First sampled active status after selection TX | Cleanup |
| --- | --- | --- | --- |
| `20260917T051606Z-point` | Center; flag 9; size 62×111 | Approximately 402 ms | Ready, then disabled observed |
| `20260917T051634Z-box` | Center; flag 1; size 200×200 | Approximately 402 ms | Ready, then disabled observed |
| `20260917T051732Z-box` | Normalized (0.4, 0.4); wire center (−200, −200); size 200×200 | Approximately 401 ms | Ready, then disabled observed |

These are polling observations at roughly 400 ms intervals, not measured
acquisition latency bounds. Each initial post-selection query still returned
ready. There are no command sequence IDs or demonstrated target IDs, so delayed
or duplicate active status must not establish identity of a replacement target.

The camera may resize/snap a selected region as it tracks. The browser should
show the operator's drag transiently and reuse camera-embedded tracking markers,
not leave the original ROI displayed as if it were the current tracked box.

Live tracking also produced 21-byte binary `OFT` packets: 10-byte header,
9-byte payload, two checksum characters. Four little-endian uint16 fields
look consistent with pixel box geometry, followed by byte `0x32`; e.g.
`(952, 536, 51, 30, 50)` during center-point tracking, and
`(670, 398, 164, 117, 50)` early in off-center box tracking. This is an
**initial inference**. The subsequently supplied tracking PDF §7 confirms
top-left box geometry and tracking status, not angles. Live status bytes are
ASCII digits and shorts fit little-endian image pixels. See the PDF-guided
follow-up; stream-coordinate and timing guarantees remain unqualified.

### Reply routing

Queries from local 8080, 9004 and ephemeral ports received valid responses.
Copies consistently arrived on 9004; copies also reached 8080 or the ephemeral
client, including a previously used client port. One routing run produced
duplicate replies on 9004. This rules out an assumption of simple exclusive
request-source-port replies; exact device registration/fan-out behavior remains
unresolved. No socket used `SO_REUSEADDR` during these probes.

Reply source ports changed across sessions/restarts (`38909`, `57707`, `35496`,
`59598`).
Validate source IP and frame contents; do not require source UDP port 9003.
Use one provider-owned transport and tolerate duplicate status samples. Do not
change existing working listen-port defaults to the Qt sample's 8080 blindly.

### Demonstrated protocol bytes

All ASCII examples include their checksum and have no newline/NUL terminator.
Checksum is the sum of preceding bytes modulo 256, as two uppercase ASCII hex
characters. Binary payloads also participate in this sum.

| Intent | Full frame |
| --- | --- |
| Tracking query | `#TPPD2rTRC0048` |
| Body angle query | `#TPPG2rGAC002D` |
| Spatial angle query | `#TPPG2rGIC0035` |
| Movement stop | `#TPPG2wPTZ0065` |
| Zoom stop | `#TPPM2wZMC0057` |
| Prepare tracking | `#TPPD2wTRC024F` |
| Cancel to ready | `#TPPD2wTRC014E` |
| Disable tracking | `#TPPD2wTRC004D` |
| Zoom in / out | `#TPPM2wZMC0259` / `#TPPM2wZMC0158` |
| Home | `#TPPG2wPTZ056A` |

Pan/tilt use the sample's `U` source character, `GSY`/`GSP` and signed-byte
speed encoded as two hex digits. Tests preserve these bytes, rather than
normalizing source addresses without a specification.

The source-derived selection format is `#tpPDAwLOC`, four big-endian int16
fields (center X/Y, width/height), reserved byte zero, and selection flag
9 (point) or 1 (box), followed by ASCII checksum. Normalized centers map to
approximately −1000…+1000; width/height to 0…2000. The sample's point defaults
are a 60×60 area on a virtual 1920×1080 image, encoded as 62×111. The center-point
full frame is `237470504441774c4f4300000000003e006f00094537` in hex;
the center-box frame is `237470504441774c4f430000000000c800c800014332`.
The live tests above cover these and one off-center box, not all edge cases.

## Existing runtime defects identified offline

The socket-free replay script and JSON result are included with evidence.
No malformed packet was transmitted to hardware.

1. **Body-angle query starvation.** Running the actual query loop with mocked
   send functions and sleep produced 24 `GIC`, 6 `TRC`, and **zero `GAC`** queries
   in 30 iterations. The earlier spatial `elif` fires every non-status cycle.
2. **Actual reply rejected.** Both baseline captures total 12 accepted TRC,
   12 accepted GAC, and 12 rejected GIA packets.
3. **Checksum bypass.** Offline corruption of a disabled response to
   `#TPDP2rTRC0248` retains an invalid checksum but is accepted as active.
   A corrupted GAC checksum is also accepted.
4. **Unsupported status retention.** Qt defines status 4 as unsupported; the
   current enum/parser rejects it, allowing an earlier cached lock to remain
   until expiry. Source finding, not induced on hardware.
5. **Reference-frame mixing risk.** A single current-angle slot and body-frame
   downstream transforms mean simply accepting GIA as GIC is insufficient.
   Keep GAC authoritative for the current body-relative path. GIA remains
   diagnostic until its frame is verified and samples are segregated.
6. **OFT misinterpreted as angles.** Replaying the center-point session using
   the listener's exact UTF-8 replacement decoding caused 30 of 99 received OFT
   deliveries (including duplicates) to be accepted as angles. One produced
   `(174.11°, 20.5°, 128.0°)` from bytes consistent with pixel-like fields
   `(836, 520, 50, 38, 50)`. Unknown OFT payloads must not feed guidance or renew
   angle freshness. A checksum alone does not fix this semantic error.

Future prerequisite slice: validated byte decoding, source checking, independent
GAC/TRC scheduling, removal of speculative OFT-to-angle parsing, explicit
inactive/unsupported normalization, and regression
fixtures from these captures. Do not fold an unrelated tracker rewrite into it.

## Initial-pass final device state and validation

The last control run sent home, then movement stop, zoom stop and tracking
disable three times during cleanup. The separate final read-only session
`20260917T051804Z-queries` confirmed `TRC00` and continuing GAC/GIA responses.
All probe processes exited. No claim is made that motors were powered off;
the camera can remain stabilized while tracking is disabled.

Validation covers captured checksums, manifest/source hashes, syntax of preserved
probe scripts, and socket-free replay of the existing parser/query scheduler.
The schema check passed in the initial investigation. Phase 0 pytest execution
was attempted but unavailable because this local virtual environment has no
`pytest`. No backend/frontend runtime files were changed; dashboard build/tests
were not rerun for this documentation/evidence-only slice. Bench observations
are not software regression, hardware watchdog, SITL, HIL, or flight acceptance.

## Open questions and next slice

- Establish supported startup/mount orientations and physical axis signs;
  explain the inverted tilt limitation before promising that mounting mode.
- Extend ROI acceptance to edges, stream resizing, rotation/flip and zoom;
  moving-target accuracy, loss/reacquisition, and target replacement remain open.
- Obtain exact model/firmware, command ACK/correlation rules, target identity/replacement semantics, and reply
  fan-out behavior. The later PDF defines temporary loss as TRC03 and permanent
  loss as return to ready; temporary loss was subsequently observed.
- Obtain device-side motion/zoom watchdog behavior before claiming disconnect
  safety. Do not infer it from successful repeated stop transmission.
- Confirm ROI limits and mappings under optical/digital zoom and sensor changes.
- Obtain definitions for observed GIA and ODZ packets; qualify OFT/ODR coordinate
  and timing semantics against the newly supplied tracking PDF. Keep unverified
  telemetry diagnostic-only until their semantics are established.
- Ask for documented roll, detector-mode and reacquisition commands only for
  later scope; no speculative opcode scanning or persistent-setting writes.

After the bench checkpoint, implement offline codec/fake-provider fixtures and
the disabled-by-default control capability. Dashboard interaction follows those
contracts; flight following remains outside this bench evidence.
