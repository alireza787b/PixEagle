#!/usr/bin/env python3
"""Native-only simulator Hold/transition baseline; no following or target publisher.

Extracted from the accepted prepare/observe/archive helpers identified in
native/baseline-runtime.json. Fresh startup parameters replace their historical
mid-run MIS write/barrier. The read-only visualizer is a separate tool.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from classes.aircraft_state import AircraftBinding, AircraftState, AirframePhase  # noqa: E402
from classes.native_guidance import NativeGuidanceClient  # noqa: E402
from tools import sih_isolated_host as shared  # noqa: E402
from tools.run_native_ownership_sih import parse_owned_samples  # noqa: E402
from tools.run_native_vector_sih import (PilotTransitionEvent, native_pilot_transition,  # noqa: E402
    stable_window, transition_source_contract, verify_simulator)

from tools.native_adapter_runtime import (adapter_launch_args, adapter_info, bootstrap_adapter,  # noqa: E402
    dds_session_ready, OwnedContainerLaunch)

GATE_M = 2.
FRESH_S = .75
MODELS = {"sihsim_xvert", "sihsim_standard_vtol", "gz_quadtailsitter"}
PARAMETERS = {"MIS_TAKEOFF_ALT", "VT_F_TRANS_DUR", "VT_B_TRANS_DUR", "VT_F_TR_OL_TM", "VT_ARSP_TRANS"}
NO_PITOT_VARIANT = "quadtailsitter-no-pitot-v1"
SYSTEM_PARAMETERS = "src/lib/systemlib/system_params.yaml"
FW_PARAMETERS = "src/modules/fw_rate_control/fw_rate_control_params.yaml"
DDS_STATUS_SOURCE = "src/modules/uxrce_dds_client/uxrce_dds_client.cpp"
ASSETS = ROOT / "native/baseline-runtime.json"
SCENARIOS = ROOT / "tools/native_baseline_scenarios"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def scenario(path):
    value = json.loads(Path(path).read_text())
    if (not isinstance(value, dict) or set(value) - {"resource_variant"} != {"schema_version", "model", "parameters", "forward", "back"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not isinstance(value["model"], str) or value["model"] not in MODELS
            or not isinstance(value["parameters"], dict)
            or not {"MIS_TAKEOFF_ALT"} <= value["parameters"].keys() <= PARAMETERS | {"SYS_HAS_NUM_ASPD"}
            or any(not finite(number) for number in value["parameters"].values())
            or value["parameters"]["MIS_TAKEOFF_ALT"] < 15.):
        raise ValueError("Explicit native VTOL fixture and stable-window altitude required")
    if "resource_variant" in value:
        if (value["resource_variant"] != NO_PITOT_VARIANT or value["model"] != "gz_quadtailsitter"
                or type(value["parameters"].get("SYS_HAS_NUM_ASPD")) is not int
                or value["parameters"]["SYS_HAS_NUM_ASPD"] != 0):
            raise ValueError("No-pitot resource variant requires the exact sensor-absent installation")
    elif "SYS_HAS_NUM_ASPD" in value["parameters"]:
        raise ValueError("Sensor installation override requires the no-pitot resource variant")
    for name in ("forward", "back"):
        event = value[name]
        if (not isinstance(event, dict) or set(event) != {"request_at_s", "capture_s"}
                or any(not finite(number) for number in event.values())
                or not 0 < event["request_at_s"] < event["capture_s"] <= 300):
            raise ValueError("Bounded explicit transition capture required")
    return value


def bootstrap_contract(source, fixture, assets):
    """Pinned rcS consumes literal overrides before any Navigator instance exists."""
    import yaml

    source_pins = assets["bootstrap_files"]
    no_pitot = fixture.get("resource_variant") == NO_PITOT_VARIANT
    if no_pitot:
        source_pins = source_pins | assets["no_pitot_sources"]
    for name, expected in source_pins.items():
        if digest(source / name) != expected:
            raise ValueError("Startup parameter ordering source changed: " + name)
    text = (source / "ROMFS/px4fmu_common/init.d-posix/rcS").read_text()
    if not (text.index('"PX4_PARAM_"*)') < text.index('. px4-rc.simulator')
            < text.index('commander start') < text.index('navigator start')):
        raise ValueError("Startup overlay must precede simulator, commander and Navigator")
    definitions = {}
    parameter_files = ["src/modules/navigator/mission_params.yaml",
                       "src/modules/vtol_att_control/vtol_att_control_params.yaml"]
    if no_pitot:
        parameter_files += [SYSTEM_PARAMETERS, FW_PARAMETERS]
    for name in parameter_files:
        for group in yaml.safe_load((source / name).read_text())["parameters"]:
            definitions.update(group["definitions"])
    for name, number in fixture["parameters"].items():
        definition = definitions[name]
        if number < definition.get("min", -math.inf) or number > definition.get("max", math.inf):
            raise ValueError("Fixture outside native parameter bounds: " + name)
    files = list((source / "ROMFS/px4fmu_common/init.d-posix/airframes").glob("*_" + fixture["model"]))
    if len(files) != 1:
        raise ValueError("One source-owned airframe required")
    contract = {"rcS_sha256": assets["bootstrap_files"]["ROMFS/px4fmu_common/init.d-posix/rcS"],
            "autostart": int(files[0].name.split("_", 1)[0]), "airframe_sha256": digest(files[0]),
            "dds_status_source_sha256": assets["bootstrap_files"][DDS_STATUS_SOURCE],
            "overlay_before_navigator": True, "midrun_parameter_write": False}
    if no_pitot:
        default = definitions["FW_USE_AIRSPD"]["default"]
        if not finite(default) or default != 1:
            raise ValueError("Reviewed native automatic airspeed control default required")
        reference = re.findall(r"(?m)^param set-default FW_AIRSPD_MIN\s+(\S+)\s*$", files[0].read_text())
        if reference != ["14"]:
            raise ValueError("Reviewed airframe forward-motion reference must remain literal FW_AIRSPD_MIN 14")
        contract.update(native_default_readback={"FW_USE_AIRSPD": default},
                        no_pitot_source_sha256=assets["no_pitot_sources"],
                        forward_motion_reference=dict(parameter="FW_AIRSPD_MIN", value=14., units="m/s",
                            source=str(files[0].relative_to(source)), source_sha256=digest(files[0])),
                        sensor_absence_scope="all uORB instances at each pre-flight-action probe only")
    return contract


def verify_adapter(bundle, manifest_path, assets):
    if digest(manifest_path) != assets["file_manifest_sha256"]:
        raise ValueError("Pinned adapter file manifest required")
    files = json.loads(Path(manifest_path).read_text())
    actual = {str(path.relative_to(bundle)) for path in bundle.rglob("*") if path.is_file() or path.is_symlink()}
    if len(files) != assets["bundle_files"] or actual != set(files):
        raise ValueError("Native adapter bundle file set changed")
    for name, pin in files.items():
        path = bundle / name
        if "symlink" in pin:
            valid = path.is_symlink() and str(path.readlink()) == pin["symlink"]
        else:
            valid = path.is_file() and not path.is_symlink() and digest(path) == pin["sha256"]
        if not valid:
            raise ValueError("Native adapter bundle changed: " + name)
    if digest(bundle / "adapter/pixeagle-native-guidance") != assets["adapter_sha256"]:
        raise ValueError("Native adapter executable changed")
    for name, expected in assets["compiled_inputs"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("Native adapter source changed: " + name)


def verify_adapter_image(assets):
    images = json.loads(shared.command("docker", "image", "inspect", assets["adapter_image"]))
    if (len(images) != 1 or images[0]["Id"] != assets["adapter_image"]
            or images[0]["Os"] != "linux" or images[0]["Architecture"] != "amd64"):
        raise ValueError("Locally available pinned native observer image required")


def readback(text, expected):
    for name, number in expected.items():
        values = re.findall(r"(?m)^\s*(?:(?:[x+*]\s*){1,2}\s+)?" + re.escape(name)
            + r"(?:\s+\[[^]\n]+\])?\s*:\s*(\S+)\s*$", text)
        if len(values) != 1 or Decimal(values[0]) != Decimal(str(number)):
            raise ValueError("Startup parameter readback mismatch: " + name)


def require_no_pursuit(packet, runtime_id):
    if (packet.get("runtime_id") != runtime_id or packet.get("owner_confirmed") is not False
            or packet.get("release_receipt") is not None or type(packet.get("publications")) is not int
            or packet.get("publications") != 0
            or packet.get("release_pending") is not False or packet.get("neutral_drain_active") is not False):
        raise ValueError("Native-only runtime must have no pursuit, owner or publications")


def sample(packet, binding, runtime_id, now):
    require_no_pursuit(packet, runtime_id)
    issues, state = [], None
    if packet.get("fresh") is not True:
        issues.append("reply_not_fresh")
    if packet.get("rescue_active") is not False:
        issues.append("rescue_or_unknown")
    try:
        state = AircraftState.from_payload(packet["aircraft_state"])
        if not state.fresh(now, FRESH_S) or state.rescue_active:
            issues.append("state_stale_or_rescue")
        if state.phase is AirframePhase.UNKNOWN:
            issues.append("phase_unknown")
    except (KeyError, TypeError, ValueError):
        issues.append("state_invalid_or_unavailable")
        state = None
    if state is not None and (state.binding != binding or not state.is_vtol):
        raise ValueError("Baseline aircraft identity changed")
    pose = (packet.get("vehicle_pose") or {}).get("vehicle_ned")
    z = pose[2] if isinstance(pose, list) and len(pose) == 3 and all(finite(x) for x in pose) else None
    if z is None:
        issues.append("pose_unavailable")
    return None if issues else state, z, issues


class Runtime:
    """Owns only this tool's two original token-labeled CIDs and private artifacts."""
    def __init__(self, args, fixture, simulator, baseline, manifest, assets):
        self.args, self.fixture, self.simulator = args, fixture, simulator
        self.baseline, self.manifest, self.assets = baseline, manifest, assets
        self.output, self.token = args.output.resolve(), uuid.uuid4().hex
        self.created, self.isolation = [], None
        self.primary = self.sidecar = self.alias = None
        self.adapter_requested = False

    @staticmethod
    def owned_container_info(cid, token):
        return shared.owned_container_info(cid, token)
    command = OwnedContainerLaunch.command
    launch = OwnedContainerLaunch.launch

    def start(self):
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        startup = {key: str(value) for key, value in self.fixture["parameters"].items()} | {"SDLOG_PROFILE": "131"}
        argv = shared.simulation_launch_args(self.simulator, self.baseline, self.manifest,
            runtime=self.output, token=self.token, name="pe-native-" + self.token + "-px4",
            model=self.fixture["model"], startup_parameters=startup)
        work = self.output / "simulator"
        logger = work / "rootfs/fs/etc/logging/logger_topics.txt"
        logger.parent.mkdir(parents=True, exist_ok=False)
        logger.write_bytes((SCENARIOS / "logger_topics.txt").read_bytes())
        if digest(logger) != self.assets["logger_sha256"]:
            raise ValueError("Additive logger profile changed")
        (work / "private").mkdir(mode=0o700)
        self.alias = Path(tempfile.mkdtemp(prefix="pe-native-baseline-"))
        (self.alias / "owner").write_text(self.token)
        (self.alias / "socket").symlink_to(work / "private", target_is_directory=True)
        self.socket = self.alias / "socket/guidance.sock"
        self.primary = self.launch(argv, "pe-native-" + self.token + "-px4")
        sidecar = adapter_launch_args(work, self.args.adapter_bundle, self.assets, token=self.token,
            primary=self.primary, label=shared.LABEL, name="pe-native-" + self.token + "-adapter")
        drop_count = getattr(self.args, 'release_drop_count', 0)
        from tools.native_owned_request_fault import ReleaseDropPolicy
        ReleaseDropPolicy(drop_count)
        if drop_count:
            adapter_script = work / 'adapter.sh'
            adapter_script.write_text(adapter_script.read_text().replace(' --ros-args ',
                ' --ros-args -r /fmu/in/owned_mode_request:=/pixeagle_sitl/owned_mode_request '))
            fault_source = ROOT / 'tools/native_owned_request_fault.py'
            (work / 'owned-request-fault.py').write_bytes(fault_source.read_bytes())
            (work / 'owned-request-fault.sh').write_text('set -eo pipefail\nsource /work/ws/install/setup.bash\n'
                f'exec python3 -u /runtime/owned-request-fault.py --drop-releases {drop_count}'
                ' > /runtime/owned-request-fault.jsonl 2>&1\n')
        self.sidecar = self.launch(sidecar, "pe-native-" + self.token + "-adapter")
        if drop_count:
            self.command(['docker', 'exec', '-d', '-e', f'PIXEAGLE_SITL_OWNED_REQUEST_FAULT={self.token}',
                '--user', f'{os.getuid()}:{os.getgid()}',
                self.sidecar, 'bash', '/runtime/owned-request-fault.sh'], timeout=15.)
        write(self.output / "host-manifest.json", dict(primary=self.primary, sidecar=self.sidecar,
            owner_token=self.token, simulator=self.simulator, fixture=self.fixture,
            simulation_build=self.baseline, adapter_image=self.assets["adapter_image"],
            startup_parameters=startup, fresh_parameter_store_before_boot=True,
            logger_sha256=digest(logger), socket_alias=str(self.socket),
            tool_sha256=digest(Path(__file__)), runtime_assets_sha256=digest(ASSETS),
            runtime_dependencies={"tools/native_adapter_runtime.py": digest(ROOT / "tools/native_adapter_runtime.py")},
            ownership_fault=dict(drop_initial_releases_per_acquisition=drop_count,
                source_sha256=digest(ROOT / 'tools/native_owned_request_fault.py') if drop_count else None)))

    def sidecar_info(self):
        return adapter_info(self, shared.owned_container_info)

    def verify(self):
        info = self.sidecar_info()
        self.primary_info()
        checked = verify_simulator(self.primary, 0, self.socket,
            simulation_build_manifest=self.args.simulation_build_manifest,
            build_repository=self.args.build_repository)
        if checked["process"]["model"] != self.fixture["model"]:
            raise ValueError("Actual simulator model differs from fixture")
        if self.isolation and any(checked[key] != self.isolation[key]
                                 for key in ("container_id", "image_id", "aircraft_uid")):
            raise ValueError("Original simulator identity changed")
        self.isolation = checked
        with (self.output / "isolation-verifications.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(checked=checked, sidecar_id=self.sidecar,
                sidecar_image=info["Image"], sidecar_running=info["State"]["Running"])) + "\n")
        return checked

    def bootstrap_status(self, *, timeout):
        """The sole pre-socket probe: a fixed read-only command in the owned primary."""
        info = self.primary_info()
        self.sidecar_info()
        mounts = {item["Destination"]: (Path(item["Source"]).resolve(), item["RW"]) for item in info["Mounts"]}
        if (mounts != {"/work": (self.output / "simulator", True)}
                or info["Config"].get("WorkingDir") != "/work/rootfs"):
            raise ValueError("DDS bootstrap requires the original private primary workdir")
        return self.command(["docker", "exec", "--user", f"{os.getuid()}:{os.getgid()}", self.primary,
            "/opt/px4/bin/px4-uxrce_dds_client", "--instance", "0", "status"], check=False, timeout=timeout)

    async def bootstrap(self, deadline, *, clock=None, sleep=asyncio.sleep):
        return await bootstrap_adapter(self, deadline, clock=clock, sleep=sleep)

    def primary_info(self):
        info = shared.owned_container_info(self.primary, self.token)
        if (info["State"]["Running"] is not True or info["Image"] != self.baseline["image_id"]
                or info["HostConfig"]["NetworkMode"] != "none"
                or info["HostConfig"]["Privileged"] or info["HostConfig"].get("Devices")
                or info["NetworkSettings"]["Ports"]
                or info["Config"]["User"] != f"{os.getuid()}:{os.getgid()}"):
            raise ValueError("Original primary simulation isolation changed")
        return info

    def cli(self, alias, *arguments, check=True):
        if self.isolation is None and (alias, arguments) != ("logger", ("stop",)):
            raise ValueError("Flight and observation CLI require verified running firmware")
        executable = Path(self.isolation["process"]["args"][0] if self.isolation else "/opt/px4/bin/px4")
        executable = executable.with_name("px4-" + alias)
        return self.command(["docker", "exec", "--user", f"{os.getuid()}:{os.getgid()}", self.primary,
                             str(executable), "--instance", "0", *arguments], check=check)

    def clock(self, stage):
        raw = self.cli("listener", "owned_mode_status", "-n", "1").stdout
        (self.output / (stage + "-native-clock.txt")).write_text(raw)
        values = parse_owned_samples(raw)
        age = re.findall(r"timestamp:\s*\d+\s*\(([0-9.]+) seconds ago\)", raw)
        if (len(values) != 1 or len(age) != 1 or float(age[0]) > FRESH_S
                or str(values[0]["autopilot_uid"]) != self.isolation["aircraft_uid"]
                or values[0]["owner_active"] or values[0]["rescue_active"]
                or values[0]["token"] != "0" * 32 or values[0]["incarnation"] == "0" * 32
                or not 0 < values[0]["timestamp"] <= values[0]["source_clock_us"]):
            raise ValueError("Fresh original native clock without pursuit required")
        return values[0]

    def verify_sensor_absence(self, stage):
        # -n 1 with no -i inspects all advertised instances without entering the poll loop.
        result = self.cli("listener", "differential_pressure", "-n", "1", check=False)
        write(self.output / (stage + "-differential-pressure.json"), dict(
            stdout=result.stdout, stderr=result.stderr, returncode=result.returncode,
            scope="point_in_time_all_instances", observed_at_monotonic_s=time.monotonic()))
        if result.returncode != 0 or result.stderr.strip() or result.stdout.strip() != "never published":
            raise ValueError("No-pitot installation requires absent differential-pressure publishers")

    def logger(self, stage):
        status = self.cli("logger", "status").stdout
        logs = self.command(["docker", "logs", self.primary], check=False)
        text = logs.stdout + logs.stderr + status
        (self.output / (stage + "-logger-status.txt")).write_text(text)
        if re.search(r"too many subscriptions|failed to add:|logger[^\n]*(?:error|failed)", text, re.I):
            raise ValueError("Logger startup/subscription failure")

    def cleanup(self):
        errors = []
        if self.primary is None and self.created:
            self.primary = self.created[0]
        if self.primary:
            try:
                self.primary_info()
                flush = self.cli("logger", "stop", check=False)
                write(self.output / "logger-stop.json", dict(returncode=flush.returncode,
                    stdout=flush.stdout, stderr=flush.stderr))
                if flush.returncode:
                    errors.append("logger_flush_unconfirmed")
            except BaseException as error:
                errors.append("logger_flush:" + str(error))
        for cid in reversed(self.created):
            try:
                info = shared.stop_owned_container(cid, self.token)
                write(self.output / (cid + "-stopped.json"), info)
                logs = self.command(["docker", "logs", cid], check=False)
                (self.output / (cid + ".log")).write_text(logs.stdout + logs.stderr)
            except BaseException as error:
                errors.append("original_container_cleanup:" + cid + ":" + str(error))
        if self.alias:
            try:
                if not ((self.alias / "owner").read_text() == self.token
                    and (self.alias / "socket").readlink() == self.output / "simulator/private"):
                    raise ValueError("socket_alias_ownership_changed")
                (self.alias / "socket").unlink()
                (self.alias / "owner").unlink()
                self.alias.rmdir()
            except BaseException as error:
                errors.append("socket_alias_cleanup:" + str(error))
        return errors


