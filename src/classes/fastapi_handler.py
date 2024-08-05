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
import uvicorn

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
            video_handler (VideoHandler): An instance of the VideoHandler class.
            telemetry_handler (TelemetryHandler): An instance of the TelemetryHandler class.
            app_controller (AppController): An instance of the AppController class.
        """
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
        self.server = None

    async def start_tracking(self, bbox: BoundingBox):
        """
        Endpoint to start tracking with the provided bounding box.

        Args:
            bbox (BoundingBox): The bounding box for tracking.

        Returns:
            dict: Status of the operation.
        """
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
        """
        Endpoint to stop tracking.

        Returns:
            dict: Status of the operation.
        """
        try:
            await self.app_controller.stop_tracking()
            return {"status": "Tracking stopped"}
        except Exception as e:
            logging.error(f"Error in stop_tracking: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def video_feed(self):
        """
        FastAPI route to serve the video feed.

        Yields:
            bytes: The next frame in JPEG format.
        """
        def generate():
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
        """
        FastAPI route to provide tracker telemetry data.
        """
        try:
            logging.debug("Received request at /telemetry/tracker_data")
            tracker_data = self.telemetry_handler.latest_tracker_data
            logging.debug(f"Tracker data: {tracker_data}")
            return JSONResponse(content=tracker_data or {})
        except Exception as e:
            logging.error(f"Error in /telemetry/tracker_data: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def follower_data(self):
        """
        FastAPI route to provide follower telemetry data.
        """
        try:
            logging.debug("Received request at /telemetry/follower_data")
            follower_data = self.telemetry_handler.latest_follower_data
            logging.debug(f"Follower data: {follower_data}")
            return JSONResponse(content=follower_data or {})
        except Exception as e:
            logging.error(f"Error in /telemetry/follower_data: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def toggle_segmentation(self):
        """
        Endpoint to toggle segmentation state (enable/disable YOLO).

        Returns:
            dict: Status of the operation and the current state of segmentation.
        """
        try:
            current_state = self.app_controller.toggle_segmentation()
            return {"status": "success", "segmentation_active": current_state}
        except Exception as e:
            logging.error(f"Error in toggle_segmentation: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def redetect(self):
        """
        Endpoint to attempt redetection of the object being tracked.

        Returns:
            dict: Status of the operation and details of the redetection attempt.
        """
        try:
            result = await self.app_controller.initiate_redetection()
            return {"status": "success", "detection_result": result}
        except Exception as e:
            logging.error(f"Error in redetect: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def cancel_activities(self):
        """
        Endpoint to cancel all active tracking and segmentation activities.

        Returns:
            dict: Status of the operation.
        """
        try:
            self.app_controller.cancel_activities()
            return {"status": "success"}
        except Exception as e:
            logging.error(f"Error in cancel_activities: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def start_offboard_mode(self):
        """
        Endpoint to start the offboard mode for PX4.

        Returns:
            dict: Status of the operation and details of the process.
        """
        try:
            result = await self.app_controller.connect_px4()
            return {"status": "success", "details": result}
        except Exception as e:
            logging.error(f"Error in start_offboard_mode: {e}")
            return {"status": "failure", "error": str(e)}

    async def stop_offboard_mode(self):
        """
        Endpoint to stop the offboard mode for PX4.

        Returns:
            dict: Status of the operation and details of the process.
        """
        try:
            result = await self.app_controller.disconnect_px4()
            return {"status": "success", "details": result}
        except Exception as e:
            logging.error(f"Error in stop_offboard_mode: {e}")
            return {"status": "failure", "error": str(e)}

    async def quit(self):
        """
        Endpoint to quit the application.

        Returns:
            dict: Status of the operation and details of the process.
        """
        try:
            logging.info("Received request to quit the application.")
            asyncio.create_task(self.app_controller.shutdown())
            self.server.should_exit = True
            return {"status": "success", "details": "Application is shutting down."}
        except Exception as e:
            logging.error(f"Error in quit: {e}")
            return {"status": "failure", "error": str(e)}

    async def start(self, host='0.0.0.0', port=Parameters.HTTP_STREAM_PORT):
        """
        Start the FastAPI server using uvicorn.
        
        Args:
            host (str): The hostname to listen on.
            port (int): The port to listen on.
        """
        config = uvicorn.Config(self.app, host=host, port=port, log_level="info")
        self.server = uvicorn.Server(config)
        await self.server.serve()

    async def stop(self):
        """
        Stop the FastAPI server.
        """
        if self.server:
            logging.info("Stopping FastAPI server...")
            self.server.should_exit = True
            await self.server.shutdown()
            logging.info("Stopped FastAPI server")
