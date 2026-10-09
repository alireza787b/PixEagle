# Streaming Performance

> Measured delivery feedback, bounded JPEG output, and preserved source detail

A `FramePublisher` exposes immutable source/stream identities and the newest
published pixels. HTTP MJPEG, WebSocket JPEG, and WebRTC consume this shared
publisher; optional GStreamer output has its own encoder and delivery settings.
Changing transport cannot restore detail already lost at capture or resize.

## Bounded delivery and caching

- Each sender samples the newest frame and skips an already delivered source
  frame, including when its delivery copy has different dimensions.
- Cadence runs from the start of the frame cycle. Encoding, pacing, and writing
  consume that interval instead of adding another full interval afterward.
- Negotiated WebSocket ACKs permit one frame in flight. The ACK timeout retires
  a stalled connection; it does not release credit to enqueue another old frame.
- The browser decodes one JPEG at a time and retains one newest pending frame.
- JPEG encoding is shared for concurrent requests with the same source/stream
  epoch, frame ID, variant, dimensions, and quality. The cache is bounded by
  `MAX_FRAME_CACHE_SIZE`; it has no time-to-live eviction. Disabling
  `ENABLE_FRAME_CACHE` disables completed-result reuse, while bounded result
  records still provide encoder service-time measurements.
- WebRTC reads fresh publisher frames with monotonic RTP timestamps. Its codec
  and congestion control are separate from the JPEG policy below.

## Configuration

```yaml
Streaming:
  STREAM_PROFILE: automatic
  STREAM_MAX_BITRATE_KBPS: 8000   # Aggregate JPEG payload budget, decimal kbps
  STREAM_FPS: 20                 # Configured ceiling, 1..60
  STREAM_QUALITY: 50             # Initial JPEG quality, bounded by the profile
  ENABLE_ADAPTIVE_QUALITY: true
  MIN_QUALITY: 30
  MAX_QUALITY: 85
  QUALITY_STEP_ADAPTIVE: 5
  QUALITY_COOLDOWN_SECONDS: 2.0
  WS_FRAME_ACK_TIMEOUT_SECONDS: 2.0
  ENABLE_FRAME_CACHE: true
  MAX_FRAME_CACHE_SIZE: 10
```

`STREAM_PROFILE` and the aggregate budget are canonical Streaming settings and
require a process restart. They do not introduce a separate client settings
store. `STREAM_FPS` cannot make an 8 FPS source/tracker publish 20 fresh frames.

## Measured per-client policy

The JPEG engine adapts from completed writes, matched ACK durations when
available, encoder service time, and optional receiver rendering delay/drop
feedback. It tracks actual bytes over observed delivery intervals. Neither
JPEG size multiplied by configured FPS nor measured traffic volume is a link
capacity estimate. Large detailed frames alone do not trigger lower quality.
Global CPU load is diagnostic and cannot reduce another client's policy.

| Measurement | Meaning |
|---|---|
| Send time | Completion time of the server's ASGI write; buffering may precede remote receipt |
| ACK time | Send start to the matching ACK, including transport and the peer's ACK behavior |
| Encoder time | Actual JPEG encoding service time; executor wait is excluded |
| Budget wait | Local aggregate JPEG pacing delay; not measured network congestion |
| Presentation delay | Optional receiver-reported rendering work/delay; absent when unreported |
| Measured byte rate | Completed JPEG traffic over observed intervals, not available capacity |
| Published frame age | Freshness of publisher pixels, separate from transport feedback age |

HTTP has write-completion feedback only. Native QGC acknowledges admission to
its bounded decoder pipeline; that ACK does not prove presentation. The browser
can report rendering delay and dropped frames with its ACK. These measurements
are not a synchronized capture-to-screen latency measurement. Legacy
`report_frame_sent` callers without measured delivery feedback retain their
requested quality and provide diagnostics only.

Successful writes also report their aggregate-budget wait. A fast LAN cannot
make an oversized JPEG fit a configured 8 Mbps ceiling: local pacing must
participate in policy decisions instead of appearing as healthy delivery.
Sustained budget pressure reduces negotiated spatial size first, then quality,
then FPS. Recovery restores cadence first and checks the estimated cost of a
larger image before increasing resolution, avoiding repeated oversized upscales.

Sustained delivery, encoding, or rendering pressure normally reduces FPS first,
then negotiated spatial size, then JPEG quality. Three pressure samples and the
configured cooldown are required. Recovery requires eight healthy samples and
twice the cooldown, restoring quality, spatial size, then FPS. Isolated jitter
and feedback separated by an outage do not accumulate into sustained pressure.

