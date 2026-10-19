# Native WebRTC qualification

## Current behavior

The authenticated WebRTC signaling manager prefers the locally supported H.264
profiles, then VP8, while preserving RTX and other local codec capabilities.
The remote offer determines the available intersection: a VP8-only browser
continues to work. No new transport setting or separate authentication path is
introduced.

The answer includes an additive `media_capabilities` object. It reports codec
preferences, `provider: aiortc`, `native_frame_association: false`,
`interactive_native_transport: websocket_jpeg`, and
`presentation_verified: false`. Preferences are not negotiated-codec or
rendering evidence. QGC continues to use the qualified authenticated JPEG path
for interactive selection; this change does not enable native WebRTC.

The typed `GET /api/v1/streams/client-config` response also exposes a separate
`native_webrtc` capability record for native clients. The current aiortc
browser provider reports `available: false` for that record because it does not
yet provide exact RTP-to-presented-frame association. This gate prevents QGC
from selecting WebRTC merely because browser negotiation works. Once the
GStreamer sender and native receiver pass provenance qualification, the record
will advertise `provider: "gstreamer"`,
`frame_association: "verified"`, and keep WebSocket JPEG as the fallback.

The same capability record includes `runtime_ready` and a bounded
`missing_components` list. A missing PyGObject/GStreamer runtime or any
required WebRTC element keeps native QGC support unavailable and gives the
operator a diagnosable reason; it never silently falls back to an unqualified
transport.

Transport and codec selection are automatic. Users do not configure a
bandwidth estimator, ICE internals or codec priority. The existing shared
streaming configuration remains authoritative; advanced limits belong there.
Installing the optional GStreamer runtime must not become a prerequisite for
ordinary PixEagle use. Without it, retain aiortc browser WebRTC and the existing
JPEG path for native clients. These are supported fallback providers, not
duplicate configuration services. Retire obsolete branches only after their
required compatibility behavior has a qualified replacement.

Peer cleanup diagnostics now include elapsed monotonic session time and the
average video payload bit rate over that interval when sender statistics are
available. The average includes negotiation/idle time and excludes network
packet overhead. It is not available-link capacity, instantaneous congestion,
client receipt, decoded FPS, or presentation latency. Existing sender counters
remain available. No SDP, ICE addresses, source credentials or session tokens
are included in these diagnostics.

## Why input timestamps are insufficient

Inspection of aiortc 1.15.0 found that its RTP sender adds a random origin to
the encoded-frame timestamp inside its private send loop. The 90 kHz PTS set
by `VideoStreamTrackCustom` is therefore not the transmitted RTP timestamp.
The public sender statistics do not expose a per-frame outgoing timestamp
callback. Do not infer this mapping from frame arrival order, approximate
clocks, or the latest tracking telemetry; do not patch private aiortc methods.

The inspected codecs use software `libx264` and `libvpx`. Their built-in
initial/maximum bitrates were respectively 1/3 Mbps and 0.5/1.5 Mbps; receiver
REMB feedback adjusts encoding within those implementation limits. These are
observed dependency behavior, not PixEagle configuration or a hardware encoder
guarantee. Recheck them when upgrading the dependency.

## Chosen extension: GStreamer media provider

Extend the existing authenticated signaling/lifecycle manager with a
GStreamer WebRTC media provider. Use its public encoder/payloader pad probes
to associate original frame PTS with actual RTP SSRC and timestamp. This
avoids maintaining an aiortc fork. Keep existing aiortc browser compatibility
until the replacement meets the same authentication, ICE, capacity, revocation
and cleanup contracts. A provider must not create another socket owner,
credential store, camera reader or configuration service.

The complete identity chain must be:

1. A publisher capture identity and immutable geometry/context enter the
   encoder with an explicit PTS and provider epoch.
2. The payloader probe records the actual RTP timestamp and SSRC for that
   encoded access unit. Send its context through the authenticated signaling
   session or a peer-bound data channel with bounded queues.
3. QGC probes the receiver RTP output and records the exact relationship to
   its GStreamer buffer PTS. Join decoded output by exact PTS, not nearest
   timestamp; retain SSRC and epoch to distinguish wrap/reconnect.
4. Immediately before presentation, attach a process-unique existing
   `QGCVideoFrameContextStore` identifier to the decoded frame. Reuse the
   existing presented-frame and screen-geometry selection checks.
