#!/usr/bin/env python3
"""Exercise production native guidance components on an already airborne SIH.

Dry-run by default. This tool never arms, takes off, transitions or flashes.
It verifies an isolated Docker SIH process before acquiring native authority.
The HTTP/App startup path is outside this component-level qualification.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Literal

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from classes.aircraft_state import AircraftBinding, AircraftState, AircraftStateOwner, AirframePhase, GuidanceSessionIdentity, Quaternion, finite_number  # noqa: E402
from classes.follower_catalog import FollowerProfile, get_follower_profile  # noqa: E402
from classes.following_readiness import evaluate_follower_guidance_input  # noqa: E402
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy  # noqa: E402
from classes.follower import FollowerFactory  # noqa: E402
from classes.native_follow_binding import NativeFollowBinding  # noqa: E402
from classes.native_guidance import NativeGuidanceClient  # noqa: E402
from classes.offboard_commander import OffboardCommander  # noqa: E402
from classes.parameters import Parameters  # noqa: E402
from classes.guidance_observation import PinholeCalibration  # noqa: E402
from classes.observation_alignment import AlignmentBinding  # noqa: E402
from classes.sih_visualization import VisualizationScenario  # noqa: E402
from classes.target_continuity import ContinuityContext, ContinuityPolicy, IdentityVerdict, TargetContinuitySupervisor, TargetEvidenceSnapshot, TargetEvidenceState  # noqa: E402
from classes.tracker_output import TrackerDataType, TrackerOutput  # noqa: E402
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target  # noqa: E402
from tools.fixed_camera_bearing_fixture import FixedCameraBearingFixture  # noqa: E402
from tools.fixed_camera_world_target import FixedCamera  # noqa: E402


@dataclass(frozen=True)
class ComponentProfile:
    profile: FollowerProfile
    tracker_type: TrackerDataType
    input_contract: str
    template: Path

    def command_contract(self, *, is_vtol: bool) -> str:
        native = self.profile.phase_command_contracts
        if is_vtol:
            if not {"multicopter", "fixed_wing", "vtol_transition"}.issubset(native):
                raise ValueError("native_component_vtol_contract_unavailable")
            return "vtol_external"
        return native["fixed_wing"]


@dataclass(frozen=True)
class ComponentFaultWindow:
    kind: Literal["target_loss", "airspeed_loss"]
    start_s: float
    end_s: float


def component_profile(name: str) -> ComponentProfile:
    """Select an input adapter from actual profile declarations, not its name."""
    profile = get_follower_profile(name)
    if (not profile.implementation_available
            or profile.phase_command_contracts.get("fixed_wing") != "fixed_wing_external"):
        raise ValueError("native_component_profile_unavailable")
    contracts = {
        ("GIMBAL_ANGLES",): (TrackerDataType.GIMBAL_ANGLES, "gimbal_angles", "gimbal-vector-native-fw.yaml"),
        ("POSITION_2D",): (TrackerDataType.POSITION_2D, "image_position_2d", "fw-navigation-native-image.yaml"),
    }
    selected = contracts.get(profile.required_tracker_data)
    if selected is None:
        raise ValueError("native_component_input_unsupported")
    tracker_type, contract, template = selected
    return ComponentProfile(profile, tracker_type, contract, ROOT / "tools/sih_visualization_scenarios" / template)


def image_optics(raw: dict, *, source_id: str) -> tuple[FixedCamera, PinholeCalibration]:
    """Read explicit synthetic optics; no hardware intrinsics are inferred."""
    camera = FixedCamera.from_mapping(raw.get("fixed_camera"))
    optics = raw.get("pinhole_calibration")
    required = {"revision", "image_size_px", "focal_length_px", "principal_point_px",
                "optical_to_body_frd_wxyz", "distortion_model"}
    if (not isinstance(optics, dict) or set(optics) != required
            or not isinstance(optics["revision"], str) or not optics["revision"].strip()):
        raise ValueError("native_component_image_calibration_invalid")
    for key, count in (("image_size_px", 2), ("focal_length_px", 2),
                       ("principal_point_px", 2), ("optical_to_body_frd_wxyz", 4)):
        if not isinstance(optics[key], list) or len(optics[key]) != count:
            raise ValueError("native_component_image_calibration_invalid")
    digest = hashlib.sha256(json.dumps({"camera": raw["fixed_camera"], "calibration": optics},
                                     sort_keys=True, allow_nan=False).encode()).hexdigest()
    calibration = PinholeCalibration(
        source_id, f"sih-optics:{optics['revision']}:{digest}", tuple(optics["image_size_px"]),
        tuple(optics["focal_length_px"]), tuple(optics["principal_point_px"]),
        Quaternion(*optics["optical_to_body_frd_wxyz"]), optics["distortion_model"],
    )
    return camera, calibration


def image_fixture(raw: dict, state: AircraftState, *, runtime_id: str, run_id: str, clock=time.monotonic):
    source_id = f"simulated-image:{run_id}"
    camera, calibration = image_optics(raw, source_id=source_id)
    if state.attitude_timing is None:
        raise ValueError("native_component_attitude_timing_unavailable")
    binding = AlignmentBinding(source_id, f"source:{run_id}", f"geometry:{calibration.revision}",
                               calibration.revision, 1, state.binding, runtime_id,
                               state.attitude_timing.quat_reset_counter)
    return FixedCameraBearingFixture(
        camera=camera, calibration=calibration, binding=binding,
        fixture_revision="fixed-camera-native-pose-v1", clock=clock,
        max_observation_age_s=.5, max_attitude_age_s=.5, allow_simulation=True,
    )


def measurement_time(output: TrackerOutput | None) -> float | None:
    """Read the producer's receipt unchanged; polling never becomes a sample."""
    if output is None or not output.tracking_active:
        return None
    measured = getattr(output, "image_measurement", None)
    value = (measured.provenance.capture.captured_at if measured is not None
             else output.raw_data.get("angle_sample_monotonic"))
    return None if value is None else finite_number(value, "native_component_measurement_time")