| Profile | FPS ceiling | Spatial choices relative to published pixels | Quality floor with the example settings above |
|---|---|---|---|
| `automatic` | `STREAM_FPS` | 1, 0.75, 0.5, 0.25 | 50 |
| `high_quality` | `STREAM_FPS` | 1, 0.75 | 70 |
| `low_bandwidth` | Smaller of `STREAM_FPS` and 10 | 0.75, 0.5, 0.25 | 45 |

All quality limits obey `MIN_QUALITY`/`MAX_QUALITY`. Automatic's floor is the
smaller of configured initial quality and 55; low bandwidth's is the smaller
of initial quality and 45, then clamped to those global limits. High quality's
floor is 70, likewise clamped. Low bandwidth caps quality at 65 unless the
configured minimum requires more; the other profiles use `MAX_QUALITY`.
WebSocket dimensions change only after the client negotiates support. Fixed-size
clients retain scale 1 and adapt FPS/quality instead. Source pixels, analysis
geometry, and selection provenance remain separate from per-client copies.

## Aggregate JPEG budget and hard limits

`STREAM_MAX_BITRATE_KBPS` applies across HTTP and WebSocket JPEG clients. It
counts JPEG payload bytes in decimal kilobits per second; it does not cap
WebRTC, GStreamer output, transport overhead, or other process/network traffic.
Leave link capacity for control traffic and those other uses explicitly.

The shared scheduler reserves at most 250 ms of JPEG serialization time. Each
sender holds at most one pending payload; exhausted reservations drop work and
sample again. An individual JPEG exceeding that horizon immediately steps down
spatial size, then quality within its profile. Lowering FPS cannot make one
oversized JPEG fit. Fixed-size clients skip spatial changes.

At 0.5 Mbps the largest admissible JPEG is 15,625 bytes. Some scenes still exceed
that size at the smallest permitted image and quality. The engine then reports
`unavailable_at_configured_limits` instead of breaking the quality floor or
building a queue. A high-quality profile can reach this limit earlier because
it preserves at least 0.75 spatial scale. A low-bandwidth preset is therefore
not a promise that every scene works at a given cellular bitrate.

The budget remains enforced when adaptation is disabled. In that case oversized
frames are dropped until the configured payload or budget changes.

## Source detail and preprocessing

Capture feeds separate analysis and display paths. Tracking preprocessing can
blur or enhance the analysis copy; display/recording pixels start from the
unfiltered capture image. Tracker overlays are mapped into display coordinates.
Delivery resize preserves the complete source aspect ratio without cropping or
upscaling, and shrinks with area interpolation.

`VideoSource.NATIVE_CAPTURE_RESOLUTION` can preserve the source's native capture
dimensions while analysis uses its configured size. Select a source/capture
resolution containing the needed detail before raising delivery bounds. Native
file/RTSP sources can exceed the delivery bounds, so their capture/display memory
and processing costs still need measurement. Configuration examples here do not
qualify Raspberry Pi, Jetson, Windows, or field performance.

## Diagnostics and retained settings

`GET /api/v1/streams/media-health` reports publisher freshness, transport state,
and per-client policy/feedback. `feedback_age_ms`, `feedback_stale`, and
`feedback_available` distinguish old measurements from current evidence.
`budget_wait_ms` distinguishes local payload-budget pacing from ACK/write delays.
Delivery feedback expires after the larger of five seconds or three cooldown
periods. Retained counters do not prove that video is still arriving.

`TARGET_BANDWIDTH_LOW_KBPS`, `TARGET_BANDWIDTH_HIGH_KBPS`,
`CPU_THRESHOLD_HIGH`, `CPU_THRESHOLD_LOW`, and `CACHE_TTL_MS` remain accepted in
existing configurations for compatibility. They have no effect on JPEG
adaptation or cache eviction. They are not alternative tuning controls for the
measured policy or aggregate budget.

Compare actual rendered FPS, drops, source age, write/ACK time, and selected
policy on representative scenes. Use WebRTC's own bytes, decoded/dropped frames,
jitter and RTT statistics when that transport is active. Local deterministic
tests, including shaped-budget fixtures, do not establish physical cellular or
target-hardware performance.

## Related paths

- [Video streaming overview](README.md)
- [WebSocket latest-frame contract](websocket.md)
- [WebRTC signaling and ICE](webrtc.md)
- [Streaming configuration reference](../06-configuration/streaming-config.md)
