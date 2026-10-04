#!/usr/bin/env python3
"""Prepare or run an isolated real PixEagle replay for the native QGC demo.

Preparation copies source/config definitions and bundled recorded video into a
new private directory. It never launches an app or touches checkout accounts.
Run executes the copied production src/main.py with its real capture/tracker,
publisher, authentication and APIs. Use a network-isolated validation harness.
This is a recorded-video viewer demo, not synthetic video or aircraft evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys

import yaml


REPOSITORY = Path(__file__).resolve().parents[1]
VIDEO = "resources/test4.mp4"
VIDEOS = {f"test{number}.mp4": f"resources/test{number}.mp4" for number in range(1, 13)}


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_json(path, data):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def demo_config(defaults, directory, port, *, video=VIDEO, clean_osd=False, model=None,
                dashboard_port=None):
    config = yaml.safe_load(yaml.safe_dump(defaults))
    config["VideoSource"].update(VIDEO_SOURCE_TYPE="VIDEO_FILE", VIDEO_FILE_PATH=video,
                                 VIDEO_FILE_EOF_POLICY="LOOP", USE_GSTREAMER=False,
                                 PIPELINE_MODE="REALTIME")
    config["Follower"].update(FOLLOWER_EXECUTION_MODE="COMMAND_PREVIEW", FOLLOWER_MODE="mc_velocity_chase")
    config["FOLLOWER_CIRCUIT_BREAKER"] = True
    config["MAVLink"]["MAVLINK_ENABLED"] = False
    # An accidental observational verification cannot reach a real MAVSDK
    # sidecar: its configured port is owned by this HTTP server, not MAVSDK.
    config["PX4"].update(EXTERNAL_MAVSDK_SERVER=True, MAVSDK_SERVER_ADDRESS="127.0.0.1",
                          MAVSDK_SERVER_PORT=port, MAVSDK_CONNECTION_TIMEOUT_S=1.0)
    config["Tracking"]["DEFAULT_TRACKING_ALGORITHM"] = "CSRT"
    config["SmartTracker"]["SMART_TRACKER_ENABLED"] = model is not None
    if model is not None:
        config["SmartTracker"].update(
            SMART_TRACKER_GPU_MODEL_PATH=f"models/{model}",
            SMART_TRACKER_CPU_MODEL_PATH=f"models/{model}",
        )
    config["GimbalTracker"].update(ENABLED=False, CONTROL_ENABLED=False)
    config["GStreamer"]["ENABLE_GSTREAMER_STREAM"] = False
    config["Recording"]["ENABLE_RECORDING"] = False
    config["Telemetry"].update(ENABLE_TELEMETRY=False, ENABLE_UDP_STREAM=False)
    config["FrameEstimation"]["SHOW_VIDEO_WINDOW"] = False
    if clean_osd:
        config["OSD"]["OSD_ENABLED"] = False
        config["SmartTracker"]["SMART_TRACKER_SHOW_PASSIVE_LABELS"] = False
    config["Streaming"].update(
        ENABLE_STREAMING=True, HTTP_STREAM_HOST="127.0.0.1", HTTP_STREAM_PORT=port,
        API_EXPOSURE_MODE="local_only", API_AUTH_MODE="browser_session",
        API_SYSTEM_RESTART_POLICY="local_only", API_ALLOWED_HOSTS=["127.0.0.1"],
        API_CORS_ALLOWED_ORIGINS=[f"http://127.0.0.1:{port}"] + (
            [f"http://127.0.0.1:{dashboard_port}"] if dashboard_port is not None else []),
        API_SESSION_USER_FILE=str(directory / "configs/secrets/native-demo-users.json"),
        API_SESSION_COOKIE_SECURE=False, API_SESSION_TTL_SECONDS=3600,
        API_BEARER_TOKEN_FILE="", ALLOW_UNAUTHENTICATED_MEDIA_STREAMING=False,
        API_SECURITY_AUDIT_ENABLED=True,
        API_SECURITY_AUDIT_LOG_PATH=str(directory / "logs/security-audit.jsonl"),
    )
    return config


def _copy_model_store(source, directory, copied, selected_model):
    """Preserve existing trust receipts; never register or execute new checkpoints."""
    sys.path.insert(0, str(REPOSITORY / "src"))
    from classes.model_artifact_policy import ModelProvenanceStore, ModelStoreLease, validate_model_filename
    from classes.model_manager import MODEL_INSPECTION_CACHE_SCHEMA_VERSION, ModelManager
    from classes.tracker_artifacts import load_tracker_artifact_manifest, resolve_tracker_artifact

    validate_model_filename(selected_model)
    source = Path(source).absolute()
    store = ModelProvenanceStore(source)
    target_root = directory / "models"
    target_root.mkdir(mode=0o700)
    records = {}
    with ModelStoreLease(source, exclusive=False) as lease:
        registry = store.load_locked(lease)
        if selected_model not in registry["artifacts"]:
            raise ValueError("Selected demo model is not registered in the source store")
        for name in sorted(registry["artifacts"]):
            if not name.endswith(".pt"):
                continue
            validate_model_filename(name)
            record, _, descriptor = store.verify_pt_pinned_locked(source / name, lease)
            target = target_root / name
            with os.fdopen(os.dup(descriptor), "rb") as input_stream, target.open("xb") as output:
                input_stream.seek(0)
                shutil.copyfileobj(input_stream, output)
            target.chmod(0o600)
            copied[f"models/{name}"] = _digest(target)
            if copied[f"models/{name}"] != record["sha256"]:
                raise ValueError(f"Model changed while copying: {name}")
            records[name] = record
    if selected_model not in records:
        raise ValueError("Selected demo model must be a registered .pt checkpoint")
    registry_path = target_root / ".model-provenance.json"
    _private_json(registry_path, {"schema_version": registry["schema_version"], "artifacts": records})
    copied["models/.model-provenance.json"] = _digest(registry_path)
    cache = ModelManager(str(source)).cache
    inspected = {}
    for name, record in records.items():
        model_id = Path(name).stem
        metadata = ModelManager._cached_validation(cache.get(model_id), provenance=record)
        if metadata is not None:
            inspected[model_id] = {
                "inspection_schema_version": MODEL_INSPECTION_CACHE_SCHEMA_VERSION,
                "inspection_artifact_sha256": record["sha256"],
                "metadata": metadata,
            }
    if inspected:
        # Runtime discovery rebuilds this disposable cache with snapshot-local paths.
        _private_json(target_root / ".models.json", inspected)
    manifest_path = REPOSITORY / "configs/tracker_artifacts.json"
    for artifact_id, artifact in load_tracker_artifact_manifest(manifest_path)["artifacts"].items():
        relative = artifact["destination"]
        original = source / Path(relative).relative_to("models")
        if not original.exists() and not original.is_symlink():
            continue
        resolved = resolve_tracker_artifact(
            {"artifact_id": artifact_id}, project_root=source.parent, manifest_path=manifest_path,
        )
        target = directory / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(resolved.path, target)
        target.chmod(0o600)
        copied[relative] = _digest(target)
        if copied[relative] != artifact["sha256"]:
            raise ValueError(f"Classic artifact changed while copying: {artifact_id}")
    return sorted(records)


def prepare(directory, *, port=8093, role="viewer", video="test4.mp4", model_store=None, model=None,
            dashboard_port=None):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Demo port must be 1024–65535")
    if dashboard_port is not None and (
        type(dashboard_port) is not int or not 1024 <= dashboard_port <= 65535 or dashboard_port == port
    ):
        raise ValueError("Dashboard port must be 1024–65535 and different from the backend port")
    if role not in ("viewer", "operator", "admin"):
        raise ValueError("Demo role must be viewer, operator or admin")
    if video not in VIDEOS:
        raise ValueError("Demo video must be an allowed bundled recording")
    if (model_store is None) != (model is None):
        raise ValueError("Full AI replay requires both a model store and selected model")
    video_path = VIDEOS[video]
    directory = Path(directory).absolute()
    if directory.exists() or directory.is_symlink():
        raise ValueError("Use a new private demo directory; existing data is never replaced")
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(mode=0o700)
    directory = directory.resolve()
    paths = subprocess.check_output(
        ["git", "ls-files", "-cmo", "--exclude-standard", "-z", "--", "src", "configs"],
        cwd=REPOSITORY,
    ).decode().split("\0")
    copied = {}
    for name in sorted(set(paths) - {"", "configs/config.yaml"}):
        source = REPOSITORY / name
        if source.is_symlink() or not source.is_file() or name.startswith("configs/secrets/"):
            continue
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[name] = _digest(target)
    for source in [REPOSITORY / video_path, *sorted((REPOSITORY / "resources/fonts").glob("*.ttf"))]:
        name = str(source.relative_to(REPOSITORY))
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[name] = _digest(target)
    defaults = yaml.safe_load((directory / "configs/config_default.yaml").read_text())
    clean_osd = video != "test4.mp4"
    model_names = _copy_model_store(model_store, directory, copied, model) if model is not None else []
    config = demo_config(defaults, directory, port, video=video_path, clean_osd=clean_osd, model=model,
                         dashboard_port=dashboard_port)
    config_path = directory / "configs/config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    config_path.chmod(0o600)
    sys.path.insert(0, str(REPOSITORY / "src"))
    from classes.browser_user_store import BrowserUserStore, make_browser_user_record
    password = secrets.token_urlsafe(24)
    record = make_browser_user_record(username="qgc-demo", plaintext_password=password, role=role)
    user_file = directory / "configs/secrets/native-demo-users.json"
    BrowserUserStore(user_file).replace_all([record], create_if_missing=True, backup=False)
    _private_json(directory / "credentials.json", {
        "purpose": "Temporary local QGC recorded-video demo only", "username": "qgc-demo",
        "password": password, "role": role, "endpoint": f"http://127.0.0.1:{port}",
    })
    copied["configs/config.yaml"] = _digest(config_path)
    copied["configs/secrets/native-demo-users.json"] = _digest(user_file)
    _private_json(directory / "demo-manifest.json", {
        "version": 1, "kind": "real-core-recorded-video", "port": port,
        "dashboard_port": dashboard_port,
        "instance_id": f"qgc-replay-{secrets.token_hex(8)}", "source_repository": str(REPOSITORY),
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPOSITORY).decode().strip(),
        "source_files": copied, "python": str(Path(sys.executable).absolute()),
        "following_enabled": False, "aircraft_connected": False,
        "role": role,
        "video": video_path, "video_sha256": copied[video_path],
        "clean_osd": clean_osd,
        "profile": "full_ai" if model is not None else "core",
        "selected_model": model,
        "models": model_names,
        "initial_model_inspection_sha256": _digest(directory / "models/.models.json")
        if (directory / "models/.models.json").is_file() else None,
        "allow_installed_model_selection": model is not None,
    })
    validate(directory)
    return directory


def validate(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir() or stat.S_IMODE(directory.stat().st_mode) & 0o077:
        raise ValueError("Demo directory must be private and cannot be a symlink")
    manifest = json.loads((directory / "demo-manifest.json").read_text())
    if manifest.get("version") != 1 or manifest.get("kind") != "real-core-recorded-video":
        raise ValueError("Unsupported demo manifest")
    for name, digest in manifest["source_files"].items():
        path = directory / name
        mutable_model_config = name == "configs/config.yaml" and manifest.get("allow_installed_model_selection") is True
        if path.is_symlink() or not path.is_file() or (not mutable_model_config and _digest(path) != digest):
            raise ValueError(f"Demo snapshot changed: {name}")
    defaults = yaml.safe_load((directory / "configs/config_default.yaml").read_text())
    config = yaml.safe_load((directory / "configs/config.yaml").read_text())
    video = manifest.get("video", VIDEO)
    if video not in VIDEOS.values():
        raise ValueError("Demo manifest video must be an allowed bundled recording")
    if manifest.get("video_sha256", manifest["source_files"].get(video)) != manifest["source_files"].get(video):
        raise ValueError("Demo video checksum does not match snapshot manifest")
    dashboard_port = manifest.get("dashboard_port")
    if dashboard_port is not None and (
        type(dashboard_port) is not int or not 1024 <= dashboard_port <= 65535
        or dashboard_port == manifest["port"]
    ):
        raise ValueError("Invalid demo dashboard port")
    expected = demo_config(defaults, directory.resolve(), manifest["port"], video=video,
                           clean_osd=manifest.get("clean_osd", False), model=manifest.get("selected_model"),
                           dashboard_port=dashboard_port)
    if manifest.get("allow_installed_model_selection") is True:
        selected = []
        for field in ("SMART_TRACKER_GPU_MODEL_PATH", "SMART_TRACKER_CPU_MODEL_PATH"):
            value = config.get("SmartTracker", {}).get(field)
            match = next((name for name in manifest.get("models", [])
                          if value in (f"models/{name}", str(directory.resolve() / "models" / name))), None)
            if match is None:
                raise ValueError("Demo model selection must use a copied installed model")
            selected.append(match)
            expected["SmartTracker"][field] = value
        if len(set(selected)) != 1:
            raise ValueError("Demo CPU and GPU paths must select the same installed model")
    if config != expected:
        raise ValueError("Demo configuration must preserve the inhibited replay profile")
    validate_runtime_policy(config)
    for name in ("credentials.json", "configs/secrets/native-demo-users.json", "configs/config.yaml"):
        if stat.S_IMODE((directory / name).stat().st_mode) & 0o077:
            raise ValueError(f"Demo private file has broad permissions: {name}")
    return manifest


def validate_runtime_policy(config):
    """Apply the runtime exposure rules, which are stricter than field schema."""
    sys.path.insert(0, str(REPOSITORY / "src"))
    from classes.api_exposure_policy import resolve_api_exposure_policy
    stream = config["Streaming"]
    return resolve_api_exposure_policy(
        bind_host=stream["HTTP_STREAM_HOST"], mode=stream["API_EXPOSURE_MODE"],
        api_port=stream["HTTP_STREAM_PORT"],
        cors_allowed_origins=stream["API_CORS_ALLOWED_ORIGINS"],
        allowed_hosts=stream["API_ALLOWED_HOSTS"], allow_credentials=True,
    )


def run(directory):
    directory = Path(directory).absolute()
    manifest = validate(directory)
    environment = dict(os.environ)
    environment.update(PYTHONPATH=str(directory / "src"), PIXEAGLE_PROJECT_ROOT=str(directory),
                       PIXEAGLE_INSTANCE_ID=manifest["instance_id"],
                       PIXEAGLE_RUNTIME_LOG_DIR=str(directory / "logs/runtime"),
                       PIXEAGLE_RUN_ID=f"native_replay_{secrets.token_hex(8)}",
                       YOLO_AUTOINSTALL="False", YOLO_CONFIG_DIR=str(directory / ".ultralytics"))
    (directory / ".ultralytics").mkdir(mode=0o700, exist_ok=True)
    os.chdir(directory)
    python = manifest["python"]
    os.execve(python, [python, "-u", "src/main.py"], environment)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "validate", "run"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8093)
    parser.add_argument("--role", choices=("viewer", "operator", "admin"), default="viewer")
    parser.add_argument("--dashboard-port", type=int,
                        help="Allow the explicit http://127.0.0.1 dashboard origin on this port")
    parser.add_argument("--video", choices=tuple(VIDEOS), default="test4.mp4")
    parser.add_argument("--model-store", type=Path, help="Copy an existing trusted local model store")
    parser.add_argument("--model", help="Registered .pt filename selected for the Full AI replay")
    args = parser.parse_args()
    if args.action == "prepare":
        path = prepare(args.directory, port=args.port, role=args.role, video=args.video,
                       model_store=args.model_store, model=args.model, dashboard_port=args.dashboard_port)
        print(f"Prepared real replay snapshot: {path}")
        print(f"Private demo login: {path / 'credentials.json'}")
        print("No application or camera started. Use the isolated validation harness for run.")
    elif args.action == "validate":
        validate(args.directory)
        print("Private snapshot, hashes and inhibited replay configuration are valid.")
    else:
        run(args.directory)


if __name__ == "__main__":
    main()
