# src/classes/fastapi_handler.py

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
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
from classes.setpoint_handler import SetpointHandler
from classes.follower import FollowerFactory

class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float

class ClickPosition(BaseModel):
    x: float
    y: float


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

        # For frame skipping/capping
        self.last_http_send_time = 0.0
        self.last_ws_send_time = 0.0

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

        self.app.get("/status")(self.get_status)


        

        # Command endpoints
        self.app.post("/commands/start_tracking")(self.start_tracking)
        self.app.post("/commands/stop_tracking")(self.stop_tracking)
        self.app.post("/commands/toggle_segmentation")(self.toggle_segmentation)
        self.app.post("/commands/redetect")(self.redetect)
        self.app.post("/commands/cancel_activities")(self.cancel_activities)
        self.app.post("/commands/start_offboard_mode")(self.start_offboard_mode)
        self.app.post("/commands/stop_offboard_mode")(self.stop_offboard_mode)
        self.app.post("/commands/quit")(self.quit)

        # Smart Tracking (new)
        self.app.post("/commands/toggle_smart_mode")(self.toggle_smart_mode)
        self.app.post("/commands/smart_click")(self.smart_click)


        self.app.get("/api/follower/schema")(self.get_follower_schema)
        self.app.get("/api/follower/profiles")(self.get_follower_profiles)
        self.app.get("/api/follower/current-profile")(self.get_current_follower_profile)
        self.app.get("/api/follower/configured-mode")(self.get_configured_follower_mode)  # New endpoint
        self.app.post("/api/follower/switch-profile")(self.switch_follower_profile)

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
        

    async def toggle_smart_mode(self):
        """
        Toggles the YOLO-based smart tracking mode.

        Returns:
            dict: Smart mode status.
        """
        try:
            self.app_controller.toggle_smart_mode()
            status = "enabled" if self.app_controller.smart_mode_active else "disabled"
            return {"status": f"Smart mode {status}"}
        except Exception as e:
            self.logger.error(f"Error in toggle_smart_mode: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        
    async def smart_click(self, click: ClickPosition):
        """
        Handles user click for selecting an object in smart mode.

        Args:
            click (ClickPosition): Click coordinates (normalized or absolute).
        
        Returns:
            dict: Selection status.
        """
        try:
            if not self.app_controller.smart_mode_active:
                raise HTTPException(status_code=400, detail="Smart mode not active.")
            
            width = self.video_handler.width
            height = self.video_handler.height

            # Handle normalized or absolute pixel coordinates
            if 0 <= click.x <= 1 and 0 <= click.y <= 1:
                x_px = int(click.x * width)
                y_px = int(click.y * height)
                self.logger.debug(f"Normalized click received. Converted to: ({x_px}, {y_px})")
            else:
                x_px = int(click.x)
                y_px = int(click.y)
                self.logger.debug(f"Absolute click received: ({x_px}, {y_px})")

            self.app_controller.handle_smart_click(x_px, y_px)
            return {"status": "Click processed", "x": x_px, "y": y_px}

        except Exception as e:
            self.logger.error(f"Error in smart_click: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        

    async def get_status(self):
        try:
            return {
                "smart_mode_active": self.app_controller.smart_mode_active,
                "tracking_started": self.app_controller.tracking_started,
                "segmentation_active": self.app_controller.segmentation_active,
                "following_active": self.app_controller.following_active,
            }
        except Exception as e:
            self.logger.error(f"Error in get_status: {e}")
            raise HTTPException(status_code=500, detail=str(e))



    async def video_feed(self):
        """
        FastAPI route to serve the video feed over HTTP as an MJPEG stream.
        """
        async def generate():
            while not self.is_shutting_down:
                # Simple capping: ensure we don't exceed STREAM_FPS
                current_time = time.time()
                if (current_time - self.last_http_send_time) < self.frame_interval:
                    # We are still within the interval; skip frame sending
                    await asyncio.sleep(0.001)
                    continue
                self.last_http_send_time = current_time

                # Lock to safely access frames
                async with self.frame_lock:
                    # Select the proper resized frame
                    frame = (self.video_handler.current_resized_osd_frame
                             if self.processed_osd
                             else self.video_handler.current_resized_raw_frame)

                    if frame is None:
                        self.logger.warning("No frame available to send (HTTP)")
                        break

                    ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        # Yield MJPEG frame
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    else:
                        self.logger.error("Failed to encode frame (HTTP)")

        return StreamingResponse(generate(), media_type='multipart/x-mixed-replace; boundary=frame')

    async def video_feed_websocket(self, websocket: WebSocket):
        """
        WebSocket endpoint to stream video frames (MJPEG over WebSocket).
        """
        await websocket.accept()
        self.logger.info(f"WebSocket connection accepted: {websocket.client}")
        try:
            while not self.is_shutting_down:
                # Simple capping: ensure we don't exceed STREAM_FPS
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
                            self.logger.error("Failed to encode frame (WebSocket)")
                    else:
                        self.logger.warning("No frame available to send (WebSocket)")

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


    async def get_follower_schema(self):
        """
        Endpoint to get the complete follower command schema.
        
        Returns:
            dict: Complete schema including all fields and profiles.
        """
        try:
            # Read the schema file directly
            import yaml
            with open('configs/follower_commands.yaml', 'r') as f:
                schema = yaml.safe_load(f)
            return JSONResponse(content=schema)
        except Exception as e:
            self.logger.error(f"Error getting follower schema: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_follower_profiles(self):
        """
        Endpoint to get available follower profiles with implementation status.
        
        Returns:
            dict: Available profiles with detailed information.
        """
        try:
            profiles = {}
            available_modes = FollowerFactory.get_available_modes()
            
            for mode in available_modes:
                profiles[mode] = FollowerFactory.get_follower_info(mode)
                
            return JSONResponse(content=profiles)
        except Exception as e:
            self.logger.error(f"Error getting follower profiles: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_current_follower_profile(self):
        """
        Endpoint to get current follower profile information.
        Shows configured profile even when not actively engaged.
        
        Returns:
            dict: Current profile details and status.
        """
        try:
            # Check if follower is actively engaged
            has_active_follower = (
                hasattr(self.app_controller, 'follower') and 
                self.app_controller.follower is not None and
                self.app_controller.following_active
            )
            
            # Get configured mode from Parameters
            configured_mode = Parameters.FOLLOWER_MODE
            
            if has_active_follower:
                # Return active follower info
                follower = self.app_controller.follower
                profile_info = {
                    'status': 'engaged',
                    'active': True,
                    'mode': follower.mode,
                    'display_name': follower.get_display_name(),
                    'description': follower.get_description(),
                    'control_type': follower.get_control_type(),
                    'available_fields': follower.get_available_fields(),
                    'current_field_values': follower.get_follower_telemetry().get('fields', {}),
                    'validation_status': follower.validate_current_mode(),
                    'configured_mode': configured_mode
                }
            else:
                # Return configured but not engaged follower info
                try:
                    # Get schema info for the configured mode
                    profile_config = SetpointHandler.get_profile_info(configured_mode)
                    profile_info = {
                        'status': 'configured',
                        'active': False,
                        'mode': configured_mode,
                        'display_name': profile_config.get('display_name', configured_mode.replace('_', ' ').title()),
                        'description': profile_config.get('description', 'Not engaged'),
                        'control_type': profile_config.get('control_type', 'unknown'),
                        'available_fields': profile_config.get('required_fields', []) + profile_config.get('optional_fields', []),
                        'current_field_values': {},
                        'validation_status': True,  # Assume valid if in schema
                        'configured_mode': configured_mode,
                        'message': 'Profile configured but not engaged. Start offboard mode to activate.'
                    }
                except Exception as e:
                    self.logger.warning(f"Could not get schema info for configured mode '{configured_mode}': {e}")
                    profile_info = {
                        'status': 'unknown',
                        'active': False,
                        'mode': configured_mode,
                        'display_name': configured_mode.replace('_', ' ').title(),
                        'description': 'Unknown profile',
                        'control_type': 'unknown',
                        'available_fields': [],
                        'current_field_values': {},
                        'validation_status': False,
                        'configured_mode': configured_mode,
                        'error': f'Profile not found in schema: {configured_mode}'
                    }
            
            return JSONResponse(content=profile_info)
            
        except Exception as e:
            self.logger.error(f"Error getting current follower profile: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def switch_follower_profile(self, request: Request):
        """
        Endpoint to switch follower profile.
        Updates configuration for future engagement or switches active follower.
        
        Args:
            request: Should contain {'profile_name': 'new_profile_name'}
            
        Returns:
            dict: Switch operation result.
        """
        try:
            data = await request.json()
            new_profile = data.get('profile_name')
            
            if not new_profile:
                raise HTTPException(status_code=400, detail="profile_name is required")
            
            # Validate that the profile exists in schema
            try:
                available_profiles = SetpointHandler.get_available_profiles()
                if new_profile not in available_profiles:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Invalid profile '{new_profile}'. Available: {available_profiles}"
                    )
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Schema validation failed: {e}")
            
            # Check if follower is actively engaged
            has_active_follower = (
                hasattr(self.app_controller, 'follower') and 
                self.app_controller.follower is not None and
                self.app_controller.following_active
            )
            
            old_configured_mode = Parameters.FOLLOWER_MODE
            
            if has_active_follower:
                # Switch the active follower
                follower = self.app_controller.follower
                success = follower.switch_mode(new_profile)
                
                if success:
                    # Also update the configured mode
                    Parameters.FOLLOWER_MODE = new_profile
                    self.logger.info(f"Active follower switched: {old_configured_mode} → {new_profile}")
                    
                    return JSONResponse(content={
                        'status': 'success',
                        'action': 'active_switch',
                        'old_profile': old_configured_mode,
                        'new_profile': new_profile,
                        'message': f'Active follower switched to {new_profile}'
                    })
                else:
                    return JSONResponse(content={
                        'status': 'error',
                        'action': 'active_switch_failed',
                        'message': f'Failed to switch active follower to {new_profile}'
                    }, status_code=500)
            else:
                # Just update the configured mode (for future engagement)
                Parameters.FOLLOWER_MODE = new_profile
                self.logger.info(f"Configured follower mode updated: {old_configured_mode} → {new_profile}")
                
                return JSONResponse(content={
                    'status': 'success',
                    'action': 'config_update',
                    'old_profile': old_configured_mode,
                    'new_profile': new_profile,
                    'message': f'Configured follower mode set to {new_profile}. Will activate when offboard mode starts.'
                })
                
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error switching follower profile: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_configured_follower_mode(self):
        """
        Endpoint to get the currently configured follower mode from Parameters.
        
        Returns:
            dict: Configured mode information.
        """
        try:
            configured_mode = Parameters.FOLLOWER_MODE
            
            try:
                profile_config = SetpointHandler.get_profile_info(configured_mode)
                return JSONResponse(content={
                    'configured_mode': configured_mode,
                    'profile_info': profile_config,
                    'status': 'valid'
                })
            except Exception as e:
                return JSONResponse(content={
                    'configured_mode': configured_mode,
                    'profile_info': None,
                    'status': 'invalid',
                    'error': str(e)
                })
                
        except Exception as e:
            self.logger.error(f"Error getting configured follower mode: {e}")
            raise HTTPException(status_code=500, detail=str(e))