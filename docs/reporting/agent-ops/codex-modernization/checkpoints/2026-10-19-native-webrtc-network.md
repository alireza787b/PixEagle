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