async def observe(client, binding, runtime_id, stream, stage, *, clock=time.monotonic):
    packet = await client.observe()
    now = clock()
    stream.write(json.dumps(dict(stage=stage, received_at_monotonic_s=now, packet=packet)) + "\n")
    stream.flush()
    state, z, issues = sample(packet, binding, runtime_id, now)
    return packet, state, z, issues


async def wait_stable(client, runtime, binding, runtime_id, stream, *, clock=time.monotonic, sleep=asyncio.sleep):
    deadline, window = clock() + 90., []
    while clock() < deadline:
        packet, state, _, issues = await observe(client, binding, runtime_id, stream, "preparation", clock=clock)
        if state is not None and state.phase is AirframePhase.MULTICOPTER and packet.get("nav_state") == 4:
            if not window or state.sequence > window[-1].sequence:
                window = (window + [state])[-7:]
            if stable_window(window, expected_altitude_m=runtime.fixture["parameters"]["MIS_TAKEOFF_ALT"]):
                return packet
        else:
            window = []
        await sleep(.5)
    raise TimeoutError("Native MC Hold never reached its unchanged stable gate")


async def admit_flight_action(client, runtime, binding, runtime_id, stream, action, deadline,
                              *, clock=None, sleep=asyncio.sleep):
    """Startup may warm up; identity, positive rescue and authority failures never retry."""
    clock = time.monotonic if clock is None else clock
    while clock() < deadline:
        runtime.verify()
        packet, state, _, issues = await observe(client, binding, runtime_id, stream, "before-" + action, clock=clock)
        if packet.get("rescue_active") is True or (packet.get("aircraft_state") or {}).get("rescue_active") is True:
            raise ValueError("Native rescue forbids simulated flight action")
        if state is not None and state.phase is not AirframePhase.MULTICOPTER:
            raise ValueError("Native MC required before arm/takeoff")
        status = runtime.cli("listener", "vehicle_status", "-n", "1").stdout
        age = re.findall(r"timestamp:\s*\d+\s*\(([0-9.]+) seconds ago\)", status)
        expected = "1" if action == "arm" else "2"
        armed = re.findall(r"(?m)^\s*arming_state:\s*(\d+)\s*$", status)
        preflight = action != "arm" or bool(re.search(r"pre_flight_checks_pass:\s*true\s*$", status, re.I | re.M))
        if (state is not None and not issues and len(age) == 1 and float(age[0]) <= FRESH_S
                and armed == [expected] and preflight):
            if clock() >= deadline:
                break
            return
        await sleep(.5)
    raise TimeoutError("Existing 30s native preflight budget exhausted before " + action)


