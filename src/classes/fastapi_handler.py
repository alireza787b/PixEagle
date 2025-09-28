# src/classes/fastapi_handler.py

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import cv2
import numpy as np
import logging
import time
import hashlib
from typing import Dict, Optional, Set, Tuple, List
from collections import deque
from dataclasses import dataclass
import json
from classes.parameters import Parameters
import uvicorn
from classes.webrtc_manager import WebRTCManager
from classes.setpoint_handler import SetpointHandler
from classes.follower import FollowerFactory
from classes.tracker_output import TrackerOutput, TrackerDataType

# Import circuit breaker with error handling
try:
    from classes.circuit_breaker import FollowerCircuitBreaker
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False

# Performance monitoring
from contextlib import asynccontextmanager
import threading
from concurrent.futures import ThreadPoolExecutor

# Models
class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float

class ClickPosition(BaseModel):
    x: float
    y: float

@dataclass
class ClientConnection:
    """Track client connection state."""
    id: str
    connected_at: float
    last_frame_time: float
    quality: int
    frame_drops: int
    bandwidth_estimate: float  # bytes/second
    frame_queue: deque

@dataclass
class CachedFrame:
    """Cached encoded frame."""
    data: bytes
    timestamp: float
    hash: str
    quality: int


class StreamingOptimizer:
    """Optimized streaming with caching and adaptive quality."""
    
    def __init__(self, max_cache_size: int = 10):
        self.frame_cache: Dict[str, CachedFrame] = {}
        self.max_cache_size = max_cache_size
        self.encoder_pool = ThreadPoolExecutor(max_workers=Parameters.ENCODING_THREADS)
        self.last_frame_hash: Optional[str] = None
        self.encoding_lock = threading.Lock()
        
    def get_frame_hash(self, frame: np.ndarray) -> str:
        """Generate hash for frame comparison."""
        # Downsample for faster hashing
        small = cv2.resize(frame, (64, 64))
        return hashlib.md5(small.tobytes()).hexdigest()
    
    def encode_frame_cached(self, frame: np.ndarray, quality: int) -> bytes:
        """Encode frame with caching."""
        # Generate frame hash
        frame_hash = self.get_frame_hash(frame)
        
        # Check if frame is identical to last
        if Parameters.SKIP_IDENTICAL_FRAMES and frame_hash == self.last_frame_hash:
            cache_key = f"{frame_hash}_{quality}"
            if cache_key in self.frame_cache:
                cached = self.frame_cache[cache_key]
                if time.time() - cached.timestamp < Parameters.CACHE_TTL_MS / 1000:
                    return cached.data
        
        self.last_frame_hash = frame_hash
        
        # Check cache
        cache_key = f"{frame_hash}_{quality}"
        if Parameters.ENABLE_FRAME_CACHE and cache_key in self.frame_cache:
            cached = self.frame_cache[cache_key]
            if time.time() - cached.timestamp < Parameters.CACHE_TTL_MS / 1000:
                return cached.data
        
        # Encode frame
        with self.encoding_lock:
            ret, buffer = cv2.imencode('.jpg', frame, 
                                       [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ret:
                raise ValueError("Failed to encode frame")
            
            frame_bytes = buffer.tobytes()
        
        # Update cache
        if Parameters.ENABLE_FRAME_CACHE:
            self.frame_cache[cache_key] = CachedFrame(
                data=frame_bytes,
                timestamp=time.time(),
                hash=frame_hash,
                quality=quality
            )
            
            # Cleanup old cache entries
            if len(self.frame_cache) > self.max_cache_size:
                oldest_key = min(self.frame_cache.keys(), 
                               key=lambda k: self.frame_cache[k].timestamp)
                del self.frame_cache[oldest_key]
        
        return frame_bytes
    
    async def encode_frame_async(self, frame: np.ndarray, quality: int) -> bytes:
        """Async wrapper for frame encoding."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.encoder_pool, 
            self.encode_frame_cached, 
            frame, 
            quality
        )


class FastAPIHandler:
    """
    Optimized FastAPI handler with professional streaming capabilities.
    Features adaptive quality, frame caching, and connection management.
    """
    
    def __init__(self, app_controller):
        """Initialize with optimized streaming support."""
        # Core dependencies
        self.app_controller = app_controller
        self.video_handler = app_controller.video_handler
        self.telemetry_handler = app_controller.telemetry_handler
        
        # Streaming optimization
        self.stream_optimizer = StreamingOptimizer()
        
        # WebRTC Manager
        self.webrtc_manager = WebRTCManager(self.video_handler)
        
        # FastAPI app
        self.app = FastAPI(title="PixEagle API", version="2.0")
        self._setup_middleware()
        
        # Logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Define routes
        self.define_routes()
        
        # Streaming parameters
        self.frame_rate = Parameters.STREAM_FPS
        self.width = Parameters.STREAM_WIDTH
        self.height = Parameters.STREAM_HEIGHT
        self.quality = Parameters.STREAM_QUALITY
        self.frame_interval = 1.0 / self.frame_rate
        
        # Connection management
        self.http_connections: Set[str] = set()
        self.ws_connections: Dict[str, ClientConnection] = {}
        self.connection_lock = asyncio.Lock()
        
        # State
        self.is_shutting_down = False
        self.server = None
        
        # Performance monitoring
        self.stats = {
            'frames_sent': 0,
            'frames_dropped': 0,
            'total_bandwidth': 0,
            'active_connections': 0
        }
        
        # Background tasks will be started when the server starts
        self.background_tasks = []
        
        # Frame timing for rate limiting
        self.last_http_send_time = 0.0
        self.last_ws_send_time = 0.0
        
        # Frame lock for thread-safe frame access
        self.frame_lock = asyncio.Lock()
        
        # OSD processing flag
        self.processed_osd = Parameters.STREAM_PROCESSED_OSD
    
    def _setup_middleware(self):
        """Configure middleware with security best practices."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure for production
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
            max_age=3600
        )
    
    def define_routes(self):
        """Define all API routes."""
        # Streaming endpoints
        self.app.get("/video_feed")(self.video_feed)
        self.app.websocket("/ws/video_feed")(self.video_feed_websocket_optimized)
        self.app.websocket("/ws/webrtc_signaling")(self.webrtc_manager.signaling_handler)
        
        # Telemetry
        self.app.get("/telemetry/tracker_data")(self.tracker_data)
        self.app.get("/telemetry/follower_data")(self.follower_data)
        self.app.get("/status")(self.get_status)
        self.app.get("/stats")(self.get_streaming_stats)
        
        # Enhanced tracker schema endpoints
        self.app.get("/api/tracker/schema")(self.get_tracker_schema)
        self.app.get("/api/tracker/current-status")(self.get_current_tracker_status)
        self.app.get("/api/tracker/output")(self.get_tracker_output)
        self.app.get("/api/tracker/capabilities")(self.get_tracker_capabilities)
        self.app.get("/api/tracker/available-types")(self.get_available_tracker_types)
        self.app.get("/api/tracker/current-config")(self.get_current_tracker_config)
        self.app.post("/api/tracker/set-type")(self.set_tracker_type)
        self.app.get("/api/compatibility/report")(self.get_compatibility_report)
        self.app.get("/api/system/schema_info")(self.get_schema_info)

        # Debug endpoints
        self.app.get("/debug/coordinate_mapping")(self.get_coordinate_mapping_info)

        # Commands
        self.app.post("/commands/start_tracking")(self.start_tracking)
        self.app.post("/commands/stop_tracking")(self.stop_tracking)
        self.app.post("/commands/toggle_segmentation")(self.toggle_segmentation)
        self.app.post("/commands/redetect")(self.redetect)
        self.app.post("/commands/cancel_activities")(self.cancel_activities)
        self.app.post("/commands/start_offboard_mode")(self.start_offboard_mode)
        self.app.post("/commands/stop_offboard_mode")(self.stop_offboard_mode)
        self.app.post("/commands/quit")(self.quit)
        
        # Smart tracking
        self.app.post("/commands/toggle_smart_mode")(self.toggle_smart_mode)
        self.app.post("/commands/smart_click")(self.smart_click)
        
        # Follower API
        self.app.get("/api/follower/schema")(self.get_follower_schema)
        self.app.get("/api/follower/profiles")(self.get_follower_profiles)
        self.app.get("/api/follower/current-profile")(self.get_current_follower_profile)
        self.app.get("/api/follower/configured-mode")(self.get_configured_follower_mode)
        self.app.get("/api/follower/setpoints-status")(self.get_follower_setpoints_with_status)
        self.app.post("/api/follower/switch-profile")(self.switch_follower_profile)

        # Circuit breaker API endpoints
        self.app.get("/api/circuit-breaker/status")(self.get_circuit_breaker_status)
        self.app.post("/api/circuit-breaker/toggle")(self.toggle_circuit_breaker)
        self.app.get("/api/circuit-breaker/statistics")(self.get_circuit_breaker_statistics)
        self.app.post("/api/circuit-breaker/reset-statistics")(self.reset_circuit_breaker_statistics)
    
    async def video_feed(self):
        """Optimized HTTP MJPEG streaming with adaptive quality."""
        client_id = f"http_{time.time()}"
        
        # Check connection limit
        async with self.connection_lock:
            if len(self.http_connections) >= Parameters.HTTP_MAX_CONNECTIONS:
                raise HTTPException(status_code=503, detail="Max connections reached")
            self.http_connections.add(client_id)
        
        async def generate():
            """Optimized frame generator."""
            quality = Parameters.STREAM_QUALITY
            last_send_time = 0
            frame_count = 0
            start_time = time.time()
            
            try:
                while not self.is_shutting_down:
                    current_time = time.time()
                    
                    # Frame rate limiting
                    if (current_time - last_send_time) < self.frame_interval:
                        await asyncio.sleep(0.001)
                        continue
                    
                    # Get frame
                    frame = (self.video_handler.current_resized_osd_frame
                            if Parameters.STREAM_PROCESSED_OSD
                            else self.video_handler.current_resized_raw_frame)
                    
                    if frame is None:
                        await asyncio.sleep(0.01)
                        continue
                    
                    # Adaptive quality based on frame rate
                    if Parameters.ENABLE_ADAPTIVE_QUALITY:
                        actual_fps = frame_count / max(1, current_time - start_time)
                        if actual_fps < self.frame_rate * 0.8:
                            quality = max(Parameters.MIN_QUALITY, quality - Parameters.QUALITY_STEP)
                        elif actual_fps > self.frame_rate * 0.95:
                            quality = min(Parameters.MAX_QUALITY, quality + Parameters.QUALITY_STEP)
                    
                    # Encode with caching
                    try:
                        frame_bytes = await self.stream_optimizer.encode_frame_async(frame, quality)
                        
                        # Send frame
                        yield (b'--frame\r\n'
                              b'Content-Type: image/jpeg\r\n'
                              b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n'
                              b'\r\n' + frame_bytes + b'\r\n')
                        
                        last_send_time = current_time
                        frame_count += 1
                        self.stats['frames_sent'] += 1
                        self.stats['total_bandwidth'] += len(frame_bytes)
                        
                    except Exception as e:
                        self.logger.error(f"Frame encoding error: {e}")
                        self.stats['frames_dropped'] += 1
                        
            finally:
                # Cleanup
                async with self.connection_lock:
                    self.http_connections.discard(client_id)
                    self.stats['active_connections'] = len(self.http_connections) + len(self.ws_connections)
        
        return StreamingResponse(
            generate(), 
            media_type='multipart/x-mixed-replace; boundary=frame',
            headers={'Cache-Control': 'no-cache'}
        )
    
    async def video_feed_websocket_optimized(self, websocket: WebSocket):
        """Optimized WebSocket streaming with adaptive quality and queuing."""
        await websocket.accept()
        
        client_id = f"ws_{id(websocket)}_{time.time()}"
        
        # Check connection limit
        async with self.connection_lock:
            if len(self.ws_connections) >= Parameters.WS_MAX_CONNECTIONS:
                await websocket.close(code=1008, reason="Max connections reached")
                return
            
            # Register client
            self.ws_connections[client_id] = ClientConnection(
                id=client_id,
                connected_at=time.time(),
                last_frame_time=0,
                quality=Parameters.STREAM_QUALITY,
                frame_drops=0,
                bandwidth_estimate=0,
                frame_queue=deque(maxlen=Parameters.MAX_FRAME_QUEUE)
            )
        
        self.logger.info(f"WebSocket connected: {client_id}")
        
        try:
            client = self.ws_connections[client_id]
            send_task = asyncio.create_task(self._ws_send_frames(websocket, client))
            receive_task = asyncio.create_task(self._ws_receive_messages(websocket, client))
            
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [send_task, receive_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                
        except WebSocketDisconnect:
            self.logger.info(f"WebSocket disconnected: {client_id}")
        except Exception as e:
            self.logger.error(f"WebSocket error: {e}")
        finally:
            # Cleanup
            async with self.connection_lock:
                self.ws_connections.pop(client_id, None)
                self.stats['active_connections'] = len(self.http_connections) + len(self.ws_connections)
    
    async def _ws_send_frames(self, websocket: WebSocket, client: ClientConnection):
        """Send frames to WebSocket client with adaptive quality."""
        last_send_time = 0
        bytes_sent = 0
        time_window_start = time.time()
        
        while not self.is_shutting_down:
            current_time = time.time()
            
            # Frame rate limiting
            if (current_time - last_send_time) < self.frame_interval:
                await asyncio.sleep(0.001)
                continue
            
            # Get frame
            frame = (self.video_handler.current_resized_osd_frame
                    if Parameters.STREAM_PROCESSED_OSD
                    else self.video_handler.current_resized_raw_frame)
            
            if frame is None:
                await asyncio.sleep(0.01)
                continue
            
            # Adaptive quality based on bandwidth
            if Parameters.ENABLE_ADAPTIVE_QUALITY and current_time - time_window_start > 1.0:
                # Calculate bandwidth
                bandwidth = bytes_sent / (current_time - time_window_start)
                client.bandwidth_estimate = bandwidth
                
                # Adjust quality
                target_bytes_per_frame = bandwidth / self.frame_rate
                if target_bytes_per_frame < 10000:  # Less than 10KB per frame
                    client.quality = max(Parameters.MIN_QUALITY, client.quality - Parameters.QUALITY_STEP)
                elif target_bytes_per_frame > 50000:  # More than 50KB per frame
                    client.quality = min(Parameters.MAX_QUALITY, client.quality + Parameters.QUALITY_STEP)
                
                # Reset measurement window
                bytes_sent = 0
                time_window_start = current_time
            
            try:
                # Encode frame
                frame_bytes = await self.stream_optimizer.encode_frame_async(frame, client.quality)
                
                # Send frame with metadata
                message = {
                    'type': 'frame',
                    'timestamp': current_time,
                    'quality': client.quality,
                    'size': len(frame_bytes)
                }
                
                # Send metadata first
                await websocket.send_json(message)
                # Send binary frame
                await websocket.send_bytes(frame_bytes)
                
                last_send_time = current_time
                bytes_sent += len(frame_bytes)
                client.last_frame_time = current_time
                
                self.stats['frames_sent'] += 1
                self.stats['total_bandwidth'] += len(frame_bytes)
                
            except Exception as e:
                self.logger.error(f"Failed to send frame: {e}")
                client.frame_drops += 1
                self.stats['frames_dropped'] += 1
                break
    
    async def _ws_receive_messages(self, websocket: WebSocket, client: ClientConnection):
        """Handle incoming WebSocket messages."""
        try:
            while not self.is_shutting_down:
                message = await websocket.receive_json()
                
                # Handle quality adjustment requests
                if message.get('type') == 'quality':
                    requested_quality = message.get('quality')
                    if Parameters.MIN_QUALITY <= requested_quality <= Parameters.MAX_QUALITY:
                        client.quality = requested_quality
                        self.logger.debug(f"Client {client.id} requested quality: {requested_quality}")
                
                # Handle heartbeat
                elif message.get('type') == 'ping':
                    await websocket.send_json({'type': 'pong', 'timestamp': time.time()})
                    
        except WebSocketDisconnect:
            pass
        except Exception as e:
            self.logger.error(f"Error receiving WebSocket message: {e}")
    
    async def _heartbeat_task(self):
        """Send periodic heartbeats to WebSocket clients."""
        while not self.is_shutting_down:
            await asyncio.sleep(Parameters.WS_HEARTBEAT_INTERVAL)
            
            # Check for stale connections
            current_time = time.time()
            async with self.connection_lock:
                stale_clients = [
                    client_id for client_id, client in self.ws_connections.items()
                    if current_time - client.last_frame_time > Parameters.WS_HEARTBEAT_INTERVAL * 2
                ]
                
                for client_id in stale_clients:
                    self.logger.warning(f"Removing stale client: {client_id}")
                    self.ws_connections.pop(client_id, None)
    
    async def _stats_reporter(self):
        """Report streaming statistics periodically."""
        while not self.is_shutting_down:
            await asyncio.sleep(30)  # Report every 30 seconds
            
            if self.stats['frames_sent'] > 0:
                self.logger.info(
                    f"Streaming stats - Frames sent: {self.stats['frames_sent']}, "
                    f"Dropped: {self.stats['frames_dropped']}, "
                    f"Bandwidth: {self.stats['total_bandwidth'] / 1024 / 1024:.2f} MB, "
                    f"Connections: {self.stats['active_connections']}"
                )
    
    async def get_streaming_stats(self):
        """Get current streaming statistics."""
        ws_clients_info = []
        async with self.connection_lock:
            for client in self.ws_connections.values():
                ws_clients_info.append({
                    'id': client.id,
                    'connected_duration': time.time() - client.connected_at,
                    'quality': client.quality,
                    'frame_drops': client.frame_drops,
                    'bandwidth_kbps': client.bandwidth_estimate * 8 / 1024
                })
        
        return JSONResponse(content={
            'frames_sent': self.stats['frames_sent'],
            'frames_dropped': self.stats['frames_dropped'],
            'total_bandwidth_mb': self.stats['total_bandwidth'] / 1024 / 1024,
            'http_connections': len(self.http_connections),
            'websocket_connections': len(self.ws_connections),
            'websocket_clients': ws_clients_info,
            'cache_size': len(self.stream_optimizer.frame_cache),
            'uptime': time.time() - (self.server.started if self.server else time.time())
        })

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
            self.logger.info("🛑 Received request to quit the application.")

            # Set shutdown flag to stop main loop
            self.app_controller.shutdown_flag = True

            # Trigger shutdown sequence
            asyncio.create_task(self.app_controller.shutdown())

            # Stop FastAPI server
            if self.server:
                self.server.should_exit = True

            self.logger.info("✅ Shutdown initiated successfully")
            return {"status": "success", "details": "Application is shutting down."}
        except Exception as e:
            self.logger.error(f"❌ Error in quit: {e}")
            return {"status": "failure", "error": str(e)}

    async def _start_background_tasks(self):
        """Start background tasks now that we have an event loop."""
        self.background_tasks = []
        
        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_task())
        self.background_tasks.append(heartbeat_task)
        
        # Start stats reporter task
        stats_task = asyncio.create_task(self._stats_reporter())
        self.background_tasks.append(stats_task)
        
        self.logger.info("Started background tasks: heartbeat and stats reporter")

    async def start(self, host='0.0.0.0', port=None):
        """Start the FastAPI server."""
        port = port or Parameters.HTTP_STREAM_PORT
        
        # Start background tasks now that we have an event loop
        await self._start_background_tasks()
        
        config = uvicorn.Config(
            self.app, 
            host=host, 
            port=port, 
            log_level="info",
            access_log=False
        )
        self.server = uvicorn.Server(config)
        self.logger.info(f"Starting FastAPI server on {host}:{port}")
        await self.server.serve()
    
    async def stop(self):
        """Stop the FastAPI server."""
        self.is_shutting_down = True
        
        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()
        
        # Close all connections
        async with self.connection_lock:
            self.logger.info(f"Closing {len(self.ws_connections)} WebSocket connections")
            self.ws_connections.clear()
            self.http_connections.clear()
        
        # Shutdown encoder pool if exists
        if hasattr(self, 'stream_optimizer') and self.stream_optimizer:
            self.stream_optimizer.encoder_pool.shutdown(wait=True)
        
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

    # ==================== Enhanced Tracker Schema API Endpoints ====================
    
    async def get_tracker_output(self):
        """
        Enhanced API endpoint to get structured tracker output.
        
        Returns:
            JSONResponse: Structured tracker data with flexible schema support
        """
        try:
            self.logger.debug("Received request at /api/tracker/output")
            
            if not hasattr(self.app_controller, 'get_tracker_output'):
                raise HTTPException(status_code=501, detail="Enhanced tracker schema not available")
            
            tracker_output = self.app_controller.get_tracker_output()
            if not tracker_output:
                return JSONResponse(content={
                    'error': 'No tracker output available',
                    'tracking_active': False,
                    'timestamp': time.time()
                })
            
            # Convert to dict for JSON response
            output_dict = tracker_output.to_dict()
            
            # Add additional metadata
            output_dict['api_version'] = '2.0'
            output_dict['schema_version'] = 'flexible'
            
            self.logger.debug(f"Returning structured tracker output: {tracker_output.data_type.value}")
            return JSONResponse(content=output_dict)
            
        except Exception as e:
            self.logger.error(f"Error in /api/tracker/output: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_tracker_capabilities(self):
        """
        API endpoint to get tracker capabilities and supported features.
        
        Returns:
            JSONResponse: Tracker capabilities information
        """
        try:
            self.logger.debug("Received request at /api/tracker/capabilities")
            
            if not hasattr(self.app_controller, 'get_tracker_capabilities'):
                return JSONResponse(content={
                    'error': 'Capabilities API not available',
                    'legacy_mode': True
                })
            
            capabilities = self.app_controller.get_tracker_capabilities()
            if not capabilities:
                return JSONResponse(content={
                    'error': 'No active tracker',
                    'tracker_active': False
                })
            
            # Add system information
            result = {
                'tracker_capabilities': capabilities,
                'system_info': {
                    'tracker_active': bool(self.app_controller.tracker),
                    'tracker_class': self.app_controller.tracker.__class__.__name__ if self.app_controller.tracker else None,
                    'api_version': '2.0',
                    'timestamp': time.time()
                }
            }
            
            self.logger.debug(f"Returning tracker capabilities")
            return JSONResponse(content=result)
            
        except Exception as e:
            self.logger.error(f"Error in /api/tracker/capabilities: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_tracker_schema(self):
        """
        Endpoint to get the complete tracker data schema.
        
        Returns:
            dict: Complete tracker schema including all data types and validation rules.
        """
        try:
            # Read the schema file directly
            import yaml
            with open('configs/tracker_schemas.yaml', 'r') as f:
                schema = yaml.safe_load(f)
            return JSONResponse(content=schema)
        except Exception as e:
            self.logger.error(f"Error getting tracker schema: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_current_tracker_status(self):
        """
        Endpoint to get current tracker status with real-time data fields.
        
        Returns:
            dict: Current tracker status with schema-driven field information.
        """
        try:
            tracker_output = self.app_controller.get_tracker_output()
            
            if not tracker_output:
                return JSONResponse(content={
                    'active': False,
                    'tracker_type': None,
                    'data_type': None,
                    'fields': {},
                    'timestamp': time.time()
                })
            
            # Get schema information for current data type
            data_type = tracker_output.data_type.value
            
            # Extract available fields dynamically with enhanced type detection
            available_fields = {}
            output_dict = tracker_output.to_dict()

            # Filter out None values and system fields
            system_fields = {'timestamp', 'tracking_active', 'tracker_id', 'data_type', 'metadata'}
            for key, value in output_dict.items():
                if key not in system_fields and value is not None:
                    # Enhanced field processing with specific gimbal angle handling
                    field_info = self._get_enhanced_field_info(key, value, data_type)
                    available_fields[key] = field_info

            # Also include important raw_data fields for display (especially for gimbal trackers)
            if tracker_output.raw_data:
                important_raw_fields = ['tracking', 'tracking_status', 'system', 'yaw', 'pitch', 'roll']
                for raw_field in important_raw_fields:
                    if raw_field in tracker_output.raw_data and tracker_output.raw_data[raw_field] is not None:
                        field_info = self._get_enhanced_field_info(raw_field, tracker_output.raw_data[raw_field], data_type)
                        available_fields[raw_field] = field_info
            
            tracker_class = self.app_controller.tracker.__class__.__name__ if self.app_controller.tracker else 'Unknown'
            
            return JSONResponse(content={
                'active': tracker_output.tracking_active,
                'tracker_type': tracker_class,
                'data_type': data_type,
                'fields': available_fields,
                'raw_data': tracker_output.raw_data,  # Include raw_data for gimbal status
                'smart_mode': getattr(self.app_controller, 'smart_mode_active', False),
                'timestamp': time.time()
            })
            
        except Exception as e:
            self.logger.error(f"Error getting current tracker status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _get_enhanced_field_info(self, field_name: str, value: any, data_type: str) -> dict:
        """
        Get enhanced field information with proper type detection for React display.

        Args:
            field_name: Name of the field
            value: Field value
            data_type: Tracker data type

        Returns:
            dict: Enhanced field information
        """
        base_type = type(value).__name__

        # Special handling for gimbal angular data (yaw, pitch, roll)
        if field_name == 'angular' and isinstance(value, (tuple, list)) and len(value) == 3:
            return {
                'value': value,
                'type': 'angular_3d',
                'display_name': 'Gimbal Angles (Y, P, R)',
                'description': 'Gimbal yaw, pitch, roll angles in degrees',
                'units': '°',
                'format': 'tuple_3d',
                'components': ['yaw', 'pitch', 'roll']
            }

        # Enhanced 2D position handling
        elif field_name in ['position_2d', 'normalized_position'] and isinstance(value, (tuple, list)) and len(value) == 2:
            return {
                'value': value,
                'type': 'position_2d',
                'display_name': 'Target Position (X, Y)',
                'description': 'Normalized 2D position coordinates',
                'units': 'normalized',
                'format': 'tuple_2d',
                'components': ['x', 'y']
            }

        # Bounding box handling
        elif field_name in ['bbox', 'normalized_bbox'] and isinstance(value, (tuple, list)) and len(value) == 4:
            return {
                'value': value,
                'type': 'bbox',
                'display_name': 'Bounding Box',
                'description': 'Target bounding box coordinates',
                'units': 'pixels' if 'normalized' not in field_name else 'normalized',
                'format': 'bbox',
                'components': ['x', 'y', 'width', 'height']
            }

        # Confidence score handling
        elif field_name == 'confidence':
            return {
                'value': value,
                'type': 'confidence',
                'display_name': 'Tracking Confidence',
                'description': 'Tracker confidence score',
                'units': '%' if isinstance(value, (int, float)) else '',
                'format': 'percentage',
                'range': [0.0, 1.0] if isinstance(value, (int, float)) else None
            }

        # Velocity handling
        elif field_name == 'velocity' and isinstance(value, (tuple, list)):
            return {
                'value': value,
                'type': 'velocity',
                'display_name': 'Target Velocity',
                'description': 'Target velocity vector',
                'units': 'px/s' if len(value) == 2 else 'units/s',
                'format': f'tuple_{len(value)}d',
                'components': ['vx', 'vy'] if len(value) == 2 else ['vx', 'vy', 'vz']
            }

        # Generic tuple/list handling
        elif isinstance(value, (tuple, list)):
            return {
                'value': value,
                'type': f'{base_type}_{len(value)}d',
                'display_name': field_name.replace('_', ' ').title(),
                'description': f'{len(value)}-dimensional {field_name} data',
                'format': f'{base_type}_{len(value)}d',
                'components': [f'component_{i}' for i in range(len(value))]
            }

        # Tracking status handling for gimbal trackers
        elif field_name in ['tracking', 'tracking_status'] and isinstance(value, str):
            return {
                'value': value,
                'type': 'tracking_status',
                'display_name': 'Tracking Status',
                'description': 'Current gimbal tracking state',
                'format': 'status_string',
                'status_color': 'success' if 'ACTIVE' in value.upper() else 'warning' if 'SELECTION' in value.upper() else 'error'
            }

        # Gimbal system/coordinate system handling
        elif field_name == 'system' and isinstance(value, str):
            return {
                'value': value,
                'type': 'coordinate_system',
                'display_name': 'Coordinate System',
                'description': 'Gimbal coordinate reference system',
                'format': 'system_string'
            }

        # Default handling for other types
        else:
            return {
                'value': value,
                'type': base_type.lower(),
                'display_name': field_name.replace('_', ' ').title(),
                'description': f'{field_name} field data',
                'format': base_type.lower()
            }

    async def get_compatibility_report(self):
        """
        API endpoint to get tracker-follower compatibility analysis.
        
        Returns:
            JSONResponse: Detailed compatibility report
        """
        try:
            self.logger.debug("Received request at /api/compatibility/report")
            
            if not hasattr(self.app_controller, 'get_system_compatibility_report'):
                return JSONResponse(content={
                    'error': 'Compatibility API not available',
                    'legacy_mode': True
                })
            
            report = self.app_controller.get_system_compatibility_report()
            
            # Add API metadata
            report['api_version'] = '2.0'
            report['report_generated_at'] = time.time()
            
            self.logger.debug(f"Returning compatibility report: compatible={report.get('compatible', False)}")
            return JSONResponse(content=report)
            
        except Exception as e:
            self.logger.error(f"Error in /api/compatibility/report: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_schema_info(self):
        """
        API endpoint to get information about the tracker schema system.
        
        Returns:
            JSONResponse: Schema system information
        """
        try:
            self.logger.debug("Received request at /api/system/schema_info")
            
            # Get available tracker data types
            data_types = [dt.value for dt in TrackerDataType]
            
            # Get current system status
            system_info = {
                'schema_version': '2.0',
                'api_version': '2.0',
                'supported_data_types': data_types,
                'data_type_descriptions': {
                    'position_2d': 'Standard 2D position tracking',
                    'position_3d': '3D position with depth information',
                    'angular': 'Bearing and elevation angles',
                    'bbox_confidence': 'Bounding box with confidence metrics',
                    'velocity_aware': 'Position with velocity estimates',
                    'external': 'External data source (e.g., radar)',
                    'multi_target': 'Multiple target tracking'
                },
                'current_tracker': {
                    'active': bool(self.app_controller.tracker),
                    'class_name': self.app_controller.tracker.__class__.__name__ if self.app_controller.tracker else None,
                    'enhanced_schema': hasattr(self.app_controller.tracker, 'get_output') if self.app_controller.tracker else False
                },
                'current_follower': {
                    'active': bool(self.app_controller.follower),
                    'class_name': self.app_controller.follower.__class__.__name__ if self.app_controller.follower else None,
                    'enhanced_schema': hasattr(self.app_controller.follower, 'validate_tracker_compatibility') if self.app_controller.follower else False
                },
                'backward_compatibility': {
                    'enabled': True,
                    'legacy_endpoints_available': True,
                    'automatic_fallback': True
                },
                'timestamp': time.time()
            }
            
            self.logger.debug("Returning schema system information")
            return JSONResponse(content=system_info)
            
        except Exception as e:
            self.logger.error(f"Error in /api/system/schema_info: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Tracker Selection & Management API Endpoints ====================
    
    async def get_available_tracker_types(self):
        """
        Endpoint to get available tracker types/algorithms.
        
        Returns:
            dict: Available tracker types with descriptions.
        """
        try:
            from classes.trackers.tracker_factory import create_tracker
            import inspect
            
            available_trackers = {
                'CSRT': {
                    'name': 'CSRT',
                    'display_name': 'CSRT Tracker',
                    'description': 'Channel and Spatial Reliability Tracker - Classical CV algorithm',
                    'data_type': 'POSITION_2D',
                    'smart_mode': False,
                    'suitable_for': ['Single target', 'Stable tracking', 'Classical computer vision']
                },
                'ParticleFilter': {
                    'name': 'ParticleFilter',
                    'display_name': 'Particle Filter',
                    'description': 'Particle Filter Tracker - Probabilistic tracking',
                    'data_type': 'POSITION_2D',
                    'smart_mode': False,
                    'suitable_for': ['Complex movements', 'Occlusions', 'Probabilistic tracking']
                },
                'Gimbal': {
                    'name': 'Gimbal',
                    'display_name': 'Gimbal Tracker',
                    'description': 'External gimbal UDP angle tracker - Real-time gimbal angle data',
                    'data_type': 'GIMBAL_ANGLES',
                    'smart_mode': False,
                    'suitable_for': ['External gimbal', 'Real-time angles', 'High precision tracking']
                },
                'SmartTracker': {
                    'name': 'SmartTracker',
                    'display_name': 'Smart Tracker (YOLO)',
                    'description': 'AI-powered YOLO-based smart tracking system',
                    'data_type': 'BBOX_CONFIDENCE',
                    'smart_mode': True,
                    'suitable_for': ['Multiple targets', 'AI detection', 'Complex scenarios']
                }
            }
            
            # Get current configured tracker
            current_tracker = getattr(self.app_controller, 'current_tracker_type', 'CSRT')
            
            return JSONResponse(content={
                'available_trackers': available_trackers,
                'current_configured': current_tracker,
                'current_active': self.app_controller.tracker.__class__.__name__ if self.app_controller.tracker else None,
                'smart_mode_active': getattr(self.app_controller, 'smart_mode_active', False)
            })
            
        except Exception as e:
            self.logger.error(f"Error getting available tracker types: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def set_tracker_type(self, request: dict):
        """
        Endpoint to set/change the tracker type.
        
        Args:
            request (dict): Request body containing tracker_type
            
        Returns:
            dict: Success/failure response
        """
        try:
            tracker_type = request.get('tracker_type')
            if not tracker_type:
                raise HTTPException(status_code=400, detail="tracker_type is required")
            
            # Validate tracker type
            valid_types = ['CSRT', 'ParticleFilter', 'Gimbal', 'SmartTracker']
            if tracker_type not in valid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid tracker type '{tracker_type}'. Available: {valid_types}"
                )
            
            # Check if tracker is currently active
            is_tracking_active = (
                hasattr(self.app_controller, 'tracker') and 
                self.app_controller.tracker is not None and
                getattr(self.app_controller, 'tracking_active', False)
            )
            
            old_tracker_type = getattr(self.app_controller, 'current_tracker_type', 'CSRT')
            
            if tracker_type == 'SmartTracker':
                # Handle smart mode activation
                if not getattr(self.app_controller, 'smart_mode_active', False):
                    # Enable smart mode
                    self.app_controller.smart_mode_active = True
                    self.app_controller.current_tracker_type = 'SmartTracker'
                    
                    if is_tracking_active:
                        # Need to restart tracking with smart mode
                        return JSONResponse(content={
                            'status': 'success',
                            'action': 'smart_mode_enabled',
                            'old_tracker': old_tracker_type,
                            'new_tracker': tracker_type,
                            'message': 'Smart mode enabled. Stop and restart tracking to activate smart tracker.',
                            'requires_restart': True
                        })
                    else:
                        return JSONResponse(content={
                            'status': 'success',
                            'action': 'configured_smart',
                            'old_tracker': old_tracker_type,
                            'new_tracker': tracker_type,
                            'message': 'Smart tracker configured. Will activate when tracking starts.'
                        })
                else:
                    return JSONResponse(content={
                        'status': 'success',
                        'action': 'already_smart',
                        'message': 'Smart tracker already active'
                    })
            else:
                # Handle classic tracker selection
                if getattr(self.app_controller, 'smart_mode_active', False):
                    # Disable smart mode
                    self.app_controller.smart_mode_active = False
                
                self.app_controller.current_tracker_type = tracker_type
                
                if is_tracking_active:
                    # Need to restart tracking with new tracker
                    return JSONResponse(content={
                        'status': 'success',
                        'action': 'classic_tracker_set',
                        'old_tracker': old_tracker_type,
                        'new_tracker': tracker_type,
                        'message': f'Tracker set to {tracker_type}. Stop and restart tracking to activate new tracker.',
                        'requires_restart': True
                    })
                else:
                    return JSONResponse(content={
                        'status': 'success',
                        'action': 'configured_classic',
                        'old_tracker': old_tracker_type,
                        'new_tracker': tracker_type,
                        'message': f'{tracker_type} tracker configured. Will activate when tracking starts.'
                    })
                    
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error setting tracker type: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_current_tracker_config(self):
        """
        Endpoint to get the current tracker configuration.
        
        Returns:
            dict: Current tracker configuration and status.
        """
        try:
            current_type = getattr(self.app_controller, 'current_tracker_type', 'CSRT')
            is_smart_active = getattr(self.app_controller, 'smart_mode_active', False)
            is_tracking_active = (
                hasattr(self.app_controller, 'tracker') and 
                self.app_controller.tracker is not None and
                getattr(self.app_controller, 'tracking_active', False)
            )
            
            # Determine expected data type based on tracker
            expected_data_type = 'BBOX_CONFIDENCE' if is_smart_active else 'POSITION_2D'
            
            return JSONResponse(content={
                'configured_tracker': current_type,
                'smart_mode_active': is_smart_active,
                'tracking_active': is_tracking_active,
                'expected_data_type': expected_data_type,
                'active_tracker_class': self.app_controller.tracker.__class__.__name__ if self.app_controller.tracker else None,
                'status': 'active' if is_tracking_active else 'configured',
                'timestamp': time.time()
            })
            
        except Exception as e:
            self.logger.error(f"Error getting current tracker config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_coordinate_mapping_info(self):
        """
        Debug endpoint to validate coordinate mapping configuration.

        Returns:
            dict: Coordinate mapping validation information
        """
        try:
            # Get validation from video handler
            validation = self.video_handler.validate_coordinate_mapping()

            # Add FastAPI handler info
            validation['fastapi_info'] = {
                'frame_rate': self.frame_rate,
                'streaming_width': self.width,
                'streaming_height': self.height,
                'quality': self.quality
            }

            # Add sample coordinate transformation
            sample_click = {'x': 0.5, 'y': 0.5}  # Center of screen
            if validation['is_valid']:
                sample_pixel_x = int(sample_click['x'] * self.video_handler.width)
                sample_pixel_y = int(sample_click['y'] * self.video_handler.height)
                validation['sample_transform'] = {
                    'dashboard_click': sample_click,
                    'pixel_coordinates': {'x': sample_pixel_x, 'y': sample_pixel_y},
                    'explanation': f"Dashboard center click maps to pixel ({sample_pixel_x}, {sample_pixel_y})"
                }
            else:
                validation['sample_transform'] = {
                    'error': 'Cannot provide sample due to validation failures'
                }

            return validation

        except Exception as e:
            self.logger.error(f"Error getting coordinate mapping info: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_follower_setpoints_with_status(self):
        """
        Get current follower setpoints with circuit breaker status.

        This endpoint provides complete visibility into:
        - Current setpoint values
        - Circuit breaker status (SAFE_MODE vs LIVE_MODE)
        - Whether commands are being sent to PX4 or just logged
        - Circuit breaker statistics when active

        Returns:
            dict: Comprehensive follower status with circuit breaker info
        """
        try:
            # Check if follower is actively engaged
            has_active_follower = (
                hasattr(self.app_controller, 'follower') and
                self.app_controller.follower is not None and
                self.app_controller.following_active
            )

            if not has_active_follower:
                # Import circuit breaker to check status even when not following
                try:
                    from classes.circuit_breaker import FollowerCircuitBreaker
                    circuit_breaker_active = FollowerCircuitBreaker.is_active()
                except ImportError:
                    circuit_breaker_active = True  # FAIL SAFE

                return JSONResponse(content={
                    'follower_active': False,
                    'message': 'No active follower',
                    'configured_mode': Parameters.FOLLOWER_MODE,
                    'circuit_breaker': {
                        'active': circuit_breaker_active,
                        'status': 'SAFE_MODE' if circuit_breaker_active else 'LIVE_MODE'
                    },
                    'timestamp': time.time()
                })

            # Get follower setpoints with circuit breaker status
            follower = self.app_controller.follower
            if hasattr(follower, 'setpoint_handler') and follower.setpoint_handler:
                setpoint_data = follower.setpoint_handler.get_fields_with_status()

                # Add follower-specific information
                setpoint_data.update({
                    'follower_active': True,
                    'follower_type': follower.__class__.__name__,
                    'configured_mode': Parameters.FOLLOWER_MODE,
                    'following_engaged': self.app_controller.following_active
                })

                return JSONResponse(content=setpoint_data)
            else:
                return JSONResponse(content={
                    'follower_active': True,
                    'follower_type': follower.__class__.__name__,
                    'error': 'Follower has no setpoint handler',
                    'timestamp': time.time()
                })

        except Exception as e:
            self.logger.error(f"Error getting follower setpoints with status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Circuit Breaker API Endpoints ====================

    async def get_circuit_breaker_status(self):
        """
        Get current circuit breaker status and configuration.

        Returns:
            dict: Circuit breaker status, availability and statistics
        """
        try:
            if not CIRCUIT_BREAKER_AVAILABLE:
                return JSONResponse(content={
                    'available': False,
                    'error': 'Circuit breaker system not available',
                    'message': 'FollowerCircuitBreaker module could not be imported'
                })

            is_active = FollowerCircuitBreaker.is_active()
            statistics = FollowerCircuitBreaker.get_statistics()

            return JSONResponse(content={
                'available': True,
                'active': is_active,
                'status': 'testing' if is_active else 'operational',
                'configuration': {
                    'parameter_name': 'FOLLOWER_CIRCUIT_BREAKER',
                    'current_value': is_active,
                    'description': 'Global circuit breaker for follower testing'
                },
                'statistics': statistics,
                'message': 'Circuit breaker active - commands logged not executed' if is_active else 'Circuit breaker disabled - normal operation',
                'timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error getting circuit breaker status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def toggle_circuit_breaker(self):
        """
        Toggle circuit breaker on/off.

        Returns:
            dict: New circuit breaker status
        """
        try:
            if not CIRCUIT_BREAKER_AVAILABLE:
                raise HTTPException(
                    status_code=503,
                    detail="Circuit breaker system not available"
                )

            # Get current state
            old_state = FollowerCircuitBreaker.is_active()

            # Toggle the parameter
            Parameters.FOLLOWER_CIRCUIT_BREAKER = not old_state
            new_state = FollowerCircuitBreaker.is_active()

            # Reset statistics when enabling
            if new_state and not old_state:
                FollowerCircuitBreaker.reset_statistics()
                self.logger.info("Circuit breaker ENABLED - Follower commands will be logged instead of executed")
            elif not new_state and old_state:
                self.logger.info("Circuit breaker DISABLED - Normal follower operation resumed")

            return JSONResponse(content={
                'status': 'success',
                'action': 'enabled' if new_state else 'disabled',
                'active': new_state,
                'old_state': old_state,
                'new_state': new_state,
                'message': f'Circuit breaker {"enabled" if new_state else "disabled"}',
                'statistics_reset': new_state and not old_state,
                'timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error toggling circuit breaker: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_circuit_breaker_statistics(self):
        """
        Get detailed circuit breaker statistics and telemetry.

        Returns:
            dict: Comprehensive circuit breaker statistics
        """
        try:
            if not CIRCUIT_BREAKER_AVAILABLE:
                raise HTTPException(
                    status_code=503,
                    detail="Circuit breaker system not available"
                )

            statistics = FollowerCircuitBreaker.get_statistics()

            # Add additional API metadata
            response_data = {
                'circuit_breaker': statistics,
                'api_info': {
                    'endpoint': '/api/circuit-breaker/statistics',
                    'api_version': '2.0',
                    'timestamp': time.time(),
                    'data_freshness': 'real-time'
                },
                'usage_summary': {
                    'testing_mode': statistics['circuit_breaker_active'],
                    'total_intercepted_commands': statistics['total_commands'],
                    'unique_followers_tested': len(statistics['followers_tested']),
                    'command_diversity': len(statistics['command_types'])
                }
            }

            # Add performance metrics if active
            if statistics['circuit_breaker_active']:
                if statistics['command_rate_hz'] > 0:
                    response_data['performance'] = {
                        'commands_per_second': statistics['command_rate_hz'],
                        'testing_efficiency': 'high' if statistics['command_rate_hz'] > 5 else 'medium' if statistics['command_rate_hz'] > 1 else 'low',
                        'last_activity': statistics['last_command_time']
                    }

            return JSONResponse(content=response_data)

        except Exception as e:
            self.logger.error(f"Error getting circuit breaker statistics: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def reset_circuit_breaker_statistics(self):
        """
        Reset circuit breaker statistics and counters.

        Returns:
            dict: Reset operation status
        """
        try:
            if not CIRCUIT_BREAKER_AVAILABLE:
                raise HTTPException(
                    status_code=503,
                    detail="Circuit breaker system not available"
                )

            # Get current statistics before reset
            old_stats = FollowerCircuitBreaker.get_statistics()

            # Reset statistics
            FollowerCircuitBreaker.reset_statistics()

            # Get new statistics after reset
            new_stats = FollowerCircuitBreaker.get_statistics()

            self.logger.info("Circuit breaker statistics reset")

            return JSONResponse(content={
                'status': 'success',
                'action': 'statistics_reset',
                'message': 'Circuit breaker statistics have been reset',
                'old_statistics': {
                    'total_commands': old_stats['total_commands'],
                    'followers_tested': len(old_stats['followers_tested']),
                    'elapsed_time': old_stats['elapsed_time_seconds']
                },
                'new_statistics': new_stats,
                'reset_timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error resetting circuit breaker statistics: {e}")
            raise HTTPException(status_code=500, detail=str(e))