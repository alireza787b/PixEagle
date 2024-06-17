# src/test_webrtc_client.py

import asyncio
import json
import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from av import VideoFrame
from classes.parameters import Parameters
import logging

class DummyVideoTrack(MediaStreamTrack):
    kind = "video"

    async def recv(self):
        frame = VideoFrame(width=640, height=480, format="rgb24")
        frame.pts = 0
        frame.time_base = 1 / 30
        return frame

async def test_webrtc():
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Starting WebRTC test client")
    pc = RTCPeerConnection()

    # Add dummy video track
    pc.addTrack(DummyVideoTrack())

    async def send_offer():
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        url = f'http://{Parameters.WEBRTC_HOST}:{Parameters.WEBRTC_PORT}/offer'
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={'sdp': pc.localDescription.sdp, 'type': pc.localDescription.type}) as resp:
                logging.info(f"Offer sent: {resp.status}")
                if resp.status != 200:
                    logging.error(f"Failed to send offer: {resp.status}")
                else:
                    data = await resp.json()
                    logging.info("Received answer from server")
                    await pc.setRemoteDescription(RTCSessionDescription(sdp=data['sdp'], type=data['type']))

    await send_offer()
    logging.info("WebRTC test client completed")

if __name__ == "__main__":
    asyncio.run(test_webrtc())
