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
from typing import Any, Dict, Optional, Set, Tuple, List
from collections import deque
from dataclasses import dataclass
import json
from classes.parameters import Parameters
from classes.config_service import ConfigService
import uvicorn
from classes.webrtc_manager import WebRTCManager
from classes.setpoint_handler import SetpointHandler
from classes.follower import FollowerFactory
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.yolo_model_manager import YOLOModelManager

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


# Config API Models
class ConfigParameterUpdate(BaseModel):
    """Request model for updating a single parameter."""
    value: Optional[str | int | float | bool | list | dict] = None


class ConfigSectionUpdate(BaseModel):
    """Request model for updating multiple parameters in a section."""
    parameters: Dict[str, Optional[str | int | float | bool | list | dict]]


class ConfigImportRequest(BaseModel):
    """Request model for importing configuration."""
    data: Dict[str, Any]  # Accept any nested structure
    merge_mode: str = "merge"  # "merge" or "replace"


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


class RateLimiter:
    """Simple in-memory rate limiter for API endpoints."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> Tuple[bool, Optional[int]]:
        """
        Check if request is allowed for given key.

        Returns:
            Tuple of (allowed: bool, retry_after: Optional[int])
        """
        now = time.time()
        with self._lock:
            if key not in self._requests:
                self._requests[key] = deque()

            # Clean old entries
            while self._requests[key] and self._requests[key][0] < now - self.window_seconds:
                self._requests[key].popleft()

            # Check limit
            if len(self._requests[key]) >= self.max_requests:
                oldest = self._requests[key][0]
                retry_after = int(oldest + self.window_seconds - now) + 1
                return False, retry_after

            # Record request
            self._requests[key].append(now)
            return True, None


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

        # Rate limiter for config write endpoints (10 requests per minute)
        self.config_rate_limiter = RateLimiter(max_requests=60, window_seconds=60)  # 1/sec average for private system

        # WebRTC Manager
        self.webrtc_manager = WebRTCManager(self.video_handler)

        # YOLO Model Manager
        self.yolo_model_manager = YOLOModelManager()

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
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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
        self.app.get("/api/follower/health")(self.get_follower_health)
        self.app.post("/api/follower/restart")(self.restart_follower)  # Hot-reload: recreate follower with fresh config

        # Tracker Selector API (mirroring follower API pattern)
        self.app.get("/api/tracker/available")(self.get_available_trackers)
        self.app.get("/api/tracker/current")(self.get_current_tracker)
        self.app.post("/api/tracker/switch")(self.switch_tracker)
        self.app.post("/api/tracker/restart")(self.restart_tracker)  # Hot-reload: reinitialize tracker with fresh config

        # YOLO Model Management API
        self.app.get("/api/yolo/models")(self.get_yolo_models)
        self.app.post("/api/yolo/switch-model")(self.switch_yolo_model)
        self.app.post("/api/yolo/upload")(self.upload_yolo_model)
        self.app.post("/api/yolo/delete/{model_id}")(self.delete_yolo_model)

        # Circuit breaker API endpoints
        self.app.get("/api/circuit-breaker/status")(self.get_circuit_breaker_status)
        self.app.post("/api/circuit-breaker/toggle")(self.toggle_circuit_breaker)
        self.app.post("/api/circuit-breaker/toggle-safety")(self.toggle_circuit_breaker_safety_bypass)
        self.app.get("/api/circuit-breaker/statistics")(self.get_circuit_breaker_statistics)
        self.app.post("/api/circuit-breaker/reset-statistics")(self.reset_circuit_breaker_statistics)

        # OSD Control API endpoints
        self.app.get("/api/osd/status")(self.get_osd_status)
        self.app.post("/api/osd/toggle")(self.toggle_osd)
        self.app.get("/api/osd/presets")(self.get_osd_presets)
        self.app.post("/api/osd/preset/{preset_name}")(self.load_osd_preset)

        # Safety configuration API endpoints (v3.5.0+)
        self.app.get("/api/safety/config")(self.get_safety_config)
        self.app.get("/api/safety/limits/{follower_name}")(self.get_follower_safety_limits)
        # Note: /api/safety/vehicle-profiles removed in v4.0.0 (was deprecated in v3.6.0)

        # Enhanced safety/config endpoints (v5.0.0+)
        self.app.get("/api/config/effective-limits")(self.get_effective_limits)
        self.app.get("/api/config/sections/relevant")(self.get_relevant_sections)
        self.app.get("/api/follower/current-mode")(self.get_current_follower_mode)

        # Configuration management API (v4.0.0+)
        # Schema & metadata
        self.app.get("/api/config/schema")(self.get_config_schema)
        self.app.get("/api/config/schema/{section}")(self.get_config_section_schema)
        self.app.get("/api/config/sections")(self.get_config_sections)
        self.app.get("/api/config/categories")(self.get_config_categories)
        # Read configuration
        self.app.get("/api/config/current")(self.get_current_config)
        self.app.get("/api/config/current/{section}")(self.get_current_config_section)
        self.app.get("/api/config/default")(self.get_default_config)
        self.app.get("/api/config/default/{section}")(self.get_default_config_section)
        # Write configuration
        self.app.put("/api/config/{section}/{parameter}")(self.update_config_parameter)
        self.app.put("/api/config/{section}")(self.update_config_section)
        self.app.post("/api/config/validate")(self.validate_config_value)
        # Diff & comparison
        self.app.get("/api/config/diff")(self.get_config_diff)
        self.app.post("/api/config/diff")(self.compare_configs)
        # Defaults sync (v5.4.0+)
        self.app.get("/api/config/defaults-sync")(self.get_defaults_sync)
        # Revert operations
        self.app.post("/api/config/revert")(self.revert_config_to_default)
        self.app.post("/api/config/revert/{section}")(self.revert_section_to_default)
        self.app.post("/api/config/revert/{section}/{parameter}")(self.revert_parameter_to_default)
        # Backup & history
        self.app.get("/api/config/history")(self.get_config_backup_history)
        self.app.post("/api/config/restore/{backup_id}")(self.restore_config_backup)
        # Import/export
        self.app.get("/api/config/export")(self.export_config)
        self.app.post("/api/config/import")(self.import_config)
        # Search
        self.app.get("/api/config/search")(self.search_config_parameters)
        # Audit log
        self.app.get("/api/config/audit")(self.get_config_audit_log)

        # System management
        self.app.post("/api/system/restart")(self.restart_backend)
        self.app.get("/api/system/status")(self.get_system_status)
        self.app.get("/api/system/config")(self.get_frontend_config)

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
        Robust endpoint to start the offboard mode for PX4.

        Features:
        - Automatic state validation
        - Auto-restart if already active
        - Comprehensive error handling
        - Detailed operation logging
        - Thread-safe execution

        This endpoint can be called from:
        - UI buttons
        - Direct API calls
        - External scripts
        - Automation systems

        Returns:
            dict: Status of the operation with detailed steps and any errors
                {
                    "status": "success" | "failure",
                    "details": {
                        "steps": [...],
                        "errors": [...],
                        "auto_stopped": bool,
                        "initial_state": str,
                        "final_state": str,
                        "execution_time_ms": float
                    },
                    "error": str (only if status is "failure")
                }
        """
        import time
        start_time = time.time()

        try:
            # Log initial state for debugging
            initial_state = "active" if self.app_controller.following_active else "inactive"
            self.logger.info(f"📥 API: Start offboard mode requested (current state: {initial_state})")

            # Pre-flight validation checks
            validation_errors = []

            # Check if PX4 interface is initialized
            if not hasattr(self.app_controller, 'px4_interface'):
                validation_errors.append("PX4 interface not initialized")

            # Check if tracker is available
            if not hasattr(self.app_controller, 'tracker'):
                validation_errors.append("Tracker not initialized")

            # Check if video handler is available
            if not hasattr(self.app_controller, 'video_handler'):
                validation_errors.append("Video handler not initialized")

            if validation_errors:
                error_msg = f"Pre-flight validation failed: {', '.join(validation_errors)}"
                self.logger.error(f"❌ {error_msg}")
                return {
                    "status": "failure",
                    "error": error_msg,
                    "details": {
                        "steps": [],
                        "errors": validation_errors,
                        "auto_stopped": False,
                        "initial_state": initial_state,
                        "final_state": initial_state
                    }
                }

            # Call the controller's connect_px4 method
            # This method handles:
            # - Thread-safe state transitions
            # - Auto-stop if already active
            # - Follower creation and initialization
            # - Offboard mode activation
            # - Error recovery and cleanup
            result = await self.app_controller.connect_px4()

            # Determine final state
            final_state = "active" if self.app_controller.following_active else "inactive"
            execution_time_ms = (time.time() - start_time) * 1000

            # Enhance result with additional metadata
            result["initial_state"] = initial_state
            result["final_state"] = final_state
            result["execution_time_ms"] = round(execution_time_ms, 2)

            # Log success with details
            if result.get("auto_stopped", False):
                self.logger.info(
                    f"✅ API: Offboard mode restarted successfully "
                    f"({initial_state} → {final_state}, {execution_time_ms:.0f}ms)"
                )
            else:
                self.logger.info(
                    f"✅ API: Offboard mode started successfully "
                    f"({initial_state} → {final_state}, {execution_time_ms:.0f}ms)"
                )

            # Log any warnings if errors occurred but operation succeeded
            if result.get("errors"):
                self.logger.warning(f"⚠️ Operation succeeded with {len(result['errors'])} warnings")

            return {"status": "success", "details": result}

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            self.logger.error(f"❌ API: Error in start_offboard_mode: {error_msg}")
            self.logger.error(f"Exception type: {type(e).__name__}")

            # Log stack trace for debugging
            import traceback
            self.logger.debug(f"Stack trace:\n{traceback.format_exc()}")

            # Attempt to determine final state even after error
            try:
                final_state = "active" if self.app_controller.following_active else "inactive"
            except:
                final_state = "unknown"

            return {
                "status": "failure",
                "error": error_msg,
                "details": {
                    "steps": [],
                    "errors": [error_msg],
                    "auto_stopped": False,
                    "initial_state": initial_state if 'initial_state' in locals() else "unknown",
                    "final_state": final_state,
                    "execution_time_ms": round(execution_time_ms, 2),
                    "exception_type": type(e).__name__
                }
            }

    async def stop_offboard_mode(self):
        """
        Robust endpoint to stop the offboard mode for PX4.

        Features:
        - Idempotent operation (safe to call multiple times)
        - Comprehensive cleanup
        - Thread-safe execution
        - Detailed operation logging
        - Graceful error handling

        This endpoint can be called from:
        - UI buttons
        - Direct API calls
        - External scripts
        - Automation systems
        - Emergency shutdown procedures

        Returns:
            dict: Status of the operation with detailed steps and any errors
                {
                    "status": "success" | "failure",
                    "details": {
                        "steps": [...],
                        "errors": [...],
                        "initial_state": str,
                        "final_state": str,
                        "execution_time_ms": float,
                        "was_active": bool
                    },
                    "error": str (only if status is "failure")
                }
        """
        import time
        start_time = time.time()

        try:
            # Log initial state
            initial_state = "active" if self.app_controller.following_active else "inactive"
            was_active = self.app_controller.following_active

            self.logger.info(f"📥 API: Stop offboard mode requested (current state: {initial_state})")

            # Idempotency check - it's OK to stop when already stopped
            if not was_active:
                self.logger.info("ℹ️ API: Follower already inactive, nothing to stop")
                return {
                    "status": "success",
                    "details": {
                        "steps": ["Follower was already inactive"],
                        "errors": [],
                        "initial_state": initial_state,
                        "final_state": "inactive",
                        "execution_time_ms": round((time.time() - start_time) * 1000, 2),
                        "was_active": False
                    }
                }

            # Call the controller's disconnect_px4 method
            # This method handles:
            # - Thread-safe state transitions
            # - SetpointSender thread cleanup
            # - Offboard mode deactivation
            # - Follower instance cleanup
            # - State reset
            result = await self.app_controller.disconnect_px4()

            # Determine final state
            final_state = "active" if self.app_controller.following_active else "inactive"
            execution_time_ms = (time.time() - start_time) * 1000

            # Enhance result with additional metadata
            result["initial_state"] = initial_state
            result["final_state"] = final_state
            result["execution_time_ms"] = round(execution_time_ms, 2)
            result["was_active"] = was_active

            # Log success
            self.logger.info(
                f"✅ API: Offboard mode stopped successfully "
                f"({initial_state} → {final_state}, {execution_time_ms:.0f}ms)"
            )

            # Verify cleanup was successful
            if self.app_controller.following_active:
                self.logger.warning(
                    "⚠️ Warning: following_active flag is still True after disconnect. "
                    "This may indicate incomplete cleanup."
                )

            # Log any warnings if errors occurred during cleanup
            if result.get("errors"):
                self.logger.warning(
                    f"⚠️ Disconnect completed with {len(result['errors'])} warnings. "
                    f"Follower state may need verification."
                )

            return {"status": "success", "details": result}

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            self.logger.error(f"❌ API: Error in stop_offboard_mode: {error_msg}")
            self.logger.error(f"Exception type: {type(e).__name__}")

            # Log stack trace for debugging
            import traceback
            self.logger.debug(f"Stack trace:\n{traceback.format_exc()}")

            # Attempt emergency cleanup even after error
            try:
                if hasattr(self.app_controller, 'setpoint_sender') and self.app_controller.setpoint_sender:
                    self.logger.warning("⚠️ Attempting emergency cleanup of setpoint sender...")
                    self.app_controller.setpoint_sender.stop()
                    self.app_controller.setpoint_sender = None

                if hasattr(self.app_controller, 'follower') and self.app_controller.follower:
                    self.logger.warning("⚠️ Attempting emergency cleanup of follower...")
                    self.app_controller.follower = None

                # Force state to inactive as last resort
                self.app_controller.following_active = False
                self.logger.warning("⚠️ Emergency cleanup completed, state forced to inactive")

            except Exception as cleanup_error:
                self.logger.error(f"❌ Emergency cleanup failed: {cleanup_error}")

            # Determine final state
            try:
                final_state = "active" if self.app_controller.following_active else "inactive"
            except:
                final_state = "unknown"

            return {
                "status": "failure",
                "error": error_msg,
                "details": {
                    "steps": [],
                    "errors": [error_msg],
                    "initial_state": initial_state if 'initial_state' in locals() else "unknown",
                    "final_state": final_state,
                    "execution_time_ms": round(execution_time_ms, 2),
                    "was_active": was_active if 'was_active' in locals() else False,
                    "exception_type": type(e).__name__
                }
            }

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

    async def get_follower_health(self):
        """
        Comprehensive health check endpoint for follower system.

        This endpoint provides detailed health status that can be used for:
        - Monitoring and alerting
        - Diagnostics and troubleshooting
        - State verification after operations
        - External integrations

        Returns:
            dict: Detailed health status including:
                - Overall health status (healthy, degraded, unhealthy)
                - Component states (follower, threads, connections)
                - Configuration validation
                - Performance metrics
                - Error conditions
        """
        import time

        try:
            health_status = {
                "timestamp": time.time(),
                "overall_status": "healthy",
                "components": {},
                "metrics": {},
                "issues": []
            }

            # Check follower state
            follower_component = {
                "active": self.app_controller.following_active,
                "status": "active" if self.app_controller.following_active else "inactive"
            }

            if self.app_controller.following_active:
                # Check follower instance
                if hasattr(self.app_controller, 'follower') and self.app_controller.follower:
                    follower = self.app_controller.follower
                    follower_component["has_instance"] = True
                    follower_component["type"] = follower.get_display_name() if hasattr(follower, 'get_display_name') else "unknown"
                    follower_component["control_type"] = follower.get_control_type() if hasattr(follower, 'get_control_type') else "unknown"
                    follower_component["mode_valid"] = follower.validate_current_mode() if hasattr(follower, 'validate_current_mode') else False
                else:
                    follower_component["has_instance"] = False
                    health_status["issues"].append("Follower marked active but instance is None")
                    health_status["overall_status"] = "degraded"

                # Check setpoint sender thread
                if hasattr(self.app_controller, 'setpoint_sender') and self.app_controller.setpoint_sender:
                    sender = self.app_controller.setpoint_sender
                    follower_component["setpoint_sender"] = {
                        "exists": True,
                        "running": sender.is_alive() if hasattr(sender, 'is_alive') else False
                    }

                    if hasattr(sender, 'is_alive') and not sender.is_alive():
                        health_status["issues"].append("SetpointSender thread is not running")
                        health_status["overall_status"] = "unhealthy"
                else:
                    follower_component["setpoint_sender"] = {"exists": False}
                    health_status["issues"].append("Follower active but SetpointSender is None")
                    health_status["overall_status"] = "unhealthy"
            else:
                follower_component["has_instance"] = bool(hasattr(self.app_controller, 'follower') and self.app_controller.follower)
                follower_component["setpoint_sender"] = {"exists": bool(hasattr(self.app_controller, 'setpoint_sender') and self.app_controller.setpoint_sender)}

                # Check for cleanup issues
                if follower_component["has_instance"] or follower_component["setpoint_sender"]["exists"]:
                    health_status["issues"].append("Follower inactive but resources not cleaned up")
                    health_status["overall_status"] = "degraded"

            health_status["components"]["follower"] = follower_component

            # Check PX4 interface
            px4_component = {
                "initialized": hasattr(self.app_controller, 'px4_interface'),
                "status": "unknown"
            }

            if px4_component["initialized"]:
                px4_interface = self.app_controller.px4_interface
                # Check if connected (if method exists)
                if hasattr(px4_interface, 'is_connected'):
                    px4_component["connected"] = px4_interface.is_connected()
                    px4_component["status"] = "connected" if px4_component["connected"] else "disconnected"
                elif hasattr(px4_interface, 'connection'):
                    px4_component["has_connection"] = px4_interface.connection is not None
                    px4_component["status"] = "ready" if px4_component["has_connection"] else "not_ready"

            health_status["components"]["px4_interface"] = px4_component

            # Check tracker
            tracker_component = {
                "initialized": hasattr(self.app_controller, 'tracker'),
                "tracking_active": getattr(self.app_controller, 'tracking_started', False)
            }

            if tracker_component["initialized"]:
                tracker = self.app_controller.tracker
                tracker_component["type"] = tracker.__class__.__name__ if tracker else "None"

            health_status["components"]["tracker"] = tracker_component

            # Check state lock
            lock_component = {
                "initialized": hasattr(self.app_controller, '_follower_state_lock'),
                "type": type(self.app_controller._follower_state_lock).__name__ if hasattr(self.app_controller, '_follower_state_lock') else "None"
            }
            health_status["components"]["state_lock"] = lock_component

            if not lock_component["initialized"]:
                health_status["issues"].append("State lock not initialized - thread safety compromised")
                health_status["overall_status"] = "unhealthy"

            # Configuration validation
            config_component = {
                "follower_mode": Parameters.FOLLOWER_MODE,
                "valid": False
            }

            try:
                available_profiles = SetpointHandler.get_available_profiles()
                config_component["valid"] = Parameters.FOLLOWER_MODE in available_profiles
                config_component["available_profiles"] = available_profiles

                if not config_component["valid"]:
                    health_status["issues"].append(f"Invalid follower mode: {Parameters.FOLLOWER_MODE}")
                    if health_status["overall_status"] == "healthy":
                        health_status["overall_status"] = "degraded"

            except Exception as e:
                config_component["error"] = str(e)
                health_status["issues"].append(f"Configuration validation error: {e}")

            health_status["components"]["configuration"] = config_component

            # Performance metrics
            metrics = {}

            # Add uptime if tracking
            if hasattr(self.app_controller, 'following_active') and self.app_controller.following_active:
                if hasattr(self.app_controller, '_following_start_time'):
                    uptime = time.time() - self.app_controller._following_start_time
                    metrics["follower_uptime_seconds"] = round(uptime, 2)

            health_status["metrics"] = metrics

            # Summary
            health_status["summary"] = {
                "components_checked": len(health_status["components"]),
                "issues_found": len(health_status["issues"]),
                "follower_operational": (
                    self.app_controller.following_active and
                    follower_component.get("has_instance", False) and
                    follower_component.get("setpoint_sender", {}).get("exists", False)
                ) if self.app_controller.following_active else True  # If inactive, consider operational
            }

            return JSONResponse(content=health_status)

        except Exception as e:
            self.logger.error(f"Error in follower health check: {e}")
            return JSONResponse(
                content={
                    "timestamp": time.time(),
                    "overall_status": "error",
                    "error": str(e),
                    "exception_type": type(e).__name__
                },
                status_code=500
            )

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

    # ==================== Tracker Selector API Endpoints ====================

    async def get_available_trackers(self):
        """
        Endpoint to get available UI-selectable classic trackers.
        Mirrors get_follower_profiles() pattern.

        Returns:
            dict: Available classic trackers with detailed metadata from schema.
        """
        try:
            from classes.schema_manager import get_schema_manager
            schema_manager = get_schema_manager()

            # Get UI-selectable classic trackers from schema
            classic_trackers = schema_manager.get_available_classic_trackers()

            # Get current configured tracker type
            current_tracker_type = getattr(self.app_controller, 'current_tracker_type',
                                          Parameters.DEFAULT_TRACKING_ALGORITHM)

            # Check if tracking is active
            tracking_active = (
                hasattr(self.app_controller, 'tracking_started') and
                self.app_controller.tracking_started
            )

            return JSONResponse(content={
                'available_trackers': classic_trackers,
                'current_configured': current_tracker_type,
                'tracking_active': tracking_active,
                'smart_mode_active': getattr(self.app_controller, 'smart_mode_active', False),
                'total_trackers': len(classic_trackers),
                'timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error getting available trackers: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_current_tracker(self):
        """
        Endpoint to get current tracker information and status.
        Mirrors get_current_follower_profile() pattern.

        Returns:
            dict: Current tracker details, status, and metadata.
        """
        try:
            from classes.schema_manager import get_schema_manager
            schema_manager = get_schema_manager()

            # Get current configured tracker type
            current_tracker_type = getattr(self.app_controller, 'current_tracker_type',
                                          Parameters.DEFAULT_TRACKING_ALGORITHM)

            # Check if tracker is actively tracking
            tracking_active = (
                hasattr(self.app_controller, 'tracking_started') and
                self.app_controller.tracking_started
            )

            # Get tracker info from schema
            tracker_info = schema_manager.get_tracker_info(current_tracker_type)

            if tracker_info:
                ui_metadata = tracker_info.get('ui_metadata', {})
                tracker_details = {
                    'status': 'tracking' if tracking_active else 'configured',
                    'active': tracking_active,
                    'tracker_type': current_tracker_type,
                    'display_name': ui_metadata.get('display_name', current_tracker_type),
                    'description': tracker_info.get('description', ''),
                    'short_description': ui_metadata.get('short_description', ''),
                    'icon': ui_metadata.get('icon', '🎯'),
                    'performance_category': ui_metadata.get('performance_category', 'unknown'),
                    'supported_schemas': tracker_info.get('supported_schemas', []),
                    'capabilities': tracker_info.get('capabilities', []),
                    'performance': tracker_info.get('performance', {}),
                    'suitable_for': ui_metadata.get('suitable_for', []),
                    'message': 'Tracker actively tracking target' if tracking_active else 'Tracker configured. Start tracking to activate.'
                }
            else:
                # Fallback for unknown tracker
                tracker_details = {
                    'status': 'unknown',
                    'active': tracking_active,
                    'tracker_type': current_tracker_type,
                    'display_name': current_tracker_type,
                    'description': 'Unknown tracker type',
                    'error': f'Tracker type "{current_tracker_type}" not found in schema'
                }

            # Add smart mode status
            tracker_details['smart_mode_active'] = getattr(self.app_controller, 'smart_mode_active', False)
            tracker_details['following_active'] = getattr(self.app_controller, 'following_active', False)
            tracker_details['timestamp'] = time.time()

            return JSONResponse(content=tracker_details)

        except Exception as e:
            self.logger.error(f"Error getting current tracker: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def switch_tracker(self, request: Request):
        """
        Endpoint to switch tracker type dynamically.
        Mirrors switch_follower_profile() pattern.

        Args:
            request: Should contain {'tracker_type': 'new_tracker_name'}

        Returns:
            dict: Switch operation result with status and messages.
        """
        try:
            data = await request.json()
            new_tracker_type = data.get('tracker_type')

            if not new_tracker_type:
                raise HTTPException(status_code=400, detail="tracker_type is required")

            # Validate tracker exists and is UI-selectable using schema manager
            from classes.schema_manager import get_schema_manager
            schema_manager = get_schema_manager()

            is_valid, error_msg = schema_manager.validate_tracker_for_ui(new_tracker_type)
            if not is_valid:
                raise HTTPException(status_code=400, detail=error_msg)

            # Get old tracker type for logging
            old_tracker_type = getattr(self.app_controller, 'current_tracker_type',
                                      Parameters.DEFAULT_TRACKING_ALGORITHM)

            # Call app_controller's switch_tracker_type method
            result = await self.app_controller.switch_tracker_type(new_tracker_type)

            if result['success']:
                self.logger.info(f"Tracker switched via API: {old_tracker_type} → {new_tracker_type}")

                return JSONResponse(content={
                    'status': 'success',
                    'action': 'tracker_switched',
                    'old_tracker': old_tracker_type,
                    'new_tracker': new_tracker_type,
                    'message': result.get('message', f'Tracker switched to {new_tracker_type}'),
                    'requires_restart': result.get('requires_restart', False),
                    'details': result
                })
            else:
                # Switch failed - return error
                error_detail = result.get('error', 'Unknown error during tracker switch')
                self.logger.error(f"Tracker switch failed: {error_detail}")

                return JSONResponse(content={
                    'status': 'error',
                    'action': 'switch_failed',
                    'old_tracker': old_tracker_type,
                    'requested_tracker': new_tracker_type,
                    'error': error_detail,
                    'details': result
                }, status_code=500)

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error switching tracker: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def restart_follower(self):
        """
        Restart the current follower with fresh config.

        This endpoint is used after configuration changes that require
        follower restart (reload_tier: follower_restart) to take effect.

        The follower is stopped, config is reloaded, and follower is restarted
        with the same profile but fresh parameters.

        Returns:
            JSONResponse: Restart status with before/after config summary.
        """
        # Rate limiting check - prevent restart abuse
        allowed, retry_after = self.config_rate_limiter.is_allowed('config_write')
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    'success': False,
                    'error': 'Too many restart requests',
                    'retry_after': retry_after,
                    'timestamp': time.time()
                },
                headers={'Retry-After': str(retry_after)}
            )

        try:
            # Reload config first
            Parameters.reload_config()
            self.logger.info("Config reloaded for follower restart")

            # Get current follower state
            has_active_follower = (
                hasattr(self.app_controller, 'follower') and
                self.app_controller.follower is not None and
                self.app_controller.following_active
            )

            current_profile = Parameters.FOLLOWER_MODE

            if has_active_follower:
                # Get old follower info before restart
                old_follower = self.app_controller.follower
                old_profile = getattr(old_follower, 'profile_name', current_profile)

                # Stop current follower
                if hasattr(self.app_controller, 'stop_following'):
                    await self.app_controller.stop_following()
                    self.logger.info("Stopped active follower for restart")

                # Start fresh follower with same profile
                if hasattr(self.app_controller, 'start_following'):
                    await self.app_controller.start_following()
                    self.logger.info(f"Restarted follower with profile: {current_profile}")

                return JSONResponse(content={
                    'success': True,
                    'action': 'follower_restarted',
                    'profile': current_profile,
                    'message': f'Follower restarted with fresh config (profile: {current_profile})',
                    'config_reloaded': True
                })
            else:
                # No active follower - just confirm config was reloaded
                return JSONResponse(content={
                    'success': True,
                    'action': 'config_reloaded',
                    'profile': current_profile,
                    'message': 'Config reloaded. No active follower to restart. Changes will apply on next start.',
                    'config_reloaded': True
                })

        except Exception as e:
            self.logger.error(f"Error restarting follower: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def restart_tracker(self):
        """
        Restart the current tracker with fresh config.

        This endpoint is used after configuration changes that require
        tracker restart (reload_tier: tracker_restart) to take effect.

        The current tracker type is preserved, but tracker is reinitialized
        with fresh parameters from config.

        Returns:
            JSONResponse: Restart status with tracker info.
        """
        # Rate limiting check - prevent restart abuse
        allowed, retry_after = self.config_rate_limiter.is_allowed('config_write')
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    'success': False,
                    'error': 'Too many restart requests',
                    'retry_after': retry_after,
                    'timestamp': time.time()
                },
                headers={'Retry-After': str(retry_after)}
            )

        try:
            # Reload config first
            Parameters.reload_config()
            self.logger.info("Config reloaded for tracker restart")

            # Get current tracker type
            current_tracker_type = getattr(
                self.app_controller,
                'current_tracker_type',
                Parameters.DEFAULT_TRACKING_ALGORITHM
            )

            # Switch to same tracker type (this reinitializes with fresh config)
            result = await self.app_controller.switch_tracker_type(current_tracker_type)

            if result.get('success'):
                self.logger.info(f"Tracker reinitialized: {current_tracker_type}")

                return JSONResponse(content={
                    'success': True,
                    'action': 'tracker_restarted',
                    'tracker_type': current_tracker_type,
                    'message': f'Tracker {current_tracker_type} reinitialized with fresh config',
                    'config_reloaded': True,
                    'details': result
                })
            else:
                error_detail = result.get('error', 'Unknown error during tracker restart')
                self.logger.error(f"Tracker restart failed: {error_detail}")

                return JSONResponse(content={
                    'success': False,
                    'action': 'restart_failed',
                    'tracker_type': current_tracker_type,
                    'error': error_detail,
                    'config_reloaded': True,
                    'details': result
                }, status_code=500)

        except Exception as e:
            self.logger.error(f"Error restarting tracker: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== YOLO Model Management API Endpoints ====================

    async def get_yolo_models(self):
        """
        Get list of available YOLO models in yolo/ folder.

        Returns:
            JSONResponse: {
                "models": {
                    "model_id": {
                        "name": "YOLO11n",
                        "path": "yolo/yolo11n.pt",
                        "type": "gpu",
                        "num_classes": 80,
                        "is_custom": false,
                        "has_ncnn": true,
                        ...
                    }
                },
                "current_model": "yolo11n.pt" (if SmartTracker is active)
            }
        """
        try:
            from pathlib import Path

            # Discover models using YOLOModelManager
            models = self.yolo_model_manager.discover_models(force_rescan=False)

            # Get current model if SmartTracker is active
            current_model = None
            if (hasattr(self.app_controller, 'smart_tracker') and
                self.app_controller.smart_tracker is not None):
                smart_tracker = self.app_controller.smart_tracker
                if hasattr(smart_tracker, 'model'):
                    # Try to extract current model path
                    try:
                        model_file = getattr(smart_tracker.model, 'ckpt_path', None)
                        if model_file:
                            current_model = Path(model_file).name
                    except Exception as e:
                        self.logger.debug(f"Could not determine current model: {e}")

            # If SmartTracker is not active, get configured model from config
            configured_model = None
            try:
                from classes.parameters import Parameters
                # Get GPU model path from config (primary) or CPU model as fallback
                use_gpu = Parameters.SmartTracker.get('SMART_TRACKER_USE_GPU', True)
                if use_gpu:
                    model_path = Parameters.SmartTracker.get('SMART_TRACKER_GPU_MODEL_PATH', 'yolo/yolo11n.pt')
                else:
                    model_path = Parameters.SmartTracker.get('SMART_TRACKER_CPU_MODEL_PATH', 'yolo/yolo11n_ncnn_model')

                # Extract just the filename
                configured_model = Path(model_path).name
            except Exception as e:
                self.logger.debug(f"Could not determine configured model: {e}")

            return JSONResponse(content={
                'status': 'success',
                'models': models,
                'current_model': current_model,  # Currently active model (if SmartTracker is running)
                'configured_model': configured_model,  # Configured model from config.yaml
                'total_count': len(models)
            })

        except Exception as e:
            self.logger.error(f"Error getting YOLO models: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def switch_yolo_model(self, request: Request):
        """
        Switch YOLO model in SmartTracker without restart.

        Args:
            request: Should contain {
                'model_path': 'yolo/yolo11n.pt',
                'device': 'auto' | 'gpu' | 'cpu'  (optional, default='auto')
            }

        Returns:
            JSONResponse: Switch operation result
        """
        try:
            data = await request.json()
            model_path = data.get('model_path')
            device = data.get('device', 'auto')

            if not model_path:
                raise HTTPException(status_code=400, detail="model_path is required")

            # Validate device parameter
            if device not in ['auto', 'gpu', 'cpu']:
                raise HTTPException(status_code=400, detail="device must be 'auto', 'gpu', or 'cpu'")

            # Check if SmartTracker is available
            if not hasattr(self.app_controller, 'smart_tracker') or self.app_controller.smart_tracker is None:
                raise HTTPException(
                    status_code=400,
                    detail="SmartTracker is not initialized. Enable Smart Mode first."
                )

            # Validate model file exists
            from pathlib import Path
            full_path = Path(model_path)
            if not full_path.exists():
                raise HTTPException(status_code=404, detail=f"Model file not found: {model_path}")

            # Call SmartTracker's switch_model method
            smart_tracker = self.app_controller.smart_tracker
            result = smart_tracker.switch_model(str(full_path), device=device)

            if result['success']:
                self.logger.info(f"YOLO model switched via API: {model_path} (device={device})")

                return JSONResponse(content={
                    'status': 'success',
                    'action': 'model_switched',
                    'model_path': model_path,
                    'device': device,
                    'message': result['message'],
                    'model_info': result.get('model_info')
                })
            else:
                # Switch failed
                error_msg = result.get('message', 'Unknown error during model switch')
                self.logger.error(f"YOLO model switch failed: {error_msg}")

                return JSONResponse(content={
                    'status': 'error',
                    'action': 'switch_failed',
                    'requested_model': model_path,
                    'error': error_msg
                }, status_code=500)

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error switching YOLO model: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def upload_yolo_model(self, request: Request):
        """
        Upload a new YOLO model file (.pt).

        Args:
            request: Multipart form with file field

        Returns:
            JSONResponse: Upload result with model metadata
        """
        try:
            from fastapi import UploadFile, File, Form
            import io

            # Parse multipart form data
            form = await request.form()
            file = form.get('file')

            if not file or not hasattr(file, 'filename'):
                raise HTTPException(status_code=400, detail="No file provided")

            filename = file.filename
            if not filename.endswith('.pt'):
                raise HTTPException(status_code=400, detail="Only .pt files are allowed")

            # Read file data
            file_data = await file.read()

            # Auto-export NCNN by default (can be made configurable)
            auto_export = form.get('auto_export_ncnn', 'true').lower() == 'true'

            # Upload via YOLOModelManager
            result = await self.yolo_model_manager.upload_model(
                file_data=file_data,
                filename=filename,
                auto_export_ncnn=auto_export
            )

            if result['success']:
                self.logger.info(f"YOLO model uploaded via API: {filename}")

                return JSONResponse(content={
                    'status': 'success',
                    'action': 'model_uploaded',
                    'filename': filename,
                    'message': result.get('message', 'Model uploaded successfully'),
                    'model_info': result.get('model_info'),
                    'ncnn_exported': result.get('ncnn_exported', False)
                })
            else:
                error_msg = result.get('error', 'Unknown error during upload')
                self.logger.error(f"YOLO model upload failed: {error_msg}")

                return JSONResponse(content={
                    'status': 'error',
                    'action': 'upload_failed',
                    'filename': filename,
                    'error': error_msg
                }, status_code=500)

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error uploading YOLO model: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_yolo_model(self, model_id: str):
        """
        Delete a YOLO model file.

        Args:
            model_id: Model identifier (filename without extension or full filename)

        Returns:
            JSONResponse: Deletion result
        """
        try:
            # Delete via YOLOModelManager
            result = self.yolo_model_manager.delete_model(model_id, delete_ncnn=True)

            if result['success']:
                self.logger.info(f"YOLO model deleted via API: {model_id}")

                return JSONResponse(content={
                    'status': 'success',
                    'action': 'model_deleted',
                    'model_id': model_id,
                    'message': result.get('message', 'Model deleted successfully')
                })
            else:
                error_msg = result.get('error', 'Unknown error during deletion')
                self.logger.error(f"YOLO model deletion failed: {error_msg}")

                return JSONResponse(content={
                    'status': 'error',
                    'action': 'deletion_failed',
                    'model_id': model_id,
                    'error': error_msg
                }, status_code=404 if 'not found' in error_msg.lower() else 500)

        except Exception as e:
            self.logger.error(f"Error deleting YOLO model: {e}")
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
        DEPRECATED: Use POST /api/tracker/switch instead.

        Endpoint to set/change the tracker type.
        This endpoint is deprecated since v4.0.0. Use /api/tracker/switch.

        Args:
            request (dict): Request body containing tracker_type

        Returns:
            dict: Success/failure response with deprecation warning
        """
        # Log deprecation warning
        self.logger.warning(
            "DEPRECATED: /api/tracker/set-type called. Use /api/tracker/switch instead."
        )

        # Deprecation notice to include in all responses
        deprecation_notice = {
            '_deprecated': True,
            '_deprecation_message': 'This endpoint is deprecated since v4.0.0. Use POST /api/tracker/switch instead.',
            '_sunset': 'v5.0.0'
        }

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
                            **deprecation_notice,
                            'status': 'success',
                            'action': 'smart_mode_enabled',
                            'old_tracker': old_tracker_type,
                            'new_tracker': tracker_type,
                            'message': 'Smart mode enabled. Stop and restart tracking to activate smart tracker.',
                            'requires_restart': True
                        })
                    else:
                        return JSONResponse(content={
                            **deprecation_notice,
                            'status': 'success',
                            'action': 'configured_smart',
                            'old_tracker': old_tracker_type,
                            'new_tracker': tracker_type,
                            'message': 'Smart tracker configured. Will activate when tracking starts.'
                        })
                else:
                    return JSONResponse(content={
                        **deprecation_notice,
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
                        **deprecation_notice,
                        'status': 'success',
                        'action': 'classic_tracker_set',
                        'old_tracker': old_tracker_type,
                        'new_tracker': tracker_type,
                        'message': f'Tracker set to {tracker_type}. Stop and restart tracking to activate new tracker.',
                        'requires_restart': True
                    })
                else:
                    return JSONResponse(content={
                        **deprecation_notice,
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
            safety_bypass = getattr(Parameters, "CIRCUIT_BREAKER_DISABLE_SAFETY", False)

            return JSONResponse(content={
                'available': True,
                'active': is_active,
                'status': 'testing' if is_active else 'operational',
                'safety_bypass': safety_bypass,
                'safety_bypass_effective': safety_bypass and is_active,
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

    async def toggle_circuit_breaker_safety_bypass(self):
        """
        Toggle safety bypass flag for circuit breaker test mode.

        When enabled AND circuit breaker is active, altitude and velocity
        safety checks are skipped, allowing ground testing of follower logic.

        Returns:
            dict: New safety bypass status
        """
        try:
            if not CIRCUIT_BREAKER_AVAILABLE:
                raise HTTPException(
                    status_code=503,
                    detail="Circuit breaker system not available"
                )

            # Get current state
            old_state = getattr(Parameters, "CIRCUIT_BREAKER_DISABLE_SAFETY", False)

            # Toggle the parameter
            new_state = not old_state
            Parameters.CIRCUIT_BREAKER_DISABLE_SAFETY = new_state

            cb_active = FollowerCircuitBreaker.is_active()
            effective = new_state and cb_active

            if new_state:
                self.logger.warning("Safety bypass ENABLED - altitude/velocity limits will be skipped when CB is active")
            else:
                self.logger.info("Safety bypass DISABLED - safety checks will be enforced")

            return JSONResponse(content={
                'status': 'success',
                'action': 'enabled' if new_state else 'disabled',
                'safety_bypass': new_state,
                'old_state': old_state,
                'new_state': new_state,
                'circuit_breaker_active': cb_active,
                'effective': effective,
                'message': f'Safety checks {"bypassed" if effective else "enforced"}',
                'warning': 'Safety bypass active - altitude/velocity limits disabled' if effective else None,
                'timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error toggling safety bypass: {e}")
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

    # ==================== OSD Control API Endpoints ====================

    async def get_osd_status(self):
        """
        Get current OSD status and configuration.

        Returns:
            dict: OSD status, configuration, and performance metrics
        """
        try:
            if not hasattr(self.app_controller, 'osd_handler'):
                return JSONResponse(content={
                    'available': False,
                    'error': 'OSD system not available'
                })

            osd_handler = self.app_controller.osd_handler

            # Get OSD enabled status
            is_enabled = osd_handler.is_enabled() if hasattr(osd_handler, 'is_enabled') else Parameters.OSD_ENABLED

            # Get performance stats if available
            perf_stats = {}
            if hasattr(osd_handler, 'get_performance_stats'):
                perf_stats = osd_handler.get_performance_stats()

            # Get preset name
            current_preset = getattr(Parameters, 'OSD_PRESET', 'professional')

            return JSONResponse(content={
                'available': True,
                'enabled': is_enabled,
                'status': 'active' if is_enabled else 'disabled',
                'configuration': {
                    'enabled_parameter': Parameters.OSD_ENABLED,
                    'current_preset': current_preset,
                    'presets_location': 'configs/osd_presets/'
                },
                'performance': perf_stats,
                'message': 'OSD overlay active on video feed' if is_enabled else 'OSD overlay disabled',
                'timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error getting OSD status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def toggle_osd(self):
        """
        Toggle OSD on/off.

        Returns:
            dict: New OSD status
        """
        try:
            if not hasattr(self.app_controller, 'osd_handler'):
                raise HTTPException(
                    status_code=503,
                    detail="OSD system not available"
                )

            osd_handler = self.app_controller.osd_handler

            # Get current state
            old_state = osd_handler.is_enabled() if hasattr(osd_handler, 'is_enabled') else Parameters.OSD_ENABLED

            # Toggle the state
            new_state = not old_state
            if hasattr(osd_handler, 'set_enabled'):
                osd_handler.set_enabled(new_state)

            # Update parameter
            Parameters.OSD_ENABLED = new_state

            self.logger.info(f"OSD {'enabled' if new_state else 'disabled'} via API")

            return JSONResponse(content={
                'status': 'success',
                'action': 'enabled' if new_state else 'disabled',
                'enabled': new_state,
                'old_state': old_state,
                'new_state': new_state,
                'message': f'OSD overlay {"enabled" if new_state else "disabled"}',
                'timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error toggling OSD: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_osd_presets(self):
        """
        Get available OSD presets.

        Returns:
            dict: Available preset information
        """
        try:
            import os
            from pathlib import Path

            presets_dir = Path("configs/osd_presets")

            if not presets_dir.exists():
                return JSONResponse(content={
                    'available': False,
                    'error': 'OSD presets directory not found',
                    'presets': []
                })

            # Scan for preset files - return just the names as strings
            presets = []
            for preset_file in presets_dir.glob("*.yaml"):
                if preset_file.name.lower() != 'readme.md':
                    preset_name = preset_file.stem
                    presets.append(preset_name)

            # Sort presets (put professional first as default)
            presets.sort(key=lambda x: (x != 'professional', x))

            # Get current preset from Parameters
            current_preset = getattr(Parameters, 'OSD_PRESET', 'professional') if hasattr(Parameters, 'OSD_PRESET') else 'professional'

            return JSONResponse(content={
                'available': True,
                'presets': presets,
                'current': current_preset,
                'presets_directory': str(presets_dir),
                'total_presets': len(presets),
                'timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error getting OSD presets: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def load_osd_preset(self, preset_name: str):
        """
        Load an OSD preset configuration.

        Args:
            preset_name: Name of the preset to load (e.g., 'minimal', 'professional', 'full_telemetry')

        Returns:
            dict: Load operation result
        """
        try:
            import yaml
            from pathlib import Path

            # Validate preset name (security)
            allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-')
            if not all(c in allowed_chars for c in preset_name):
                raise HTTPException(status_code=400, detail="Invalid preset name")

            preset_path = Path(f"configs/osd_presets/{preset_name}.yaml")

            if not preset_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Preset '{preset_name}' not found"
                )

            # Load preset configuration to validate it exists and is valid YAML
            with open(preset_path, 'r') as f:
                preset_config = yaml.safe_load(f)

            # Count elements in preset
            element_count = len(preset_config.get('ELEMENTS', {}))

            # Update Parameters.OSD_PRESET to switch to this preset
            old_preset = getattr(Parameters, 'OSD_PRESET', 'professional')
            Parameters.OSD_PRESET = preset_name

            # Reinitialize OSD renderer to load new preset IMMEDIATELY
            if hasattr(self.app_controller, 'osd_handler'):
                try:
                    from classes.osd_renderer import OSDRenderer
                    # Destroy old renderer and create new one with new preset
                    self.app_controller.osd_handler.renderer = OSDRenderer(self.app_controller)
                    self.logger.info(f"OSD renderer reinitialized with preset '{preset_name}'")
                except Exception as e:
                    self.logger.error(f"Failed to reinitialize OSD renderer: {e}")

            self.logger.info(f"OSD preset switched: '{old_preset}' → '{preset_name}'")

            return JSONResponse(content={
                'status': 'success',
                'action': 'preset_loaded',
                'old_preset': old_preset,
                'new_preset': preset_name,
                'preset_file': str(preset_path),
                'configuration_updated': True,
                'element_count': element_count,
                'message': f'OSD preset switched to "{preset_name}". Restart app for changes to take effect.',
                'requires_restart': True,
                'timestamp': time.time()
            })

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error loading OSD preset: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Safety Configuration API Endpoints (v3.5.0+) ====================

    async def get_safety_config(self):
        """
        Get complete safety configuration from SafetyManager.

        Returns:
            dict: Safety configuration including global limits and follower overrides
        """
        try:
            # Try to import SafetyManager
            try:
                from classes.safety_manager import SafetyManager, get_safety_manager
                safety_manager = get_safety_manager()
                safety_available = True
            except ImportError:
                safety_available = False
                safety_manager = None

            if not safety_available or safety_manager is None:
                return JSONResponse(content={
                    'available': False,
                    'message': 'SafetyManager not available',
                    'timestamp': time.time()
                })

            # Get configuration from SafetyManager (simplified v3.6.0)
            config = {
                'available': True,
                'global_limits': safety_manager._global_limits,
                'follower_overrides': safety_manager._follower_overrides,
                'timestamp': time.time()
            }

            return JSONResponse(content=config)

        except Exception as e:
            self.logger.error(f"Error getting safety config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_follower_safety_limits(self, follower_name: str):
        """
        Get effective safety limits for a specific follower.

        Args:
            follower_name: Name of the follower (e.g., 'MC_VELOCITY_CHASE')

        Returns:
            dict: Effective limits for the specified follower including
                  velocity, altitude, and rate limits
        """
        try:
            # Try to import SafetyManager
            try:
                from classes.safety_manager import SafetyManager, get_safety_manager
                safety_manager = get_safety_manager()
                safety_available = True
            except ImportError:
                safety_available = False
                safety_manager = None

            if not safety_available or safety_manager is None:
                # Fallback to Parameters.get_effective_limit (match frontend field names)
                limits = {
                    'follower_name': follower_name,
                    'velocity': {
                        'forward': Parameters.get_effective_limit('MAX_VELOCITY_FORWARD', follower_name),
                        'lateral': Parameters.get_effective_limit('MAX_VELOCITY_LATERAL', follower_name),
                        'vertical': Parameters.get_effective_limit('MAX_VELOCITY_VERTICAL', follower_name),
                    },
                    'altitude': {
                        'min': Parameters.get_effective_limit('MIN_ALTITUDE', follower_name),
                        'max': Parameters.get_effective_limit('MAX_ALTITUDE', follower_name),
                        'warning_buffer': Parameters.get_effective_limit('ALTITUDE_WARNING_BUFFER', follower_name),
                    },
                    'rates': {
                        'yaw_deg': Parameters.get_effective_limit('MAX_YAW_RATE', follower_name),
                        'pitch_deg': Parameters.get_effective_limit('MAX_PITCH_RATE', follower_name) or 45.0,
                        'roll_deg': Parameters.get_effective_limit('MAX_ROLL_RATE', follower_name) or 45.0,
                    },
                    'altitude_safety_enabled': True,
                    'timestamp': time.time()
                }
                return JSONResponse(content=limits)

            # Get limits from SafetyManager
            velocity_limits = safety_manager.get_velocity_limits(follower_name)
            altitude_limits = safety_manager.get_altitude_limits(follower_name)
            rate_limits = safety_manager.get_rate_limits(follower_name)

            # Get detailed summary to determine override status
            limits_summary = safety_manager.get_effective_limits_summary(follower_name)

            # Helper to check if any params in a group are overridden
            def is_group_overridden(param_names):
                return any(limits_summary.get(p, {}).get('is_overridden', False) for p in param_names)

            def get_group_source(param_names):
                for p in param_names:
                    if limits_summary.get(p, {}).get('is_overridden', False):
                        return limits_summary[p].get('source', 'GlobalLimits')
                return 'GlobalLimits'

            # Check override status for each category
            velocity_params = ['MAX_VELOCITY', 'MAX_VELOCITY_FORWARD', 'MAX_VELOCITY_LATERAL', 'MAX_VELOCITY_VERTICAL']
            altitude_params = ['MIN_ALTITUDE', 'MAX_ALTITUDE', 'ALTITUDE_WARNING_BUFFER', 'ALTITUDE_SAFETY_ENABLED']
            rate_params = ['MAX_YAW_RATE', 'MAX_PITCH_RATE', 'MAX_ROLL_RATE']

            velocity_overridden = is_group_overridden(velocity_params)
            altitude_overridden = is_group_overridden(altitude_params)
            rates_overridden = is_group_overridden(rate_params)
            has_any_overrides = velocity_overridden or altitude_overridden or rates_overridden

            # Convert radians to degrees for rate limits (config stores deg/s, SafetyManager converts to rad/s)
            from math import degrees

            limits = {
                'follower_name': follower_name,
                # Frontend expects 'velocity' not 'velocity_limits'
                'velocity': {
                    'forward': velocity_limits.forward,
                    'lateral': velocity_limits.lateral,
                    'vertical': velocity_limits.vertical,
                    'max_magnitude': velocity_limits.max_magnitude,
                    'source': get_group_source(velocity_params),
                    'is_overridden': velocity_overridden,
                },
                # Frontend expects 'altitude' with 'min'/'max' not 'min_altitude'/'max_altitude'
                'altitude': {
                    'min': altitude_limits.min_altitude,
                    'max': altitude_limits.max_altitude,
                    'warning_buffer': altitude_limits.warning_buffer,
                    'safety_enabled': altitude_limits.safety_enabled,
                    'source': get_group_source(altitude_params),
                    'is_overridden': altitude_overridden,
                },
                # Frontend expects 'rates' with '_deg' suffix fields
                'rates': {
                    'yaw_deg': degrees(rate_limits.yaw),
                    'pitch_deg': degrees(rate_limits.pitch),
                    'roll_deg': degrees(rate_limits.roll),
                    'source': get_group_source(rate_params),
                    'is_overridden': rates_overridden,
                },
                'altitude_safety_enabled': safety_manager.is_altitude_safety_enabled(follower_name),
                'has_any_overrides': has_any_overrides,
                'timestamp': time.time()
            }

            return JSONResponse(content=limits)

        except Exception as e:
            self.logger.error(f"Error getting follower safety limits: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Note: get_vehicle_profiles() removed in v4.0.0 (was deprecated in v3.6.0)

    # ==================== Enhanced Safety/Config API Endpoints (v5.0.0+) ====================

    async def get_effective_limits(self, follower_name: str = None):
        """
        Get effective safety limits with resolution chain for UI display.

        Returns all limits with their effective values, sources, and whether
        they are overridden for the specified follower.

        Args:
            follower_name: Optional follower name (e.g., 'MC_VELOCITY_CHASE')

        Returns:
            dict: Detailed limit resolution for UI display
        """
        try:
            try:
                from classes.safety_manager import SafetyManager, get_safety_manager
                safety_manager = get_safety_manager()
                safety_available = True
            except ImportError:
                safety_available = False
                safety_manager = None

            if not safety_available or safety_manager is None:
                return JSONResponse(content={
                    'available': False,
                    'message': 'SafetyManager not available',
                    'timestamp': time.time()
                })

            # Get detailed limit summary from SafetyManager
            limits_summary = safety_manager.get_effective_limits_summary(follower_name)
            available_followers = safety_manager.get_available_followers()

            return JSONResponse(content={
                'success': True,
                'follower_name': follower_name,
                'limits': limits_summary,
                'available_followers': available_followers,
                'timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error getting effective limits: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_relevant_sections(self, follower_mode: str = None):
        """
        Get configuration sections relevant to the current follower mode.

        Args:
            follower_mode: Follower mode name (e.g., 'mc_velocity_chase').
                          If not provided, uses currently configured mode.

        Returns:
            dict: Section names grouped by relevance
        """
        try:
            # Mode to section mapping
            MODE_SECTIONS = {
                'mc_velocity_chase': ['Follower', 'MC_VELOCITY_CHASE', 'Safety', 'PID', 'Tracking', 'OSD'],
                'mc_velocity_position': ['Follower', 'MC_VELOCITY_POSITION', 'Safety', 'PID', 'Tracking', 'OSD'],
                'mc_velocity_distance': ['Follower', 'MC_VELOCITY_DISTANCE', 'Safety', 'PID', 'Tracking', 'OSD'],
                'mc_velocity_ground': ['Follower', 'MC_VELOCITY_GROUND', 'Safety', 'PID', 'Tracking', 'OSD'],
                'mc_velocity': ['Follower', 'MC_VELOCITY', 'Safety', 'PID', 'Tracking', 'OSD'],
                'mc_attitude_rate': ['Follower', 'MC_ATTITUDE_RATE', 'Safety', 'PID', 'Tracking', 'OSD'],
                'gm_pid_pursuit': ['Follower', 'GM_PID_PURSUIT', 'Safety', 'GimbalTracker', 'GimbalTrackerSettings', 'PID', 'Tracking', 'Gimbal', 'OSD'],
                'gm_velocity_vector': ['Follower', 'GM_VELOCITY_VECTOR', 'Safety', 'GimbalTracker', 'GimbalTrackerSettings', 'PID', 'Tracking', 'Gimbal', 'OSD'],
                'fw_attitude_rate': ['Follower', 'FW_ATTITUDE_RATE', 'Safety', 'PID', 'Tracking', 'OSD'],
            }

            # Global sections that are always relevant
            GLOBAL_SECTIONS = ['VideoSource', 'PX4', 'MAVLink', 'Streaming', 'Debugging']

            # Use provided mode or get from Parameters
            mode = follower_mode.lower() if follower_mode else Parameters.FOLLOWER_MODE.lower()

            # Get relevant sections for this mode
            mode_specific = MODE_SECTIONS.get(mode, ['Follower', 'Safety', 'PID', 'Tracking', 'OSD'])

            # Get all section names from config service
            try:
                service = self._get_config_service()
                all_sections = list(service.get_schema().get('sections', {}).keys())
            except Exception:
                all_sections = []

            # Categorize sections
            active_sections = list(set(mode_specific + GLOBAL_SECTIONS))
            other_sections = [s for s in all_sections if s not in active_sections]

            return JSONResponse(content={
                'success': True,
                'current_mode': mode,
                'active_sections': active_sections,
                'other_sections': other_sections,
                'mode_specific_sections': mode_specific,
                'global_sections': GLOBAL_SECTIONS,
                'timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error getting relevant sections: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_current_follower_mode(self):
        """
        Get the currently active follower mode with detailed status.

        Returns:
            dict: Current mode name, status, and related configuration
        """
        try:
            configured_mode = Parameters.FOLLOWER_MODE
            is_active = self.app_controller.following_active if self.app_controller else False

            # Get effective limits for current mode
            try:
                from classes.safety_manager import get_safety_manager
                safety_manager = get_safety_manager()
                limits_summary = safety_manager.get_effective_limits_summary(configured_mode.upper())
                limits_available = True
            except Exception:
                limits_summary = {}
                limits_available = False

            # Get profile info
            try:
                profile_config = SetpointHandler.get_profile_info(configured_mode)
                profile_valid = True
            except Exception:
                profile_config = None
                profile_valid = False

            return JSONResponse(content={
                'success': True,
                'mode': configured_mode,
                'mode_upper': configured_mode.upper(),
                'is_active': is_active,
                'profile_valid': profile_valid,
                'profile_info': profile_config,
                'limits_available': limits_available,
                'effective_limits': limits_summary if limits_available else None,
                'timestamp': time.time()
            })

        except Exception as e:
            self.logger.error(f"Error getting current follower mode: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # =========================================================================
    # Configuration Management API Handlers (v4.0.0+)
    # =========================================================================

    def _get_config_service(self) -> ConfigService:
        """Get ConfigService singleton instance."""
        return ConfigService.get_instance()

    async def get_config_schema(self):
        """Get full configuration schema."""
        try:
            service = self._get_config_service()
            schema = service.get_schema()
            return JSONResponse(content={
                'success': True,
                'schema': schema,
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting config schema: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_config_section_schema(self, section: str):
        """Get schema for a specific section."""
        try:
            service = self._get_config_service()
            schema = service.get_schema(section)
            if not schema:
                raise HTTPException(status_code=404, detail=f"Section '{section}' not found")
            return JSONResponse(content={
                'success': True,
                'section': section,
                'schema': schema,
                'timestamp': time.time()
            })
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error getting section schema: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_config_sections(self):
        """Get list of all configuration sections."""
        try:
            service = self._get_config_service()
            sections = service.get_sections()
            return JSONResponse(content={
                'success': True,
                'sections': sections,
                'count': len(sections),
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting config sections: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_config_categories(self):
        """Get category definitions."""
        try:
            service = self._get_config_service()
            categories = service.get_categories()
            return JSONResponse(content={
                'success': True,
                'categories': categories,
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting config categories: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_current_config(self):
        """Get current configuration."""
        try:
            service = self._get_config_service()
            config = service.get_config()
            return JSONResponse(content={
                'success': True,
                'config': config,
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting current config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_current_config_section(self, section: str):
        """Get current configuration for a specific section."""
        try:
            service = self._get_config_service()
            config = service.get_config(section)
            return JSONResponse(content={
                'success': True,
                'section': section,
                'config': config,
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting section config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_default_config(self):
        """Get default configuration."""
        try:
            service = self._get_config_service()
            config = service.get_default()
            return JSONResponse(content={
                'success': True,
                'config': config,
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting default config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_default_config_section(self, section: str):
        """Get default configuration for a specific section."""
        try:
            service = self._get_config_service()
            config = service.get_default(section)
            return JSONResponse(content={
                'success': True,
                'section': section,
                'config': config,
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting default section config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_config_parameter(self, section: str, parameter: str, body: ConfigParameterUpdate):
        """Update a single configuration parameter."""
        # Rate limiting check
        allowed, retry_after = self.config_rate_limiter.is_allowed('config_write')
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    'success': False,
                    'error': 'Too many requests',
                    'retry_after': retry_after,
                    'timestamp': time.time()
                },
                headers={'Retry-After': str(retry_after)}
            )

        try:
            service = self._get_config_service()
            result = service.set_parameter(section, parameter, body.value)

            if not result.valid:
                return JSONResponse(
                    status_code=400,
                    content={
                        'success': False,
                        'validation': result.to_dict(),
                        'timestamp': time.time()
                    }
                )

            # Save config
            saved = service.save_config()

            # Hot-reload Parameters class for immediate-tier params
            applied = False
            if saved:
                try:
                    reload_success = Parameters.reload_config()
                    if reload_success:
                        applied = True
                        self.logger.info(f"Config hot-reloaded after updating {section}.{parameter}")
                    else:
                        self.logger.warning(f"Config reload returned False for {section}.{parameter}")
                except Exception as reload_error:
                    self.logger.error(f"Config reload failed: {reload_error}")

            # Get reload tier and message
            reload_tier = service.get_reload_tier(section, parameter)
            reload_message = service.get_reload_message(reload_tier)

            return JSONResponse(content={
                'success': True,
                'section': section,
                'parameter': parameter,
                'value': body.value,
                'validation': result.to_dict(),
                'saved': saved,
                'applied': applied,
                'reload_tier': reload_tier,
                'reload_message': reload_message,
                'reboot_required': service.is_reboot_required(section, parameter),  # Backward compat
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error updating config parameter: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_config_section(self, section: str, body: ConfigSectionUpdate):
        """Update multiple parameters in a section."""
        # Rate limiting check
        allowed, retry_after = self.config_rate_limiter.is_allowed('config_write')
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    'success': False,
                    'error': 'Too many requests',
                    'retry_after': retry_after,
                    'timestamp': time.time()
                },
                headers={'Retry-After': str(retry_after)}
            )

        try:
            service = self._get_config_service()
            result = service.set_section(section, body.parameters)

            if not result.valid:
                return JSONResponse(
                    status_code=400,
                    content={
                        'success': False,
                        'validation': result.to_dict(),
                        'timestamp': time.time()
                    }
                )

            # Save config
            saved = service.save_config()

            # Hot-reload Parameters class for immediate-tier params
            applied = False
            if saved:
                try:
                    reload_success = Parameters.reload_config()
                    if reload_success:
                        applied = True
                        self.logger.info(f"Config hot-reloaded after updating section {section}")
                    else:
                        self.logger.warning(f"Config reload returned False for section {section}")
                except Exception as reload_error:
                    self.logger.error(f"Config reload failed: {reload_error}")

            # Get reload tiers for all changed params
            reload_tiers = {
                param: service.get_reload_tier(section, param)
                for param in body.parameters.keys()
            }

            # Determine highest-priority tier (system > tracker > follower > immediate)
            # Default to 4 (system_restart) for unknown tiers as safe fallback
            tier_priority = {'system_restart': 4, 'tracker_restart': 3, 'follower_restart': 2, 'immediate': 1}
            if reload_tiers:
                max_tier = max(reload_tiers.values(), key=lambda t: tier_priority.get(t, 4))
            else:
                # Empty parameters dict - shouldn't happen, but handle gracefully
                max_tier = 'immediate'
            reload_message = service.get_reload_message(max_tier)

            # Backward compat: reboot_required if any param needs system restart
            reboot_required = any(
                service.is_reboot_required(section, param)
                for param in body.parameters.keys()
            )

            return JSONResponse(content={
                'success': True,
                'section': section,
                'parameters': body.parameters,
                'validation': result.to_dict(),
                'saved': saved,
                'applied': applied,
                'reload_tiers': reload_tiers,
                'reload_tier': max_tier,
                'reload_message': reload_message,
                'reboot_required': reboot_required,  # Backward compat
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error updating config section: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def validate_config_value(self, request: Request):
        """Validate a configuration value without saving."""
        try:
            body = await request.json()
            section = body.get('section')
            parameter = body.get('parameter')
            value = body.get('value')

            if not section or not parameter:
                raise HTTPException(status_code=400, detail="section and parameter are required")

            service = self._get_config_service()
            result = service.validate_value(section, parameter, value)

            return JSONResponse(content={
                'success': True,
                'section': section,
                'parameter': parameter,
                'value': value,
                'validation': result.to_dict(),
                'timestamp': time.time()
            })
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error validating config value: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_config_diff(self):
        """Get differences between current config and defaults."""
        try:
            service = self._get_config_service()
            diffs = service.get_changed_from_default()
            return JSONResponse(content={
                'success': True,
                'differences': [d.to_dict() for d in diffs],
                'count': len(diffs),
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting config diff: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def compare_configs(self, request: Request):
        """Compare two configurations.

        Supports two modes:
        1. compare_config: Compare incoming config against current config
        2. config1/config2: Compare two arbitrary configs
        """
        try:
            body = await request.json()
            service = self._get_config_service()

            # Mode 1: Compare incoming config against current
            if 'compare_config' in body:
                compare_config = body.get('compare_config', {})
                current_config = service.get_config()
                diffs = service.get_diff(current_config, compare_config)
            else:
                # Mode 2: Compare two arbitrary configs
                config1 = body.get('config1', {})
                config2 = body.get('config2', {})
                diffs = service.get_diff(config1, config2)

            return JSONResponse(content={
                'success': True,
                'differences': [d.to_dict() for d in diffs],
                'count': len(diffs),
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error comparing configs: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_defaults_sync(self):
        """Get sync information between current config and defaults (v5.4.0+).

        Returns:
            - new_parameters: Parameters in default that user doesn't have
            - changed_defaults: Parameters where default value has changed
            - removed_parameters: Parameters user has that are no longer in schema
        """
        try:
            service = self._get_config_service()
            schema = service.get_schema()
            current_config = service.get_config()
            default_config = service.get_default_config()

            new_parameters = []
            changed_defaults = []
            removed_parameters = []

            # Get all sections from schema
            sections = schema.get('sections', {})

            for section_name, section_schema in sections.items():
                parameters = section_schema.get('parameters', {})
                current_section = current_config.get(section_name, {})
                default_section = default_config.get(section_name, {})

                for param_name, param_schema in parameters.items():
                    default_value = param_schema.get('default')
                    current_value = current_section.get(param_name)

                    # New parameter: in schema/defaults but not in user config
                    if param_name not in current_section and param_name in default_section:
                        new_parameters.append({
                            'section': section_name,
                            'parameter': param_name,
                            'default_value': default_value,
                            'description': param_schema.get('description', ''),
                            'type': param_schema.get('type', 'string'),
                        })

                # Check for removed parameters (in current but not in schema)
                for param_name in current_section:
                    if param_name not in parameters:
                        removed_parameters.append({
                            'section': section_name,
                            'parameter': param_name,
                            'current_value': current_section[param_name],
                        })

            return JSONResponse(content={
                'success': True,
                'new_parameters': new_parameters,
                'changed_defaults': changed_defaults,
                'removed_parameters': removed_parameters,
                'counts': {
                    'new': len(new_parameters),
                    'changed': len(changed_defaults),
                    'removed': len(removed_parameters),
                    'total': len(new_parameters) + len(changed_defaults) + len(removed_parameters),
                },
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting defaults sync: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def revert_config_to_default(self):
        """Revert all configuration to defaults."""
        try:
            service = self._get_config_service()
            success = service.revert_to_default()
            if success:
                service.save_config()

            return JSONResponse(content={
                'success': success,
                'message': 'Configuration reverted to defaults' if success else 'Failed to revert',
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error reverting config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def revert_section_to_default(self, section: str):
        """Revert a section to defaults."""
        try:
            service = self._get_config_service()
            success = service.revert_to_default(section=section)
            if success:
                service.save_config()

            return JSONResponse(content={
                'success': success,
                'section': section,
                'message': f"Section '{section}' reverted to defaults" if success else 'Failed to revert',
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error reverting section: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def revert_parameter_to_default(self, section: str, parameter: str):
        """Revert a single parameter to default."""
        try:
            service = self._get_config_service()
            success = service.revert_to_default(section=section, param=parameter)
            if success:
                service.save_config()

            default_value = service.get_default_parameter(section, parameter)

            return JSONResponse(content={
                'success': success,
                'section': section,
                'parameter': parameter,
                'default_value': default_value,
                'message': f"Parameter reverted to default" if success else 'Failed to revert',
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error reverting parameter: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_config_backup_history(self, request: Request):
        """Get list of configuration backups."""
        try:
            limit = int(request.query_params.get('limit', 20))
            service = self._get_config_service()
            backups = service.get_backup_history(limit=limit)

            return JSONResponse(content={
                'success': True,
                'backups': [b.to_dict() for b in backups],
                'count': len(backups),
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting backup history: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def restore_config_backup(self, backup_id: str):
        """Restore configuration from a backup."""
        try:
            service = self._get_config_service()
            success = service.restore_backup(backup_id)

            return JSONResponse(content={
                'success': success,
                'backup_id': backup_id,
                'message': 'Configuration restored from backup' if success else 'Failed to restore backup',
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error restoring backup: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def export_config(self, request: Request):
        """Export configuration."""
        try:
            sections = request.query_params.get('sections')
            changes_only = request.query_params.get('changes_only', 'false').lower() == 'true'

            sections_list = sections.split(',') if sections else None

            service = self._get_config_service()
            exported = service.export_config(sections=sections_list, changes_only=changes_only)

            return JSONResponse(content={
                'success': True,
                'config': exported,
                'changes_only': changes_only,
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error exporting config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def import_config(self, body: ConfigImportRequest):
        """Import configuration."""
        # Rate limiting check
        allowed, retry_after = self.config_rate_limiter.is_allowed('config_write')
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    'success': False,
                    'error': 'Too many requests',
                    'retry_after': retry_after,
                    'timestamp': time.time()
                },
                headers={'Retry-After': str(retry_after)}
            )

        try:
            service = self._get_config_service()
            success, diffs = service.import_config(body.data, body.merge_mode)

            if success:
                service.save_config()

            return JSONResponse(content={
                'success': success,
                'merge_mode': body.merge_mode,
                'changes': [d.to_dict() for d in diffs],
                'changes_count': len(diffs),
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error importing config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def search_config_parameters(self, request: Request):
        """Search configuration parameters with filtering and pagination."""
        try:
            query = request.query_params.get('q', '')
            section = request.query_params.get('section')
            param_type = request.query_params.get('type')
            modified_only = request.query_params.get('modified_only', '').lower() == 'true'
            limit = int(request.query_params.get('limit', 50))
            offset = int(request.query_params.get('offset', 0))

            service = self._get_config_service()
            result = service.search_parameters(
                query=query,
                section=section,
                param_type=param_type,
                modified_only=modified_only,
                limit=limit,
                offset=offset
            )

            return JSONResponse(content={
                'success': True,
                'query': query,
                'filters': {
                    'section': section,
                    'type': param_type,
                    'modified_only': modified_only
                },
                **result,
                'timestamp': time.time()
            })
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error searching config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_config_audit_log(self, request: Request):
        """Get configuration change audit log."""
        try:
            limit = int(request.query_params.get('limit', 100))
            offset = int(request.query_params.get('offset', 0))
            section = request.query_params.get('section')
            action = request.query_params.get('action')

            service = self._get_config_service()
            result = service.get_audit_log(
                limit=limit,
                offset=offset,
                section=section,
                action=action
            )

            return JSONResponse(content={
                'success': True,
                **result,
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting audit log: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== System Management ====================

    async def get_system_status(self):
        """Get current system status for health checks."""
        try:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()

            return JSONResponse(content={
                'success': True,
                'status': 'running',
                'uptime': time.time() - process.create_time(),
                'memory_mb': memory_info.rss / (1024 * 1024),
                'cpu_percent': process.cpu_percent(),
                'pid': process.pid,
                'restart_pending': getattr(self, '_restart_pending', False),
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting system status: {e}")
            return JSONResponse(content={
                'success': True,
                'status': 'running',
                'timestamp': time.time()
            })

    async def get_frontend_config(self):
        """Return frontend configuration for runtime config injection.

        This endpoint provides configuration values that the frontend may need
        at runtime, supporting dynamic host detection and network configuration.
        """
        try:
            return JSONResponse(content={
                'success': True,
                'config': {
                    'api_port': Parameters.HTTP_STREAM_PORT,
                    'websocket_port': Parameters.HTTP_STREAM_PORT,
                    'version': '4.0.0',
                    'api_host': Parameters.HTTP_STREAM_HOST,
                },
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting frontend config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def restart_backend(self, request: Request):
        """Initiate backend restart.

        The backend will exit with code 42, which signals the wrapper script
        (run_main.sh) to restart the application.

        This preserves the dashboard connection and allows config reloading.
        """
        try:
            body = await request.json() if request.headers.get('content-type') == 'application/json' else {}
            reason = body.get('reason', 'User requested restart')

            self.logger.info(f"🔄 Restart requested: {reason}")

            # Mark restart pending
            self._restart_pending = True

            # Create config backup before restart
            try:
                service = self._get_config_service()
                service._create_backup()
                self.logger.info("✅ Config backup created before restart")
            except Exception as e:
                self.logger.warning(f"Could not create backup before restart: {e}")

            # Send response before initiating shutdown
            response = JSONResponse(content={
                'success': True,
                'message': 'Restart initiated',
                'reason': reason,
                'timestamp': time.time()
            })

            # Schedule graceful shutdown with restart exit code
            async def initiate_restart():
                await asyncio.sleep(0.5)  # Allow response to be sent
                self.logger.info("🔄 Initiating restart sequence...")

                # Set shutdown flag
                self.app_controller.shutdown_flag = True

                # Trigger shutdown
                try:
                    await self.app_controller.shutdown()
                except Exception as e:
                    self.logger.error(f"Error during shutdown: {e}")

                # Stop server with restart code
                if self.server:
                    self.server.should_exit = True

                # Exit with restart code (42) for wrapper script to detect
                self.logger.info("🔄 Exiting with restart code 42")
                import os
                os._exit(42)

            asyncio.create_task(initiate_restart())

            return response

        except Exception as e:
            self.logger.error(f"Error initiating restart: {e}")
            raise HTTPException(status_code=500, detail=str(e))