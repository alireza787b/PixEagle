"""Pinned, network-isolated simulator host lifecycle extracted from the historical QGC harness.

S10 cleanup debt: consolidate remaining QGC/native launchers on this host boundary.
This module owns only isolated processes/artifacts, never follower calculations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
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


def verified_simulation_build(path: Path, *, repository: Path | None = None) -> tuple[str, dict, dict]:
    """Select one strict builder from the manifest; no caller-supplied simulator kind."""
    from tools.sih_baseline import validate_build_manifest

    raw = Path(path).read_bytes()
    manifest = json.loads(raw)
    kinds = {"pixeagle_sih_build": "sih", "pixeagle_gazebo_build": "gazebo"}
    kind = manifest.get("kind") if isinstance(manifest, dict) else None
    simulator = kinds.get(kind) if isinstance(kind, str) else None
    if simulator is None:
        raise ValueError("Unknown simulation build manifest kind")
    selection = {} if simulator == "sih" else {"simulator": simulator}
    if repository is not None:
        selection["repository"] = repository
    verified = validate_build_manifest(path, **selection)
    if verified["manifest_sha256"] != hashlib.sha256(raw).hexdigest():
        raise ValueError("Simulation manifest changed during verification")
    return simulator, verified, manifest


def _simulation_model(simulator: str, manifest: dict | None, requested: str | None, *, scenario=None) -> str:
    if simulator == "gazebo":
        if not isinstance(manifest, dict) or not isinstance(manifest.get("build"), dict):
            raise ValueError("Gazebo requires a verified Gazebo build manifest")
        expected = "gz_" + (scenario["descriptor"] if scenario else manifest["build"])["model"]
        if requested is not None and requested != expected:
            raise ValueError("Requested simulator model differs from the verified Gazebo manifest")
        return expected
    model = "sihsim_quadx" if requested is None else requested
    if simulator != "sih" or not isinstance(model, str) or not model.startswith("sihsim_"):
        raise ValueError("Gazebo requires a verified Gazebo build manifest")
    return model


def simulation_launch_args(simulator: str, baseline: dict, manifest: dict | None, *,
                           runtime: Path, token: str, name: str, model: str | None = None,
                           startup_parameters: dict[str, str] | None = None,
                           gazebo_scenario: str | None = None, desktop_network_id: str | None = None,
                           published_tcp_ports: tuple[int, ...] = ()) -> list[str]:
    """Stage a private rootfs and plan the owned primary; never launch it.

    Callers own the fixture parameter allowlist and native bounds. Values here
    are literal finite numbers consumed by the pinned rcS before Navigator.
    """
    network = "none"
    publications = []
    if desktop_network_id is not None:
        network = owned_internal_network_info(desktop_network_id, token)["Id"]
    if (published_tcp_ports and desktop_network_id is None
            or any(type(port) is not int or not 1024 <= port <= 65535 for port in published_tcp_ports)
            or len(set(published_tcp_ports)) != len(published_tcp_ports)):
        raise ValueError("Desktop TCP ports require an owned internal network and unique unprivileged ports")
    for port in published_tcp_ports:
        publications.extend(["--publish", f"127.0.0.1:{port}:{port}/tcp"])
    scenario = None
    if gazebo_scenario is not None:
        from tools.gazebo_scenario import verified_scenario
        if simulator != "gazebo" or manifest is None:
            raise ValueError("A runtime scenario requires a verified Gazebo build")
        scenario = verified_scenario(gazebo_scenario, baseline, manifest)
    model = _simulation_model(simulator, manifest, model, scenario=scenario)
    options = []
    source_build = baseline.get("kind") in {"verified_source_build", "verified_gazebo_source_build"}
    if startup_parameters and not source_build:
        raise ValueError("Startup parameters require a verified source build")
    for key, value in (startup_parameters or {}).items():
        if (not isinstance(key, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", key) is None
                or not isinstance(value, str) or re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value) is None
                or not math.isfinite(float(value))):
            raise ValueError("Startup parameter requires a literal name and finite numeric value")
    if simulator == "gazebo":
        if baseline.get("kind") != "verified_gazebo_source_build" or manifest is None:
            raise ValueError("Gazebo requires a verified Gazebo build manifest")
        spec = manifest["build"]
        image = baseline["image_id"]
        world = scenario["descriptor"]["world"] if scenario else spec["world"]
        for key, value in {"GZ_IP": "127.0.0.1", "GZ_PARTITION": token,
                           "GZ_DISTRO": spec["distribution"], "PX4_GZ_WORLD": world,
                           "PX4_GZ_NO_FOLLOW": "1", "HEADLESS": "1"}.items():
            options.extend(["-e", f"{key}={value}"])
        if scenario:
            from tools.gazebo_scenario import scenario_environment
            if set(startup_parameters or {}) & scenario["expected_parameters"].keys():
                raise ValueError("Startup parameters cannot override Gazebo scenario identity")
            for key, value in scenario_environment(scenario).items():
                options.extend(["-e", f"{key}={value}"])
    elif simulator == "sih" and model.startswith("sihsim_"):
        image = baseline.get("image_id", baseline.get("reference"))
    else:
        raise ValueError("Unsupported simulator launch plan")
    if source_build:
        if scenario:
            from tools.gazebo_scenario import stage_scenario_resources
            options.extend(stage_scenario_resources(scenario, runtime))
        work = runtime.resolve() / "simulator"
        for directory in ("home", "rootfs"):
            (work / directory).mkdir(parents=True, mode=0o700, exist_ok=True)
        options.extend(["--user", f"{os.getuid()}:{os.getgid()}",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--mount", f"type=bind,src={work},dst=/work", "--workdir", "/work/rootfs",
            "-e", "HOME=/work/home"])
    for key, value in sorted((startup_parameters or {}).items()):
        options.extend(["--env", f"PX4_PARAM_{key}={value}"])
    return ["docker", "run", "-d", "-i", "--name", name, "--label", f"{LABEL}={token}",
            "--network", network, *publications, "-e", f"PX4_SIM_MODEL={model}", *options, image,
            *(["-i", "0", "-w", "/work/rootfs", "/opt/px4/etc"] if source_build else [])]


def owned_internal_network_info(network_id: str, token: str) -> dict:
    """Desktop access uses an owner-bound internal bridge; never the host LAN."""
    if not token or not isinstance(network_id, str) or re.fullmatch(r"[0-9a-f]{64}", network_id) is None:
        raise ValueError("Desktop network requires its original full ID and ownership token")
    records = json.loads(command("docker", "network", "inspect", network_id))
    if len(records) != 1:
        raise RuntimeError("Desktop network identity is ambiguous")
    info = records[0]
    if (info.get("Id") != network_id or (info.get("Labels") or {}).get(LABEL) != token
            or info.get("Driver") != "bridge" or info.get("Internal") is not True
            or info.get("EnableIPv6") is True):
        raise RuntimeError("Desktop network isolation or ownership changed")
    return info


def create_owned_internal_network(name: str, token: str) -> str:
    network_id = command("docker", "network", "create", "--driver", "bridge", "--internal",
                         "--label", f"{LABEL}={token}", name)
    owned_internal_network_info(network_id, token)
    return network_id


def remove_owned_internal_network(network_id: str, token: str) -> None:
    info = owned_internal_network_info(network_id, token)
    if info.get("Containers"):
        raise RuntimeError("Desktop network still has attached containers")
    command("docker", "network", "rm", network_id)


def _require_owned_container(info: dict, token: str, container_id: str | None = None) -> dict:
    if (not token or (info.get("Config", {}).get("Labels") or {}).get(LABEL) != token
            or (container_id is not None and info.get("Id") != container_id)):
        raise RuntimeError("Refusing cleanup: container ownership changed")
    return info


def owned_container_info(container_id: str, token: str) -> dict:
    """Inspect only the original immutable container ID and its ownership token."""
    if not isinstance(container_id, str) or re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise ValueError("Owned container requires its original full container ID")
    records = json.loads(command("docker", "inspect", container_id))
    if len(records) != 1:
        raise RuntimeError("Refusing cleanup: container identity is ambiguous")
    return _require_owned_container(records[0], token, container_id)


def stop_owned_container(container_id: str, token: str, *, timeout: int = 10) -> dict:
    """Stop an original owned container; retain it and return verified final state."""
    if type(timeout) is not int or not 1 <= timeout <= 45:
        raise ValueError("Owned container stop timeout must be between 1 and 45 seconds")
    before = owned_container_info(container_id, token)
    if before["State"]["Running"]:
        command("docker", "stop", "--time", str(timeout), container_id, timeout=timeout + 5)
    after = owned_container_info(container_id, token)
    if after["State"]["Running"]:
        raise RuntimeError("Owned container did not stop")
    return after


def host(args: argparse.Namespace, *, driver_path: Path, configure=None) -> None:
    if not args.execute:
        raise SystemExit("Use --execute only for this isolated simulated-aircraft qualification.")
    repo = args.backend_repo.resolve()
    runtime = args.output.resolve()
    if runtime.exists():
        raise SystemExit("Use a new output directory; existing evidence is never overwritten.")
    baseline_manifest = getattr(args, "simulation_build_manifest", None)
    if baseline_manifest is not None:
        simulator, baseline, build_manifest = verified_simulation_build(Path(baseline_manifest))
        px4_image = baseline["image_id"]
    else:
        simulator, build_manifest = "sih", None
        px4_image = PX4_IMAGE
        baseline = {"kind": "compatibility_image", "reference": px4_image}
    simulator_model = _simulation_model(simulator, build_manifest, getattr(args, "simulator_model", None))
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
        "simulator_model": simulator_model,
        "simulator": simulator,
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
        "px4_image": json.loads(command("docker", "image", "inspect", px4_image))[0]["Id"],
        "sih_baseline": baseline,
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
        command(*simulation_launch_args(simulator, baseline, build_manifest,
            runtime=runtime, token=token, name=names[0], model=simulator_model))
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
            info = _require_owned_container(json.loads(probe.stdout)[0], token)
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
        "find /work /root /home /tmp /workspace /PX4-Autopilot /src/PX4-Autopilot -type f -name '*.ulg' 2>/dev/null | head -20",
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