def measurement_world_target(output: TrackerOutput, target):
    if measurement_time(output) is None:
        return None
    if output.data_type is TrackerDataType.POSITION_2D:
        return output.raw_data.get("measurement_target_ned") if output.image_measurement is not None else None
    return target


def observed_airspeed_status(state: AircraftState, feedback: dict) -> dict:
    return dict(speed_source=state.airspeed.source, airspeed_valid=state.airspeed.valid,
                airspeed_control_enabled=feedback.get("airspeed_control_enabled"))


def observed_pose_record(packet, *, follow_start: float, previous_timestamp_us: int | None):
    pose = packet["vehicle_pose"]
    timestamp = pose["px4_timestamp_us"]
    if type(timestamp) is not int or not 0 < timestamp < 2**64:
        raise ValueError("native_component_pose_timestamp_invalid")
    if previous_timestamp_us is not None:
        if timestamp < previous_timestamp_us:
            raise ValueError("native_component_pose_reordered")
        if timestamp == previous_timestamp_us:
            return None
    received = finite_number(pose["observed_at_monotonic_s"], "native_component_pose_receipt")
    if received < 0.:
        raise ValueError("native_component_pose_receipt_invalid")
    feedback = packet.get("native_guidance_feedback") or {}
    return dict(timestamp=received-follow_start, vehicle_ned=pose["vehicle_ned"],
        vehicle_quaternion=pose["quaternion_wxyz"], px4_timestamp_us=timestamp,
        observed_at_monotonic_s=received, timestamp_basis="native_pose_acquisition_receipt",
        native_fw_forward_ned=feedback.get("fixed_wing_forward_ned"), source=pose["source"])


def component_target_evidence(output, *, input_owner, session_epoch: int, now=time.monotonic):
    observed = measurement_time(output)
    evidence = TargetEvidenceSnapshot.from_tracker_output(
        output, session_epoch=session_epoch, now_monotonic_s=now() if observed is None else observed,
    )
    projection_error = None if output is None else output.metadata.get("projection_error")
    if projection_error:
        return replace(evidence, state=TargetEvidenceState.UNCERTAIN,
                       identity_verdict=IdentityVerdict.UNCONFIRMED, reason_code=projection_error)
    if evidence.state is TargetEvidenceState.CONFIRMED:
        readiness = evaluate_follower_guidance_input(input_owner, output)
        if not readiness["ready"]:
            return replace(evidence, state=TargetEvidenceState.UNCERTAIN,
                           identity_verdict=IdentityVerdict.UNCONFIRMED, reason_code=readiness["reason_code"])
    return evidence


def prepare_component_intent(follower, intent, *, loss_decay: bool):
    fields = follower.prepare_authorized_command(dict(intent.fields), loss_decay=loss_decay)
    return replace(intent, fields=fields)


def project_component_image(fixture, packet, state, target, *, timestamp_s):
    """Keep projection refusals in the existing continuity evidence contract."""
    try:
        return fixture.project(packet, state, tuple(target), timestamp_s=timestamp_s)
    except ValueError as error:
        if str(error) not in {
            "sih_projection_attitude_stale", "sih_projection_pose_stale", "sih_projection_frame_stale",
            "alignment_attitude_stale", "image_receipt_stale",
        }:
            raise
        # Missing/delayed pose association is not a new image measurement.
        return TrackerOutput(TrackerDataType.POSITION_2D, timestamp_s, False,
            tracker_id="simulated_fixed_camera_bearing", raw_data={
                "has_output": False, "usable_for_following": False, "data_is_stale": True,
                "freshness_reason": str(error),
            }, metadata={"simulation_only": True, "projection_error": str(error)})


def command(*args):
    return subprocess.check_output(args, text=True, timeout=15)


def archive_configuration(output: Path) -> dict:
    artifacts = {}
    for name in ("config.yaml", "config_schema.yaml", "follower_commands.yaml"):
        source = output / name if name == "config.yaml" else ROOT / "configs" / name
        data = source.read_bytes()
        if name != "config.yaml":
            (output / name).write_bytes(data)
        artifacts[name] = {"path": name, "sha256": hashlib.sha256(data).hexdigest()}
    return artifacts


def native_parameters(socket: Path, isolation: dict) -> str:
    executable = str(Path(isolation["process"]["args"][0]).with_name("px4-param"))
    return command("docker", "exec", "--user", str(socket.stat().st_uid), isolation["container_id"],
                   executable, "--instance", str(isolation["instance"]), "show")


def require_airspeed_failure_injection(parameters: str, isolation: dict) -> None:
    if isolation.get("firmware_build") is None:
        raise ValueError("native_component_fault_requires_verified_source_build")
    enabled = re.findall(r"(?m)^\s*(?:[x+*]\s+)?SYS_FAILURE_EN(?:\s+\[[^]\n]+\])?\s*:\s*(\S+)\s*$", parameters)
    if enabled != ["1"]:
        raise ValueError("native_component_failure_injection_disabled")


def native_airspeed_failure(socket: Path, isolation: dict, blocked: bool) -> dict:
    """Use only the verified SIH binary's CLI and pinned container/instance."""
    if type(blocked) is not bool:
        raise ValueError("native_component_airspeed_fault_invalid")
    executable = str(Path(isolation["process"]["args"][0]).with_name("px4-failure"))
    argv = ("docker", "exec", "--user", str(socket.stat().st_uid), isolation["container_id"],
            executable, "--instance", str(isolation["instance"]), "airspeed", "off" if blocked else "ok", "-i", "1")
    started = time.monotonic()
    try:
        completed = subprocess.run(argv, text=True, capture_output=True, timeout=15, check=False)
        return dict(argv=list(argv), returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr,
                    started_at_monotonic_s=started, finished_at_monotonic_s=time.monotonic())
    except (OSError, subprocess.TimeoutExpired) as error:
        return dict(argv=list(argv), returncode=None, error=f"{type(error).__name__}:{error}",
                    started_at_monotonic_s=started, finished_at_monotonic_s=time.monotonic())


