#!/usr/bin/env python3
"""Generated H.264 RTP/UDP receiver proof for PixEagle.

This tool is intentionally dry-run by default. Guarded execute mode starts only
a local GStreamer `videotestsrc` sender and verifies PixEagle's UDP/GStreamer
receiver path with evidence artifacts. It does not start PX4, Docker, Gazebo,
MAVLink2REST, MavlinkAnywhere, HIL, services, or real aircraft endpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform as system_platform
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Tuple

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "reports" / "video"
DEFAULT_RUN_ID = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
DEFAULT_PORT = 5600
DEFAULT_WIDTH = 320
DEFAULT_HEIGHT = 240
DEFAULT_FPS = 15
DEFAULT_FRAME_COUNT = 8
DEFAULT_CAPTURE_SECONDS = 6.0
DEFAULT_STALE_SECONDS = 1.4
DEFAULT_STALE_TIMEOUT_SECONDS = 0.6

CLAIM_BOUNDARY = (
    "Generated RTP/UDP video ingest proof only. This does not claim tracker, "
    "follower, PX4, Gazebo, SITL, HIL, field, or real-aircraft validation."
)

REQUIRED_RECEIVER_TERMS = [
    "udpsrc",
    "caps=\"application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000\"",
    "rtph264depay",
    "h264parse",
    "avdec_h264",
    "videoconvert",
    "video/x-raw,format=BGR",
    "videoscale",
    "appsink",
    "drop=true",
    "max-buffers=1",
    "sync=false",
]

STRICT_UDP_TEMPLATE = (
    "udpsrc uri={url} "
    "caps=\"application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000\" "
    "! rtph264depay ! h264parse ! avdec_h264 ! videoconvert "
    "! video/x-raw,format=BGR ! videoscale "
    "! video/x-raw,width={width},height={height} "
    "! appsink drop=true max-buffers=1 sync=false"
)


def _read_default_udp_template() -> str:
    """Read the checked-in UDP pipeline template without importing app code."""
    config_path = REPO_ROOT / "configs" / "config_default.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    try:
        template = config["GStreamerPipelines"]["UDP"]
    except (TypeError, KeyError) as exc:
        raise ValueError(f"Could not find GStreamerPipelines.UDP in {config_path}") from exc
    if not isinstance(template, str) or not template.strip():
        raise ValueError(f"GStreamerPipelines.UDP must be a non-empty string in {config_path}")
    return template


def format_receiver_pipeline(
    template: str,
    *,
    url: str,
    width: int,
    height: int,
) -> str:
    return template.format(url=url, width=width, height=height)


def validate_receiver_pipeline(
    template: str,
    *,
    url: str = "udp://127.0.0.1:5600",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> Dict[str, Any]:
    """Validate the RTP/H.264 receiver contract used by PixEagle."""
    pipeline = format_receiver_pipeline(template, url=url, width=width, height=height)
    missing = [term for term in REQUIRED_RECEIVER_TERMS if term not in pipeline]
    dimension_terms = [f"width={width}", f"height={height}"]
    missing.extend(term for term in dimension_terms if term not in pipeline)

    ordered_terms = [
        "udpsrc",
        "caps=\"application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000\"",
        "rtph264depay",
        "h264parse",
        "avdec_h264",
        "videoconvert",
        "video/x-raw,format=BGR",
        "videoscale",
        "appsink",
    ]
    last_index = -1
    out_of_order: List[str] = []
    for term in ordered_terms:
        index = pipeline.find(term)
        if index < last_index:
            out_of_order.append(term)
        last_index = index

    return {
        "valid": not missing and not out_of_order,
        "missing": missing,
        "out_of_order": out_of_order,
        "pipeline": pipeline,
    }


def is_strict_post_stop_stale(
    frame_status: Dict[str, Any],
    *,
    stale_timeout_seconds: float,
) -> bool:
    """Return True only for a proven post-stop stale/unusable frame status."""
    try:
        frame_age_seconds = float(frame_status.get("frame_age_seconds"))
    except (TypeError, ValueError):
        return False
    return (
        not frame_status.get("usable_for_following")
        and frame_status.get("reason") == "udp_async_frame_stale"
        and frame_age_seconds >= stale_timeout_seconds
    )


def build_sender_command(*, host: str, port: int, width: int, height: int, fps: int) -> List[str]:
    """Build a deterministic local H.264 RTP sender pipeline."""
    return [
        "gst-launch-1.0",
        "-q",
        "videotestsrc",
        "is-live=true",
        "pattern=ball",
        "!",
        f"video/x-raw,width={width},height={height},framerate={fps}/1",
        "!",
        "videoconvert",
        "!",
        "x264enc",
        "tune=zerolatency",
        "speed-preset=ultrafast",
        f"key-int-max={fps}",
        "bitrate=800",
        "!",
        "rtph264pay",
        "config-interval=1",
        "pt=96",
        "!",
        "udpsink",
        f"host={host}",
        f"port={port}",
        "sync=false",
        "async=false",
    ]


def _opencv_gstreamer_enabled() -> Tuple[bool, Dict[str, Any]]:
    try:
        import cv2  # type: ignore
    except Exception as exc:
        return False, {"cv2_import_error": str(exc)}

    build_info = cv2.getBuildInformation()
    enabled = False
    for line in build_info.splitlines():
        if "GStreamer" in line and ":" in line:
            enabled = line.split(":", 1)[1].strip().upper().startswith("YES")
            break
    return enabled, {
        "opencv_version": getattr(cv2, "__version__", "unknown"),
        "gstreamer_enabled": enabled,
    }


def _command_output(command: List[str]) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {"command": command, "error": str(exc)}


def _runtime_metadata(
    *,
    args: argparse.Namespace,
    gst_launch: str | None,
    opencv_info: Dict[str, Any],
) -> Dict[str, Any]:
    metadata = {
        "python": sys.version,
        "platform": system_platform.platform(),
        "kernel": system_platform.release(),
        "machine": system_platform.machine(),
        "opencv": opencv_info,
        "gst_launch": gst_launch,
        "gst_launch_version": _command_output([gst_launch, "--version"]) if gst_launch else None,
        "git_head": _command_output(["git", "rev-parse", "HEAD"]),
        "git_status_short": _command_output(["git", "status", "--short", "--branch"]),
        "tool_args": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
        "environment_path": os.environ.get("PATH", ""),
    }
    return metadata


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: Dict[str, Any] | List[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _prepare_artifact_dir(args: argparse.Namespace) -> Path:
    artifact_dir = Path(args.artifact_root).resolve() / args.run_id
    if artifact_dir.exists() and any(artifact_dir.iterdir()):
        raise RuntimeError(f"Refusing to reuse non-empty artifact directory: {artifact_dir}")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def _patch_video_parameters(
    video_handler_module: Any,
    *,
    template: str,
    port: int,
    width: int,
    height: int,
    fps: int,
    stale_timeout_seconds: float,
) -> None:
    params = video_handler_module.Parameters
    params.VIDEO_SOURCE_TYPE = "UDP_STREAM"
    params.USE_GSTREAMER = True
    params.UDP_URL = f"udp://127.0.0.1:{port}"
    params.CAPTURE_WIDTH = width
    params.CAPTURE_HEIGHT = height
    params.CAPTURE_FPS = fps
    params.DEFAULT_FPS = fps
    params.UDP = template
    params.STORE_LAST_FRAMES = 5
    params.RTSP_MAX_CONSECUTIVE_FAILURES = 2
    params.RTSP_CONNECTION_TIMEOUT = stale_timeout_seconds
    params.RTSP_MAX_RECOVERY_ATTEMPTS = 0
    params.RTSP_FRAME_CACHE_SIZE = 5
    params.RTSP_RECOVERY_BACKOFF_BASE = 0.1
    params.RTSP_RECOVERY_BACKOFF_MAX = 0.2
    params.FRAME_ROTATION_DEG = 0
    params.FRAME_FLIP_MODE = "none"


def _run_execute(args: argparse.Namespace, template: str, receiver_contract: Dict[str, Any]) -> Dict[str, Any]:
    if not args.allow_process_start:
        raise RuntimeError("--execute requires --allow-process-start")

    artifact_dir = _prepare_artifact_dir(args)
    gst_launch = shutil.which("gst-launch-1.0")
    cv_gst_ok, cv_info = _opencv_gstreamer_enabled()
    runtime_metadata = _runtime_metadata(args=args, gst_launch=gst_launch, opencv_info=cv_info)
    if not gst_launch or not cv_gst_ok:
        manifest = {
            "status": "incomplete",
            "mode": "execute",
            "claim_boundary": CLAIM_BOUNDARY,
            "artifact_dir": str(artifact_dir),
            "reason": "required_gstreamer_runtime_unavailable",
            "gst_launch": gst_launch,
            "opencv": cv_info,
        }
        _write_json(artifact_dir / "manifest.json", manifest)
        _write_json(artifact_dir / "versions" / "runtime.json", runtime_metadata)
        return manifest

    sender_cmd = build_sender_command(
        host="127.0.0.1",
        port=args.port,
        width=args.width,
        height=args.height,
        fps=args.fps,
    )
    receiver_pipeline = receiver_contract["pipeline"]
    sender_log = artifact_dir / "logs" / "gst_sender.log"
    sender_log.parent.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from classes import video_handler as video_handler_module  # pylint: disable=import-outside-toplevel

    _patch_video_parameters(
        video_handler_module,
        template=template,
        port=args.port,
        width=args.width,
        height=args.height,
        fps=args.fps,
        stale_timeout_seconds=args.stale_timeout_seconds,
    )

    frames: List[Dict[str, Any]] = []
    statuses: List[Dict[str, Any]] = []
    post_stop_statuses: List[Dict[str, Any]] = []
    handler = None
    sender = None
    started_at = time.time()
    try:
        with sender_log.open("w", encoding="utf-8") as log_handle:
            sender = subprocess.Popen(
                sender_cmd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            time.sleep(args.sender_warmup_seconds)
            handler = video_handler_module.VideoHandler()

            deadline = time.monotonic() + args.capture_seconds
            while time.monotonic() < deadline and len(frames) < args.frame_count:
                frame = handler.get_frame()
                status = handler.get_frame_status()
                statuses.append(status)
                if frame is not None and status.get("source") == "fresh":
                    frames.append({
                        "index": len(frames),
                        "shape": list(frame.shape),
                        "sha256": hashlib.sha256(frame.tobytes()).hexdigest(),
                        "status": status,
                    })
                time.sleep(max(0.01, 1.0 / max(args.fps * 2, 1)))

            sender.terminate()
            try:
                sender.wait(timeout=3)
            except subprocess.TimeoutExpired:
                sender.kill()
                sender.wait(timeout=3)

            post_deadline = time.monotonic() + args.stale_seconds
            while time.monotonic() < post_deadline:
                handler.get_frame()
                post_stop_statuses.append(handler.get_frame_status())
                time.sleep(0.1)
    except Exception as exc:
        manifest = {
            "status": "failed",
            "mode": "execute",
            "claim_boundary": CLAIM_BOUNDARY,
            "artifact_dir": str(artifact_dir),
            "reason": str(exc),
            "receiver_pipeline": receiver_pipeline,
            "sender_command": sender_cmd,
            "sender_exit_code": sender.returncode if sender else None,
            "sender_stop_expected": True,
            "opencv": cv_info,
            "gst_launch": gst_launch,
        }
        _write_json(artifact_dir / "manifest.json", manifest)
        _write_json(artifact_dir / "versions" / "runtime.json", runtime_metadata)
        return manifest
    finally:
        if sender and sender.poll() is None:
            sender.terminate()
            try:
                sender.wait(timeout=3)
            except subprocess.TimeoutExpired:
                sender.kill()
                sender.wait(timeout=3)
        if handler:
            handler.release()

    fresh_ok = len(frames) >= args.frame_count
    stale_ok = any(
        is_strict_post_stop_stale(
            frame_status,
            stale_timeout_seconds=args.stale_timeout_seconds,
        )
        for frame_status in post_stop_statuses
    )
    frame_shapes = [frame["shape"] for frame in frames]
    dimensions_ok = all(shape[:2] == [args.height, args.width] for shape in frame_shapes)
    status = "passed" if fresh_ok and stale_ok and dimensions_ok else "failed"

    manifest = {
        "status": status,
        "mode": "execute",
        "claim_boundary": CLAIM_BOUNDARY,
        "artifact_dir": str(artifact_dir),
        "started_at_epoch": started_at,
        "finished_at_epoch": time.time(),
        "fresh_frame_count": len(frames),
        "requested_frame_count": args.frame_count,
        "dimensions_ok": dimensions_ok,
        "fresh_ok": fresh_ok,
        "stale_unusable_ok": stale_ok,
        "stale_timeout_seconds": args.stale_timeout_seconds,
        "receiver_pipeline": receiver_pipeline,
        "sender_command": sender_cmd,
        "sender_exit_code": sender.returncode if sender else None,
        "sender_stop_expected": True,
        "opencv": cv_info,
        "gst_launch": gst_launch,
        "runtime": runtime_metadata,
    }

    _write_json(artifact_dir / "manifest.json", manifest)
    _write_json(
        artifact_dir / "video" / "source_config.json",
        {
            "VideoSource": {
                "VIDEO_SOURCE_TYPE": "UDP_STREAM",
                "UDP_URL": f"udp://127.0.0.1:{args.port}",
                "CAPTURE_WIDTH": args.width,
                "CAPTURE_HEIGHT": args.height,
                "CAPTURE_FPS": args.fps,
                "USE_GSTREAMER": True,
            }
        },
    )
    _write_text(artifact_dir / "video" / "receiver_pipeline.txt", receiver_pipeline + "\n")
    _write_text(artifact_dir / "video" / "sender_pipeline.txt", " ".join(sender_cmd) + "\n")
    _write_json(artifact_dir / "video" / "frame_status_sequence.json", statuses)
    _write_json(artifact_dir / "video" / "post_stop_frame_status_sequence.json", post_stop_statuses)
    _write_json(
        artifact_dir / "video" / "frame_hashes.json",
        {
            "count": len(frames),
            "first": frames[0] if frames else None,
            "last": frames[-1] if frames else None,
            "all": frames,
        },
    )
    _write_json(
        artifact_dir / "versions" / "runtime.json",
        {
            **runtime_metadata,
        },
    )
    return manifest


def build_dry_run_result(args: argparse.Namespace, template: str, receiver_contract: Dict[str, Any]) -> Dict[str, Any]:
    sender_cmd = build_sender_command(
        host="127.0.0.1",
        port=args.port,
        width=args.width,
        height=args.height,
        fps=args.fps,
    )
    return {
        "status": "dry_run",
        "mode": "dry-run",
        "claim_boundary": CLAIM_BOUNDARY,
        "would_start_processes": False,
        "would_write_artifacts": False,
        "receiver_contract": receiver_contract,
        "sender_command": sender_cmd,
        "artifact_root": str(Path(args.artifact_root).resolve()),
    }


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate contract without side effects")
    mode.add_argument("--execute", action="store_true", help="Run guarded local sender/receiver proof")
    parser.add_argument("--allow-process-start", action="store_true", help="Required with --execute")
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--frame-count", type=int, default=DEFAULT_FRAME_COUNT)
    parser.add_argument("--capture-seconds", type=float, default=DEFAULT_CAPTURE_SECONDS)
    parser.add_argument("--stale-seconds", type=float, default=DEFAULT_STALE_SECONDS)
    parser.add_argument("--stale-timeout-seconds", type=float, default=DEFAULT_STALE_TIMEOUT_SECONDS)
    parser.add_argument("--sender-warmup-seconds", type=float, default=0.6)
    parser.add_argument("--json", action="store_true", help="Print machine-readable result")
    args = parser.parse_args(argv)
    if not args.dry_run and not args.execute:
        args.dry_run = True
    return args


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    template = _read_default_udp_template()
    receiver_contract = validate_receiver_pipeline(
        template,
        url=f"udp://127.0.0.1:{args.port}",
        width=args.width,
        height=args.height,
    )
    if not receiver_contract["valid"]:
        result = {
            "status": "failed",
            "mode": "execute" if args.execute else "dry-run",
            "claim_boundary": CLAIM_BOUNDARY,
            "reason": "receiver_pipeline_contract_failed",
            "receiver_contract": receiver_contract,
        }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Receiver pipeline contract failed: {receiver_contract}", file=sys.stderr)
        return 1

    try:
        if args.execute:
            result = _run_execute(args, template, receiver_contract)
        else:
            result = build_dry_run_result(args, template, receiver_contract)
    except Exception as exc:
        result = {
            "status": "failed",
            "mode": "execute" if args.execute else "dry-run",
            "claim_boundary": CLAIM_BOUNDARY,
            "reason": str(exc),
        }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']}: {CLAIM_BOUNDARY}")

    if result["status"] == "incomplete":
        return 3
    if result["status"] == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
