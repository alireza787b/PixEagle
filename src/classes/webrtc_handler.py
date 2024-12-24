import asyncio
import logging
import time
import numpy as np
from av import VideoFrame

from aiortc import (
    RTCPeerConnection,
    RTCConfiguration,
    RTCIceServer,
    RTCSessionDescription
)
from aiortc.mediastreams import MediaStreamTrack

from classes.parameters import Parameters

class VideoFrameTrack(MediaStreamTrack):
    """
    A MediaStreamTrack that holds the latest frame from 'push_frame()'
    in memory, returning it whenever aiortc calls 'recv()'.
    """
    kind = "video"

    def __init__(self):
        super().__init__()
        self.latest_frame = None
        logging.debug("VideoFrameTrack initialized with no frame yet.")

    async def recv(self):
        # Produce frames at the rate the WebRTC pipeline requests them
        pts, time_base = await self.next_timestamp()

        while self.latest_frame is None:
            logging.debug("VideoFrameTrack.recv(): No frame yet, sleeping 10ms.")
            await asyncio.sleep(0.01)

        # We have a frame to send
        frame = self.latest_frame
        logging.debug(f"VideoFrameTrack.recv(): Sending frame with shape {frame.shape}.")

        # Convert the np.ndarray (BGR) to an AV VideoFrame
        av_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        av_frame.pts = pts
        av_frame.time_base = time_base
        return av_frame


class WebRTCHandler:
    """
    WebRTC Handler using aiortc.
    - If ENABLE_WEBRTC is true, we create a peer connection and a video track.
    - 'push_frame(frame)' sets the track's latest frame.
    - If no connection is established, that's okay: once a remote offer is set,
      frames can flow if the ICE completes.

    Steps:
      1) In AppController, create WebRTCHandler if ENABLE_WEBRTC is true.
      2) In update_loop(), call push_frame() each time a new frame is processed.
      3) In fastapi_handler, handle 'offer'/'candidate' from the client, 
         then set_remote_description(...) + create_answer().
    """

    def __init__(self):
        self.enabled = getattr(Parameters, "ENABLE_WEBRTC", False)
        if self.enabled:
            logging.info("WebRTCHandler: ENABLE_WEBRTC is True. Initializing.")
            self.video_track = VideoFrameTrack()
            self._build_peer_connection()
        else:
            logging.info("WebRTCHandler: Disabled in config.")
            self.pc = None
            self.video_track = None

    def _build_peer_connection(self):
        # Build ICE server config from STUN/TURN
        ice_servers = []
        if Parameters.STUN_SERVER:
            ice_servers.append(RTCIceServer(urls=[Parameters.STUN_SERVER]))
        if Parameters.TURN_SERVER:
            ice_servers.append(
                RTCIceServer(
                    urls=[Parameters.TURN_SERVER],
                    username=Parameters.TURN_USERNAME,
                    credential=Parameters.TURN_PASSWORD,
                )
            )
        config = RTCConfiguration(iceServers=ice_servers)

        self.pc = RTCPeerConnection(configuration=config)
        if self.video_track:
            self.pc.addTrack(self.video_track)
            logging.info("WebRTCHandler: PeerConnection created, video track added.")
        else:
            logging.warning("WebRTCHandler: video_track is None, no track added.")

    def start(self):
        """
        Called by AppController if needed. 
        Might be used to do more advanced logic if desired.
        """
        if not self.enabled:
            logging.info("WebRTCHandler.start(): Not enabled.")
            return
        logging.info("WebRTCHandler.start(): Starting real WebRTC pipeline (placeholder).")

    def push_frame(self, frame: np.ndarray):
        """
        Called each time a new frame arrives from the camera pipeline.
        """
        if not self.enabled or not self.pc:
            return

        if self.video_track:
            self.video_track.latest_frame = frame
            #logging.debug(f"WebRTCHandler.push_frame(): Stored frame of shape {frame.shape}.")
        else:
            logging.debug("WebRTCHandler.push_frame(): No video_track to store frame.")

    def stop(self):
        """
        Cleanly shut down the peer connection.
        """
        if self.enabled and self.pc:
            logging.info("WebRTCHandler.stop(): Closing RTCPeerConnection.")
            asyncio.create_task(self.pc.close())

    async def set_remote_description(self, sdp: str, sdp_type: str):
        if not self.enabled or not self.pc:
            logging.warning("set_remote_description called, but WebRTC is disabled or pc is None.")
            return

        desc = RTCSessionDescription(sdp, sdp_type)
        logging.debug(f"WebRTCHandler.set_remote_description(): {sdp_type=} len(sdp)={len(sdp)}")
        await self.pc.setRemoteDescription(desc)
        logging.info(f"WebRTCHandler: set remote {sdp_type} description done.")

    async def create_answer(self):
        """
        Create an answer after setting remote offer.
        """
        if not self.enabled or not self.pc:
            logging.warning("create_answer() called but not enabled or no pc.")
            return None
        logging.debug("WebRTCHandler.create_answer(): Creating answer.")
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        logging.info("WebRTCHandler.create_answer(): Local description set to answer.")
        return answer

    async def add_ice_candidate(self, candidate_dict: dict):
        if not self.enabled or not self.pc:
            logging.warning("add_ice_candidate called but not enabled or no pc.")
            return
        try:
            logging.debug(f"Adding ICE candidate: {candidate_dict}")
            # If aiortc is new enough, pass the dict in directly:
            await self.pc.addIceCandidate({
                "candidate": candidate_dict["candidate"],
                "sdpMid": candidate_dict["sdpMid"],
                "sdpMLineIndex": candidate_dict["sdpMLineIndex"]
            })
            logging.debug("Candidate added successfully.")
        except Exception as e:
            logging.error(f"Error adding ICE candidate: {e}")