async def capture(client, runtime, binding, runtime_id, stream, stage, initial_phase, target_phase,
                  contract, reference_z, heights, *, clock=time.monotonic, sleep=asyncio.sleep):
    event = runtime.fixture[stage]
    start, requested, last_window = clock(), False, -math.inf
    window, issues_seen, event_result = [], {}, None
    while clock() - start < event["capture_s"]:
        packet, state, z, issues = await observe(client, binding, runtime_id, stream, stage, clock=clock)
        if z is not None:
            heights.append(abs(z - reference_z))  # All actual numeric poses, even stale/rescue replies.
        for issue in issues:
            issues_seen[issue] = issues_seen.get(issue, 0) + 1
        if packet.get("nav_state") != 4:
            issues_seen["native_hold_exited"] = issues_seen.get("native_hold_exited", 0) + 1
        if state is None or packet.get("nav_state") != 4:
            window = []
        else:
            if window and window[-1].phase is not state.phase:
                window = []
            if clock() - last_window >= .5 and (not window or state.sequence > window[-1].sequence):
                last_window = clock()
                window = (window + [state])[-7:]
        if not requested and clock() - start >= event["request_at_s"]:
            if (state is None or state.phase is not initial_phase or packet.get("nav_state") != 4
                    or not stable_window(window)):
                raise ValueError("Fresh settled native Hold required before single pilot transition")
            requested = True
            runtime.verify()
            event_result = await asyncio.to_thread(native_pilot_transition, runtime.socket, runtime.isolation,
                PilotTransitionEvent(event["request_at_s"], target_phase), initial_phase, contract,
                build_repository=runtime.args.build_repository)
            write(runtime.output / (stage + "-pilot-transition.json"), event_result)
            if event_result.get("returncode") != 0:
                raise ValueError("Pilot transition failed; no retry")
        await sleep(.05)
    healthy = (requested and state is not None and state.phase is target_phase and packet.get("nav_state") == 4
               and not issues_seen and bool(window) and all(item.phase is target_phase for item in window)
               and stable_window(window))
    maximum = max(heights) if heights else None
    return dict(settled_healthy=healthy, observation_issues=issues_seen,
        maximum_full_window_observed_excursion_m=maximum,
        performance_passed=healthy and maximum is not None and maximum <= GATE_M,
        pilot_transition=event_result, reference_reset=False)


