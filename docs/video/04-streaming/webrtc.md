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
│  ┌─────────┐               ┌─────────┐                          │
│  │ Client  │◀──Signaling──▶│ Python  │                          │
│  │ JS      │   (HTTP)      │ aiortc  │                          │
│  └────┬────┘               └────┬────┘                          │
│       │                         │                                │
│       │    ┌───────────────────┐│                                │
│       └────│  P2P Connection   │┘                                │
│            │  (STUN/TURN)      │                                 │
│            └───────────────────┘                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

```yaml
FastAPI:
  ENABLE_WEBRTC: true
  WEBRTC_STUN_SERVER: stun:stun.l.google.com:19302
  WEBRTC_TURN_SERVER: null  # Optional TURN for NAT traversal
  WEBRTC_BITRATE: 2000000   # bits/second
```

## Signaling Endpoints

### Create Offer

```
POST /webrtc/offer
Content-Type: application/json

{
    "sdp": "<client SDP offer>",
    "type": "offer"
}

Response:
{
    "sdp": "<server SDP answer>",
    "type": "answer"
}
```

### ICE Candidates

```
POST /webrtc/ice
Content-Type: application/json

{
    "candidate": "<ICE candidate>",
    "sdpMid": "video",
    "sdpMLineIndex": 0
}
```

## Implementation

### Server (Python/aiortc)

```python
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay
import cv2
import numpy as np
from av import VideoFrame

class VideoTrack(VideoStreamTrack):
    """Video stream track from VideoHandler."""

    def __init__(self, video_handler):
        super().__init__()
        self.video_handler = video_handler

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        # Get frame from handler
        frame = self.video_handler.current_osd_frame
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Create VideoFrame
        video_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base

        return video_frame

class WebRTCManager:
    def __init__(self, video_handler):
        self.video_handler = video_handler
        self.pcs = set()
        self.relay = MediaRelay()

    async def create_peer_connection(self):
        pc = RTCPeerConnection()
        self.pcs.add(pc)

        @pc.on("connectionstatechange")
        async def on_state_change():
            if pc.connectionState == "failed":
                await pc.close()
                self.pcs.discard(pc)

        return pc

    async def handle_offer(self, offer_sdp):
        pc = await self.create_peer_connection()

        # Add video track
        video_track = VideoTrack(self.video_handler)
        pc.addTrack(video_track)

        # Set remote description
        offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
        await pc.setRemoteDescription(offer)

        # Create answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return pc.localDescription.sdp

# FastAPI integration
webrtc_manager = WebRTCManager(video_handler)

@app.post("/webrtc/offer")
async def webrtc_offer(request: dict):
    answer_sdp = await webrtc_manager.handle_offer(request["sdp"])
    return {"sdp": answer_sdp, "type": "answer"}
```

### Client (JavaScript)

```javascript
class WebRTCClient {
    constructor(signalingUrl) {
        this.signalingUrl = signalingUrl;
        this.pc = null;
        this.videoElement = document.getElementById('video');
    }

    async connect() {
        // Create peer connection
        this.pc = new RTCPeerConnection({
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' }
            ]
        });

        // Handle incoming tracks
        this.pc.ontrack = (event) => {
            this.videoElement.srcObject = event.streams[0];
        };

        // Handle ICE candidates
        this.pc.onicecandidate = async (event) => {
            if (event.candidate) {
                await this.sendIceCandidate(event.candidate);
            }
        };

        // Add transceiver for receiving video
        this.pc.addTransceiver('video', { direction: 'recvonly' });

        // Create offer
        const offer = await this.pc.createOffer();
        await this.pc.setLocalDescription(offer);

        // Send to server
        const response = await fetch(`${this.signalingUrl}/webrtc/offer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sdp: offer.sdp,
                type: 'offer'
            })
        });

        const answer = await response.json();
        await this.pc.setRemoteDescription(answer);
    }

    async sendIceCandidate(candidate) {
        await fetch(`${this.signalingUrl}/webrtc/ice`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(candidate.toJSON())
        });
    }

    disconnect() {
        if (this.pc) {
            this.pc.close();
            this.pc = null;
        }
    }
}

// Usage
const client = new WebRTCClient('http://localhost:8000');
client.connect();
```

### HTML

```html
<!DOCTYPE html>
<html>
<head>
    <title>WebRTC Video</title>
</head>
<body>
    <video id="video" autoplay playsinline></video>
    <button onclick="connect()">Connect</button>
    <button onclick="disconnect()">Disconnect</button>

    <script>
        let pc = null;

        async function connect() {
            pc = new RTCPeerConnection({
                iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
            });

            pc.ontrack = (event) => {
                document.getElementById('video').srcObject = event.streams[0];
            };

            pc.addTransceiver('video', { direction: 'recvonly' });

            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);

            const response = await fetch('/webrtc/offer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sdp: offer.sdp, type: 'offer' })
            });

            const answer = await response.json();
            await pc.setRemoteDescription(answer);
        }

        function disconnect() {
            if (pc) {
                pc.close();
                pc = null;
            }
        }
    </script>
</body>
</html>
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
