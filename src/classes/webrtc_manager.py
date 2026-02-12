# src/classes/webrtc_manager.py
"""
WebRTC peer connection manager with signaling over WebSocket.

Uses FramePublisher for thread-safe frame access (instead of direct
video_handler.get_frame() which bypassed OSD/resize and competed
with the main capture loop).
"""

from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.sdp import candidate_from_sdp
from av import VideoFrame
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
import logging
import fractions
import time
from typing import Dict

from classes.parameters import Parameters

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class VideoStreamTrackCustom(VideoStreamTrack):
    """
    A video stream track that pulls frames from FramePublisher.

    Fixes from original:
    - Uses FramePublisher instead of video_handler.get_frame() (no capture device contention)
    - PTS is monotonic milliseconds from stream start (not Unix timestamp)
    - Reads OSD-composited, stream-resolution frames
    """

    def __init__(self, frame_publisher, frame_rate=30):
        super().__init__()
        self.frame_publisher = frame_publisher
        self.frame_rate = frame_rate
        self.frame_interval = 1.0 / self.frame_rate
        self.last_frame_time = time.time()
        self._start_time = time.monotonic()

    async def recv(self):
        """Receive the next video frame."""
        while True:
            current_time = time.time()
            elapsed = current_time - self.last_frame_time

            if elapsed < self.frame_interval:
                await asyncio.sleep(self.frame_interval - elapsed)

            stamped = self.frame_publisher.get_latest(prefer_osd=True)
            if stamped is not None:
                frame = stamped.frame
                # Validate frame format
                if frame.dtype != 'uint8' or len(frame.shape) != 3 or frame.shape[2] != 3:
                    logger.error("Invalid frame format. Expected uint8 with 3 channels (BGR).")
                    await asyncio.sleep(0.01)
                    continue

                try:
                    video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
                    # Correct PTS: monotonic counter in milliseconds from stream start
                    elapsed_ms = int((time.monotonic() - self._start_time) * 1000)
                    video_frame.pts = elapsed_ms
                    video_frame.time_base = fractions.Fraction(1, 1000)
                    self.last_frame_time = current_time
                    return video_frame
                except Exception as e:
                    logger.error(f"Error converting frame to VideoFrame: {e}")
                    await asyncio.sleep(0.01)
            else:
                await asyncio.sleep(0.01)


