"""Fail-closed API bind and CORS exposure policy."""

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Iterable, Optional, Tuple
from urllib.parse import urlsplit


LOCAL_ONLY = "local_only"
TRUSTED_LAN_LEGACY = "trusted_lan_legacy"
SUPPORTED_EXPOSURE_MODES = frozenset({LOCAL_ONLY, TRUSTED_LAN_LEGACY})
DEFAULT_LOCAL_CORS_ORIGINS = (
    "http://127.0.0.1:3040",
    "http://localhost:3040",
    "http://127.0.0.1:5077",
    "http://localhost:5077",
)


class APIExposurePolicyError(ValueError):
    """Raised when API exposure configuration is unsafe or inconsistent."""


@dataclass(frozen=True)
class APIExposurePolicy:
    """Validated process-local API exposure settings."""

    bind_host: str
    mode: str
    cors_allowed_origins: Tuple[str, ...]
    api_port: Optional[int] = None
    allow_credentials: bool = False
    legacy_remote_bind_migrated: bool = False

    @property
    def is_legacy_remote_exposure(self) -> bool:
        return self.mode == TRUSTED_LAN_LEGACY and not is_loopback_host(self.bind_host)


def is_loopback_host(host: str) -> bool:
    """Return whether a bind host is explicitly loopback-only."""
    normalized = str(host or "").strip().lower()
    if normalized == "localhost":
        return True
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _normalize_origin(origin: str) -> str:
    normalized = str(origin or "").strip().rstrip("/")
    if normalized == "*":
        raise APIExposurePolicyError("Wildcard CORS origins are prohibited")

    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise APIExposurePolicyError(
            f"CORS origin must be an explicit http(s) origin without path/query: {origin!r}"
        )
    return normalized


def _normalize_host_name(host: str) -> str:
    normalized = str(host or "").strip().lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    return normalized


def _parse_host_header(host_header: Optional[str]) -> tuple[str, Optional[int]] | None:
    raw = str(host_header or "").strip()
    if not raw:
        return None

    if raw.startswith("["):
        end = raw.find("]")
        if end < 0:
            return None
        hostname = raw[1:end]
        rest = raw[end + 1 :]
        if rest.startswith(":"):
            port_text = rest[1:]
        elif rest:
            return None
        else:
            port_text = ""
    elif raw.count(":") == 1:
        hostname, port_text = raw.rsplit(":", 1)
    else:
        hostname, port_text = raw, ""

    if not hostname:
        return None

    if port_text:
        try:
            port = int(port_text)
        except ValueError:
            return None
        if port < 1 or port > 65535:
            return None
    else:
        port = None

    return _normalize_host_name(hostname), port


def _origin_hostname(origin: str) -> str:
    return _normalize_host_name(urlsplit(origin).hostname or "")


def _port_matches(request_port: Optional[int], policy: APIExposurePolicy) -> bool:
    if request_port is None or policy.api_port is None:
        return True
    return request_port == policy.api_port


def _normalize_api_port(api_port: Optional[int]) -> Optional[int]:
    if api_port is None or api_port == "":
        return None
    try:
        normalized = int(api_port)
    except (TypeError, ValueError) as exc:
        raise APIExposurePolicyError(f"Invalid API port: {api_port!r}") from exc
    if normalized < 1 or normalized > 65535:
        raise APIExposurePolicyError(f"Invalid API port: {api_port!r}")
    return normalized


def _normalize_origins(origins: Iterable[str]) -> Tuple[str, ...]:
    if isinstance(origins, str):
        origins = origins.split(",")
    normalized = tuple(dict.fromkeys(_normalize_origin(origin) for origin in origins))
    return normalized


def is_http_host_allowed(host_header: Optional[str], policy: APIExposurePolicy) -> bool:
    """Return whether the HTTP Host authority is allowed by the exposure mode."""
    parsed = _parse_host_header(host_header)
    if parsed is None:
        return False

    hostname, port = parsed
    if not _port_matches(port, policy):
        return False

    if is_loopback_host(hostname):
        return True

    if policy.mode != TRUSTED_LAN_LEGACY:
        return False

    allowed_hosts = {
        _origin_hostname(origin)
        for origin in policy.cors_allowed_origins
        if _origin_hostname(origin)
    }

    bind_host = _normalize_host_name(policy.bind_host)
    if bind_host and bind_host not in {"0.0.0.0", "::"}:
        allowed_hosts.add(bind_host)

    return hostname in allowed_hosts


