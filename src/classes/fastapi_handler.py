import asyncio
from fastapi import FastAPI, BackgroundTasks, WebSocket, HTTPException
from fastapi import Request
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, JSONResponse
import threading
import cv2
import logging
import time
from fastapi.middleware.cors import CORSMiddleware
from classes.parameters import Parameters

class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int

class FastAPIHandler:
    def __init__(self, video_handler, telemetry_handler,app_controller):
        """
        Initialize the FastAPIHandler with video and telemetry handlers.

        Args:
            video_handler (VideoHandler): An instance of the VideoHandler class.
            telemetry_handler (TelemetryHandler): An instance of the TelemetryHandler class.
        """
        self.video_handler = video_handler
        self.telemetry_handler = telemetry_handler
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
        self.app.post("/commands/example_command_test")(self.commands)
        self.app.post("/commands/tracking")(self.toggle_tracking)
        self.app.post("/commands/toggle_segmentation")(self.toggle_segmentation)
        self.app.post("/commands/redetect")(self.redetect)
        self.app.post("/commands/cancel_activities")(self.cancel_activities)
        self.app.post("/commands/start_offboard_mode")(self.start_offboard_mode)
        self.app.post("/commands/stop_offboard_mode")(self.stop_offboard_mode)
        self.app.post("/commands/quit")(self.quit)




        self.server_thread = None
        self.frame_rate = Parameters.STREAM_FPS
        self.width = Parameters.STREAM_WIDTH
        self.height = Parameters.STREAM_HEIGHT
        self.quality = Parameters.STREAM_QUALITY
        self.processed_osd = Parameters.STREAM_PROCESSED_OSD
        self.last_frame_time = 0
        self.frame_interval = 1.0 / self.frame_rate
        self.is_shutting_down = False
        self.server = None
        
    async def toggle_tracking(self, request: Request, bbox: BoundingBox = None):
        """
        Endpoint to start or stop tracking.
        If a bounding box is provided, tracking will start. If not, tracking will stop.

        Args:
            request (Request): The incoming HTTP request.
            bbox (BoundingBox, optional): The bounding box for tracking.

        Returns:
            dict: Status of the operation.
        """
        try:
            if bbox:
                await self.app_controller.start_tracking(bbox.dict())
            else:
                await self.app_controller.stop_tracking()
            return {"status": "success"}
        except Exception as e:
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
                    if self.processed_osd:
                        frame = self.video_handler.current_osd_frame
                    else:
                        frame = self.video_handler.current_raw_frame

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

    async def commands(self, command: dict):
        """
        FastAPI route to handle incoming commands.
        """
        logging.info(f"Received command: {command}")
        return JSONResponse(content={'status': 'success', 'command': command})

    def start(self, host='0.0.0.0', port=Parameters.HTTP_STREAM_PORT):
        """
        Start the FastAPI server in a new thread.

        Args:
            host (str): The hostname to listen on.
            port (int): The port to listen on.
        """
        if self.server_thread is None:
            import uvicorn
            self.server = uvicorn.Server(uvicorn.Config(self.app, host=host, port=port, log_level="info"))
            self.server_thread = threading.Thread(target=self.server.run)
            self.server_thread.start()
            logging.info(f"Started FastAPI server on {host}:{port}")

    def stop(self):
        """
        Stop the FastAPI server.
        """
        if self.server:
            logging.info("Stopping FastAPI server...")
            self.server.should_exit = True
            self.server.force_exit = True
            self.server_thread.join()
            logging.info("Stopped FastAPI server")


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
            raise HTTPException(status_code=500, detail=str(e))
        
    async def redetect(self):
        """
        Endpoint to attempt redetection of the object being tracked.

        Returns:
            dict: Status of the operation and details of the redetection attempt.
        """
        try:
            result = self.app_controller.initiate_redetection()
            return {"status": "success", "detection_result": result}
        except Exception as e:
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
            return {"status": "failure", "error": str(e)}
        
    async def quit(self):
        """
        Endpoint to quit the application.

        Returns:
            dict: Status of the operation and details of the process.
        """
        try:
            result = await self.app_controller.shutdown()
            return {"status": "success", "details": result}
        except Exception as e:
            return {"status": "failure", "error": str(e)}
        
        
    async def quit(self):
        """
        Endpoint to quit the application.

        Returns:
            dict: Status of the operation and details of the process.
        """
        try:
            # Trigger the shutdown process
            asyncio.create_task(self.app_controller.shutdown())
            self.server.should_exit = True  # Gracefully stop the FastAPI server
            return {"status": "success", "details": "Application is shutting down."}
        except Exception as e:
            return {"status": "failure", "error": str(e)}