5. If the mapping is absent, ambiguous, expired or incompatible, reject
   interactive selection and use the qualified JPEG fallback. New telemetry
   cannot retroactively authenticate a displayed old image.

`GstReferenceTimestampMeta` is not by itself a capture-identity association:
it carries reconstructed reference-clock timing after synchronization.
Camera-compressed passthrough needs the same proven identity between analysis
frames and encoded output before it can support selection.

## Feasibility and platform gates

- First prove exact mapping with recorded numbered frames, H.264 and VP8,
  codec drops/reordering, delayed metadata, RTP wrap, source changes and
  reconnect. Instrument encoder submission, wire timestamp, decoder output
  and presented identity independently. Prove dropped frames never inherit
  another frame's context.
- The reviewed QGC SDK pins GStreamer 1.28.4. Its current common plugin
  allowlist omits WebRTC, NICE, DTLS, SRTP and SCTP. Add required plugins and
  development libraries through the existing build configuration and packaging
  system. The inspected local Linux runtime was 1.24.2 with `webrtcbin`, but
  its WebRTC development pkg-config package was absent.
- Android needs static registration and complete ICE/DTLS/SRTP/SCTP link
  dependencies. Windows needs clean-machine packaging/decoder validation;
  installing development GStreamer globally must not be required by users.
- `PixEagleVideoItem` currently presents CPU-backed frames and rejects GPU
  handles. First measure negotiated CPU output; qualify native texture
  rendering separately if needed, retaining actual presentation identity.
  Adding `webrtcbin` alone does not establish visible QGC video.
- Validate an established congestion controller with the chosen GStreamer
  sender. A WebRTC connection alone is not proof of adaptive encoding. Measure
  CPU, temperature, encoder latency and constrained-link behavior on the Pi.
- Keep native WebRTC capability disabled until exact frame association,
  presentation, selection, authentication and platform packaging pass. Retain
  JPEG fallback across negotiation, media and metadata failures. Do not resume
  tracking, camera movement or following when a transport reconnects.

## Validation evidence

`GStreamerFrameAssociation` is the implemented sender prerequisite, not an
enabled transport. It freezes JSON frame context before appsrc submission and
joins observed payloader packets by exact segment running-time. It emits an
association only at an H.264/VP8 access-unit marker, with the actual SSRC and
32-bit RTP timestamp. It handles timestamp wrap without deriving an offset.
Context capacity, age and per-frame metadata size are bounded. Retired epochs,
reused input times, inconsistent packet identities and ambiguous associations
are rejected. Reset the helper before replacing a source, codec or segment;
every pipeline callback must retain the epoch from its creation.

An encoder may change the raw buffer PTS: the measured `x264enc` pipeline adds
1000 hours. Use the public `GstSegment.to_running_time` conversion on both sides
of the encoder, not a hardcoded offset. When an input is refused, discard its
context. An omitted/dropped frame has no output association; do not shift its
context onto the next frame. Association at payloader output does not prove
that a packet was sent on the network, received, decoded or presented.

Run the camera-free qualification with an interpreter that has the optional
GStreamer introspection packages:

```bash
/usr/bin/python3 tools/qualify_gstreamer_association.py \
  --output /tmp/pixeagle-gstreamer-sender-association.json
PYTHONPATH=src .venv/bin/pytest -q \
  tests/unit/streaming/test_gstreamer_frame_association.py \
  tests/unit/streaming/test_gstreamer_sender_optional.py
```

The actual-packet pytest cases skip if GI/codecs are absent. The standalone
tool fails with diagnostics instead of claiming qualification. Existing
installations do not acquire a mandatory GI dependency. Software encoder
probes require `appsrc`, `videoconvert`, `appsink`, plus `x264enc`, `h264parse`,
`rtph264pay` for H.264 or `vp8enc`, `rtpvp8pay` for VP8. GI needs the `Gst` and
`GstRtp` 1.0 typelibs. Full WebRTC additionally needs `webrtcbin`, libnice
(`nicesrc`/`nicesink`), DTLS/SRTP, SCTP, and corresponding development libraries
in native builds. These are diagnostic requirements, not instructions to
install development GStreamer globally on a packaged QGC user's machine.