def is_websocket_origin_allowed(origin: Optional[str], policy: APIExposurePolicy) -> bool:
    """Return whether a WebSocket Origin is explicitly allowed."""
    if not origin:
        return False
    try:
        normalized = _normalize_origin(origin)
    except APIExposurePolicyError:
        return False
    return normalized in policy.cors_allowed_origins


def is_websocket_request_allowed(
    *,
    host: Optional[str],
    origin: Optional[str],
    policy: APIExposurePolicy,
) -> bool:
    """Require both an allowed Host authority and explicit WebSocket Origin."""
    return is_http_host_allowed(host, policy) and is_websocket_origin_allowed(
        origin,
        policy,
    )


def is_http_browser_request_allowed(
    *,
    host: Optional[str],
    origin: Optional[str],
    sec_fetch_site: Optional[str],
    policy: APIExposurePolicy,
) -> bool:
    """Reject browser cross-site requests while allowing non-browser clients."""
    if not is_http_host_allowed(host, policy):
        return False
    if str(sec_fetch_site or "").strip().lower() == "cross-site":
        return False
    if origin:
        return is_websocket_origin_allowed(origin, policy)
    return True


def resolve_api_exposure_policy(
    *,
    bind_host: str,
    mode: str,
    cors_allowed_origins: Iterable[str],
    api_port: Optional[int] = None,
    legacy_remote_bind_migrated: bool = False,
) -> APIExposurePolicy:
    """Validate and normalize API bind and CORS configuration."""
    normalized_host = str(bind_host or "").strip()
    normalized_mode = str(mode or "").strip().lower()
    normalized_origins = _normalize_origins(cors_allowed_origins or ())
    normalized_api_port = _normalize_api_port(api_port)

    if not normalized_host:
        raise APIExposurePolicyError("HTTP_STREAM_HOST must be explicit")

    if normalized_mode not in SUPPORTED_EXPOSURE_MODES:
        supported = ", ".join(sorted(SUPPORTED_EXPOSURE_MODES))
        raise APIExposurePolicyError(
            f"Unsupported API exposure mode {mode!r}; supported modes: {supported}"
        )

    if normalized_mode == LOCAL_ONLY:
        if not is_loopback_host(normalized_host):
            raise APIExposurePolicyError(
                "API_EXPOSURE_MODE=local_only requires an explicit loopback "
                f"HTTP_STREAM_HOST, got {bind_host!r}"
            )
        remote_origins = [
            origin
            for origin in normalized_origins
            if not is_loopback_host(urlsplit(origin).hostname or "")
        ]
        if remote_origins:
            raise APIExposurePolicyError(
                "API_EXPOSURE_MODE=local_only permits only loopback CORS origins, "
                f"got: {', '.join(remote_origins)}"
            )

    return APIExposurePolicy(
        bind_host=normalized_host,
        mode=normalized_mode,
        cors_allowed_origins=normalized_origins,
        api_port=normalized_api_port,
        legacy_remote_bind_migrated=legacy_remote_bind_migrated,
    )


def resolve_api_exposure_policy_from_parameters(parameters, *, bind_host=None):
    """Build the exposure policy from the flattened Parameters contract."""
    raw_config = getattr(parameters, "_raw_config", {})
    raw_streaming = raw_config.get("Streaming", {}) if isinstance(raw_config, dict) else {}
    if not isinstance(raw_streaming, dict):
        raw_streaming = {}

    mode_is_explicit = "API_EXPOSURE_MODE" in raw_streaming
    if mode_is_explicit:
        mode = raw_streaming.get("API_EXPOSURE_MODE")
    elif raw_streaming:
        mode = LOCAL_ONLY
    else:
        mode = getattr(parameters, "API_EXPOSURE_MODE", LOCAL_ONLY)

    effective_bind_host = bind_host or getattr(parameters, "HTTP_STREAM_HOST", "127.0.0.1")
    legacy_remote_bind_migrated = False
    if not mode_is_explicit and mode == LOCAL_ONLY and not is_loopback_host(effective_bind_host):
        effective_bind_host = "127.0.0.1"
        legacy_remote_bind_migrated = True

    raw_origins = raw_streaming.get("API_CORS_ALLOWED_ORIGINS")
    if raw_origins is None:
        raw_origins = getattr(parameters, "API_CORS_ALLOWED_ORIGINS", DEFAULT_LOCAL_CORS_ORIGINS)

    return resolve_api_exposure_policy(
        bind_host=effective_bind_host,
        mode=mode,
        cors_allowed_origins=raw_origins,
        api_port=getattr(parameters, "HTTP_STREAM_PORT", 5077),
        legacy_remote_bind_migrated=legacy_remote_bind_migrated,
    )
