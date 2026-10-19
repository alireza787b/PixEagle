# Native WebRTC: encoded workload and delayed-frame checkpoint

Status: software repair under qualification; no deployment or release.

The backend work starts at `eba9e8d818af1d4216cd4965fc5fd99e3128f3a7`
on `feature/video-quality-adaptive`. QGC's upstream-port baseline is
`d35cefcc96c97bf06e0f8bbb58d8f8a3781b3a6b`; its integration worktree also
merges upstream `c535d1dea7f5ea24dd5a0818c2aa768ab0ddbd0d` at
`badb1441e887c753a72a2128362739ec8fd81544`.

## Backend changes

- Reuse `AdaptiveQualityEngine` profile/startup bounds and hysteresis for native
  encoded workload. GCC owns bitrate estimation/pacing; actual
  submission-to-payloader feedback controls pixel/cadence workload. JPEG ACK
  and delivery measurements remain separate.
- Renegotiate raw dimensions/FPS with immutable publisher geometry. Preserve
  capture identity, analysis pixels and exact outgoing RTP association.
- Retain the native in-flight selection window within the existing shared
  frame, age and byte bounds. ACK-paced JPEG keeps its three-frame limit.
- Advertise and verify negotiated NACK/PLI feedback. A transceiver property
  alone did not establish generic NACK negotiation.
- Add truthful per-peer bitrate, delivery-policy, pipeline-time and feedback-age
  diagnostics. Pipeline time includes queueing, not just encoder service.
- Extend camera-free fixtures with scaled geometry, decoded-dimension checks
  and optional deliberate metadata delay. No production setup prompt, API
  route, authentication store, gain or flight authority changes.

## Related receiver repair

QGC rejects flagged corruption and mismatched decoded dimensions, requests a
keyframe through negotiated feedback for an unresolved resize, and joins late
metadata to the exact decoded buffer for at most 100 ms before presentation.
Stop cancels this wait. Late metadata cannot authorize a previously displayed
image. Association counters distinguish missing RTP, missing metadata,
geometry refusal and corruption.

The custom receiver also follows QGC's plugin cleanup hook so it is destroyed
before application teardown. The existing upstream cleanup fix covers the stock
receiver list separately.

## Verification and limits

Evidence: `~/.cache/pixeagle-qgc-baseline/native-webrtc-2026-10-19/`.

- Backend unit gate: **3,727 passed, seven optional-runtime skips**.
- Backend integration gate: **196 passed**.
- Final focused streaming/route/config gate: **377 passed, seven skips**.
- Optional-runtime encrypted peer tests: **22 passed**; the two negotiated
  congestion/NACK tests also passed after enabling receiver feedback.
- Schema drift: current, 43 groups / 612 parameters.
- Native-disabled QGC source syntax checks passed.
- Recorded QGC H.264/VP8 matrix passed at **2/5/10 Mbps**, with 40 ms delay,
  5 ms jitter and 0.5% configured random loss. Qdisc congestion drops are
  additional to that configured random loss. Each codec has ten seconds of
  observation after its first verified frame; this is not a soak.
- A separate 10 Mbps, loss-free run with **50 ms injected metadata delay**
  passed both codec, frame-identity and retained-selection checks.
- **0.5 Mbps remains unqualified**: startup/usable-frame gates failed.
- **1 Mbps remains unqualified for VP8**: resize recovery or selection freshness
  still fails. H.264 passed short probes but had multi-second verified-frame
  gaps; no seamless-operation claim is made.
- Full QGC regression renewal: **471 suites passed**, standard `Flaky|Network`
  exclusions; changed-file lint passed. Weak-link fallback qualification remains
  open. Failed attempts are retained.

The optional peer fixture's extreme 64 kbps uniform-pixel diagnostic also failed
its strict pixel-fidelity check. A separate diagnostic confirmed dimensional
transitions, but deliberately relaxed pixel comparison; it is not acceptance
or frame-identity evidence. Do not convert it into a passing qualification.

Native product capability remains disabled. Core operation without optional GI
still uses browser aiortc and the qualified native JPEG fallback. No Pi, camera,
Pixhawk, service or saved field profile was changed.

## Next work

