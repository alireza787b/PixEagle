#!/usr/bin/env python3
"""Apply PixEagle setup profiles to a local runtime config.

The checked-in `configs/config_default.yaml` remains the source of truth.
This tool creates or updates `configs/config.yaml` only when the operator
explicitly chooses a profile that needs local host-specific values.
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import os
import re
import secrets
import sys
import tempfile
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from pathlib import Path
from time import strftime
from typing import Any, Callable
from urllib.parse import urlsplit

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from classes.api_auth_runtime import make_token_record
from classes.browser_user_store import (
    BrowserUserStore,
    BrowserUserStoreError,
    make_browser_user_record,
)

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "config_default.yaml"
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "configs" / "config.yaml"
DEFAULT_DEMO_USER_FILE = PROJECT_ROOT / "configs" / "secrets" / "demo-browser-users.json"
DEFAULT_QGC_TOKEN_FILE = PROJECT_ROOT / "configs" / "secrets" / "qgc-media-tokens.json"
DEFAULT_QGC_HANDOFF_FILE = PROJECT_ROOT / "configs" / "secrets" / "qgc-media-handoff.json"
DEFAULT_PRODUCTION_USERNAME = "pixeagle-operator"
DEFAULT_QGC_TOKEN_ID = "qgc-media-viewer"
DEFAULT_QGC_TOKEN_SUBJECT = "qgroundcontrol"
LOOPBACK_CORS_ORIGINS = [
    "http://127.0.0.1:3040",
    "http://localhost:3040",
    "http://127.0.0.1:5077",
    "http://localhost:5077",
]
DEFAULT_DASHBOARD_PORT = 3040
DEFAULT_HTTP_STREAM_PORT = 5077
QGC_DEFAULT_UDP_H264_PORT = 5600
UNSPECIFIED_BIND_HOSTS = {"0.0.0.0", "::"}
HOSTNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MACHINE_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
ALLOWED_DEMO_IP_NETWORKS = tuple(
    ip_network(value)
    for value in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "169.254.0.0/16",
        "fc00::/7",
        "fe80::/10",
    )
)
DISALLOWED_PRODUCTION_HOST_NETWORKS = tuple(
    ip_network(value)
    for value in (
        "0.0.0.0/8",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "240.0.0.0/4",
        "2001:db8::/32",
    )
)


class ProfileError(ValueError):
    """Raised when a profile request is incomplete or unsafe."""


@dataclass(frozen=True)
class Profile:
    name: str
    status: str
    description: str
    applier: Callable[[argparse.Namespace], dict[tuple[str, ...], Any]]


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    existed: bool
    content: bytes | None
    mode: int | None


@dataclass(frozen=True)
class AppliedFile:
    snapshot: FileSnapshot
    backup_path: Path | None = None


def _profile_local_dev(args: argparse.Namespace) -> dict[tuple[str, ...], Any]:
    return {
        ("Streaming", "API_EXPOSURE_MODE"): "local_only",
        ("Streaming", "HTTP_STREAM_HOST"): "127.0.0.1",
        ("Streaming", "API_CORS_ALLOWED_ORIGINS"): LOOPBACK_CORS_ORIGINS,
        ("Streaming", "API_ALLOWED_HOSTS"): [],
        ("Streaming", "API_AUTH_MODE"): "local_compat",
        ("Streaming", "API_SYSTEM_RESTART_POLICY"): "local_only",
        ("SmartTracker", "SMART_TRACKER_MODEL_TRUST_POLICY"): "operator_ack_or_digest",
        ("GStreamer", "ENABLE_GSTREAMER_STREAM"): False,
        ("GStreamer", "GSTREAMER_HOST"): "127.0.0.1",
        ("GStreamer", "GSTREAMER_PORT"): QGC_DEFAULT_UDP_H264_PORT,
    }


def _profile_follower_command_preview(
    args: argparse.Namespace,
) -> dict[tuple[str, ...], Any]:
    """Enable the explicit replay-to-intent lab boundary without networking."""
    return {
        ("VideoSource", "VIDEO_SOURCE_TYPE"): "VIDEO_FILE",
        ("VideoSource", "VIDEO_FILE_EOF_POLICY"): "LOOP",
        ("Follower", "FOLLOWER_EXECUTION_MODE"): "COMMAND_PREVIEW",
        ("FOLLOWER_CIRCUIT_BREAKER",): True,
        ("CIRCUIT_BREAKER_DISABLE_SAFETY",): False,
        ("FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES",): False,
    }


def _profile_beginner_lab(args: argparse.Namespace) -> dict[tuple[str, ...], Any]:
    """Create the local-only beginner runtime with replay follower testing."""
    defaults = _load_yaml(args.defaults)
    try:
        video_file_path = str(defaults["VideoSource"]["VIDEO_FILE_PATH"])
        tracker_algorithm = str(
            defaults["Tracking"]["DEFAULT_TRACKING_ALGORITHM"]
        ).upper()
    except (KeyError, TypeError) as exc:
        raise ProfileError(
            "checked-in defaults do not define the beginner video/tracker"
        ) from exc
    if tracker_algorithm not in {"CSRT", "KCF"}:
        raise ProfileError(
            "beginner_lab requires a Core classic tracker default (CSRT or KCF)"
        )

    changes = _profile_local_dev(args)
    changes.update(_profile_follower_command_preview(args))
    changes.update(
        {
            ("VideoSource", "VIDEO_FILE_PATH"): video_file_path,
            ("Tracking", "DEFAULT_TRACKING_ALGORITHM"): tracker_algorithm,
        }
    )
    return changes


def _profile_field_qgc_video(args: argparse.Namespace) -> dict[tuple[str, ...], Any]:
    if not args.gcs_host:
        raise ProfileError(
            "field_qgc_video requires --gcs-host <ground-station-ip-or-hostname>."
        )
    if args.gstreamer_port < 1 or args.gstreamer_port > 65535:
        raise ProfileError("--gstreamer-port must be in the range 1..65535.")

    changes = _profile_local_dev(args)
    changes.update(
        {
            ("GStreamer", "ENABLE_GSTREAMER_STREAM"): True,
            ("GStreamer", "GSTREAMER_HOST"): args.gcs_host,
            ("GStreamer", "GSTREAMER_PORT"): args.gstreamer_port,
        }
    )
    return changes


def _profile_demo_lan_browser(args: argparse.Namespace) -> dict[tuple[str, ...], Any]:
    if not args.lan_host:
        raise ProfileError(
            "demo_lan_browser requires --lan-host <pixeagle-lan-ip-or-hostname>."
        )
    lan_host = _normalize_lan_host(
        args.lan_host,
        allow_public_http_demo=args.allow_public_http_demo,
    )
    http_stream_port = _normalize_port(args.http_stream_port, "--http-stream-port")
    dashboard_port = _normalize_port(args.dashboard_port, "--dashboard-port")
    user_file = _resolve_output_path(args.session_user_file)
    credential_handoff_file = (
        _resolve_output_path(args.credential_handoff_file)
        if args.credential_handoff_file
        else None
    )
    _validate_distinct_output_paths(
        {
            "--defaults": args.defaults,
            "--config": args.config,
            "--session-user-file": user_file,
            **(
                {"--credential-handoff-file": credential_handoff_file}
                if credential_handoff_file is not None
                else {}
            ),
        }
    )
    username_flag = "--session-username" if args.session_username is not None else "--demo-username"
    username = _normalize_session_username(
        args.session_username if args.session_username is not None else args.demo_username,
        username_flag,
    )
    role = args.session_role or args.demo_role
    rotate_credentials = args.rotate_session_credentials or args.rotate_demo_credentials

    if user_file.exists() and not rotate_credentials and not args.dry_run:
        raise ProfileError(
            f"session user file already exists: {user_file}. "
            "Pass --rotate-demo-credentials or --rotate-session-credentials to replace it after saving the old password."
        )
    if (
        credential_handoff_file is not None
        and credential_handoff_file.exists()
        and not rotate_credentials
        and not args.dry_run
    ):
        raise ProfileError(
            f"credential handoff file already exists: {credential_handoff_file}. "
            "Pass --rotate-demo-credentials or --rotate-session-credentials to replace it after securely handling the old file."
        )

    args._demo_lan_host = lan_host["allowed_host"]
    args._demo_origin_host = lan_host["origin_host"]
    args._demo_session_user_file = user_file
    args._demo_credential_handoff_file = credential_handoff_file
    args._demo_http_stream_port = http_stream_port
    args._demo_dashboard_port = dashboard_port
    args._demo_username = username
    args._demo_role = role
    args._demo_rotate_credentials = rotate_credentials
    args._demo_public_http = lan_host["public_http_demo"]

    remote_origins = [
        f"http://{lan_host['origin_host']}:{dashboard_port}",
        f"http://{lan_host['origin_host']}:{http_stream_port}",
    ]
    cors_origins = list(dict.fromkeys([*LOOPBACK_CORS_ORIGINS, *remote_origins]))

    return {
        ("Streaming", "API_EXPOSURE_MODE"): "trusted_lan_legacy",
        ("Streaming", "HTTP_STREAM_HOST"): "0.0.0.0",
        ("Streaming", "HTTP_STREAM_PORT"): http_stream_port,
        ("Streaming", "API_CORS_ALLOWED_ORIGINS"): cors_origins,
        ("Streaming", "API_ALLOWED_HOSTS"): [lan_host["allowed_host"]],
        ("Streaming", "API_AUTH_MODE"): "browser_session",
        ("Streaming", "API_SYSTEM_RESTART_POLICY"): "lab_admin_browser",
        ("Streaming", "API_SESSION_USER_FILE"): str(user_file),
        ("Streaming", "API_SESSION_COOKIE_SECURE"): False,
        ("SmartTracker", "SMART_TRACKER_MODEL_TRUST_POLICY"): "operator_ack_or_digest",
        ("GStreamer", "ENABLE_GSTREAMER_STREAM"): False,
        ("GStreamer", "GSTREAMER_HOST"): "127.0.0.1",
        ("GStreamer", "GSTREAMER_PORT"): QGC_DEFAULT_UDP_H264_PORT,
    }


def _profile_production_remote(args: argparse.Namespace) -> dict[tuple[str, ...], Any]:
    if os.name == "nt" and not args.dry_run:
        raise ProfileError(
            "production_remote credential generation currently requires POSIX "
            "owner-only file modes. Generate it on the Linux deployment host; "
            "Windows ACL automation is not yet evidence-backed."
        )
    if not args.public_host:
        raise ProfileError(
            "production_remote requires --public-host <tls-hostname-or-stable-ip>."
        )
    public_host = _normalize_public_host(args.public_host)
    public_origin = _normalize_public_origin(args.public_origin, public_host)
    http_stream_port = _normalize_port(args.http_stream_port, "--http-stream-port")
    user_file = _resolve_output_path(args.session_user_file)
    credential_handoff_file = (
        _resolve_output_path(args.credential_handoff_file)
        if args.credential_handoff_file
        else None
    )
    if user_file == DEFAULT_DEMO_USER_FILE:
        raise ProfileError(
            "production_remote requires --session-user-file <deployment-managed-json>; "
            "do not reuse the demo credential path."
        )
    _validate_distinct_output_paths(
        {
            "--defaults": args.defaults,
            "--config": args.config,
            "--session-user-file": user_file,
            **(
                {"--credential-handoff-file": credential_handoff_file}
                if credential_handoff_file is not None
                else {}
            ),
        }
    )
    if (
        not args.dry_run
        and credential_handoff_file is None
        and not args.show_generated_password
        and not sys.stdout.isatty()
    ):
        raise ProfileError(
            "production_remote requires --credential-handoff-file for non-interactive "
            "use, or explicit --show-generated-password to acknowledge stdout exposure."
        )

    username = _normalize_session_username(
        args.session_username or DEFAULT_PRODUCTION_USERNAME,
        "--session-username",
    )
    role = args.session_role or "admin"
    if user_file.exists() and not args.rotate_session_credentials and not args.dry_run:
        raise ProfileError(
            f"session user file already exists: {user_file}. "
            "Pass --rotate-session-credentials to replace it after saving the old password."
        )
    if (
        credential_handoff_file is not None
        and credential_handoff_file.exists()
        and not args.rotate_session_credentials
        and not args.dry_run
    ):
        raise ProfileError(
            f"credential handoff file already exists: {credential_handoff_file}. "
            "Pass --rotate-session-credentials to replace it after securely handling the old file."
        )

    args._production_allowed_host = public_host["allowed_host"]
    args._production_origin = public_origin
    args._production_session_user_file = user_file
    args._production_credential_handoff_file = credential_handoff_file
    args._production_http_stream_port = http_stream_port
    args._production_username = username
    args._production_role = role

    public_authority = _origin_host_authority(public_origin)
    return {
        ("Streaming", "API_EXPOSURE_MODE"): "trusted_lan_legacy",
        ("Streaming", "HTTP_STREAM_HOST"): "127.0.0.1",
        ("Streaming", "HTTP_STREAM_PORT"): http_stream_port,
        ("Streaming", "API_CORS_ALLOWED_ORIGINS"): [public_origin],
        ("Streaming", "API_ALLOWED_HOSTS"): [public_authority],
        ("Streaming", "API_AUTH_MODE"): "browser_session",
        ("Streaming", "API_SYSTEM_RESTART_POLICY"): "local_only",
        ("Streaming", "API_SESSION_USER_FILE"): str(user_file),
        ("Streaming", "API_SESSION_COOKIE_SECURE"): True,
        ("Streaming", "API_SECURITY_AUDIT_ENABLED"): True,
        ("SmartTracker", "SMART_TRACKER_MODEL_TRUST_POLICY"): "digest_required",
        ("GStreamer", "ENABLE_GSTREAMER_STREAM"): False,
        ("GStreamer", "GSTREAMER_HOST"): "127.0.0.1",
        ("GStreamer", "GSTREAMER_PORT"): QGC_DEFAULT_UDP_H264_PORT,
    }


def _profile_qgc_direct_media(args: argparse.Namespace) -> dict[tuple[str, ...], Any]:
    if os.name == "nt" and not args.dry_run:
        raise ProfileError(
            "qgc_direct_media credential generation currently requires POSIX "
            "owner-only file modes. Generate it on the Linux PixEagle deployment host."
        )
    if not args.public_host:
        raise ProfileError(
            "qgc_direct_media requires --public-host <tls-hostname-or-stable-ip>."
        )

    public_host = _normalize_public_host(args.public_host)
    public_origin = _normalize_public_origin(args.public_origin, public_host)
    http_stream_port = _normalize_port(args.http_stream_port, "--http-stream-port")
    token_file = _resolve_output_path(args.bearer_token_file)
    handoff_file = _resolve_output_path(args.qgc_handoff_file)
    token_id = _normalize_machine_identifier(args.token_id, "--token-id")
    token_subject = _normalize_machine_identifier(args.token_subject, "--token-subject")
    _validate_distinct_output_paths(
        {
            "--defaults": args.defaults,
            "--config": args.config,
            "--bearer-token-file": token_file,
            "--qgc-handoff-file": handoff_file,
        }
    )

    for path, label in (
        (token_file, "bearer token file"),
        (handoff_file, "credential handoff file"),
    ):
        if path.exists() and not args.rotate_qgc_token and not args.dry_run:
            raise ProfileError(
                f"{label} already exists: {path}. "
                "Pass --rotate-qgc-token to replace it after securely handling the old credential."
            )

    args._qgc_public_origin = public_origin
    args._qgc_http_stream_port = http_stream_port
    args._qgc_token_file = token_file
    args._qgc_handoff_file = handoff_file
    args._qgc_token_id = token_id
    args._qgc_token_subject = token_subject

    return {
        ("Streaming", "API_EXPOSURE_MODE"): "trusted_lan_legacy",
        ("Streaming", "HTTP_STREAM_HOST"): "127.0.0.1",
        ("Streaming", "HTTP_STREAM_PORT"): http_stream_port,
        ("Streaming", "API_CORS_ALLOWED_ORIGINS"): [public_origin],
        ("Streaming", "API_ALLOWED_HOSTS"): [_origin_host_authority(public_origin)],
        ("Streaming", "API_AUTH_MODE"): "machine_bearer",
        ("Streaming", "API_SYSTEM_RESTART_POLICY"): "local_only",
        ("Streaming", "API_BEARER_TOKEN_FILE"): str(token_file),
        ("Streaming", "API_SECURITY_AUDIT_ENABLED"): True,
        ("SmartTracker", "SMART_TRACKER_MODEL_TRUST_POLICY"): "digest_required",
        ("GStreamer", "ENABLE_GSTREAMER_STREAM"): False,
        ("GStreamer", "GSTREAMER_HOST"): "127.0.0.1",
        ("GStreamer", "GSTREAMER_PORT"): QGC_DEFAULT_UDP_H264_PORT,
    }


def _profile_unsafe_demo_lan_media_only(
    args: argparse.Namespace,
) -> dict[tuple[str, ...], Any]:
    if not args.lan_host:
        raise ProfileError(
            "unsafe_demo_lan_media_only requires --lan-host <pixeagle-lan-ip-or-hostname>."
        )

    lan_host = _normalize_lan_host(
        args.lan_host,
        allow_public_http_demo=args.allow_public_http_demo,
    )
    http_stream_port = _normalize_port(args.http_stream_port, "--http-stream-port")
    dashboard_port = _normalize_port(args.dashboard_port, "--dashboard-port")
    args._unsafe_media_origin_host = lan_host["origin_host"]
    args._unsafe_media_http_stream_port = http_stream_port
    args._unsafe_media_dashboard_port = dashboard_port
    args._unsafe_media_public_http = lan_host["public_http_demo"]

    remote_origins = [
        f"http://{lan_host['origin_host']}:{dashboard_port}",
        f"http://{lan_host['origin_host']}:{http_stream_port}",
    ]
    cors_origins = list(dict.fromkeys([*LOOPBACK_CORS_ORIGINS, *remote_origins]))

    return {
        ("Streaming", "API_EXPOSURE_MODE"): "trusted_lan_legacy",
        ("Streaming", "HTTP_STREAM_HOST"): "0.0.0.0",
        ("Streaming", "HTTP_STREAM_PORT"): http_stream_port,
        ("Streaming", "API_CORS_ALLOWED_ORIGINS"): cors_origins,
        ("Streaming", "API_ALLOWED_HOSTS"): [lan_host["allowed_host"]],
        ("Streaming", "API_AUTH_MODE"): "local_compat",
        ("Streaming", "API_SYSTEM_RESTART_POLICY"): "local_only",
        ("Streaming", "API_BEARER_TOKEN_FILE"): "",
        ("Streaming", "API_SESSION_USER_FILE"): "",
        ("Streaming", "ALLOW_UNAUTHENTICATED_MEDIA_STREAMING"): True,
        ("Streaming", "API_SECURITY_AUDIT_ENABLED"): True,
        ("GStreamer", "ENABLE_GSTREAMER_STREAM"): False,
        ("GStreamer", "GSTREAMER_HOST"): "127.0.0.1",
        ("GStreamer", "GSTREAMER_PORT"): QGC_DEFAULT_UDP_H264_PORT,
    }


def _profile_deferred(profile_name: str, reason: str) -> Callable[[argparse.Namespace], dict[tuple[str, ...], Any]]:
    def _raise(_: argparse.Namespace) -> dict[tuple[str, ...], Any]:
        raise ProfileError(
            f"{profile_name} is defined but not automated by this tool yet. {reason}"
        )

    return _raise


PROFILES: dict[str, Profile] = {
    "local_dev": Profile(
        name="local_dev",
        status="supported",
        description="Same-host dashboard/API development with loopback backend access.",
        applier=_profile_local_dev,
    ),
    "follower_command_preview": Profile(
        name="follower_command_preview",
        status="supported_lab",
        description=(
            "Explicit video-file local follower test; records local "
            "CommandIntent values while keeping the PX4 command inhibit active."
        ),
        applier=_profile_follower_command_preview,
    ),
    "beginner_lab": Profile(
        name="beginner_lab",
        status="supported_lab",
        description=(
            "Same-host beginner demo with recorded video, classic tracking, "
            "and a local-only follower test that cannot command PX4."
        ),
        applier=_profile_beginner_lab,
    ),
    "field_qgc_video": Profile(
        name="field_qgc_video",
        status="supported",
        description=(
            "Send H.264/RTP/UDP video to QGroundControl while keeping the "
            "PixEagle backend loopback-only."
        ),
        applier=_profile_field_qgc_video,
    ),
    "demo_lan_browser": Profile(
        name="demo_lan_browser",
        status="supported",
        description=(
            "Lab LAN browser demo with generated browser_session credentials "
            "and exact Host/CORS allowlists."
        ),
        applier=_profile_demo_lan_browser,
    ),
    "production_remote": Profile(
        name="production_remote",
        status="supported_guarded",
        description=(
            "Generate loopback backend/browser-session config for an external "
            "TLS reverse proxy and exact Host/CORS allowlists."
        ),
        applier=_profile_production_remote,
    ),
    "qgc_direct_media": Profile(
        name="qgc_direct_media",
        status="supported_guarded",
        description=(
            "Generate a media:read bearer profile for QGC HTTP MJPEG/WebSocket "
            "video behind an external HTTPS/WSS reverse proxy."
        ),
        applier=_profile_qgc_direct_media,
    ),
    "unsafe_demo_lan_media_only": Profile(
        name="unsafe_demo_lan_media_only",
        status="supported_unsafe",
        description=(
            "Explicit anonymous HTTP/WS media-only lab exception; never a "
            "dashboard/control profile and never default."
        ),
        applier=_profile_unsafe_demo_lan_media_only,
    ),
}


def _load_yaml(path: Path) -> CommentedMap:
    yaml = YAML()
    yaml.preserve_quotes = True
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.load(handle)
    if not isinstance(data, CommentedMap):
        raise ProfileError(f"{path} does not contain a YAML mapping.")
    return data


def _normalize_port(value: int, flag_name: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ProfileError(f"{flag_name} must be an integer in the range 1..65535.") from exc
    if port < 1 or port > 65535:
        raise ProfileError(f"{flag_name} must be in the range 1..65535.")
    return port


def _hostname_is_valid(hostname: str) -> bool:
    trimmed = hostname.rstrip(".")
    if not trimmed or len(trimmed) > 253:
        return False
    return all(HOSTNAME_PATTERN.match(label) for label in trimmed.split("."))


def _hostname_is_lan_scoped(hostname: str) -> bool:
    trimmed = hostname.rstrip(".")
    return "." not in trimmed or trimmed.endswith((".local", ".lan"))


def _address_is_demo_scope(address: Any) -> bool:
    return any(address in network for network in ALLOWED_DEMO_IP_NETWORKS)


def _address_is_disallowed_production_host(address: Any) -> bool:
    return any(address in network for network in DISALLOWED_PRODUCTION_HOST_NETWORKS)


def _normalize_session_username(value: str, flag_name: str) -> str:
    username = str(value or "").strip().lower()
    if not username:
        raise ProfileError(f"{flag_name} must not be empty.")
    return username


def _normalize_machine_identifier(value: str, flag_name: str) -> str:
    identifier = str(value or "").strip().lower()
    if not MACHINE_IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ProfileError(
            f"{flag_name} must be 1..64 lowercase letters, digits, dots, underscores, or hyphens."
        )
    return identifier


def _normalize_lan_host(
    value: str,
    *,
    allow_public_http_demo: bool = False,
) -> dict[str, str]:
    raw = str(value or "").strip()
    if not raw:
        raise ProfileError("--lan-host must not be empty.")
    if raw == "*" or "://" in raw or "/" in raw or "@" in raw or "?" in raw or "#" in raw:
        raise ProfileError(
            "--lan-host must be a hostname or IP literal without wildcard, scheme, path, query, fragment, or credentials."
        )
    if "%" in raw:
        raise ProfileError(
            "--lan-host must not include IPv6 zone identifiers; use an IPv6 ULA address or local hostname instead."
        )

    if raw.startswith("["):
        try:
            parsed_url = urlsplit(f"//{raw}")
        except ValueError as exc:
            raise ProfileError(f"--lan-host is not a valid hostname or IP literal: {value!r}") from exc
        try:
            parsed_port = parsed_url.port
        except ValueError as exc:
            raise ProfileError("--lan-host must not include a port; use --http-stream-port if needed.") from exc
        if parsed_port is not None:
            raise ProfileError("--lan-host must not include a port; use --http-stream-port if needed.")
        if (
            parsed_url.username
            or parsed_url.password
            or parsed_url.path not in {"", None}
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ProfileError(
                "--lan-host must be a hostname or IP literal without credentials, path, query, or fragment."
            )
        host = parsed_url.hostname if parsed_url.hostname else raw.strip("[]")
    else:
        try:
            ip_address(raw)
        except ValueError:
            try:
                parsed_url = urlsplit(f"//{raw}")
            except ValueError as exc:
                raise ProfileError(f"--lan-host is not a valid hostname or IP literal: {value!r}") from exc
            try:
                parsed_port = parsed_url.port
            except ValueError as exc:
                raise ProfileError("--lan-host must not include a port; use --http-stream-port if needed.") from exc
            if parsed_port is not None:
                raise ProfileError("--lan-host must not include a port; use --http-stream-port if needed.")
            if (
                parsed_url.username
                or parsed_url.password
                or parsed_url.path not in {"", None}
                or parsed_url.query
                or parsed_url.fragment
            ):
                raise ProfileError(
                    "--lan-host must be a hostname or IP literal without credentials, path, query, or fragment."
                )
            host = parsed_url.hostname if parsed_url.hostname else raw.strip("[]")
        else:
            host = raw
    host = str(host or "").strip().lower()
    if not host or any(char.isspace() for char in host):
        raise ProfileError("--lan-host must be a single hostname or IP literal.")

    try:
        address = ip_address(host)
    except ValueError:
        if host == "localhost" or host in UNSPECIFIED_BIND_HOSTS:
            raise ProfileError("--lan-host must identify the PixEagle LAN address, not loopback or wildcard bind hosts.")
        if not _hostname_is_valid(host):
            raise ProfileError(f"--lan-host is not a valid hostname or IP literal: {value!r}")
        if not _hostname_is_lan_scoped(host) and not allow_public_http_demo:
            raise ProfileError(
                "--lan-host hostnames must be single-label or end with .local/.lan for demo_lan_browser."
            )
        return {
            "allowed_host": host.rstrip("."),
            "origin_host": host.rstrip("."),
            "public_http_demo": not _hostname_is_lan_scoped(host),
        }

    if address.is_loopback or address.is_unspecified:
        raise ProfileError("--lan-host must identify the PixEagle LAN address, not loopback or wildcard bind hosts.")
    if not _address_is_demo_scope(address):
        if not allow_public_http_demo:
            raise ProfileError(
                "--lan-host must be an RFC1918 private, link-local, IPv6 ULA, or shared private-overlay address for demo_lan_browser."
            )
        if (
            address.is_multicast
            or address.is_reserved
            or address.is_link_local
            or _address_is_disallowed_production_host(address)
        ):
            raise ProfileError(
                "--lan-host public HTTP demo override requires a routable host/IP, not multicast, link-local, documentation, or reserved address space."
            )
    allowed_host = address.compressed
    origin_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return {
        "allowed_host": allowed_host,
        "origin_host": origin_host,
        "public_http_demo": not _address_is_demo_scope(address),
    }


def _extract_host_literal(value: str, flag_name: str, *, allow_port: bool) -> tuple[str, int | None]:
    raw = str(value or "").strip()
    if not raw:
        raise ProfileError(f"{flag_name} must not be empty.")
    if raw == "*" or "://" in raw or "/" in raw or "@" in raw or "?" in raw or "#" in raw:
        raise ProfileError(
            f"{flag_name} must be a hostname or IP literal without wildcard, scheme, path, query, fragment, or credentials."
        )
    if "%" in raw:
        raise ProfileError(
            f"{flag_name} must not include IPv6 zone identifiers; use a stable hostname, IPv6 ULA, or routable address instead."
        )

    if raw.startswith("["):
        parse_value = f"//{raw}"
    else:
        try:
            ip_address(raw)
        except ValueError:
            parse_value = f"//{raw}"
        else:
            host = raw
            return host, None

    try:
        parsed_url = urlsplit(parse_value)
    except ValueError as exc:
        raise ProfileError(f"{flag_name} is not a valid hostname or IP literal: {value!r}") from exc
    try:
        parsed_port = parsed_url.port
    except ValueError as exc:
        raise ProfileError(f"{flag_name} contains an invalid port.") from exc
    if parsed_port is not None and not allow_port:
        raise ProfileError(f"{flag_name} must not include a port; use --public-origin if needed.")
    if (
        parsed_url.username
        or parsed_url.password
        or parsed_url.path not in {"", None}
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ProfileError(
            f"{flag_name} must be a hostname or IP literal without credentials, path, query, or fragment."
        )
    host = parsed_url.hostname if parsed_url.hostname else raw.strip("[]")
    return str(host or ""), parsed_port


def _normalize_public_host(value: str, flag_name: str = "--public-host") -> dict[str, str]:
    host, _ = _extract_host_literal(value, flag_name, allow_port=False)
    host = str(host or "").strip().lower()
    if not host or any(char.isspace() for char in host):
        raise ProfileError(f"{flag_name} must be a single hostname or IP literal.")

    try:
        address = ip_address(host)
    except ValueError:
        if host == "localhost" or host in UNSPECIFIED_BIND_HOSTS:
            raise ProfileError(
                f"{flag_name} must identify the remote TLS/reverse-proxy host, not loopback or wildcard bind hosts."
            )
        if not _hostname_is_valid(host):
            raise ProfileError(f"{flag_name} is not a valid hostname or IP literal: {value!r}")
        normalized_host = host.rstrip(".")
        return {"allowed_host": normalized_host, "origin_host": normalized_host}

    if address.is_loopback or address.is_unspecified:
        raise ProfileError(
            f"{flag_name} must identify the remote TLS/reverse-proxy host, not loopback or wildcard bind hosts."
        )
    if (
        address.is_multicast
        or address.is_link_local
        or _address_is_disallowed_production_host(address)
    ):
        raise ProfileError(
            f"{flag_name} must be a stable TLS endpoint, not multicast, link-local, or documentation/reserved address space."
        )
    allowed_host = address.compressed
    origin_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return {"allowed_host": allowed_host, "origin_host": origin_host}


def _normalize_public_origin(value: str | None, public_host: dict[str, str]) -> str:
    if not value:
        return f"https://{public_host['origin_host']}"

    raw = str(value).strip()
    try:
        parsed_url = urlsplit(raw)
    except ValueError as exc:
        raise ProfileError(f"--public-origin is not a valid HTTPS origin: {value!r}") from exc
    try:
        parsed_port = parsed_url.port
    except ValueError as exc:
        raise ProfileError("--public-origin contains an invalid port.") from exc

    if parsed_url.scheme.lower() != "https":
        raise ProfileError("--public-origin must use https://.")
    if not parsed_url.hostname:
        raise ProfileError("--public-origin must include a hostname or IP literal.")
    if (
        parsed_url.username
        or parsed_url.password
        or parsed_url.path not in {"", "/"}
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ProfileError(
            "--public-origin must be an HTTPS origin only, without credentials, path, query, or fragment."
        )

    origin_host = _normalize_public_host(parsed_url.hostname, "--public-origin")
    if origin_host["allowed_host"] != public_host["allowed_host"]:
        raise ProfileError("--public-origin host must match --public-host.")

    if parsed_port in {None, 443}:
        return f"https://{origin_host['origin_host']}"
    return f"https://{origin_host['origin_host']}:{parsed_port}"


def _origin_host_authority(origin: str) -> str:
    parsed = urlsplit(origin)
    host = str(parsed.hostname or "").lower()
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80
    if ":" in host:
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def _resolve_output_path(path_value: Path) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _canonical_path(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _validate_distinct_output_paths(paths: dict[str, Path]) -> None:
    seen: dict[Path, tuple[str, Path]] = {}
    for label, raw_path in paths.items():
        expanded_path = Path(raw_path).expanduser()
        if expanded_path.is_symlink():
            raise ProfileError(f"{label} must not be a symbolic link: {expanded_path}")
        path = _canonical_path(expanded_path)
        previous = seen.get(path)
        if previous is not None:
            raise ProfileError(
                f"{label} must not resolve to the same path as {previous[0]}: {path}"
            )
        for previous_label, previous_path in seen.values():
            try:
                same_file = (
                    expanded_path.exists()
                    and previous_path.exists()
                    and expanded_path.samefile(previous_path)
                )
            except OSError as exc:
                raise ProfileError(
                    f"failed to compare output paths {expanded_path} and {previous_path}: {exc}"
                ) from exc
            if same_file:
                raise ProfileError(
                    f"{label} must not reference the same file as {previous_label}: {expanded_path}"
                )
        seen[path] = (label, expanded_path)


def _serialize_yaml(data: CommentedMap) -> bytes:
    """Serialize a profile result and fail closed if a round-trip is invalid.

    ruamel's comment-preserving emitter can retain stale line metadata after a
    profile changes the length of a sequence. In that narrow case it can join
    adjacent mapping keys. Preserve comments when the round-trip is valid; use
    a plain deterministic representation as the safe fallback.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    buffer = io.StringIO()
    yaml.dump(data, buffer)
    serialized = buffer.getvalue()

    validator = YAML(typ="safe")
    try:
        validator.load(serialized)
        return serialized.encode("utf-8")
    except Exception:
        pass

    def to_plain(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): to_plain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [to_plain(item) for item in value]
        # Round-trip YAML uses ScalarInt/ScalarFloat subclasses for values
        # loaded from the commented template. The safe representer does not
        # register those subclasses, so normalize them to builtin scalars.
        if isinstance(value, bool):
            return bool(value)
        if isinstance(value, int):
            return int(value)
        if isinstance(value, float):
            return float(value)
        if isinstance(value, str):
            return str(value)
        return value

    fallback_yaml = YAML(typ="safe")
    fallback_yaml.default_flow_style = False
    fallback_buffer = io.StringIO()
    fallback_yaml.dump(to_plain(data), fallback_buffer)
    fallback_serialized = fallback_buffer.getvalue()
    try:
        validator.load(fallback_serialized)
    except Exception as exc:
        raise ProfileError(f"profile serialization produced invalid YAML: {exc}") from exc
    return fallback_serialized.encode("utf-8")


