# Native JPEG frame provenance — slice 2

The authenticated `/ws/video_feed` route remains the existing JSON-then-binary
JPEG protocol. This slice adds `provenance` to each frame JSON; existing fields,
integer acknowledgement IDs, browser sessions, bearer scopes, Host/Origin
checks, logout/expiry revocation, and query-credential rejection remain intact.
It adds no media-control, target-selection, or flight-action route.

`GET /api/v1/integration/context` advertises `video.frame_provenance.v1` when
streaming is enabled and the publisher is available. Its additive `video`
fields are `provenance_version: "1"`, `ws_path: "/ws/video_feed"`, opaque
`stream_id`, `stream_epoch`, `source_epoch`, nullable `width`, `height`, and
`variant`, `capture_state`, and `geometry_verified: false`. `ws_path` is a
constant server-relative path without credentials/query; native clients must
preserve their configured proxy prefix. Context capture state is `unknown`
when pixels exist, otherwise `unavailable`: a GET is not a capture observation.
Only frame metadata contains measured ages. Disabled streaming does not
advertise the capability or WS path.

Example metadata (opaque IDs abbreviated for readability):

```json
{
  "type": "frame",
  "timestamp": 1790000000.0,
  "quality": 80,
  "size": 20480,
  "frame_id": 42,
  "frame_age_ms": 8.0,
  "delivery_token": "client-challenge-000042",
  "provenance": {
    "version": "1",
    "instance_id": "companion-a",
    "runtime_id": "runtime-uuid",
    "stream_id": "publisher-uuid",
    "stream_epoch": "stream-epoch-uuid",
    "source_epoch": "source-epoch-uuid",
    "frame_id": "42",
    "capture_id": "39",
    "capture_state": "cached",
    "capture_age_ms": 1250.0,
    "publication_age_ms": 8.0,
    "encoded_width": 640,
    "encoded_height": 360,
    "variant": "processed_osd",
    "geometry_verified": false
  }
}
```

The immediately following binary message is the JPEG described by this object.
`APIFrameProvenance` is strict: version `"1"`, positive canonical decimal string
IDs, positive integer dimensions, finite nonnegative ages, known enums, and
no unknown fields. Unknown capture ID/time/source is explicitly null and state
`unknown` or `unavailable`. A native client must validate the supported version,
context runtime/instance binding, decoded dimensions, and pair ordering before
presenting trusted provenance. The compatibility integer `frame_id` remains the
ACK key; the nested decimal string preserves identity without float rounding.

## Pixels, generations, and age

The publisher owns a read-only pixel copy and immutable capture metadata.
Publication time and frame ID are assigned with the pixel reference swap.
Publication IDs remain increasing during a publisher lifetime, including resets.
Encoding caches include publisher/stream epoch, frame ID, output variant, and
JPEG quality. Metadata quality is the quality actually encoded, before any
next-frame adaptive adjustment.

Source open/reopen/release invalidates prior publisher pixels even when the
replacement fails. Captures finishing after retirement cannot restore old
pixels. Source epochs are opaque; source URLs and camera credentials are never
exposed. Recorded-file loops keep the cached boundary frame's old identity and
advance source epoch at the first new capture. Size or variant changes advance
the stream epoch. Missing raw/OSD variants are removed rather than inherited
from a previous publication. Async encoding rechecks the stream generation
after encode and again after taking the send lock.

`capture_age_ms` measures monotonic backend capture receipt through transmission,
including processing and cached-frame residence. Async readers preserve their
reader timestamp; prefetched file frames preserve probe time. This is not
sensor exposure time. Reusing cached pixels retains the original capture ID and
time even if a new OSD is published. `publication_age_ms` measures only time
since the current output was published. Ages are refreshed immediately before
metadata send. Client time after receipt must be added to both ages. A state of
`fresh` describes how the capture was obtained; age still determines whether it
is currently stale. No clock synchronization with the ground station is assumed.

The dimensions are exact encoded output dimensions. `geometry_verified: false`
means crop/orientation/calibration, source-to-aircraft geometry, and target
coordinate mapping are not established. Reliable frame identity and JPEG size
do not authorize clicking or following.

## Bounded native delivery challenge

Network buffering can delay an otherwise young-looking frame. Native clients
can send an opaque 16–128 character ASCII `[A-Za-z0-9_-]` `delivery_token` with
`stream_capabilities` and each `frame_ack`:

```json
{"type":"stream_capabilities","latest_frame_ack":true,"delivery_token":"client-challenge-000041"}
{"type":"frame_ack","frame_id":42,"delivery_token":"client-challenge-000042"}
```

