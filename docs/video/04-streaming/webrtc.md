# WebRTC Video Streaming

> Peer-to-peer video with minimal latency

## Overview

WebRTC is the dashboard's preferred low-latency transport when it is enabled
and the browser can establish an ICE path. PixEagle uses `aiortc` for the
server peer, a WebSocket for signaling, and the shared latest frame from
`FramePublisher`. The browser reports video ready only after decoded media is
actually rendered.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     WebRTC Architecture                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Browser                    Server                               │
│  ───────                    ──────                               │
│                                                                  │
│  ┌─────────┐               ┌─────────────┐                      │
│  │ Client  │◀──WebSocket──▶│ FastAPI      │                     │
│  │ JS      │ /ws/webrtc_   │ exposure +   │                     │
│  │         │  signaling    │ auth guards  │                     │
│  └────┬────┘               └──────┬──────┘                      │
│       │                           │                             │
│       │                     ┌─────────┐                         │
│       │                     │ aiortc  │                         │
│       │    ┌────────────────┴──┐      │                         │
│       └────│  P2P Connection   │◀─────┘                         │
│            │  (STUN/TURN)      │                                 │
│            └───────────────────┘                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

```yaml
Streaming:
  WEBRTC_MAX_CONNECTIONS: 3
  WEBRTC_STUN_SERVER: "stun:stun.l.google.com:19302"
  WEBRTC_TURN_SERVER: ""
  WEBRTC_TURN_USERNAME: ""
  WEBRTC_TURN_CREDENTIAL: ""
```

PixEagle applies these ICE servers to the server-side `aiortc` peer. A TURN URL
must use `turn:` or `turns:`. Set both TURN credential fields or leave both
empty; a partial credential pair is rejected. The media-health API reports only
the server kind, URL, and whether credentials are configured. It never returns
the username or credential.

The dashboard reads its runtime transport and ICE settings from
`GET /api/v1/streams/client-config`. That authenticated, `no-store` response
is the single browser configuration source. It may include deployment-issued
TURN credentials for the authorized browser session; health endpoints and
logs remain redacted. Prefer short-lived TURN credentials in production.

## Signaling Endpoints

PixEagle currently uses one WebSocket signaling endpoint:

```
WEBSOCKET /ws/webrtc_signaling
```

The WebSocket Host/Origin policy and API authorization runtime run before
`accept()`. In the checked-in `local_compat` mode this requires a same-host
loopback socket client. In `machine_bearer` mode a browser cannot currently
attach the required `Authorization` header to the native WebSocket, so browser
WebRTC should use explicit `API_AUTH_MODE=browser_session` with the
credential-aware dashboard client. Production remote-browser setup should use
the guarded `production_remote` profile or an equivalent reviewed HTTPS/WSS
config; handoff still requires proxy/firewall evidence, credential handoff
evidence, adversarial auth/media tests, and safety evidence gates.

Client offer message:

```json
{
  "type": "offer",
  "payload": {
    "sdp": "<client SDP offer>",
    "type": "offer"
  }
}
```

Server answer message:

```json
{
  "type": "answer",
  "peer_id": "peer_...",
  "payload": {
    "sdp": "<server SDP answer>",
    "type": "answer"
  }
}
```

ICE candidates use the same WebSocket with `type: "ice-candidate"` and a
standard browser `RTCIceCandidate.toJSON()` payload.

PixEagle owns WebRTC peer lifetime through `WebRTCManager`. `FastAPIHandler`
constructs the manager and registers `WebRTCManager.signaling_handler`; the
manager owns pre-accept streaming, Host/Origin, authorization, and audit gates,
server-owned peer IDs, SDP/ICE handling, browser-session revocation, capacity
reservation, and bounded peer cleanup. A signaling socket cleanup removes and
closes that peer connection, and API server shutdown calls the manager-level
shutdown path to close all active peers before shared streaming resources are
released. The media-health route reports process-local peer counts only; it does
not prove that a remote WebRTC peer rendered usable video.

Browser support for `RTCPeerConnection`, successful signaling, and a configured
STUN server are not enough to prove WebRTC media is usable. The browser and
PixEagle host still need a working ICE path. Dashboard Auto mode now attempts
WebRTC for local and remote HTTP/IP lab pages when the runtime advertises it;
it falls back to WebSocket JPEG only after a bounded negotiation or decoded
frame failure. Manual WebRTC reports the failure instead of silently claiming
support. Do not broaden public firewall rules to random UDP ranges as a
shortcut.

Authentication and ICE reachability are separate boundaries. The anonymous
media lab flag applies only to MJPEG and WebSocket JPEG; it does not bypass
WebRTC signaling authorization or create a UDP path through a host firewall or
NAT. Lab WebRTC is available through the normal browser-session media
permission path, but HTTP/IP exposure is not a production security posture.

