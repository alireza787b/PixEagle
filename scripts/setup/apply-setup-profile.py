#!/usr/bin/env python3
"""Apply PixEagle setup profiles to a local runtime config.

The checked-in `configs/config_default.yaml` remains the source of truth.
This tool creates or updates `configs/config.yaml` only when the operator
explicitly chooses a profile that needs local host-specific values.
"""

from __future__ import annotations

import argparse
import copy
import sys
from dataclasses import dataclass
from pathlib import Path
from time import strftime
from typing import Any, Callable

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "config_default.yaml"
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "configs" / "config.yaml"
LOOPBACK_CORS_ORIGINS = ["http://127.0.0.1:3040", "http://localhost:3040"]
QGC_DEFAULT_UDP_H264_PORT = 5600


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
        status="defined_not_automated",
        description=(
            "Lab LAN browser demo with generated browser_session credentials "
            "and exact Host/CORS allowlists."
        ),
        applier=_profile_deferred(
            "demo_lan_browser",
            "Use an SSH tunnel today; full automation must generate external "
            "hashed users, configure dashboard bind/origin, and record the "
            "lab-only security boundary."
        ),
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
    except ProfileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    action = "Dry run" if args.dry_run else "Applied"
    print(f"{action}: PixEagle setup profile {args.profile}")
    for summary in summaries:
        print(f"  - {summary}")
    if written is not None:
        print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
