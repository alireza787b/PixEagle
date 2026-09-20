# Vendor tracking protocol reference findings

Date: 2026-09-17. Scope: review of operator-supplied PDFs and Qt source.
Statements below describe those references and proposed integration; they do
not assert additional live-camera validation. See the adjacent bench records
for hardware observations.

## Reference provenance

The supplied PDFs were copied from `/home/alireza/Downloads/` into the
gitignored local directory `reports/gimbal-bench/vendor-reference/`.
`manifest.json` in that directory records their source paths and SHA-256 hashes.
The PDFs themselves are not included in this evidence package.

| Local reference filename | SHA-256 |
| --- | --- |
| `Interaction Tracking Protocol(out).pdf` | `3f5315f6c1654155daaf7ddebd5f26dc46424c534a0866e694e05ce99473cfeb` |
| `User manual for FL-30 Camera.pdf` | `6c807d1f41e8f8df08d246114ca33549bc5e165672dc4e97ac4d8a89af2c124b` |

The reviewed Qt file is `VideoPlayer/mainwindow.cpp`, extracted locally under
`/tmp/pixeagle-vendor-review-n764alrk/VideoPlayer qt5 mingw32/`. Its archive
provenance is recorded in the checkpoint. Source line numbers below refer to
that supplied copy, not PixEagle runtime code.

## One camera tracker supports both selection interactions

Tracking protocol section 1 explicitly describes enabling recognition boxes
in the video, then either clicking a recognized object or manually selecting
a target. Section 2 defines a fuzzy-click descriptor bit that asks the camera
to select a nearby detection. This supports two UI interactions using the
same camera-side tracker; it does not require another local detection model.

| Operation | Reference definition |
| --- | --- |
| Enter selection mode | Section 1: `#TPPD2wTRC024F`; enables recognition and waits for a target. |
| Select target | Section 2: binary `LOC` coordinates and descriptor; fuzzy-click bit 3 selects a nearby detection when available. |
| Read tracker state | Section 3: `rTRC` with ASCII payload `00`. First returned character is mode; this PDF documents only mode `0`. |
| Cancel current target | Section 5: `wTRC01`, returning to target selection. |
| Exit tracking | Section 6: `wTRC00`, described for the target-selection state. |
| Enable detection metadata output | Section 9: `#TPPD2wFED1034`. Output is disabled by default. |
| Disable detection metadata output | Section 9: `#TPPD2wFED2035`. |

Sections 5–7 use serial examples with source address `U`; section 7 explicitly
requires source address `P` for UDP, with checksum recalculated. Preserve
case-sensitive headers and binary payloads; these commands are not all ASCII.

The FL-30 manual's recognition/tracking specifications name **human and
vehicle** categories, up to 100 simultaneous detections, minimum detection
size 16×16 pixels, tracking target dimensions 16–256 pixels, and target memory
of 2 seconds. These are vendor specifications, not measured capabilities of
this device/firmware. A room without a visible person or vehicle is not a
useful negative test of semantic detection.

## Selection geometry and descriptor ambiguity

Tracking protocol section 2 defines center coordinates relative to image
center: each image axis spans 2000 units, from −1000 to +1000, positive right
and down. Width and height are also scaled to their respective image axes.
For normalized image coordinates `(u, v, width, height)`, the corresponding
values are `(2000u−1000, 2000v−1000, 2000width, 2000height)`, subject to the
adapter's validated rounding and bounds. The 16–256 target-size constraint
is in pixels before this coordinate conversion, not a wire-unit range.

The payload contains signed 16-bit x/y, unsigned 16-bit width/height and a
16-bit descriptor. The worked example uses big-endian coordinate bytes:
64×64 pixels at the center of a 1920×1080 image becomes `(0, 0, 67, 119)`.
Its ten payload bytes are `00 00 00 00 00 43 00 77 00 08`.

