# Streaming Performance

> Bounded frame delivery, encoding cache, and adaptive JPEG quality

PixEagle keeps capture/tracking work independent from each media consumer. A
`FramePublisher` exposes the newest stamped frame. HTTP MJPEG and WebSocket
clients encode from that publisher; WebRTC reads it through
`VideoStreamTrackCustom`; the optional GStreamer output has its own cadence and
OSD/encoder path.

## What prevents latency growth

- Every output skips duplicate frame IDs.
- WebSocket sends are cadence-limited and do not catch up in bursts after a
  slow encode or network write.
- The dashboard decodes one JPEG at a time and retains only one newest pending
  frame.
- WebRTC's track waits for a fresh publisher frame and emits monotonically
  increasing RTP timestamps.
- Encoded JPEGs are cached by `frame_id` and quality for the short lifetime of
  the configured cache.

This is a latest-frame policy, not a frame-replay policy. It keeps operator
views current when AI processing or a browser decoder is slower than the
camera.

## Configuration

```yaml
Streaming:
  ENABLE_FRAME_CACHE: true
  MAX_FRAME_CACHE_SIZE: 10
  STREAM_FPS: 20                 # output ceiling, 1..60
  STREAM_QUALITY: 80
  ENABLE_ADAPTIVE_QUALITY: true
  MIN_QUALITY: 30
  MAX_QUALITY: 85
  QUALITY_STEP_ADAPTIVE: 5
  QUALITY_COOLDOWN_SECONDS: 2.0
  TARGET_BANDWIDTH_LOW_KBPS: 50
  TARGET_BANDWIDTH_HIGH_KBPS: 200
```

`STREAM_FPS` limits output work; it cannot make an 8 FPS detector publish 20
fresh frames. The UI and media-health route should be read as:

| Measurement | Meaning |
|---|---|
| Latest frame age | Freshness of the shared publisher |
| Processing/source rate | How quickly capture and tracking produce fresh frames |
| Rendered FPS | How quickly the browser actually displays them |
| Transport bandwidth | Bytes delivered to the selected client |

## Adaptive quality direction

`AdaptiveQualityEngine` uses per-client EWMA estimates and a cooldown:

- estimated bandwidth above `TARGET_BANDWIDTH_HIGH_KBPS` requests lower JPEG
  quality;
- estimated bandwidth below `TARGET_BANDWIDTH_LOW_KBPS` permits higher quality;
- high encode time or CPU load requests lower quality;
- quality is bounded by `MIN_QUALITY` and `MAX_QUALITY`.

The thresholds are estimated encoded throughput in KiB/s, not a measured link
capacity. The engine is conservative: a negative signal wins over a positive
signal, and hysteresis prevents rapid oscillation. WebRTC does not use the JPEG
quality slider; its negotiated media path has its own encoder behavior.

## Practical tuning

For a CPU-only companion computer or SmartTracker workload, start with:

```yaml
Streaming:
  STREAM_WIDTH: 640
  STREAM_HEIGHT: 480
  STREAM_FPS: 15
  STREAM_QUALITY: 60
```

If the source and tracker can sustain it, raise `STREAM_FPS` to 20 or 30. If
the latest frame age rises while CPU is saturated, lowering output resolution
or AI inference frequency is more effective than increasing network buffers.
Do not add queues to hide stale frames.

## Diagnostics

Use the typed route:

```text
GET /api/v1/streams/media-health
```

It reports process-local frame freshness, transport state, drop ratio, and
redacted adaptive-quality state. It does not prove remote playback. In the
dashboard, enable the stream statistics overlay to compare rendered FPS,
bandwidth, and latency with that server-side view.

For a remote WebRTC path, inspect browser WebRTC statistics (inbound video
bytes, decoded frames, dropped frames, jitter, and RTT) separately from the
server's publisher rate. A smooth transport cannot create frames that the
detector never produced.

## Related paths

- [Video streaming overview](README.md)
- [WebSocket latest-frame contract](websocket.md)
- [WebRTC signaling and ICE](webrtc.md)
- [Streaming configuration reference](../06-configuration/streaming-config.md)
