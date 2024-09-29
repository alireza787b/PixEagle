# src/classes/webrtc_manager.py

from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
import logging
from typing import Dict
import time
import fractions

from classes.parameters import Parameters

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class VideoStreamTrackCustom(VideoStreamTrack):
    """
    A video stream track that pulls frames from the VideoHandler.
    """

    def __init__(self, video_handler, frame_rate=30):
        super().__init__()  # Initialize the base VideoStreamTrack
        self.video_handler = video_handler
        self.frame_rate = frame_rate
        self.frame_interval = 1.0 / self.frame_rate
        self.last_frame_time = time.time()

    async def recv(self):
        """
        Receive the next video frame.

        Returns:
            VideoFrame: The next video frame.
        """
        while True:
            current_time = time.time()
            elapsed = current_time - self.last_frame_time

            if elapsed < self.frame_interval:
                await asyncio.sleep(self.frame_interval - elapsed)

            frame = self.video_handler.get_frame()
            if frame is not None:
                # Validate frame format
                if frame.dtype != 'uint8' or len(frame.shape) != 3 or frame.shape[2] != 3:
                    logger.error("Invalid frame format. Expected uint8 with 3 channels (BGR).")
                    await asyncio.sleep(0.01)
                    continue

                try:
                    # Convert the frame (numpy.ndarray) to a VideoFrame
                    video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
                    video_frame.pts = time.time()
                    video_frame.time_base = fractions.Fraction(1, 1000)
                    self.last_frame_time = current_time
                    return video_frame
                except Exception as e:
                    logger.error(f"Error converting frame to VideoFrame: {e}")
                    await asyncio.sleep(0.01)
            else:
                # No frame available; wait before retrying
                await asyncio.sleep(0.01)

class WebRTCManager:
    """
    Manages WebRTC peer connections and signaling.
    """

    def __init__(self, video_handler):
        """
        Initialize the WebRTCManager with necessary dependencies.

        Args:
            video_handler (VideoHandler): An instance of the VideoHandler class.
        """
        self.video_handler = video_handler
        self.peer_connections: Dict[str, RTCPeerConnection] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

    async def signaling_handler(self, websocket: WebSocket):
        """
        Handle incoming signaling messages over WebSocket.

        Args:
            websocket (WebSocket): The WebSocket connection.
        """
        await websocket.accept()
        peer_id = None
        try:
            async for message in websocket.iter_text():
                data = json.loads(message)
                msg_type = data.get("type")
                payload = data.get("payload")
                peer_id = data.get("peer_id")

                if not peer_id:
                    # Assign a unique peer_id if not provided
                    peer_id = f"peer_{int(time.time())}"
                    self.peer_connections[peer_id] = RTCPeerConnection()
                    self.logger.info(f"Created RTCPeerConnection for {peer_id}")

                    # Handle ICE candidates from server side
                    @self.peer_connections[peer_id].on("icecandidate")
                    async def on_icecandidate(event, peer_id=peer_id):
                        if event.candidate:
                            await websocket.send_text(json.dumps({
                                "type": "ice-candidate",
                                "peer_id": peer_id,
                                "payload": {
                                    "candidate": event.candidate.to_json()
                                }
                            }))
                            self.logger.debug(f"Sent ICE candidate to {peer_id}")

                    @self.peer_connections[peer_id].on("connectionstatechange")
                    async def on_connectionstatechange():
                        state = self.peer_connections[peer_id].connectionState
                        self.logger.info(f"Connection state for {peer_id}: {state}")
                        if state == "failed":
                            await self.peer_connections[peer_id].close()
                            del self.peer_connections[peer_id]
                            self.logger.info(f"RTCPeerConnection for {peer_id} failed and closed.")

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
            if peer_id and peer_id in self.peer_connections:
                await self.peer_connections[peer_id].close()
                del self.peer_connections[peer_id]
                self.logger.info(f"Closed and removed RTCPeerConnection for {peer_id}")

    async def handle_offer(self, pc: RTCPeerConnection, offer: Dict, websocket: WebSocket, peer_id: str):
        """
        Handle WebRTC offer from the client.

        Args:
            pc (RTCPeerConnection): The peer connection.
            offer (Dict): The SDP offer.
            websocket (WebSocket): The WebSocket connection.
            peer_id (str): The unique identifier for the peer.
        """
        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=offer["sdp"], type=offer["type"]))
            self.logger.info(f"Set remote description for {peer_id}")

            # Add video track to the peer connection
            video_track = VideoStreamTrackCustom(self.video_handler, frame_rate=Parameters.STREAM_FPS)
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
        """
        Handle WebRTC answer from the client.

        Args:
            pc (RTCPeerConnection): The peer connection.
            answer (Dict): The SDP answer.
            websocket (WebSocket): The WebSocket connection.
            peer_id (str): The unique identifier for the peer.
        """
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
        """
        Handle ICE candidate from the client.

        Args:
            pc (RTCPeerConnection): The peer connection.
            candidate (Dict): The ICE candidate.
            websocket (WebSocket): The WebSocket connection.
            peer_id (str): The unique identifier for the peer.
        """
        try:
            if candidate:
                ice_candidate = candidate.get("candidate")
                sdp_mid = candidate.get("sdpMid")
                sdp_m_line_index = candidate.get("sdpMLineIndex")
                if ice_candidate and sdp_mid and sdp_m_line_index is not None:
                    await pc.addIceCandidate({
                        "candidate": ice_candidate,
                        "sdpMid": sdp_mid,
                        "sdpMLineIndex": sdp_m_line_index
                    })
                    self.logger.info(f"Added ICE candidate for {peer_id}")
        except Exception as e:
            self.logger.error(f"Error handling ICE candidate for {peer_id}: {e}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Failed to handle ICE candidate"
            }))