The descriptor table says **little-endian**, but the example ends `00 08`,
placing fuzzy-click bit 3 as in a big-endian value. The Qt implementation at
`mainwindow.cpp:590–622` likewise puts descriptor flags in the last byte,
but sends `00 09` for point selection and `00 01` for box selection. The PDF
marks bit 0 reserved. Preserve this discrepancy explicitly: compare the
documented and Qt variants in controlled bench tests before choosing a
production encoding. Do not silently transpose descriptor bytes or assume
reserved bit 0 has no effect.

Qt maps displayed image coordinates through a virtual 1920×1080 image and
then the protocol scale. A reusable browser adapter should instead preserve
normalized source-image geometry, account for letterboxing and invert any
display rotation/flip before encoding. Unsupported crop/PIP transforms need
an explicit capability limit rather than guessed coordinates.

## Tracker state, tracking boxes and detections are distinct data

Section 3 defines states `0` disabled, `1` awaiting selection, `2` actively
tracking, `3` temporarily lost, and `4` tracking unsupported. Permanent loss
returns to selection state. Qt's additional vehicle/person mode labels are
not evidence that this PDF supports commands to select distinct modes.

Section 7 defines `OFT` as a packed tracking-result structure: `#tp`, source
`D`, destination `P`, length `9`, control `w`, command `OFT`, four `short`
fields for bounding-box top-left x/y and width/height, a tracking-status byte,
and two checksum characters. **OFT is bounding-box telemetry, not gimbal
angles.** The reference does not explicitly specify short endianness or
whether the status byte uses numeric values or ASCII digits. Establish those
from raw captures. Never feed OFT coordinates into flight angle state.

Section 8 defines detection results separately as `ODR` with the mixed-case
header `#tP`. Its packed payload starts with a detection-count byte, followed
by that many records of six `short` fields: x, y, width, height, label ID,
confidence. Confidence is scaled by 10000. Two checksum characters follow
the last actual record; the declared 255-element C array is a maximum, not
a requirement to send empty records.

Open ODR format questions requiring captured evidence are:

- Short endianness and signedness constraints; coordinate units and whether
  x/y are top-left or center are not explicit in section 8.
- Label-ID mapping is not supplied; do not label detections using a guessed
  model's class list.
- The single `char` length field cannot directly represent the full
  `1 + 12 × 255 = 3061` byte payload. Its encoding/overflow semantics need
  confirmation; validate datagram size, record count and checksum together.
- No stable target identifier, frame timestamp or selection acknowledgement
  sequence is defined. Detection metadata cannot alone prove which object
  was acquired or that its geometry matches the displayed frame.

## Heartbeat is documented as a fault indication

Section 4 specifies serial example request `#TPUD2rTRA004B` every 1–3 seconds
and response `#TPDU2rTRA114D`. Its text says a response indicates an abnormal
tracker, such as watchdog reset or algorithm failure, and the ground station
should reset its tracking state and wait for reboot. This is not documented
as an ordinary positive health acknowledgement. Silence must not count as
proof of health; retain independent freshness checks on actual state.

## Proposed integration boundary

Keep the integration default-off and expose its controls only when the
compatible external gimbal tracker and the optional control capability are
enabled. Provide camera-assisted click selection and manual point/region
selection within one camera tracker lifecycle. The existing ordinary
PixEagle tracker workflows should retain their default behavior.

Use a vendor adapter for binary framing, capabilities, coordinate conversion
and camera state. Reuse the existing connection owner and typed API/action
contracts. Distinguish candidate detections, selected-target geometry,
tracking state and angle telemetry, including separate freshness checks.
Following must use confirmed eligible tracking/angle state; a sent UDP
command or visible detection alone is not successful acquisition.

Validate embedded video boxes plus fuzzy click first. Add ODR-driven browser
overlays only after its framing/geometry are demonstrated, avoiding duplicate
boxes where the camera already burns them into video. Require following to
stop before manual target or camera changes, as agreed for this integration.
No Qt runtime, local AI model or new tracker algorithm is necessary for this
scope. Implementation and live bench outcomes remain separate slices.

## Additional UDP/UART protocol supplied during implementation