class AirspeedLossInjection:
    """One test-only CLI task; target guidance and publication keep running."""

    def __init__(self, socket, isolation, windows, *, log, started, clock=time.monotonic):
        self.socket, self.isolation, self.windows = socket, isolation, windows
        self.log, self.started, self.clock = log, started, clock
        self.events = []
        self._active = False
        self._task = None

    @property
    def active(self):
        return self._active

    def _record(self, phase, blocked, **details):
        now = self.clock()
        event = dict(kind="airspeed_loss", phase=phase, operation="off" if blocked else "ok",
                     timestamp=now-self.started, observed_at_monotonic_s=now, **details)
        self.events.append(event)
        self.log("fault-events.jsonl", event)

    async def _apply(self, blocked):
        self._record("started", blocked)
        result = await asyncio.to_thread(native_airspeed_failure, self.socket, self.isolation, blocked)
        self._record("finished", blocked, command=result)
        if result.get("returncode") != 0:
            raise RuntimeError("native_component_airspeed_fault_command_failed")
        if not blocked:
            self._active = False

    async def tick(self, elapsed):
        if self._task is not None:
            if not self._task.done():
                return
            task, self._task = self._task, None
            await task
        desired = any(window.start_s <= elapsed < window.end_s for window in self.windows)
        if desired != self._active:
            # Even a failed/timed-out off command may have reached PX4.
            if desired:
                self._active = True
            self._task = asyncio.create_task(self._apply(desired), name="native-sih-airspeed-fault")

    async def close(self):
        pending_error = None
        if self._task is not None:
            task, self._task = self._task, None
            try:
                await task
            except Exception as error:
                pending_error = error
        if self._active:
            await self._apply(False)
        if pending_error is not None:
            raise pending_error


def airspeed_fault_response_checks(response, events) -> dict[str, bool]:
    checks = dict(airspeed_fault_commands_succeeded=False, airspeed_source_degraded=False,
                  airspeed_sensor_restored=False)
    finished = [event for event in events if event.get("phase") == "finished"]
    if (not finished or len(finished) % 2
            or any(event.get("operation") != ("off" if index % 2 == 0 else "ok")
                   or event.get("command", {}).get("returncode") != 0 for index, event in enumerate(finished))):
        return checks
    intervals = []
    try:
        for off, restored in zip(finished[::2], finished[1::2]):
            off_start = (finite_number(off["command"]["started_at_monotonic_s"], "fault_start")
                         - finite_number(off["observed_at_monotonic_s"], "fault_event_receipt") + off["timestamp"])
            restore_finish = (finite_number(restored["command"]["finished_at_monotonic_s"], "fault_finish")
                              - finite_number(restored["observed_at_monotonic_s"], "fault_event_receipt")
                              + restored["timestamp"])
            if not 0. <= off_start <= restore_finish:
                return checks
            intervals.append((off_start, restore_finish))
    except (KeyError, TypeError, ValueError):
        return checks
    checks["airspeed_fault_commands_succeeded"] = True
    degraded = restored = True
    for index, (off_start, restore_finish) in enumerate(intervals):
        end = intervals[index+1][0] if index+1 < len(intervals) else math.inf
        baseline = any(row["timestamp"] < off_start and row.get("speed_source") == "sensor"
                       and row.get("airspeed_valid") is True for row in response)
        lost = [row for row in response if off_start <= row["timestamp"] < restore_finish
                and ((row.get("speed_source") == "ground_minus_wind" and row.get("airspeed_valid") is True)
                     or (row.get("speed_source") == "unavailable" and row.get("airspeed_valid") is False
                         and row.get("airspeed_control_enabled") is False))]
        degraded = degraded and baseline and bool(lost)
        restored = restored and baseline and bool(lost) and any(
            max(restore_finish, lost[0]["timestamp"]) < row["timestamp"] < end
            and row.get("speed_source") == "sensor" and row.get("airspeed_valid") is True for row in response)
    checks["airspeed_source_degraded"] = degraded
    checks["airspeed_sensor_restored"] = restored
    return checks


async def cleanup_component_run(commander, binding, fault_injection, result):
    """Quiesce/release control before waiting for test-sensor CLI cleanup."""
    try:
        try:
            if commander is not None and commander.running:
                if await commander.stop(publish_final=False) is False:
                    raise RuntimeError("native_component_publisher_not_quiesced")
        except Exception as error:
            result["passed"] = False
            result["publisher_cleanup_error"] = str(error)
    finally:
        try:
            try:
                if binding is not None and binding.owner_confirmed:
                    result["cleanup"] = await binding.stop("isolated_sih_cleanup")
            except Exception as error:
                result["passed"] = False
                result["cleanup_error"] = str(error)
        finally:
            if fault_injection is not None:
                try:
                    await fault_injection.close()
                except Exception as error:
                    result["passed"] = False
                    result["fault_cleanup_error"] = str(error)
                result["fault_events"] = fault_injection.events


