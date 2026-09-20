# PXE-0172: PDF-guided detection and manual tracking bench follow-up

Date: 2026-09-17. Branch: `feat/optional-gimbal-control-bench`.
Scope: standalone camera investigation, documentation and evidence only.
No PixEagle runtime, configuration, flight control or dashboard changes.

## References and design decision

Copied the operator-supplied `Interaction Tracking Protocol(out).pdf` and
`User manual for FL-30 Camera.pdf`, extracted text and SHA-256 manifest to
`reports/gimbal-bench/vendor-reference/` (persistent local, gitignored).
The [reference review](../evidence/2026-09-17-gimbal-control-bench/vendor-protocol-findings.md)
records hashes, sections, Qt comparisons and protocol ambiguities. The vendor
PDFs and room images are not included in Git.

The tracking PDF confirms the requested two interactions: enabling tracking
starts detection; an operator can click a detected object using fuzzy selection,
or select a manual region. These are two interactions with one camera tracker,
not two new PixEagle tracking algorithms. The camera manual lists human and
vehicle detection, not arbitrary household-object classification.

Keep both interactions in the proposed default-off integration. A camera
capability should expose manual selection and AI-assisted selection separately;
they must share the existing external provider's lifecycle, transport and
confirmed tracking state. Camera detection should not instantiate PixEagle's
local SmartTracker/YOLO pipeline. Native boxes may support a minimal first UI;
decoded candidate metadata can follow after its geometry/field semantics are
qualified. Do not infer target identity or flight eligibility from a candidate.

## Documented commands tested

All frames include the sum-modulo-256 checksum encoded as two ASCII hex bytes.

| Operation | Frame / behavior |
| --- | --- |
| Enable detection metadata | `#TPPD2wFED1034` |
| Disable detection metadata | `#TPPD2wFED2035` |
| Enable detection / await selection | `#TPPD2wTRC024F` |
| Tracker fault query, UDP source P | `#TPPD2rTRA0046` |
| Observed reply | `#TPDP2rTRA1148` |
| Manual ROI | Binary LOC, descriptor bytes `00 00`, fuzzy selection off |

The descriptor's prose/table and worked example disagree about byte order.
Qt uses `00 09` for a point and `00 01` for a box; both were exercised in the
initial pass. This pass confirms a manual box with `00 00` reaches active state.
The PDF's `00 08` fuzzy-click example was implemented in a bounded probe, but
its selection precondition failed and **no fuzzy LOC was transmitted**.

## Live outcomes

| Session | Result and limitation |
| --- | --- |
| `20260917T071735Z-queries` | Reconnected camera replied; disabled tracking baseline. |
| `20260917T071854Z-ai-observe` | FED enable plus TRC prepare produced ODR detection packets and TRC01. Eight distinct captured ODR byte strings, delivered to three listening ports (24 deliveries). |
| `20260917T072022Z-ai-observe` | Ready state, but no ODR packets during this short scene. No heartbeat queries in this run. Absence does not distinguish no detections from output/firmware conditions. |
| `20260917T072135Z-ai-select` | 57 ODR deliveries. At selection time the newest candidate was about 0.619 seconds old, exceeding the probe's 0.6-second limit. Probe rejected selection and cleaned up; not a successful AI-click test. |
| `20260917T072332Z-box` | Manual chair selection at normalized center (0.7, 0.6), wire center (400, 200), size (200, 200), descriptor 0. Ready → active; repeated temporary-loss/active transitions; cancel → ready; disable → disabled. |
| `20260917T072435Z-queries` | Separate final read-only check returned only TRC00, plus angle replies; no ODR observed in this capture. |

The manual session held selection for approximately 6.2 seconds. The first
sampled active status arrived about 402 ms after LOC transmission. Temporary
loss first appeared about 2.4 seconds after selection. These are polling
observations, not acquisition or loss-detection latency guarantees.

