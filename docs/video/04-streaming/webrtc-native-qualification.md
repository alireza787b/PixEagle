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

## Encoded workload policy and delayed selection

Native GCC still owns bitrate estimation and packet pacing. The shared
`AdaptiveQualityEngine` now also accepts actual payloader-completion feedback
for compressed video. It applies the existing Automatic/High quality/Low
bandwidth profile bounds, startup scale/FPS and cooldown; it does not synthesize
JPEG ACKs or claim client presentation. Each peer keeps independent state.

The initial compressed workload heuristic reduces spatial detail when the
controller's target falls below 0.07 bits per pixel per submitted frame, or
when submission-to-payloader time exceeds the frame's service budget.
Sustained recovery requires more than 0.14 bits per pixel for the candidate
size/cadence and twice the configured cooldown. These separated policy
thresholds are conservative workload heuristics, not quality guarantees or a
second network estimator. Pipeline time includes queueing; it is distinct from
encoder-only service time. Profile FPS, resolution and aggregate bitrate limits
remain canonical. No new installation prompt or transport setting is added.

The existing authenticated `frame-challenge` payload accepts optional typed
`presentation` feedback (version 1). QGC reports cumulative verified receipts
and distinct frames confirmed by the Qt rendering surface's `frameSwapped`,
with a media-store epoch, client-local elapsed time and conservative frame-age
bounds. Admission, decode and repeated paint notifications are not counted as
new presentations. Immutable receipts survive bounded context-cache eviction;
old epochs cannot contribute. These observations are QoS evidence, never
selection or aircraft authority. Invalid optional feedback does not invalidate
the separate age-bound challenge.

The policy uses full one-second windows and sustained renderer pressure to
reduce cadence before sacrificing image detail. Upward workload adaptation
requires fresh, healthy presentation evidence as well as encoder headroom.
Reordered/regressed feedback, a different epoch or a disconnected renderer
cannot refresh that evidence. Rates use differences on one client clock;
age bounds are not true sensor-to-screen latency measurements.

`VideoDeliveryBudget` is shared by native encoder admission and HTTP/WebSocket
JPEG pacing. Each native encoder holds its configured maximum target until
teardown actually finishes, including delayed cleanup. Admission drains prior
bounded JPEG reservations before media starts; cancellation releases admission.
The manager divides the configured payload budget among its maximum native
peer count plus one share for JPEG fallback. GCC may use less than a reserved
ceiling. This conservative allocation is not measured link capacity or a
wire-rate guarantee: RTP/RTCP overhead and retransmissions are additional.
The transitional aiortc browser sender does not expose a supported encoder
ceiling API and is **not** covered by this allocation yet. Aggregate parity
remains a rollout gate; do not claim all browser/native traffic is bounded
until browser provider migration is qualified.

The existing media-health response includes these reservations and optional
peer-local encoder/presentation observations under the WebRTC transport's
`details.delivery`. It explicitly counts browser peers outside the allocation;
it does not turn sender rates into measured network capacity or presentation.

The loopback native integration fixture also supports explicit `normal`,
`reject`, `missing_metadata` and `wrong_dimensions` qualification modes. They reuse production
session authentication and both transport implementations without an aircraft
command path. QGC's controller test verifies automatic native choice, JPEG
fallback after refusal or absent exact metadata, fresh selection geometry and
explicit Stop without replay/retry. This fixture admission never changes the
product capability gate. See the matching QGC network checkpoint for commands.

Caps changes preserve publisher frame identity and retained analysis geometry.
QGC must reject decoded buffers whose dimensions differ from their associated
metadata, including concealment after a missing resize keyframe. Corrupted
output cannot receive selection provenance. Missing context remains
noninteractive and must trigger the existing recovery/fallback path if it
persists.

RTP is not paced by a per-frame JPEG ACK. Its delivered-selection retention now
covers the existing selection-age window (plus two in-flight frames), bounded
by the publisher's existing frame and shared byte limits. JPEG retains its
three-frame policy. Retention never increases the allowed selection age or
substitutes newer pixels for an expired token. Source changes and peer close
still retire the retained context. Measured constrained-link and platform
evidence remains required before enabling the product capability.

## Prediction-reference integrity and encoder buffering

The native QGC receiver now requires continuous RTP access units and a clean
sync frame before attaching selection provenance. Packet loss invalidates the
prediction reference even when the decoder does not flag concealed pixels.
Missing fragments in a sync frame cannot restore it. A metadata/decoded-size
mismatch is a named `decoded_geometry` failure that invokes automatic JPEG
fallback; exact association never authorizes a differently sized image.

