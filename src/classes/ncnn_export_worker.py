"""Cgroup-contained Ultralytics NCNN export worker invoked by ModelManager."""

from __future__ import annotations

import argparse
import json
import os
import signal
import stat
import sys
from pathlib import Path
from typing import Dict


def _write_result(path: Path, payload: dict) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        offset = 0
        while offset < len(encoded):
            offset += os.write(descriptor, encoded[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _apply_resource_controls(
    *,
    cpu_seconds: int,
    address_space_bytes: int,
    file_size_bytes: int,
    open_files: int,
    processes: int,
) -> Dict[str, Dict[str, int]]:
    """Apply required POSIX rlimits before any third-party module is imported."""
    if os.name != "posix":
        raise SystemExit("NCNN export process controls require POSIX")
    try:
        import resource
    except ImportError as exc:
        raise SystemExit("POSIX resource controls are unavailable") from exc

    requested = {
        "address_space_bytes": ("RLIMIT_AS", address_space_bytes),
        "core_bytes": ("RLIMIT_CORE", 0),
        "cpu_seconds": ("RLIMIT_CPU", cpu_seconds),
        "file_size_bytes": ("RLIMIT_FSIZE", file_size_bytes),
        "open_files": ("RLIMIT_NOFILE", open_files),
        "processes": ("RLIMIT_NPROC", processes),
    }
    applied: Dict[str, Dict[str, int]] = {}
    for label, (resource_name, requested_limit) in requested.items():
        if not isinstance(requested_limit, int) or requested_limit < 0:
            raise SystemExit(f"Invalid NCNN resource limit: {label}")
        resource_id = getattr(resource, resource_name, None)
        if resource_id is None:
            raise SystemExit(f"Required NCNN resource limit is unavailable: {resource_name}")
        _, current_hard = resource.getrlimit(resource_id)
        if current_hard == resource.RLIM_INFINITY:
            applied_limit = requested_limit
        else:
            applied_limit = min(requested_limit, int(current_hard))
        if label != "core_bytes" and applied_limit <= 0:
            raise SystemExit(f"Required NCNN resource limit is unusable: {label}")
        resource.setrlimit(resource_id, (applied_limit, applied_limit))
        observed_soft, observed_hard = resource.getrlimit(resource_id)
        if observed_soft != applied_limit or observed_hard != applied_limit:
            raise SystemExit(f"Failed to establish NCNN resource limit: {label}")
        applied[label] = {"hard": int(observed_hard), "soft": int(observed_soft)}
    return applied


def _validate_source(source: Path, workspace: Path) -> None:
    source_stat = os.lstat(source)
    if (
        source.parent != workspace
        or source.suffix.lower() != ".pt"
        or not stat.S_ISREG(source_stat.st_mode)
        or source_stat.st_uid != os.geteuid()
        or source_stat.st_nlink != 1
        or stat.S_IMODE(source_stat.st_mode) != 0o600
        or source_stat.st_size <= 0
    ):
        raise SystemExit("NCNN worker received an unsafe source artifact")


def _contain_command(argv: list[str]) -> int:
    """Stop after exec so the parent can move this PID into its dedicated cgroup."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--contain-command", action="store_true")
    parser.add_argument("--ready-fd", required=True, type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command or args.ready_fd < 3 or os.name != "posix":
        raise SystemExit("Invalid NCNN export cgroup admission command")
    try:
        ready_stat = os.fstat(args.ready_fd)
        if not stat.S_ISFIFO(ready_stat.st_mode):
            raise SystemExit("NCNN export admission descriptor is not a pipe")
        if os.write(args.ready_fd, b"ready\n") != len(b"ready\n"):
            raise SystemExit("NCNN export admission handshake was incomplete")
    finally:
        os.close(args.ready_fd)
    os.kill(os.getpid(), signal.SIGSTOP)
    os.execvpe(command[0], command, os.environ)
    raise SystemExit("NCNN export admission exec unexpectedly returned")


def main() -> int:
    if "--contain-command" in sys.argv[1:]:
        return _contain_command(sys.argv[1:])
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--source", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--control-result", required=True)
    parser.add_argument("--cpu-seconds", required=True, type=int)
    parser.add_argument("--address-space-bytes", required=True, type=int)
    parser.add_argument("--file-size-bytes", required=True, type=int)
    parser.add_argument("--open-files", required=True, type=int)
    parser.add_argument("--processes", required=True, type=int)
    args = parser.parse_args()

    source = Path(args.source).resolve(strict=True)
    result = Path(args.result).resolve(strict=False)
    control_result = Path(args.control_result).resolve(strict=False)
    workspace = Path.cwd().resolve(strict=True)
    if (
        source.parent != workspace
        or result.parent != workspace
        or control_result.parent != workspace
        or result == control_result
    ):
        raise SystemExit("NCNN worker paths must be direct children of one workspace")
    if (
        result.exists()
        or result.is_symlink()
        or control_result.exists()
        or control_result.is_symlink()
    ):
        raise SystemExit("NCNN worker received an unsafe source or result path")

    os.umask(0o077)
    if os.getpgrp() != os.getpid() or os.getsid(0) != os.getpid():
        raise SystemExit("NCNN worker is not the leader of a private process group/session")
    _validate_source(source, workspace)
    applied_limits = _apply_resource_controls(
        cpu_seconds=args.cpu_seconds,
        address_space_bytes=args.address_space_bytes,
        file_size_bytes=args.file_size_bytes,
        open_files=args.open_files,
        processes=args.processes,
    )
    _write_result(
        control_result,
        {
            "limits": applied_limits,
            "pid": os.getpid(),
            "process_group_id": os.getpgrp(),
            "schema_version": 1,
            "session_id": os.getsid(0),
        },
    )

    os.environ["YOLO_AUTOINSTALL"] = "false"
    os.environ["YOLO_OFFLINE"] = "true"
    os.environ["YOLO_CONFIG_DIR"] = str(workspace / ".ultralytics")

    from ultralytics import YOLO

    model = YOLO(str(source))
    exported = model.export(format="ncnn")
    exported_path = getattr(exported, "path", exported)
    _write_result(result, {"returned_path": str(exported_path)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
