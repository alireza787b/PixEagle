# src/classes/webrtc_server.py

import asyncio
import logging
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiohttp import web
from av import VideoFrame
from classes.parameters import Parameters

class CustomVideoStreamTrack(VideoStreamTrack):
    def __init__(self, frame_generator):
        super().__init__()
        self.frame_generator = frame_generator

    async def recv(self):
        logging.info("Receiving frame from frame_generator")
        frame = await self.frame_generator()
        if frame is not None:
            logging.info("Frame received")
            video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
            video_frame.pts = 0
            video_frame.time_base = 1 / 30
            return video_frame
        logging.info("No frame received")
        return None

async def run(pc, offer):
    logging.info("Setting remote description")
    await pc.setRemoteDescription(offer)
    logging.info("Creating answer")
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    logging.info("Answer created")
    return pc.localDescription

async def webrtc_handler(request):
    logging.info("Received WebRTC offer request")
    try:
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        pc = RTCPeerConnection()
        video_generator = request.app['frame_generator']
        pc.addTrack(CustomVideoStreamTrack(video_generator))
        answer = await run(pc, offer)
        logging.info("Sending WebRTC answer")
        return web.json_response({"sdp": answer.sdp, "type": answer.type})
    except Exception as e:
        logging.error(f"Error handling WebRTC offer: {e}")
        return web.Response(status=500, text=str(e))

def create_app(frame_generator):
    app = web.Application()
    app['frame_generator'] = frame_generator
    app.router.add_post('/offer', webrtc_handler)
    logging.info("WebRTC server created")
    return app

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    app = create_app(lambda: None)
    web.run_app(app, port=Parameters.WEBRTC_PORT)
