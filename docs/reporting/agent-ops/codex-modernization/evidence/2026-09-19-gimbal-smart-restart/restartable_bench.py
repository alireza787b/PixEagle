"""Local bench supervisor: isolate settings and restart children only on exit 42.

Run from the repository with its .venv interpreter. --check validates setup without
starting video, API, gimbal or flight subsystems. No service installation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "reports/gimbal-manual-integration"
CONFIG = BENCH / "bench-config.yaml"


def validate_config():
    import yaml
    config = yaml.safe_load(CONFIG.read_text())
    required = (
        config.get("FOLLOWER_CIRCUIT_BREAKER") is True,
        config.get("Follower", {}).get("FOLLOWER_EXECUTION_MODE") == "COMMAND_PREVIEW",
        config.get("MAVLink", {}).get("MAVLINK_ENABLED") is False,
        config.get("Streaming", {}).get("HTTP_STREAM_HOST") == "127.0.0.1",
    )
    if not all(required):
        raise RuntimeError("Bench requires active circuit breaker, COMMAND_PREVIEW, disabled MAVLink, loopback API")
    return config


def configure_runtime():
    validate_config()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "src"))
    os.environ.setdefault("YOLO_AUTOINSTALL", "False")
    from classes.config_service import ConfigService
    # Set persistence paths BEFORE Parameters imports instantiate this singleton.
    ConfigService.CONFIG_PATH = str(CONFIG.relative_to(ROOT))
    ConfigService.BACKUP_DIR = str((BENCH / "config-backups").relative_to(ROOT))
    ConfigService.AUDIT_LOG_PATH = str((BENCH / "config-audit.json").relative_to(ROOT))
    ConfigService.SYNC_META_PATH = str((BENCH / "config-sync-meta.json").relative_to(ROOT))
    from classes.parameters import Parameters
    original_load = Parameters.load_config.__func__
    original_reload = Parameters.reload_config.__func__

    def bench_path(config_file):
        if config_file in (None, "configs/config.yaml"):
            return str(CONFIG)
        if Path(config_file).resolve() != CONFIG:
            raise ValueError("This bench runtime only loads its isolated bench configuration")
        return str(CONFIG)

    def load(cls, config_file=None, *args, **kwargs):
        validate_config()
        return original_load(cls, bench_path(config_file), *args, **kwargs)

    def reload_config(cls, config_file=None, *args, **kwargs):
        validate_config()
        return original_reload(cls, bench_path(config_file), *args, **kwargs)

    Parameters.load_config = classmethod(load)
    Parameters.reload_config = classmethod(reload_config)
    Parameters.load_config(strict_dependents=True)
    service = ConfigService.get_instance()
    if service._get_path(service.CONFIG_PATH).resolve() != CONFIG:
        raise RuntimeError("Config persistence is not isolated")
    return Parameters, service


def child(check=False):
    parameters, service = configure_runtime()
    if check:
        print(json.dumps({"configuration": str(CONFIG), "persistence": str(service._get_path(service.CONFIG_PATH)),
                          "rotation": parameters.FRAME_ROTATION_DEG,
                          "circuit_breaker": parameters.FOLLOWER_CIRCUIT_BREAKER,
                          "execution_mode": parameters.FOLLOWER_EXECUTION_MODE,
                          "mavlink_enabled": parameters.MAVLINK_ENABLED,
                          "runtime_started": False}, indent=2))
        return 0
    from classes.gimbal_interface import GimbalInterface
    output = (BENCH / "wire.jsonl").open("a")
    wire_lock = threading.Lock()
    original_send = GimbalInterface._send_command
    original_parse = GimbalInterface._parse_gimbal_packet

    def wire(kind, data, **extra):
        if isinstance(data, str):
            data = data.encode("ascii")
        with wire_lock:
            output.write(json.dumps(dict(time=time.time(), kind=kind, hex=data.hex(), **extra)) + "\n")
            output.flush()

    def send(self, data):
        result = original_send(self, data)
        wire("tx", data, sent=result)
        return result

    def parse(self, data, **kwargs):
        result = original_parse(self, data, **kwargs)
        wire("rx", data, accepted=result is not None, **kwargs)
        return result

    GimbalInterface._send_command = send
    GimbalInterface._parse_gimbal_packet = parse
    from main import main
    return main()


def supervise(command):
    stopped = threading.Event()
    process = None

    def stop(signum, _frame):
        stopped.set()
        if process is not None and process.poll() is None:
            process.send_signal(signum)

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        while not stopped.is_set():
            validate_config()
            print("Starting isolated PixEagle bench backend", flush=True)
            process = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
            code = process.wait()
            if stopped.is_set() or code != 42:
                return code if code >= 0 else 128 - code
            print("Bench restart requested (42); reloading saved bench configuration in 2 seconds", flush=True)
            stopped.wait(2)
        return 0
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.child or args.check:
        raise SystemExit(child(check=args.check))
    raise SystemExit(supervise([sys.executable, "-u", str(Path(__file__).resolve()), "--child"]))
