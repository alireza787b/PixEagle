# src/classes/stream_manager.py

import asyncio
import logging
from aiohttp import web
from .webrtc_server import create_app
from .parameters import Parameters

class StreamManager:
    def __init__(self, app_controller):
        self.app_controller = app_controller
        self.streaming_active = False
        self.runner = None

    async def start_streaming(self):
        logging.info("Attempting to start streaming")
        if not self.streaming_active:
            app = create_app(self.frame_generator)
            self.runner = web.AppRunner(app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, Parameters.WEBRTC_HOST, Parameters.WEBRTC_PORT)
            await self.site.start()
            self.streaming_active = True
            logging.info(f"Streaming started on {Parameters.WEBRTC_HOST}:{Parameters.WEBRTC_PORT}")
        else:
            logging.info("Streaming already active")

    async def stop_streaming(self):
        logging.info("Attempting to stop streaming")
        if self.streaming_active:
            await self.runner.cleanup()
            self.streaming_active = False
            logging.info("Streaming stopped")
        else:
            logging.info("Streaming not active")

    async def frame_generator(self):
        while True:
            frame = self.app_controller.current_frame
            if frame is not None:
                logging.info("Yielding frame")
                yield frame
            else:
                logging.info("No frame to yield")
            await asyncio.sleep(0.1)  # Adjust as necessary
