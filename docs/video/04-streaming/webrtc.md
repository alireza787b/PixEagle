# WebRTC Video Streaming

> Peer-to-peer video with minimal latency

## Overview

WebRTC provides the lowest latency streaming option, using peer-to-peer connections with H.264 compression. PixEagle uses the `aiortc` library for Python WebRTC support.

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

Browser support for `RTCPeerConnection` is not enough to prove WebRTC media is
usable. WebRTC video also needs a working ICE path between the browser and the
PixEagle host. For the temporary public HTTP/IP demo, PixEagle dashboard Auto
mode intentionally selects WebSocket JPEG and shows that reason in the video
panel. Manual WebRTC remains an explicit lab attempt and reports negotiation
failure instead of silently claiming support. Do not broaden public firewall
rules to random UDP ranges as a shortcut for production readiness.

The dashboard does not treat signaling success or `ontrack` as proof of usable
video. It marks WebRTC ready only after the video element reports decoded frame
data. If no decoded frame arrives within 15 seconds, Auto mode falls back to
WebSocket and manual WebRTC shows a visible failure; receiving a track alone
does not cancel that deadline.

The checked-in dashboard currently has a browser-side STUN configuration but
does not ingest static TURN secrets from the backend. Production networks that
require browser relay need a separately reviewed, short-lived TURN credential
delivery design. Configuring `WEBRTC_TURN_*` today configures the PixEagle
server peer; it is not by itself end-to-end browser TURN readiness.

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

pc.addTransceiver('video', { direction: 'recvonly' });
pc.ontrack = (event) => {
  videoElement.srcObject = event.streams[0];
};
pc.onicecandidate = (event) => {
  if (event.candidate && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'ice-candidate',
      payload: event.candidate.toJSON()
    }));
  }
};

ws.onopen = async () => {
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
  } else if (message.type === 'ice-candidate' && message.payload) {
    await pc.addIceCandidate(new RTCIceCandidate(message.payload));
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
bundles. Prefer deployment-issued, time-limited credentials for a future
browser-side TURN integration.

## Performance Tuning

### Bitrate Control

```python
# In VideoTrack
async def recv(self):
    # Adjust quality based on bandwidth
    if self.bandwidth_limited:
        frame = cv2.resize(frame, (320, 240))
```

### Hardware Encoding

```python
# Use hardware encoder if available
encoder_name = 'h264_nvenc' if nvidia_available else 'libx264'
```

## Troubleshooting

### Connection Failed

1. Check STUN/TURN servers are accessible
2. Verify firewall allows UDP traffic
3. Check browser console for ICE errors
4. On public HTTP/IP demos, use WebSocket Auto mode unless a reviewed ICE/TURN
   path exists

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
const localHttp = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);
const reviewedContext = window.location.protocol === 'https:' || localHttp;
if (!window.RTCPeerConnection || !reviewedContext) {
    console.info('Use WebSocket until the WebRTC ICE/TURN path is reviewed');
}
```