The dashboard does not treat signaling success or `ontrack` as proof of usable
video. It marks WebRTC ready only after the video element reports decoded frame
data. If no decoded frame arrives within 8 seconds, Auto mode falls back to
WebSocket and manual WebRTC shows a visible failure; receiving a track alone
does not cancel that deadline.

The dashboard does not hard-code a separate ICE list. Configuring
`WEBRTC_TURN_*` makes the validated server records available through the typed
client-config response as well as to the server peer. This is end-to-end
browser readiness only when the TURN service, credentials, firewall, and
expiry/rotation policy have been tested together.

## Implementation

### Server Integration

```python
from classes.webrtc_manager import WebRTCManager

webrtc_manager = WebRTCManager(
    frame_publisher=frame_publisher,
    exposure_policy=api_exposure_policy,
    api_auth_runtime=api_auth_runtime,
)

app.websocket("/ws/webrtc_signaling")(webrtc_manager.signaling_handler)
```

### Client (JavaScript)

```javascript
const pc = new RTCPeerConnection({
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
});
const ws = new WebSocket('ws://127.0.0.1:5077/ws/webrtc_signaling');
const videoElement = document.querySelector('video');

pc.addTransceiver('video', { direction: 'recvonly' });
pc.ontrack = (event) => {
  videoElement.srcObject = event.streams[0];
};
const pendingCandidates = [];
const sendOrQueueIceCandidate = (candidate) => {
  const message = JSON.stringify({
    type: 'ice-candidate',
    payload: candidate.toJSON(),
  });
  if (ws.readyState === WebSocket.OPEN) ws.send(message);
  else if (pendingCandidates.length < 64) pendingCandidates.push(message);
};
pc.onicecandidate = (event) => {
  if (event.candidate) {
    // Queue candidates until the signaling socket is OPEN.
    sendOrQueueIceCandidate(event.candidate);
  }
};

ws.onopen = async () => {
  pendingCandidates.splice(0).forEach((message) => ws.send(message));
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  ws.send(JSON.stringify({
    type: 'offer',
    payload: {
      sdp: offer.sdp,
      type: offer.type
    }
  }));
};

ws.onmessage = async (event) => {
  const message = JSON.parse(event.data);
  if (message.type === 'answer') {
    await pc.setRemoteDescription(new RTCSessionDescription(message.payload));
    while (pendingCandidates.length > 0) {
      await pc.addIceCandidate(pendingCandidates.shift());
    }
  } else if (message.type === 'ice-candidate' && message.payload) {
    const candidatePayload = message.payload.candidate || message.payload;
    const candidate = new RTCIceCandidate(candidatePayload);
    if (pc.remoteDescription) await pc.addIceCandidate(candidate);
    else pendingCandidates.push(candidate);
  }
};
```

## NAT Traversal

### STUN Server

For public networks, STUN helps discover public IP:

```python
ice_servers = [
    {"urls": "stun:stun.l.google.com:19302"},
    {"urls": "stun:stun1.l.google.com:19302"},
]
```

### TURN Server

For restrictive networks, TURN relays traffic:

```python
ice_servers = [
    {"urls": "stun:stun.l.google.com:19302"},
    {
        "urls": "turn:turn.example.com:3478",
        "username": "user",
        "credential": "password"
    }
]
```

Static examples explain the protocol only. Do not publish long-lived TURN
credentials in dashboard assets, API health responses, logs, or support
bundles. Prefer deployment-issued, time-limited credentials; the dashboard
currently consumes the selected browser ICE records through the authenticated
client-config route.

## Performance Tuning

### Bitrate and hardware guidance

WebRTC does not use the dashboard's JPEG quality slider. The browser and
`aiortc` negotiate the media codec and network behavior. For a constrained
companion computer, reduce the canonical `STREAM_WIDTH`, `STREAM_HEIGHT`, or
capture/detector workload and verify the resulting rendered FPS and frame age.
Use the maintained GStreamer H.264/RTP path when a hardware encoder and a GCS
receiver are required; do not add a second browser-side quality or codec
configuration surface.

## Troubleshooting

### Connection Failed

1. Check STUN/TURN servers are accessible
2. Verify firewall allows UDP traffic
3. Check browser console for ICE errors
4. On public HTTP/IP demos, use dashboard Auto mode. It tries WebRTC and
   visibly falls back to WebSocket if the ICE or decoded-frame check fails.

### No Video

1. Verify video track is being added
2. Check `ontrack` handler
3. Verify frame format is correct (RGB24)

### High Latency

1. Reduce resolution
2. Lower bitrate
3. Use hardware encoding
4. Check network conditions

### Browser Compatibility

```javascript
// Constructor support is necessary but not sufficient.
if (!window.RTCPeerConnection) {
    console.info('Use Auto/WebSocket on browsers without WebRTC support');
}
```