The provider follows the pinned GStreamer webrtcsink encoder recipe for short
rate-control buffers: x264 VBV 120 ms; VP8 CBR initial/optimal/maximum buffers
100/120/150 ms and maximum intra bitrate 250%. VP8 uses 15-bit RTP picture IDs.
The framework's default 200 ms WebRTC jitter latency is retained. These do not
extend provenance freshness or selection deadlines. See the
[upstream encoder recipe](https://raw.githubusercontent.com/GStreamer/gst-plugins-rs/0.13.7/net/webrtc/src/webrtcsink/imp.rs).
H.264 aggregation remains at its compatible default: an aggregation experiment
failed exact access-unit association and was reverted.

Client-local presentation elapsed times accept long-running sessions through
the JSON exact-integer range. A one-week validation ceiling would incorrectly
discard healthy QoS feedback after seven days; it is not a media-age bound.

`delivery_policy.fps` remains the requested ceiling. The optional
`associated_encoded_fps` measures completed, associated access units over
one-second monotonic windows, and becomes unavailable after three seconds
without fresh encoder feedback. Startup, long gaps and profile changes discard
the old measurement. Spatial bitrate pressure uses observed cadence once it
is available, so slow analysis does not count nonexistent frames. Pipeline
overload still compares against the requested cadence; completing fewer frames
cannot hide encoder queueing. Neither quantity claims receiver presentation.

The latest recorded 10 Mbps loss probe passed both codecs with strict displayed
barcode identity. A synthetic 1 Mbps wrong-dimension test passed automatic JPEG
fallback. Linux VA-API VP8 still reports caps-ordering warnings; sustained weak
link quality and clean platform packages remain unqualified. No deployment
capability, configuration, service or field gains changed.

## Isolated recorded-video Pi checkpoint

`tools/native_replay_demo.py prepare --experimental-native-webrtc` explicitly
admits the candidate sender only in a private recorded-video snapshot. It pins
the worker/source hashes and keeps loopback authentication, camera control off,
MAVLink off, the circuit breaker on and command preview. The child checks the
validated snapshot and optional runtime before admitting native capability.
Ordinary configuration, service launch and normal replay retain their existing
capability gate. This is a developer qualification tool, not an operator setup
switch or a released transport guarantee.

Use a separate copied environment and preserve the installed field profile:

```bash
python tools/native_replay_demo.py prepare --directory /private/new/replay \
  --video test11.mp4 --role operator --port 8093 --experimental-native-webrtc
python tools/native_replay_demo.py run --directory /private/new/replay
```

The process binds loopback. For a remote Pi, forward only its authenticated
test API/signaling port and retain direct ICE media reachability between the
test computers. SSH forwarding is TCP signaling/JPEG, not an RTP tunnel or a
measurement of the datalink. Use normal replay without the flag first to
verify compatibility without optional GI. Keep credentials private. A final
deployment still uses the normal updater after acceptance; an experimental
snapshot must never replace the installed service or enable aircraft commands.

### Adaptive cadence and encoder caps

The native sender keeps its configured maximum FPS as the nominal raw-video
caps rate. Automatic delivery cadence is carried by each buffer's monotonic PTS
and duration; a 12-to-13 FPS policy step does not renegotiate the encoder/parser.
Delivery dimension changes still update caps. Requested policy FPS, completed
encoded FPS and actual receiver presentations remain distinct diagnostics.

The cadence regression exercises rate increases/decreases, a spatial resize,
monotonic timestamps, buffer durations and retained per-frame requested rates.
Its pre-repair version demonstrated an extra caps update for a cadence-only
step. Focused optional-media tests pass after the change. This does not yet
qualify datalink quality, remove the product native gate or justify overriding
the framework's congestion estimate. The observed Pi pixelation remains an
operator acceptance issue until the complete path is retested.

### Explicit read-only camera-source bench

The same isolated harness can import RTSP capture settings from an existing
profile. This is a developer qualification command, not an installation step:

```bash
python tools/native_replay_demo.py prepare \
  --directory /private/new-camera-bench --port 8197 --role operator \
  --rtsp-config /path/to/configs/config.yaml --experimental-native-webrtc
```

Preparation never starts the camera. Run through the same duration/temperature
guard as the recorded bench. Only the RTSP URI, transport, latency, keepalive,
RTCP, capture-runtime flag and allowlisted streaming quality limits are imported.
The source profile is never saved or modified. The snapshot keeps its own analysis defaults, accounts,
loopback authentication, disabled MAVLink, command preview, circuit breaker,
and disabled gimbal tracking/control. It is a camera-video/local-tracker test,
not acceptance of camera-owned tracking or aircraft following.

The private manifest pins the imported source settings and copied code. Treat
the entire directory as sensitive because its private configuration/manifest
can contain a camera URI with credentials. Unsupported URI schemes, arbitrary
pipelines and deployment control settings are not imported. Changing the
snapshot or command inhibits is rejected before startup. Ordinary recorded
bench commands and the native product capability gate remain unchanged.

Camera benches can reuse the source profile's canonical `Streaming` quality
settings (profile, dimensions, cadence/startup, JPEG quality bounds, payload
allocation, peer count, cooldown and encoder threshold). The manifest pins
these values, and `ConfigService` validates the complete inhibited configuration
against the copied schema. Authentication, bind/exposure, credentials, flight,
camera-control and arbitrary pipeline settings are never imported through this
quality path. No new runtime settings store or tuning API is introduced.

For adaptation ceilings, algorithm thresholds, shared bitrate allocation and
network troubleshooting, use the canonical
[streaming performance guide](streaming-optimizer.md#native-encoded-video-tuning).

### Explicit 1080p comparison

Native qualification can raise `Streaming.STREAM_WIDTH/STREAM_HEIGHT` to
1920/1080 through the existing configuration. The sender uses those canonical
bounds, capped at 1920×1080, with the same provenance/age checks. Factory and
accepted custom profiles remain 720p. No independent native resolution setting
or client-specific store exists. Keeping FPS and bitrate allocation constant
is the first comparison; a larger source does not guarantee more useful detail
at the same compression budget. Record effective dimensions rather than calling
a configured ceiling the received resolution.

H.264 negotiation checks receiver frame-size and macroblock-rate limits before
choosing the codec, and constrains the encoder to the compatible level. A
level-3.1-only receiver is not offered 1080p H.264; VP8 can be selected when
available, otherwise negotiation fails into the established fallback. The
development QGC software-decoder offer supports up to level 4.2. This does not
qualify hardware decoders or packaged Windows/Android runtimes. The independent
1080p encrypted pixel fixture uses 4 Mbps; its intermittent luminance failure
at 1 Mbps remains recorded as a low-budget quality/integrity qualification gap,
not a reason to loosen pixel-identity checks.

Evaluate paired scenes for small-target visibility, motion blur/compression,
fresh presented FPS, frame-age bounds/gaps, encoder time, bitrate, loss and
Pi CPU/temperature. A static indoor camera check cannot qualify aerial ground
sampling distance, identification range, moving-target detection probability
or pilot workload. Those require representative optics, altitude, motion,
target sizes and field/operator evidence. Capture receipt age is not full
camera-to-screen latency. Do not retune aircraft gains from a video experiment.

### Manual workload and low-budget diagnostics

The canonical `ENABLE_ADAPTIVE_QUALITY` flag now also controls native spatial
and cadence adaptation. Off retains configured dimensions/FPS (no startup
reduction), while mandatory GCC continues to control encoded bitrate. Pressure
and measurements remain distinct from workload authority. The encrypted
H.264 fixture verifies actual TWCC feedback with this flag off, not just a
mocked policy. There is no duplicate QGC saved setting. JPEG budget refusal,
frame freshness/provenance and unsupported-codec fallback remain active.

The private forced-1080p diagnostic retained the original failing pixel gate:
two 1 Mbps runs showed whole-frame luminance errors, not only a corner-pixel
outlier (maximum median errors 32 and 52). The 2/4 Mbps comparison runs kept
median errors within 3. These are synthetic uniform-frame measurements, not
visual-quality scores or evidence that metadata association is necessarily the
cause. Decoder/reference damage and bitrate starvation remain to be separated.
Do not weaken selection checks, force a high bitrate floor or count a diagnostic
that bypassed a failing assertion as acceptance. This forced-size test is not
the same as Automatic, which may reduce the workload under that budget.

A separate five-second encrypted loopback with a 1 Mbps encoder ceiling,
1080p source and Automatic startup at 0.75/10 FPS passed the original pixel
and RTP checks at 1440×810 with actual TWCC feedback. No renderer feedback was
provided, so it could not authorize a quality increase. This validates the
conservative startup case, not a shaped 1 Mbps radio path, sustained recovery,
QGC presentation or resolution optimality. The forced-size failure remains
separately recorded.
