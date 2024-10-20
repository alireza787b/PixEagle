# src/classes/fastapi_handler.py

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import cv2
import logging
import time
from classes.parameters import Parameters
import uvicorn
from typing import Dict
from classes.webrtc_manager import WebRTCManager  # Import the WebRTCManager

class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float

class FastAPIHandler:
    def __init__(self, app_controller):
        """
        Initialize the FastAPIHandler with necessary dependencies and settings.

        Args:
            app_controller (AppController): An instance of the AppController class.
        """
        # Dependencies
        self.app_controller = app_controller
        self.video_handler = app_controller.video_handler
        self.telemetry_handler = app_controller.telemetry_handler

        # Initialize WebRTC Manager
        self.webrtc_manager = WebRTCManager(self.video_handler)

        # FastAPI app initialization
        self.app = FastAPI()
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Update as needed for security
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)  # Adjust the logging level as needed

        # Define API routes
        self.define_routes()

        # Video streaming parameters
        self.frame_rate = Parameters.STREAM_FPS
        self.width = Parameters.STREAM_WIDTH
        self.height = Parameters.STREAM_HEIGHT
        self.quality = Parameters.STREAM_QUALITY
        self.processed_osd = Parameters.STREAM_PROCESSED_OSD
        self.frame_interval = 1.0 / self.frame_rate

        # State variables
        self.is_shutting_down = False
        self.server = None

        # Lock for thread-safe frame access
        self.frame_lock = asyncio.Lock()

    def define_routes(self):
        """
        Define all the API routes for the FastAPIHandler.
        """
        # HTTP streaming endpoint
        self.app.get("/video_feed")(self.video_feed)
        # WebSocket streaming endpoint
        self.app.websocket("/ws/video_feed")(self.video_feed_websocket)
        # WebRTC Signaling endpoint
        self.app.websocket("/ws/webrtc_signaling")(self.webrtc_manager.signaling_handler)

        # Telemetry endpoints
        self.app.get("/telemetry/tracker_data")(self.tracker_data)
        self.app.get("/telemetry/follower_data")(self.follower_data)

        # Command endpoints
        self.app.post("/commands/start_tracking")(self.start_tracking)
        self.app.post("/commands/stop_tracking")(self.stop_tracking)
        self.app.post("/commands/toggle_segmentation")(self.toggle_segmentation)
        self.app.post("/commands/redetect")(self.redetect)
        self.app.post("/commands/cancel_activities")(self.cancel_activities)
        self.app.post("/commands/start_offboard_mode")(self.start_offboard_mode)
        self.app.post("/commands/stop_offboard_mode")(self.stop_offboard_mode)
        self.app.post("/commands/quit")(self.quit)

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

            # Normalize bounding box if values are between 0 and 1
            if all(0 <= value <= 1 for value in [bbox.x, bbox.y, bbox.width, bbox.height]):
                bbox_pixels = {
                    'x': int(bbox.x * width),
                    'y': int(bbox.y * height),
                    'width': int(bbox.width * width),
                    'height': int(bbox.height * height)
                }
                self.logger.debug(f"Received normalized bbox, converting to pixels: {bbox_pixels}")
            else:
                bbox_pixels = bbox.dict()
                self.logger.debug(f"Received raw pixel bbox: {bbox_pixels}")

            # Start tracking using the app controller
            await self.app_controller.start_tracking(bbox_pixels)
            return {"status": "Tracking started", "bbox": bbox_pixels}
        except Exception as e:
            self.logger.error(f"Error in start_tracking: {e}")
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
            self.logger.error(f"Error in stop_tracking: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def video_feed(self):
        """
        FastAPI route to serve the video feed over HTTP.

        Returns:
            StreamingResponse: A streaming response with video frames.
        """
        async def generate():
            while not self.is_shutting_down:
                start_time = time.time()
                async with self.frame_lock:
                    # Get the current frame
                    frame = (self.video_handler.current_osd_frame if self.processed_osd
                             else self.video_handler.current_raw_frame)
                    if frame is None:
                        self.logger.warning("No frame available to send")
                        break
                    # Resize and encode the frame
                    frame = cv2.resize(frame, (self.width, self.height))
                    ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        # Yield the frame in the HTTP response
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    else:
                        self.logger.error("Failed to encode frame")
                # Control the frame rate
                elapsed_time = time.time() - start_time
                await asyncio.sleep(max(0, self.frame_interval - elapsed_time))
        return StreamingResponse(generate(), media_type='multipart/x-mixed-replace; boundary=frame')

    async def video_feed_websocket(self, websocket: WebSocket):
        """
        WebSocket endpoint to stream video frames.

        Args:
            websocket (WebSocket): The WebSocket connection object.
        """
        await websocket.accept()
        self.logger.info(f"WebSocket connection accepted: {websocket.client}")
        try:
            while not self.is_shutting_down:
                start_time = time.time()
                async with self.frame_lock:
                    # Get the current frame
                    frame = (self.video_handler.current_osd_frame if self.processed_osd
                             else self.video_handler.current_raw_frame)
                    if frame is not None:
                        # Resize and encode the frame
                        frame = cv2.resize(frame, (self.width, self.height))
                        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                        if ret:
                            # Send the frame over the WebSocket
                            await websocket.send_bytes(buffer.tobytes())
                        else:
                            self.logger.error("Failed to encode frame")
                    else:
                        self.logger.warning("No frame available to send")
                # Control the frame rate
                elapsed_time = time.time() - start_time
                await asyncio.sleep(max(0, self.frame_interval - elapsed_time))
        except WebSocketDisconnect:
            self.logger.info(f"WebSocket disconnected: {websocket.client}")
        except Exception as e:
            self.logger.error(f"Error in WebSocket video feed: {e}")
            await websocket.close()

    async def tracker_data(self):
        """
        FastAPI route to provide tracker telemetry data.

        Returns:
            JSONResponse: The latest tracker data.
        """
        try:
            self.logger.debug("Received request at /telemetry/tracker_data")
            tracker_data = self.telemetry_handler.latest_tracker_data
            self.logger.debug(f"Returning tracker data: {tracker_data}")
            return JSONResponse(content=tracker_data or {})
        except Exception as e:
            self.logger.error(f"Error in /telemetry/tracker_data: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def follower_data(self):
        """
        FastAPI route to provide follower telemetry data.

        Returns:
            JSONResponse: The latest follower data.
        """
        try:
            self.logger.debug("Received request at /telemetry/follower_data")
            follower_data = self.telemetry_handler.latest_follower_data
            self.logger.debug(f"Returning follower data: {follower_data}")
            return JSONResponse(content=follower_data or {})
        except Exception as e:
            self.logger.error(f"Error in /telemetry/follower_data: {e}")
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
            self.logger.error(f"Error in toggle_segmentation: {e}")
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
            self.logger.error(f"Error in redetect: {e}")
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
            self.logger.error(f"Error in cancel_activities: {e}")
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
            self.logger.error(f"Error in start_offboard_mode: {e}")
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
            self.logger.error(f"Error in stop_offboard_mode: {e}")
            return {"status": "failure", "error": str(e)}

    async def quit(self):
        """
        Endpoint to quit the application.

        Returns:
            dict: Status of the operation and details of the process.
        """
        try:
            self.logger.info("Received request to quit the application.")
            asyncio.create_task(self.app_controller.shutdown())
            if self.server:
                self.server.should_exit = True
            return {"status": "success", "details": "Application is shutting down."}
        except Exception as e:
            self.logger.error(f"Error in quit: {e}")
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
        self.logger.info(f"Starting FastAPI server on {host}:{port}")
        await self.server.serve()

    async def stop(self):
        """
        Stop the FastAPI server.
        """
        if self.server:
            self.logger.info("Stopping FastAPI server...")
            self.server.should_exit = True
            await self.server.shutdown()
            self.logger.info("Stopped FastAPI server")