async def capture_cycle(client, runtime, binding, runtime_id, stream, initial):
    start = runtime.clock("start")
    reference_z, heights = initial["vehicle_pose"]["vehicle_ned"][2], []
    contract = transition_source_contract(runtime.isolation, build_repository=runtime.args.build_repository)
    forward = await capture(client, runtime, binding, runtime_id, stream, "forward",
        AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING, contract, reference_z, heights)
    if forward["settled_healthy"]:
        back = await capture(client, runtime, binding, runtime_id, stream, "back",
            AirframePhase.FIXED_WING, AirframePhase.MULTICOPTER, contract, reference_z, heights)
    else:
        back = dict(skipped=True, reason="Forward did not reach fresh healthy native FW Hold")
    end = runtime.clock("end")
    return dict(forward=forward, back=back,
        maximum_full_window_observed_excursion_m=max(heights) if heights else None,
        response_passed=forward["performance_passed"] and back.get("performance_passed", False)), start, end


def audit_ulog(rootfs, start, end, *, parser=None):
    """Native-clock closed-log heights; never infer position from commands."""
    if parser is None:
        from pyulog import ULog
        parser = ULog
    files = list(rootfs.rglob("*.ulg"))
    if len(files) != 1 or not files[0].stat().st_size:
        raise ValueError("One nonempty closed ULog required for the fresh baseline")
    if start["incarnation"] != end["incarnation"] or end["source_clock_us"] <= start["source_clock_us"]:
        raise ValueError("Native clock reset; no host/native clock mapping is substituted")
    log = parser(str(files[0]))
    topics = {}
    for name in ("vehicle_local_position", "vehicle_local_position_groundtruth"):
        data = log.get_dataset(name).data
        rows = [(int(stamp), float(z)) for stamp, z in zip(data["timestamp"], data["z"])
                if start["source_clock_us"] <= stamp <= end["source_clock_us"]]
        selected = [z for _, z in rows]
        if (len(rows) < 2 or any(not math.isfinite(z) for z in selected)
                or rows[0][0] - start["source_clock_us"] > FRESH_S * 1e6
                or end["source_clock_us"] - rows[-1][0] > FRESH_S * 1e6
                or any(not 0 < b[0] - a[0] <= FRESH_S * 1e6 for a, b in zip(rows, rows[1:]))):
            raise ValueError("Full native-window position/groundtruth unavailable: " + name)
        topics[name] = dict(samples=len(selected), maximum_excursion_m=max(abs(z - selected[0]) for z in selected),
                            source=name, filtered_by_pose_flags=False)
    clean = not log.dropouts and not log.file_corruption
    return dict(ulog=str(files[0]), sha256=digest(files[0]), bytes=files[0].stat().st_size,
        native_window_us=[start["source_clock_us"], end["source_clock_us"]], topics=topics,
        dropouts=len(log.dropouts), corruption=bool(log.file_corruption),
        passed=clean and all(value["maximum_excursion_m"] <= GATE_M for value in topics.values()))