On the inspected Linux GStreamer 1.24.2 installation, both actual H.264 and VP8
probes passed with fragmented RTP, forced timestamp wrap, intentionally omitted
input and a second source epoch. Their input running-times remained exactly
associated with the observed RTP packets. `nicesrc` and `nicesink` were absent;
no ICE connection was attempted. No Pi performance, network delivery, receiver
decoding or QGC presentation claim follows from this result.

Add `--decode-receiver` to run independent H.264/VP8 RTP/jitterbuffer/decoder
pipelines from copied packets. This gate passed locally with reordered RTP,
wrap, omitted source input, delayed metadata and two source epochs. The probe
joins marker-packet running-time to exactly equal decoded-buffer running-time
and checks uniform decoded luminance against independently numbered input.
One intentionally missing metadata entry stays noninteractive; its late arrival
cannot relabel another frame. Receiver timing differs from source timing because
the jitterbuffer adjusts it. Never match decoded output directly to source PTS
or by a nearest-time heuristic. These bounded fixture checks do not qualify
native QGC rendering or a WebRTC connection. Receiver probes additionally need
`rtpjitterbuffer`, `rtph264depay`/`avdec_h264` or `rtpvp8depay`/`vp8dec`.

The inspected runtime also lacked `rtpgccbwe` and `webrtcsink`. ICE connectivity
alone would therefore not fulfill the congestion-control gate. For the explicit
`webrtcbin` provider, integrate the established `rtpgccbwe` Google Congestion
Control element through the public `request-aux-sender` hook, negotiate TWCC,
and apply `notify::estimated-bitrate` to encoder targets. The sum of targets
must fit the estimate. Package the required gst-plugins-rs component and measure
pacing/adaptation; do not replace it with a new traffic heuristic. See
[rtpgccbwe](https://gstreamer.freedesktop.org/documentation/rsrtp/rtpgccbwe.html)
and [webrtcbin](https://gstreamer.freedesktop.org/documentation/webrtc/).

## Native sender implementation and loopback checkpoint

`GStreamerWebRTCPeer` now consumes the existing immutable `FramePublisher`
through a dedicated media worker. It never opens a camera or socket. The
existing manager owns authorization, signaling capacity, session expiry and
cleanup. Native offers request `provider: "gstreamer"` on that same signaling
session; ordinary browser offers continue through aiortc. The experimental
provider is refused before allocation while native capability is unavailable.

The sender supports H.264 constrained-baseline, then VP8, with one video media
section, bounded appsrc/encode queues and a bounded metadata mailbox. Setup
and teardown run off the asyncio API/control loop. Concurrent close operations
join one teardown; retired epochs and callbacks cannot emit new metadata.
Source identity changes terminate the peer for owner-controlled recovery.

Payloader access-unit observations produce `frame-context` messages containing
the provider epoch, actual SSRC/RTP timestamp and immutable publisher context.
They travel on the existing authorized signaling socket. A prior client
`frame-challenge` token is echoed in the context: the receiver's elapsed local
time from sending that token provides a conservative age bound without
comparing clocks across machines. This does not measure sensor exposure time.
Until the receiver verifies this association at presentation, the sender still
reports `presentation_verified: false` and native capability remains disabled.

The public `request-aux-sender` callback installs `rtpgccbwe` when TWCC is
negotiated. Estimated bitrate notifications update the encoder target. Missing
TWCC or the estimator refuses adaptive native negotiation. Installing the hook
does not by itself qualify adaptation under network congestion; the network
matrix, per-client policy and aggregate budgets remain open gates.

Run camera-free encrypted transport checks with:

```bash
PYTHONPATH=src .venv/bin/python tools/qualify_gstreamer_webrtc.py \
  --congestion-control --output /tmp/native-webrtc-loopback.json
```

The optional Linux runtime needs PyGObject with Gst/GstRtp/GstSdp/GstWebRTC/
GstVideo typelibs, NICE, DTLS/SRTP, both codec paths and `rtpgccbwe`. The local
1.24.2 test used gst-plugins-rs **0.13.7**, commit
`cdec77cad2d9b7348d800507bc6eeec5039717eb`, its checked-in Cargo lock and Rust
1.75.0. This is development evidence, not a new production dependency pin for
the QGC 1.28.4 SDK. Do not require users to install development GStreamer.

The fixture tests real ICE, DTLS/SRTP, H.264/VP8 decoding and independently
recognizable pixels. It deliberately withholds one frame's metadata and checks
that its late arrival cannot authorize another frame. With
`--congestion-control`, it also requires actual installation of the GCC hook.
The short, unconstrained loopback does not establish usable bandwidth,
adaptation, camera latency or flight performance.

`tools/qualify_gstreamer_native_server.py` supplies numbered barcode frames to
the QGC presentation test. It binds **127.0.0.1 only**, reuses the manager's
local-compat authorization, and has no tracking or aircraft routes. Only this
fixture admits the experimental sender before product qualification. It must
never be used as a deployment launcher or as browser-session security evidence.

The remaining sequence is QGC presented-frame qualification, automatic
capability discovery/fallback, constrained-network and lifecycle qualification,
then platform packaging and the Pi/operator checkpoint. The existing JPEG
path remains the default during this work; no deployment profile is migrated.

The 2026-10-19 Linux checkpoint passed the QGC GStreamer policy/orchestrator
suite (30/30) and the PixEagle runtime/link tests (7/7). Evidence is retained
under `~/.cache/pixeagle-qgc-baseline/native-webrtc-2026-10-19/`; these are
software and loopback results and do not qualify Windows, Android, a Pi, or a
physical camera.

The prerequisite unit/integration tests exercise real aiortc SDP negotiation
for H.264 preference and VP8-only fallback, RTX preservation, audio isolation,
truthful capability flags and session-rate diagnostics. They do not qualify
Pi encoding performance, real network conditions, native QGC WebRTC, or camera
passthrough. These remain explicit gates above.

References: [aiortc public APIs](https://aiortc.readthedocs.io/en/latest/api.html),
[aiortc sender implementation](https://github.com/aiortc/aiortc/blob/main/src/aiortc/rtcrtpsender.py),
[GStreamer WebRTC](https://gstreamer.freedesktop.org/documentation/webrtc/),
[GStreamer RTP jitterbuffer](https://gstreamer.freedesktop.org/documentation/rtpmanager/rtpjitterbuffer.html).

## Setup and update ownership

The existing optional GStreamer setup choice owns native-media dependencies.
`scripts/setup/reconcile-gstreamer-runtime.sh` is shared by the OpenCV builder
and setup/update reconciliation; `--verify-only` never installs anything and
`--dry-run` previews the work. Core/Full requirements do not import optional GI
or force a GStreamer build. Capture readiness and native-media readiness are
reported separately by `make check-gstreamer-runtime`.

Distribution packages supply WebRTC/ICE/DTLS/SRTP/SCTP and codec plugins.
`requirements-gstreamer.txt` pins PyGObject 3.50.0 and pycairo 1.27.0 in the
selected venv; system Python package directories are not exposed to it.
When the distro lacks `rtpgccbwe`, the reconciler builds only `gst-plugin-rtp`
0.13.7 at `cdec77cad2d9b7348d800507bc6eeec5039717eb`, using `cargo build --locked`
and two jobs. Its `.so` lives in `<venv>/lib/gstreamer-1.0`; the shared lazy
loader scans that directory for both capability probes and actual peers.
This path works independently of an interactive shell's environment.

The pinned plugin requires Rust >=1.71. An older distro toolchain, unavailable
Python development headers, package failure or plugin-load failure leaves the
advanced capability unavailable with diagnostics. Setup does not install a
floating rustup toolchain, modify the OS Python, rewrite capture settings or
break Core media to force WebRTC. Experts may supply a supported distro/runtime
and rerun the same reconciler. Raspberry Pi and Windows runtime installation
remain unqualified until their platform tests pass.

The receiver/sender negotiation must include the transport-wide feedback RTP
extension in the negotiated answer as well as on actual outgoing packets.
Merely loading `rtpgccbwe` and connecting its callback is insufficient: the
initial probe installed the controller but received no feedback. Correcting
the advertised sender caps produced 43/42 feedback events and 20/11 encoder
bitrate updates for H.264/VP8 in a five-second local run. This establishes the
feedback path, not the constrained-link operating envelope. The peer now
refuses an adaptive answer that omits the negotiated extension.

Optional setup uses the existing resource-lock supervisor and venv transaction
helpers. A failed Python/plugin installation restores the prior Python
environment; package-manager changes remain OS-managed. Verification and preview
perform no installation. Runtime setup never starts/restarts the application.
