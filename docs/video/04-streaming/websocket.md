# WebSocket Video Streaming

> Compatibility video transport for dashboards, QGC test builds, and native clients

## Contract

PixEagle exposes:

```text
WS /ws/video_feed
```

Each video frame is two ordered WebSocket messages:

1. JSON metadata with `type: "frame"`, `frame_id`, `timestamp`, `quality`, and
   `size`.
2. A binary JPEG payload.

The server reads the shared `FramePublisher`, skips duplicate frame IDs, limits
send cadence to `Streaming.STREAM_FPS`, and sends the newest available frame.
The dashboard has one active JPEG decode and one newest pending frame. It
replaces an older pending frame rather than allowing decode or network backlog
to turn into visible latency.

WebSocket is a compatibility fallback, not a replacement for WebRTC or the
GStreamer H.264/RTP path. Use dashboard `auto` to try WebRTC first and fall
back here after a bounded failure.

## Authorization and exposure

PixEagle validates Host/Origin and the media authorization policy before
accepting the socket. Browser-session clients need the `media:read` scope.
Same-host native clients may use the local compatibility boundary. Remote
operation requires the configured authenticated exposure profile; query-string
credentials are not supported.

The unsafe lab flag `ALLOW_UNAUTHENTICATED_MEDIA_STREAMING` applies only to the
legacy MJPEG and video WebSocket media paths. It does not open dashboard,
control, configuration, logs, or WebRTC signaling. Do not expose the backend
port directly to an untrusted network for production use.

Use the typed health resource for process-local diagnostics:

```text
GET /api/v1/streams/media-health
```

It reports connection and frame-publisher state; it does not prove that a
remote browser or QGC client rendered video.

## Configuration

```yaml
Streaming:
  ENABLE_STREAMING: true
  DEFAULT_PROTOCOL: auto
  STREAM_FPS: 20           # output ceiling, 1..60
  STREAM_QUALITY: 80       # JPEG quality
  WS_MAX_CONNECTIONS: 10
  WS_HEARTBEAT_INTERVAL: 30
  WS_STALE_TIMEOUT_MULTIPLIER: 2
```

`STREAM_FPS` is a ceiling. A camera, video file, tracker, or AI detector may
publish fewer fresh frames. The dashboard's displayed value is rendered FPS,
not a claim about detector throughput. For source/processing/rendering
diagnostics see the streaming media-health resource and runtime logs.

## Browser client outline

The dashboard uses `createLatestJpegFrameRenderer` in
`dashboard/src/services/latestJpegFrameRenderer.js`. A small native client
should follow the same policy: keep metadata paired with its following binary
frame, decode at most one frame at a time, replace the pending frame with the
newest one, and close decoded resources/object URLs.

```javascript
const ws = new WebSocket('ws://127.0.0.1:5077/ws/video_feed');
ws.binaryType = 'arraybuffer';

let pendingMetadata = null;
let activeDecode = false;
let newest = null;

ws.onmessage = (event) => {
  if (typeof event.data === 'string') {
    const message = JSON.parse(event.data);
    if (message.type === 'frame') pendingMetadata = message;
    return;
  }

  newest = { bytes: event.data, metadata: pendingMetadata };
  pendingMetadata = null;
  renderNewestWhenIdle();
};

async function renderNewestWhenIdle() {
  if (activeDecode || !newest) return;
  activeDecode = true;
  const frame = newest;
  newest = null;
  try {
    const bitmap = await createImageBitmap(new Blob([frame.bytes], {
      type: 'image/jpeg',
    }));
    // Draw bitmap to the canvas, then close it. Keep only the latest pending frame.
    bitmap.close();
  } finally {
    activeDecode = false;
    renderNewestWhenIdle();
  }
}
```

The outline omits authentication, canvas sizing, error handling, and cleanup.
Production clients should use the repository renderer or implement equivalent
bounded cleanup.

## Browser media configuration

The dashboard obtains transport availability and the current target FPS from:

```text
GET /api/v1/streams/client-config
```

This authenticated, `Cache-Control: no-store` response is the browser source
of truth. It is also where authorized browser clients receive validated ICE
records for WebRTC. Do not duplicate ICE or protocol settings in frontend
environment files.

## Client messages

The current server accepts only these client messages:

```json
{"type":"quality","quality":60}
```

```json
{"type":"ping","client_timestamp":1730000000000}
```

The first requests a bounded per-client JPEG quality. The second receives a
`pong` containing the echoed timestamp and is used for display latency. OSD,
resize, and source changes are server configuration; arbitrary `config`
messages are not part of this contract.

## QGroundControl

The draft/test QGC PR #13594 consumes complete binary JPEG messages and ignores
the JSON metadata messages. For a same-host test:

```text
ws://127.0.0.1:5077/ws/video_feed
```

For a remote companion, use an explicitly authenticated WSS/reverse-proxy
profile and the QGC build's supported credential fields. The maintained field
path remains GStreamer H.264/RTP/UDP because it avoids exposing PixEagle's
backend API port to the ground station. See [Remote Media Security](remote-media-security.md)
and [QGC HTTP/WebSocket Source Plan](qgc-http-websocket-source-plan.md).

## Troubleshooting

### Connection refused or unauthorized

1. Confirm `ENABLE_STREAMING` and `WS_MAX_CONNECTIONS` are non-zero.
2. Confirm the URL host/port matches the browser page and configured bind.
3. Check the Host/Origin and `media:read` policy.
4. Inspect `GET /api/v1/streams/media-health` and the runtime log.

### Video is delayed or choppy

1. Prefer dashboard Auto/WebRTC.
2. Check rendered FPS versus the latest frame age.
3. Reduce `STREAM_WIDTH`, `STREAM_HEIGHT`, or JPEG quality.
4. Reduce AI/tracker processing load or use a GStreamer/hardware path.
5. Do not add an unbounded client decode queue; render the newest frame.

### Cleanup

Close the socket and release all decoder resources when the client is stopped.
The PixEagle server heartbeat removes stale clients and unregisters their frame
publisher/quality state exactly once.