def verified_runtime(args, fixture):
    """Validate the explicit simulator fixture before constructing its owned lifecycle."""
    assets = json.loads(ASSETS.read_text())
    verify_adapter(args.adapter_bundle.resolve(), args.adapter_file_manifest, assets)
    simulator, baseline, manifest = shared.verified_simulation_build(args.simulation_build_manifest,
        repository=args.build_repository)
    variant = manifest.get("build", {}).get("resource_variant")
    declared = fixture.get("resource_variant")
    if ((declared is None and variant is not None)
            or (declared is not None and (simulator != "gazebo" or not isinstance(variant, dict)
                or variant.get("name") != declared))):
        raise ValueError("Fixture resource variant differs from verified manifest")
    verify_adapter_image(assets)
    if (simulator == "gazebo") != fixture["model"].startswith("gz_"):
        raise ValueError("Fixture simulator differs from verified manifest")
    if simulator == "gazebo" and fixture["model"] != "gz_" + manifest["build"]["model"]:
        raise ValueError("Gazebo model is strictly manifest-derived")
    source = args.simulation_build_manifest.resolve().parent / "context/source"
    boot = bootstrap_contract(source, fixture, assets)
    return Runtime(args, fixture, simulator, baseline, manifest, assets), boot, simulator


async def admit_native_runtime(runtime, client, fixture, boot):
    """Shared boot and simulated arm/takeoff; the caller owns close/CID cleanup."""
    deadline = time.monotonic() + 45.
    await runtime.bootstrap(deadline)
    runtime.verify()
    capabilities = await client.connect()
    if (capabilities.multicopter_supported is not True or capabilities.fixed_wing_supported is not True
            or capabilities.owned_mode_supported is not True or capabilities.unrestricted_speed_supported is not False):
        raise ValueError("Native protocol capabilities are not the reviewed baseline")
    binding = AircraftBinding(runtime.isolation["aircraft_uid"], runtime.token, 1)
    await client.bind(binding)
    write(runtime.output / "capabilities.json", dict(capabilities=asdict(capabilities), binding=asdict(binding)))
    deadline = time.monotonic() + 30.
    readback(runtime.cli("param", "show").stdout,
             fixture["parameters"] | {"SDLOG_PROFILE": 131, "SYS_AUTOSTART": boot["autostart"]}
             | boot.get("native_default_readback", {}))
    runtime.logger("before-arm")
    with (runtime.output / "preflight-observations.jsonl").open("x") as stream:
        for action in ("arm", "takeoff"):
            if fixture.get("resource_variant") == NO_PITOT_VARIANT:
                runtime.verify_sensor_absence("before-" + action)
            await admit_flight_action(client, runtime, binding, capabilities.runtime_id, stream, action, deadline)
            runtime.cli("commander", action)
    return capabilities, binding