Video shows the chair inside the camera-rendered tracking brackets, then a
large change of view to the floor/cables with brackets on a different region.
GAC fields changed substantially over the same interval. This proves command
acceptance and tracking-state/scene changes, **not stable chair tracking** or
successful reacquisition of the same target. Handheld motion and the inverted
image prevent attributing all motion to the motors or diagnosing its cause.
No further automatic tracking run was attempted after this unstable result.

Three short tilt probes were also sent (−10/250 ms, +20/500 ms, −20/1000 ms).
The operator reported no visible gimbal movement. Record these as transmitted
commands with angle/video observations, not a new physical-motion success.

Private visual evidence:

- Manual chair brackets: `20260917T072331Z-observe/tcp-73.png`.
- Changed scene during lock/loss: same session, `tcp-181.png`.
- After cancellation: same session, `tcp-336.png`.

## New packet findings and unresolved differences

1. **ODR metadata exists on this unit.** Captures use case-sensitive `#tP`, a
   raw length byte `0x0D`, count 1, one 12-byte record and two checksum bytes:
   total 25 bytes. Little-endian signed shorts yield plausible image-pixel
   geometry, for example `(1557, 5, 357, 1026, 127, 0)`. Every observed record
   in this pass has label 127 and confidence 0. Do not label these as a verified
   person class or discard them through an assumed confidence threshold.
   No multi-object packet, class mapping, reliable overlay alignment or
   successful detection-assisted snap was demonstrated.
2. **OFT is tracking geometry, not angles.** The PDF explicitly defines box
   top-left x/y, width/height and tracking status. The manual run's first OFT
   decodes as `(1288, 590, 127, 81, 0x32)` with little-endian shorts. Cancellation
   produced `(0, 0, 0, 0, 0x31)`. Live status is ASCII `2`/`1`, despite the
   specification's numeric-looking comments. The existing speculative runtime
   angle parser must be corrected before integrating controls.
3. **TRA conflicts with the documented health meaning.** Six fault queries
   each produced `TRA11`, copied to three listening ports (18 deliveries),
   while TRC remained ready and detection output existed. The PDF says such a
   reply indicates abnormal tracker operation. Do not reinterpret it as a
   healthy ACK or use silence as proof of health. Firmware behavior versus
   documentation remains unresolved; this investigation did not reset firmware.
4. **Temporary loss is now observed.** TRC03 occurred repeatedly in the manual
   run. Subsequent TRC02 does not prove reacquisition of the original chair.
   The PDF says permanent loss returns to awaiting selection; a controlled
   occlusion/permanent-loss experiment is still outstanding.

## Cleanup and validation

Control sessions used bounded durations, repeated movement/zoom stops, tracking
disable and best-effort stop threads. AI sessions also sent FED20 during
cleanup. The last manual run returned TRC00; the separate final query confirmed
it. Stabilization can remain powered. No device watchdog or disconnect behavior
was established.

The updated evidence manifest records exact script revisions and raw packets
for all sessions, including the rejected AI selection. Packaging checks script
syntax, SHA-256 links, frame-image hashes locally, and transmitted/received
checksums. See the evidence validation record for totals. No runtime files were
changed; application tests/build were not rerun for this evidence-only follow-up.

## Next bounded slices

1. Correct the existing telemetry prerequisites with captured fixtures:
   byte/checksum validation, independent angle/status scheduling, OFT separation
   and inactive/lost/unsupported handling. Keep unverified GIA diagnostic-only.
2. Add a default-off provider control contract and typed APIs; use one socket
   owner, explicit capabilities, fresh confirmed state and bounded held inputs.
3. Add the gated responsive panel with manual ROI and AI-assisted click paths,
   inverse video-coordinate transforms, and the agreed following-stop interlock.
4. Qualify camera tracking on a steady, correctly oriented mounting base with
   a suitably framed person: actual fuzzy snap, target changes, controlled loss,
   rotation/zoom mapping and stopping. This pass is not flight acceptance.

The PDF resolves the existence of both workflows and basic commands. Remaining
manufacturer questions should be limited to evidence gaps: descriptor byte
order/reserved bit 0, TRA meaning on this firmware, ODR label/confidence fields,
coordinate/timestamp contracts, and supported mounting/watchdog behavior.
