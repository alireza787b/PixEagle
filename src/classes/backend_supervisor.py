"""Owned Linux backend supervision shared by hardware and isolated SIH launchers."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tempfile
import uuid

CONTRACT = "owned-exit42-v1"


def supervisor_available() -> bool:
    """The supported launcher must still be this backend's immediate parent."""
    if os.name != "posix" or os.environ.get("PIXEAGLE_RESTART_SUPERVISOR") != CONTRACT:
        return False
    try:
        parent = int(os.environ.get("PIXEAGLE_RESTART_SUPERVISOR_PID", "0"))
        if parent <= 1 or parent != os.getppid():
            return False
        os.kill(parent, 0)
        return True
    except (ValueError, OSError):
        return False


def validate_sih_routes(config):
    px4 = config.get("PX4", {})
    mavlink = config.get("MAVLink", {})
    if (px4.get("SYSTEM_ADDRESS") != "udpin://127.0.0.1:14540"
            or px4.get("EXTERNAL_MAVSDK_SERVER") is not True
            or px4.get("MAVSDK_SERVER_ADDRESS") != "127.0.0.1"
            or px4.get("MAVSDK_SERVER_PORT") != 50051
            or mavlink.get("MAVLINK_ENABLED") is not True
            or mavlink.get("MAVLINK_HOST") != "127.0.0.1"
            or mavlink.get("MAVLINK_PORT") != 8088):
        raise ValueError("SIH requires isolated loopback command and telemetry routes")


def supervise(root: Path, *, log: Path | None = None, sih: bool = False) -> int:
    child = None
    stopping = False
    stop_deadline = None

    def terminate(signum, _frame):
        nonlocal stopping, stop_deadline
        stopping = True
        stop_deadline = time.monotonic() + 10.0
        if child is not None and child.poll() is None:
            child.send_signal(signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, terminate)
    while not stopping:
        if sih:
            import yaml

            path = root / "configs/config.yaml"
            config = yaml.safe_load(path.read_text(encoding="utf-8"))
            validate_sih_routes(config)
            config["FOLLOWER_CIRCUIT_BREAKER"] = True
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as staged:
                os.chmod(staged.name, 0o600)
                staged.write(yaml.safe_dump(config, sort_keys=False))
                staged.flush()
                os.fsync(staged.fileno())
            os.replace(staged.name, path)
        environment = os.environ.copy()
        environment.pop("PIXEAGLE_SIH_REPLAY_BINDING", None)
        if sih:
            environment["PIXEAGLE_SIH_REPLAY_BINDING"] = str(root / "logs/sih-replay-binding.json")
        environment.update(
            PIXEAGLE_RESTART_SUPERVISOR=CONTRACT,
            PIXEAGLE_RESTART_SUPERVISOR_PID=str(os.getpid()),
            PIXEAGLE_RUN_ID=f"backend_{uuid.uuid4().hex}",
        )
        output = None
        if log is not None:
            log.parent.mkdir(parents=True, exist_ok=True)
            run_log = log.with_name(f"{log.stem}-{environment['PIXEAGLE_RUN_ID']}{log.suffix}")
            output = run_log.open("xb")
            if log.is_symlink() or log.exists():
                if log.is_symlink():
                    log.unlink()
                else:
                    log.rename(log.with_name(f"{log.stem}-previous-{uuid.uuid4().hex}{log.suffix}"))
            log.symlink_to(run_log.name)
        try:
            child = subprocess.Popen(
                [sys.executable, "-u", str(root / "src/main.py")],
                cwd=root, env=environment, stdout=output, stderr=subprocess.STDOUT if output else None,
            )
            while True:
                try:
                    code = child.wait(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    if stop_deadline is not None and time.monotonic() >= stop_deadline:
                        child.kill()

        finally:
            if output is not None:
                output.close()
        if stopping or code != 42:
            return 128 - code if code < 0 else code
        print("PixEagle requested backend restart; sidecars remain running.", flush=True)
        time.sleep(2)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--sih", action="store_true")
    args = parser.parse_args()
    raise SystemExit(supervise(args.root.resolve(), log=args.log, sih=args.sih))
