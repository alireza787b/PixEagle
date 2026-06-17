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
UNSPECIFIED_BIND_HOSTS = frozenset({"0.0.0.0", "::"})


class APIExposurePolicyError(ValueError):
    """Raised when API exposure configuration is unsafe or inconsistent."""


@dataclass(frozen=True)
class APIExposurePolicy:
    """Validated process-local API exposure settings."""

    bind_host: str
    mode: str
    cors_allowed_origins: Tuple[str, ...]
    allowed_hosts: Tuple[str, ...] = ()
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


def _normalize_allowed_host(host: str) -> str:
    raw = str(host or "").strip()
    if not raw:
        raise APIExposurePolicyError("API_ALLOWED_HOSTS entries must not be empty")
    if raw == "*":
        raise APIExposurePolicyError("Wildcard API_ALLOWED_HOSTS entries are prohibited")
    if "://" in raw or "/" in raw or "@" in raw:
        raise APIExposurePolicyError(
            "API_ALLOWED_HOSTS entries must be hostnames or IP literals without scheme, path, or credentials"
        )

    parsed = _parse_host_header(raw)
    if parsed is None:
        raise APIExposurePolicyError(f"Invalid API_ALLOWED_HOSTS entry: {host!r}")
    hostname, _port = parsed
    if hostname in UNSPECIFIED_BIND_HOSTS:
        raise APIExposurePolicyError(
            f"API_ALLOWED_HOSTS must not contain wildcard bind address {host!r}"
        )
    return hostname


def _normalize_allowed_hosts(hosts: Iterable[str]) -> Tuple[str, ...]:
    if isinstance(hosts, str):
        hosts = hosts.split(",")
    normalized = tuple(
        dict.fromkeys(_normalize_allowed_host(host) for host in (hosts or ()))
    )
    return normalized


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

    allowed_hosts = set(policy.allowed_hosts)

    bind_host = _normalize_host_name(policy.bind_host)
    if bind_host and bind_host not in UNSPECIFIED_BIND_HOSTS:
        allowed_hosts.add(bind_host)

    if not allowed_hosts:
        # Compatibility fallback for older trusted_lan_legacy configs created
        # before API_ALLOWED_HOSTS existed. New remote profiles should set
        # API_ALLOWED_HOSTS explicitly so Host allowlisting is not confused
        # with browser CORS origin allowlisting.
        allowed_hosts = {
            _origin_hostname(origin)
            for origin in policy.cors_allowed_origins
            if _origin_hostname(origin)
        }

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
    client_host: Optional[str] = None,
    policy: APIExposurePolicy,
) -> bool:
    """Return whether the WebSocket request stays inside the exposure boundary.

    Browsers send an Origin header and must match the explicit allowlist. Native
    same-host clients, such as QGroundControl or CLI smoke tests, may omit
    Origin; those are accepted only when both the socket peer and Host authority
    are loopback.
    """
    if not is_http_host_allowed(host, policy):
        return False
    if is_websocket_origin_allowed(origin, policy):
        return True
    if origin:
        return False

    parsed_host = _parse_host_header(host)
    if parsed_host is None:
        return False
    hostname, _port = parsed_host
    return is_loopback_host(client_host or "") and is_loopback_host(hostname)


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
    allowed_hosts: Iterable[str] = (),
    api_port: Optional[int] = None,
    allow_credentials: bool = False,
    legacy_remote_bind_migrated: bool = False,
) -> APIExposurePolicy:
    """Validate and normalize API bind and CORS configuration."""
    normalized_host = str(bind_host or "").strip()
    normalized_mode = str(mode or "").strip().lower()
    normalized_origins = _normalize_origins(cors_allowed_origins or ())
    normalized_allowed_hosts = _normalize_allowed_hosts(allowed_hosts or ())
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
        remote_allowed_hosts = [
            host for host in normalized_allowed_hosts if not is_loopback_host(host)
        ]
        if remote_allowed_hosts:
            raise APIExposurePolicyError(
                "API_EXPOSURE_MODE=local_only permits only loopback API_ALLOWED_HOSTS, "
                f"got: {', '.join(remote_allowed_hosts)}"
            )

    return APIExposurePolicy(
        bind_host=normalized_host,
        mode=normalized_mode,
        cors_allowed_origins=normalized_origins,
        allowed_hosts=normalized_allowed_hosts,
        api_port=normalized_api_port,
        allow_credentials=bool(allow_credentials),
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

    raw_allowed_hosts = raw_streaming.get("API_ALLOWED_HOSTS")
    if raw_allowed_hosts is None:
        raw_allowed_hosts = getattr(parameters, "API_ALLOWED_HOSTS", ())

    auth_mode = raw_streaming.get(
        "API_AUTH_MODE",
        getattr(parameters, "API_AUTH_MODE", ""),
    )
    allow_credentials = str(auth_mode or "").strip().lower() == "browser_session"

    return resolve_api_exposure_policy(
        bind_host=effective_bind_host,
        mode=mode,
        cors_allowed_origins=raw_origins,
        allowed_hosts=raw_allowed_hosts,
        api_port=getattr(parameters, "HTTP_STREAM_PORT", 5077),
        allow_credentials=allow_credentials,
        legacy_remote_bind_migrated=legacy_remote_bind_migrated,
    )