class WebRTCManager:
    """
    Manages WebRTC peer connections and signaling.

    Accepts a FramePublisher instead of VideoHandler for thread-safe
    frame access. Enforces connection limits via WEBRTC_MAX_CONNECTIONS.
    """

    def __init__(self, frame_publisher):
        """
        Initialize the WebRTCManager.

        Args:
            frame_publisher: A FramePublisher instance for thread-safe frame access.
        """
        self.frame_publisher = frame_publisher
        self.peer_connections: Dict[str, RTCPeerConnection] = {}
        self.max_connections = getattr(Parameters, 'WEBRTC_MAX_CONNECTIONS', 3)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

    async def signaling_handler(self, websocket: WebSocket):
        """
        Handle incoming signaling messages over WebSocket.

        One peer connection per WebSocket session. The peer_id is assigned once
        on the first message (or taken from the client if provided) and reused
        for all subsequent messages on the same connection.
        """
        await websocket.accept()
        peer_id = None
        registered = False  # Track whether we registered with FramePublisher

        # Check connection limit before proceeding
        if len(self.peer_connections) >= self.max_connections:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Max WebRTC connections ({self.max_connections}) reached"
            }))
            await websocket.close(code=1008, reason="Max connections reached")
            return

        try:
            async for message in websocket.iter_text():
                data = json.loads(message)
                msg_type = data.get("type")
                payload = data.get("payload")

                # Create peer connection once per WebSocket session
                if peer_id is None:
                    peer_id = data.get("peer_id") or f"peer_{int(time.time() * 1000)}"
                    self.peer_connections[peer_id] = RTCPeerConnection()
                    self.frame_publisher.register_client()
                    registered = True
                    self.logger.info(f"Created RTCPeerConnection for {peer_id}")

                    # Handle ICE candidates from server side
                    @self.peer_connections[peer_id].on("icecandidate")
                    async def on_icecandidate(event, _peer_id=peer_id):
                        if event.candidate:
                            try:
                                await websocket.send_text(json.dumps({
                                    "type": "ice-candidate",
                                    "peer_id": _peer_id,
                                    "payload": {
                                        "candidate": event.candidate.to_json()
                                    }
                                }))
                                self.logger.debug(f"Sent ICE candidate to {_peer_id}")
                            except Exception:
                                pass  # WebSocket may already be closed

                    @self.peer_connections[peer_id].on("connectionstatechange")
                    async def on_connectionstatechange(_peer_id=peer_id):
                        pc = self.peer_connections.get(_peer_id)
                        if pc:
                            state = pc.connectionState
                            self.logger.info(f"Connection state for {_peer_id}: {state}")
                            if state in ("failed", "closed"):
                                await self._cleanup_peer(_peer_id)

                pc = self.peer_connections.get(peer_id)

                if not pc:
                    self.logger.error(f"No RTCPeerConnection found for peer_id: {peer_id}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Invalid peer_id"
                    }))
                    continue

                # Handle different message types
                if msg_type == "offer":
                    await self.handle_offer(pc, payload, websocket, peer_id)
                elif msg_type == "answer":
                    await self.handle_answer(pc, payload, websocket, peer_id)
                elif msg_type == "ice-candidate":
                    await self.handle_ice_candidate(pc, payload, websocket, peer_id)
                else:
                    self.logger.warning(f"Unknown message type: {msg_type}")

        except WebSocketDisconnect:
            self.logger.info(f"WebRTC signaling WebSocket disconnected: {peer_id}")
        except Exception as e:
            self.logger.error(f"Error in signaling_handler: {e}")
        finally:
            if peer_id:
                await self._cleanup_peer(peer_id)
            elif registered:
                # Edge case: registered but peer_id somehow lost
                self.frame_publisher.unregister_client()

    async def _cleanup_peer(self, peer_id: str):
        """Close and remove a peer connection, unregister from FramePublisher."""
        pc = self.peer_connections.pop(peer_id, None)
        if pc is not None:
            try:
                await pc.close()
            except Exception:
                pass
            self.frame_publisher.unregister_client()
            self.logger.info(f"Cleaned up RTCPeerConnection for {peer_id}")

    async def handle_offer(self, pc: RTCPeerConnection, offer: Dict, websocket: WebSocket, peer_id: str):
        """Handle WebRTC offer from the client."""
        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=offer["sdp"], type=offer["type"]))
            self.logger.info(f"Set remote description for {peer_id}")

            # Add video track using FramePublisher
            video_track = VideoStreamTrackCustom(
                self.frame_publisher,
                frame_rate=getattr(Parameters, 'STREAM_FPS', 30),
            )
            pc.addTrack(video_track)
            self.logger.info(f"Added VideoStreamTrack to {peer_id}")

            # Create answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            # Send the answer back to the client
            await websocket.send_text(json.dumps({
                "type": pc.localDescription.type,
                "payload": {
                    "sdp": pc.localDescription.sdp
                },
                "peer_id": peer_id
            }))
            self.logger.info(f"Sent answer to {peer_id}")
        except Exception as e:
            self.logger.error(f"Error handling offer for {peer_id}: {e}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Failed to handle offer"
            }))

    async def handle_answer(self, pc: RTCPeerConnection, answer: Dict, websocket: WebSocket, peer_id: str):
        """Handle WebRTC answer from the client."""
        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
            self.logger.info(f"Set remote description (answer) for {peer_id}")
        except Exception as e:
            self.logger.error(f"Error handling answer for {peer_id}: {e}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Failed to handle answer"
            }))

    async def handle_ice_candidate(self, pc: RTCPeerConnection, candidate: Dict, websocket: WebSocket, peer_id: str):
        """Handle ICE candidate from the client."""
        try:
            if candidate:
                ice_candidate_str = candidate.get("candidate")
                sdp_mid = candidate.get("sdpMid")
                sdp_m_line_index = candidate.get("sdpMLineIndex")
                if ice_candidate_str and sdp_mid and sdp_m_line_index is not None:
                    rtc_candidate = candidate_from_sdp(ice_candidate_str)
                    rtc_candidate.sdpMid = sdp_mid
                    rtc_candidate.sdpMLineIndex = sdp_m_line_index
                    await pc.addIceCandidate(rtc_candidate)
                    self.logger.info(f"Added ICE candidate for {peer_id}")
        except Exception as e:
            self.logger.error(f"Error handling ICE candidate for {peer_id}: {e}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Failed to handle ICE candidate"
            }))