def verify_simulator(container: str, instance: int, socket: Path, *, sih_build_manifest: Path | None = None) -> dict:
    info = json.loads(command("docker", "inspect", container))[0]
    if (info["HostConfig"]["NetworkMode"] != "none" or info["HostConfig"]["Privileged"]
            or info["HostConfig"].get("Devices") or info["NetworkSettings"]["Ports"]):
        raise ValueError("SIH requires an isolated container without hardware or published ports")
    baseline = None
    if sih_build_manifest is not None:
        from tools.sih_baseline import validate_build_manifest

        baseline = validate_build_manifest(sih_build_manifest)
    # Inspect the real process and inherited model, not an operator-supplied label.
    script = """import hashlib, json, pathlib, sys
out=[]
for p in pathlib.Path('/proc').iterdir():
 try:
  args=(p/'cmdline').read_bytes().split(b'\\0'); args=[x.decode() for x in args if x]
  env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode().split('\\0') if '=' in x)
  if args and pathlib.Path(args[0]).name=='px4':
   value=dict(args=args, model=env.get('PX4_SIM_MODEL'), cwd=str((p/'cwd').resolve()))
   if sys.argv[1]=='verify':
    value['binary_sha256']=hashlib.sha256((p/'exe').read_bytes()).hexdigest()
   out.append(value)
 except (OSError, UnicodeError): pass
print(json.dumps(out))
"""
    matches = [p for p in json.loads(command("docker", "exec", "--user", str(socket.stat().st_uid),
                                            container, "python3", "-c", script, "verify" if baseline else "legacy"))
               if "-i" in p["args"] and p["args"].index("-i") + 1 < len(p["args"])
               and p["args"][p["args"].index("-i") + 1] == str(instance)
               and (baseline is not None or p["args"][0].endswith('/build/px4_sitl_sih/bin/px4'))]
    if len(matches) != 1 or not str(matches[0]["model"]).startswith("sihsim_"):
        raise ValueError("An unambiguous running PX4 SIH instance is required")
    process = matches[0]
    if baseline is not None and process.get("binary_sha256") != baseline["binary_sha256"]:
        raise ValueError("Running SIH binary differs from the verified source build")
    mapped = [str(Path(m["Destination"]) / socket.resolve().relative_to(Path(m["Source"])))
              for m in info["Mounts"] if socket.resolve().is_relative_to(Path(m["Source"]))]
    if len(mapped) != 1 or not socket.is_socket():
        raise ValueError("Native socket must be in the verified simulation container bind mount")
    listener = str(Path(process["args"][0]).with_name("px4-listener"))
    status = command("docker", "exec", "--user", str(socket.stat().st_uid), container, listener, "--instance", str(instance),
                     "fixed_wing_guidance_status", "-n", "1")
    uid = re.search(r"autopilot_uid:\s*(\d+)", status)
    if uid is None:
        raise ValueError("Simulator aircraft UID is unavailable")
    return dict(container_id=info["Id"], image_id=info["Image"], instance=instance,
                process=process, aircraft_uid=uid.group(1), native_socket=mapped[0],
                initial_native_status=status, firmware_build=baseline)


def stable_window(states: list[AircraftState], *, minimum_relative_altitude_m=15., expected_altitude_m=None) -> bool:
    if len(states) < 7:
        return False
    phase = states[0].phase
    if phase not in (AirframePhase.FIXED_WING, AirframePhase.MULTICOPTER):
        return False
    if any(s.phase is not phase or s.rescue_active or s.fixed_wing_envelope is None
           or s.relative_altitude_m < minimum_relative_altitude_m for s in states):
        return False
    if phase is AirframePhase.FIXED_WING and any(
            not s.airspeed.valid or s.airspeed.equivalent_m_s is None
            or s.airspeed.equivalent_m_s < s.fixed_wing_envelope.minimum_eas_m_s for s in states):
        return False
    if phase is AirframePhase.MULTICOPTER and any(
            not s.is_vtol or s.velocity_ned_m_s.horizontal_magnitude > .5
            or abs(math.remainder(s.navigation_heading_rad - states[0].navigation_heading_rad, 2 * math.pi)) > math.radians(5)
            for s in states):
        return False
    if states[-1].observed_at_monotonic_s - states[0].observed_at_monotonic_s < 2.9:
        return False
    return (max(s.relative_altitude_m for s in states) - min(s.relative_altitude_m for s in states) <= 1.
            and all(abs(s.velocity_ned_m_s.z) <= .5 for s in states)
            and (expected_altitude_m is None or all(abs(s.relative_altitude_m - expected_altitude_m) <= 2.
                                                   for s in states)))


class ObservationConnection:
    """Test-only telemetry bridge; all guidance and publication stay in production."""

    is_command_preview = False

    def __init__(self, binding, *, clock=time.monotonic):
        self.owner = AircraftStateOwner(clock=clock)
        self.owner.bind(binding)
        self.last_packet = None

    def get_aircraft_state(self):
        return self.owner.snapshot(timeout_s=.75)

    def commit_aircraft_state(self, state):
        return self.owner.commit(state)

    def retain_packet(self, state: AircraftState, packet) -> bool:
        incoming = AircraftState.from_payload(packet["aircraft_state"])
        if incoming != state or self.get_aircraft_state() != state:
            return False
        self.last_packet = packet
        return True

    @property
    def current_altitude(self):
        state = self.get_aircraft_state()
        return None if state is None else state.relative_altitude_m


def attach_component_observer(binding, connection, log, *, started: float, clock=time.monotonic):
    """Use one accepted-packet callback for acquisition and later publications."""
    original_observer = binding.on_observation

    async def observation(state, packet, intent):
        coherent = connection.retain_packet(state, packet)
        log("observations.jsonl", dict(timestamp=clock()-started, value=packet,
                                      retained_for_projection=coherent))
        return await original_observer(state, packet, intent)

    binding.on_observation = observation
    binding.transport.on_observation = observation


def tracker_for_world_target(packet, target, mount, *, clock=time.monotonic):
    pose = packet["vehicle_pose"]
    measured_at = pose["observed_at_monotonic_s"]
    if not 0. <= clock() - measured_at <= .5:
        raise ValueError("px4_pose_stale")
    angles = camera_angles_for_world_target(pose["vehicle_ned"], target, pose["quaternion_wxyz"], mount)
    return TrackerOutput(TrackerDataType.GIMBAL_ANGLES, time.time(), True,
                         tracker_id="independent_sih_target", angular=angles,
                         raw_data={"angle_sample_monotonic": measured_at, "has_output": True,
                                   "usable_for_following": True, "data_is_stale": False})


