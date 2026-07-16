"""Process-local API v1 streaming/media health helpers."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from classes.api_v1_contracts import STREAMING_MEDIA_CLAIM_BOUNDARY
from classes.parameters import Parameters


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round_optional(value: Optional[float], digits: int = 3) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def _streaming_enabled() -> bool:
    return bool(getattr(Parameters, "ENABLE_STREAMING", True))


def _frame_stale_timeout_s() -> float:
    fps = _safe_float(getattr(Parameters, "STREAM_FPS", 10), 10.0)
    if fps <= 0:
        return 1.0
    return max(1.0, round(3.0 / fps, 3))


def _transport_status(
    *,
    enabled: bool,
    active_connections: int,
    max_connections: Optional[int],
    unavailable: bool = False,
) -> str:
    if unavailable:
        return "unavailable"
    if not enabled:
        return "disabled"
    if max_connections is not None and max_connections > 0:
        if active_connections >= max_connections:
            return "saturated"
    if max_connections is not None and max_connections <= 0:
        return "disabled"
    if active_connections > 0:
        return "active"
    return "idle"


def _endpoint(path: str) -> str:
    host = str(getattr(Parameters, "HTTP_STREAM_HOST", "127.0.0.1"))
    port = _safe_int(getattr(Parameters, "HTTP_STREAM_PORT", 5077), 5077)
    return f"http://{host}:{port}{path}"


def _websocket_endpoint(path: str) -> str:
    host = str(getattr(Parameters, "HTTP_STREAM_HOST", "127.0.0.1"))
    port = _safe_int(getattr(Parameters, "HTTP_STREAM_PORT", 5077), 5077)
    return f"ws://{host}:{port}{path}"


def _frame_snapshot(owner: Any, health_issues: List[str]) -> Dict[str, Any]:
    publisher = getattr(owner, "frame_publisher", None)
    preferred_source = (
        "osd" if bool(getattr(Parameters, "STREAM_PROCESSED_OSD", True)) else "raw"
    )
    latest_frame = None
    if publisher and hasattr(publisher, "get_latest"):
        try:
            latest_frame = publisher.get_latest(prefer_osd=(preferred_source == "osd"))
        except Exception as exc:
            health_issues.append(f"frame_publisher_unavailable:{exc}")

    latest_frame_age_s = None
    latest_frame_id = None
    latest_frame_is_osd = None
    stale_timeout_s = _frame_stale_timeout_s()
    latest_frame_stale = False
    if latest_frame is not None:
        latest_frame_id = getattr(latest_frame, "frame_id", None)
        latest_frame_is_osd = getattr(latest_frame, "is_osd", None)
        timestamp = getattr(latest_frame, "timestamp", None)
        if timestamp is not None:
            latest_frame_age_s = max(0.0, time.monotonic() - float(timestamp))
            latest_frame_stale = latest_frame_age_s > stale_timeout_s

    stats = getattr(owner, "stats", {}) or {}
    frames_sent = _safe_int(stats.get("frames_sent", 0))
    frames_dropped = _safe_int(stats.get("frames_dropped", 0))
    frame_total = frames_sent + frames_dropped
    drop_ratio = round(frames_dropped / frame_total, 4) if frame_total else 0.0
    stream_optimizer = getattr(owner, "stream_optimizer", None)
    frame_cache = getattr(stream_optimizer, "frame_cache", {}) or {}

    return {
        "source_available": latest_frame is not None,
        "preferred_source": preferred_source,
        "latest_frame_id": latest_frame_id,
        "latest_frame_age_s": _round_optional(latest_frame_age_s),
        "latest_frame_stale": latest_frame_stale,
        "stale_timeout_s": stale_timeout_s,
        "latest_frame_is_osd": latest_frame_is_osd,
        "publisher_client_count": _safe_int(
            getattr(publisher, "client_count", 0),
        ),
        "frames_sent": frames_sent,
        "frames_dropped": frames_dropped,
        "drop_ratio": drop_ratio,
        "total_bandwidth_mb": round(
            _safe_float(stats.get("total_bandwidth", 0)) / 1024 / 1024,
            3,
        ),
        "cache_size": len(frame_cache),
    }


def _websocket_clients_snapshot(clients: List[Any], now: float) -> List[Dict[str, Any]]:
    snapshots = []
    for client in clients:
        last_frame_time = _safe_float(getattr(client, "last_frame_time", 0.0))
        last_frame_age_s = None
        if last_frame_time > 0:
            last_frame_age_s = max(0.0, now - last_frame_time)
        snapshots.append(
            {
                "id": str(getattr(client, "id", "")),
                "connected_duration_s": round(
                    max(0.0, now - _safe_float(getattr(client, "connected_at", now))),
                    3,
                ),
                "quality": _safe_int(getattr(client, "quality", 0)),
                "frame_drops": _safe_int(getattr(client, "frame_drops", 0)),
                "bandwidth_kbps": round(
                    _safe_float(getattr(client, "bandwidth_estimate", 0.0)) * 8 / 1024,
                    1,
                ),
                "last_frame_age_s": _round_optional(last_frame_age_s),
            }
        )
    return snapshots


def _security_snapshot(owner: Any) -> Dict[str, Any]:
    exposure_policy = getattr(owner, "exposure_policy", None)
    auth_runtime = getattr(owner, "api_auth_runtime", None)
    return {
        "exposure_mode": getattr(
            exposure_policy,
            "mode",
            getattr(Parameters, "API_EXPOSURE_MODE", None),
        ),
        "bind_host": getattr(
            exposure_policy,
            "bind_host",
            getattr(Parameters, "HTTP_STREAM_HOST", None),
        ),
        "auth_mode": getattr(
            auth_runtime,
            "mode",
            getattr(Parameters, "API_AUTH_MODE", None),
        ),
        "required_scope": "media:read",
        "websocket_origin_check": True,
        "query_string_tokens_allowed": False,
    }


def _config_snapshot() -> Dict[str, Any]:
    return {
        "streaming_enabled": _streaming_enabled(),
        "stream_fps": _safe_int(getattr(Parameters, "STREAM_FPS", 10), 10),
        "stream_width": _safe_int(getattr(Parameters, "STREAM_WIDTH", 640), 640),
        "stream_height": _safe_int(getattr(Parameters, "STREAM_HEIGHT", 480), 480),
        "stream_quality": _safe_int(getattr(Parameters, "STREAM_QUALITY", 50), 50),
        "processed_osd": bool(getattr(Parameters, "STREAM_PROCESSED_OSD", True)),
        "adaptive_quality_enabled": bool(
            getattr(Parameters, "ENABLE_ADAPTIVE_QUALITY", True)
        ),
        "default_protocol": str(getattr(Parameters, "DEFAULT_PROTOCOL", "auto")),
        "pipeline_mode": str(getattr(Parameters, "PIPELINE_MODE", "REALTIME")),
    }


def _quality_engine_snapshot(owner: Any, health_issues: List[str]) -> Dict[str, Any]:
    quality_engine = getattr(owner, "quality_engine", None)
    if not quality_engine or not hasattr(quality_engine, "get_all_states"):
        return {}
    try:
        return quality_engine.get_all_states()
    except Exception as exc:
        health_issues.append(f"quality_engine_unavailable:{exc}")
        return {}


async def _connection_snapshot(owner: Any) -> tuple[int, List[Any]]:
    lock = getattr(owner, "connection_lock", None)

    async def read_unlocked() -> tuple[int, List[Any]]:
        http_connections = getattr(owner, "http_connections", set()) or set()
        ws_connections = getattr(owner, "ws_connections", {}) or {}
        return len(http_connections), list(ws_connections.values())

    if lock is None:
        return await read_unlocked()

    async with lock:
        return await read_unlocked()


async def get_streaming_media_health_snapshot(owner: Any) -> Dict[str, Any]:
    """Return typed process-local media transport and frame-publisher health."""
    health_issues: List[str] = []
    now = time.time()

    try:
        http_active, ws_clients = await _connection_snapshot(owner)
    except Exception as exc:
        health_issues.append(f"connection_snapshot_unavailable:{exc}")
        http_active, ws_clients = 0, []

    webrtc_manager = getattr(owner, "webrtc_manager", None)
    peer_connections = getattr(webrtc_manager, "peer_connections", {}) or {}
    webrtc_active = len(peer_connections)

    gstreamer_handler = getattr(getattr(owner, "app_controller", None), "gstreamer_handler", None)
    gstreamer_status: Dict[str, Any] = {}
    if gstreamer_handler is not None:
        try:
            gstreamer_status = dict(getattr(gstreamer_handler, "encoder_status", {}) or {})
        except Exception as exc:
            health_issues.append(f"gstreamer_status_unavailable:{exc}")

    gstreamer_config_enabled = bool(getattr(Parameters, "ENABLE_GSTREAMER_STREAM", False))
    gstreamer_active = bool(gstreamer_status.get("enabled", False))
    gstreamer_cleanup_pending = bool(gstreamer_status.get("cleanup_pending", False))
    gstreamer_last_error = gstreamer_status.get("last_error")
    gstreamer_details = {
        key: value
        for key, value in gstreamer_status.items()
        if key not in {"cleanup_pending", "last_error"}
    }
    if gstreamer_config_enabled and gstreamer_handler is None:
        health_issues.append("gstreamer_config_enabled_handler_missing")
    if gstreamer_config_enabled and gstreamer_handler is not None and not gstreamer_active:
        health_issues.append("gstreamer_output_configured_but_inactive")
    if gstreamer_cleanup_pending:
        health_issues.append("gstreamer_output_cleanup_pending")

    http_max = _safe_int(getattr(Parameters, "HTTP_MAX_CONNECTIONS", 20), 20)
    ws_max = _safe_int(getattr(Parameters, "WS_MAX_CONNECTIONS", 10), 10)
    webrtc_max = _safe_int(getattr(Parameters, "WEBRTC_MAX_CONNECTIONS", 3), 3)
    backend_streaming_enabled = _streaming_enabled()
    http_enabled = backend_streaming_enabled and http_max > 0
    ws_enabled = backend_streaming_enabled and ws_max > 0
    webrtc_enabled = backend_streaming_enabled and webrtc_max > 0

    transports = [
        {
            "name": "http_mjpeg",
            "enabled": http_enabled,
            "status": _transport_status(
                enabled=http_enabled,
                active_connections=http_active,
                max_connections=http_max,
            ),
            "endpoint": _endpoint("/video_feed"),
            "route_registered": True,
            "active_connections": http_active,
            "max_connections": http_max,
            "details": {},
        },
        {
            "name": "websocket_jpeg",
            "enabled": ws_enabled,
            "status": _transport_status(
                enabled=ws_enabled,
                active_connections=len(ws_clients),
                max_connections=ws_max,
            ),
            "endpoint": _websocket_endpoint("/ws/video_feed"),
            "route_registered": True,
            "active_connections": len(ws_clients),
            "max_connections": ws_max,
            "details": {
                "clients": _websocket_clients_snapshot(ws_clients, now),
                "heartbeat_interval_s": _safe_int(
                    getattr(Parameters, "WS_HEARTBEAT_INTERVAL", 30),
                    30,
                ),
                "stale_timeout_multiplier": _safe_int(
                    getattr(Parameters, "WS_STALE_TIMEOUT_MULTIPLIER", 2),
                    2,
                ),
            },
        },
        {
            "name": "webrtc_signaling",
            "enabled": webrtc_enabled,
            "status": _transport_status(
                enabled=webrtc_enabled,
                active_connections=webrtc_active,
                max_connections=webrtc_max,
            ),
            "endpoint": _websocket_endpoint("/ws/webrtc_signaling"),
            "route_registered": True,
            "active_connections": webrtc_active,
            "max_connections": webrtc_max,
            "details": {
                "peer_ids": sorted(str(peer_id) for peer_id in peer_connections.keys()),
                "ice_servers": list(
                    getattr(webrtc_manager, "ice_server_summary", []) or []
                ),
            },
        },
        {
            "name": "gstreamer_udp_h264",
            "enabled": gstreamer_config_enabled,
            "status": (
                "active"
                if gstreamer_config_enabled and gstreamer_active
                else "unavailable"
                if gstreamer_cleanup_pending
                else _transport_status(
                    enabled=gstreamer_config_enabled,
                    active_connections=0,
                    max_connections=None,
                    unavailable=gstreamer_config_enabled and gstreamer_handler is None,
                )
            ),
            "endpoint": (
                f"udp://{getattr(Parameters, 'GSTREAMER_HOST', '127.0.0.1')}:"
                f"{_safe_int(getattr(Parameters, 'GSTREAMER_PORT', 5600), 5600)}"
            ),
            "route_registered": False,
            "active_connections": 0,
            "max_connections": None,
            "cleanup_pending": gstreamer_cleanup_pending,
            "last_error": gstreamer_last_error,
            "details": {
                **gstreamer_details,
                "pipeline_active": gstreamer_active,
                "connection_semantics": "udp_output_has_no_client_connection_count",
            },
        },
    ]

    frames = _frame_snapshot(owner, health_issues)
    active_clients = http_active + len(ws_clients) + webrtc_active
    active_media_outputs = active_clients > 0 or gstreamer_active
    if active_media_outputs and not frames["source_available"]:
        health_issues.append("active_media_clients_without_published_frame")
    if active_media_outputs and frames["latest_frame_stale"]:
        health_issues.append("published_frame_stale")
    if not backend_streaming_enabled and active_clients > 0:
        health_issues.append("backend_streaming_disabled_with_active_clients")

    saturated = [item["name"] for item in transports if item["status"] == "saturated"]
    if saturated:
        health_issues.append(f"transport_connection_limit_reached:{','.join(saturated)}")

    quality_engine = _quality_engine_snapshot(owner, health_issues)
    if getattr(owner, "is_shutting_down", False):
        status = "unavailable"
        consumer_guidance = "unavailable"
    elif health_issues:
        status = "degraded"
        consumer_guidance = "operator_attention"
    elif active_clients > 0 or gstreamer_active:
        status = "active"
        consumer_guidance = "serving_media"
    else:
        status = "idle"
        consumer_guidance = "idle"

    return {
        "schema_version": 1,
        "source": "streaming_media",
        "status": status,
        "consumer_guidance": consumer_guidance,
        "transports": transports,
        "frames": frames,
        "security": _security_snapshot(owner),
        "config": _config_snapshot(),
        "quality_engine": quality_engine,
        "health_issues": health_issues,
        "claim_boundary": STREAMING_MEDIA_CLAIM_BOUNDARY,
        "timestamp": now,
    }


__all__ = [
    "get_streaming_media_health_snapshot",
]
