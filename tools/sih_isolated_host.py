"""Pinned, network-isolated SIH host lifecycle extracted from the historical QGC harness.

S10 cleanup debt: consolidate remaining QGC/native launchers on this host boundary.
This module owns only isolated processes/artifacts, never follower calculations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time
import uuid

PX4_IMAGE = "px4io/px4-sitl@sha256:fd6d93dc2705482aeb64ea26fdf16185d8a511010fdc53e26305f10d91855865"
WORKER_IMAGE = "sha256:ecfaf2358be090447ff9948397075ce76cefff3a152fbfab006a2d26495ea14b"
LABEL = "org.pixeagle.qgc.gimbal_evidence"


HOST_SOURCE = {
    "repository": "qgroundcontrol-pixeagle-webrtc-port",
    "revision": "c7cfdfa137b9f23ed366aa185c522502a653c4ff",
    "path": "custom-pixeagle/validation/run-gimbal-sih-evidence.py",
    "sha256": "e7abec53d19f3cd8050b64aabae281f47515aa6b6eca55747d4ceb7a909b241d",
    "extracted_functions": ["command", "write_json", "host"],
    "cleanup_debt": "S10: consolidate other SIH launchers on the shared isolated host lifecycle",
}

def command(*args: str, timeout: float = 30) -> str:
    return subprocess.check_output(args, text=True, timeout=timeout).strip()


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def host(args: argparse.Namespace, *, driver_path: Path, configure=None) -> None:
    if not args.execute:
        raise SystemExit("Use --execute only for this isolated simulated-aircraft qualification.")
    repo = args.backend_repo.resolve()
    runtime = args.output.resolve()
    if runtime.exists():
        raise SystemExit("Use a new output directory; existing evidence is never overwritten.")
    for path in (
        repo / "src/classes/app_controller.py",
        args.python,
        args.bin_dir / "mavsdk_server_bin",
        args.bin_dir / "mavlink2rest",
    ):
        if not path.is_file():
            raise SystemExit(f"Required dependency is missing: {path}")
    runtime.mkdir(parents=True, mode=0o700)
    shutil.copytree(
        repo / "src", runtime / "backend/src", ignore=shutil.ignore_patterns("__pycache__")
    )
    (runtime / "backend/tools").mkdir()
    shutil.copyfile(
        repo / "tools/sitl_gimbal_geometry_fixture.py",
        runtime / "backend/tools/sitl_gimbal_geometry_fixture.py",
    )
    for relative in command("git", "-C", str(repo), "ls-files", "configs").splitlines():
        source = repo / relative
        destination = runtime / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    import yaml

    config = yaml.safe_load((runtime / "configs/config_default.yaml").read_text(encoding="utf-8"))
    config["PX4"].update(
        EXTERNAL_MAVSDK_SERVER=True,
        MAVSDK_SERVER_ADDRESS="127.0.0.1",
        MAVSDK_SERVER_PORT=50051,
        SYSTEM_ADDRESS="udpin://127.0.0.1:14540",
    )
    config["Follower"]["USE_MAVLINK2REST"] = True
    config["MAVLink"].update(MAVLINK_ENABLED=True, MAVLINK_HOST="127.0.0.1", MAVLINK_PORT=8088)
    config["Follower"]["FOLLOWER_MODE"] = args.follower
    config["Follower"]["FOLLOWER_EXECUTION_MODE"] = "PX4"
    config["Follower"]["FollowerOverrides"]["GM_VELOCITY_VECTOR"]["LATERAL_GUIDANCE_MODE"] = (
        "coordinated_turn"
    )
    config["GimbalTracker"].update(
        MOUNT_TYPE=args.mount, ENABLED=False, CONTROL_ENABLED=False, UDP_HOST="127.0.0.1"
    )
    config["FOLLOWER_CIRCUIT_BREAKER"] = True
    if configure is not None:
        configure(config)
    if getattr(args, "session_controls", False):
        args.worker_extra_args = ["--session-controls"]
    (runtime / "configs/config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    (runtime / "backend/configs").mkdir()
    names = [f"pixeagle-evidence-{uuid.uuid4().hex[:10]}-{suffix}" for suffix in ("px4", "worker")]
    token = uuid.uuid4().hex
    manifest = {
        "kind": getattr(args, "evidence_kind", "mc-world-target-production-dispatch-sih"),
        "host_source": HOST_SOURCE,
        "follower": args.follower,
        "mount": args.mount,
        "network": "none",
        "host_ports": [],
        "physical_camera": False,
        "native_camera_selection_qualified": False,
        "source_head": command("git", "-C", str(repo), "rev-parse", "HEAD"),
        "worktree_dirty": bool(command("git", "-C", str(repo), "status", "--porcelain")),
        "source_checksums": {
            str(path.relative_to(runtime / "backend")): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted((runtime / "backend").rglob("*.py"))
        },
        "fixture_sha256": hashlib.sha256(
            (runtime / "backend/tools/sitl_gimbal_geometry_fixture.py").read_bytes()
        ).hexdigest(),
        "config_sha256": hashlib.sha256((runtime / "configs/config.yaml").read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256((driver_path or Path(__file__)).read_bytes()).hexdigest(),
        "simulator_model": getattr(args, "simulator_model", "sihsim_quadx"),
        "binary_checksums": {
            name: hashlib.sha256((args.bin_dir / name).read_bytes()).hexdigest()
            for name in ("mavsdk_server_bin", "mavlink2rest")
        },
        "python_packages": json.loads(
            command(
                str(args.python),
                "-c",
                "import importlib.metadata,json; print(json.dumps(sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions())))",
            )
        ),
        "px4_image": json.loads(command("docker", "image", "inspect", PX4_IMAGE))[0]["Id"],
        "worker_image": json.loads(command("docker", "image", "inspect", WORKER_IMAGE))[0]["Id"],
    }
    write_json(runtime / "manifest.json", manifest)
    worker_script = runtime / "driver.py"
    shutil.copyfile((driver_path or Path(__file__)).resolve(), worker_script)
    shutil.copyfile(Path(__file__).resolve(), runtime / "sih_evidence_runtime.py")
    artifact_errors = []
    entry = runtime / "entry.sh"
    worker_extra = shlex.join(getattr(args, "worker_extra_args", []))
    entry.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        '"$EVIDENCE_BIN/mavlink2rest" -c udpin:127.0.0.1:14550 -s 127.0.0.1:8088 > /work/evidence/mavlink2rest.log 2>&1 &\n'
        'rest_pid=$!\n"$EVIDENCE_BIN/mavsdk_server_bin" -p 50051 udpin://127.0.0.1:14540 > /work/evidence/mavsdk.log 2>&1 &\n'
        'sdk_pid=$!\ntrap \'kill "$rest_pid" "$sdk_pid" 2>/dev/null || true\' EXIT\n'
        '"$EVIDENCE_PYTHON" /work/driver.py --worker --follower "$EVIDENCE_FOLLOWER" --mount "$EVIDENCE_MOUNT"'
        + (f" {worker_extra}" if worker_extra else "")
        + "\n",
        encoding="utf-8",
    )
    try:
        command(
            "docker",
            "run",
            "-d",
            "-i",
            "--name",
            names[0],
            "--label",
            f"{LABEL}={token}",
            "--network",
            "none",
            "-e",
            f"PX4_SIM_MODEL={getattr(args, 'simulator_model', 'sihsim_quadx')}",
            PX4_IMAGE,
        )
        python_root = args.python.absolute().parent.parent
        command(
            "docker",
            "run",
            "-d",
            "--name",
            names[1],
            "--label",
            f"{LABEL}={token}",
            "--network",
            f"container:{names[0]}",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "LD_LIBRARY_PATH=/mnt/hostlibs",
            "-e",
            "PIXEAGLE_PROJECT_ROOT=/work/evidence",
            "-e",
            "PYTHONPATH=/work/backend/src:/work/backend/tools",
            "-e",
            f"EVIDENCE_OWNER={token}",
            "-e",
            f"EVIDENCE_PYTHON={args.python}",
            "-e",
            f"EVIDENCE_BIN={args.bin_dir}",
            "-e",
            f"EVIDENCE_FOLLOWER={args.follower}",
            "-e",
            f"EVIDENCE_MOUNT={args.mount}",
            "-v",
            f"{runtime / 'backend'}:/work/backend:ro",
            "-v",
            f"{runtime / 'configs'}:/work/backend/configs",
            "-v",
            f"{runtime}:/work/evidence",
            "-v",
            f"{worker_script}:/work/driver.py:ro",
            "-v",
            f"{python_root}:{python_root}:ro",
            "-v",
            f"{args.bin_dir}:{args.bin_dir}:ro",
            "-v",
            "/usr/lib/x86_64-linux-gnu:/mnt/hostlibs:ro",
            "-v",
            f"{args.opencv_lib}:{args.opencv_lib}:ro",
            "-w",
            "/work/evidence",
            WORKER_IMAGE,
            "bash",
            "/work/evidence/entry.sh",
        )
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            state = json.loads(command("docker", "inspect", names[1]))[0]["State"]
            if not state["Running"]:
                with (runtime / "worker.log").open("w") as log:
                    subprocess.run(
                        ["docker", "logs", names[1]],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
                if state["ExitCode"] != 0:
                    raise RuntimeError(f"SIH worker failed; inspect {runtime / 'worker.log'}")
                print(f"SIH worker completed; collecting artifacts: {runtime / 'result.json'}")
                return
            time.sleep(1)
        raise RuntimeError("SIH qualification exceeded its 240-second deadline")
    finally:
        for name in reversed(names):
            probe = subprocess.run(
                ["docker", "inspect", name], capture_output=True, text=True, check=False
            )
            if probe.returncode != 0:
                continue
            info = json.loads(probe.stdout)[0]
            if info["Config"]["Labels"].get(LABEL) != token:
                raise RuntimeError(f"Refusing cleanup: container ownership changed for {name}")
            if name == names[0]:
                try:
                    collect_px4_artifacts(name, runtime)
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    artifact_errors.append(str(exc))
            subprocess.run(
                ["docker", "logs", name],
                stdout=(runtime / f"{name}.log").open("w"),
                stderr=subprocess.STDOUT,
                check=False,
            )
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, check=True)
        write_json(runtime / "artifact-collection.json", {"passed": not artifact_errors, "errors": artifact_errors})
        if artifact_errors:
            result_path = runtime / "result.json"
            if result_path.is_file():
                result = json.loads(result_path.read_text(encoding="utf-8"))
                result.update(passed=False, artifact_collection_errors=artifact_errors)
                write_json(result_path, result)
            raise RuntimeError("PX4 evidence artifact collection failed: " + "; ".join(artifact_errors))


def collect_px4_artifacts(container: str, output: Path) -> None:
    """Retain actual simulator logs before the owned container is removed."""
    paths = command(
        "docker", "exec", container, "sh", "-c",
        "find /root /home /tmp /workspace /PX4-Autopilot /src/PX4-Autopilot -type f -name '*.ulg' 2>/dev/null | head -20",
    ).splitlines()
    if not paths:
        raise RuntimeError("No PX4 ULog was retained by the isolated simulator")
    command("docker", "stop", "--time", "10", container, timeout=20)
    destination = output / "px4/ulog"
    destination.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(paths):
        subprocess.run(["docker", "cp", f"{container}:{path}", str(destination / f"{index}-{Path(path).name}")], check=True)
    write_json(output / "px4/ulog-manifest.json", {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in destination.iterdir()
    })
