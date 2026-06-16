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
credential-aware dashboard client. Production remote-browser approval still
requires TLS/operator deployment hardening, typed replacements and retirement
for remaining legacy tracking/control mutations, adversarial auth/media tests,
and evidence gates.

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
  const offer = await pc.createOffer({ offerToReceiveVideo: true });
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
// Check WebRTC support
if (!window.RTCPeerConnection) {
    alert('WebRTC not supported');
}
```