def _snapshot_file(path: Path) -> FileSnapshot:
    try:
        if path.is_symlink():
            raise ProfileError(f"refusing to replace symbolic-link output path: {path}")
        if not path.exists():
            return FileSnapshot(path=path, existed=False, content=None, mode=None)
        if not path.is_file():
            raise ProfileError(f"output path exists but is not a regular file: {path}")
        stat_result = path.stat()
        return FileSnapshot(
            path=path,
            existed=True,
            content=path.read_bytes(),
            mode=stat_result.st_mode & 0o777,
        )
    except OSError as exc:
        raise ProfileError(f"failed to inspect output path {path}: {exc}") from exc


def _atomic_write_bytes(path: Path, content: bytes, *, mode: int) -> None:
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(temp_name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ProfileError(f"failed to write {path}: {exc}") from exc


def _next_backup_path(path: Path) -> Path:
    timestamp = strftime("%Y%m%d_%H%M%S")
    candidate = path.with_name(f"{path.name}.backup.{timestamp}")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.backup.{timestamp}.{suffix}")
        suffix += 1
    return candidate


def _apply_file(
    path: Path,
    content: bytes,
    *,
    mode: int,
    create_backup: bool,
    backup_mode: int | None = None,
) -> AppliedFile:
    snapshot = _snapshot_file(path)
    backup_path = None
    if snapshot.existed and create_backup:
        backup_path = _next_backup_path(path)
        _atomic_write_bytes(
            backup_path,
            snapshot.content or b"",
            mode=backup_mode if backup_mode is not None else (snapshot.mode or mode),
        )
    try:
        _atomic_write_bytes(path, content, mode=mode)
    except ProfileError:
        if backup_path is not None:
            try:
                backup_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return AppliedFile(snapshot=snapshot, backup_path=backup_path)


def _rollback_files(applied_files: list[AppliedFile]) -> list[str]:
    errors: list[str] = []
    for applied in reversed(applied_files):
        snapshot = applied.snapshot
        try:
            if snapshot.existed:
                _atomic_write_bytes(
                    snapshot.path,
                    snapshot.content or b"",
                    mode=snapshot.mode or 0o600,
                )
            else:
                snapshot.path.unlink(missing_ok=True)
            if applied.backup_path is not None:
                applied.backup_path.unlink(missing_ok=True)
        except (ProfileError, OSError) as exc:
            errors.append(f"{snapshot.path}: {exc}")
    return errors


def _set_nested(config: CommentedMap, key_path: tuple[str, ...], value: Any) -> Any:
    node: Any = config
    for key in key_path[:-1]:
        if key not in node or not isinstance(node[key], CommentedMap):
            node[key] = CommentedMap()
        node = node[key]
    leaf = key_path[-1]
    old_value = copy.deepcopy(node.get(leaf))
    node[leaf] = value
    return old_value


def _format_key(key_path: tuple[str, ...]) -> str:
    return ".".join(key_path)


def _build_plan(args: argparse.Namespace) -> tuple[CommentedMap, list[str]]:
    profile = PROFILES[args.profile]
    base_path = args.config if args.config.exists() else args.defaults
    config = _load_yaml(base_path)
    changes = profile.applier(args)

    summaries: list[str] = []
    for key_path, value in changes.items():
        old_value = _set_nested(config, key_path, value)
        summaries.append(f"{_format_key(key_path)}: {old_value!r} -> {value!r}")
    return config, summaries


def _write_config(args: argparse.Namespace, config: CommentedMap) -> tuple[Path | None, AppliedFile | None]:
    if args.dry_run:
        return None, None

    applied = _apply_file(
        args.config,
        _serialize_yaml(config),
        mode=0o600,
        create_backup=args.config.exists() and not args.no_backup,
    )
    return args.config, applied


def _write_generated_session_user_file(
    *,
    user_file: Path,
    username: str,
    role: str,
    rotate_credentials: bool,
) -> tuple[str, AppliedFile]:
    password = secrets.token_urlsafe(24)
    snapshot = _snapshot_file(user_file)
    try:
        user_record = make_browser_user_record(
            username=username,
            plaintext_password=password,
            role=role,
        )
        result = BrowserUserStore(user_file).replace_all(
            [user_record],
            create_if_missing=True,
            backup=user_file.exists() and rotate_credentials,
        )
    except BrowserUserStoreError as exc:
        raise ProfileError(
            f"failed to write browser-session user file: {exc}"
        ) from exc
    applied = AppliedFile(
        snapshot=snapshot,
        backup_path=result.backup_path,
    )
    return password, applied


def _write_generated_qgc_token_file(
    *,
    token_file: Path,
    token_id: str,
    token_subject: str,
    rotate_credentials: bool,
) -> tuple[str, AppliedFile]:
    plaintext_token = secrets.token_urlsafe(32)
    token_record = make_token_record(
        token_id=token_id,
        subject=token_subject,
        plaintext_token=plaintext_token,
        scopes=["media:read"],
    )
    payload = {"tokens": [token_record]}
    applied = _apply_file(
        token_file,
        (json.dumps(payload, indent=2) + "\n").encode("utf-8"),
        mode=0o600,
        create_backup=token_file.exists() and rotate_credentials,
        backup_mode=0o600,
    )
    return plaintext_token, applied


def _write_profile_artifacts(args: argparse.Namespace) -> tuple[list[str], list[AppliedFile]]:
    if args.profile == "field_qgc_video":
        return [
            "QGC UDP VIDEO: run 'make check-gstreamer-runtime' before relying on this profile.",
            (
                "QGC UDP VIDEO: the active OpenCV build must report GStreamer: YES, "
                "and a supported H.264 encoder plus RTP/UDP plugins must be installed."
            ),
            "QGC UDP VIDEO: local pipeline readiness does not prove receiver playback; confirm moving video in QGC.",
        ], []

    if args.profile == "demo_lan_browser":
        user_file: Path = args._demo_session_user_file
        handoff_file: Path | None = args._demo_credential_handoff_file
        if args.dry_run:
            summaries = [
                f"Would generate browser-session user file: {user_file}",
                "LAB ONLY: use this profile only on an isolated operator-approved LAN/private overlay without TLS.",
            ]
            if handoff_file is not None:
                summaries.append(f"Would write one-time demo credential handoff file: {handoff_file}")
            else:
                summaries.append("Would print the generated password once; plaintext is never written to disk.")
            if args._demo_public_http:
                summaries.append(
                    "TEMPORARY PUBLIC HTTP: explicit override enabled; credentials would cross the network without TLS."
                )
            return summaries, []

        password, applied = _write_generated_session_user_file(
            user_file=user_file,
            username=args._demo_username,
            role=args._demo_role,
            rotate_credentials=args._demo_rotate_credentials,
        )
        applied_files = [applied]

        if handoff_file is not None:
            handoff_payload = {
                "username": args._demo_username,
                "password": password,
                "role": args._demo_role,
                "dashboard_url": f"http://{args._demo_origin_host}:{args._demo_dashboard_port}",
                "backend_api_url": f"http://{args._demo_origin_host}:{args._demo_http_stream_port}",
                "authentication": "browser_session",
                "one_time_handoff": True,
                "security_boundary": (
                    "temporary public HTTP demo"
                    if args._demo_public_http
                    else "isolated LAN/private-overlay HTTP demo"
                ),
            }
            try:
                handoff_applied = _apply_file(
                    handoff_file,
                    (json.dumps(handoff_payload, indent=2) + "\n").encode("utf-8"),
                    mode=0o600,
                    create_backup=False,
                )
            except ProfileError as exc:
                rollback_errors = _rollback_files(applied_files)
                if rollback_errors:
                    raise ProfileError(
                        f"{exc}; credential rollback was incomplete: "
                        + "; ".join(rollback_errors)
                    ) from exc
                raise
            applied_files.append(handoff_applied)

        summaries = [
            f"Generated browser-session user file: {user_file}",
            f"Demo username: {args._demo_username}",
            (
                "Open the dashboard on the lab LAN/private overlay at "
                f"http://{args._demo_origin_host}:{args._demo_dashboard_port}"
            ),
            (
                "LAB ONLY: allow dashboard port "
                f"{args._demo_dashboard_port} and backend/API media port "
                f"{args._demo_http_stream_port} only from trusted demo devices."
            ),
            "LAB ONLY: do not use this HTTP profile for production or untrusted networks.",
        ]
        if handoff_file is not None:
            summaries.insert(2, f"Generated one-time demo credential handoff file: {handoff_file}")
            summaries.insert(
                3,
                "Read the password from that owner-only file; the runtime user file contains only the PBKDF2 hash.",
            )
        else:
            summaries.insert(2, f"Demo password: {password}")
            summaries.insert(3, "Store this password now; it is shown once and only the PBKDF2 hash was written.")
        if args._demo_role != "admin":
            summaries.append(
                "The initial account is not an administrator; use the host "
                "manage-browser-users.py recovery CLI to add an admin account."
            )
        if args._demo_public_http:
            summaries.append(
                "TEMPORARY PUBLIC HTTP: this override sends credentials over plain HTTP; stop the demo and rotate/delete credentials after testing."
            )
        return summaries, applied_files

    if args.profile == "qgc_direct_media":
        token_file = args._qgc_token_file
        handoff_file = args._qgc_handoff_file
        proxy_target = f"http://127.0.0.1:{args._qgc_http_stream_port}"
        http_url = f"{args._qgc_public_origin}/pixeagle-api/video_feed"
        websocket_url = (
            f"wss://{urlsplit(args._qgc_public_origin).netloc}"
            "/pixeagle-api/ws/video_feed"
        )
        if args.dry_run:
            return [
                f"Would generate owner-only QGC bearer token file: {token_file}",
                f"Would write one-time QGC credential handoff file: {handoff_file}",
                (
                    "QGC DIRECT MEDIA: configure an external HTTPS/WSS reverse proxy "
                    f"for {args._qgc_public_origin}; PixEagle remains loopback at {proxy_target}."
                ),
                f"QGC HTTP MJPEG URL: {http_url}",
                f"QGC WebSocket JPEG URL: {websocket_url}",
                "This profile does not install TLS/proxy/firewall services or prove QGC playback.",
            ], []

        applied_files: list[AppliedFile] = []
        plaintext_token, token_applied = _write_generated_qgc_token_file(
            token_file=token_file,
            token_id=args._qgc_token_id,
            token_subject=args._qgc_token_subject,
            rotate_credentials=args.rotate_qgc_token,
        )
        applied_files.append(token_applied)

        handoff_payload = {
            "token_id": args._qgc_token_id,
            "subject": args._qgc_token_subject,
            "bearer_token": plaintext_token,
            "scopes": ["media:read"],
            "authentication": "Bearer token",
            "origin": args._qgc_public_origin,
            "http_mjpeg_url": http_url,
            "websocket_jpeg_url": websocket_url,
            "one_time_handoff": True,
        }
        try:
            handoff_applied = _apply_file(
                handoff_file,
                (json.dumps(handoff_payload, indent=2) + "\n").encode("utf-8"),
                mode=0o600,
                create_backup=False,
            )
        except ProfileError as exc:
            rollback_errors = _rollback_files(applied_files)
            if rollback_errors:
                raise ProfileError(
                    f"{exc}; credential rollback was incomplete: "
                    + "; ".join(rollback_errors)
                ) from exc
            raise
        applied_files.append(handoff_applied)

        return [
            f"Generated QGC media bearer token file: {token_file}",
            f"Generated one-time QGC credential handoff file: {handoff_file}",
            "Transfer the QGC settings/token securely, then delete the handoff file.",
            f"QGC HTTP MJPEG URL: {http_url}",
            f"QGC WebSocket JPEG URL: {websocket_url}",
            f"QGC Origin: {args._qgc_public_origin}",
            (
                "QGC DIRECT MEDIA: PUBLIC_HOST is the QGC URL/proxy Host "
                "authority, not the GCS client/source IP."
            ),
            (
                "QGC DIRECT MEDIA: proxy /pixeagle-api to "
                f"{proxy_target}, preserve Host and Origin, and keep backend port "
                f"{args._qgc_http_stream_port} off untrusted networks."
            ),
            "QGC DIRECT MEDIA: strict TLS remains required; use a deployment CA file in QGC when the certificate is not publicly trusted.",
        ], applied_files

    if args.profile == "unsafe_demo_lan_media_only":
        media_http_url = (
            f"http://{args._unsafe_media_origin_host}:"
            f"{args._unsafe_media_http_stream_port}/video_feed"
        )
        media_ws_url = (
            f"ws://{args._unsafe_media_origin_host}:"
            f"{args._unsafe_media_http_stream_port}/ws/video_feed"
        )
        summaries = [
            "UNSAFE LAB MEDIA ONLY: anonymous access is enabled only for /video_feed and /ws/video_feed.",
            f"HTTP MJPEG URL: {media_http_url}",
            f"WebSocket JPEG URL: {media_ws_url}",
            (
                "UNSAFE LAB MEDIA ONLY: LAN_HOST is the PixEagle URL Host "
                "authority, not the GCS client/source IP."
            ),
            (
                "Dashboard/control/config/log/API routes are not made anonymous; "
                "use demo_lan_browser or production_remote when remote dashboard access is needed."
            ),
            (
                "LAB ONLY: allow backend/media port "
                f"{args._unsafe_media_http_stream_port} only from trusted demo devices."
            ),
        ]
        if args._unsafe_media_public_http:
            summaries.append(
                "TEMPORARY PUBLIC HTTP: explicit override enabled; video is visible to anyone who can reach the URL."
            )
        else:
            summaries.append(
                "LAB ONLY: do not use this profile on untrusted LANs, shared field networks, or production remote links."
            )
        return summaries, []

    if args.profile == "production_remote":
        user_file = args._production_session_user_file
        proxy_target = f"http://127.0.0.1:{args._production_http_stream_port}"
        if args.dry_run:
            return [
                f"Would generate production browser-session user file: {user_file}",
                (
                    f"Would write one-time credential handoff file: {args._production_credential_handoff_file}"
                    if args._production_credential_handoff_file is not None
                    else "Would print the generated password once to the acknowledged interactive/stdout channel."
                ),
                (
                    "PRODUCTION REMOTE: configure an external HTTPS/WSS reverse proxy for "
                    f"{args._production_origin}; PixEagle backend remains loopback at {proxy_target}."
                ),
                (
                    "PRODUCTION REMOTE: serve the dashboard under /pixeagle and proxy "
                    f"/pixeagle-api to {proxy_target}, or document an equivalent reviewed same-origin path."
                ),
                "This profile does not install a proxy, open firewall ports, deploy services, or prove production readiness.",
            ], []

        applied_files: list[AppliedFile] = []
        password, applied = _write_generated_session_user_file(
            user_file=user_file,
            username=args._production_username,
            role=args._production_role,
            rotate_credentials=args.rotate_session_credentials,
        )
        applied_files.append(applied)

        handoff_file = args._production_credential_handoff_file
        if handoff_file is not None:
            handoff_payload = {
                "username": args._production_username,
                "password": password,
                "role": args._production_role,
                "one_time_handoff": True,
            }
            try:
                handoff_applied = _apply_file(
                    handoff_file,
                    (json.dumps(handoff_payload, indent=2) + "\n").encode("utf-8"),
                    mode=0o600,
                    create_backup=False,
                )
            except ProfileError as exc:
                rollback_errors = _rollback_files(applied_files)
                if rollback_errors:
                    raise ProfileError(
                        f"{exc}; credential rollback was incomplete: "
                        + "; ".join(rollback_errors)
                    ) from exc
                raise
            applied_files.append(handoff_applied)

        summaries = [
            f"Generated production browser-session user file: {user_file}",
            f"Production username: {args._production_username}",
            f"Production remote origin: {args._production_origin}",
            (
                "PRODUCTION REMOTE: configure HTTPS/WSS reverse proxy to serve the dashboard under "
                f"/pixeagle and proxy /pixeagle-api to {proxy_target}."
            ),
            (
                "PRODUCTION REMOTE: preserve Host and Origin, keep backend port "
                f"{args._production_http_stream_port} off untrusted networks, and collect deployment evidence before claiming readiness."
            ),
        ]
        if handoff_file is not None:
            summaries.insert(
                2,
                f"Generated one-time credential handoff file: {handoff_file}",
            )
            summaries.insert(
                3,
                "Transfer the credential securely, then delete the handoff file; the runtime user file contains only the PBKDF2 hash.",
            )
        else:
            summaries.insert(2, f"Production password: {password}")
            summaries.insert(
                3,
                "Store this password now; it is shown once and only the PBKDF2 hash was written.",
            )
        if args._production_role != "admin":
            summaries.append(
                "The initial account is not an administrator; use the host "
                "manage-browser-users.py recovery CLI to add an admin account."
            )
        return summaries, applied_files

    return [], []


def _print_profiles() -> None:
    print("Available PixEagle setup profiles:")
    for profile in PROFILES.values():
        print(f"  {profile.name:<28} {profile.status:<22} {profile.description}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply a PixEagle setup profile to configs/config.yaml."
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        help="Profile to apply. Use --list-profiles to see status and purpose.",
    )
    parser.add_argument(
        "--defaults",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Default config source. Defaults to configs/config_default.yaml.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=RUNTIME_CONFIG_PATH,
        help="Runtime config destination. Defaults to configs/config.yaml.",
    )
    parser.add_argument(
        "--gcs-host",
        help="Ground-station host/IP for the field_qgc_video profile.",
    )
    parser.add_argument(
        "--gstreamer-port",
        type=int,
        default=QGC_DEFAULT_UDP_H264_PORT,
        help="QGC UDP h.264 receive port. Default: 5600.",
    )
    parser.add_argument(
        "--lan-host",
        help=(
            "PixEagle LAN hostname/IP used by browser clients for the "
            "demo_lan_browser or unsafe_demo_lan_media_only profile."
        ),
    )
    parser.add_argument(
        "--public-host",
        help=(
            "Public or deployment-stable TLS hostname/IP used by production_remote "
            "or qgc_direct_media. Do not include a scheme, path, or port."
        ),
    )
    parser.add_argument(
        "--public-origin",
        help=(
            "Optional HTTPS origin for production_remote or qgc_direct_media. "
            "Defaults to https://<public-host>; may include a port."
        ),
    )
    parser.add_argument(
        "--bearer-token-file",
        type=Path,
        default=DEFAULT_QGC_TOKEN_FILE,
        help=(
            "Owner-only hashed bearer-token JSON generated for qgc_direct_media. "
            "Default: configs/secrets/qgc-media-tokens.json."
        ),
    )
    parser.add_argument(
        "--qgc-handoff-file",
        type=Path,
        default=DEFAULT_QGC_HANDOFF_FILE,
        help=(
            "Owner-only one-time plaintext QGC media credential handoff JSON. "
            "Delete after configuring QGC."
        ),
    )
    parser.add_argument(
        "--token-id",
        default=DEFAULT_QGC_TOKEN_ID,
        help="Machine-token identifier for qgc_direct_media.",
    )
    parser.add_argument(
        "--token-subject",
        default=DEFAULT_QGC_TOKEN_SUBJECT,
        help="Machine-token subject for qgc_direct_media.",
    )
    parser.add_argument(
        "--rotate-qgc-token",
        action="store_true",
        help="Rotate existing qgc_direct_media token and handoff files.",
    )
    parser.add_argument(
        "--http-stream-port",
        type=int,
        default=DEFAULT_HTTP_STREAM_PORT,
        help="Backend API/streaming port for LAN demo profiles. Default: 5077.",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=DEFAULT_DASHBOARD_PORT,
        help="Dashboard port for LAN demo CORS guidance. Default: 3040.",
    )
    parser.add_argument(
        "--session-user-file",
        type=Path,
        default=DEFAULT_DEMO_USER_FILE,
        help=(
            "External browser-session user JSON for demo_lan_browser or production_remote. "
            "Default: configs/secrets/demo-browser-users.json."
        ),
    )
    parser.add_argument(
        "--session-username",
        help=(
            "Generated browser-session username for profiles that create user "
            "records. Overrides the demo-specific username when supplied."
        ),
    )
    parser.add_argument(
        "--session-role",
        choices=["viewer", "operator", "admin"],
        help="Role for generated browser-session users. Default: profile-specific.",
    )
    parser.add_argument(
        "--credential-handoff-file",
        type=Path,
        help=(
            "Optional 0600 JSON file for one-time generated browser credentials. "
            "Required for non-interactive production_remote use unless stdout disclosure is explicitly acknowledged."
        ),
    )
    parser.add_argument(
        "--show-generated-password",
        action="store_true",
        help=(
            "Explicitly allow production_remote to print the generated password "
            "to stdout. Avoid this in CI or captured orchestration logs."
        ),
    )
    parser.add_argument(
        "--demo-username",
        default="pixeagle-demo",
        help="Generated browser-session username for demo_lan_browser.",
    )
    parser.add_argument(
        "--demo-role",
        choices=["viewer", "operator", "admin"],
        default="admin",
        help="Role for the generated demo_lan_browser user. Default: admin.",
    )
    parser.add_argument(
        "--rotate-demo-credentials",
        action="store_true",
        help=(
            "Replace an existing demo_lan_browser user file after creating a "
            "timestamped backup."
        ),
    )
    parser.add_argument(
        "--allow-public-http-demo",
        action="store_true",
        help=(
            "Explicitly allow demo_lan_browser to use a public host/IP for a temporary plain-HTTP demo. "
            "Never use this for production."
        ),
    )
    parser.add_argument(
        "--rotate-session-credentials",
        action="store_true",
        help=(
            "Replace an existing generated browser-session user file after "
            "creating a timestamped backup."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without writing configs/config.yaml.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not back up an existing runtime config before writing.",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List profile names, status, and purpose, then exit.",
    )
    args = parser.parse_args(argv)
    if args.list_profiles:
        return args
    if not args.profile:
        parser.error("--profile is required unless --list-profiles is used")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.list_profiles:
        _print_profiles()
        return 0

    if not args.defaults.exists():
        print(f"ERROR: default config not found: {args.defaults}", file=sys.stderr)
        return 2

    try:
        config, summaries = _build_plan(args)
        artifact_summaries, applied_artifacts = _write_profile_artifacts(args)
        try:
            written, _config_applied = _write_config(args, config)
        except ProfileError as exc:
            rollback_errors = _rollback_files(applied_artifacts)
            if rollback_errors:
                raise ProfileError(
                    f"{exc}; rollback was incomplete: {'; '.join(rollback_errors)}"
                ) from exc
            raise
    except ProfileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    action = "Dry run" if args.dry_run else "Applied"
    print(f"{action}: PixEagle setup profile {args.profile}")
    for summary in summaries:
        print(f"  - {summary}")
    for summary in artifact_summaries:
        print(f"  - {summary}")
    if written is not None:
        print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