The operator subsequently supplied `udp&uart-Protocol - EN(1).pdf`, whose
cover identifies document version **V1.1.3**. Its local copy is
`reports/gimbal-bench/vendor-reference/udp&uart-Protocol - EN(1).pdf`;
the reference manifest and a direct file hash give SHA-256
`cde37e2e73a714ceb5bf57b7191d80ad9fe11281193da1df8c492077d9dc4768`.
Section 1 describes a SIP-series protocol covering multiple product variants;
an available command in this document is not proof that this camera supports
or has passed testing for that function.

| Section | Additional reference finding | Integration consequence |
| --- | --- | --- |
| 2.1, frame structure | `#TP` is fixed two-character payload, `#tp` has an ASCII length through `0x0F`, `#tP` uses a raw length byte through `0xFF`, and `#Tp` extends length through `0xFFFF` using the control-byte position. | This clarifies raw ODR length encoding but does not resolve the tracking PDF's `#tP` header with up to 255 twelve-byte records. Do not assume an undocumented switch to `#Tp`; retain capture-based length/count validation. |
| 4.2, speed control | `GSY`, `GSP`, and **`GSR`** control yaw, pitch, and roll speed. Each uses a signed eight-bit speed encoded as two ASCII hex characters, with documented range −99 to +99 degrees/second. Section 4.1 `PTZ00` stops rotation. | Roll speed control is now **documented, not hardware-verified**. Do not advertise roll as a validated capability or add it to this manual-control slice without separate testing. |
| 4.3.3, attitude reading | `GAC` reads magnetic encoder angles; section 4.3.1 defines the encoder reference relative to the airframe. Replies contain yaw/pitch/roll as signed 16-bit ASCII hexadecimal centidegrees, high byte first. | Supports retaining GAC as the body-relative angle source. |
| 4.3.5, gyroscope reading | `GIC` reads gyroscope attitude in the spatial reference described in section 4.3.2, with the same angle encoding. | Spatial attitude must not overwrite body-relative guidance input. |
| 4.3.6, active gyro transmission | `GIA` is documented as the enable/disable switch for gyro reporting: write `01`/`00`, or query a two-character `00`/`01` switch-state reply. | Earlier bench captures instead contain a twelve-character angle-shaped `GIA` reply to `GIC`. This is a document/firmware discrepancy, not evidence that GIA should be aliased to GIC or GAC. Preserve it as raw diagnostic data. |
| 5.6.2, flip/mirror reading | `rROT` queries camera image orientation; documented return values are `00` for 0° and `02` for 180°. Serial example is `#TPUD2rROT0059`. | A read-only orientation query is documented; UDP uses source `P` and a recalculated checksum. This reference does not establish how camera-side rotation affects LOC coordinates. |

### Pitch direction requires separate command and angle conventions

Section 4.2 says positive yaw speed rotates right and **positive pitch speed
rotates downward**. Sections 4.3.1 and 4.3.2 instead describe positive pitch
angle commands as upward, while their introductory 90° examples describe
downward pointing. These statements are inconsistent as a single sign
convention. The control adapter must distinguish speed-command sign from
reported angle sign and validate visible movement for the mounted camera.
Do not relabel speed buttons or invert flight-angle telemetry solely from
one of these prose statements.

This appendix records document findings only. It adds no roll, angle-control,
orientation-query or other live-test success claim. The subsequent user
instruction narrows implementation to **manual camera selection and controls
first**, leaving AI-assisted selection and ODR overlays for a later slice;
both can still use the same optional camera tracker boundary.


## 2026-09-18 implementation and source-comparison update

The subsequent bounded GSR probe and actual PixEagle API roll +/− calls produced
signed GAC roll changes. Roll is now included in the optional manual controls;
the earlier table's “not hardware-verified” statement records the earlier review
stage. This is not angular-accuracy or physical-direction calibration.

Read-only VSN response in `20260917T185212Z-identity` contained `1.6.26.R.D`.
Model identity remains unverified. The complete Qt workflow, source hashes,
manual/fuzzy differences, loss-display omission, exact Qt click bench and
remaining manufacturer questions are recorded in the
[2026-09-18 checkpoint](../../checkpoints/2026-09-18-gimbal-qt-workflow-review.md).
