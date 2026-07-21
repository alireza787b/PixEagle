# src/classes/fastapi_handler.py

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import cv2
import numpy as np
import logging
import time
import hashlib
from typing import Any, Dict, Literal, Optional, Set, Tuple, List
from collections import deque
from dataclasses import dataclass
import json
from classes.parameters import Parameters
from classes.config_service import ConfigService
import uvicorn
from classes.webrtc_manager import WebRTCManager
from classes.setpoint_handler import SetpointHandler
from classes.frame_publisher import FramePublisher
from classes.adaptive_quality_engine import AdaptiveQualityEngine
from classes.api_v1_errors import (
    build_api_v1_error_response,
)
from classes.api_exposure_policy import (
    is_http_browser_request_allowed,
    resolve_api_exposure_policy_from_parameters,
)
from classes.api_auth_runtime import (
    APIAuthRuntime,
    authorize_http_request,
    resolve_api_auth_runtime_from_parameters,
)
from classes.api_security_audit import (
    APISecurityAuditError,
    audit_failure_must_block,
    resolve_api_security_audit_logger_from_parameters,
)
from classes.api_security_types import (
    APIAuditPolicy,
    APIPrincipal,
    APIPrincipalKind,
    APISensitivity,
)
from classes.api_v1_actions import (
    ActionType,
    ApiActionStore,
    attach_legacy_action_audit,
    build_action_precondition_failed_response,
    circuit_breaker_safety_bypass_set_action as dispatch_circuit_breaker_safety_bypass_set_action,
    circuit_breaker_safety_bypass_set_action_unlocked as dispatch_circuit_breaker_safety_bypass_set_action_unlocked,
    circuit_breaker_set_action as dispatch_circuit_breaker_set_action,
    circuit_breaker_set_action_unlocked as dispatch_circuit_breaker_set_action_unlocked,
    ensure_api_action_store,
    get_action_resource as dispatch_get_action_resource,
    new_api_action_record,
    operator_abort_action as dispatch_operator_abort_action,
    operator_abort_action_unlocked as dispatch_operator_abort_action_unlocked,
    segmentation_toggle_action as dispatch_segmentation_toggle_action,
    segmentation_toggle_action_unlocked as dispatch_segmentation_toggle_action_unlocked,
    smart_click_action as dispatch_smart_click_action,
    smart_click_action_unlocked as dispatch_smart_click_action_unlocked,
    smart_mode_toggle_action as dispatch_smart_mode_toggle_action,
    smart_mode_toggle_action_unlocked as dispatch_smart_mode_toggle_action_unlocked,
    system_restart_action as dispatch_system_restart_action,
    system_restart_action_unlocked as dispatch_system_restart_action_unlocked,
    start_offboard_action as dispatch_start_offboard_action,
    start_offboard_action_unlocked as dispatch_start_offboard_action_unlocked,
    stop_offboard_action as dispatch_stop_offboard_action,
    stop_offboard_action_unlocked as dispatch_stop_offboard_action_unlocked,
    tracker_restart_action as dispatch_tracker_restart_action,
    tracker_restart_action_unlocked as dispatch_tracker_restart_action_unlocked,
    tracker_switch_action as dispatch_tracker_switch_action,
    tracker_switch_action_unlocked as dispatch_tracker_switch_action_unlocked,
    tracking_redetect_action as dispatch_tracking_redetect_action,
    tracking_redetect_action_unlocked as dispatch_tracking_redetect_action_unlocked,
    tracking_start_action as dispatch_tracking_start_action,
    tracking_start_action_unlocked as dispatch_tracking_start_action_unlocked,
    tracking_stop_action as dispatch_tracking_stop_action,
    tracking_stop_action_unlocked as dispatch_tracking_stop_action_unlocked,
)
from classes.managed_sih import managed_sih_action as dispatch_managed_sih_action
from classes.api_v1_auth_routes import (
    change_auth_password as dispatch_change_auth_password,
    create_auth_user as dispatch_create_auth_user,
    delete_auth_user as dispatch_delete_auth_user,
    get_auth_session as dispatch_get_auth_session,
    get_auth_users as dispatch_get_auth_users,
    login_auth_session as dispatch_login_auth_session,
    logout_auth_session as dispatch_logout_auth_session,
    update_auth_user as dispatch_update_auth_user,
)
from classes.api_v1_log_routes import (
    export_log_session_bundle as dispatch_export_log_session_bundle,
    get_log_session_entries as dispatch_get_log_session_entries,
    get_log_sessions as dispatch_get_log_sessions,
    get_logs_status as dispatch_get_logs_status,
    record_frontend_error as dispatch_record_frontend_error,
)
from classes.api_legacy_control_routes import (
    cancel_activities as dispatch_operator_abort_executor,
    start_offboard_mode as dispatch_offboard_start_executor,
    stop_offboard_mode as dispatch_offboard_stop_executor,
)
from classes.config_sync import (
    ConfigSyncApplyRequest,
    ConfigSyncPlanRequest,
)
from classes.api_legacy_config_routes import (
    ConfigImportRequest,
    ConfigParameterUpdate,
    ConfigSectionUpdate,
    apply_defaults_sync as dispatch_apply_defaults_sync,
    compare_configs as dispatch_compare_configs,
    export_config as dispatch_export_config,
    get_config_audit_log as dispatch_get_config_audit_log,
    get_config_backup_history as dispatch_get_config_backup_history,
    get_config_categories as dispatch_get_config_categories,
    get_config_diff as dispatch_get_config_diff,
    get_config_schema as dispatch_get_config_schema,
    get_config_section_schema as dispatch_get_config_section_schema,
    get_config_sections as dispatch_get_config_sections,
    get_current_config as dispatch_get_current_config,
    get_current_config_section as dispatch_get_current_config_section,
    get_default_config as dispatch_get_default_config,
    get_default_config_section as dispatch_get_default_config_section,
    get_defaults_sync as dispatch_get_defaults_sync,
    import_config as dispatch_import_config,
    plan_defaults_sync as dispatch_plan_defaults_sync,
    restore_config_backup as dispatch_restore_config_backup,
    revert_config_to_default as dispatch_revert_config_to_default,
    revert_parameter_to_default as dispatch_revert_parameter_to_default,
    revert_section_to_default as dispatch_revert_section_to_default,
    search_config_parameters as dispatch_search_config_parameters,
    update_config_parameter as dispatch_update_config_parameter,
    update_config_section as dispatch_update_config_section,
    validate_config_value as dispatch_validate_config_value,
)
from classes.api_legacy_model_routes import (
    delete_model as dispatch_delete_model,
    download_model_file as dispatch_download_model_file,
    get_active_model as dispatch_get_active_model,
    get_model_labels as dispatch_get_model_labels,
    get_models as dispatch_get_models,
    switch_model as dispatch_switch_model,
    upload_model as dispatch_upload_model,
)
from classes.api_legacy_gstreamer_routes import (
    get_gstreamer_status as dispatch_get_gstreamer_status,
    toggle_gstreamer as dispatch_toggle_gstreamer,
)
from classes.api_legacy_media_routes import (
    ClientConnection,
    get_streaming_stats as dispatch_get_streaming_stats,
    get_streaming_status as dispatch_get_streaming_status,
    get_video_health as dispatch_get_video_health,
    reconnect_video as dispatch_reconnect_video,
    video_feed as dispatch_video_feed,
    video_feed_websocket_optimized as dispatch_video_feed_websocket_optimized,
)
from classes.api_legacy_follower_routes import (
    get_configured_follower_mode as dispatch_get_configured_follower_mode,
    get_current_follower_mode as dispatch_get_current_follower_mode,
    get_current_follower_profile as dispatch_get_current_follower_profile,
    get_follower_config_effective as dispatch_get_follower_config_effective,
    get_follower_config_general as dispatch_get_follower_config_general,
    get_follower_health as dispatch_get_follower_health,
    get_follower_profiles as dispatch_get_follower_profiles,
    get_follower_schema as dispatch_get_follower_schema,
    get_follower_setpoints_with_status as dispatch_get_follower_setpoints_with_status,
    restart_follower as dispatch_restart_follower,
    switch_follower_profile as dispatch_switch_follower_profile,
)
from classes.api_legacy_tracker_routes import (
    restart_tracker as dispatch_restart_tracker,
    switch_tracker_to_type as dispatch_switch_tracker_to_type,
)
from classes.api_legacy_osd_routes import (
    get_osd_color_modes as dispatch_get_osd_color_modes,
    get_osd_modes as dispatch_get_osd_modes,
    get_osd_presets as dispatch_get_osd_presets,
    get_osd_status as dispatch_get_osd_status,
    load_osd_preset as dispatch_load_osd_preset,
    set_osd_color_mode as dispatch_set_osd_color_mode,
    toggle_osd as dispatch_toggle_osd,
)
from classes.api_legacy_recording_routes import (
    delete_recording_file as dispatch_delete_recording_file,
    download_recording as dispatch_download_recording,
    get_recording_status as dispatch_get_recording_status,
    get_storage_status as dispatch_get_storage_status,
    list_recordings as dispatch_list_recordings,
    pause_recording as dispatch_pause_recording,
    resume_recording as dispatch_resume_recording,
    set_recording_include_osd as dispatch_set_recording_include_osd,
    start_recording as dispatch_start_recording,
    stop_recording as dispatch_stop_recording,
    toggle_recording as dispatch_toggle_recording,
)
from classes.api_legacy_safety_routes import (
    get_circuit_breaker_statistics as dispatch_get_circuit_breaker_statistics,
    get_circuit_breaker_status as dispatch_get_circuit_breaker_status,
    get_effective_limits as dispatch_get_effective_limits,
    get_follower_safety_limits as dispatch_get_follower_safety_limits,
    get_relevant_sections as dispatch_get_relevant_sections,
    get_safety_config as dispatch_get_safety_config,
    reset_circuit_breaker_statistics as dispatch_reset_circuit_breaker_statistics,
    set_circuit_breaker_safety_bypass_state as dispatch_set_circuit_breaker_safety_bypass_state,
    set_circuit_breaker_state as dispatch_set_circuit_breaker_state,
    toggle_circuit_breaker as dispatch_toggle_circuit_breaker,
    toggle_circuit_breaker_safety_bypass as dispatch_toggle_circuit_breaker_safety_bypass,
)
from classes.api_v1_read_routes import (
    get_config_runtime_status as dispatch_get_config_runtime_status,
    get_following_status as dispatch_get_following_status,
    get_following_telemetry as dispatch_get_following_telemetry,
    get_runtime_status as dispatch_get_runtime_status,
    get_system_about as dispatch_get_system_about,
    get_streaming_media_health as dispatch_get_streaming_media_health,
    get_telemetry_health as dispatch_get_telemetry_health,
    get_tracking_catalog as dispatch_get_tracking_catalog,
    get_tracking_runtime_status as dispatch_get_tracking_runtime_status,
    get_tracking_telemetry as dispatch_get_tracking_telemetry,
)
from classes.api_v1_snapshots import (
    TRACKER_OUTPUT_UNSET,
    classify_following_commander_degradation,
    classify_inactive_following_commander_issue,
    classify_runtime_status,
    coerce_mapping,
    first_present,
    get_active_following_setpoint_handler,
    get_circuit_breaker_snapshot,
    get_following_command_publication_status,
    get_following_profile_status,
    get_following_status_snapshot,
    get_following_telemetry_snapshot,
    get_legacy_follower_telemetry_snapshot,
    get_legacy_runtime_status_snapshot,
    get_legacy_tracker_telemetry_snapshot,
    get_runtime_status_snapshot,
    get_system_about_snapshot,
    get_tracker_following_readiness,
    get_tracker_runtime_status_snapshot,
    get_tracking_catalog_snapshot,
    get_tracking_telemetry_snapshot,
    optional_float_list,
    position_3d_projection,
    sanitize_tracking_field_value,
    serialize_command_intent,
    tracker_output_to_field_map,
)
from classes.api_v1_sitl import (
    frame_status_from_sitl_video_stall,
    get_sitl_validation_status as dispatch_get_sitl_validation_status,
    get_sitl_validation_status_snapshot,
    inject_sitl_commander_publish_failure as dispatch_sitl_commander_publish_failure,
    inject_sitl_mavlink2rest_timeout as dispatch_sitl_mavlink2rest_timeout,
    inject_sitl_mavsdk_disconnect as dispatch_sitl_mavsdk_disconnect,
    inject_sitl_tracker_output as dispatch_sitl_tracker_output,
    inject_sitl_video_stall as dispatch_sitl_video_stall,
    parse_tracker_data_type,
    sitl_error_response,
    sitl_injections_enabled,
    tracker_output_from_sitl_injection,
)
from classes.api_v1_paths import (
    SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH,
    SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH,
    SITL_MAVSDK_DISCONNECT_INJECTION_PATH,
    SITL_TRACKER_OUTPUT_INJECTION_PATH,
    SITL_VALIDATION_INJECTION_PATHS,
    SITL_VIDEO_STALL_INJECTION_PATH,
    is_api_v1_auth_path,
    uses_typed_api_error_envelope,
)
from classes.api_v1_contracts import (
    ACTION_ERROR_RESPONSES,
    ACTION_ROUTE_RESPONSES,
    APIActionAuditEvent,
    APIActionRequest,
    APIActionResponse,
    APIAuthLoginRequest,
    APIAuthLoginResponse,
    APIAuthLogoutResponse,
    APIAuthPasswordChangeRequest,
    APIAuthPasswordChangeResponse,
    APIAuthPrincipal,
    APIAuthSessionResponse,
    APIAuthUserCreateRequest,
    APIAuthUserDeleteRequest,
    APIAuthUserDeleteResponse,
    APIAuthUserMutationResponse,
    APIAuthUserSummary,
    APIAuthUsersResponse,
    APIAuthUserUpdateRequest,
    APICircuitBreakerSetRequest,
    APIConfigRuntimePendingChange,
    APIConfigRestartActionStatus,
    APIConfigRuntimeStatusResponse,
    APIErrorResponse,
    APIFrontendErrorReportRequest,
    APIFrontendErrorReportResponse,
    APIFollowingCommandPublicationStatus,
    APIFollowingProfileStatus,
    APIFollowingStatusResponse,
    APIFollowingTelemetryResponse,
    APILogSessionEntriesResponse,
    APILogSessionsResponse,
    APILogStatusResponse,
    APIRuntimeModesStatus,
    APIRuntimeStatusResponse,
    APIRuntimeSubsystemStatus,
    APISystemAboutResponse,
    APISystemBackendStatus,
    APISystemGitMetadata,
    APISystemRepositoryMetadata,
    APISystemRuntimeMetadata,
    APISystemUpdateStatus,
    APIStreamingConfigSummary,
    APIStreamingFrameHealth,
    APIStreamingMediaHealthResponse,
    APIStreamingSecurityBoundary,
    APIStreamingTransportHealth,
    APITrackingCatalogEntry,
    APITrackingCatalogResponse,
    APITrackingBoundingBox,
    APITrackingClickPosition,
    APITrackingRuntimeStatusResponse,
    APITrackingSmartClickRequest,
    APITrackingStartRequest,
    APITrackingTelemetryResponse,
    APITrackerSwitchRequest,
    APITelemetryHealthResponse,
    APITelemetryPayloadHealth,
    APITelemetryRequestFreshness,
    APITelemetryTransportHealth,
    AUTH_ROUTE_RESPONSES,
    CONFIG_RUNTIME_STATUS_ERROR_RESPONSES,
    FOLLOWING_STATUS_ERROR_RESPONSES,
    FOLLOWING_TELEMETRY_ERROR_RESPONSES,
    LOGS_EXPORT_RESPONSES,
    LOGS_ERROR_RESPONSES,
    RUNTIME_STATUS_ERROR_RESPONSES,
    SYSTEM_ABOUT_ERROR_RESPONSES,
    STREAMING_MEDIA_HEALTH_ERROR_RESPONSES,
    SITLCommandIntentSummary,
    SITLCommanderPublishFailureInjection,
    SITLCommanderPublishFailureResponse,
    SITLCommanderPublishFailureSummary,
    SITLDisconnectResultSummary,
    SITLFrameStatusSummary,
    SITLMavlink2RestTimeoutInjection,
    SITLMavlink2RestTimeoutResponse,
    SITLMavlink2RestTimeoutSummary,
    SITLMavlinkTelemetrySummary,
    SITLMavsdkDisconnectInjection,
    SITLMavsdkDisconnectResponse,
    SITLMavsdkDisconnectSummary,
    SITLOffboardCommanderSummary,
    SITLPX4ConnectionSummary,
    SITLManagedLifecycleRequest,
    SITLManagedLifecycleStatus,
    SITLTrackerInjectionResponse,
    SITLTrackerInjectionSummary,
    SITLTrackerOutputInjection,
    SITLValidationCommand,
    SITLValidationLatestRun,
    SITLValidationPlanSummary,
    SITLValidationStatusResponse,
    SITLVideoStallInjection,
    SITLVideoStallResponse,
    SITLVideoStallSummary,
    SITL_ERROR_RESPONSES,
    SITL_VALIDATION_STATUS_ERROR_RESPONSES,
    TELEMETRY_HEALTH_ERROR_RESPONSES,
    TRACKING_CATALOG_ERROR_RESPONSES,
    TRACKING_RUNTIME_STATUS_ERROR_RESPONSES,
    TRACKING_TELEMETRY_ERROR_RESPONSES,
)
from classes.fastapi_api_v1_routes import register_api_v1_routes
from classes.tracker_output import TrackerDataType
from classes.tracking_roi import (
    TrackingROIError,
    tracking_point_to_pixels,
    tracking_roi_to_pixels,
)
from classes.model_manager import ModelManager, model_manager_kwargs_from_parameters
from classes.app_version import PIXEAGLE_VERSION


