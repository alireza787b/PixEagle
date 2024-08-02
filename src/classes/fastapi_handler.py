import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, JSONResponse
import cv2
import logging
import time
from fastapi.middleware.cors import CORSMiddleware
from classes.parameters import Parameters

class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float

class FastAPIHandler:
    def __init__(self, app_controller):
        """
        Initialize the FastAPIHandler with video and telemetry handlers.

        Args:
            app_controller (AppController): An instance of the AppController class.
        """
        logging.debug("Initializing FastAPIHandler...")
        self.video_handler = app_controller.video_handler
        self.telemetry_handler = app_controller.telemetry_handler
        self.app_controller = app_controller
        self.app = FastAPI()
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.app.get("/video_feed")(self.video_feed)
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

        self.frame_rate = Parameters.STREAM_FPS
        self.width = Parameters.STREAM_WIDTH
        self.height = Parameters.STREAM_HEIGHT
        self.quality = Parameters.STREAM_QUALITY
        self.processed_osd = Parameters.STREAM_PROCESSED_OSD
        self.last_frame_time = 0
        self.frame_interval = 1.0 / self.frame_rate
        self.is_shutting_down = False
        logging.debug("FastAPIHandler initialized.")

    async def start_tracking(self, bbox: BoundingBox):
        logging.debug(f"start_tracking called with bbox: {bbox}")
        try:
            width = self.video_handler.width
            height = self.video_handler.height

            if all(0 <= value <= 1 for value in [bbox.x, bbox.y, bbox.width, bbox.height]):
                bbox_pixels = {
                    'x': int(bbox.x * width),
                    'y': int(bbox.y * height),
                    'width': int(bbox.width * width),
                    'height': int(bbox.height * height)
                }
                logging.debug(f"Received normalized bbox, converting to pixels: {bbox_pixels}")
            else:
                bbox_pixels = bbox.dict()
                logging.debug(f"Received raw pixel bbox: {bbox_pixels}")

            await self.app_controller.start_tracking(bbox_pixels)
            return {"status": "Tracking started", "bbox": bbox_pixels}
        except Exception as e:
            logging.error(f"Error in start_tracking: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def stop_tracking(self):
        logging.debug("stop_tracking called")
        try:
            await self.app_controller.stop_tracking()
            return {"status": "Tracking stopped"}
        except Exception as e:
            logging.error(f"Error in stop_tracking: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def video_feed(self):
        logging.debug("video_feed called")
        def generate():
            logging.debug("video_feed generate called")
            while not self.is_shutting_down:
                current_time = time.time()
                if current_time - self.last_frame_time >= self.frame_interval:
                    frame = self.video_handler.current_osd_frame if self.processed_osd else self.video_handler.current_raw_frame

                    if frame is None:
                        break

                    frame = cv2.resize(frame, (self.width, self.height))
                    ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                    frame = buffer.tobytes()
                    self.last_frame_time = current_time
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                else:
                    time.sleep(self.frame_interval - (current_time - self.last_frame_time))
        
        return StreamingResponse(generate(), media_type='multipart/x-mixed-replace; boundary=frame')

    async def tracker_data(self):
        logging.debug("tracker_data called")
        try:
            tracker_data = self.telemetry_handler.latest_tracker_data
            logging.debug(f"Tracker data: {tracker_data}")
            return JSONResponse(content=tracker_data or {})
        except Exception as e:
            logging.error(f"Error in /telemetry/tracker_data: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def follower_data(self):
        logging.debug("follower_data called")
        try:
            follower_data = self.telemetry_handler.latest_follower_data
            logging.debug(f"Follower data: {follower_data}")
            return JSONResponse(content=follower_data or {})
        except Exception as e:
            logging.error(f"Error in /telemetry/follower_data: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def toggle_segmentation(self):
        logging.debug("toggle_segmentation called")
        try:
            current_state = self.app_controller.toggle_segmentation()
            return {"status": "success", "segmentation_active": current_state}
        except Exception as e:
            logging.error(f"Error in toggle_segmentation: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def redetect(self):
        logging.debug("redetect called")
        try:
            result = await self.app_controller.initiate_redetection()
            return {"status": "success", "detection_result": result}
        except Exception as e:
            logging.error(f"Error in redetect: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def cancel_activities(self):
        logging.debug("cancel_activities called")
        try:
            self.app_controller.cancel_activities()
            return {"status": "success"}
        except Exception as e:
            logging.error(f"Error in cancel_activities: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def start_offboard_mode(self):
        logging.debug("start_offboard_mode called")
        try:
            result = await self.app_controller.connect_px4()
            return {"status": "success", "details": result}
        except Exception as e:
            logging.error(f"Error in start_offboard_mode: {e}")
            return {"status": "failure", "error": str(e)}

    async def stop_offboard_mode(self):
        logging.debug("stop_offboard_mode called")
        try:
            result = await self.app_controller.disconnect_px4()
            return {"status": "success", "details": result}
        except Exception as e:
            logging.error(f"Error in stop_offboard_mode: {e}")
            return {"status": "failure", "error": str(e)}

    async def quit(self):
        logging.debug("quit called")
        try:
            logging.info("Received request to quit the application.")
            await self.app_controller.shutdown()
            return {"status": "success", "details": "Application is shutting down."}
        except Exception as e:
            logging.error(f"Error in quit: {e}")
            return {"status": "failure", "error": str(e)}
