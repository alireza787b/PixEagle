"""Typed API v1 request/response contracts for PixEagle."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import status
from pydantic import BaseModel, Field

from classes.runtime_logging import RUNTIME_LOG_CLAIM_BOUNDARY
from classes.tracker_output import TrackerDataType
from classes.tracker_runtime_status import TRACKER_RUNTIME_CLAIM_BOUNDARY


MAVLINK_TELEMETRY_CLAIM_BOUNDARY = (
    "PixEagle local MAVLink2REST client health only; not PX4, SITL, HIL, "
    "field, or follower-response proof."
)
RUNTIME_STATUS_CLAIM_BOUNDARY = (
    "PixEagle process-local runtime and subsystem snapshots only; not PX4, "
    "SITL, HIL, field, or follower-response proof."
)
FOLLOWING_STATUS_CLAIM_BOUNDARY = (
    "PixEagle process-local following state and command-publication health "
    "only; not PX4, SITL, HIL, field, or follower-response proof."
)
FOLLOWING_TELEMETRY_CLAIM_BOUNDARY = (
    "PixEagle process-local follower telemetry and setpoint snapshots only; "
    "not PX4-observed Offboard, SITL, HIL, field, or vehicle-response proof."
)
TRACKING_TELEMETRY_CLAIM_BOUNDARY = (
    "PixEagle process-local tracker telemetry and geometry snapshots only; "
    "not PX4, SITL, HIL, field, follower-response, or vehicle-response proof."
)
TRACKING_CATALOG_CLAIM_BOUNDARY = (
    "PixEagle process-local tracker catalog and configuration metadata only; "
    "not tracker runtime, PX4, SITL, HIL, field, follower-response, or "
    "vehicle-response proof."
)
STREAMING_MEDIA_CLAIM_BOUNDARY = (
    "PixEagle process-local media transport and frame-publisher health only; "
    "not proof that a remote browser, QGC, WebRTC peer, GCS, PX4, SITL, HIL, "
    "or field video path received usable media."
)
SYSTEM_ABOUT_CLAIM_BOUNDARY = (
    "PixEagle process-local version, repository, and runtime metadata only; "
    "not proof of update availability, deployment state, PX4, SITL, HIL, "
    "field, follower-response, or vehicle-response behavior."
)
SYSTEM_UPDATE_STATUS_REASON = (
    "Runtime About does not fetch, pull, restart, or check update availability. "
    "Stop PixEagle and run make update on the host."
)
SYSTEM_UPDATE_SAFE_WORKFLOW = "Stopped-runtime host workflow: make update"
CONFIG_RUNTIME_STATUS_CLAIM_BOUNDARY = (
    "Process-start effective configuration compared with the current persisted "
    "configuration using ConfigService reload tiers; not proof that a supervisor "
    "restarted PixEagle or applied a change."
)
SITL_VALIDATION_STATUS_CLAIM_BOUNDARY = (
    "PixEagle SIH/SITL training metadata and local evidence manifest summary "
    "only. Managed lifecycle availability is not a command execution result; "
    "the separate guarded actions can start or stop only the pinned PX4 SIH "
    "container and do not manage routing or prove PX4 behavior, SITL runtime "
    "success, HIL, field, "
    "real-aircraft, follower-response, or vehicle-response behavior."
)


class APISystemRepositoryMetadata(BaseModel):
    """Public repository identity without reading local remotes."""

    name: str = "PixEagle"
    url: str = "https://github.com/alireza787b/PixEagle"
    docs_url: str = "https://github.com/alireza787b/PixEagle/tree/main/docs"


class APISystemGitMetadata(BaseModel):
    """Local git checkout metadata with unknown-safe fallbacks."""

    available: bool = False
    commit: str = "unknown"
    full_commit: Optional[str] = None
    branch: str = "unknown"
    date: str = "unknown"
    dirty: Optional[bool] = None
    describe: Optional[str] = None


class APISystemBackendStatus(BaseModel):
    """Backend process status safe for authenticated dashboard display."""

    status: Literal["running", "degraded", "unavailable"] = "running"
    restart_pending: bool = False
    pid: Optional[int] = None
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None
    video_available: Optional[bool] = None
    video_status: str = "unknown"


class APISystemRuntimeMetadata(BaseModel):
    """Local runtime metadata without filesystem paths or credential material."""

    uptime_seconds: Optional[float] = None
    started_at: Optional[str] = None
    python_version: str
    run_id: Optional[str] = None


class APISystemUpdateStatus(BaseModel):
    """Read-only boundary pointing to the maintained host update workflow."""

    supported: bool = False
    state: Literal["not_checked", "deferred"] = "not_checked"
    available: Optional[bool] = None
    checked_at: Optional[str] = None
    reason: str = SYSTEM_UPDATE_STATUS_REASON
    safe_workflow: str = SYSTEM_UPDATE_SAFE_WORKFLOW


class APISystemAboutResponse(BaseModel):
    """Typed system/about metadata for operators, dashboard, and agent context."""

    schema_version: int = 1
    source: Literal["pixeagle_system_about"] = "pixeagle_system_about"
    version: str
    repository: APISystemRepositoryMetadata
    git: APISystemGitMetadata
    backend: APISystemBackendStatus
    runtime: APISystemRuntimeMetadata
    update: APISystemUpdateStatus
    claim_boundary: str = SYSTEM_ABOUT_CLAIM_BOUNDARY
    timestamp: float


class SITLValidationCommand(BaseModel):
    """Operator terminal command advertised by the validation training surface."""

    label: str
    command: str
    mode: Literal["dry_run", "probe_only", "execute_px4"]
    starts_processes: bool = False
    writes_artifacts: bool = False
    requires_operator_stack: bool = False
    claim_boundary: str


class SITLValidationPlanSummary(BaseModel):
    """Static summary of the checked-in SIH validation plan."""

    name: str
    title: str
    level: Literal["L2"] = "L2"
    source: str
    hash: str
    scenario_count: int
    required_phase2_scenarios_present: List[str] = Field(default_factory=list)
    required_phase2_scenarios_missing: List[str] = Field(default_factory=list)
    evidence_artifact_count: int
    routing_provider: str = "mavlink-anywhere"
    px4_image: Optional[str] = None
    px4_model: Optional[str] = None


class SITLValidationLatestRun(BaseModel):
    """Latest local SITL evidence manifest summary without absolute paths."""

    available: bool = False
    run_id: Optional[str] = None
    mode: Optional[str] = None
    result: Optional[Literal["pass", "incomplete", "failed"]] = None
    result_reason: Optional[str] = None
    artifact_dir: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: Optional[str] = None
    scenario_execution_enabled: bool = False
    control_actions_allowed: bool = False
    missing_or_placeholder_count: int = 0
    missing_or_placeholder_artifacts: List[str] = Field(default_factory=list)
    missing_or_placeholder_truncated: bool = False
    semantic_failures: List[str] = Field(default_factory=list)
    artifact_content_failures: List[str] = Field(default_factory=list)
    claim_boundary: str = SITL_VALIDATION_STATUS_CLAIM_BOUNDARY


class SITLManagedLifecycleStatus(BaseModel):
    """Read-only readiness and ownership state for the optional SIH lifecycle."""

    feature_enabled: bool = False
    readiness: Literal[
        "disabled",
        "setup_required",
        "ready",
        "running",
        "conflict",
        "unavailable",
    ]
    docker_cli_available: bool = False
    docker_daemon_accessible: bool = False
    docker_server_version: Optional[str] = None
    image_available: bool = False
    container_name: str
    container_state: Literal[
        "unknown",
        "absent",
        "running",
        "stopped",
        "conflict",
    ] = "unknown"
    container_id: Optional[str] = None
    ownership_verified: bool = False
    start_available: bool = False
    stop_available: bool = False
    start_path: str
    stop_path: str
    px4_connected: Optional[bool] = None
    system_address: Optional[str] = None
    control_state_available: bool = False
    control_active: bool = False
    routing_managed_by_dashboard: bool = False
    start_requires_no_real_aircraft_confirmation: bool = True
    stop_requires_no_real_aircraft_confirmation: bool = False
    reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class SITLValidationStatusResponse(BaseModel):
    """Read-only SIH Dev/Training validation status for the dashboard."""

    schema_version: int = 3
    source: Literal["pixeagle_sitl_validation_status"] = (
        "pixeagle_sitl_validation_status"
    )
    profile: Literal["official_px4_sih"] = "official_px4_sih"
    default_artifact_root: str = "reports/sitl"
    injections_enabled: bool = False
    raw_injection_controls_exposed: bool = False
    plan: SITLValidationPlanSummary
    commands: List[SITLValidationCommand] = Field(default_factory=list)
    managed_lifecycle: SITLManagedLifecycleStatus
    latest_run: SITLValidationLatestRun
    claim_boundary: str = SITL_VALIDATION_STATUS_CLAIM_BOUNDARY
    timestamp: float


class APILogSessionManifest(BaseModel):
    """Runtime log session manifest exposed without credential material."""

    schema_version: int = 1
    app: str
    run_id: str
    created_at: str
    pid: int
    cwd: str
    python: str
    component_files: Dict[str, str] = Field(default_factory=dict)
    claim_boundary: str = RUNTIME_LOG_CLAIM_BOUNDARY


class APILogStatusResponse(BaseModel):
    """Runtime log subsystem status for operators and agents."""

    schema_version: int = 1
    enabled: bool
    active_run_id: str
    base_dir: str
    active_session_dir: str
    manifest: Optional[APILogSessionManifest] = None
    claim_boundary: str = RUNTIME_LOG_CLAIM_BOUNDARY


class APILogSessionSummary(BaseModel):
    """Summary of one durable runtime log session."""

    run_id: str
    active: bool = False
    created_at: Optional[str] = None
    size_bytes: int = 0
    modified_at: Optional[str] = None
    components: List[str] = Field(default_factory=list)
    claim_boundary: str = RUNTIME_LOG_CLAIM_BOUNDARY


class APILogSessionsResponse(BaseModel):
    """List of durable runtime log sessions."""

    schema_version: int = 1
    active_run_id: str
    sessions: List[APILogSessionSummary] = Field(default_factory=list)
    claim_boundary: str = RUNTIME_LOG_CLAIM_BOUNDARY


class APILogEntry(BaseModel):
    """One redacted runtime JSONL entry."""

    ts: str
    level: str
    component: str
    logger: str
    run_id: str
    pid: int
    thread: str
    module: Optional[str] = None
    function: Optional[str] = None
    line: Optional[int] = None
    stream: Optional[str] = None
    source: Optional[str] = None
    message: str
    extra: Optional[Dict[str, Any]] = None
    traceback: Optional[str] = None


class APILogSessionEntriesResponse(BaseModel):
    """Filtered runtime JSONL entries for one session/component."""

    schema_version: int = 1
    run_id: str
    component: str
    count: int
    limit: int
    offset: int
    next_offset: int = 0
    tail: bool = False
    matched_total: Optional[int] = None
    has_more: Optional[bool] = None
    level: Optional[str] = None
    since: Optional[str] = None
    entries: List[APILogEntry] = Field(default_factory=list)
    claim_boundary: str = RUNTIME_LOG_CLAIM_BOUNDARY


class APIFrontendErrorReportRequest(BaseModel):
    """Bounded browser-side runtime error report."""

    source: str = Field(default="dashboard", min_length=1, max_length=80)
    level: Literal["INFO", "WARNING", "ERROR", "CRITICAL"] = "ERROR"
    name: Optional[str] = Field(default=None, max_length=160)
    message: str = Field(min_length=1, max_length=2000)
    stack: Optional[str] = Field(default=None, max_length=8000)
    url: Optional[str] = Field(default=None, max_length=2048)
    route: Optional[str] = Field(default=None, max_length=512)
    user_agent: Optional[str] = Field(default=None, max_length=512)
    context: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


class APIFrontendErrorReportResponse(BaseModel):
    """Acknowledgement for a stored browser-side runtime error report."""

    schema_version: int = 1
    accepted: bool = True
    run_id: str
    component: str
    entry_ts: str
    claim_boundary: str = RUNTIME_LOG_CLAIM_BOUNDARY


class APIErrorResponse(BaseModel):
    """Structured API error envelope for typed /api/v1 routes."""

    error: str
    code: str
    detail: Any
    timestamp: int
    path: str
    request_id: str


class APIAuthLoginRequest(BaseModel):
    """Browser/operator login request for session-backed API access."""

    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=4096, repr=False)

    class Config:
        extra = "forbid"


class APIAuthPrincipal(BaseModel):
    """Session principal details returned without credential material."""

    kind: Literal["anonymous", "session"]
    subject: str
    role: Optional[Literal["viewer", "operator", "admin"]] = None
    scopes: List[str] = Field(default_factory=list)
    session_id: Optional[str] = None


class APIAuthSessionResponse(BaseModel):
    """Current browser/operator session state."""

    authenticated: bool
    auth_mode: str
    principal: APIAuthPrincipal
    csrf_required: bool = True
    csrf_header_name: str
    csrf_token: Optional[str] = None
    expires_at: Optional[float] = None


class APIAuthLoginResponse(BaseModel):
    """Successful browser/operator login response."""

    authenticated: bool = True
    auth_mode: str
    principal: APIAuthPrincipal
    csrf_required: bool = True
    csrf_header_name: str
    csrf_token: str
    expires_at: float


class APIAuthLogoutResponse(BaseModel):
    """Browser/operator logout result."""

    authenticated: bool = False
    revoked: bool
    auth_mode: str


class APIAuthUserSummary(BaseModel):
    """Credential-free browser-user metadata."""

    username: str
    role: Literal["viewer", "operator", "admin"]
    enabled: bool


class APIAuthUsersResponse(BaseModel):
    """Admin-only browser-user inventory without password hashes."""

    users: List[APIAuthUserSummary] = Field(default_factory=list)


class APIAuthUserCreateRequest(BaseModel):
    """Create one external browser-session user."""

    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=4096, repr=False)
    role: Literal["viewer", "operator", "admin"] = "operator"
    enabled: bool = True

    class Config:
        extra = "forbid"


class APIAuthUserUpdateRequest(BaseModel):
    """Update selected fields for one external browser-session user."""

    role: Optional[Literal["viewer", "operator", "admin"]] = None
    enabled: Optional[bool] = None
    password: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=4096,
        repr=False,
    )

    class Config:
        extra = "forbid"


class APIAuthUserMutationResponse(BaseModel):
    """Safe result for a browser-user create or update mutation."""

    user: APIAuthUserSummary
    sessions_revoked: int = Field(default=0, ge=0)


class APIAuthUserDeleteRequest(BaseModel):
    """Explicit username confirmation for destructive account deletion."""

    confirm_username: str = Field(min_length=1, max_length=120)

    class Config:
        extra = "forbid"


class APIAuthUserDeleteResponse(BaseModel):
    """Safe result for a committed browser-user deletion."""

    deleted: bool = True
    username: str
    sessions_revoked: int = Field(default=0, ge=0)


class APIAuthPasswordChangeRequest(BaseModel):
    """Current and replacement passwords for a session-owned change."""

    current_password: str = Field(min_length=1, max_length=4096, repr=False)
    new_password: str = Field(min_length=1, max_length=4096, repr=False)

    class Config:
        extra = "forbid"


class APIAuthPasswordChangeResponse(BaseModel):
    """Replacement browser session issued after a password change."""

    authenticated: bool = True
    auth_mode: str
    principal: APIAuthPrincipal
    csrf_required: bool = True
    csrf_header_name: str
    csrf_token: str
    expires_at: float
    sessions_revoked: int = Field(ge=1)


class APIConfigRuntimePendingChange(BaseModel):
    """One redacted persisted change that requires a process restart."""

    path: str
    section: str
    parameter: str
    change_type: Literal["added", "removed", "changed"]
    reload_tier: Literal["system_restart"] = "system_restart"
    sensitive: bool = False
    startup_value: Any = None
    persisted_value: Any = None


class APIConfigRestartActionStatus(BaseModel):
    """Current request principal/runtime eligibility for process restart."""

    path: str
    available: bool
    reason: str
    requires_confirmation: bool = True
    requires_idempotency_key: bool = True


class APIConfigRuntimeStatusResponse(BaseModel):
    """Typed pending-restart status derived from the immutable startup config."""

    schema_version: int = 1
    source: Literal["config_service"] = "config_service"
    startup_config_source: Literal["runtime_config", "checked_in_defaults"]
    persisted_config_source: Literal["runtime_config", "checked_in_defaults"]
    persisted_config_digest: str
    startup_snapshot_timestamp: float
    startup_snapshot_immutable: bool = True
    system_restart_policy: Literal["local_only", "lab_admin_browser"]
    restart_required: bool
    pending_change_count: int
    pending_changes: List[APIConfigRuntimePendingChange] = Field(default_factory=list)
    restart_action: APIConfigRestartActionStatus
    claim_boundary: str = CONFIG_RUNTIME_STATUS_CLAIM_BOUNDARY
    timestamp: float


class APIActionRequest(BaseModel):
    """Typed request envelope for operator or validation control actions."""

    source: str = Field(default="operator", min_length=1, max_length=120)
    reason: str = Field(default="operator_request", min_length=1, max_length=240)
    dry_run: bool = False
    confirm: bool = False
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=160)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


class SITLManagedLifecycleRequest(APIActionRequest):
    """Explicit acknowledgement required for a managed SIH process mutation."""

    no_real_aircraft_confirmed: bool = False


class APICircuitBreakerSetRequest(APIActionRequest):
    """Explicit durable circuit-breaker state mutation."""

    enabled: bool


class APITrackingBoundingBox(BaseModel):
    """Bounding box for typed manual tracking-start actions.

    Coordinate units are explicit. Existing clients that omit the field are
    interpreted as normalized; pixel clients must declare ``pixels``.
    """

    coordinate_space: Literal["normalized", "pixels"] = "normalized"
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    width: float = Field(allow_inf_nan=False)
    height: float = Field(allow_inf_nan=False)

    class Config:
        extra = "forbid"


class APITrackingStartRequest(APIActionRequest):
    """Typed manual tracking-start action request."""

    bbox: APITrackingBoundingBox


class APITrackingClickPosition(BaseModel):
    """Click position for typed smart-tracker selection actions.

    Coordinate units are explicit. Existing clients that omit the field are
    interpreted as normalized; pixel clients must declare ``pixels``.
    """

    coordinate_space: Literal["normalized", "pixels"] = "normalized"
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)

    class Config:
        extra = "forbid"


class APITrackingSmartClickRequest(APIActionRequest):
    """Typed smart-tracker click-selection action request."""

    click: APITrackingClickPosition


class APITrackerSwitchRequest(APIActionRequest):
    """Typed tracker-selection action request."""

    tracker_type: str = Field(min_length=1, max_length=120)

    class Config:
        extra = "forbid"


class APIActionAuditEvent(BaseModel):
    """Audit event embedded in typed action resources."""

    event_id: str
    event_type: str
    timestamp: float
    source: str
    reason: str


class APIActionResponse(BaseModel):
    """Tracked action resource for typed /api/v1 control mutations."""

    action_id: str
    action_type: Literal[
        "circuit_breaker_set",
        "offboard_start",
        "offboard_stop",
        "operator_abort",
        "segmentation_toggle",
        "smart_click",
        "smart_mode_toggle",
        "managed_sih_start",
        "managed_sih_stop",
        "system_restart",
        "tracker_restart",
        "tracker_switch",
        "tracking_redetect",
        "tracking_start",
        "tracking_stop",
    ]
    status: Literal["validated", "success", "failure"]
    accepted: bool
    executed: bool
    dry_run: bool
    confirmed: bool
    idempotency_key: Optional[str] = None
    idempotent_replay: bool = False
    source: str
    reason: str
    following_active_before: Optional[bool] = None
    following_active_after: Optional[bool] = None
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    claim_boundary: str
    audit_event: APIActionAuditEvent
    timestamp: float


class APITelemetryTransportHealth(BaseModel):
    """MAVLink2REST request/transport health for typed API consumers."""

    state: Optional[str] = None
    latest_request_ok: bool = False
    latest_request_result: Literal["not_attempted", "success", "failure"] = (
        "not_attempted"
    )
    latest_request_age_s: Optional[float] = None
    last_error: Optional[str] = None
    error_count: int = 0
    validation_timeout_active: bool = False
    request_timeout_s: Optional[float] = None
    request_retries: Optional[int] = None
    endpoint: Optional[str] = None


class APITelemetryRequestFreshness(BaseModel):
    """Freshness of the last successful MAVLink2REST sample."""

    fresh: bool = False
    last_success_age_s: Optional[float] = None
    stale_timeout_s: Optional[float] = None
    last_success_monotonic_available: bool = False


class APITelemetryPayloadHealth(BaseModel):
    """Availability of parsed telemetry payload cached by PixEagle."""

    has_payload: bool = False
    sample_count: int = 0
    available_keys: List[str] = Field(default_factory=list)
    flight_mode: Optional[Any] = None
    arm_status: Optional[Any] = None
    fresh: bool = False
    payload_age_s: Optional[float] = None


class APITelemetryHealthResponse(BaseModel):
    """Typed MAVLink telemetry health for API/MCP/dashboard consumers."""

    schema_version: int = 1
    source: Literal["mavlink2rest"] = "mavlink2rest"
    enabled: bool
    status: Literal[
        "disabled",
        "healthy",
        "degraded",
        "stale",
        "error",
        "connecting",
        "disconnected",
    ]
    consumer_guidance: Literal[
        "disabled",
        "usable",
        "degraded_latest_request_failed",
        "stale",
        "unavailable",
        "connecting",
    ]
    transport: APITelemetryTransportHealth
    request_freshness: APITelemetryRequestFreshness
    payload: APITelemetryPayloadHealth
    claim_boundary: str = MAVLINK_TELEMETRY_CLAIM_BOUNDARY
    timestamp: float


class APIStreamingTransportHealth(BaseModel):
    """Process-local health for one PixEagle media transport."""

    name: Literal[
        "http_mjpeg",
        "websocket_jpeg",
        "webrtc_signaling",
        "gstreamer_udp_h264",
    ]
    enabled: bool = True
    status: Literal["disabled", "idle", "active", "saturated", "unavailable"]
    endpoint: Optional[str] = None
    route_registered: bool = True
    active_connections: int = 0
    max_connections: Optional[int] = None
    cleanup_pending: bool = False
    last_error: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class APIStreamingFrameHealth(BaseModel):
    """Frame-publisher freshness and stream output counters."""

    source_available: bool = False
    preferred_source: Literal["osd", "raw"]
    latest_frame_id: Optional[int] = None
    latest_frame_age_s: Optional[float] = None
    latest_frame_stale: bool = False
    stale_timeout_s: float
    latest_frame_is_osd: Optional[bool] = None
    publisher_client_count: int = 0
    frames_sent: int = 0
    frames_dropped: int = 0
    drop_ratio: float = 0.0
    total_bandwidth_mb: float = 0.0
    cache_size: int = 0


class APIStreamingSecurityBoundary(BaseModel):
    """Media route exposure/auth posture without exposing credential material."""

    exposure_mode: Optional[str] = None
    bind_host: Optional[str] = None
    auth_mode: Optional[str] = None
    required_scope: str = "media:read"
    websocket_origin_check: bool = True
    query_string_tokens_allowed: bool = False


class APIStreamingConfigSummary(BaseModel):
    """Runtime streaming config values relevant to clients and diagnostics."""

    streaming_enabled: bool = True
    stream_fps: int
    stream_width: int
    stream_height: int
    stream_quality: int
    processed_osd: bool
    adaptive_quality_enabled: bool
    default_protocol: str
    pipeline_mode: str


class APIStreamingClientTransports(BaseModel):
    """Browser transports available in this running backend process."""

    webrtc: bool = True
    websocket: bool = True
    http_mjpeg: bool = True


class APIStreamingClientIceServer(BaseModel):
    """ICE server record consumed by an authorized browser peer."""

    urls: str
    username: Optional[str] = None
    credential: Optional[str] = None


class APIStreamingClientConfigResponse(BaseModel):
    """Runtime browser media configuration from the backend source of truth."""

    schema_version: int = 1
    source: Literal["streaming_client_config"] = "streaming_client_config"
    streaming_enabled: bool = True
    default_protocol: Literal["auto", "webrtc", "websocket", "http"] = "auto"
    target_fps: int = Field(ge=1, le=60)
    transports: APIStreamingClientTransports
    ice_servers: List[APIStreamingClientIceServer] = Field(default_factory=list)
    claim_boundary: str = STREAMING_MEDIA_CLAIM_BOUNDARY
    timestamp: float


class APIStreamingMediaHealthResponse(BaseModel):
    """Typed media transport health for API/MCP/dashboard consumers."""

    schema_version: int = 1
    source: Literal["streaming_media"] = "streaming_media"
    status: Literal["idle", "active", "degraded", "unavailable"]
    consumer_guidance: Literal[
        "idle",
        "serving_media",
        "operator_attention",
        "unavailable",
    ]
    transports: List[APIStreamingTransportHealth] = Field(default_factory=list)
    frames: APIStreamingFrameHealth
    security: APIStreamingSecurityBoundary
    config: APIStreamingConfigSummary
    quality_engine: Dict[str, Any] = Field(default_factory=dict)
    health_issues: List[str] = Field(default_factory=list)
    claim_boundary: str = STREAMING_MEDIA_CLAIM_BOUNDARY
    timestamp: float


class APIRuntimeModesStatus(BaseModel):
    """Current PixEagle operator-mode flags."""

    smart_mode_active: bool = False
    tracking_started: bool = False
    segmentation_active: bool = False
    following_active: bool = False


class APIRuntimeSubsystemStatus(BaseModel):
    """Local subsystem snapshots exposed without expanding flight claims."""

    video_status: str = "unknown"
    offboard_commander: Optional[Dict[str, Any]] = None
    offboard_commander_failure: Optional[Any] = None
    px4_connection: Optional[Dict[str, Any]] = None
    mavlink_telemetry: Optional[Dict[str, Any]] = None
    smart_tracker_runtime: Optional[Dict[str, Any]] = None


class APIRuntimeStatusResponse(BaseModel):
    """Typed PixEagle runtime status for API/MCP/dashboard consumers."""

    schema_version: int = 1
    source: Literal["pixeagle_runtime"] = "pixeagle_runtime"
    status: Literal["idle", "active", "degraded", "unavailable"]
    consumer_guidance: Literal[
        "idle",
        "vision_active",
        "following_active",
        "operator_attention",
        "unavailable",
    ]
    modes: APIRuntimeModesStatus
    subsystems: APIRuntimeSubsystemStatus
    reason: Optional[str] = None
    claim_boundary: str = RUNTIME_STATUS_CLAIM_BOUNDARY
    timestamp: float


class APIFollowingProfileStatus(BaseModel):
    """Follower profile identity without exposing legacy telemetry internals."""

    configured_mode: Optional[str] = None
    current_mode: Optional[str] = None
    profile_valid: bool = False
    display_name: Optional[str] = None
    control_type: Optional[str] = None
    available_fields: List[str] = Field(default_factory=list)
    manager_type: Optional[str] = None
    follower_type: Optional[str] = None
    follower_instance_present: bool = False


class APICommandPreviewReadiness(BaseModel):
    """Explicit tracker-to-intent preview state; never a PX4 authorization."""

    execution_mode: Literal["PX4", "COMMAND_PREVIEW"] = "PX4"
    configured: bool = False
    ready: bool = False
    usable_for_command_preview: bool = False
    autonomous_following_authorized: bool = False
    commands_sent_to_px4: bool = False
    tracker_requires_video: bool = True
    operational_limits_enforced: bool = False
    target_freshness_required: bool = True
    finite_validation_required: bool = True
    warnings: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    circuit_breaker: Optional[Dict[str, Any]] = None
    video_frame_status: Dict[str, Any] = Field(default_factory=dict)


class APIFollowingCommandPublicationStatus(BaseModel):
    """Process-local command publication state for following consumers."""

    source: Literal["offboard_commander", "command_preview"] = "offboard_commander"
    execution_mode: Literal["PX4", "COMMAND_PREVIEW"] = "PX4"
    exists: bool = False
    running: Optional[bool] = None
    task_active: Optional[bool] = None
    health_state: Optional[str] = None
    command_publication_source: Optional[str] = None
    sends_mavsdk_commands: Optional[bool] = None
    commands_sent_to_px4: bool = False
    last_intent_fresh: Optional[bool] = None
    failsafe_defaults_active: Optional[bool] = None
    successful_publishes: Optional[int] = None
    failed_publishes: Optional[int] = None
    consecutive_failures: Optional[int] = None
    local_successful_publish_observed: bool = False
    offboard_commander: Optional[Dict[str, Any]] = None


class APIFollowingStatusResponse(BaseModel):
    """Typed following status for API/MCP/dashboard consumers."""

    schema_version: int = 1
    source: Literal["following_runtime"] = "following_runtime"
    status: Literal["inactive", "active", "degraded", "unavailable"]
    consumer_guidance: Literal[
        "inactive",
        "following_active",
        "operator_attention",
        "unavailable",
    ]
    following_active: bool
    execution_mode: Literal["PX4", "COMMAND_PREVIEW"] = "PX4"
    commands_sent_to_px4: bool = False
    profile: APIFollowingProfileStatus
    command_preview: APICommandPreviewReadiness = Field(
        default_factory=APICommandPreviewReadiness
    )
    command_publication: APIFollowingCommandPublicationStatus
    health_issues: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    claim_boundary: str = FOLLOWING_STATUS_CLAIM_BOUNDARY
    timestamp: float


class APIFollowingTelemetryResponse(BaseModel):
    """Typed follower telemetry/setpoint snapshot for API/MCP/dashboard consumers."""

    schema_version: int = 1
    source: Literal["following_telemetry"] = "following_telemetry"
    status: Literal["inactive", "active", "degraded", "unavailable"]
    consumer_guidance: Literal[
        "inactive",
        "following_active",
        "operator_attention",
        "unavailable",
    ]
    following_active: bool
    execution_mode: Literal["PX4", "COMMAND_PREVIEW"] = "PX4"
    commands_sent_to_px4: bool = False
    profile: APIFollowingProfileStatus
    command_preview: APICommandPreviewReadiness = Field(
        default_factory=APICommandPreviewReadiness
    )
    fields: Dict[str, Any] = Field(default_factory=dict)
    field_source: Literal[
        "active_follower",
        "legacy_telemetry",
        "schema_profile",
        "unavailable",
    ] = "unavailable"
    last_command_intent: Optional[Dict[str, Any]] = None
    target_loss_handler: Optional[Dict[str, Any]] = None
    safety_systems: Optional[Dict[str, Any]] = None
    performance: Optional[Dict[str, Any]] = None
    circuit_breaker: Optional[Dict[str, Any]] = None
    circuit_breaker_active: Optional[bool] = None
    command_publication: APIFollowingCommandPublicationStatus
    flight_mode: Optional[Any] = None
    flight_mode_text: Optional[str] = None
    is_offboard: Optional[bool] = None
    telemetry_enabled: bool = True
    legacy_payload_keys: List[str] = Field(default_factory=list)
    health_issues: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    claim_boundary: str = FOLLOWING_TELEMETRY_CLAIM_BOUNDARY
    timestamp: float


class APITrackingFollowingReadiness(BaseModel):
    """Canonical autonomous-following readiness derived from tracker and frame state."""

    usable_for_following: bool
    reason: Optional[str] = None
    tracker_requires_video: bool = True
    video_frame_status: Dict[str, Any] = Field(default_factory=dict)


class APITrackingRuntimeStatusResponse(BaseModel):
    """Typed tracker runtime status for API/MCP/dashboard consumers."""

    schema_version: int = 1
    source: Literal["tracker_runtime"] = "tracker_runtime"
    status: Literal[
        "no_output",
        "visible_output",
        "active_usable",
        "not_usable",
        "stale_output",
        "unavailable",
    ]
    consumer_guidance: Literal[
        "no_output",
        "diagnostic_only",
        "usable",
        "not_usable",
        "stale",
        "unavailable",
    ]
    has_output: bool
    active_tracking: bool
    usable_for_following: bool
    data_is_stale: bool
    reason: Optional[str] = None
    configured_tracker: Optional[str] = None
    active_tracker: Optional[str] = None
    tracker_id: Optional[str] = None
    tracker_type: Optional[str] = None
    data_type: Optional[str] = None
    provider: Optional[str] = None
    protocol: Optional[str] = None
    connection_status: Optional[str] = None
    tracking_status: Optional[str] = None
    target_count: int = 0
    selected_target_id: Optional[Any] = None
    output_fields: List[str] = Field(default_factory=list)
    smart_mode_active: bool = False
    following_active: bool = False
    following_readiness: APITrackingFollowingReadiness = Field(
        default_factory=lambda: APITrackingFollowingReadiness(
            usable_for_following=False,
            reason="Following readiness was not evaluated for this embedded snapshot",
        )
    )
    claim_boundary: str = TRACKER_RUNTIME_CLAIM_BOUNDARY
    timestamp: float


class APITrackingCatalogEntry(BaseModel):
    """One tracker catalog entry exposed by the typed tracker catalog route."""

    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    request_tracker_type: Optional[str] = None
    factory_key: Optional[str] = None
    data_type: Optional[str] = None
    smart_mode: bool = False
    available: bool = True
    unavailable_reason: Optional[str] = None
    source: Literal["schema_manager", "builtin_compatibility"]
    supported_schemas: List[str] = Field(default_factory=list)
    capabilities: List[Any] = Field(default_factory=list)
    performance: Dict[str, Any] = Field(default_factory=dict)
    suitable_for: List[str] = Field(default_factory=list)
    icon: Optional[str] = None
    performance_category: Optional[str] = None


class APITrackingCatalogResponse(BaseModel):
    """Typed tracker catalog/configuration metadata for dashboard/API consumers."""

    schema_version: int = 1
    source: Literal["tracking_catalog"] = "tracking_catalog"
    status: Literal["available", "degraded", "unavailable"]
    consumer_guidance: Literal[
        "selectable",
        "operator_attention",
        "schema_manager_unavailable",
    ]
    configured_tracker: Optional[str] = None
    active_tracker: Optional[str] = None
    smart_mode_active: bool = False
    tracking_started: bool = False
    tracking_active: bool = False
    ui_trackers: List[APITrackingCatalogEntry] = Field(default_factory=list)
    tracker_types: Dict[str, APITrackingCatalogEntry] = Field(default_factory=dict)
    data_type_schemas: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    total_trackers: int = 0
    runtime_status: APITrackingRuntimeStatusResponse
    health_issues: List[str] = Field(default_factory=list)
    claim_boundary: str = TRACKING_CATALOG_CLAIM_BOUNDARY
    timestamp: float


class APITrackingTelemetryResponse(BaseModel):
    """Typed tracker telemetry/geometry snapshot for dashboard/API/MCP consumers."""

    schema_version: int = 1
    source: Literal["tracking_telemetry"] = "tracking_telemetry"
    status: Literal[
        "no_output",
        "visible_output",
        "active_usable",
        "not_usable",
        "stale_output",
        "unavailable",
    ]
    consumer_guidance: Literal[
        "no_output",
        "diagnostic_only",
        "usable",
        "not_usable",
        "stale",
        "unavailable",
    ]
    has_output: bool
    active_tracking: bool
    tracking_active: bool = False
    tracker_started: bool = False
    usable_for_following: bool
    data_is_stale: bool
    center: Optional[List[float]] = None
    bounding_box: Optional[List[float]] = None
    fields: Dict[str, Any] = Field(default_factory=dict)
    tracker_data: Dict[str, Any] = Field(default_factory=dict)
    field_source: Literal[
        "tracker_output",
        "legacy_telemetry",
        "unavailable",
    ] = "unavailable"
    runtime_status: APITrackingRuntimeStatusResponse
    legacy_payload_keys: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    claim_boundary: str = TRACKING_TELEMETRY_CLAIM_BOUNDARY
    timestamp: float
    observed_at: float


ACTION_ERROR_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {
        "model": APIErrorResponse,
        "description": "The action is outside its configured transport or principal policy.",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": APIErrorResponse,
        "description": "Action resource was not found.",
    },
    status.HTTP_409_CONFLICT: {
        "model": APIErrorResponse,
        "description": "Action confirmation or state requirements were not met.",
    },
    status.HTTP_422_UNPROCESSABLE_ENTITY: {
        "model": APIErrorResponse,
        "description": "Invalid typed action request.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": APIErrorResponse,
        "description": "A required state barrier, backup, or durable audit is unavailable.",
    },
}
ACTION_ROUTE_RESPONSES = {
    status.HTTP_200_OK: {
        "model": APIActionResponse,
        "description": "Dry-run validation result or idempotent action replay.",
    },
    **ACTION_ERROR_RESPONSES,
}
AUTH_ROUTE_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": APIErrorResponse,
        "description": "Invalid credentials or missing session authentication.",
    },
    status.HTTP_403_FORBIDDEN: {
        "model": APIErrorResponse,
        "description": "Required scope, browser session, or CSRF proof was missing.",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": APIErrorResponse,
        "description": "The requested browser-session user was not found.",
    },
    status.HTTP_409_CONFLICT: {
        "model": APIErrorResponse,
        "description": (
            "The account mutation conflicted with current state, confirmation, "
            "or final enabled-user/admin invariants."
        ),
    },
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "model": APIErrorResponse,
        "description": (
            "Browser credential-attempt throttling or bounded password-hash "
            "capacity is active."
        ),
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": APIErrorResponse,
        "description": "Browser session authentication is not configured.",
    },
}
RUNTIME_STATUS_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "PixEagle runtime status could not be evaluated.",
    },
}
CONFIG_RUNTIME_STATUS_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "Persisted configuration restart status could not be evaluated.",
    },
}
SYSTEM_ABOUT_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "PixEagle system/about metadata could not be evaluated.",
    },
}
FOLLOWING_STATUS_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "Following status could not be evaluated.",
    },
}
FOLLOWING_TELEMETRY_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "Following telemetry could not be evaluated.",
    },
}
TELEMETRY_HEALTH_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "Telemetry health could not be evaluated.",
    },
}
STREAMING_MEDIA_HEALTH_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "Streaming media health could not be evaluated.",
    },
}
STREAMING_CLIENT_CONFIG_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "Streaming browser client configuration could not be evaluated.",
    },
}
TRACKING_RUNTIME_STATUS_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "Tracker runtime status could not be evaluated.",
    },
}
TRACKING_CATALOG_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "Tracker catalog could not be evaluated.",
    },
}
TRACKING_TELEMETRY_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "Tracker telemetry could not be evaluated.",
    },
}
LOGS_ERROR_RESPONSES = {
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "model": APIErrorResponse,
        "description": "Runtime log reporting rate limit was exceeded.",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": APIErrorResponse,
        "description": "Runtime log session or component was not found.",
    },
    status.HTTP_422_UNPROCESSABLE_ENTITY: {
        "model": APIErrorResponse,
        "description": "Runtime log query parameters were invalid.",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "Runtime logs could not be evaluated.",
    },
}
LOGS_EXPORT_RESPONSES = {
    status.HTTP_200_OK: {
        "description": "Sanitized runtime log evidence bundle.",
        "content": {
            "application/gzip": {
                "schema": {
                    "type": "string",
                    "format": "binary",
                }
            }
        },
        "headers": {
            "X-PixEagle-Run-ID": {
                "schema": {"type": "string"},
                "description": "Runtime log session ID contained in the export.",
            },
            "X-PixEagle-Log-Export-Sha256": {
                "schema": {"type": "string"},
                "description": "SHA-256 digest of the generated tar.gz bundle.",
            },
            "X-PixEagle-Log-Export-Size": {
                "schema": {"type": "integer"},
                "description": "Generated bundle size in bytes.",
            },
            "X-PixEagle-Claim-Boundary": {
                "schema": {"type": "string"},
                "description": "Runtime evidence claim boundary for this bundle.",
            },
        },
    },
    **LOGS_ERROR_RESPONSES,
}


class SITLTrackerOutputInjection(BaseModel):
    """Validation-only tracker output stimulus for PX4/SITL scenarios."""

    injection_id: str = "sitl_tracker_output"
    source: str = "sitl_validation"
    dry_run: bool = False
    data_type: str = TrackerDataType.POSITION_2D.value
    timestamp: Optional[float] = None
    tracking_active: bool = True
    tracker_id: str = "sitl_validation"
    position_2d: Optional[Tuple[float, float]] = None
    position_3d: Optional[Tuple[float, float, float]] = None
    angular: Optional[Tuple[float, ...]] = None
    bbox: Optional[Tuple[int, int, int, int]] = None
    normalized_bbox: Optional[Tuple[float, float, float, float]] = None
    confidence: Optional[float] = None
    velocity: Optional[Tuple[float, float]] = None
    acceleration: Optional[Tuple[float, float]] = None
    target_id: Optional[int] = None
    targets: Optional[List[Dict[str, Any]]] = None
    quality_metrics: Dict[str, float] = Field(default_factory=dict)
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    usable_for_following: Optional[bool] = None
    data_is_stale: Optional[bool] = None
    freshness_reason: Optional[str] = None
    has_output: Optional[bool] = None

    class Config:
        extra = "forbid"


class SITLTrackerInjectionSummary(BaseModel):
    source: str
    tracker_id: str
    data_type: str
    input_tracking_active: bool
    processed_tracking_active: Optional[bool] = None
    processed_usable_for_following: Optional[bool] = None
    processed_data_is_stale: Optional[bool] = None
    freshness_reason: Optional[str] = None
    has_output: Optional[bool] = None


class SITLCommandIntentSummary(BaseModel):
    profile_name: str
    control_type: str
    fields: Dict[str, float]
    source: str
    reason: Optional[str] = None
    created_at_monotonic_s: float
    created_at_utc: str


class SITLOffboardCommanderSummary(BaseModel):
    exists: bool
    running: Optional[bool] = None
    health_state: Optional[str] = None
    command_publication_source: Optional[str] = None
    command_failure_threshold: Optional[int] = None
    publish_count: Optional[int] = None
    last_intent_fresh: Optional[bool] = None
    failsafe_defaults_active: Optional[bool] = None
    successful_publishes: Optional[int] = None
    failed_publishes: Optional[int] = None
    consecutive_failures: Optional[int] = None
    rejected_intents: Optional[int] = None
    last_publish_success: Optional[bool] = None
    last_publish_reason: Optional[str] = None
    last_error: Optional[str] = None
    failure_policy_triggered: Optional[bool] = None
    failure_policy_reason: Optional[str] = None
    failure_policy_trigger_count: Optional[int] = None
    failure_action: Optional[str] = None


class SITLTrackerInjectionResponse(BaseModel):
    """Response from a validation-only tracker output injection."""

    status: str
    accepted: bool
    reason: Optional[str] = None
    following_active: bool
    injection: SITLTrackerInjectionSummary
    command_intent: Optional[SITLCommandIntentSummary] = None
    offboard_commander: Optional[SITLOffboardCommanderSummary] = None
    timestamp: float


class SITLVideoStallInjection(BaseModel):
    """Validation-only video/frame stall stimulus for PX4/SITL scenarios."""

    injection_id: str = "sitl_video_stall"
    source: str = "sitl_validation"
    dry_run: bool = False
    frame_source: str = "sitl_validation"
    frame_status: str = "unavailable"
    usable_for_following: bool = False
    reason: str = "sitl_video_stall"
    timestamp: Optional[float] = None
    consecutive_failures: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


class SITLFrameStatusSummary(BaseModel):
    """Stable frame-status evidence returned by video-stall validation routes."""

    source: str
    status: str
    usable_for_following: bool
    reason: str
    timestamp: float
    sitl_injection: bool = True
    sitl_injection_id: Optional[str] = None
    consecutive_failures: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class SITLVideoStallSummary(BaseModel):
    source: str
    tracker_requires_video: bool
    frame_status: SITLFrameStatusSummary


class SITLVideoStallResponse(BaseModel):
    """Response from a validation-only video stall injection."""

    status: str
    accepted: bool
    reason: Optional[str] = None
    following_active: bool
    injection: SITLVideoStallSummary
    command_intent: Optional[SITLCommandIntentSummary] = None
    offboard_commander: Optional[SITLOffboardCommanderSummary] = None
    timestamp: float


class SITLCommanderPublishFailureInjection(BaseModel):
    """Validation-only OffboardCommander publish-failure stimulus."""

    injection_id: str = "sitl_commander_publish_failure"
    source: str = "sitl_validation"
    dry_run: bool = False
    failure_mode: Literal["recorded_failure"] = "recorded_failure"
    failure_count: Optional[int] = Field(default=None, ge=1, le=100)
    reason: str = "sitl_commander_publish_failure"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


class SITLCommanderPublishFailureSummary(BaseModel):
    source: str
    failure_mode: Literal["recorded_failure"] = "recorded_failure"
    requested_failure_count: Optional[int] = None
    applied_failure_count: int
    failure_reason: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SITLCommanderPublishFailureResponse(BaseModel):
    """Response from a validation-only commander publish-failure injection."""

    status: str
    accepted: bool
    reason: Optional[str] = None
    following_active: bool
    injection: SITLCommanderPublishFailureSummary
    offboard_commander: Optional[SITLOffboardCommanderSummary] = None
    offboard_commander_before: Optional[SITLOffboardCommanderSummary] = None
    offboard_commander_after: Optional[SITLOffboardCommanderSummary] = None
    offboard_commander_failure: Optional[Dict[str, Any]] = None
    disconnect_result: Optional[Dict[str, Any]] = None
    timestamp: float


class SITLMavsdkDisconnectInjection(BaseModel):
    """Validation-only PixEagle-local MAVSDK command-path disconnect stimulus."""

    injection_id: str = "sitl_mavsdk_disconnect"
    source: str = "sitl_validation"
    dry_run: bool = False
    failure_mode: Literal[
        "local_mavsdk_command_disconnect"
    ] = "local_mavsdk_command_disconnect"
    failure_count: Optional[int] = Field(default=None, ge=1, le=100)
    reason: str = "sitl_mavsdk_disconnect"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


class SITLPX4ConnectionSummary(BaseModel):
    status: Optional[str] = None
    connected: Optional[bool] = None
    active_mode: Optional[bool] = None
    validation_disconnect_active: Optional[bool] = None
    disconnect_reason: Optional[str] = None
    disconnect_source: Optional[str] = None
    disconnect_age_s: Optional[float] = None
    disconnect_count: Optional[int] = None
    last_error: Optional[str] = None
    system_address: Optional[str] = None
    uses_mavlink2rest: Optional[bool] = None


class SITLMavsdkDisconnectSummary(BaseModel):
    source: str
    failure_mode: Literal[
        "local_mavsdk_command_disconnect"
    ] = "local_mavsdk_command_disconnect"
    requested_failure_count: Optional[int] = None
    applied_failure_count: int
    failure_reason: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SITLDisconnectResultSummary(BaseModel):
    steps: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class SITLMavsdkDisconnectResponse(BaseModel):
    """Response from a validation-only local MAVSDK command-path disconnect."""

    status: str
    accepted: bool
    reason: Optional[str] = None
    following_active: bool
    injection: SITLMavsdkDisconnectSummary
    px4_connection_before: Optional[SITLPX4ConnectionSummary] = None
    px4_connection_after: Optional[SITLPX4ConnectionSummary] = None
    offboard_commander: Optional[SITLOffboardCommanderSummary] = None
    offboard_commander_before: Optional[SITLOffboardCommanderSummary] = None
    offboard_commander_after: Optional[SITLOffboardCommanderSummary] = None
    offboard_commander_failure: Optional[Dict[str, Any]] = None
    disconnect_result: Optional[SITLDisconnectResultSummary] = None
    timestamp: float


class SITLMavlinkTelemetrySummary(BaseModel):
    enabled: Optional[bool] = None
    status: Optional[str] = None
    connection_state: Optional[str] = None
    fresh: Optional[bool] = None
    last_success_age_s: Optional[float] = None
    stale_timeout_s: Optional[float] = None
    request_timeout_s: Optional[float] = None
    request_retries: Optional[int] = None
    connection_error_count: Optional[int] = None
    last_error: Optional[str] = None
    endpoint: Optional[str] = None
    validation_timeout_active: Optional[bool] = None


class SITLMavlink2RestTimeoutInjection(BaseModel):
    """Validation-only MAVLink2REST client timeout stimulus."""

    injection_id: str = "sitl_mavlink2rest_timeout"
    source: str = "sitl_validation"
    dry_run: bool = False
    failure_count: int = Field(default=1, ge=1, le=100)
    reason: str = "sitl_mavlink2rest_timeout"
    force_stale: bool = True
    timeout_window_s: float = Field(default=2.0, ge=0.0, le=30.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


class SITLMavlink2RestTimeoutSummary(BaseModel):
    source: str
    requested_failure_count: int
    applied_failure_count: int
    failure_reason: str
    force_stale: bool
    timeout_window_s: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SITLMavlink2RestTimeoutResponse(BaseModel):
    """Response from a validation-only MAVLink2REST timeout injection."""

    status: str
    accepted: bool
    reason: Optional[str] = None
    injection: SITLMavlink2RestTimeoutSummary
    mavlink_telemetry: Optional[SITLMavlinkTelemetrySummary] = None
    timestamp: float


SITL_ERROR_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {
        "model": APIErrorResponse,
        "description": "SITL validation injections are disabled.",
    },
    status.HTTP_409_CONFLICT: {
        "model": APIErrorResponse,
        "description": "SITL validation injection could not be dispatched.",
    },
    status.HTTP_422_UNPROCESSABLE_ENTITY: {
        "model": APIErrorResponse,
        "description": "Invalid SITL validation injection request.",
    },
    status.HTTP_501_NOT_IMPLEMENTED: {
        "model": APIErrorResponse,
        "description": "SITL validation injection hook unavailable.",
    },
}

SITL_VALIDATION_STATUS_ERROR_RESPONSES = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": APIErrorResponse,
        "description": "SITL validation status could not be evaluated.",
    },
}