BACKEND_RESTART_SHUTDOWN_TIMEOUT_SECONDS = 10.0
BACKEND_RESTART_EXIT_CODE = 42

# Performance monitoring
from contextlib import asynccontextmanager
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import os

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
    """
    Optimized frame encoding with frame_id-based caching.

    Uses monotonic frame_id from FramePublisher instead of MD5 hashing
    (zero hash overhead). The encoding lock only protects the cache dict,
    not cv2.imencode itself (which is thread-safe for independent buffers).
    """

    def __init__(self, max_cache_size: int = 10):
        self.frame_cache: Dict[str, CachedFrame] = {}
        self.max_cache_size = max_cache_size
        self.encoder_pool = ThreadPoolExecutor(max_workers=Parameters.ENCODING_THREADS)
        self._cache_lock = threading.Lock()
        self._last_frame_id: int = -1

    def encode_frame_for_id(self, frame: np.ndarray, frame_id: int, quality: int) -> bytes:
        """
        Encode frame using frame_id for dedup instead of MD5 hash.

        If the same frame_id + quality was already encoded, returns cached bytes.
        cv2.imencode runs without any lock (thread-safe for independent buffers).
        """
        cache_key = f"{frame_id}_{quality}"

        # Check cache (lightweight lock on dict only)
        if getattr(Parameters, 'ENABLE_FRAME_CACHE', True):
            with self._cache_lock:
                if cache_key in self.frame_cache:
                    cached = self.frame_cache[cache_key]
                    if time.time() - cached.timestamp < getattr(Parameters, 'CACHE_TTL_MS', 100) / 1000:
                        return cached.data

        # Skip identical frames
        if getattr(Parameters, 'SKIP_IDENTICAL_FRAMES', True) and frame_id == self._last_frame_id:
            with self._cache_lock:
                # Return any cached version at this quality
                if cache_key in self.frame_cache:
                    return self.frame_cache[cache_key].data
        self._last_frame_id = frame_id

        # Encode without lock (cv2.imencode is thread-safe)
        ret, buffer = cv2.imencode('.jpg', frame,
                                   [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ret:
            raise ValueError("Failed to encode frame")

        frame_bytes = buffer.tobytes()

        # Update cache
        if getattr(Parameters, 'ENABLE_FRAME_CACHE', True):
            with self._cache_lock:
                self.frame_cache[cache_key] = CachedFrame(
                    data=frame_bytes,
                    timestamp=time.time(),
                    hash=str(frame_id),
                    quality=quality,
                )
                # Evict oldest if over limit
                if len(self.frame_cache) > self.max_cache_size:
                    oldest_key = min(self.frame_cache.keys(),
                                    key=lambda k: self.frame_cache[k].timestamp)
                    del self.frame_cache[oldest_key]

        return frame_bytes

    async def encode_frame_async(self, frame: np.ndarray, frame_id: int, quality: int) -> bytes:
        """Async wrapper for frame encoding."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.encoder_pool,
            self.encode_frame_for_id,
            frame, frame_id, quality,
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

        # Thread-safe frame publisher (shared with app_controller)
        self.frame_publisher: FramePublisher = app_controller.frame_publisher

        # Streaming optimization (frame_id-based, no MD5 hashing)
        self.stream_optimizer = StreamingOptimizer(
            max_cache_size=getattr(Parameters, 'MAX_FRAME_CACHE_SIZE', 10)
        )

        # Unified adaptive quality engine (EWMA bandwidth + CPU + encoding time)
        self.quality_engine = AdaptiveQualityEngine()

        # Fail-closed process exposure policy shared by HTTP and WebSockets
        self.exposure_policy = resolve_api_exposure_policy_from_parameters(Parameters)
        self.api_auth_runtime = resolve_api_auth_runtime_from_parameters(Parameters)
        self.security_audit_logger = resolve_api_security_audit_logger_from_parameters(Parameters)

        # Rate limiter for config write endpoints (10 requests per minute)
        self.config_rate_limiter = RateLimiter(max_requests=60, window_seconds=60)  # 1/sec average for private system

        # WebRTC Manager (uses FramePublisher instead of direct video_handler access)
        self.webrtc_manager = WebRTCManager(
            self.frame_publisher,
            self.exposure_policy,
            self.api_auth_runtime,
            self.security_audit_logger,
        )

        # Detection Model Manager
        self.model_manager = ModelManager(
            **model_manager_kwargs_from_parameters(Parameters)
        )
        self.model_ingest_semaphore = asyncio.Semaphore(1)
        self._api_action_store = ApiActionStore()

        # FastAPI app
        self.app = FastAPI(title="PixEagle API", version=PIXEAGLE_VERSION)
        self.app.add_exception_handler(
            RequestValidationError,
            self._handle_request_validation_error,
        )
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
    
    def _setup_middleware(self):
        """Configure explicit CORS policy for the selected exposure mode."""
        # Starlette prepends each middleware registration. Register authorization
        # first so validated browser requests traverse Origin -> CORS -> auth.
        # This keeps hostile Host/Origin requests outside CORS while allowing an
        # approved dashboard origin to observe a fail-closed 401/403 response.
        self.app.middleware("http")(self._enforce_http_authorization)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=list(self.exposure_policy.cors_allowed_origins),
            allow_credentials=self.exposure_policy.allow_credentials,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Accept",
                "Authorization",
                "Cache-Control",
                "Content-Type",
                "Expires",
                "Idempotency-Key",
                "Pragma",
                "X-PixEagle-CSRF",
                self.api_auth_runtime.csrf_header_name,
                "X-Request-ID",
            ],
            expose_headers=[
                "Content-Disposition",
                "X-PixEagle-Run-ID",
                "X-PixEagle-Log-Export-Sha256",
                "X-PixEagle-Log-Export-Size",
                "X-PixEagle-Claim-Boundary",
            ],
            max_age=3600
        )
        # Register last so Host/Origin validation remains the outer boundary and
        # rejects DNS-rebinding attempts before CORS handles a preflight.
        self.app.middleware("http")(self._enforce_http_browser_origin)

    def _record_security_audit_event(
        self,
        *,
        event_type: str,
        outcome: str,
        reason: str,
        transport: str,
        method: Optional[str],
        path: str,
        status_code: Optional[int],
        principal: APIPrincipal,
        audit_policy: APIAuditPolicy | str,
        sensitivity: APISensitivity | str,
        client_host: Optional[str] = None,
        host_header: Optional[str] = None,
        origin: Optional[str] = None,
        sec_fetch_site: Optional[str] = None,
        missing_scopes: tuple[str, ...] = (),
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record a sanitized security audit event without exposing credentials."""
        audit_logger = getattr(self, "security_audit_logger", None)
        if audit_logger is None:
            return True
        try:
            recorded = audit_logger.record_event(
                event_type=event_type,
                outcome=outcome,
                reason=reason,
                transport=transport,
                method=method,
                path=path,
                status_code=status_code,
                principal=principal,
                audit_policy=audit_policy,
                sensitivity=sensitivity,
                client_host=client_host,
                host_header=host_header,
                origin=origin,
                sec_fetch_site=sec_fetch_site,
                missing_scopes=missing_scopes,
                request_id=request_id,
                metadata=metadata,
            )
            if recorded:
                return True
            return not audit_failure_must_block(
                audit_policy=audit_policy,
                outcome=outcome,
            )
        except APISecurityAuditError as exc:
            logging.getLogger(__name__).error("API security audit write failed: %s", exc)
            return not audit_failure_must_block(
                audit_policy=audit_policy,
                outcome=outcome,
            )

    def _record_http_auth_audit(
        self,
        request: Request,
        auth_result,
    ) -> bool:
        return self._record_security_audit_event(
            event_type="api.http.authorization",
            outcome="allowed" if auth_result.allowed else "denied",
            reason=auth_result.reason,
            transport="http",
            method=getattr(request, "method", None),
            path=str(getattr(getattr(request, "url", None), "path", "")),
            status_code=200 if auth_result.allowed else auth_result.status_code,
            principal=auth_result.principal,
            audit_policy=auth_result.audit_policy,
            sensitivity=auth_result.sensitivity,
            client_host=getattr(getattr(request, "client", None), "host", None),
            host_header=request.headers.get("host"),
            origin=request.headers.get("origin"),
            sec_fetch_site=request.headers.get("sec-fetch-site"),
            missing_scopes=auth_result.missing_scopes,
            request_id=request.headers.get("x-request-id"),
        )

    def _security_audit_unavailable_response(self, path: str):
        if self._uses_typed_api_error_envelope(path):
            return self._api_v1_error_response(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="security_audit_unavailable",
                detail="API security audit event could not be recorded.",
                path=path,
            )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "API security audit event could not be recorded."},
        )

    async def _enforce_http_browser_origin(self, request: Request, call_next):
        """Reject untrusted Host/Origin requests before CORS or route execution."""
        request_path = str(getattr(getattr(request, "url", None), "path", ""))
        if not is_http_browser_request_allowed(
            host=request.headers.get("host"),
            origin=request.headers.get("origin"),
            sec_fetch_site=request.headers.get("sec-fetch-site"),
            policy=self.exposure_policy,
        ):
            self._record_security_audit_event(
                event_type="api.http.origin",
                outcome="denied",
                reason="browser_origin_not_allowed",
                transport="http",
                method=getattr(request, "method", None),
                path=request_path,
                status_code=status.HTTP_403_FORBIDDEN,
                principal=APIPrincipal.anonymous(),
                audit_policy=APIAuditPolicy.SECURITY_CRITICAL,
                sensitivity=APISensitivity.SYSTEM,
                client_host=getattr(getattr(request, "client", None), "host", None),
                host_header=request.headers.get("host"),
                origin=request.headers.get("origin"),
                sec_fetch_site=request.headers.get("sec-fetch-site"),
                request_id=request.headers.get("x-request-id"),
            )
            if self._uses_typed_api_error_envelope(request_path):
                return self._api_v1_error_response(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code="browser_origin_not_allowed",
                    detail="Browser Origin not allowed",
                    path=request_path,
                )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Browser Origin not allowed"},
            )

        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    async def _enforce_http_authorization(self, request: Request, call_next):
        """Authorize validated HTTP requests inside the standard CORS boundary."""
        request_path = str(getattr(getattr(request, "url", None), "path", ""))
        if request.method.upper() != "OPTIONS":
            auth_result = authorize_http_request(
                runtime=self.api_auth_runtime,
                method=request.method,
                path=request_path,
                headers=request.headers,
                client_host=getattr(request.client, "host", None),
                host_header=request.headers.get("host"),
                exposure_policy=self.exposure_policy,
                query_params=request.query_params,
            )
            if not self._record_http_auth_audit(request, auth_result):
                return self._security_audit_unavailable_response(request_path)
            if not auth_result.allowed:
                headers = {}
                if auth_result.is_authentication_failure:
                    headers["WWW-Authenticate"] = "Bearer"
                if self._uses_typed_api_error_envelope(str(request.url.path)):
                    response = self._api_v1_error_response(
                        status_code=auth_result.status_code,
                        code=auth_result.reason,
                        detail={
                            "message": "API request not authorized",
                            "reason": auth_result.reason,
                            "missing_scopes": list(auth_result.missing_scopes),
                        },
                        path=request_path,
                    )
                    for key, value in headers.items():
                        response.headers[key] = value
                    return response
                return JSONResponse(
                    status_code=auth_result.status_code,
                    content={
                        "detail": "API request not authorized",
                        "reason": auth_result.reason,
                        "missing_scopes": list(auth_result.missing_scopes),
                    },
                    headers=headers,
                )
            request.state.api_principal = auth_result.principal

        return await call_next(request)
    
    def define_routes(self):
        """Define all API routes."""
        # Streaming endpoints
        self.app.get("/video_feed")(self.video_feed)
        self.app.websocket("/ws/video_feed")(self.video_feed_websocket_optimized)
        self.app.websocket("/ws/webrtc_signaling")(self.webrtc_manager.signaling_handler)
        
        # Streaming status API
        self.app.get("/api/streaming/status")(self.get_streaming_status)

        # Telemetry
        self.app.get("/telemetry/tracker_data")(self.tracker_data)
        self.app.get("/telemetry/follower_data")(self.follower_data)
        self.app.get("/status")(self.get_status)
        register_api_v1_routes(self, globals())
        self.app.get("/stats")(self.get_streaming_stats)
        self.app.get("/api/video/health")(self.get_video_health)
        self.app.post("/api/video/reconnect")(self.reconnect_video)
        
        self.app.get("/api/compatibility/report")(self.get_compatibility_report)
        self.app.get("/api/system/schema_info")(self.get_schema_info)

        # Debug endpoints
        self.app.get("/debug/coordinate_mapping")(self.get_coordinate_mapping_info)

        # Local process administration.
        self.app.post("/commands/quit")(self.quit)
        
        # Follower API
        self.app.get("/api/follower/schema")(self.get_follower_schema)
        self.app.get("/api/follower/profiles")(self.get_follower_profiles)
        self.app.get("/api/follower/current-profile")(self.get_current_follower_profile)
        self.app.get("/api/follower/configured-mode")(self.get_configured_follower_mode)
        self.app.get("/api/follower/setpoints-status")(self.get_follower_setpoints_with_status)
        self.app.post("/api/follower/switch-profile")(self.switch_follower_profile)
        self.app.get("/api/follower/health")(self.get_follower_health)
        self.app.post("/api/follower/restart")(self.restart_follower)  # Hot-reload: recreate follower with fresh config

        # Detection Model Management API
        self.app.get("/api/models")(self.get_models)
        self.app.get("/api/models/active")(self.get_active_model)
        self.app.get("/api/models/{model_id}/labels")(self.get_model_labels)
        self.app.post("/api/models/switch")(self.switch_model)
        self.app.post("/api/models/upload")(self.upload_model)
        self.app.get("/api/models/{model_id}/file")(self.download_model_file)
        self.app.delete("/api/models/{model_id}")(self.delete_model)
        # Backward-compat aliases (deprecated — use /api/models/* instead)
        self.app.get("/api/yolo/models")(self.get_models)
        self.app.get("/api/yolo/active-model")(self.get_active_model)
        self.app.get("/api/yolo/models/{model_id}/labels")(self.get_model_labels)
        self.app.post("/api/yolo/switch-model")(self.switch_model)
        self.app.post("/api/yolo/upload")(self.upload_model)
        self.app.post("/api/yolo/delete/{model_id}")(self.delete_model)

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
        self.app.get("/api/osd/color-modes")(self.get_osd_color_modes)
        self.app.post("/api/osd/color-mode/{mode}")(self.set_osd_color_mode)
        self.app.get("/api/osd/modes")(self.get_osd_modes)

        # GStreamer QGC Output API endpoints
        self.app.get("/api/gstreamer/status")(self.get_gstreamer_status)
        self.app.post("/api/gstreamer/toggle")(self.toggle_gstreamer)

        # Recording API endpoints
        self.app.post("/api/recording/start")(self.start_recording)
        self.app.post("/api/recording/pause")(self.pause_recording)
        self.app.post("/api/recording/resume")(self.resume_recording)
        self.app.post("/api/recording/stop")(self.stop_recording)
        self.app.get("/api/recording/status")(self.get_recording_status)
        self.app.post("/api/recording/toggle")(self.toggle_recording)
        self.app.get("/api/recordings")(self.list_recordings)
        self.app.get("/api/recordings/{filename}")(self.download_recording)
        self.app.delete("/api/recordings/{filename}")(self.delete_recording_file)
        self.app.get("/api/storage/status")(self.get_storage_status)
        self.app.post("/api/recording/include-osd/{enabled}")(self.set_recording_include_osd)

        # Safety configuration API endpoints (v3.5.0+)
        self.app.get("/api/safety/config")(self.get_safety_config)
        self.app.get("/api/safety/limits/{follower_name}")(self.get_follower_safety_limits)

        # Follower configuration API endpoints (v6.1.0+)
        self.app.get("/api/follower/config/general")(self.get_follower_config_general)
        self.app.get("/api/follower/config/{follower_name}")(self.get_follower_config_effective)

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
        self.app.post("/api/config/defaults-sync/plan")(self.plan_defaults_sync)
        self.app.post("/api/config/defaults-sync/apply")(self.apply_defaults_sync)
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
        self.app.get("/api/system/status")(self.get_system_status)
        self.app.get("/api/system/config")(self.get_frontend_config)

    def _media_principal_is_active(self, principal: Optional[APIPrincipal]) -> bool:
        """Return whether a long-lived media client's browser session is active."""
        if principal is None or principal.kind != APIPrincipalKind.SESSION:
            return True
        runtime = getattr(self, "api_auth_runtime", None)
        return bool(runtime and runtime.principal_session_is_active(principal))

    def _record_media_session_revoked(
        self,
        *,
        principal: Optional[APIPrincipal],
        transport: str,
        path: str,
    ) -> None:
        if principal is None or principal.kind != APIPrincipalKind.SESSION:
            return
        self._record_security_audit_event(
            event_type="api.media.session",
            outcome="denied",
            reason="session_expired_or_revoked",
            transport=transport,
            method="GET" if transport == "http" else "WEBSOCKET",
            path=path,
            status_code=401 if transport == "http" else 1008,
            principal=principal,
            audit_policy=APIAuditPolicy.SENSITIVE_READ,
            sensitivity=APISensitivity.MEDIA,
        )

    async def video_feed(self, request: Request):
        """Optimized HTTP MJPEG streaming with adaptive quality."""
        return await dispatch_video_feed(self, request)
    
    async def video_feed_websocket_optimized(self, websocket: WebSocket):
        """Optimized WebSocket streaming with adaptive quality and queuing."""
        return await dispatch_video_feed_websocket_optimized(self, websocket)

    def _update_active_connection_count(self) -> None:
        """Refresh aggregate active connection stats from tracked clients."""
        self.stats['active_connections'] = len(self.http_connections) + len(self.ws_connections)

    def _is_websocket_client_stale(
        self,
        client: ClientConnection,
        *,
        current_time: float,
        stale_timeout: float,
    ) -> bool:
        """Return true when a WebSocket client has missed its media freshness window."""
        reference_time = client.last_frame_time if client.last_frame_time > 0 else client.connected_at
        return current_time - reference_time > stale_timeout

    def _stale_websocket_client_ids(
        self,
        *,
        current_time: float,
        stale_timeout: float,
    ) -> List[str]:
        """List stale WebSocket client IDs without mutating connection state."""
        return [
            client_id
            for client_id, client in self.ws_connections.items()
            if self._is_websocket_client_stale(
                client,
                current_time=current_time,
                stale_timeout=stale_timeout,
            )
        ]

    async def _cleanup_websocket_client(
        self,
        client_id: str,
        *,
        close_code: Optional[int] = None,
        close_reason: str = "",
    ) -> bool:
        """Remove one WebSocket client and unregister its streaming resources once."""
        async with self.connection_lock:
            client = self.ws_connections.pop(client_id, None)
            self._update_active_connection_count()

        if client is None:
            return False

        try:
            self.quality_engine.unregister_client(client_id)
        except Exception as exc:
            self.logger.warning("Error unregistering WebSocket quality client %s: %s", client_id, exc)

        try:
            self.frame_publisher.unregister_client()
        except Exception as exc:
            self.logger.warning("Error unregistering WebSocket frame client %s: %s", client_id, exc)

        websocket = getattr(client, "websocket", None)
        if websocket is not None and close_code is not None:
            try:
                await websocket.close(code=close_code, reason=close_reason)
            except Exception as exc:
                self.logger.debug("WebSocket close ignored for %s: %s", client_id, exc)

        return True

    async def _close_all_websocket_clients(
        self,
        *,
        close_code: int,
        close_reason: str,
    ) -> int:
        """Close and unregister every tracked WebSocket streaming client."""
        async with self.connection_lock:
            client_ids = list(self.ws_connections.keys())

        closed = 0
        for client_id in client_ids:
            if await self._cleanup_websocket_client(
                client_id,
                close_code=close_code,
                close_reason=close_reason,
            ):
                closed += 1
        return closed
    
    async def _ws_send_frames(self, websocket: WebSocket, client: ClientConnection):
        """Send frames to WebSocket client with unified adaptive quality."""
        last_send_time = 0.0
        last_frame_id = -1
        consecutive_errors = 0

        while not self.is_shutting_down:
            current_time = time.time()

            # Precise sleep instead of busy-wait
            remaining = self.frame_interval - (current_time - last_send_time)
            if remaining > 0:
                await asyncio.sleep(remaining)
                continue

            # Get frame from thread-safe publisher
            stamped = self.frame_publisher.get_latest(
                prefer_osd=Parameters.STREAM_PROCESSED_OSD
            )
            if stamped is None:
                await asyncio.sleep(0.01)
                continue

            # Skip identical frames
            if stamped.frame_id == last_frame_id:
                await asyncio.sleep(0.005)
                continue

            try:
                # Encode frame with frame_id-based caching
                encode_start = time.monotonic()
                frame_bytes = await self.stream_optimizer.encode_frame_async(
                    stamped.frame, stamped.frame_id, client.quality
                )
                encode_time = time.monotonic() - encode_start

                # Adaptive quality (unified engine)
                if Parameters.ENABLE_ADAPTIVE_QUALITY:
                    client.quality = self.quality_engine.report_frame_sent(
                        client.id, len(frame_bytes), encode_time
                    )

                # Send frame with metadata
                message = {
                    'type': 'frame',
                    'timestamp': current_time,
                    'quality': client.quality,
                    'size': len(frame_bytes),
                    'frame_id': stamped.frame_id,
                }

                # Send metadata then binary frame
                await websocket.send_json(message)
                await websocket.send_bytes(frame_bytes)

                last_send_time = time.time()
                last_frame_id = stamped.frame_id
                client.last_frame_time = last_send_time
                consecutive_errors = 0

                self.stats['frames_sent'] += 1
                self.stats['total_bandwidth'] += len(frame_bytes)

            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    self.logger.error(f"WebSocket stream terminated after {consecutive_errors} send errors: {e}")
                    client.frame_drops += 1
                    self.stats['frames_dropped'] += 1
                    break
                self.logger.warning(f"WebSocket send error ({consecutive_errors}/3): {e}")
                client.frame_drops += 1
                self.stats['frames_dropped'] += 1
                await asyncio.sleep(0.1)
    
    async def _ws_receive_messages(self, websocket: WebSocket, client: ClientConnection):
        """Handle incoming WebSocket messages."""
        try:
            while not self.is_shutting_down:
                message = await websocket.receive_json()

                msg_type = message.get('type')

                # Handle quality adjustment requests
                if msg_type == 'quality':
                    requested_quality = message.get('quality')
                    if isinstance(requested_quality, (int, float)):
                        requested_quality = int(requested_quality)
                        if Parameters.MIN_QUALITY <= requested_quality <= Parameters.MAX_QUALITY:
                            self.quality_engine.set_client_quality(client.id, requested_quality)
                            client.quality = requested_quality
                            self.logger.debug(f"Client {client.id} requested quality: {requested_quality}")

                # Handle heartbeat (echo client_timestamp for RTT-based latency)
                elif msg_type == 'ping':
                    await websocket.send_json({
                        'type': 'pong',
                        'timestamp': time.time(),
                        'client_timestamp': message.get('client_timestamp', 0),
                    })

        except WebSocketDisconnect:
            pass
        except Exception as e:
            self.logger.error(f"Error receiving WebSocket message: {e}")

    async def _ws_monitor_session(
        self,
        websocket: WebSocket,
        client: ClientConnection,
    ) -> None:
        """Close a media WebSocket after browser-session logout or expiry."""
        principal = client.principal
        if principal is None or principal.kind != APIPrincipalKind.SESSION:
            await asyncio.Future()
            return
        while not self.is_shutting_down:
            if not self._media_principal_is_active(principal):
                self._record_media_session_revoked(
                    principal=principal,
                    transport="websocket",
                    path="/ws/video_feed",
                )
                await websocket.close(
                    code=1008,
                    reason="Browser session expired or revoked",
                )
                return
            await asyncio.sleep(0.25)
    
    async def _heartbeat_task(self):
        """Check for stale WebSocket connections periodically."""
        heartbeat_interval = getattr(Parameters, 'WS_HEARTBEAT_INTERVAL', 30)
        stale_multiplier = getattr(Parameters, 'WS_STALE_TIMEOUT_MULTIPLIER', 2)

        while not self.is_shutting_down:
            await asyncio.sleep(heartbeat_interval)

            # Check for stale connections
            current_time = time.time()
            stale_timeout = heartbeat_interval * stale_multiplier
            async with self.connection_lock:
                stale_clients = self._stale_websocket_client_ids(
                    current_time=current_time,
                    stale_timeout=stale_timeout,
                )

            for client_id in stale_clients:
                self.logger.warning(f"Closing stale WebSocket client: {client_id}")
                await self._cleanup_websocket_client(
                    client_id,
                    close_code=1001,
                    close_reason="WebSocket media stream stale",
                )
    
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

    async def _cpu_monitor_task(self):
        """Monitor CPU load for adaptive quality engine."""
        try:
            import psutil
        except ImportError:
            self.logger.warning("psutil not available — CPU-based quality adaptation disabled")
            return

        while not self.is_shutting_down:
            try:
                cpu = psutil.cpu_percent(interval=None)
                self.quality_engine.update_cpu_load(cpu)
            except Exception:
                pass
            await asyncio.sleep(5)

    async def get_streaming_status(self):
        """Report current streaming method, quality, FPS, adaptation status."""
        return await dispatch_get_streaming_status(self)

    async def get_streaming_stats(self):
        """Get current streaming statistics."""
        return await dispatch_get_streaming_stats(self)

    async def _execute_tracking_start_action(self, bbox: APITrackingBoundingBox):
        """
        Internal executor to start tracking with the provided bounding box.

        Args:
            bbox: Explicit normalized or pixel bounding box for tracking.

        Returns:
            dict: Status of the operation.
        """
        try:
            frame_snapshot = self.app_controller.get_tracking_input_frame_snapshot()
            if frame_snapshot is None:
                raise HTTPException(
                    status_code=409,
                    detail="Video source is unavailable. Restore camera connection before starting tracking."
                )
            frame_height, frame_width = frame_snapshot.shape[:2]
            try:
                bbox_pixels = tracking_roi_to_pixels(
                    x=bbox.x,
                    y=bbox.y,
                    width=bbox.width,
                    height=bbox.height,
                    coordinate_space=bbox.coordinate_space,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
            except TrackingROIError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            # Start tracking using the app controller
            start_result = await self.app_controller.start_tracking(
                bbox_pixels,
                frame=frame_snapshot,
            )
            if not start_result.get("started", False):
                raise HTTPException(
                    status_code=409,
                    detail=f"Tracking start refused: {start_result.get('reason', 'unknown')}",
                )
            result = {
                "status": (
                    "Tracking target replaced"
                    if start_result.get("retargeted")
                    else "Tracking started"
                ),
                "started": True,
                "retargeted": bool(start_result.get("retargeted")),
                "bbox": bbox_pixels,
                "coordinate_space": bbox.coordinate_space,
                "frame_dimensions": {
                    "width": frame_width,
                    "height": frame_height,
                },
            }
            if "target_transition" in start_result:
                result["target_transition"] = start_result["target_transition"]
            return result
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error in start_tracking: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def _execute_tracking_stop_action(self):
        """
        Internal executor to stop tracking.

        Returns:
            dict: Status of the operation.
        """
        try:
            result = await self.app_controller.stop_tracking()
            return {"status": "Tracking stopped", "result": result}
        except Exception as e:
            self.logger.error(f"Error in stop_tracking: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _execute_smart_mode_toggle_action(self):
        """
        Internal executor to toggle the AI-based smart tracking mode.

        Returns:
            dict: Smart mode status.
        """
        try:
            follow_stop = None
            if getattr(self.app_controller, "following_active", False):
                follow_stop = await self.app_controller.cancel_activities_async()
            changed = self.app_controller.toggle_smart_mode()
            status = "enabled" if self.app_controller.smart_mode_active else "disabled"
            result = {
                "status": f"Smart mode {status}",
                "follow_stop": follow_stop,
            }
            if changed is False:
                result["error"] = getattr(
                    self.app_controller,
                    "last_smart_mode_error",
                    None,
                ) or "Smart mode could not be changed."
            return result
        except Exception as e:
            self.logger.error(f"Error in toggle_smart_mode: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _execute_smart_click_action(self, click: APITrackingClickPosition):
        """
        Internal executor for selecting an object in smart mode.

        Args:
            click: Explicit normalized or pixel click coordinates.
        
        Returns:
            dict: Selection status.
        """
        try:
            if not self.app_controller.smart_mode_active:
                raise HTTPException(status_code=400, detail="Smart mode not active.")
            frame_snapshot = self.app_controller.get_tracking_input_frame_snapshot()
            if frame_snapshot is None:
                raise HTTPException(
                    status_code=409,
                    detail="Video source is unavailable. Smart click requires an active frame."
                )
            frame_height, frame_width = frame_snapshot.shape[:2]
            try:
                x_px, y_px = tracking_point_to_pixels(
                    x=click.x,
                    y=click.y,
                    coordinate_space=click.coordinate_space,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
            except TrackingROIError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            selector = getattr(self.app_controller, "select_smart_target", None)
            if not callable(selector):
                raise HTTPException(
                    status_code=503,
                    detail="Tracker mutation state barrier is unavailable.",
                )
            click_result = await selector(x_px, y_px)
            if not isinstance(click_result, dict):
                click_result = {
                    "success": False,
                    "reason": "unknown_smart_click_result",
                    "message": "Smart click did not report a target-selection result.",
                }
            applied = bool(click_result.get("success"))
            return {
                "status": "Click processed" if applied else "Click not applied",
                "applied": applied,
                "x": x_px,
                "y": y_px,
                **click_result,
            }

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error in smart_click: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    def _sitl_injections_enabled(self) -> bool:
        return sitl_injections_enabled()

    def _api_v1_error_response(
        self,
        *,
        status_code: int,
        code: str,
        detail: Any,
        path: str = SITL_TRACKER_OUTPUT_INJECTION_PATH,
    ) -> JSONResponse:
        """Build a typed /api/v1 error envelope."""
        return build_api_v1_error_response(
            status_code=status_code,
            code=code,
            detail=detail,
            path=path,
        )

    def _sitl_error_response(
        self,
        *,
        status_code: int,
        code: str,
        detail: Any,
        path: str = SITL_TRACKER_OUTPUT_INJECTION_PATH,
    ) -> JSONResponse:
        return sitl_error_response(
            status_code=status_code,
            code=code,
            detail=detail,
            path=path,
        )

    @staticmethod
    def _uses_typed_api_error_envelope(path: str) -> bool:
        return uses_typed_api_error_envelope(path)

    def _ensure_action_store(self) -> ApiActionStore:
        """Initialize action storage for tests that construct via __new__."""
        return ensure_api_action_store(self)

    def _action_lock_for_key(
        self,
        action_type: str,
        idempotency_key: Optional[str],
    ) -> Optional[asyncio.Lock]:
        """Return a per-idempotency-key async lock for confirmed mutations."""
        return self._ensure_action_store().action_lock_for_key(
            action_type,
            idempotency_key,
        )

    def _lookup_idempotent_action(
        self,
        action_type: str,
        idempotency_key: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        return self._ensure_action_store().lookup_idempotent_action(
            action_type,
            idempotency_key,
        )

    def _store_action_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return self._ensure_action_store().store_action_record(record)

    @staticmethod
    def _new_api_action_record(
        *,
        action_type: ActionType,
        request: APIActionRequest,
        status_value: Literal["validated", "success", "failure"],
        accepted: bool,
        executed: bool,
        following_active_before: Optional[bool],
        following_active_after: Optional[bool],
        result: Dict[str, Any],
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        return new_api_action_record(
            action_type=action_type,
            request=request,
            status_value=status_value,
            accepted=accepted,
            executed=executed,
            following_active_before=following_active_before,
            following_active_after=following_active_after,
            result=result,
            error=error,
        )

    def _attach_legacy_action_audit(
        self,
        payload: Dict[str, Any],
        *,
        action_type: ActionType,
        internal_handler: str,
        following_active_before: Optional[bool],
        following_active_after: Optional[bool],
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attach an audit record for an internal compatibility executor."""
        return attach_legacy_action_audit(
            payload,
            store=self._ensure_action_store(),
            action_type=action_type,
            internal_handler=internal_handler,
            following_active_before=following_active_before,
            following_active_after=following_active_after,
            error=error,
        )

    def _action_precondition_failed_response(
        self,
        *,
        action_type: ActionType,
        request: APIActionRequest,
        path: str,
        code: str,
        message: str,
    ) -> JSONResponse:
        following_current = bool(getattr(self.app_controller, "following_active", False))
        return build_action_precondition_failed_response(
            store=self._ensure_action_store(),
            action_type=action_type,
            request=request,
            path=path,
            code=code,
            message=message,
            following_active=following_current,
        )

    def _confirmation_required_response(
        self,
        *,
        action_type: ActionType,
        request: APIActionRequest,
        path: str,
    ) -> JSONResponse:
        return self._action_precondition_failed_response(
            action_type=action_type,
            request=request,
            path=path,
            code="ACTION_CONFIRMATION_REQUIRED",
            message=(
                "Set confirm=true to execute this control action, or "
                "dry_run=true to validate the request without mutation."
            ),
        )

    def _idempotency_key_required_response(
        self,
        *,
        action_type: ActionType,
        request: APIActionRequest,
        path: str,
    ) -> JSONResponse:
        return self._action_precondition_failed_response(
            action_type=action_type,
            request=request,
            path=path,
            code="ACTION_IDEMPOTENCY_KEY_REQUIRED",
            message=(
                "Set idempotency_key for confirmed control actions so retries "
                "and concurrent duplicate requests cannot execute the mutation twice."
            ),
        )

    async def _handle_request_validation_error(
        self,
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """
        Return the /api/v1 envelope for SITL validation request errors.

        Existing legacy routes keep FastAPI's default-style `detail` response
        until the broader API migration replaces their contracts.
        """
        errors = jsonable_encoder(exc.errors())
        request_path = str(request.url.path)
        if is_api_v1_auth_path(request_path):
            errors = [
                {
                    key: "[REDACTED]" if key == "input" else value
                    for key, value in error.items()
                }
                for error in errors
            ]
        if self._uses_typed_api_error_envelope(request_path):
            return self._api_v1_error_response(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="REQUEST_VALIDATION_ERROR",
                detail={"validation_errors": errors},
                path=request_path,
            )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": errors},
        )

    @staticmethod
    def _parse_tracker_data_type(value: str) -> TrackerDataType:
        return parse_tracker_data_type(value)

    def _tracker_output_from_sitl_injection(
        self,
        injection: SITLTrackerOutputInjection,
    ) -> Any:
        return tracker_output_from_sitl_injection(injection)

    @staticmethod
    def _frame_status_from_sitl_video_stall(
        injection: SITLVideoStallInjection,
    ) -> Dict[str, Any]:
        return frame_status_from_sitl_video_stall(injection)

    async def inject_sitl_tracker_output(
        self,
        injection: SITLTrackerOutputInjection,
        response: Response,
    ) -> Any:
        return await dispatch_sitl_tracker_output(self, injection, response)

    async def inject_sitl_video_stall(
        self,
        injection: SITLVideoStallInjection,
        response: Response,
    ) -> Any:
        return await dispatch_sitl_video_stall(self, injection, response)

    async def inject_sitl_commander_publish_failure(
        self,
        injection: SITLCommanderPublishFailureInjection,
        response: Response,
    ) -> Any:
        return await dispatch_sitl_commander_publish_failure(self, injection, response)

    async def inject_sitl_mavsdk_disconnect(
        self,
        injection: SITLMavsdkDisconnectInjection,
        response: Response,
    ) -> Any:
        return await dispatch_sitl_mavsdk_disconnect(self, injection, response)

    async def inject_sitl_mavlink2rest_timeout(
        self,
        injection: SITLMavlink2RestTimeoutInjection,
        response: Response,
    ) -> Any:
        return await dispatch_sitl_mavlink2rest_timeout(self, injection, response)

    async def get_sitl_validation_status(self) -> Any:
        return await dispatch_get_sitl_validation_status(self)

    async def get_status(self):
        try:
            return self._get_legacy_runtime_status_snapshot()
        except Exception as e:
            self.logger.error(f"Error in get_status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_auth_session(
        self,
        request: Request,
    ) -> APIAuthSessionResponse:
        return await dispatch_get_auth_session(self, request)

    async def login_auth_session(
        self,
        request: Request,
        request_body: APIAuthLoginRequest,
        response: Response,
    ) -> APIAuthLoginResponse:
        return await dispatch_login_auth_session(self, request, request_body, response)

    async def logout_auth_session(
        self,
        request: Request,
        response: Response,
    ) -> APIAuthLogoutResponse:
        return await dispatch_logout_auth_session(self, request, response)

    async def get_auth_users(
        self,
        request: Request,
    ) -> APIAuthUsersResponse:
        return await dispatch_get_auth_users(self, request)

    async def create_auth_user(
        self,
        request: Request,
        request_body: APIAuthUserCreateRequest,
    ) -> APIAuthUserMutationResponse:
        return await dispatch_create_auth_user(self, request, request_body)

    async def update_auth_user(
        self,
        username: str,
        request: Request,
        request_body: APIAuthUserUpdateRequest,
    ) -> APIAuthUserMutationResponse:
        return await dispatch_update_auth_user(
            self,
            username,
            request,
            request_body,
        )

    async def delete_auth_user(
        self,
        username: str,
        request: Request,
        request_body: APIAuthUserDeleteRequest,
    ) -> APIAuthUserDeleteResponse:
        return await dispatch_delete_auth_user(
            self,
            username,
            request,
            request_body,
        )

    async def change_auth_password(
        self,
        request: Request,
        request_body: APIAuthPasswordChangeRequest,
        response: Response,
    ) -> APIAuthPasswordChangeResponse:
        return await dispatch_change_auth_password(
            self,
            request,
            request_body,
            response,
        )

    async def get_system_about(self):
        return await dispatch_get_system_about(self)

    async def get_runtime_status(self):
        return await dispatch_get_runtime_status(self)

    async def get_config_runtime_status(self, request: Request):
        return await dispatch_get_config_runtime_status(self, request)

    async def get_following_status(self):
        return await dispatch_get_following_status(self)

    async def get_following_telemetry(self):
        return await dispatch_get_following_telemetry(self)

    async def get_telemetry_health(self):
        return await dispatch_get_telemetry_health(self)

    async def get_logs_status(self) -> APILogStatusResponse:
        return await dispatch_get_logs_status(self)

    async def get_log_sessions(
        self,
        limit: int = 50,
    ) -> APILogSessionsResponse:
        return await dispatch_get_log_sessions(self, limit=limit)

    async def get_log_session_entries(
        self,
        run_id: str,
        component: str = "backend",
        level: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        since: Optional[str] = None,
        tail: bool = False,
    ) -> APILogSessionEntriesResponse:
        return await dispatch_get_log_session_entries(
            self,
            run_id=run_id,
            component=component,
            level=level,
            limit=limit,
            offset=offset,
            since=since,
            tail=tail,
        )

    async def export_log_session_bundle(
        self,
        run_id: str,
    ) -> FileResponse:
        return await dispatch_export_log_session_bundle(self, run_id)

    async def record_frontend_error(
        self,
        request: Request,
        request_body: APIFrontendErrorReportRequest,
    ) -> APIFrontendErrorReportResponse:
        return await dispatch_record_frontend_error(self, request, request_body)

    async def get_streaming_media_health(self):
        return await dispatch_get_streaming_media_health(self)

    async def get_tracking_runtime_status(self):
        return await dispatch_get_tracking_runtime_status(self)

    async def get_tracking_catalog(self):
        return await dispatch_get_tracking_catalog(self)

    async def get_tracking_telemetry(self):
        return await dispatch_get_tracking_telemetry(self)

    async def get_video_health(self):
        """Get video subsystem health for degraded-mode observability."""
        return await dispatch_get_video_health(self)

    async def reconnect_video(self):
        """Manually trigger video reconnection attempt."""
        return await dispatch_reconnect_video(self)





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

    async def _execute_segmentation_toggle_action(self):
        """
        Internal executor to toggle segmentation state.

        Returns:
            dict: Status of the operation and the current state of segmentation.
        """
        try:
            if (
                not self.app_controller.segmentation_active
                and self.app_controller.smart_mode_active
            ):
                return {
                    "status": "error",
                    "segmentation_active": False,
                    "error": (
                        "Segmentation overlay cannot be enabled while Smart mode "
                        "is active. Disable Smart mode first."
                    ),
                }
            if not self.app_controller.segmentation_active:
                segmentor = getattr(self.app_controller, "segmentor", None)
                capability_getter = getattr(segmentor, "get_capability_status", None)
                capability = (
                    capability_getter()
                    if callable(capability_getter)
                    else {
                        "available": False,
                        "unavailable_reason": "capability_status_unavailable",
                    }
                )
                if not capability.get("available", False):
                    return {
                        "status": "error",
                        "segmentation_active": False,
                        "error": (
                            "Segmentation is unavailable: "
                            f"{capability.get('unavailable_reason', 'unknown')}"
                        ),
                        "capability": capability,
                    }
            previous_state = bool(self.app_controller.segmentation_active)
            current_state = self.app_controller.toggle_segmentation()
            if current_state is (not previous_state):
                return {"status": "success", "segmentation_active": current_state}
            return {
                "status": "error",
                "segmentation_active": bool(self.app_controller.segmentation_active),
                "error": "Segmentation state change was refused.",
            }
        except Exception as e:
            self.logger.error(f"Error in toggle_segmentation: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _execute_tracking_redetect_action(self):
        """
        Internal executor to attempt redetection of the object being tracked.

        Returns:
            dict: Status of the operation and details of the redetection attempt.
        """
        try:
            result = self.app_controller.initiate_redetection()
            return {"status": "success", "detection_result": result}
        except Exception as e:
            self.logger.error(f"Error in redetect: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _execute_operator_abort_action(self):
        return await dispatch_operator_abort_executor(self)

    async def _execute_tracker_switch_action(self, tracker_type: str):
        response = await dispatch_switch_tracker_to_type(self, tracker_type)
        payload = json.loads(response.body.decode("utf-8"))
        payload["http_status_code"] = response.status_code
        return payload

    async def _execute_tracker_restart_action(self):
        response = await dispatch_restart_tracker(self)
        payload = json.loads(response.body.decode("utf-8"))
        payload["http_status_code"] = response.status_code
        return payload

    async def _execute_circuit_breaker_set_action(self, enabled: bool):
        response = await dispatch_set_circuit_breaker_state(self, enabled)
        payload = json.loads(response.body.decode("utf-8"))
        payload["http_status_code"] = response.status_code
        return payload

    async def _execute_circuit_breaker_safety_bypass_set_action(
        self,
        enabled: bool,
    ):
        response = await dispatch_set_circuit_breaker_safety_bypass_state(
            self,
            enabled,
        )
        payload = json.loads(response.body.decode("utf-8"))
        payload["http_status_code"] = response.status_code
        return payload

    async def circuit_breaker_safety_bypass_set_action(
        self,
        request: APICircuitBreakerSetRequest,
        response: Response,
    ) -> Any:
        return await dispatch_circuit_breaker_safety_bypass_set_action(
            self,
            request,
            response,
        )

    async def _circuit_breaker_safety_bypass_set_action_unlocked(
        self,
        request: APICircuitBreakerSetRequest,
        response: Response,
    ) -> Any:
        return await dispatch_circuit_breaker_safety_bypass_set_action_unlocked(
            self,
            request,
            response,
        )

    async def circuit_breaker_set_action(
        self,
        request: APICircuitBreakerSetRequest,
        response: Response,
    ) -> Any:
        return await dispatch_circuit_breaker_set_action(self, request, response)

    async def _circuit_breaker_set_action_unlocked(
        self,
        request: APICircuitBreakerSetRequest,
        response: Response,
    ) -> Any:
        return await dispatch_circuit_breaker_set_action_unlocked(
            self,
            request,
            response,
        )

    async def start_offboard_action(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_start_offboard_action(self, request, response)

    async def _start_offboard_action_unlocked(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_start_offboard_action_unlocked(self, request, response)

    async def operator_abort_action(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_operator_abort_action(self, request, response)

    async def _operator_abort_action_unlocked(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_operator_abort_action_unlocked(self, request, response)

    async def get_action_resource(self, action_id: str) -> Any:
        return await dispatch_get_action_resource(self, action_id)

    async def _execute_offboard_start_action(self):
        return await dispatch_offboard_start_executor(self)

    async def stop_offboard_action(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_stop_offboard_action(self, request, response)

    async def _stop_offboard_action_unlocked(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_stop_offboard_action_unlocked(self, request, response)

    async def tracking_start_action(
        self,
        request: APITrackingStartRequest,
        response: Response,
    ) -> Any:
        return await dispatch_tracking_start_action(self, request, response)

    async def _tracking_start_action_unlocked(
        self,
        request: APITrackingStartRequest,
        response: Response,
    ) -> Any:
        return await dispatch_tracking_start_action_unlocked(self, request, response)

    async def tracking_stop_action(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_tracking_stop_action(self, request, response)

    async def _tracking_stop_action_unlocked(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_tracking_stop_action_unlocked(self, request, response)

    async def tracking_redetect_action(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_tracking_redetect_action(self, request, response)

    async def _tracking_redetect_action_unlocked(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_tracking_redetect_action_unlocked(self, request, response)

    async def segmentation_toggle_action(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_segmentation_toggle_action(self, request, response)

    async def _segmentation_toggle_action_unlocked(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_segmentation_toggle_action_unlocked(self, request, response)

    async def smart_mode_toggle_action(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_smart_mode_toggle_action(self, request, response)

    async def _smart_mode_toggle_action_unlocked(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_smart_mode_toggle_action_unlocked(self, request, response)

    async def smart_click_action(
        self,
        request: APITrackingSmartClickRequest,
        response: Response,
    ) -> Any:
        return await dispatch_smart_click_action(self, request, response)

    async def _smart_click_action_unlocked(
        self,
        request: APITrackingSmartClickRequest,
        response: Response,
    ) -> Any:
        return await dispatch_smart_click_action_unlocked(self, request, response)

    async def tracker_switch_action(
        self,
        request: APITrackerSwitchRequest,
        response: Response,
    ) -> Any:
        return await dispatch_tracker_switch_action(self, request, response)

    async def _tracker_switch_action_unlocked(
        self,
        request: APITrackerSwitchRequest,
        response: Response,
    ) -> Any:
        return await dispatch_tracker_switch_action_unlocked(self, request, response)

    async def tracker_restart_action(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_tracker_restart_action(self, request, response)

    async def _tracker_restart_action_unlocked(
        self,
        request: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_tracker_restart_action_unlocked(self, request, response)

    async def system_restart_action(
        self,
        request: Request,
        request_body: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_system_restart_action(
            self,
            request_body,
            response,
            request,
        )

    async def _system_restart_action_unlocked(
        self,
        request: Request,
        request_body: APIActionRequest,
        response: Response,
    ) -> Any:
        return await dispatch_system_restart_action_unlocked(
            self,
            request_body,
            response,
            request,
        )

    async def managed_sih_start_action(
        self,
        request: Request,
        request_body: SITLManagedLifecycleRequest,
        response: Response,
    ) -> Any:
        return await dispatch_managed_sih_action(
            self,
            request_body,
            response,
            request,
            operation="start",
        )

    async def managed_sih_stop_action(
        self,
        request: Request,
        request_body: SITLManagedLifecycleRequest,
        response: Response,
    ) -> Any:
        return await dispatch_managed_sih_action(
            self,
            request_body,
            response,
            request,
            operation="stop",
        )

    def _get_legacy_runtime_status_snapshot(self) -> Dict[str, Any]:
        return get_legacy_runtime_status_snapshot(self)

    @staticmethod
    def _classify_following_commander_degradation(
        commander_status: Optional[Dict[str, Any]],
        following_active: bool,
    ) -> Optional[str]:
        return classify_following_commander_degradation(
            commander_status,
            following_active,
        )

    @staticmethod
    def _classify_inactive_following_commander_issue(
        commander_status: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        return classify_inactive_following_commander_issue(commander_status)

    @staticmethod
    def _classify_runtime_status(
        legacy_status: Dict[str, Any],
    ) -> Tuple[str, str, Optional[str]]:
        return classify_runtime_status(legacy_status)

    def _get_following_profile_status(
        self,
        following_active: bool,
    ) -> Tuple[Dict[str, Any], List[str]]:
        return get_following_profile_status(self, following_active)

    def _get_following_command_publication_status(self) -> Dict[str, Any]:
        return get_following_command_publication_status(self)

    def _get_following_status_snapshot(self) -> Dict[str, Any]:
        return get_following_status_snapshot(self)

    def _get_active_following_setpoint_handler(self) -> Optional[Any]:
        return get_active_following_setpoint_handler(self)

    def _get_legacy_follower_telemetry_snapshot(self) -> Dict[str, Any]:
        return get_legacy_follower_telemetry_snapshot(self)

    def _get_legacy_tracker_telemetry_snapshot(self) -> Dict[str, Any]:
        return get_legacy_tracker_telemetry_snapshot(self)

    @staticmethod
    def _coerce_mapping(value: Any) -> Dict[str, Any]:
        return coerce_mapping(value)

    @staticmethod
    def _first_present(*values: Any) -> Any:
        return first_present(*values)

    @staticmethod
    def _serialize_command_intent(intent: Any) -> Optional[Dict[str, Any]]:
        return serialize_command_intent(intent)

    def _get_circuit_breaker_snapshot(
        self,
        legacy_telemetry: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[bool], List[str]]:
        return get_circuit_breaker_snapshot(legacy_telemetry)

    def _get_following_telemetry_snapshot(self) -> Dict[str, Any]:
        return get_following_telemetry_snapshot(self)

    def _get_runtime_status_snapshot(self) -> Dict[str, Any]:
        return get_runtime_status_snapshot(self)

    def _get_system_about_snapshot(self) -> Dict[str, Any]:
        return get_system_about_snapshot(self)

    def _get_sitl_validation_status_snapshot(self) -> Dict[str, Any]:
        return get_sitl_validation_status_snapshot(self)

    def _get_tracker_runtime_status_snapshot(
        self,
        tracker_output: Any = TRACKER_OUTPUT_UNSET,
    ) -> Dict[str, Any]:
        return get_tracker_runtime_status_snapshot(
            self,
            tracker_output=tracker_output,
        )

    @staticmethod
    def _optional_float_list(
        value: Any,
        *,
        expected_length: Optional[int] = None,
        normalized: bool = False,
    ) -> Optional[List[float]]:
        return optional_float_list(
            value,
            expected_length=expected_length,
            normalized=normalized,
        )

    @staticmethod
    def _sanitize_tracking_field_value(value: Any) -> Any:
        return sanitize_tracking_field_value(value)

    @staticmethod
    def _tracker_output_to_field_map(tracker_output: Any) -> Dict[str, Any]:
        return tracker_output_to_field_map(tracker_output)

    @staticmethod
    def _position_3d_projection(value: Any) -> Optional[List[float]]:
        return position_3d_projection(value)

    def _get_tracking_telemetry_snapshot(self) -> Dict[str, Any]:
        return get_tracking_telemetry_snapshot(self)

    def _get_tracking_catalog_snapshot(self) -> Dict[str, Any]:
        return get_tracking_catalog_snapshot(self)

    def _get_tracker_following_readiness(
        self,
        runtime_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return get_tracker_following_readiness(
            self,
            runtime_status=runtime_status,
        )

    async def _execute_offboard_stop_action(self):
        return await dispatch_offboard_stop_executor(self)

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

        # Start CPU monitoring for adaptive quality
        cpu_task = asyncio.create_task(self._cpu_monitor_task())
        self.background_tasks.append(cpu_task)

        self.logger.info("Started background tasks: heartbeat, stats reporter, CPU monitor")

    async def start(self, host=None, port=None):
        """Start the FastAPI server."""
        host = host or Parameters.HTTP_STREAM_HOST
        port = port or Parameters.HTTP_STREAM_PORT
        self.exposure_policy = resolve_api_exposure_policy_from_parameters(
            Parameters,
            bind_host=host,
        )
        host = self.exposure_policy.bind_host
        Parameters.HTTP_STREAM_HOST = host
        self.webrtc_manager.exposure_policy = self.exposure_policy
        if self.exposure_policy.legacy_remote_bind_migrated:
            self.logger.warning(
                "Legacy API bind without API_EXPOSURE_MODE was coerced to %s. "
                "Set Streaming.API_EXPOSURE_MODE=trusted_lan_legacy explicitly "
                "only for temporary isolated-network compatibility.",
                host,
            )
        if self.exposure_policy.is_legacy_remote_exposure:
            self.logger.critical(
                "Starting lab-only trusted_lan_legacy API exposure on %s:%s "
                "with authentication mode %s; direct non-loopback HTTP is not "
                "production-approved. Use a reviewed TLS reverse proxy or "
                "private trusted transport for operational deployments",
                host,
                port,
                Parameters.API_AUTH_MODE,
            )
        
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
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        self.background_tasks = []
        
        # Close streaming transports owned by this handler.
        closed_ws = await self._close_all_websocket_clients(
            close_code=1001,
            close_reason="PixEagle API server stopping",
        )
        async with self.connection_lock:
            http_count = len(self.http_connections)
            self.http_connections.clear()
            self._update_active_connection_count()
        self.logger.info(
            "Closed %s WebSocket streaming clients; cleared %s HTTP MJPEG records",
            closed_ws,
            http_count,
        )

        # Close WebRTC peer connections before releasing shared frame resources.
        if hasattr(self, 'webrtc_manager') and self.webrtc_manager:
            await self.webrtc_manager.shutdown()
        
        # Shutdown encoder pool if exists
        if hasattr(self, 'stream_optimizer') and self.stream_optimizer:
            self.stream_optimizer.encoder_pool.shutdown(wait=True)
        
        if self.server:
            self.logger.info("Stopping FastAPI server...")
            self.server.should_exit = True
            await self.server.shutdown()
            self.logger.info("Stopped FastAPI server")


    async def get_follower_schema(self):
        return await dispatch_get_follower_schema(self)

    async def get_follower_profiles(self):
        return await dispatch_get_follower_profiles(self)

    async def get_current_follower_profile(self):
        return await dispatch_get_current_follower_profile(self)

    async def switch_follower_profile(self, request: Request):
        return await dispatch_switch_follower_profile(self, request)

    async def get_follower_health(self):
        return await dispatch_get_follower_health(self)

    async def get_configured_follower_mode(self):
        return await dispatch_get_configured_follower_mode(self)

    async def restart_follower(self):
        return await dispatch_restart_follower(self)

    # ==================== Detection Model Management API Endpoints ====================

    async def get_models(self, request: Request = None):
        return await dispatch_get_models(self, request)

    async def get_active_model(self):
        return await dispatch_get_active_model(self)

    async def get_model_labels(self, model_id: str, request: Request):
        return await dispatch_get_model_labels(self, model_id, request)

    async def download_model_file(self, model_id: str):
        return await dispatch_download_model_file(self, model_id)

    async def switch_model(self, request: Request):
        return await dispatch_switch_model(self, request)

    async def upload_model(self, request: Request):
        return await dispatch_upload_model(self, request)

    async def delete_model(self, model_id: str):
        return await dispatch_delete_model(self, model_id)

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
                    'automatic_fallback': False,
                    'remaining_tracker_diagnostic_routes': [],
                    'retired_tracker_catalog_config_routes': [
                        '/api/tracker/available',
                        '/api/tracker/current',
                        '/api/tracker/available-types',
                        '/api/tracker/current-config',
                    ],
                    'retired_tracker_diagnostic_routes': [
                        '/api/tracker/current-status',
                        '/api/tracker/output',
                        '/api/tracker/schema',
                        '/api/tracker/capabilities',
                    ],
                    'claim_boundary': (
                        'Legacy compatibility is explicit per registered route; '
                        'retired tracker aliases are not available and are not '
                        'used as automatic fallbacks.'
                    ),
                },
                'timestamp': time.time()
            }
            
            self.logger.debug("Returning schema system information")
            return JSONResponse(content=system_info)
            
        except Exception as e:
            self.logger.error(f"Error in /api/system/schema_info: {e}")
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
        return await dispatch_get_follower_setpoints_with_status(self)

    # ==================== Circuit Breaker API Endpoints ====================

    async def get_circuit_breaker_status(self):
        return await dispatch_get_circuit_breaker_status(self)

    async def toggle_circuit_breaker(self):
        """
        Toggle circuit breaker on/off.

        Returns:
            dict: New circuit breaker status
        """
        return await dispatch_toggle_circuit_breaker(self)

    async def toggle_circuit_breaker_safety_bypass(self):
        """
        Toggle safety bypass flag for circuit breaker test mode.

        When enabled AND circuit breaker is active, altitude and velocity
        safety checks are skipped, allowing ground testing of follower logic.

        Returns:
            dict: New safety bypass status
        """
        return await dispatch_toggle_circuit_breaker_safety_bypass(self)

    async def get_circuit_breaker_statistics(self):
        return await dispatch_get_circuit_breaker_statistics(self)

    async def reset_circuit_breaker_statistics(self):
        """
        Reset circuit breaker statistics and counters.

        Returns:
            dict: Reset operation status
        """
        return await dispatch_reset_circuit_breaker_statistics(self)

    # ==================== OSD Control API Endpoints ====================

    async def get_osd_status(self):
        return await dispatch_get_osd_status(self)

    async def toggle_osd(self):
        return await dispatch_toggle_osd(self)

    async def get_osd_presets(self):
        return await dispatch_get_osd_presets(self)

    async def load_osd_preset(self, preset_name: str):
        return await dispatch_load_osd_preset(self, preset_name)

    # ==================== OSD Color Mode & Mode Management ====================

    async def get_osd_color_modes(self):
        return await dispatch_get_osd_color_modes(self)

    async def set_osd_color_mode(self, mode: str):
        return await dispatch_set_osd_color_mode(self, mode)

    async def get_osd_modes(self):
        return await dispatch_get_osd_modes(self)

    # ==================== GStreamer QGC Output API Endpoints ====================

    async def get_gstreamer_status(self):
        return await dispatch_get_gstreamer_status(self)

    async def toggle_gstreamer(self):
        return await dispatch_toggle_gstreamer(self)

    # ==================== Recording API Endpoints ====================

    async def start_recording(self):
        return await dispatch_start_recording(self)

    async def pause_recording(self):
        return await dispatch_pause_recording(self)

    async def resume_recording(self):
        return await dispatch_resume_recording(self)

    async def stop_recording(self):
        return await dispatch_stop_recording(self)

    async def get_recording_status(self):
        return await dispatch_get_recording_status(self)

    async def toggle_recording(self):
        return await dispatch_toggle_recording(self)

    async def list_recordings(self):
        return await dispatch_list_recordings(self)

    async def download_recording(self, filename: str, request: Request = None):
        return await dispatch_download_recording(self, filename, request)

    async def delete_recording_file(self, filename: str):
        return await dispatch_delete_recording_file(self, filename)

    async def get_storage_status(self):
        return await dispatch_get_storage_status(self)

    async def set_recording_include_osd(self, enabled: str):
        return await dispatch_set_recording_include_osd(self, enabled)

    # ==================== Safety Configuration API Endpoints (v3.5.0+) ====================

    async def get_safety_config(self):
        return await dispatch_get_safety_config(self)

    async def get_follower_safety_limits(self, follower_name: str):
        return await dispatch_get_follower_safety_limits(self, follower_name)

    # Note: get_vehicle_profiles() removed in v4.0.0 (was deprecated in v3.6.0)

    # ==================== Follower Config API Endpoints (v6.1.0+) ====================

    async def get_follower_config_general(self):
        return await dispatch_get_follower_config_general(self)

    async def get_follower_config_effective(self, follower_name: str):
        return await dispatch_get_follower_config_effective(self, follower_name)

    # ==================== Enhanced Safety/Config API Endpoints (v5.0.0+) ====================

    async def get_effective_limits(self, follower_name: str = None):
        return await dispatch_get_effective_limits(self, follower_name)

    async def get_relevant_sections(self, follower_mode: str = None):
        return await dispatch_get_relevant_sections(self, follower_mode)

    async def get_current_follower_mode(self):
        return await dispatch_get_current_follower_mode(self)

    # =========================================================================
    # Configuration Management API Handlers (v4.0.0+)
    # =========================================================================

    def _get_config_service(self) -> ConfigService:
        """Get ConfigService singleton instance."""
        return ConfigService.get_instance()

    async def get_config_schema(self):
        return await dispatch_get_config_schema(self)

    async def get_config_section_schema(self, section: str):
        return await dispatch_get_config_section_schema(self, section)

    async def get_config_sections(self):
        return await dispatch_get_config_sections(self)

    async def get_config_categories(self):
        return await dispatch_get_config_categories(self)

    async def get_current_config(self):
        return await dispatch_get_current_config(self)

    async def get_current_config_section(self, section: str):
        return await dispatch_get_current_config_section(self, section)

    async def get_default_config(self):
        return await dispatch_get_default_config(self)

    async def get_default_config_section(self, section: str):
        return await dispatch_get_default_config_section(self, section)

    async def update_config_parameter(self, section: str, parameter: str, body: ConfigParameterUpdate):
        return await dispatch_update_config_parameter(self, section, parameter, body)

    async def update_config_section(self, section: str, body: ConfigSectionUpdate):
        return await dispatch_update_config_section(self, section, body)

    async def validate_config_value(self, request: Request):
        return await dispatch_validate_config_value(self, request)

    async def get_config_diff(self):
        return await dispatch_get_config_diff(self)

    async def compare_configs(self, request: Request):
        return await dispatch_compare_configs(self, request)

    async def get_defaults_sync(self):
        return await dispatch_get_defaults_sync(self)

    async def plan_defaults_sync(self, body: ConfigSyncPlanRequest):
        return await dispatch_plan_defaults_sync(self, body)

    async def apply_defaults_sync(self, body: ConfigSyncApplyRequest):
        return await dispatch_apply_defaults_sync(self, body)

    async def revert_config_to_default(self):
        return await dispatch_revert_config_to_default(self)

    async def revert_section_to_default(self, section: str):
        return await dispatch_revert_section_to_default(self, section)

    async def revert_parameter_to_default(self, section: str, parameter: str):
        return await dispatch_revert_parameter_to_default(self, section, parameter)

    async def get_config_backup_history(self, request: Request):
        return await dispatch_get_config_backup_history(self, request)

    async def restore_config_backup(self, backup_id: str):
        return await dispatch_restore_config_backup(self, backup_id)

    async def export_config(self, request: Request):
        return await dispatch_export_config(self, request)

    async def import_config(self, body: ConfigImportRequest):
        return await dispatch_import_config(self, body)

    async def search_config_parameters(self, request: Request):
        return await dispatch_search_config_parameters(self, request)

    async def get_config_audit_log(self, request: Request):
        return await dispatch_get_config_audit_log(self, request)

    # ==================== System Management ====================

    async def get_system_status(self):
        """Get current system status for health checks."""
        try:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()
            video_health = self.video_handler.get_connection_health() if self.video_handler else {"status": "unavailable"}

            return JSONResponse(content={
                'success': True,
                'status': 'running',
                'uptime': time.time() - process.create_time(),
                'memory_mb': memory_info.rss / (1024 * 1024),
                'cpu_percent': process.cpu_percent(),
                'pid': process.pid,
                'restart_pending': getattr(self, '_restart_pending', False),
                'video': {
                    'available': bool(self.video_handler and self.video_handler.is_available()),
                    'status': video_health.get('status', 'unknown'),
                    'time_since_last_frame': video_health.get('time_since_last_frame'),
                    'recovery_attempts': video_health.get('recovery_attempts', 0),
                },
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting system status: {e}")
            return JSONResponse(content={
                'success': True,
                'status': 'running',
                'video': {'available': False, 'status': 'unknown'},
                'timestamp': time.time()
            })

    async def get_frontend_config(self):
        """Return frontend configuration for runtime config injection.

        This endpoint provides configuration values that the frontend may need
        at runtime, supporting dynamic host detection and network configuration.
        Includes version and git metadata for dashboard display.
        """
        try:
            # Get git metadata (gracefully fallback if git unavailable)
            git_info = {}
            try:
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

                commit_hash = subprocess.check_output(
                    ['git', 'rev-parse', '--short', 'HEAD'],
                    cwd=project_root,
                    stderr=subprocess.DEVNULL,
                    text=True
                ).strip()

                commit_date = subprocess.check_output(
                    ['git', 'log', '-1', '--format=%cd', '--date=short'],
                    cwd=project_root,
                    stderr=subprocess.DEVNULL,
                    text=True
                ).strip()

                branch = subprocess.check_output(
                    ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                    cwd=project_root,
                    stderr=subprocess.DEVNULL,
                    text=True
                ).strip()

                git_info = {
                    'commit': commit_hash,
                    'date': commit_date,
                    'branch': branch
                }
            except (subprocess.CalledProcessError, FileNotFoundError, Exception):
                # Git not available or not a git repo - provide minimal info
                git_info = {
                    'commit': 'unknown',
                    'date': 'unknown',
                    'branch': 'unknown'
                }

            return JSONResponse(content={
                'success': True,
                'config': {
                    'api_port': Parameters.HTTP_STREAM_PORT,
                    'websocket_port': Parameters.HTTP_STREAM_PORT,
                    'version': PIXEAGLE_VERSION,
                    'api_host': Parameters.HTTP_STREAM_HOST,
                    'git': git_info
                },
                'timestamp': time.time()
            })
        except Exception as e:
            self.logger.error(f"Error getting frontend config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _schedule_backend_restart(
        self,
        *,
        state_lock: Optional[asyncio.Lock] = None,
    ) -> asyncio.Task:
        """Schedule the fixed PixEagle process restart path."""

        # Persist restart intent before the response-flush delay. If an
        # independent shutdown arrives during that window, every process exit
        # path must still ask the supervisor for a replacement backend.
        self.app_controller.requested_process_exit_code = BACKEND_RESTART_EXIT_CODE

        async def initiate_restart():
            try:
                await asyncio.sleep(0.5)
                self.logger.info("Initiating backend process restart sequence")
                self.app_controller.shutdown_flag = True
                try:
                    await asyncio.wait_for(
                        self.app_controller.shutdown(),
                        timeout=BACKEND_RESTART_SHUTDOWN_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    self.logger.error(
                        "Backend restart shutdown exceeded %.1f seconds; forcing process exit",
                        BACKEND_RESTART_SHUTDOWN_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    self.logger.error("Error during restart shutdown: %s", exc)
                if self.server:
                    self.server.should_exit = True
                self.logger.info(
                    "Exiting with PixEagle restart code %d",
                    BACKEND_RESTART_EXIT_CODE,
                )
                os._exit(BACKEND_RESTART_EXIT_CODE)
            finally:
                if state_lock is not None:
                    try:
                        state_lock.release()
                    except RuntimeError:
                        pass

        task = asyncio.create_task(initiate_restart())
        self._restart_task = task
        return task
