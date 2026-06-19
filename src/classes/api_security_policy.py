"""Declarative, default-deny security policy for PixEagle API routes.

This module classifies the HTTP and WebSocket surface consumed by the runtime
authentication middleware. New routes must be declared here, covered by the
inventory tests, and assigned explicit authentication, scope, CSRF, and audit
requirements before they can execute.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from classes.api_security_types import (
    ACTIONS_EXECUTE,
    ACTIONS_READ,
    APIAccessMode,
    APIAuditPolicy,
    APIRouteSecurityPolicy,
    APISensitivity,
    CONFIG_READ,
    CONFIG_WRITE,
    CONTROL_READ,
    CONTROL_WRITE,
    DEBUG_READ,
    MEDIA_READ,
    MEDIA_WRITE,
    MODELS_MANAGE,
    MODELS_READ,
    MODELS_SELECT,
    RECORDINGS_READ,
    RECORDINGS_WRITE,
    SAFETY_READ,
    SAFETY_WRITE,
    SITL_INJECT,
    STATUS_READ,
    SYSTEM_ADMIN,
    SYSTEM_READ,
    TELEMETRY_READ,
)


@dataclass(frozen=True)
class APIRouteSecurityRule:
    """A method/template rule that resolves declared and concrete paths."""

    name: str
    methods: frozenset[str]
    path_templates: tuple[str, ...]
    policy: APIRouteSecurityPolicy

    def matches(self, method: str, path: str) -> bool:
        normalized_method = str(method or "").strip().upper()
        if normalized_method not in self.methods:
            return False
        return any(
            _path_template_matches(template, path)
            for template in self.path_templates
        )


def _policy(
    access: APIAccessMode,
    sensitivity: APISensitivity,
    scopes: Iterable[str],
    audit: APIAuditPolicy,
    *,
    csrf: bool = False,
    rationale: str,
) -> APIRouteSecurityPolicy:
    return APIRouteSecurityPolicy(
        access=access,
        sensitivity=sensitivity,
        required_scopes=frozenset(scopes),
        audit=audit,
        csrf_required_for_session=csrf,
        rationale=rationale,
    )


AUTH_STATUS = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.STATUS,
    {STATUS_READ},
    APIAuditPolicy.NONE,
    rationale="Process status and compatibility metadata require an authenticated viewer.",
)
AUTH_TELEMETRY = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.TELEMETRY,
    {TELEMETRY_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="Live vehicle, target, follower, and safety state is sensitive operational data.",
)
AUTH_MEDIA_READ = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.MEDIA,
    {MEDIA_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="Live imagery and media transport require explicit media read authority.",
)
AUTH_MEDIA_WRITE = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.MEDIA,
    {MEDIA_WRITE},
    APIAuditPolicy.MUTATION,
    csrf=True,
    rationale="Media reconnect/output changes mutate the live runtime.",
)
AUTH_CONFIG_READ = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.CONFIG,
    {CONFIG_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="Runtime and default configuration can reveal operational deployment details.",
)
AUTH_CONFIG_WRITE = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.CONFIG,
    {CONFIG_WRITE},
    APIAuditPolicy.MUTATION,
    csrf=True,
    rationale="Configuration changes require explicit write authority and browser CSRF.",
)
AUTH_MODELS_READ = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.MODELS,
    {MODELS_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="Model inventory and files are authenticated product resources.",
)
AUTH_MODELS_SELECT = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.MODELS,
    {MODELS_SELECT},
    APIAuditPolicy.MUTATION,
    csrf=True,
    rationale="Selecting the active model changes detector behavior.",
)
AUTH_MODELS_MANAGE = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.MODELS,
    {MODELS_MANAGE},
    APIAuditPolicy.MUTATION,
    csrf=True,
    rationale="Model installation, remote download, and deletion are administrative.",
)
AUTH_RECORDINGS_READ = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.RECORDINGS,
    {RECORDINGS_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="Recordings can contain sensitive imagery and operational data.",
)
AUTH_RECORDINGS_WRITE = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.RECORDINGS,
    {RECORDINGS_WRITE},
    APIAuditPolicy.MUTATION,
    csrf=True,
    rationale="Recording lifecycle and deletion require explicit write authority.",
)
AUTH_CONTROL_READ = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.CONTROL,
    {CONTROL_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="Tracker, follower, OSD, and output state requires authenticated access.",
)
AUTH_CONTROL_WRITE = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.CONTROL,
    {CONTROL_WRITE},
    APIAuditPolicy.MUTATION,
    csrf=True,
    rationale="Runtime tracker, follower, OSD, or output mutations require operator authority.",
)
AUTH_SAFETY_READ = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.SAFETY,
    {SAFETY_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="Safety configuration and circuit-breaker state are sensitive operational data.",
)
AUTH_SAFETY_WRITE = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.SAFETY,
    {SAFETY_WRITE},
    APIAuditPolicy.SECURITY_CRITICAL,
    csrf=True,
    rationale="Safety-state mutations require elevated authority and durable security audit events.",
)
AUTH_ACTION_READ = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.CONTROL,
    {ACTIONS_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="Action resources expose control intent and execution outcomes.",
)
AUTH_ACTION_EXECUTE = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.CONTROL,
    {ACTIONS_EXECUTE},
    APIAuditPolicy.SECURITY_CRITICAL,
    csrf=True,
    rationale="Guarded flight-adjacent actions require explicit execution authority.",
)
AUTH_SYSTEM_READ = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.SYSTEM,
    {SYSTEM_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="System status and frontend configuration require authenticated access.",
)
PUBLIC_AUTH_SESSION = _policy(
    APIAccessMode.PUBLIC,
    APISensitivity.SYSTEM,
    (),
    APIAuditPolicy.NONE,
    rationale="Browser clients need a safe bootstrap route to discover session state.",
)
PUBLIC_AUTH_LOGIN = _policy(
    APIAccessMode.PUBLIC,
    APISensitivity.SYSTEM,
    (),
    APIAuditPolicy.SECURITY_CRITICAL,
    rationale="Login must be reachable before authentication but requires rate/audit hardening.",
)
AUTH_SESSION_LOGOUT = _policy(
    APIAccessMode.AUTHENTICATED,
    APISensitivity.SYSTEM,
    {STATUS_READ},
    APIAuditPolicy.SECURITY_CRITICAL,
    csrf=True,
    rationale="Logout revokes browser session state and requires session-bound CSRF.",
)
LOCAL_LEGACY_MODELS_READ = _policy(
    APIAccessMode.LOCAL_ONLY,
    APISensitivity.MODELS,
    {MODELS_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="Deprecated YOLO aliases stay local-only until clients migrate to canonical routes.",
)
LOCAL_LEGACY_MODELS_SELECT = _policy(
    APIAccessMode.LOCAL_ONLY,
    APISensitivity.MODELS,
    {MODELS_SELECT},
    APIAuditPolicy.MUTATION,
    csrf=True,
    rationale="Deprecated YOLO selection stays local-only until canonical migration.",
)
LOCAL_LEGACY_MODELS_MANAGE = _policy(
    APIAccessMode.LOCAL_ONLY,
    APISensitivity.MODELS,
    {MODELS_MANAGE},
    APIAuditPolicy.MUTATION,
    csrf=True,
    rationale="Deprecated YOLO model management stays local-only until retirement.",
)
LOCAL_SYSTEM_ADMIN = _policy(
    APIAccessMode.LOCAL_ONLY,
    APISensitivity.SYSTEM,
    {SYSTEM_ADMIN},
    APIAuditPolicy.SECURITY_CRITICAL,
    csrf=True,
    rationale=(
        "Process termination/restart and safety bypass remain local-only "
        "administrative actions."
    ),
)
LOCAL_API_DOCUMENTATION = _policy(
    APIAccessMode.LOCAL_ONLY,
    APISensitivity.SYSTEM,
    {SYSTEM_ADMIN},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="OpenAPI and interactive docs stay local-only and require administrative authority.",
)
LOCAL_SITL_INJECTION = _policy(
    APIAccessMode.LOCAL_ONLY,
    APISensitivity.VALIDATION,
    {SITL_INJECT},
    APIAuditPolicy.SECURITY_CRITICAL,
    csrf=True,
    rationale=(
        "Validation injectors stay local-only in addition to their explicit "
        "runtime enablement gate."
    ),
)
LOCAL_DEBUG_READ = _policy(
    APIAccessMode.LOCAL_ONLY,
    APISensitivity.DEBUG,
    {DEBUG_READ},
    APIAuditPolicy.SENSITIVE_READ,
    rationale="Debug coordinate data is a local engineering surface, not a remote product API.",
)
DENY_UNCLASSIFIED = _policy(
    APIAccessMode.DENY,
    APISensitivity.UNKNOWN,
    (),
    APIAuditPolicy.SECURITY_CRITICAL,
    rationale="Unclassified routes are denied by default.",
)


API_ROUTE_SECURITY_RULES = (
    APIRouteSecurityRule(
        "auth_session_status",
        frozenset({"GET"}),
        ("/api/v1/auth/session",),
        PUBLIC_AUTH_SESSION,
    ),
    APIRouteSecurityRule(
        "auth_login",
        frozenset({"POST"}),
        ("/api/v1/auth/login",),
        PUBLIC_AUTH_LOGIN,
    ),
    APIRouteSecurityRule(
        "auth_logout",
        frozenset({"POST"}),
        ("/api/v1/auth/logout",),
        AUTH_SESSION_LOGOUT,
    ),
    APIRouteSecurityRule(
        "status_reads",
        frozenset({"GET"}),
        (
            "/status",
            "/stats",
            "/api/compatibility/report",
            "/api/streaming/status",
            "/api/system/schema_info",
            "/api/v1/runtime/status",
        ),
        AUTH_STATUS,
    ),
    APIRouteSecurityRule(
        "telemetry_reads",
        frozenset({"GET"}),
        (
            "/telemetry/tracker_data",
            "/telemetry/follower_data",
            "/api/v1/telemetry/health",
            "/api/v1/following/status",
            "/api/v1/following/telemetry",
            "/api/v1/tracking/runtime-status",
            "/api/v1/tracking/telemetry",
            "/api/tracker/current-status",
            "/api/tracker/output",
            "/api/follower/setpoints-status",
            "/api/follower/health",
        ),
        AUTH_TELEMETRY,
    ),
    APIRouteSecurityRule(
        "media_http_reads",
        frozenset({"GET"}),
        (
            "/video_feed",
            "/api/video/health",
            "/api/v1/streams/media-health",
        ),
        AUTH_MEDIA_READ,
    ),
    APIRouteSecurityRule(
        "media_websocket_reads",
        frozenset({"WEBSOCKET"}),
        (
            "/ws/video_feed",
            "/ws/webrtc_signaling",
        ),
        AUTH_MEDIA_READ,
    ),
    APIRouteSecurityRule(
        "media_mutations",
        frozenset({"POST"}),
        ("/api/video/reconnect",),
        AUTH_MEDIA_WRITE,
    ),
    APIRouteSecurityRule(
        "config_reads",
        frozenset({"GET"}),
        (
            "/api/config/audit",
            "/api/config/categories",
            "/api/config/current",
            "/api/config/current/{section}",
            "/api/config/default",
            "/api/config/default/{section}",
            "/api/config/defaults-sync",
            "/api/config/diff",
            "/api/config/effective-limits",
            "/api/config/export",
            "/api/config/history",
            "/api/config/schema",
            "/api/config/schema/{section}",
            "/api/config/search",
            "/api/config/sections",
            "/api/config/sections/relevant",
            "/api/follower/config/general",
            "/api/follower/config/{follower_name}",
        ),
        AUTH_CONFIG_READ,
    ),
    APIRouteSecurityRule(
        "config_preview_operations",
        frozenset({"POST"}),
        (
            "/api/config/validate",
            "/api/config/diff",
            "/api/config/defaults-sync/plan",
        ),
        AUTH_CONFIG_READ,
    ),
    APIRouteSecurityRule(
        "config_parameter_mutations",
        frozenset({"PUT"}),
        (
            "/api/config/{section}",
            "/api/config/{section}/{parameter}",
        ),
        AUTH_CONFIG_WRITE,
    ),
    APIRouteSecurityRule(
        "config_resource_mutations",
        frozenset({"POST"}),
        (
            "/api/config/defaults-sync/apply",
            "/api/config/revert",
            "/api/config/revert/{section}",
            "/api/config/revert/{section}/{parameter}",
            "/api/config/restore/{backup_id}",
            "/api/config/import",
        ),
        AUTH_CONFIG_WRITE,
    ),
    APIRouteSecurityRule(
        "model_reads",
        frozenset({"GET"}),
        (
            "/api/models",
            "/api/models/active",
            "/api/models/{model_id}/file",
            "/api/models/{model_id}/labels",
        ),
        AUTH_MODELS_READ,
    ),
    APIRouteSecurityRule(
        "model_selection",
        frozenset({"POST"}),
        ("/api/models/switch",),
        AUTH_MODELS_SELECT,
    ),
    APIRouteSecurityRule(
        "model_management_post_mutations",
        frozenset({"POST"}),
        (
            "/api/models/upload",
            "/api/models/download",
        ),
        AUTH_MODELS_MANAGE,
    ),
    APIRouteSecurityRule(
        "model_delete_mutations",
        frozenset({"DELETE"}),
        ("/api/models/{model_id}",),
        AUTH_MODELS_MANAGE,
    ),
    APIRouteSecurityRule(
        "recording_reads",
        frozenset({"GET"}),
        (
            "/api/recording/status",
            "/api/recordings",
            "/api/recordings/{filename}",
            "/api/storage/status",
        ),
        AUTH_RECORDINGS_READ,
    ),
    APIRouteSecurityRule(
        "recording_post_mutations",
        frozenset({"POST"}),
        (
            "/api/recording/start",
            "/api/recording/pause",
            "/api/recording/resume",
            "/api/recording/stop",
            "/api/recording/toggle",
            "/api/recording/include-osd/{enabled}",
        ),
        AUTH_RECORDINGS_WRITE,
    ),
    APIRouteSecurityRule(
        "recording_delete_mutations",
        frozenset({"DELETE"}),
        ("/api/recordings/{filename}",),
        AUTH_RECORDINGS_WRITE,
    ),
    APIRouteSecurityRule(
        "control_reads",
        frozenset({"GET"}),
        (
            "/api/follower/schema",
            "/api/follower/profiles",
            "/api/follower/current-profile",
            "/api/follower/configured-mode",
            "/api/follower/current-mode",
            "/api/tracker/schema",
            "/api/tracker/capabilities",
            "/api/tracker/available-types",
            "/api/tracker/current-config",
            "/api/tracker/available",
            "/api/tracker/current",
            "/api/osd/status",
            "/api/osd/presets",
            "/api/osd/color-modes",
            "/api/osd/modes",
            "/api/gstreamer/status",
        ),
        AUTH_CONTROL_READ,
    ),
    APIRouteSecurityRule(
        "control_mutations",
        frozenset({"POST"}),
        (
            "/api/follower/switch-profile",
            "/api/follower/restart",
            "/api/tracker/set-type",
            "/api/tracker/switch",
            "/api/tracker/restart",
            "/api/osd/toggle",
            "/api/osd/preset/{preset_name}",
            "/api/osd/color-mode/{mode}",
            "/api/gstreamer/toggle",
        ),
        AUTH_CONTROL_WRITE,
    ),
    APIRouteSecurityRule(
        "safety_reads",
        frozenset({"GET"}),
        (
            "/api/safety/config",
            "/api/safety/limits/{follower_name}",
            "/api/circuit-breaker/status",
            "/api/circuit-breaker/statistics",
        ),
        AUTH_SAFETY_READ,
    ),
    APIRouteSecurityRule(
        "safety_mutations",
        frozenset({"POST"}),
        (
            "/api/circuit-breaker/toggle",
            "/api/circuit-breaker/reset-statistics",
        ),
        AUTH_SAFETY_WRITE,
    ),
    APIRouteSecurityRule(
        "typed_action_reads",
        frozenset({"GET"}),
        ("/api/v1/actions/{action_id}",),
        AUTH_ACTION_READ,
    ),
    APIRouteSecurityRule(
        "typed_action_mutations",
        frozenset({"POST"}),
        (
            "/api/v1/actions/offboard-start",
            "/api/v1/actions/offboard-stop",
            "/api/v1/actions/operator-abort",
            "/api/v1/actions/segmentation-toggle",
            "/api/v1/actions/smart-click",
            "/api/v1/actions/smart-mode-toggle",
            "/api/v1/actions/tracking-redetect",
            "/api/v1/actions/tracking-start",
            "/api/v1/actions/tracking-stop",
        ),
        AUTH_ACTION_EXECUTE,
    ),
    APIRouteSecurityRule(
        "system_reads",
        frozenset({"GET"}),
        (
            "/api/system/status",
            "/api/system/config",
        ),
        AUTH_SYSTEM_READ,
    ),
    APIRouteSecurityRule(
        "legacy_yolo_reads",
        frozenset({"GET"}),
        (
            "/api/yolo/models",
            "/api/yolo/active-model",
            "/api/yolo/models/{model_id}/labels",
        ),
        LOCAL_LEGACY_MODELS_READ,
    ),
    APIRouteSecurityRule(
        "legacy_yolo_selection",
        frozenset({"POST"}),
        ("/api/yolo/switch-model",),
        LOCAL_LEGACY_MODELS_SELECT,
    ),
    APIRouteSecurityRule(
        "legacy_yolo_management",
        frozenset({"POST"}),
        (
            "/api/yolo/upload",
            "/api/yolo/download",
            "/api/yolo/delete/{model_id}",
        ),
        LOCAL_LEGACY_MODELS_MANAGE,
    ),
    APIRouteSecurityRule(
        "local_system_admin",
        frozenset({"POST"}),
        (
            "/commands/quit",
            "/api/system/restart",
            "/api/circuit-breaker/toggle-safety",
        ),
        LOCAL_SYSTEM_ADMIN,
    ),
    APIRouteSecurityRule(
        "local_sitl_injections",
        frozenset({"POST"}),
        (
            "/api/v1/sitl/injections/commander-publish-failure",
            "/api/v1/sitl/injections/mavlink2rest-timeout",
            "/api/v1/sitl/injections/mavsdk-disconnect",
            "/api/v1/sitl/injections/tracker-output",
            "/api/v1/sitl/injections/video-stall",
        ),
        LOCAL_SITL_INJECTION,
    ),
    APIRouteSecurityRule(
        "local_debug_reads",
        frozenset({"GET"}),
        ("/debug/coordinate_mapping",),
        LOCAL_DEBUG_READ,
    ),
    APIRouteSecurityRule(
        "local_api_documentation",
        frozenset({"GET", "HEAD"}),
        (
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
        ),
        LOCAL_API_DOCUMENTATION,
    ),
)


def _path_template_matches(template: str, path: str) -> bool:
    normalized_path = str(path or "").split("?", 1)[0]
    pattern = re.escape(template)
    pattern = re.sub(r"\\\{[^/{}]+\\\}", r"[^/]+", pattern)
    return re.fullmatch(pattern, normalized_path) is not None


def matching_route_security_rules(
    method: str,
    path: str,
) -> tuple[APIRouteSecurityRule, ...]:
    """Return all matching rules so coverage tests can detect ambiguity."""
    return tuple(
        rule for rule in API_ROUTE_SECURITY_RULES if rule.matches(method, path)
    )


def resolve_route_security_policy(method: str, path: str) -> APIRouteSecurityPolicy:
    """Resolve one route policy and fail closed on missing or ambiguous rules."""
    matches = matching_route_security_rules(method, path)
    if len(matches) != 1:
        return DENY_UNCLASSIFIED
    return matches[0].policy


__all__ = [
    "APIRouteSecurityRule",
    "API_ROUTE_SECURITY_RULES",
    "DENY_UNCLASSIFIED",
    "matching_route_security_rules",
    "resolve_route_security_policy",
]
