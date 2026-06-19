#!/usr/bin/env python3
"""Apply PixEagle setup profiles to a local runtime config.

The checked-in `configs/config_default.yaml` remains the source of truth.
This tool creates or updates `configs/config.yaml` only when the operator
explicitly chooses a profile that needs local host-specific values.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import secrets
import sys
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

from classes.api_auth_runtime import make_user_record

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "config_default.yaml"
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "configs" / "config.yaml"
DEFAULT_DEMO_USER_FILE = PROJECT_ROOT / "configs" / "secrets" / "demo-browser-users.json"
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


class ProfileError(ValueError):
    """Raised when a profile request is incomplete or unsafe."""


@dataclass(frozen=True)
class Profile:
    name: str
    status: str
    description: str
    applier: Callable[[argparse.Namespace], dict[tuple[str, ...], Any]]


def _profile_local_dev(args: argparse.Namespace) -> dict[tuple[str, ...], Any]:
    return {
        ("Streaming", "API_EXPOSURE_MODE"): "local_only",
        ("Streaming", "HTTP_STREAM_HOST"): "127.0.0.1",
        ("Streaming", "API_CORS_ALLOWED_ORIGINS"): LOOPBACK_CORS_ORIGINS,
        ("Streaming", "API_ALLOWED_HOSTS"): [],
        ("Streaming", "API_AUTH_MODE"): "local_compat",
        ("GStreamer", "ENABLE_GSTREAMER_STREAM"): False,
        ("GStreamer", "GSTREAMER_HOST"): "127.0.0.1",
        ("GStreamer", "GSTREAMER_PORT"): QGC_DEFAULT_UDP_H264_PORT,
    }


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
    lan_host = _normalize_lan_host(args.lan_host)
    http_stream_port = _normalize_port(args.http_stream_port, "--http-stream-port")
    dashboard_port = _normalize_port(args.dashboard_port, "--dashboard-port")
    user_file = _resolve_output_path(args.session_user_file)
    username = str(args.demo_username).strip().lower()
    if not username:
        raise ProfileError("--demo-username must not be empty.")

    if user_file.exists() and not args.rotate_demo_credentials and not args.dry_run:
        raise ProfileError(
            f"session user file already exists: {user_file}. "
            "Pass --rotate-demo-credentials to replace it after saving the old password."
        )

    args._demo_lan_host = lan_host["allowed_host"]
    args._demo_origin_host = lan_host["origin_host"]
    args._demo_session_user_file = user_file
    args._demo_http_stream_port = http_stream_port
    args._demo_dashboard_port = dashboard_port
    args._demo_username = username

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
        ("Streaming", "API_SESSION_USER_FILE"): str(user_file),
        ("Streaming", "API_SESSION_COOKIE_SECURE"): False,
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
        status="defined_not_automated",
        description=(
            "Hardened remote operator profile with TLS, durable credentials, "
            "exact Host/CORS allowlists, and audit evidence."
        ),
        applier=_profile_deferred(
            "production_remote",
            "Production remote access remains gated on TLS/operator hardening, "
            "credential rollout, adversarial auth/media tests, and evidence."
        ),
    ),
    "unsafe_demo_lan_media_only": Profile(
        name="unsafe_demo_lan_media_only",
        status="not_supported",
        description=(
            "Future explicit anonymous media-only lab exception; never a "
            "dashboard/control profile and never default."
        ),
        applier=_profile_deferred(
            "unsafe_demo_lan_media_only",
            "PixEagle does not currently provide anonymous remote backend "
            "media; use field_qgc_video or an SSH tunnel."
        ),
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


def _normalize_lan_host(value: str) -> dict[str, str]:
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
        if not _hostname_is_lan_scoped(host):
            raise ProfileError(
                "--lan-host hostnames must be single-label or end with .local/.lan for demo_lan_browser."
            )
        return {"allowed_host": host.rstrip("."), "origin_host": host.rstrip(".")}

    if address.is_loopback or address.is_unspecified:
        raise ProfileError("--lan-host must identify the PixEagle LAN address, not loopback or wildcard bind hosts.")
    if not _address_is_demo_scope(address):
        raise ProfileError(
            "--lan-host must be an RFC1918 private, link-local, IPv6 ULA, or shared private-overlay address for demo_lan_browser."
        )
    allowed_host = address.compressed
    origin_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return {"allowed_host": allowed_host, "origin_host": origin_host}


def _resolve_output_path(path_value: Path) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _dump_yaml(path: Path, data: CommentedMap) -> None:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle)


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


def _write_config(args: argparse.Namespace, config: CommentedMap) -> Path | None:
    if args.dry_run:
        return None

    if args.config.exists() and not args.no_backup:
        backup = args.config.with_name(
            f"{args.config.name}.backup.{strftime('%Y%m%d_%H%M%S')}"
        )
        backup.write_bytes(args.config.read_bytes())
    _dump_yaml(args.config, config)
    return args.config


def _write_profile_artifacts(args: argparse.Namespace) -> list[str]:
    if args.profile != "demo_lan_browser":
        return []

    user_file: Path = args._demo_session_user_file
    if args.dry_run:
        return [
            f"Would generate browser-session user file: {user_file}",
            "Would print the generated password once; plaintext is never written to disk.",
            "LAB ONLY: use this profile only on an isolated operator-approved LAN/private overlay without TLS.",
        ]

    if user_file.exists() and args.rotate_demo_credentials:
        backup = user_file.with_name(
            f"{user_file.name}.backup.{strftime('%Y%m%d_%H%M%S')}"
        )
        backup.write_bytes(user_file.read_bytes())

    password = secrets.token_urlsafe(24)
    username = args._demo_username
    try:
        user_record = make_user_record(
            username=username,
            plaintext_password=password,
            role=args.demo_role,
        )
    except ValueError as exc:
        raise ProfileError(str(exc)) from exc
    payload = {
        "users": [user_record]
    }
    user_file.parent.mkdir(parents=True, exist_ok=True)
    user_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    user_file.chmod(0o600)

    return [
        f"Generated browser-session user file: {user_file}",
        f"Demo username: {username}",
        f"Demo password: {password}",
        "Store this password now; it is shown once and only the PBKDF2 hash was written.",
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
            "demo_lan_browser profile."
        ),
    )
    parser.add_argument(
        "--http-stream-port",
        type=int,
        default=DEFAULT_HTTP_STREAM_PORT,
        help="Backend API/streaming port for demo_lan_browser. Default: 5077.",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=DEFAULT_DASHBOARD_PORT,
        help="Dashboard port for demo_lan_browser CORS guidance. Default: 3040.",
    )
    parser.add_argument(
        "--session-user-file",
        type=Path,
        default=DEFAULT_DEMO_USER_FILE,
        help=(
            "External browser-session user JSON for demo_lan_browser. "
            "Default: configs/secrets/demo-browser-users.json."
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
        default="operator",
        help="Role for the generated demo_lan_browser user. Default: operator.",
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
        written = _write_config(args, config)
        artifact_summaries = _write_profile_artifacts(args)
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
