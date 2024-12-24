import json
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
from classes.webrtc_handler import WebRTCHandler  # if needed


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class FastAPIHandler:
    def __init__(self, app_controller):
        self.app_controller = app_controller
        self.video_handler = app_controller.video_handler
        self.telemetry_handler = app_controller.telemetry_handler

        self.app = FastAPI()
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        self.define_routes()

        self.frame_rate = Parameters.STREAM_FPS
        self.width = Parameters.STREAM_WIDTH
        self.height = Parameters.STREAM_HEIGHT
        self.quality = Parameters.STREAM_QUALITY
        self.processed_osd = Parameters.STREAM_PROCESSED_OSD
        self.frame_interval = 1.0 / self.frame_rate

        self.is_shutting_down = False
        self.server = None

        self.frame_lock = asyncio.Lock()
        self.last_http_send_time = 0.0
        self.last_ws_send_time = 0.0

    def define_routes(self):
        self.app.get("/video_feed")(self.video_feed)
        self.app.websocket("/ws/video_feed")(self.video_feed_websocket)

        self.app.websocket("/ws/webrtc_signaling")(self.webrtc_signaling_handler)

        if getattr(self.app_controller, "gstreamer_http_handler", None):
            self.app.get("/video_feed_gstreamer")(self.video_feed_gstreamer)

        self.app.get("/telemetry/tracker_data")(self.tracker_data)
        self.app.get("/telemetry/follower_data")(self.follower_data)

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
        async def generate():
            while not self.is_shutting_down:
                current_time = time.time()
                if (current_time - self.last_http_send_time) < self.frame_interval:
                    await asyncio.sleep(0.001)
                    continue
                self.last_http_send_time = current_time

                async with self.frame_lock:
                    frame = (self.video_handler.current_osd_frame
                             if self.processed_osd
                             else self.video_handler.current_raw_frame)
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
        await websocket.accept()
        self.logger.info(f"[video_feed_websocket] Client connected: {websocket.client}")
        try:
            while not self.is_shutting_down:
                current_time = time.time()
                if (current_time - self.last_ws_send_time) < self.frame_interval:
                    await asyncio.sleep(0.001)
                    continue
                self.last_ws_send_time = current_time

                async with self.frame_lock:
                    # Decide if you want raw or OSD
                    frame = (
                        self.video_handler.current_osd_frame
                        if self.processed_osd
                        else self.video_handler.current_raw_frame
                    )
                    if frame is not None:
                        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                        if ret:
                            self.logger.debug("[video_feed_websocket] Sending WS frame.")
                            await websocket.send_bytes(buffer.tobytes())
                        else:
                            self.logger.error("[video_feed_websocket] Failed to encode MJPEG frame.")
                    else:
                        self.logger.warning("[video_feed_websocket] No frame available. Continuing to wait.")
                        await asyncio.sleep(0.001)  # Sleep briefly before next frame check
                        continue  # Do not break; keep the WebSocket open
        except WebSocketDisconnect:
            self.logger.info("[video_feed_websocket] Client disconnected.")
        except Exception as e:
            self.logger.error(f"[video_feed_websocket] Error: {e}")
            await websocket.close()


    async def video_feed_gstreamer(self):
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

    async def webrtc_signaling_handler(self, websocket: WebSocket):
        """
        Parse "offer", "candidate", or "bye" from the client
        and call the relevant webrtc_handler methods.
        """
        await websocket.accept()
        webrtc_handler = self.app_controller.webrtc_handler
        if not webrtc_handler or not webrtc_handler.enabled:
            logging.warning("webrtc_signaling_handler: webrtc_handler is None or disabled.")
            return

        logging.info("WebRTC Signaling: Client connected.")
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                msg_type = message.get("type", None)

                if msg_type == "offer":
                    sdp = message["sdp"]
                    logging.info("WebRTC Signaling: Received 'offer'.")
                    await webrtc_handler.set_remote_description(sdp, "offer")
                    # create answer
                    answer = await webrtc_handler.create_answer()
                    if answer:
                        response = {
                            "type": "answer",
                            "sdp": answer.sdp
                        }
                        logging.info("WebRTC Signaling: Sending 'answer' to client.")
                        await websocket.send_text(json.dumps(response))

                elif msg_type == "candidate":
                    candidate = message["candidate"]
                    logging.info(f"WebRTC Signaling: Received ICE candidate -> {candidate}")
                    await webrtc_handler.add_ice_candidate(candidate)

                elif msg_type == "bye":
                    logging.info("WebRTC Signaling: Received 'bye' from client. Closing connection soon.")
                    break

                else:
                    logging.warning(f"WebRTC Signaling: Unknown msg type '{msg_type}'.")

        except WebSocketDisconnect:
            self.logger.info("WebRTC Signaling WebSocket disconnected.")
        except Exception as e:
            logging.error(f"webrtc_signaling_handler error: {e}")
            await websocket.close()
