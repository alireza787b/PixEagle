#!/usr/bin/env python3
"""Terminate one proven PixEagle process through a stable Linux pidfd."""

from __future__ import annotations

import argparse
import os
import select
import signal
import stat
import sys
from pathlib import Path


class OwnershipError(RuntimeError):
    """The requested process identity could not be proven."""


def process_start_token(pid: int) -> str:
    line = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    fields = line.rsplit(") ", 1)[1].split()
    token = fields[19]
    if not token.isdecimal():
        raise OwnershipError("process start token is invalid")
    return token


def process_environment(pid: int) -> dict[str, str]:
    raw = Path(f"/proc/{pid}/environ").read_bytes()
    environment: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        environment[key.decode("utf-8", "strict")] = value.decode("utf-8", "strict")
    return environment


def pidfd_exited(descriptor: int, timeout_seconds: float) -> bool:
    poller = select.poll()
    poller.register(descriptor, select.POLLIN | select.POLLHUP | select.POLLERR)
    return bool(poller.poll(max(0, round(timeout_seconds * 1000))))


def prove_identity(args: argparse.Namespace, descriptor: int) -> None:
    try:
        process_path = Path(f"/proc/{args.pid}")
        metadata = process_path.stat()
        token = process_start_token(args.pid)
        environment = process_environment(args.pid)
    except (FileNotFoundError, ProcessLookupError):
        if pidfd_exited(descriptor, 0):
            return
        raise OwnershipError("process identity disappeared before verification") from None
    except (IndexError, OSError, UnicodeError, ValueError) as exc:
        raise OwnershipError(f"cannot inspect process identity: {exc}") from exc

    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != args.expected_uid:
        raise OwnershipError("process owner does not match")
    if token != args.start_token:
        raise OwnershipError("process start token does not match")

    expected_root = str(Path(args.project_root).resolve(strict=True))
    if environment.get("PIXEAGLE_PROJECT_ROOT") != expected_root:
        raise OwnershipError("process checkout marker does not match")
    if environment.get("PIXEAGLE_RUNTIME_MODE") != args.runtime_mode:
        raise OwnershipError("process runtime mode does not match")
    if args.run_id and environment.get("PIXEAGLE_RUN_ID") != args.run_id:
        raise OwnershipError("process run ID does not match")


def terminate(args: argparse.Namespace) -> int:
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise OwnershipError("this Linux/Python runtime does not provide pidfd signaling")
    if args.pid in {os.getpid(), os.getppid()}:
        raise OwnershipError("refusing to signal the terminator or its parent")

    try:
        descriptor = os.pidfd_open(args.pid, 0)
    except ProcessLookupError:
        return 0
    except OSError as exc:
        raise OwnershipError(f"cannot open pidfd for PID {args.pid}: {exc}") from exc

    try:
        os.set_inheritable(descriptor, False)
        prove_identity(args, descriptor)
        if pidfd_exited(descriptor, 0):
            return 0
        signal.pidfd_send_signal(descriptor, signal.SIGTERM)
        if pidfd_exited(descriptor, args.term_timeout):
            return 0
        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        if not pidfd_exited(descriptor, args.kill_timeout):
            raise OwnershipError("process did not exit after pidfd SIGKILL")
        return 0
    except ProcessLookupError:
        return 0
    finally:
        os.close(descriptor)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--pid", type=int, required=True)
    value.add_argument("--start-token", required=True)
    value.add_argument("--expected-uid", type=int, required=True)
    value.add_argument("--project-root", required=True)
    value.add_argument("--runtime-mode", choices=("manual", "service"), required=True)
    value.add_argument("--run-id", default="")
    value.add_argument("--term-timeout", type=float, default=3.0)
    value.add_argument("--kill-timeout", type=float, default=2.0)
    return value


def main() -> int:
    args = parser().parse_args()
    if args.pid <= 1 or not args.start_token.isdecimal():
        raise OwnershipError("invalid PID or start token")
    if args.expected_uid < 0 or args.term_timeout < 0 or args.kill_timeout < 0:
        raise OwnershipError("invalid owner or timeout")
    return terminate(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OwnershipError as exc:
        print(f"PixEagle process ownership error: {exc}", file=sys.stderr)
        raise SystemExit(73) from exc