async def execute(args, fixture):
    if fixture.get("resource_variant") == NO_PITOT_VARIANT:
        raise ValueError("No-pitot fixture supports guidance only; native-transition capture remains measured-only")
    from pyulog import ULog  # Fail before any staging/control if the optional development parser is absent.

    runtime, boot, simulator = verified_runtime(args, fixture)
    client = None
    result = dict(passed=False, simulator=simulator, fixture=fixture, altitude_gate_m=GATE_M,
        following_acquired=False, submitted_intents=0, native_publications_requirement=0,
        external_100ms_gap_exercised=False, bootstrap_contract=boot, errors=[])
    start_clock = end_clock = None
    try:
        runtime.start()
        client = NativeGuidanceClient(runtime.socket)
        capabilities, binding = await admit_native_runtime(runtime, client, fixture, boot)
        with (runtime.output / "observations.jsonl").open("x") as stream:
            initial = await wait_stable(client, runtime, binding, capabilities.runtime_id, stream)
            cycle, start_clock, end_clock = await capture_cycle(client, runtime, binding,
                capabilities.runtime_id, stream, initial)
            result.update(cycle)
    except BaseException as error:
        result["errors"].append(type(error).__name__ + ":" + str(error))
    finally:
        if client is not None:
            try:
                await client.close()
            except BaseException as error:
                result["errors"].append("client_close:" + str(error))
        if runtime.output.exists():
            result["errors"].extend(runtime.cleanup())
    if start_clock is not None and end_clock is not None:
        try:
            result["closed_ulog"] = audit_ulog(runtime.output / "simulator/rootfs", start_clock, end_clock, parser=ULog)
        except BaseException as error:
            result["errors"].append("closed_ulog:" + str(error))
    result["passed"] = (result.get("response_passed", False) and result.get("closed_ulog", {}).get("passed", False)
                        and not result["errors"])
    if runtime.output.exists():
        result["original_container_ids"] = runtime.created
        publications = []
        for name in ("preflight-observations.jsonl", "observations.jsonl"):
            path = runtime.output / name
            if path.exists():
                publications.extend(json.loads(line)["packet"].get("publications") for line in path.read_text().splitlines())
        result["observed_publications_max"] = max((value for value in publications if type(value) is int), default=None)
        write(runtime.output / "result.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, default=SCENARIOS / "sih-standard-hold-cycle.json")
    parser.add_argument("--simulation-build-manifest", type=Path)
    parser.add_argument("--build-repository", type=Path)
    parser.add_argument("--adapter-bundle", type=Path)
    parser.add_argument("--adapter-file-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    fixture = scenario(args.scenario)
    if not args.execute:
        print(json.dumps(dict(execute=False, fixture=fixture, altitude_gate_m=GATE_M,
            runner_supported=fixture.get("resource_variant") is None,
            verified_simulation_manifest_required=True, no_following_or_target_commands=True,
            bootstrap="Fresh rootfs PX4_PARAM_* before Navigator; source-bound and read back"), indent=2))
        return 0
    if any(getattr(args, key) is None for key in
           ("simulation_build_manifest", "adapter_bundle", "adapter_file_manifest", "output")):
        parser.error("--execute requires verified simulation manifest, pinned adapter bundle/file manifest and new output")
    if args.output.exists() or args.output.is_symlink():
        parser.error("Use a new output directory; existing evidence is never overwritten")
    result = asyncio.run(execute(args, fixture))
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