Close weak-link recovery/fallback and receiver-feedback gaps, reconcile native/JPEG
aggregate allocation through the existing budget owner,
and record exact candidate revisions. Then request the cooled Pi for a recorded
video checkpoint without and with the optional runtime, using a longer bundled
clip (test11 is about 290 seconds). Camera tests and Windows packaging/operator
acceptance follow. Keep ordinary defaults and the custom vertical-gimbal
profile separate and backed up during deployment.

## Presentation, shared budget and controller fallback continuation

The current slice adds typed optional presentation feedback on the existing
authenticated challenge message. QGC counts distinct confirmed surface swaps
separately from decoded/context receipts and sends local elapsed intervals and
conservative age bounds. Old/regressed epochs cannot freshen the receiver;
sustained renderer pressure reduces cadence, while workload increases require
fresh healthy presentation evidence. These observations confer no selection
or aircraft authority.

Native encoder admission and JPEG pacing now share `VideoDeliveryBudget`.
Reservations survive delayed encoder teardown and leave a JPEG share; cancelled
startup releases its reservation. This is a configured payload allocation,
not a wire-rate guarantee. The transitional aiortc browser provider remains
outside the allocation; existing media-health details explicitly report that
gap. No private aiortc encoder fields are modified.

A longer test11 run revealed an H.264 concealed-slice barcode mismatch at
10 Mbps. The native receiver now negotiates complete AVC access units, required
for the depayloader's wait-for-keyframe guard. The renewed 20-second-per-codec
10 Mbps test passes; 1 Mbps still has H.264 gaps and VP8 resize/selection failures.
The failed artifacts remain available. No age limit or timeout was extended.

The loopback integration fixture reuses production auth, signaling, publisher,
native sender and JPEG routes. QGC controller tests pass healthy native playback,
negotiation-refusal fallback, missing-metadata watchdog fallback and explicit
Stop. Initial fixture geometry/signal-lifetime failures remain documented in
the raw logs. These are software tests, not physical acceptance.

Renewed evidence in the same cache directory:

- `presentation-qgc-full.log`: 471 suites passed, 210 seconds.
- `presentation-backend-unit.log`: 3,793 passed (unit plus route inventory), seven skips.
- `presentation-integration.log`: 196 passed.
- `presentation-final-focused.log`: 422 passed, seven optional-runtime skips.
- `presentation-actual-media.log`: 36 actual-media/feedback cases passed.
- `presentation-schema.log`: schema current, 43 groups / 612 parameters.
- Dashboard: 64 suites / 493 tests passed; production build and lint passed.
  The existing outdated Browserslist database notice is retained in the logs.
- `controller-normal-qgc-v3.log`, `controller-reject-qgc-v2.log`,
  `controller-missing-metadata-qgc.log`: real controller playback/fallback passed.
- `access-unit-10mbps/`: both codecs passed; `access-unit-1mbps/` and
  `vp8-resize-1mbps-debug/` retain weak-link failures.

Native capability remains disabled. Remaining gates include constrained-link
fallback, restart/revocation, VP8 resize recovery, browser aggregate parity and
clean platform runtimes. No Pi, camera, flight settings, deployment or GitHub
build was changed. Request the cooled Pi for the longer recorded-video checkpoint
after local readiness, then camera and Pixhawk separately as agreed.

The required whitespace hook normalized 40 pre-existing whitespace-only lines
in `fastapi_handler.py`; its only behavioral change is passing the shared
payload-budget owner to `WebRTCManager`.

## Packet-loss integrity continuation

QGC now invalidates prediction-reference provenance after incomplete RTP access
units until a complete clean sync frame arrives. A decoded-size mismatch is a
named failure with automatic JPEG fallback. The Linux VA-API VP8 decoder can
conceal damaged pixels without marking them corrupted; a retained 741/749
barcode mismatch motivated this additional guard. No barcode tolerance,
selection-age bound or presentation watchdog was relaxed.

The sender adopts the pinned webrtcsink short CBR/VBV buffers and 15-bit VP8
picture IDs, retaining the framework default 200 ms jitter latency. H.264
aggregation was tried and reverted after ambiguous access-unit associations.
Client QoS elapsed counters now permit long-lived sessions, rather than
silently discarding feedback after one week. Native integration fixtures add
an explicit wrong-dimension fault; product capability remains disabled.

Renewed evidence:

- `reference-final-backend-core.log`: 399 passed, seven optional-runtime skips
  (streaming units, route inventory and parameter reload).