def load_component_scenario(path, *, mount, altitude, duration, is_vtol, follower="gm_velocity_vector"):
    selected = component_profile(follower)
    scenario = VisualizationScenario.from_yaml(path)
    expected_airframe = "vtol" if is_vtol else "fixed_wing"
    if (scenario.schema_version != 2 or scenario.follower_profile != selected.profile.mode
            or scenario.input_contract != selected.input_contract or scenario.airframe != expected_airframe
            or scenario.command_contract != selected.command_contract(is_vtol=is_vtol)
            or scenario.mount_type != mount or scenario.altitude_control is not altitude):
        raise ValueError("native_component_scenario_contract_mismatch")
    component_fault_windows(scenario.faults, duration)
    if scenario.requested_speed is not None:
        raise ValueError("native_component_use_explicit_mc_request_action")
    if scenario.target_at(0.) is None or scenario.target_at(duration) is None:
        raise ValueError("native_component_target_does_not_cover_run")
    raw = yaml.safe_load(path.read_text())
    if selected.tracker_type is TrackerDataType.POSITION_2D:
        image_optics(raw, source_id="scenario-validation")
    elif "fixed_camera" in raw or "pinhole_calibration" in raw:
        raise ValueError("native_component_optics_input_mismatch")
    return raw


def component_loss_windows(faults, duration, *, kind="target_loss"):
    """Validate test stimuli; the production supervisor owns recovery policy."""
    windows = []
    for fault in faults:
        if fault.get("kind") != kind:
            raise ValueError("native_component_fault_injection_not_implemented")
        if set(fault) != {"kind", "at_s", "duration_s"}:
            raise ValueError("native_component_loss_window_invalid")
        start, length = fault["at_s"], fault["duration_s"]
        if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in (start, length)) or start < 0. or length <= 0. or start + length > duration):
            raise ValueError("native_component_loss_window_invalid")
        windows.append((float(start), float(start + length)))
    windows.sort()
    if any(right[0] < left[1] for left, right in zip(windows, windows[1:])):
        raise ValueError("native_component_loss_windows_overlap")
    return windows


def component_fault_windows(faults, duration) -> tuple[ComponentFaultWindow, ...]:
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not math.isfinite(duration) or duration <= 0.):
        raise ValueError("native_component_fault_duration_invalid")
    if any(not isinstance(fault, dict) or not isinstance(fault.get("kind"), str) for fault in faults):
        raise ValueError("native_component_fault_injection_not_implemented")
    kinds = {fault.get("kind") for fault in faults}
    if not kinds:
        return ()
    if not kinds.issubset({"target_loss", "airspeed_loss"}):
        raise ValueError("native_component_fault_injection_not_implemented")
    if len(kinds) != 1:
        raise ValueError("native_component_fault_families_mixed")
    kind = next(iter(kinds))
    return tuple(ComponentFaultWindow(kind, start, end)
                 for start, end in component_loss_windows(faults, duration, kind=kind))


def loss_tracker_output(data_type=TrackerDataType.GIMBAL_ANGLES):
    # Target truth continues, but absence has no image, angle or measurement time.
    if data_type not in {TrackerDataType.GIMBAL_ANGLES, TrackerDataType.POSITION_2D}:
        raise ValueError("native_component_loss_input_unsupported")
    return TrackerOutput(data_type, time.time(), False,
                         tracker_id="independent_sih_target", raw_data={"has_output": False,
                         "usable_for_following": False, "data_is_stale": False})


def phase_response_segments(response):
    """Describe observed phase spans; never substitute them for acceptance checks."""
    segments = []
    for row in response:
        if not segments or segments[-1]["phase"] != row["phase"]:
            segments.append(dict(phase=row["phase"], start_s=row["timestamp"], end_s=row["timestamp"],
                                 range_start_m=row["range_m"], range_end_m=row["range_m"],
                                 altitude_min_m=row["altitude_m"], altitude_max_m=row["altitude_m"], samples=0))
        segment = segments[-1]
        segment.update(end_s=row["timestamp"], range_end_m=row["range_m"], samples=segment["samples"] + 1,
                       altitude_min_m=min(segment["altitude_min_m"], row["altitude_m"]),
                       altitude_max_m=max(segment["altitude_max_m"], row["altitude_m"]))
    return segments


