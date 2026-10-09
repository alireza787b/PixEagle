#!/usr/bin/env python3
"""Prepare a private camera/SIH profile; do not start services or permit commands.

The profile starts with the PixEagle flight-command circuit breaker active.
Only an isolated SIH launcher may later connect it to PX4 and explicitly
disable that guard after verifying the simulated aircraft identity.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
from urllib.parse import urlsplit

import yaml


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
from tools.native_replay_demo import VIDEOS


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_json(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    path.chmod(0o600)


def prepare(
    directory: Path, *, camera_host: str | None = None, rtsp_url: str | None = None, mount_type: str = "HORIZONTAL",
    follower_mode: str = "gm_velocity_chase", backend_port: int = 8096,
    dashboard_port: int | None = None, continuity_mode: str = "immediate_handoff",
    tracking_engine: str = "camera", model_store: Path | None = None, model: str | None = None,
    recorded_video: str | None = None,
    follower_execution_mode: str = "PX4",
    allow_recorded_sih_following: bool = False,
) -> Path:
    if mount_type not in ("HORIZONTAL", "VERTICAL"):
        raise ValueError("Mount must be HORIZONTAL or VERTICAL")
    modes = {"camera": ("gm_velocity_chase", "gm_velocity_vector"),
             "local": ("mc_velocity_position", "mc_velocity_chase", "mc_velocity_distance")}
    if tracking_engine not in modes or follower_mode not in modes[tracking_engine]:
        raise ValueError("Follower must match the selected tracking engine")
    if follower_execution_mode not in ("PX4", "COMMAND_PREVIEW"):
        raise ValueError("Unsupported follower execution mode")
    if follower_execution_mode == "COMMAND_PREVIEW" and recorded_video is None:
        raise ValueError("This follower-test profile requires recorded video")
    if allow_recorded_sih_following and (recorded_video is None or follower_execution_mode != "PX4"):
        raise ValueError("Recorded SIH following requires a recorded video and PX4 execution")
    if (model_store is None) != (model is None) or model is not None and tracking_engine != "local":
        raise ValueError("Local Smart requires both a model store and selected model")
    if continuity_mode not in ("immediate_handoff", "bounded_decay"):
        raise ValueError("Unsupported target continuity mode")
    if type(backend_port) is not int or not 1024 <= backend_port <= 65535:
        raise ValueError("Backend port must be 1024–65535")
    if dashboard_port is not None and (
        type(dashboard_port) is not int or not 1024 <= dashboard_port <= 65535
        or dashboard_port == backend_port
    ):
        raise ValueError("Dashboard port must be distinct and in 1024–65535")
    if recorded_video is not None:
        if recorded_video not in VIDEOS or tracking_engine != "local":
            raise ValueError("Recorded-video SIH requires local tracking and a bundled video")
        if camera_host is not None or rtsp_url is not None:
            raise ValueError("Choose recorded video or an RTSP camera, not both")
    else:
        if not camera_host or any(character.isspace() or character in "/:@?#" for character in camera_host):
            raise ValueError("Camera host must be a host or IP address, without a URL scheme")
        parsed_rtsp = urlsplit(rtsp_url or "")
        if (parsed_rtsp.scheme != "rtsp" or parsed_rtsp.hostname != camera_host
                or parsed_rtsp.username is not None or parsed_rtsp.password is not None
                or parsed_rtsp.fragment):
            raise ValueError("RTSP URL must use the selected camera host without embedded credentials")

    directory = Path(directory).absolute()
    if directory.exists() or directory.is_symlink():
        raise ValueError("Use a new private directory; an existing runtime is never overwritten")
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(mode=0o700)
    directory = directory.resolve()
    copied: dict[str, str] = {}
    paths = subprocess.check_output(
        ["git", "ls-files", "-cmo", "--exclude-standard", "-z", "--", "src"],
        cwd=REPOSITORY,
    ).decode().split("\0")
    for name in sorted(set(paths) - {""}):
        source = REPOSITORY / name
        if source.is_symlink() or not source.is_file():
            continue
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[name] = _digest(target)
    config_paths = subprocess.check_output(
        ["git", "ls-files", "-cmo", "--exclude-standard", "-z", "--", "configs"],
        cwd=REPOSITORY,
    ).decode().split("\0")
    for relative in sorted(set(config_paths) - {"", "configs/config.yaml"}):
        if relative.startswith("configs/secrets/"):
            continue
        source = REPOSITORY / relative
        if source.is_symlink() or not source.is_file():
            continue
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[relative] = _digest(target)
    for source in sorted((REPOSITORY / "resources/fonts").glob("*.ttf")):
        relative = str(source.relative_to(REPOSITORY))
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[relative] = _digest(target)

    config = yaml.safe_load((directory / "configs/config_default.yaml").read_text(encoding="utf-8"))
    if recorded_video is not None:
        relative = VIDEOS[recorded_video]
        source = REPOSITORY / relative
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[relative] = _digest(target)
        config["VideoSource"].update(VIDEO_SOURCE_TYPE="VIDEO_FILE", VIDEO_FILE_PATH=relative,
            USE_GSTREAMER=False, PIPELINE_MODE="REALTIME", FRAME_ROTATION_DEG=0, FRAME_FLIP_MODE="none")
        config["GimbalTracker"].update(ENABLED=False, CONTROL_ENABLED=False, MOUNT_TYPE=mount_type)
    else:
        config["VideoSource"].update(
            VIDEO_SOURCE_TYPE="RTSP_OPENCV", RTSP_URL=rtsp_url,
            USE_GSTREAMER=False, PIPELINE_MODE="REALTIME",
            FRAME_ROTATION_DEG=0, FRAME_FLIP_MODE="none",
        )
        config["GimbalTracker"].update(
            ENABLED=True, CONTROL_ENABLED=True, PROVIDER="topotek_sip_udp",
            UDP_HOST=camera_host, MOUNT_TYPE=mount_type,
        )
    model_names = []
    if model is not None:
        sys.path.insert(0, str(REPOSITORY))
        from tools.native_replay_demo import _copy_model_store
        model_names = _copy_model_store(model_store, directory, copied, model)
    config["Tracking"]["DEFAULT_TRACKING_ALGORITHM"] = "Gimbal" if tracking_engine == "camera" else "CSRT"
    config["SmartTracker"]["SMART_TRACKER_ENABLED"] = model is not None
    if model is not None:
        config["SmartTracker"].update(SMART_TRACKER_GPU_MODEL_PATH=f"models/{model}",
            SMART_TRACKER_CPU_MODEL_PATH=f"models/{model}", SMART_TRACKER_USE_GPU=True,
            # Qualification profiles show the detector's short class labels so
            # an operator can see what is selectable. Factory defaults remain
            # quiet through the normal configuration path.
            SMART_TRACKER_SHOW_PASSIVE_LABELS=True)
    config["Follower"].update(FOLLOWER_MODE=follower_mode, FOLLOWER_EXECUTION_MODE=follower_execution_mode)
    config["Follower"]["SIH_RECORDED_VIDEO_FOLLOWING"] = allow_recorded_sih_following
    config["Follower"]["FollowerOverrides"]["GM_VELOCITY_VECTOR"]["LATERAL_GUIDANCE_MODE"] = "coordinated_turn"
    config["TargetContinuity"]["MODE"] = continuity_mode
    # This explicit qualification profile owns one policy for both allowed
    # followers. Do not let fresh-install sparse defaults defeat the CLI mode.
    if tracking_engine == "camera":
        config["TargetContinuity"].pop("FollowerOverrides", None)
    if continuity_mode == "bounded_decay":
        config["TargetContinuity"].update(
            MAX_COAST_TIME_S=8.0, MAX_COAST_DISTANCE_M=4.0,
            MAX_RETARGET_TIME_S=8.0, AUTHORITY_RESTORE_TIME_S=0.5,
        )
    config["FOLLOWER_CIRCUIT_BREAKER"] = True
    config["PX4"].update(
        SYSTEM_ADDRESS="udpin://127.0.0.1:14540",
        EXTERNAL_MAVSDK_SERVER=True, MAVSDK_SERVER_ADDRESS="127.0.0.1",
        MAVSDK_SERVER_PORT=50051,
    )
    config["MAVLink"].update(MAVLINK_ENABLED=True, MAVLINK_HOST="127.0.0.1", MAVLINK_PORT=8088)
    config["GStreamer"]["ENABLE_GSTREAMER_STREAM"] = False
    config["Recording"]["ENABLE_RECORDING"] = False
    config["FrameEstimation"]["SHOW_VIDEO_WINDOW"] = False
    config["OSD"]["OSD_ENABLED"] = False
    config["Streaming"].update(
        ENABLE_STREAMING=True, HTTP_STREAM_HOST="0.0.0.0", HTTP_STREAM_PORT=backend_port,
        API_EXPOSURE_MODE="trusted_lan_legacy", API_AUTH_MODE="browser_session",
        API_ALLOWED_HOSTS=["127.0.0.1"],
        API_CORS_ALLOWED_ORIGINS=[f"http://127.0.0.1:{backend_port}"] + (
            [f"http://127.0.0.1:{dashboard_port}"] if dashboard_port else []
        ),
        API_SESSION_USER_FILE=str(directory / "configs/secrets/sitl-users.json"),
        API_SESSION_COOKIE_SECURE=False, API_BEARER_TOKEN_FILE="",
        ALLOW_UNAUTHENTICATED_MEDIA_STREAMING=False,
        API_SYSTEM_RESTART_POLICY="lab_admin_browser",
        API_SECURITY_AUDIT_ENABLED=True,
        API_SECURITY_AUDIT_LOG_PATH=str(directory / "logs/security-audit.jsonl"),
    )
    (directory / "logs").mkdir(mode=0o700)
    config_path = directory / "configs/config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    config_path.chmod(0o600)
    copied["configs/config.yaml"] = _digest(config_path)

    sys.path.insert(0, str(REPOSITORY / "src"))
    from classes.browser_user_store import BrowserUserStore, make_browser_user_record

    password = secrets.token_urlsafe(24)
    user_file = directory / "configs/secrets/sitl-users.json"
    BrowserUserStore(user_file).replace_all([
        make_browser_user_record(username="sih-operator", plaintext_password=password, role="admin")
    ], create_if_missing=True, backup=False)
    copied["configs/secrets/sitl-users.json"] = _digest(user_file)
    _private_json(directory / "credentials.json", {
        "purpose": "Isolated PX4 SIH gimbal qualification only",
        "username": "sih-operator", "password": password,
        "endpoint": f"http://127.0.0.1:{backend_port}",
    })
    _private_json(directory / "profile-manifest.json", {
        "version": 1, "kind": "gimbal-sih-preflight", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_repository": str(REPOSITORY),
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPOSITORY).decode().strip(),
        "source_files": copied, "python": str(Path(sys.executable).absolute()),
        "instance_id": f"gimbal-sih-{secrets.token_hex(8)}", "backend_port": backend_port,
        "camera_host": camera_host, "rtsp_url": rtsp_url,
        "mount_type": mount_type, "follower_mode": follower_mode,
        "tracking_engine": tracking_engine, "models": model_names, "recorded_video": recorded_video,
        "follower_execution_mode": follower_execution_mode,
        "allow_recorded_sih_following": allow_recorded_sih_following,
        "continuity_mode": continuity_mode,
        "flight_commands_blocked": True, "services_started": False,
    })
    validate(directory)
    return directory


def validate(directory: Path) -> dict:
    """Validate an untouched prepared profile before isolated Docker startup."""
    directory = Path(directory).absolute()
    if (directory.is_symlink() or not directory.is_dir()
            or stat.S_IMODE(directory.stat().st_mode) & 0o077):
        raise ValueError("SIH profile directory must be private and not a symlink")
    manifest = json.loads((directory / "profile-manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("version") != 1 or manifest.get("kind") != "gimbal-sih-preflight"
            or manifest.get("flight_commands_blocked") is not True):
        raise ValueError("Expected a prepared, command-blocked gimbal SIH profile")
    for name, expected in manifest["source_files"].items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or _digest(path) != expected:
            raise ValueError(f"SIH profile snapshot changed: {name}")
    config = yaml.safe_load((directory / "configs/config.yaml").read_text(encoding="utf-8"))
    sys.path.insert(0, str(REPOSITORY / "src"))
    from classes.backend_supervisor import validate_sih_routes
    validate_sih_routes(config)
    if (config.get("FOLLOWER_CIRCUIT_BREAKER") is not True
            or config.get("Follower", {}).get("FOLLOWER_EXECUTION_MODE") != manifest.get("follower_execution_mode", "PX4")
            or config.get("Follower", {}).get("SIH_RECORDED_VIDEO_FOLLOWING", False) != manifest.get("allow_recorded_sih_following", False)
            or config.get("PX4", {}).get("SYSTEM_ADDRESS") != "udpin://127.0.0.1:14540"
            or config.get("Streaming", {}).get("HTTP_STREAM_HOST") != "0.0.0.0"
            or config.get("Streaming", {}).get("API_EXPOSURE_MODE") != "trusted_lan_legacy"
            or config.get("Streaming", {}).get("HTTP_STREAM_PORT") != manifest.get("backend_port")
            or config.get("GimbalTracker", {}).get("MOUNT_TYPE") != manifest.get("mount_type")
            or (manifest.get("recorded_video") is None and
                config.get("GimbalTracker", {}).get("UDP_HOST") != manifest.get("camera_host"))
            or config.get("TargetContinuity", {}).get("MODE") != manifest.get("continuity_mode")):
        raise ValueError("SIH profile safety or camera contract changed")
    if manifest.get("recorded_video") is not None:
        if (config["GimbalTracker"]["ENABLED"] or config["GimbalTracker"]["CONTROL_ENABLED"]
                or config["Tracking"]["DEFAULT_TRACKING_ALGORITHM"] != "CSRT"
                or config["VideoSource"]["VIDEO_SOURCE_TYPE"] != "VIDEO_FILE"
                or manifest.get("tracking_engine") != "local"):
            raise ValueError("Recorded-video profile must not activate a camera provider")
    for name in ("configs/config.yaml", "configs/secrets/sitl-users.json", "credentials.json"):
        if stat.S_IMODE((directory / name).stat().st_mode) & 0o077:
            raise ValueError(f"SIH private file has broad permissions: {name}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--camera-host")
    parser.add_argument("--rtsp-url")
    parser.add_argument("--mount-type", choices=("HORIZONTAL", "VERTICAL"), default="HORIZONTAL")
    parser.add_argument("--recorded-video", choices=tuple(VIDEOS))
    parser.add_argument("--follower-mode", choices=("gm_velocity_chase", "gm_velocity_vector", "mc_velocity_position", "mc_velocity_chase", "mc_velocity_distance"),
                        default="gm_velocity_chase")
    parser.add_argument("--tracking-engine", choices=("camera", "local"), default="camera")
    parser.add_argument("--follower-execution-mode", choices=("PX4", "COMMAND_PREVIEW"), default="PX4")
    parser.add_argument("--allow-recorded-sih-following", action="store_true")
    parser.add_argument("--model-store", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--backend-port", type=int, default=8096)
    parser.add_argument("--dashboard-port", type=int)
    parser.add_argument("--continuity-mode", choices=("immediate_handoff", "bounded_decay"),
                        default="immediate_handoff")
    args = parser.parse_args()
    path = prepare(args.directory, camera_host=args.camera_host, rtsp_url=args.rtsp_url,
                   mount_type=args.mount_type, follower_mode=args.follower_mode,
                   backend_port=args.backend_port, dashboard_port=args.dashboard_port,
                   continuity_mode=args.continuity_mode, tracking_engine=args.tracking_engine,
                   model_store=args.model_store, model=args.model, recorded_video=args.recorded_video,
                   follower_execution_mode=args.follower_execution_mode,
                   allow_recorded_sih_following=args.allow_recorded_sih_following)
    print(f"Prepared private SIH profile: {path}")
    print("Camera and PX4 services remain stopped; PixEagle flight commands are blocked.")
    print("Run only inside a dedicated Docker network with the API port mapped to host loopback.")


if __name__ == "__main__":
    main()