The server echoes the latest accepted token at the top level of the next frame
metadata. Only the exact outstanding integer ACK can update that token; invalid
or old ACKs cannot rotate it. Disabling ACK clears it, and a new socket starts
without it. Invalid token values are ignored without changing legacy ACK
semantics. It is correlation data, not authentication or a secret.

The client records the monotonic time it sends a token and requires the expected
echo before trusting a frame. Adding token-send-to-metadata-receipt elapsed time
to server ages is a conservative transit bound: the frame metadata must have
been sent after the server received that token. Add subsequent local elapsed
time as well. Tokenless pre-negotiation pairs may be validated/ACKed and discarded;
once echo negotiation succeeds, missing/mismatched echoes invalidate native
presentation. Old clients that send no token receive no echo and remain compatible.

One send lock keeps pong messages out of frame JSON/JPEG pairs. Any failed or
cancelled pair clears outstanding ACK state and closes the socket (1011), rather
than waiting for an ACK to a partial pair or retrying into ambiguous framing.
A source reset can occur after transmission begins; already transmitted bytes
retain their original generation and cannot be relabelled as the replacement.

## Read-only status

Context also advertises `status.tracker_runtime.v1` for existing authenticated
`GET /api/v1/tracking/runtime-status` (`telemetry:read`). It reports authoritative
process-local tracking/following state and readiness. It has no frame join ID;
clients must not overlay separately polled tracker coordinates on a JPEG as if
synchronized. Poll status separately, expire it independently, and preserve the
existing following-disabled native-client boundary.

## Camera-free validation fixture

`tools/native_integration_fixture.py` now uses the production publisher, JPEG
encoder, WS route, authentication/session middleware, context, and read-only
tracker route around synthetic aircraft/camera observations. It binds only
`127.0.0.1`; it creates no real camera, tracker, MAVSDK, flight runtime, user file,
service, or deployment. Its viewer credentials are the existing test-only
`operator` / `fixture-only`.

```bash
.venv/bin/python tools/native_integration_fixture.py \
  --port 8091 --system-id 1 --uid 18446744073709551001 \
  --instance-id fixture-one --media-control-file /tmp/pixeagle-fixture-one.json
```

For the first video/status demo without PX4 or a QGC mock vehicle:

```bash
.venv/bin/python tools/native_integration_fixture.py \
  --port 8093 --instance-id fixture-no-aircraft --no-aircraft \
  --media-control-file /tmp/pixeagle-fixture-no-aircraft.json
```

This mode labels its synthetic video `NO AIRCRAFT`. Both command and telemetry
stay disconnected with unknown identities, including after observational
verification. Authenticated video and read-only tracker status continue; no
connection or control operation is available. Aircraft identity/freshness
arguments cannot be combined with `--no-aircraft`. A client may present these
pixels as a companion preview; it must not claim verified aircraft association.
The fixture proves that the production API/media paths work without aircraft
state, not that a real camera or deployed PixEagle runtime has been qualified.

Atomically replace the local control file with an object. Defaults:

```json
{"mode":"live","source":"camera-a","reset":"0","width":640,"height":360,"variant":"processed_osd"}
```

`freeze` republishes cached pixels with the same capture ID/time; `drop` stops
publication. Changing `source` creates a new source epoch and restarts synthetic
capture numbering. Changing `reset` retires the publication epoch. Size and
variant changes retire the previous output. Invalid/partial controls stop
publication until repaired; unknown fields are rejected. No HTTP fixture-control
or production-control route was added.

Visible `FRAME N` equals `provenance.capture_id`. The same unsigned value is
encoded in 64 high-contrast cells: 8×8 grid, 12-pixel cells, top-left (16,16),
little-endian bit order by row, white=1 and black=0. JPEG-safe sample centers are
`(22 + 12*(bit%8), 22 + 12*(bit//8))`. This supports image-to-metadata comparison;
it does not establish actual camera, tracker, aircraft, or deployment behavior.

For a separate **real Core replay**, `tools/native_replay_demo.py` prepares a
private source/config snapshot with the bundled recorded video and viewer
authentication. Its `run` action executes actual `src/main.py`, preserving the
normal capture/tracker/OSD/API paths while keeping PX4 and sidecars unavailable.
Preparation and execution are separate; see the
[prepared replay checkpoint](../reporting/agent-ops/codex-modernization/checkpoints/2026-09-21-qgc-native-video.md#prepared-real-core-replay)
for commands, isolation, credentials and validation limits.
