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

The remaining implementation sequence is: add the GStreamer provider under
the existing authenticated signaling/session lifecycle; transmit these bounded
associations on its authenticated peer channel; retain exact RTP-to-decoded-PTS
identity in QGC; bind context to the frame actually presented; then qualify
congestion control, restart/revocation and platform packaging. Avoid enabling
native interactive video before the complete identity chain passes. The
existing JPEG path remains the default and fallback during this work.

The prerequisite unit/integration tests exercise real aiortc SDP negotiation
for H.264 preference and VP8-only fallback, RTX preservation, audio isolation,
truthful capability flags and session-rate diagnostics. They do not qualify
Pi encoding performance, real network conditions, native QGC WebRTC, or camera
passthrough. These remain explicit gates above.

References: [aiortc public APIs](https://aiortc.readthedocs.io/en/latest/api.html),
[aiortc sender implementation](https://github.com/aiortc/aiortc/blob/main/src/aiortc/rtcrtpsender.py),
[GStreamer WebRTC](https://gstreamer.freedesktop.org/documentation/webrtc/),
[GStreamer RTP jitterbuffer](https://gstreamer.freedesktop.org/documentation/rtpmanager/rtpjitterbuffer.html).