- `reference-final-backend-actual-media.log`: 38 passed with optional GI,
  encrypted media, RTCP feedback and presentation validation.
- `reference-recovery-10mbps-loss/`: strict displayed identities passed for
  both codecs, 20 seconds each. H.264 largest verified-frame gap 962 ms; VP8
  476 ms. This is a short controlled observation, not a field latency promise.
- `reference-controller-normal-2mbps/`: authenticated native playback passed.
- `reference-geometry-fallback-1mbps/`: wrong decoded geometry recovered to
  fresh selectable JPEG; the expected source/bus errors were verified.
- `reference-metadata-fallback-1mbps/`: connected native transport without
  metadata recovered to selectable JPEG, 13.4-second total test runtime.
- `reference-metadata-fallback-05mbps/`: startup fallback passed, 10.4 seconds.
  Native never connected, so this is not metadata-loss recovery evidence.
- Changed-file backend and QGC lint passed; native-disabled source factory and
  receiver syntax checks passed. Full QGC renewal is recorded separately.

Sticky-event ordering warnings from VA-API VP8 remain visible. Sustained native
0.5/1 Mbps quality, actual cadence under stalled analysis, restart/revocation,
browser/native aggregate parity and clean platform packages remain open. No
hardware, deployment service, saved profile, flight gain or Actions run changed.

## Measured cadence and decoder-input continuation

Native delivery diagnostics now separate requested FPS from
`associated_encoded_fps`, measured over complete one-second windows. Stale,
idle and changed-profile measurements expire. Spatial workload uses observed
cadence while pipeline overload still uses the requested service budget.
Focused clock-controlled tests cover slow analysis, slow encoding and reset;
the optional actual-media test requires a measured encoder cadence.

The longer 2 Mbps retest failed strict VP8 barcode identity again. A cache-only
probe saved plaintext encoder output; independent decoding verified 83/83
source barcodes, while the received image failed. A software receiver also
failed, so VA-API alone is not the explanation. The raw failed probes and
`encoder-origin-independent-decode.json` remain in the evidence directory.

QGC inspection found a leaky encoded queue after the initial RTP guard.
The repair moves reference verification to decoder input and checks access-unit
ordinals across that queue. Missing references require a clean sync frame
before dependent units enter the decoder. Verification is in progress; product
native capability stays disabled. No hardware or deployment changes are made.

Cadence validation passed `cadence-final-core.log` (150 tests, five optional
skips), `cadence-final-actual-media.log` (81 tests with the optional runtime),
and `cadence-final-backend-unit.log` (3,798 tests, seven optional-runtime skips).
Schema remains current at 43 groups / 612 parameters. The existing Starlette
422-name deprecation warnings remain in the logs; no warning filter was added.

The first decoder-input repair probe at 2 Mbps preserved VP8 identity for
213 frames across 20 seconds, largest verified gap 892 ms. H.264's ending
freshness check failed with no barcode mismatch; the overall run remains a
failure and 2 Mbps is not a qualified native operating claim. Independent
camera and aircraft acceptance are still separate gates.

`cadence-final-integration.log` renews the 196-test backend integration gate.
The real bound-manager QGC lifecycle fixture now passes source replacement,
cached-capture rejection/recovery, sign-out/new-session and explicit Stop
(`controller-recovery-v3-10mbps/`, 8.2 seconds). Initial fixture assumptions
about error-stage normalization and waiting for logout completion were fixed;
their failed logs remain available. This is local software evidence.

## Cooled Pi and cadence-only caps repair

An isolated ten-minute Pi replay completed at peak 60.6°C without throttling.
The operator found motion almost acceptable but reported progressive pixelation;
the native policy reached 320×180. Capture stayed fresh during the retained
115-sample observation. Native quality is not accepted. Ordinary installed
source/configuration and the native product gate remain unchanged.

A Windows Ethernet bridge made the datalink reachable from Ubuntu. The first
unconstrained ICE run still used Wi-Fi, as interface counters demonstrated.
A later normal-sender test temporarily excluded the candidate user's Wi-Fi UDP
path, retained TCP management and automatically removed the test filter. It
received media over Ethernet at 960×540 but failed strict freshness. A private
ICE-binding experiment crashed before media; it is rejected test setup, not
a deployed receiver repair. Its source and failure evidence are retained.

