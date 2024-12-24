# src/classes/fastapi_handler.py

import sys
import asyncio
import cv2
import logging
import time
import uvicorn
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from classes.parameters import Parameters
from classes.webrtc_manager import WebRTCManager


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class FastAPIHandler:
    def __init__(self, app_controller):
        """
        The main FastAPI handler, with optional routes for GStreamer if available.
        """
        self.app_controller = app_controller
        self.video_handler = app_controller.video_handler
        self.telemetry_handler = app_controller.telemetry_handler

        # WebRTC manager
        self.webrtc_manager = WebRTCManager(self.video_handler)

        # Create the FastAPI application
        self.app = FastAPI()
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # Define all routes
        self.define_routes()

        # Streaming parameters
        self.frame_rate = Parameters.STREAM_FPS
        self.width = Parameters.STREAM_WIDTH
        self.height = Parameters.STREAM_HEIGHT
        self.quality = Parameters.STREAM_QUALITY
        self.processed_osd = Parameters.STREAM_PROCESSED_OSD
        self.frame_interval = 1.0 / self.frame_rate

        self.is_shutting_down = False
        self.server = None

        # For concurrency
        self.frame_lock = asyncio.Lock()
        self.last_http_send_time = 0.0
        self.last_ws_send_time = 0.0

    def define_routes(self):
        # MJPEG routes
        self.app.get("/video_feed")(self.video_feed)
        self.app.websocket("/ws/video_feed")(self.video_feed_websocket)
        self.app.websocket("/ws/webrtc_signaling")(self.webrtc_manager.signaling_handler)

        # If the app_controller defines "gstreamer_http_handler", we add an H.264 route
        if getattr(self.app_controller, "gstreamer_http_handler", None):
            self.app.get("/video_feed_gstreamer")(self.video_feed_gstreamer)

        # Telemetry
        self.app.get("/telemetry/tracker_data")(self.tracker_data)
        self.app.get("/telemetry/follower_data")(self.follower_data)

        # Commands
        self.app.post("/commands/start_tracking")(self.start_tracking)
        self.app.post("/commands/stop_tracking")(self.stop_tracking)
        self.app.post("/commands/toggle_segmentation")(self.toggle_segmentation)
        self.app.post("/commands/redetect")(self.redetect)
        self.app.post("/commands/cancel_activities")(self.cancel_activities)
        self.app.post("/commands/start_offboard_mode")(self.start_offboard_mode)
        self.app.post("/commands/stop_offboard_mode")(self.stop_offboard_mode)
        self.app.post("/commands/quit")(self.quit)

    async def start_tracking(self, bbox: BoundingBox):
        try:
            width = self.video_handler.width
            height = self.video_handler.height
            # Convert bounding box to pixel coords if normalized
            if all(0 <= v <= 1 for v in [bbox.x, bbox.y, bbox.width, bbox.height]):
                bbox_pixels = {
                    'x': int(bbox.x * width),
                    'y': int(bbox.y * height),
                    'width': int(bbox.width * width),
                    'height': int(bbox.height * height)
                }
                self.logger.debug(f"Normalized bbox -> pixels: {bbox_pixels}")
            else:
                bbox_pixels = bbox.dict()
                self.logger.debug(f"Raw pixel bbox: {bbox_pixels}")

            await self.app_controller.start_tracking(bbox_pixels)
            return {"status": "Tracking started", "bbox": bbox_pixels}
        except Exception as e:
            self.logger.error(f"Error in start_tracking: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def stop_tracking(self):
        try:
            await self.app_controller.stop_tracking()
            return {"status": "Tracking stopped"}
        except Exception as e:
            self.logger.error(f"Error in stop_tracking: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def video_feed(self):
        """
        MJPEG over HTTP route. 
        """
        async def generate():
            while not self.is_shutting_down:
                current_time = time.time()
                if (current_time - self.last_http_send_time) < self.frame_interval:
                    await asyncio.sleep(0.001)
                    continue
                self.last_http_send_time = current_time

                async with self.frame_lock:
                    frame = (self.video_handler.current_resized_osd_frame
                             if self.processed_osd
                             else self.video_handler.current_resized_raw_frame)
                    if frame is None:
                        self.logger.warning("No MJPEG frame available.")
                        break

                    ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                    if ret:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' +
                               buffer.tobytes() + b'\r\n')
                    else:
                        self.logger.error("Failed to encode MJPEG frame.")
        return StreamingResponse(generate(), media_type='multipart/x-mixed-replace; boundary=frame')

    async def video_feed_websocket(self, websocket: WebSocket):
        """
        MJPEG over WebSocket route.
        """
        await websocket.accept()
        self.logger.info(f"WebSocket client connected: {websocket.client}")
        try:
            while not self.is_shutting_down:
                current_time = time.time()
                if (current_time - self.last_ws_send_time) < self.frame_interval:
                    await asyncio.sleep(0.001)
                    continue
                self.last_ws_send_time = current_time

                async with self.frame_lock:
                    frame = (self.video_handler.current_resized_osd_frame
                             if self.processed_osd
                             else self.video_handler.current_resized_raw_frame)
                    if frame is not None:
                        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                        if ret:
                            await websocket.send_bytes(buffer.tobytes())
                        else:
                            self.logger.error("Failed to encode MJPEG frame (WebSocket).")
                    else:
                        self.logger.warning("No frame available (WebSocket).")
        except WebSocketDisconnect:
            self.logger.info("WebSocket disconnected.")
        except Exception as e:
            self.logger.error(f"Error in WebSocket feed: {e}")
            await websocket.close()

    async def video_feed_gstreamer(self):
        """
        H.264 chunked streaming route, only available if gstreamer_http_handler is set up.
        """
        handler = self.app_controller.gstreamer_http_handler
        if not handler:
            raise HTTPException(status_code=400, detail="HTTP GStreamer pipeline not enabled.")

        async def generate_h264_ts():
            try:
                while not self.is_shutting_down:
                    chunk = None
                    try:
                        chunk = await asyncio.wait_for(handler.data_queue.get(), timeout=0.05)
                    except asyncio.TimeoutError:
                        await asyncio.sleep(0.001)
                    if chunk:
                        yield chunk
                # on shutdown
                await handler.data_queue.put(b'')
            except Exception as e:
                self.logger.error(f"GStreamerHTTP streaming error: {e}")
            finally:
                handler.stop()

        return StreamingResponse(generate_h264_ts(), media_type="video/mp2t")

    async def tracker_data(self):
        try:
            data = self.telemetry_handler.latest_tracker_data
            return JSONResponse(content=data or {})
        except Exception as e:
            self.logger.error(f"Error in /telemetry/tracker_data: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def follower_data(self):
        try:
            data = self.telemetry_handler.latest_follower_data
            return JSONResponse(content=data or {})
        except Exception as e:
            self.logger.error(f"Error in /telemetry/follower_data: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def toggle_segmentation(self):
        try:
            current_state = self.app_controller.toggle_segmentation()
            return {"status": "success", "segmentation_active": current_state}
        except Exception as e:
            self.logger.error(f"Error in toggle_segmentation: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def redetect(self):
        try:
            result = self.app_controller.initiate_redetection()
            return {"status": "success", "detection_result": result}
        except Exception as e:
            self.logger.error(f"Error in redetect: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def cancel_activities(self):
        try:
            self.app_controller.cancel_activities()
            return {"status": "success"}
        except Exception as e:
            self.logger.error(f"Error in cancel_activities: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def start_offboard_mode(self):
        try:
            result = await self.app_controller.connect_px4()
            return {"status": "success", "details": result}
        except Exception as e:
            self.logger.error(f"Error in start_offboard_mode: {e}")
            return {"status": "failure", "error": str(e)}

    async def stop_offboard_mode(self):
        try:
            result = await self.app_controller.disconnect_px4()
            return {"status": "success", "details": result}
        except Exception as e:
            self.logger.error(f"Error in stop_offboard_mode: {e}")
            return {"status": "failure", "error": str(e)}

    async def quit(self):
        try:
            self.logger.info("Received request to quit.")
            asyncio.create_task(self.app_controller.shutdown())
            if self.server:
                self.server.should_exit = True
            return {"status": "success", "details": "Shutting down."}
        except Exception as e:
            self.logger.error(f"Error in quit: {e}")
            return {"status": "failure", "error": str(e)}

    async def start(self, host='0.0.0.0', port=Parameters.HTTP_STREAM_PORT):
        config = uvicorn.Config(self.app, host=host, port=port, log_level="info")
        self.server = uvicorn.Server(config)
        self.logger.info(f"Starting FastAPI server on {host}:{port}")
        await self.server.serve()

    async def stop(self):
        if self.server:
            self.logger.info("Stopping FastAPI server...")
            self.server.should_exit = True
            await self.server.shutdown()
            self.logger.info("Stopped FastAPI server")