async def run(args, isolation):
    selected = component_profile(args.follower)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for directory in ("trace", "px4"):
        (output / directory).mkdir()
    config = yaml.safe_load(args.config.read_text())
    if selected.tracker_type is TrackerDataType.GIMBAL_ANGLES:
        config["GimbalTracker"]["MOUNT_TYPE"] = args.mount
    config["Follower"]["FollowerOverrides"].setdefault(selected.profile.config_section, {})[
        "ENABLE_ALTITUDE_CONTROL"] = args.altitude
    # Explicit simulator overlay; public and installed configurations stay untouched.
    config["Follower"]["FOLLOWER_MODE"] = selected.profile.mode
    config["FOLLOWER_CIRCUIT_BREAKER"] = False
    (output / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    Parameters.load_config(output / "config.yaml", strict_dependents=True)
    configuration = archive_configuration(output)
    source = command("git", "-C", str(ROOT), "rev-parse", "HEAD").strip()
    patch = command("git", "-C", str(ROOT), "diff", "HEAD")
    (output / "source.patch").write_text(patch)
    (output / "manifest.json").write_text(json.dumps(dict(
        evidence_kind="px4_observed_sih", qualification="native_guidance_component",
        application_startup_qualified=False, revision=source, worktree_dirty=bool(patch),
        isolation=isolation, altitude_guidance=args.altitude, mount=args.mount,
        follower=selected.profile.mode, input_contract=selected.input_contract,
        simulated_tracker_input=True,
        argv=list(sys.argv), working_directory=str(Path.cwd()),
        configuration=configuration,
        parameter_snapshots={"before": "px4/parameters-before.txt", "after": "px4/parameters-after.txt"},
        expected_handoff_reason=args.expect_handoff,
    ), indent=2))
    logs = {}

    def log(name, value):
        if name not in logs:
            logs[name] = (output / name).open("x")
        logs[name].write(json.dumps(value, allow_nan=False) + "\n")
        logs[name].flush()

    client = NativeGuidanceClient(args.socket)
    commander = binding = fault_injection = None
    failure_injection_enabled = None
    response = []
    result = dict(passed=False, reason="not_started")
    started = time.monotonic()
    try:
        parameters_before = native_parameters(args.socket, isolation)
        (output / "px4/parameters-before.txt").write_text(parameters_before)
        capabilities = await client.connect()
        aircraft = AircraftBinding(isolation["aircraft_uid"], f"sih-{output.name}", 1)
        log("runtime.jsonl", dict(timestamp=time.monotonic(), capabilities=asdict(capabilities),
                                  binding=asdict(aircraft),
                                  control_contract="native_guidance_component_only"))
        await client.bind(aircraft)
        connection = ObservationConnection(aircraft)
        window = []
        while time.monotonic() - started < args.stable_timeout:
            packet = await client.observe()
            log("observations.jsonl", dict(timestamp=time.monotonic() - started, value=packet))
            # PX4 VehicleStatus::NAVIGATION_STATE_AUTO_LOITER. Takeoff/landing
            # transients cannot satisfy a numerically flat altitude window.
            if (packet["fresh"] and not packet["rescue_active"] and packet.get("vehicle_pose")
                    and packet.get("nav_state") == 4):
                state = AircraftState.from_payload(packet["aircraft_state"])
                connection.commit_aircraft_state(state)
                if connection.retain_packet(state, packet):
                    if not window or state.sequence > window[-1].sequence:
                        window = (window + [state])[-7:]
                    if stable_window(window, expected_altitude_m=args.test_altitude):
                        break
                else:
                    window = []
            else:
                window = []
            await asyncio.sleep(.5)
        else:
            raise ValueError("stable_airborne_window_not_reached")
        log("stable-flight.jsonl", dict(timestamp=time.monotonic() - started, states=[asdict(s) for s in window]))
        follower = FollowerFactory.create_follower(selected.profile.mode, connection, (.5, .5))
        continuity_config = config["TargetContinuity"]
        supervisor = TargetContinuitySupervisor(ContinuityPolicy.resolve(
            continuity_config, selected.profile.mode, state.phase))
        supervisor.reset_session(session_epoch=1, reason="isolated_sih_start")
        target_output = [None]
        pose = connection.last_packet["vehicle_pose"]
        origin = pose["vehicle_ned"]
        heading = state.navigation_heading_rad
        forward, right = (math.cos(heading), math.sin(heading)), (-math.sin(heading), math.cos(heading))
        # Fixed world trajectory, frozen before following. Never moved relative to the chasing aircraft.
        target_start = [origin[k] + forward[k] * 160. + right[k] * 35. for k in (0, 1)]
        target_start.append(origin[2] + (8. if args.altitude else 0.))
        target_end = [target_start[k] + forward[k] * 6. * args.duration for k in (0, 1)] + [target_start[2]]
        scenario_raw = (load_component_scenario(args.scenario, mount=args.mount, altitude=args.altitude,
                                                duration=args.duration, is_vtol=state.is_vtol,
                                                follower=selected.profile.mode)
                        if args.scenario else yaml.safe_load(selected.template.read_text()))
        if (selected.tracker_type is TrackerDataType.POSITION_2D
                and scenario_raw.get("mount_type") != args.mount):
            raise ValueError("native_component_fixed_camera_mount_mismatch")
        scenario_raw.update(name=output.name, mount_type=args.mount, initial_conditions={"vehicle_ned": origin})
        scenario_raw["airframe"] = "vtol" if state.is_vtol else "fixed_wing"
        scenario_raw["follower"].update(
            profile=selected.profile.mode, purpose=selected.profile.description,
            input_contract=selected.input_contract, command_contract=selected.command_contract(is_vtol=state.is_vtol),
            altitude_control=args.altitude,
        )
        scenario_raw["constraints"] = {"altitude": dict(min=follower.altitude_limits.min_altitude,
                                                       max=follower.altitude_limits.max_altitude)}
        scenario_raw["continuity_policy"] = json.loads(json.dumps(asdict(supervisor.policy)))
        if args.scenario is None:
            scenario_raw["target"]["waypoints"] = [dict(time_s=0., position_ned=target_start),
                                                    dict(time_s=args.duration, position_ned=target_end)]
        scenario_path = output / "scenario.yaml"
        scenario_path.write_text(yaml.safe_dump(scenario_raw, sort_keys=False))
        scenario = VisualizationScenario.from_yaml(scenario_path)
        fault_windows = component_fault_windows(scenario.faults, args.duration)
        loss_windows = [(window.start_s, window.end_s) for window in fault_windows if window.kind == "target_loss"]
        airspeed_windows = tuple(window for window in fault_windows if window.kind == "airspeed_loss")
        if airspeed_windows:
            failure_injection_enabled = False
            require_airspeed_failure_injection(parameters_before, isolation)
            failure_injection_enabled = True
        projected = None
        if selected.tracker_type is TrackerDataType.POSITION_2D:
            projected = image_fixture(scenario_raw, state, runtime_id=capabilities.runtime_id, run_id=output.name)
            follower.bind_guidance_input_resolver(projected.resolve)

        def tracker_input(packet, state, target):
            if projected is not None:
                return project_component_image(projected, packet, state, target, timestamp_s=time.time())
            return tracker_for_world_target(packet, target, args.mount)

        guidance = follower.create_airframe_session(
            GuidanceSessionIdentity(output.name, aircraft, 1), capabilities,
            confirmation_s=config["Follower"]["AIRFRAME_PHASE_CONFIRMATION_S"],
            observation_timeout_s=.75, transition_timeout_s=config["Follower"]["VTOL_TRANSITION_TIMEOUT_S"],
            fixed_wing_policy=FixedWingGuidancePolicy.from_mapping(config["FixedWingGuidance"]),
        )
        input_owner = SimpleNamespace(follower=SimpleNamespace(follower=follower), px4_interface=connection)

        def target_evidence():
            return component_target_evidence(target_output[0], input_owner=input_owner, session_epoch=1)

        base = ContinuityContext("PX4_NATIVE", state.phase, "fixed_wing_external", True, False, True)
        binding = NativeFollowBinding(
            guidance, connection, client, supervisor, profile_name=selected.profile.mode,
            continuity_config=continuity_config, target_evidence=target_evidence, context=lambda: base,
            circuit_breaker=lambda: False,
        )
        attach_component_observer(binding, connection, log, started=started)
        target_output[0] = tracker_input(connection.last_packet, state, scenario.target_at(0.))
        initial_evidence = target_evidence()
        if initial_evidence.state is not TargetEvidenceState.CONFIRMED:
            raise ValueError(initial_evidence.reason_code)
        baseline = await binding.engage()
        follower.bind_airframe_session(guidance)

        async def published(event):
            intent = event["command_intent"]
            log("trace/offboard_publish_trace.jsonl", dict(
                record_type="offboard_publish", timestamp=time.monotonic() - follow_start,
                publish_success=event["publish_status"]["last_publish_success"],
                command_intent=None if intent is None else asdict(intent)))

        commander = OffboardCommander(connection, follower.setpoint_handler, command_rate_hz=20.,
                                      command_ttl_s=.3, command_transport=binding.transport,
                                      on_publish_result=published)
        if not commander.submit_intent(baseline):
            raise ValueError(commander.last_error)
        follow_start = time.monotonic()
        if airspeed_windows:
            fault_injection = AirspeedLossInjection(args.socket, isolation, airspeed_windows, log=log, started=follow_start)
        if not await commander.start():
            raise ValueError(commander.last_error)
        initial_altitude = state.relative_altitude_m
        initial_publications = commander.successful_publishes
        mc_request_applied = False
        handoff_reason = None
        handoff_time = None
        previous_pose_timestamp = None
        while (elapsed := time.monotonic() - follow_start) < args.duration:
            if fault_injection is not None:
                await fault_injection.tick(elapsed)
            packet = connection.last_packet
            state = connection.get_aircraft_state()
            if state is None or not commander.running or commander.failed_publishes:
                raise ValueError("native_publication_or_state_unhealthy")
            if (args.mc_request is not None and not mc_request_applied and not binding.pursuit_paused
                    and state.phase is AirframePhase.MULTICOPTER):
                control = guidance.controls.current_control
                follower.update_session_control("requested_speed", args.mc_request, control.revision)
                mc_request_applied = True
                log("session-control-updates.jsonl", dict(timestamp=elapsed, control="requested_speed",
                    value=args.mc_request, guidance_identity=asdict(guidance.identity)))
            target = scenario.target_at(elapsed)
            pose_time = max(0., packet["vehicle_pose"]["observed_at_monotonic_s"] - follow_start)
            measurement_target = scenario.target_at(pose_time)
            loss_active = any(start <= elapsed < end for start, end in loss_windows)
            target_output[0] = (loss_tracker_output(selected.tracker_type) if loss_active
                                else tracker_input(packet, state, measurement_target))
            evidence = target_evidence()
            nominal = binding.paused_baseline()
            if nominal is None and evidence.state is TargetEvidenceState.CONFIRMED:
                if not follower.follow_target(target_output[0]):
                    guard_reason = getattr(follower, "_geometry_invalid", None) or getattr(follower, "_safety_rejection", None)
                    if guard_reason:
                        raise ValueError(guard_reason)
                    evidence = replace(evidence, state=TargetEvidenceState.UNCERTAIN,
                        identity_verdict=IdentityVerdict.UNCONFIRMED, reason_code="follower_rejected_measurement")
                else:
                    nominal = follower.get_last_command_intent()
            decision = supervisor.evaluate(evidence, binding.context(base), nominal)
            intent = decision.authorized_intent
            if decision.handoff_request is None:
                if intent is None:
                    raise ValueError("continuity_authorized_intent_missing")
                status = supervisor.get_status()
                loss_decay = status.get("transition_phase") == "loss" and intent.reason == "bounded_horizontal_decay"
                intent = prepare_component_intent(follower, intent, loss_decay=loss_decay)
                if not commander.submit_intent(intent):
                    raise ValueError(commander.last_error)
                supervisor.record_authorized_intent(intent)
                follower.on_command_submitted(dict(intent.fields))
            feedback = packet.get("native_guidance_feedback") or {}
            p = packet["vehicle_pose"]
            response.append(dict(timestamp=elapsed, phase=state.phase.value, range_m=math.dist(p["vehicle_ned"], target),
                                 **observed_airspeed_status(state, feedback),
                                 altitude_m=state.relative_altitude_m,
                                 eas_m_s=state.airspeed.equivalent_m_s,
                                 pose_observed_at=p["observed_at_monotonic_s"]))
            pose_record = observed_pose_record(packet, follow_start=follow_start, previous_timestamp_us=previous_pose_timestamp)
            if pose_record is not None:
                log("px4/pose_trace.jsonl", pose_record)
                previous_pose_timestamp = pose_record["px4_timestamp_us"]
            log("trace/target_truth.jsonl", dict(timestamp=elapsed, target_ned=target))
            log("trace/tracker_command_trace.jsonl", dict(record_type="tracker_command", timestamp=elapsed,
                **observed_airspeed_status(state, feedback),
                requested_speed=(guidance.controls.current_control.value if guidance.controls.current_control else None),
                command_intent=None if intent is None else asdict(intent),
                measurement_age_s=(None if measurement_time(target_output[0]) is None
                                   else time.monotonic() - measurement_time(target_output[0])),
                measurement_target_ned=measurement_world_target(target_output[0], measurement_target),
                tracker_output=target_output[0].to_dict()))
            log("trace/follower_state.jsonl", dict(timestamp=elapsed, state=decision.authority_state.value,
                **observed_airspeed_status(state, feedback),
                aircraft_phase=state.phase.value, observed_eas_m_s=state.airspeed.equivalent_m_s,
                native_effective_eas_m_s=feedback.get("effective_eas_m_s"),
                phase_state=guidance.phase_owner.state.value, phase_reason=guidance.phase_owner.reason,
                guidance_generation=guidance.identity.guidance_generation,
                pursuit_paused=binding.pursuit_paused, effective_continuity_policy=asdict(supervisor.policy),
                continuity=supervisor.get_status(), injected_target_loss=loss_active,
                airspeed_fault_requested=bool(fault_injection is not None and fault_injection.active),
                events=["injected_target_loss"] if loss_active else [], limiting_reason=decision.reason_code))
            if decision.handoff_request is not None:
                handoff_reason, handoff_time = decision.reason_code, elapsed
                break
            await asyncio.sleep(.05)
        await commander.stop(publish_final=False)
        native_publications = binding.transport.observed_publications
        handoff = await binding.stop(handoff_reason or "isolated_sih_complete")
        supervisor.record_handoff_result(success=handoff["executed"], detail=handoff["reason"])
        log("handoff.jsonl", dict(timestamp=time.monotonic() - follow_start, result=handoff,
                                 continuity=supervisor.get_status()))
        await client.connect()
        await client.bind(aircraft)
        packet = await client.observe()
        log("final-observation.jsonl", packet)
        after_stop = []
        for _ in range(5):
            await asyncio.sleep(.1)
            stopped_packet = await client.observe()
            after_stop.append(stopped_packet["publications"])
            log("post-stop-observations.jsonl", stopped_packet)
        altitude_error = max(abs(row["altitude_m"] - initial_altitude) for row in response)
        checks = dict(range_decreased=response[-1]["range_m"] < response[0]["range_m"],
                      altitude_floor=min(row["altitude_m"] for row in response) >= follower.altitude_limits.min_altitude,
                      finite_observed_response=all(math.isfinite(row["range_m"]) for row in response),
                      no_publication_after_stop=len(set(after_stop + [packet["publications"]])) == 1,
                      hold_confirmed=handoff["executed"],
                      no_publication_failure=commander.failed_publishes == 0,
                      expected_handoff=handoff_reason == args.expect_handoff)
        if args.altitude:
            checks["altitude_guidance_response"] = response[-1]["altitude_m"] < initial_altitude - .5
        else:
            checks["altitude_hold"] = altitude_error <= args.altitude_tolerance
        result = dict(passed=all(checks.values()), reason="component_scenario_complete", response_checks=checks,
                      scope="native_guidance_component_only", follower=selected.profile.mode,
                      input_contract=selected.input_contract, handoff=handoff,
                      successful_publications=commander.successful_publishes - initial_publications,
                      observed_native_publications=native_publications,
                      failed_publications=commander.failed_publishes, initial_relative_altitude_m=initial_altitude,
                      final_relative_altitude_m=packet["aircraft_state"]["relative_altitude_m"],
                      target_range_start_m=response[0]["range_m"], target_range_end_m=response[-1]["range_m"],
                      maximum_altitude_change_m=altitude_error,
                      maximum_altitude_hold_error_m=None if args.altitude else altitude_error,
                      required_altitude_hold_tolerance_m=None if args.altitude else args.altitude_tolerance,
                      phase_segments=phase_response_segments(response),
                      handoff_reason=handoff_reason, handoff_time_s=handoff_time,
                      expected_handoff_reason=args.expect_handoff,
                      application_startup_qualified=False)
    except Exception as error:
        result = dict(passed=False, reason=f"{type(error).__name__}:{error}")
        raise
    finally:
        await cleanup_component_run(commander, binding, fault_injection, result)
        if fault_injection is not None:
            fault_checks = airspeed_fault_response_checks(response, fault_injection.events)
            result.setdefault("response_checks", {}).update(fault_checks)
            if not all(fault_checks.values()):
                if result["passed"]:
                    result["reason"] = "airspeed_fault_response_not_observed"
                result["passed"] = False
                result["fault_response_failures"] = [key for key, value in fault_checks.items() if not value]
        if failure_injection_enabled is not None:
            result["failure_injection_enabled"] = failure_injection_enabled
        await client.close()
        try:
            (output / "px4/parameters-after.txt").write_text(native_parameters(
                args.socket, isolation))
        except Exception as error:
            result["passed"] = False
            result["parameter_snapshot_error"] = str(error)
        (output / "result.json").write_text(json.dumps(result, indent=2))
        for log_file in logs.values():
            log_file.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--container", required=True)
    parser.add_argument("--instance", type=int, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--follower", default="gm_velocity_vector", help="Registered native FW profile; input follows its declared contract")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/config_default.yaml")
    parser.add_argument("--sih-build-manifest", type=Path, help="Verify the running executable against a pinned source-built SIH bundle")
    parser.add_argument("--scenario", type=Path, help="Version-2 world-target YAML; must match mount, altitude and actual airframe")
    parser.add_argument("--expect-handoff", help="Expected production reason code; an absent or different handoff fails the test")
    parser.add_argument("--mount", choices=("HORIZONTAL", "VERTICAL"), required=True)
    parser.add_argument("--altitude", action="store_true")
    parser.add_argument("--duration", type=float, default=15.)
    parser.add_argument("--stable-timeout", type=float, default=90.)
    parser.add_argument("--test-altitude", type=float, default=30., help="Stable SIH altitude, home-relative metres")
    parser.add_argument("--altitude-tolerance", type=float, default=2., help="Maximum measured hold error, metres")
    parser.add_argument("--mc-request", type=float, help="Explicit simulated operator speed adjustment in initial VTOL MC")
    args = parser.parse_args()
    if not 1. <= args.duration <= 60. or not 1. <= args.stable_timeout <= 180.:
        parser.error("Scenario duration must be 1–60 s; stable timeout must be 1–180 s")
    if not 15. <= args.test_altitude <= 120. or not 0. < args.altitude_tolerance <= 10.:
        parser.error("SIH altitude must be 15–120 m; hold tolerance must be (0,10] m")
    if args.mc_request is not None and (not math.isfinite(args.mc_request) or args.mc_request < 0.):
        parser.error("MC request must be finite and nonnegative")
    try:
        component_profile(args.follower)
    except ValueError as error:
        parser.error(str(error))
    isolation = verify_simulator(args.container, args.instance, args.socket, sih_build_manifest=args.sih_build_manifest)
    if not args.execute:
        print(json.dumps(dict(execute=False, isolation=isolation), indent=2))
        return
    result = asyncio.run(run(args, isolation))
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