The sender unnecessarily renegotiated raw-video caps for each policy FPS step.
The repair keeps the configured ceiling as nominal caps and uses PTS/duration
for delivery cadence; geometry changes still renegotiate. A regression first
failed on the extra 12-to-13 FPS caps update, then passed after the change.
Full-path Pi acceptance is still pending; no gain, bitrate floor, freshness
deadline, setup workflow or factory default was changed.

Verification: 328 streaming tests passed with seven optional skips, 74 route/
configuration tests passed, all 25 focused peer tests passed with the optional
encrypted-media runtime, and schema/syntax checks passed. Direct Ruff checks
retain pre-existing BLE001 and PIE807 findings, independently reproduced from
HEAD; checks excluding those baseline rules pass. The new import is sorted.
No Dashboard or QGC implementation changed in this repair. Evidence is under
the private `native-webrtc-2026-10-19/pi/` root, including
`cadence-regression-before.log`, `cadence-focused-after.log`,
`cadence-optional-media.log`, `cadence-streaming-gate.log` and
`datalink-filter-controller.log`.

## Repaired datalink acceptance and live-camera limits

The cadence repair is `15ae6d2`. Subsequent commits `73e6057` and `f384607`
document actual adaptation parameters/thresholds and extend the existing
inhibited harness for explicit RTSP capture-only import. No factory value,
flight gain, safety policy or installed profile was changed. The RTSP bench
imports no aircraft/gimbal-control settings; its snapshot validation retains
command preview, circuit breaker, disabled MAVLink and private loopback auth.
The new harness plus route/config gates passed 119 tests; changed-file Ruff,
syntax, schema and diff checks passed. The retained Starlette warning is
pre-existing. A first new harness test exposed its missing RTSP manifest-kind
admission; that validation was corrected and all gates renewed.

Repaired Pi-to-QGC recorded media passed both actual paths: datalink 13.51
presented FPS (largest gap 263 ms) and Wi-Fi 12.11 FPS (336 ms), each for 20
seconds. A 119-second visible datalink observation reached 1280×720 after
adaptive spatial/cadence changes. The operator reported smooth motion and good
quality. Preserve this raw report separately; the source was fresh throughout,
but dimensions also spent time at 640×360 and 960×540. This is not a guarantee
of continuous 720p/20 FPS. Temporary test UDP exclusions proved media routing
and were removed; SSH/API management remained reachable. A backend address
alone did not establish which ICE interface carried RTP.

The connected camera's independent source baseline was 1920×1080 at 29.88
decoded FPS over 30 seconds, no reported decode errors, peak 52.9°C. Its first
QGC Wi-Fi check passed 11.85 presented FPS (largest gap 418 ms), but a 120-second
visible observation failed sustained quality: 105/115 samples at 320×180,
target bitrate as low as 64 kbps, despite fresh source pixels. The Pi reached
73.8°C before requested stop. Camera datalink passed the short QGC check at
13.42 FPS (largest gap 302 ms); its longer run hit the 75.45°C thermal guard at
139.48 seconds and exited cleanly. The remaining quality/cooling limitations
must not be replaced with passing short-run claims. Optional long-poll clients
terminated on guarded shutdown; their incomplete observations are not soaks.

All 41 backed-up installed configuration files still match. Installed source
remains `664171e00`, normal `pixeagle.service` stays intentionally stopped, and
only the separate candidate worktree advanced. Saved circuit breaker is OFF;
do not restart the installed service while describing it as an inhibited
bench. No camera movement or aircraft command was issued. The operator was
asked to check/improve cooling; software work can continue independently.

Private evidence under `native-webrtc-2026-10-19/pi/` includes
`native-datalink-cadence-v8/`, `native-wifi-cadence-v9/`,
`camera-source-baseline/`, `native-camera-cadence-v10/`,
`native-camera-datalink-v11/` and `camera-bench-harness-gates.log`. Credential
files/manifests and camera imagery remain private. Source-startup/test-bound
failures are retained separately from measured presentation failures.

Next: profile the full camera workload and repeat sustained comparisons with
adequate cooling; close Wi-Fi quality, packet-loss provenance and fallback
gates before browser parity, platform packaging and deployment. The native
capability remains disabled. Do not tune flight-controller gains from these
video-only observations or call Wi-Fi a confirmed universal hardware defect.
