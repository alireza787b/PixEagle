#!/usr/bin/env python3
"""Exercise production native guidance on an already airborne isolated simulator.

Dry-run by default. This tool never arms, takes off or flashes. An explicitly
declared pilot_transition stimulus toggles only the verified isolated simulator.
It verifies the Docker SIH/Gazebo process before acquiring native authority.
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
import tempfile
import time
from types import SimpleNamespace
from typing import Literal
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from classes.aircraft_state import AircraftBinding, AircraftState, AircraftStateOwner, AirframePhase, GuidanceSessionIdentity, Quaternion, finite_number  # noqa: E402
from classes.follower_catalog import FollowerProfile, NATIVE_PHASE_CONTRACTS, get_follower_profile  # noqa: E402
from classes.following_readiness import evaluate_follower_guidance_input  # noqa: E402
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy  # noqa: E402
from classes.follower import FollowerFactory  # noqa: E402
from classes.native_follow_binding import NativeFollowBinding  # noqa: E402
from classes.native_guidance import NativeGuidanceClient, NativeReleaseReceipt  # noqa: E402
from classes.offboard_commander import OffboardCommander  # noqa: E402
from classes.parameters import Parameters  # noqa: E402
from classes.guidance_observation import PinholeCalibration  # noqa: E402
from classes.gimbal_geometry import resolve_angle_geometry  # noqa: E402
from classes.observation_alignment import AlignmentBinding  # noqa: E402
from classes.sih_visualization import VisualizationScenario  # noqa: E402
from classes.target_continuity import ContinuityContext, ContinuityPolicy, IdentityVerdict, TargetContinuitySupervisor, TargetEvidenceSnapshot, TargetEvidenceState  # noqa: E402
from classes.tracker_output import TrackerDataType, TrackerOutput  # noqa: E402
from tools.fixed_camera_bearing_fixture import FixedCameraBearingFixture  # noqa: E402
from tools.gimbal_bearing_fixture import GimbalBearingFixture  # noqa: E402
from tools.fixed_camera_world_target import FixedCamera  # noqa: E402
from tools.sih_isolated_host import verified_simulation_build  # noqa: E402
from tools.native_sih_wire import WireRecorder, archive_wire_helper  # noqa: E402


@dataclass(frozen=True)
class ComponentProfile:
    profile: FollowerProfile
    tracker_type: TrackerDataType
    input_contract: str
    template: Path

    def command_contract(self, *, is_vtol: bool) -> str:
        native = self.profile.phase_command_contracts
        if is_vtol and all(native.get(phase) == contract for phase, contract in NATIVE_PHASE_CONTRACTS.items()):
            return "vtol_external"
        return native["fixed_wing"]


@dataclass(frozen=True)
class ComponentFaultWindow:
    kind: Literal["target_loss", "airspeed_loss"]
    start_s: float
    end_s: float


@dataclass(frozen=True)
class PilotTransitionEvent:
    at_s: float
    requested_phase: AirframePhase


def host_boot_id():
    return str(uuid.UUID(Path("/proc/sys/kernel/random/boot_id").read_text().strip()))


@dataclass(frozen=True)
class WorldTargetClock:
    """Immutable test truth and a host clock; never aircraft/control state."""
    path: Path
    artifact_bytes: bytes
    scenario_path: Path
    scenario_bytes: bytes
    target_id: str
    origin_s: float
    boot_id: str
    scenario: VisualizationScenario

    @classmethod
    def from_file(cls, path: Path, *, now=None):
        path = path.resolve()
        data = path.read_bytes()
        raw = json.loads(data)
        fields = {"schema_version", "target_id", "frame", "host_monotonic_origin_s", "host_boot_id",
                  "scenario_yaml", "scenario_sha256"}
        if (not isinstance(raw, dict) or set(raw) != fields or type(raw["schema_version"]) is not int
                or raw["schema_version"] != 1 or raw["frame"] != "local_ned"
                or not isinstance(raw["target_id"], str) or not raw["target_id"].strip()
                or not isinstance(raw["scenario_yaml"], str) or not raw["scenario_yaml"]
                or not isinstance(raw["scenario_sha256"], str)
                or re.fullmatch("[0-9a-f]{64}", raw["scenario_sha256"]) is None):
            raise ValueError("native_component_target_clock_invalid")
        origin = finite_number(raw["host_monotonic_origin_s"], "target_clock_origin")
        if origin < 0. or raw["host_boot_id"] != host_boot_id():
            raise ValueError("native_component_target_clock_boot_or_origin_invalid")
        source = Path(raw["scenario_yaml"])
        source = source if source.is_absolute() else path.parent/source
        source = source.resolve()
        source_bytes = source.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != raw["scenario_sha256"]:
            raise ValueError("native_component_target_clock_scenario_changed")
        result = cls(path, data, source, source_bytes, raw["target_id"], origin, raw["host_boot_id"],
                     VisualizationScenario.from_yaml(source))
        result.require_current(now=time.monotonic() if now is None else now)
        return result

    def require_current(self, *, now):
        try:
            unchanged = (self.path.read_bytes() == self.artifact_bytes
                         and self.scenario_path.read_bytes() == self.scenario_bytes and self.boot_id == host_boot_id())
        except OSError as error:
            raise ValueError("native_component_target_clock_changed") from error
        if not unchanged:
            raise ValueError("native_component_target_clock_changed")
        if finite_number(now, "target_clock_now") < self.origin_s:
            raise ValueError("native_component_target_clock_future_origin")

    def require_coverage(self, host_start_s, duration_s):
        if finite_number(duration_s, "target_clock_duration") <= 0.:
            raise ValueError("native_component_target_clock_duration_invalid")
        self.target_at_host(host_start_s)
        self.target_at_host(host_start_s + duration_s)

    def target_at_host(self, receipt_s):
        value = self.scenario.target_at(finite_number(receipt_s, "target_clock_receipt") - self.origin_s)
        if value is None:
            raise ValueError("native_component_target_clock_coverage_missing")
        return value

    def require_matching_target(self, raw):
        original = yaml.safe_load(self.scenario_bytes)["target"]
        if json.dumps(raw.get("target"), sort_keys=True, allow_nan=False) != json.dumps(original, sort_keys=True, allow_nan=False):
            raise ValueError("native_component_target_clock_target_changed")

    def slice_raw(self, raw, *, host_start_s, duration_s):
        self.require_coverage(host_start_s, duration_s)
        offset = host_start_s-self.origin_s
        points = [dict(time_s=0., position_ned=self.target_at_host(host_start_s))]
        points.extend(dict(time_s=point.time_s-offset, position_ned=point.position_ned)
                      for point in self.scenario.target_waypoints if offset < point.time_s < offset+duration_s)
        points.append(dict(time_s=duration_s, position_ned=self.target_at_host(host_start_s+duration_s)))
        result = dict(raw)
        result["target"] = {**yaml.safe_load(self.scenario_bytes)["target"], "waypoints": points}
        return result

    def archive(self, output):
        (output/"target-clock.json").write_bytes(self.artifact_bytes)
        (output/"original-target-scenario.yaml").write_bytes(self.scenario_bytes)
        return dict(target_id=self.target_id, frame="local_ned", host_monotonic_origin_s=self.origin_s,
            host_boot_id=self.boot_id, clock_path="target-clock.json",
            clock_sha256=hashlib.sha256(self.artifact_bytes).hexdigest(),
            scenario_path="original-target-scenario.yaml", scenario_sha256=hashlib.sha256(self.scenario_bytes).hexdigest())


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


def require_component_phase(selected: ComponentProfile, state: AircraftState):
    if state.phase.value not in selected.profile.phase_command_contracts:
        raise ValueError("native_component_profile_phase_unavailable")


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


def gimbal_fixture(state: AircraftState, *, mount_type: str, runtime_id: str, run_id: str, clock=time.monotonic):
    if state.attitude_timing is None:
        raise ValueError('native_component_attitude_timing_unavailable')
    geometry = resolve_angle_geometry(Parameters.GimbalTracker, mount_type)
    provider_id = 'simulated_gimbal_world_target'
    mapping = hashlib.sha256(json.dumps(dict(provider=provider_id, mount=mount_type, mapping=asdict(geometry)),
                                       sort_keys=True, allow_nan=False).encode()).hexdigest()
    binding = AlignmentBinding(f'simulated-gimbal:{run_id}', 1, f'sih-gimbal-mapping:{mapping}', None,
        1, state.binding, runtime_id, state.attitude_timing.quat_reset_counter, provider_id=provider_id)
    return GimbalBearingFixture(binding=binding, mount_type=mount_type, geometry=geometry,
        fixture_revision='gimbal-native-pose-v1', clock=clock,
        max_observation_age_s=.5, max_attitude_age_s=.5, allow_simulation=True)


def bind_component_fixture(selected, follower, raw, state, *, mount_type, runtime_id, run_id, clock=time.monotonic):
    """Bind one explicit simulation resolver before acquiring native authority."""
    if selected.tracker_type is TrackerDataType.POSITION_2D:
        fixture = image_fixture(raw, state, runtime_id=runtime_id, run_id=run_id, clock=clock)
    elif selected.tracker_type is TrackerDataType.GIMBAL_ANGLES:
        fixture = gimbal_fixture(state, mount_type=mount_type, runtime_id=runtime_id, run_id=run_id, clock=clock)
    else:
        raise ValueError('native_component_input_unsupported')
    follower.bind_guidance_input_resolver(fixture.resolve)
    return fixture


def measurement_time(output: TrackerOutput | None) -> float | None:
    """Read the producer's receipt unchanged; polling never becomes a sample."""
    if output is None or not output.tracking_active:
        return None
    measured = getattr(output, "image_measurement", None)
    value = (measured.provenance.capture.captured_at if measured is not None
             else output.raw_data.get("angle_sample_monotonic"))
    return None if value is None else finite_number(value, "native_component_measurement_time")


def measurement_world_target(output: TrackerOutput, _current_target):
    if measurement_time(output) is None:
        return None
    measured = output.image_measurement if output.data_type is TrackerDataType.POSITION_2D else output.gimbal_observation
    return output.raw_data.get('measurement_target_ned') if measured is not None else None


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


def project_component_input(fixture, packet, state, target, *, timestamp_s):
    """Keep projection refusals in the existing continuity evidence contract."""
    try:
        return fixture.project(packet, state, tuple(target), timestamp_s=timestamp_s)
    except ValueError as error:
        if str(error) not in {
            "sih_projection_attitude_stale", "sih_projection_pose_stale", "sih_projection_frame_stale",
            "sih_projection_native_state_unavailable", "alignment_attitude_stale", "image_receipt_stale",
            "alignment_observation_receipt_stale_or_future", "guidance_input_stale",
        }:
            raise
        # Missing/delayed association is not a new image or boresight sample.
        return TrackerOutput(fixture.tracker_type, timestamp_s, False,
            tracker_id="simulated_native_bearing", raw_data={
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


def pilot_transition_event(faults, duration) -> PilotTransitionEvent | None:
    events = [fault for fault in faults if fault.get("kind") == "pilot_transition"]
    if not events:
        return None
    if len(events) != 1 or len(faults) != 1:
        raise ValueError("native_component_transition_event_mixed_or_repeated")
    event = events[0]
    if set(event) != {"kind", "at_s", "requested_phase"}:
        raise ValueError("native_component_transition_event_invalid")
    at = finite_number(event["at_s"], "transition_event_time")
    if not 0. < at < duration:
        raise ValueError("native_component_transition_event_invalid")
    try:
        phase = AirframePhase(event["requested_phase"])
    except (ValueError, TypeError) as error:
        raise ValueError("native_component_transition_phase_invalid") from error
    if phase not in (AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING):
        raise ValueError("native_component_transition_phase_invalid")
    return PilotTransitionEvent(at, phase)


def transition_source_contract(isolation, *, build_repository: Path | None = None):
    """Read CLI phase constants from the exact source-built firmware, once."""
    from tools.build_native_guidance import verify_extension
    from tools.sih_baseline import verify_source

    build = isolation.get("firmware_build")
    if not build:
        raise ValueError("native_component_transition_requires_verified_source_build")
    source = Path(build["manifest"]).resolve().parent / "context/source"
    simulator, checked, _ = verified_simulation_build(Path(build["manifest"]), repository=build_repository)
    if checked != build:
        raise ValueError("native_component_transition_build_changed")
    verify_source(source, ROOT if build_repository is None else build_repository, verify_extension,
                  **({} if simulator == "sih" else {"simulator": simulator}))
    message = source / "msg/versioned/VehicleStatus.msg"
    fields = {}
    for phase, name in (("multicopter", "VEHICLE_TYPE_ROTARY_WING"), ("fixed_wing", "VEHICLE_TYPE_FIXED_WING")):
        values = re.findall(rf"(?m)^uint8 {name}\s*=\s*(\d+)\s*(?:#[^\n]*)?$", message.read_text())
        if len(values) != 1:
            raise ValueError("native_component_transition_constants_missing")
        fields[phase] = int(values[0])
    return dict(vehicle_types=fields, source=str(message), sha256=hashlib.sha256(message.read_bytes()).hexdigest())


def native_pilot_transition(socket, isolation, event, initial_phase, contract, *, build_repository: Path | None = None):
    """One opposite-phase simulator CLI request; a zero exit is not phase proof."""
    if build_repository is not None and not (isolation.get("firmware_build") or {}).get("manifest"):
        raise ValueError("An explicit simulation build repository requires a verified build manifest")
    authority = {} if build_repository is None else {"build_repository": build_repository}
    checked = verify_simulator(isolation["container_id"], isolation["instance"], socket,
        simulation_build_manifest=Path(isolation["firmware_build"]["manifest"]), **authority)
    if (any(checked[key] != isolation[key] for key in ("container_id", "image_id", "aircraft_uid"))
            or checked.get("firmware_build") != isolation.get("firmware_build")):
        raise ValueError("native_component_transition_simulator_changed")
    executable = Path(isolation["process"]["args"][0])
    prefix = ("docker", "exec", "--user", str(socket.stat().st_uid), isolation["container_id"])
    status = command(*prefix, str(executable.with_name("px4-listener")), "--instance", str(isolation["instance"]),
                     "vehicle_status", "-n", "1")
    def field(name):
        values = re.findall(rf"(?mi)^\s*{name}:\s*(\S+)\s*$", status)
        return values[0].lower() if len(values) == 1 else None
    age = re.search(r"timestamp:\s*\d+\s*\(([0-9.]+) seconds ago\)", status)
    if (not age or float(age.group(1)) > .75 or field("is_vtol") != "true"
            or field("in_transition_mode") != "false"
            or field("vehicle_type") != str(contract["vehicle_types"][initial_phase.value])
            or event.requested_phase is initial_phase):
        raise ValueError("native_component_transition_precondition_changed")
    argv = (*prefix, str(executable.with_name("px4-commander")), "--instance", str(isolation["instance"]), "transition")
    started = time.monotonic()
    try:
        result = subprocess.run(argv, text=True, capture_output=True, timeout=15, check=False)
        return dict(argv=list(argv), returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
                    before_vehicle_status=status, started_at_monotonic_s=started, finished_at_monotonic_s=time.monotonic())
    except (OSError, subprocess.TimeoutExpired) as error:
        return dict(argv=list(argv), returncode=None, error=f"{type(error).__name__}:{error}",
                    before_vehicle_status=status, started_at_monotonic_s=started, finished_at_monotonic_s=time.monotonic())


class PilotTransitionInjection:
    """One declared test action; never retry, reverse, restore or acquire a mode."""
    def __init__(self, socket, isolation, event, initial_phase, contract, *, log, started, clock=time.monotonic,
                 build_repository=None):
        self.socket, self.isolation, self.event = socket, isolation, event
        self.initial_phase, self.contract = initial_phase, contract
        self.log, self.started, self.clock = log, started, clock
        self.build_repository = build_repository
        self.events = []
        self.requested = False
        self._task = None

    async def _apply(self):
        authority = {} if self.build_repository is None else {"build_repository": self.build_repository}
        command_result = await asyncio.to_thread(native_pilot_transition, self.socket, self.isolation,
                                                self.event, self.initial_phase, self.contract, **authority)
        record = dict(kind="pilot_transition", timestamp=self.clock()-self.started,
            requested_phase=self.event.requested_phase.value, from_phase=self.initial_phase.value,
            command=command_result)
        self.events.append(record)
        self.log("fault-events.jsonl", record)
        if command_result.get("returncode") != 0:
            raise RuntimeError("native_component_transition_command_unconfirmed")

    async def tick(self, elapsed, state, owner_confirmed):
        if self._task is not None and self._task.done():
            task, self._task = self._task, None
            await task
        if self.requested or elapsed < self.event.at_s:
            return
        if (not state or not state.fresh(self.clock(), .75) or not state.is_vtol
                or state.rescue_active or state.phase is not self.initial_phase or owner_confirmed is not True):
            raise ValueError("native_component_transition_pursuit_not_current")
        self.requested = True
        self._task = asyncio.create_task(self._apply(), name="native-sih-pilot-transition")

    async def close(self):
        if self._task is not None:
            task, self._task = self._task, None
            await task


def transition_witness(wire, *, event, acquisition, not_before_s, host_origin_s):
    for row in wire:
        if row.get("direction") != "actual_backend_reply" or row.get("timestamp", -1.) < not_before_s:
            continue
        packet = row.get("value", {}).get("payload", {})
        if (packet.get("fresh") is not True or packet.get("runtime_id") != acquisition.runtime_id
                or not packet.get("aircraft_state")):
            continue
        state = AircraftState.from_payload(packet["aircraft_state"])
        if (not state.fresh(host_origin_s+row["timestamp"], .75)
                or state.binding != acquisition.identity.binding or not state.is_vtol or state.rescue_active
                or state.phase is not AirframePhase.VTOL_TRANSITION):
            continue
        receipt = packet.get("release_receipt")
        if receipt is not None:
            NativeReleaseReceipt.from_payload(receipt).require_match(acquisition.identity, acquisition.runtime_id,
                                                                    acquisition.token, acquisition)
        return row
    return None


def pilot_transition_checks(injection, witness, terminal_reason, expected_reason, post):
    return dict(
        pilot_transition_command_succeeded=bool(injection.events and injection.events[-1]["command"].get("returncode") == 0),
        pilot_transition_observed=witness is not None,
        backend_transition_ended=terminal_reason == expected_reason == "aircraft_transition_observed",
        requested_phase_settled=post is not None and post["settled"] is True,
    )


async def wait_transition_terminal(binding, commander, *, expected_reason, timeout_s, clock=time.monotonic):
    """Wait for the already-running attempt; create no intent or completion."""
    if finite_number(timeout_s, "transition_terminal_wait") <= 0.:
        raise ValueError("native_component_transition_terminal_wait_invalid")
    deadline = clock()+timeout_s
    while True:
        reason = binding.terminal_reason
        status = commander.get_status()
        if reason is not None and reason != expected_reason:
            raise ValueError("native_component_transition_terminal_reason_mismatch:"+reason)
        if status["failed_publishes"] != 0:
            raise ValueError("native_component_transition_publication_failed")
        if status["terminal_failure"] and status["terminal_failure_reason"] != expected_reason:
            raise ValueError("native_component_transition_commander_reason_mismatch")
        if (reason == expected_reason and status["terminal_failure"] is True
                and status["running"] is False and status["task_active"] is False):
            return status
        remaining = deadline-clock()
        if remaining <= 0.:
            raise TimeoutError("native_component_transition_terminal_completion_missing")
        await asyncio.sleep(min(.01, remaining))


def record_released_observation(packet, acquisition, *, captured_at, follow_start, log,
                                scenario, response=None, previous_pose_timestamp_us=None,
                                release_observed_at=None, previous_publications=None, world_clock=None):
    """Project this actual packet; return state and source/release/counter cursors."""
    if (packet.get("owner_confirmed") is not False or packet.get("runtime_id") != acquisition.runtime_id
            or packet.get("rescue_active") is not False):
        raise ValueError("native_component_post_transition_owner_or_rescue")
    receipt = NativeReleaseReceipt.from_payload(packet.get("release_receipt"))
    receipt.require_match(acquisition.identity, acquisition.runtime_id, acquisition.token, acquisition)
    if not receipt.released:
        raise ValueError("native_component_post_transition_release_unconfirmed")
    publications = packet.get("publications")
    if type(publications) is not int or publications < 0:
        raise ValueError("native_component_publication_count_invalid")
    if previous_publications is not None and publications != previous_publications:
        raise ValueError("native_component_publication_after_release")
    unchanged = (None, previous_pose_timestamp_us, release_observed_at, publications)
    if packet.get("fresh") is not True or not packet.get("aircraft_state") or not packet.get("vehicle_pose"):
        return unchanged
    captured_at = finite_number(captured_at, "native_component_capture_receipt")
    state = AircraftState.from_payload(packet["aircraft_state"])
    if state.binding != acquisition.identity.binding:
        raise ValueError("native_component_post_transition_aircraft_changed")
    pose_received = finite_number(packet["vehicle_pose"].get("observed_at_monotonic_s"),
                                  "native_component_pose_receipt")
    if pose_received < 0. or pose_received > captured_at:
        raise ValueError("native_component_pose_receipt_invalid")
    if not state.fresh(captured_at, .75) or captured_at-pose_received > .75:
        return unchanged
    pose = observed_pose_record(packet, follow_start=follow_start, previous_timestamp_us=previous_pose_timestamp_us)
    elapsed = captured_at-follow_start
    target = (world_clock.target_at_host(captured_at) if world_clock is not None else scenario.target_at(elapsed))
    if target is None:
        raise ValueError("native_component_post_transition_target_truth_missing")
    if response is not None:
        response.append(dict(timestamp=elapsed, phase=state.phase.value,
            range_m=math.dist(packet["vehicle_pose"]["vehicle_ned"], target), altitude_m=state.relative_altitude_m,
            pursuit_active=False, authority_held=False))
    log("trace/target_truth.jsonl", dict(timestamp=elapsed, target_ned=target))
    if pose is not None:
        log("px4/pose_trace.jsonl", pose)
        previous_pose_timestamp_us = pose["px4_timestamp_us"]
    held = packet.get("nav_state") == 4
    if held and release_observed_at is None:
        release_observed_at = elapsed
    log("trace/follower_state.jsonl", dict(timestamp=elapsed, state="INACTIVE", phase_state="ended",
        authority_state="INACTIVE", command_expected=False, observed_hold=held,
        publisher_running=False, publisher_task_active=False,
        command_owner_released_at=release_observed_at, aircraft_phase=state.phase.value,
        aircraft_observed_at_monotonic_s=state.observed_at_monotonic_s,
        pose_observed_at_monotonic_s=pose_received, pose_timestamp_us=packet["vehicle_pose"]["px4_timestamp_us"],
        captured_at_monotonic_s=captured_at,
        limiting_reason="session_cleanup_after_phase_evidence", events=["post_session_native_transition"]))
    return state, previous_pose_timestamp_us, release_observed_at, publications


async def capture_post_transition(client, event, acquisition, *, log, started, follow_start, timeout_s,
                                  scenario, response, previous_pose_timestamp_us=None, world_clock=None,
                                  release_observed_at=None, previous_publications=None, clock=time.monotonic):
    """Read only after publisher join/release; observed motion remains PX4 truth."""
    deadline = clock() + timeout_s
    window, samples, publications, previous_pose = [], [], previous_publications, previous_pose_timestamp_us
    while clock() < deadline:
        packet = await client.observe()
        captured_at = clock()
        log("post-transition-observations.jsonl", dict(timestamp=captured_at-started, value=packet))
        state, previous_pose, release_observed_at, publications = record_released_observation(
            packet, acquisition, captured_at=captured_at, follow_start=follow_start, log=log,
            scenario=scenario, response=response, previous_pose_timestamp_us=previous_pose,
            release_observed_at=release_observed_at, previous_publications=publications, world_clock=world_clock)
        if state is not None:
            samples.append(state)
            if state.phase is event.requested_phase and packet.get("nav_state") == 4:
                if (not window or state.sequence > window[-1][0].sequence
                        and state.observed_at_monotonic_s - window[-1][0].observed_at_monotonic_s >= .49):
                    window = (window + [stability_sample(state, packet, captured_at=captured_at)])[-7:]
                if stable_samples(window):
                    return dict(settled=True, states=[asdict(item[0]) for item in window], publications=publications,
                                last_packet=packet, samples=len(samples))
            else:
                window = []
        else:
            window = []
        await asyncio.sleep(.05)
    raise TimeoutError("native_component_post_transition_settle_timeout")


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


async def stop_component_publisher(commander):
    """A failed existing join cannot authorize an inactive capture marker."""
    if await commander.stop(publish_final=False) is False:
        raise RuntimeError("native_component_publisher_not_quiesced")


async def cleanup_component_run(commander, binding, fault_injection, result):
    """Quiesce/release control before waiting for test-sensor CLI cleanup."""
    try:
        try:
            if commander is not None and commander.running:
                await stop_component_publisher(commander)
        except Exception as error:
            result["passed"] = False
            result["publisher_cleanup_error"] = str(error)
    finally:
        try:
            try:
                if binding is not None and (binding.owner_confirmed or getattr(binding, "acquire_dispatched", False)):
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


def gazebo_airframe_identity(manifest: dict, packaged: Path) -> tuple[dict, str, str]:
    """Read only literal identity declarations from the attested packaged airframe."""
    airframe_id = manifest["build"]["airframe_id"]
    names = [name for name in manifest["artifacts"]["etc"]
             if re.fullmatch(rf"init\.d-posix/airframes/{airframe_id}_[A-Za-z0-9_]+", name)]
    if len(names) != 1:
        raise ValueError("Gazebo packaged airframe identity is ambiguous")
    name = names[0]
    path = packaged / "etc" / name
    checksum = manifest["artifacts"]["etc"][name].get("sha256")
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise ValueError("Gazebo packaged airframe differs from the verified manifest")
    lines = [line.split("#", 1)[0].strip() for line in path.read_text().splitlines()]
    if any(re.match(r"^(?:if|elif|else|fi|case|esac|for|while|until|do|done|function)\b", line) for line in lines):
        raise ValueError("Gazebo airframe identity requires unconditional literal declarations")
    expected = {"SYS_AUTOSTART": airframe_id}
    for key in ("CA_ROTOR_COUNT", "CA_SV_CS_COUNT", "VT_TYPE", "SIM_GZ_EN"):
        declarations = [line for line in lines if re.search(rf"\b{key}\b", line)]
        match = (re.fullmatch(rf"param\s+set-default\s+{key}\s+([+-]?[0-9]+)", declarations[0])
                 if len(declarations) == 1 else None)
        if match is None:
            raise ValueError(f"Gazebo airframe identity declaration is missing or ambiguous: {key}")
        expected[key] = int(match.group(1))
    return expected, name, checksum


def verify_gazebo_runtime(container, instance, uid, process, manifest, *, packaged: Path):
    """Read the locked scene, resource bytes and allocator identity; send no control."""
    spec = manifest["build"]
    expected_parameters, airframe, airframe_sha256 = gazebo_airframe_identity(manifest, packaged)
    model, world = f'{spec["model"]}_{instance}', spec["world"]
    environment = process.get("environment", {})
    required_environment = {
        "PX4_GZ_WORLD": world,
        "PX4_GZ_MODELS": "/opt/px4/gazebo/models",
        "PX4_GZ_WORLDS": "/opt/px4/gazebo/worlds",
        "GZ_SIM_RESOURCE_PATH": "/opt/px4/gazebo/models:/opt/px4/gazebo/worlds",
        "GZ_SIM_SYSTEM_PLUGIN_PATH": "/opt/px4/gazebo/plugins",
        "GZ_SIM_SERVER_CONFIG_PATH": "/opt/px4/gazebo/server.config",
    }
    if any(environment.get(key) != value for key, value in required_environment.items()):
        raise ValueError("Gazebo process resource paths differ from the packaged build")
    partition = environment.get("GZ_PARTITION")
    if not isinstance(partition, str) or not partition.strip():
        raise ValueError("Gazebo requires a nonempty process transport partition")
    prefix = ("docker", "exec", "--user", str(uid), "-e", "GZ_PARTITION=" + partition, container)
    # Inspect the container filesystem, including symlink targets and file modes.
    script = """import hashlib,json,pathlib,sys
base=pathlib.Path('/opt/px4/gazebo'); result={}
for p in sorted(base.rglob('*')):
 if p.is_symlink(): result[str(p.relative_to(base))]={'link':str(p.readlink())}
 elif p.is_file(): result[str(p.relative_to(base))]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'executable':bool(p.stat().st_mode&0o111)}
airframe=pathlib.Path('/opt/px4/etc')/sys.argv[1]
print(json.dumps({'gazebo':result,'airframe_sha256':hashlib.sha256(airframe.read_bytes()).hexdigest()}))
"""
    observed = json.loads(command(*prefix, "python3", "-c", script, airframe))
    resources = observed.get("gazebo")
    if resources != manifest["artifacts"]["gazebo"] or observed.get("airframe_sha256") != airframe_sha256:
        raise ValueError("Gazebo runtime resources differ from the verified build")
    scene = command(*prefix, "gz", "service", "-s", f"/world/{world}/scene/info",
                    "--reqtype", "gz.msgs.Empty", "--reptype", "gz.msgs.Scene", "--timeout", "2000", "--req", "")
    models = re.findall(r'(?m)^model \{\n  name: "([^"\n]+)"\n', scene)
    if sorted(models) != sorted(["ground_plane", model]):
        raise ValueError("Gazebo scene does not contain only the locked aircraft and ground plane")
    topics = command(*prefix, "gz", "topic", "-l")
    observed_topics = set(topics.splitlines())
    required_topics = {f"/world/{world}/pose/info", f"/world/{world}/dynamic_pose/info",
                       f"/model/{model}/odometry_with_covariance",
                       f"/world/{world}/model/{model}/link/base_link/sensor/imu_sensor/imu"}
    if (not required_topics <= observed_topics
            or set(re.findall(r"(?m)^/world/([^/]+)/", topics)) != {world}
            or set(re.findall(r"/model/([^/]+)/", topics)) != {model}):
        raise ValueError("Gazebo topics do not identify the locked world and model")
    parameter_executable = str(Path(process["args"][0]).with_name("px4-param"))
    parameters = command(*prefix, parameter_executable, "--instance", str(instance), "show")
    for name, value in expected_parameters.items():
        found = re.findall(rf"(?m)^\s*[x+* ]*{name}(?:\s+\[[^]\n]+\])?\s*:\s*(\S+)\s*$", parameters)
        if found != [str(value)]:
            raise ValueError(f"Gazebo aircraft parameter differs from the locked quad tailsitter: {name}")
    return dict(model=model, world=world, parameters=parameters, scene=scene, topics=topics,
                airframe=airframe, airframe_sha256=airframe_sha256, expected_parameters=expected_parameters,
                resources_sha256=hashlib.sha256(json.dumps(resources, sort_keys=True).encode()).hexdigest())


def verify_simulator(container: str, instance: int, socket: Path, *, simulation_build_manifest: Path | None = None,
                     build_repository: Path | None = None) -> dict:
    if build_repository is not None and simulation_build_manifest is None:
        raise ValueError("An explicit simulation build repository requires a verified build manifest")
    info = json.loads(command("docker", "inspect", container))[0]
    if (info["HostConfig"]["NetworkMode"] != "none" or info["HostConfig"]["Privileged"]
            or info["HostConfig"].get("Devices") or info["NetworkSettings"]["Ports"]):
        raise ValueError("Simulation requires an isolated container without hardware or published ports")
    simulator, baseline, manifest = "sih", None, None
    if simulation_build_manifest is not None:
        simulator, baseline, manifest = verified_simulation_build(simulation_build_manifest, repository=build_repository)
        if simulator == "gazebo" and info["Image"] != baseline["image_id"]:
            raise ValueError("Running simulator image differs from the verified source build")
    # Inspect the real process and inherited model, not an operator-supplied label.
    script = """import hashlib, json, pathlib, sys
out=[]
for p in pathlib.Path('/proc').iterdir():
 try:
  args=(p/'cmdline').read_bytes().split(b'\\0'); args=[x.decode() for x in args if x]
  env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode().split('\\0') if '=' in x)
  if args and pathlib.Path(args[0]).name=='px4':
   value=dict(args=args, model=env.get('PX4_SIM_MODEL'), cwd=str((p/'cwd').resolve()),
              environment={k: env.get(k) for k in ('PX4_GZ_WORLD', 'PX4_GZ_MODELS', 'PX4_GZ_WORLDS',
               'GZ_SIM_RESOURCE_PATH', 'GZ_SIM_SYSTEM_PLUGIN_PATH', 'GZ_SIM_SERVER_CONFIG_PATH', 'GZ_PARTITION')})
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
    if len(matches) != 1:
        raise ValueError("An unambiguous running PX4 SIH or Gazebo instance is required")
    process = matches[0]
    expected_model = "gz_" + manifest["build"]["model"] if simulator == "gazebo" else None
    if (process["model"] != expected_model if expected_model else not str(process["model"]).startswith("sihsim_")):
        raise ValueError("Running simulator model requires its matching verified build manifest")
    if baseline is not None and process.get("binary_sha256") != baseline["binary_sha256"]:
        raise ValueError("Running simulator binary differs from the verified source build")
    mapped = [str(Path(m["Destination"]) / socket.resolve().relative_to(Path(m["Source"])))
              for m in info["Mounts"] if socket.resolve().is_relative_to(Path(m["Source"]))]
    if len(mapped) != 1 or not socket.is_socket():
        raise ValueError("Native socket must be in the verified simulation container bind mount")
    gazebo = (verify_gazebo_runtime(container, instance, socket.stat().st_uid, process, manifest,
                                    packaged=Path(baseline["manifest"]).parent / "packaged")
              if simulator == "gazebo" else None)
    listener = str(Path(process["args"][0]).with_name("px4-listener"))
    status = command("docker", "exec", "--user", str(socket.stat().st_uid), container, listener, "--instance", str(instance),
                     "fixed_wing_guidance_status", "-n", "1")
    uid = re.search(r"autopilot_uid:\s*(\d+)", status)
    if uid is None:
        raise ValueError("Simulator aircraft UID is unavailable")
    return dict(container_id=info["Id"], image_id=info["Image"], instance=instance,
                process=process, aircraft_uid=uid.group(1), native_socket=mapped[0],
                initial_native_status=status, firmware_build=baseline, simulator=simulator, gazebo=gazebo)


def stable_window(states: list[AircraftState], *, minimum_relative_altitude_m=15., expected_altitude_m=None,
                  native_airspeed_control_enabled: list[bool] | None = None) -> bool:
    """Sensorless admission needs native control feedback paired with each state.

    Callers check packet freshness and retain matching native feedback. State
    time is the oldest constituent receipt, so independent airspeed receipt may
    be newer; this predicate bounds their association, not absolute packet age.
    Unavailable airspeed never becomes a measurement or stall-margin estimate.
    """
    if len(states) < 7:
        return False
    if native_airspeed_control_enabled is not None and (
            len(native_airspeed_control_enabled) != len(states)
            or any(type(value) is not bool for value in native_airspeed_control_enabled)):
        return False
    phase = states[0].phase
    if phase not in (AirframePhase.FIXED_WING, AirframePhase.MULTICOPTER):
        return False
    if any(s.phase is not phase or s.rescue_active or s.fixed_wing_envelope is None
           or s.binding != states[0].binding or s.source != states[0].source
           or s.altitude_reference_generation != states[0].altitude_reference_generation
           or s.relative_altitude_m < minimum_relative_altitude_m for s in states):
        return False
    if any(current.sequence <= previous.sequence
           or not 0. < current.observed_at_monotonic_s - previous.observed_at_monotonic_s <= .75
           for previous, current in zip(states, states[1:])):
        return False
    if phase is AirframePhase.FIXED_WING:
        for index, state in enumerate(states):
            airspeed = state.airspeed
            if abs(state.observed_at_monotonic_s - airspeed.observed_at_monotonic_s) > .75:
                return False
            if airspeed.valid:
                if airspeed.equivalent_m_s is None or airspeed.equivalent_m_s < state.fixed_wing_envelope.minimum_eas_m_s:
                    return False
            elif (native_airspeed_control_enabled is None or native_airspeed_control_enabled[index]
                    or airspeed.source != "unavailable" or airspeed.equivalent_m_s is not None
                    or airspeed.true_m_s is not None):
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


def stability_sample(state: AircraftState, packet, *, captured_at: float) -> tuple[AircraftState, bool | None]:
    """Retain only feedback belonging to this accepted native snapshot."""
    flag = None
    feedback = packet.get("native_guidance_feedback")
    if isinstance(feedback, dict):
        received = feedback.get("observed_at_monotonic_s")
        mode, epoch = packet.get("nav_state"), packet.get("nav_state_timestamp")
        try:
            matched_state = AircraftState.from_payload(packet["aircraft_state"]) == state
        except (KeyError, TypeError, ValueError):
            matched_state = False
        if (matched_state and packet.get("fresh") is True and state.fresh(captured_at, .75)
                and type(feedback.get("airspeed_control_enabled")) is bool
                and type(received) in (int, float) and math.isfinite(received)
                and state.observed_at_monotonic_s <= received <= captured_at
                and captured_at-received <= .75
                and type(mode) is int and type(epoch) is int and epoch > 0
                and type(feedback.get("nav_state")) is int and feedback["nav_state"] == mode
                and type(feedback.get("nav_state_timestamp")) is int and feedback["nav_state_timestamp"] == epoch):
            flag = feedback["airspeed_control_enabled"]
    return state, flag


def forward_ground_speed(state: AircraftState) -> float:
    """Observed navigation motion, never measured or estimated airspeed."""
    heading = state.navigation_heading_rad
    return state.velocity_ned_m_s.x * math.cos(heading) + state.velocity_ned_m_s.y * math.sin(heading)


def forward_motion_ready(states, minimum_m_s: float) -> bool:
    """A declared simulator-start condition, separate from any stall policy."""
    if type(minimum_m_s) not in (int, float) or not math.isfinite(minimum_m_s) or minimum_m_s <= 0.:
        raise ValueError("native_component_motion_threshold_invalid")
    return bool(states) and all(state.phase is AirframePhase.FIXED_WING
        and math.isfinite(speed := forward_ground_speed(state)) and speed >= minimum_m_s
        for state in states)


def stable_samples(samples, *, expected_altitude_m=None, minimum_forward_ground_speed_m_s=None) -> bool:
    states = [sample[0] for sample in samples]
    controls = ([sample[1] for sample in samples]
                if any(state.phase is AirframePhase.FIXED_WING and not state.airspeed.valid for state in states)
                else None)
    stable = stable_window(states, expected_altitude_m=expected_altitude_m,
                           native_airspeed_control_enabled=controls)
    return stable and (minimum_forward_ground_speed_m_s is None
        or forward_motion_ready(states, minimum_forward_ground_speed_m_s))


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
        coherent = state is not None and connection.retain_packet(state, packet)
        log("observations.jsonl", dict(timestamp=clock()-started, value=packet,
                                      retained_for_projection=coherent))
        return await original_observer(state, packet, intent)

    binding.on_observation = observation
    binding.transport.on_observation = observation


async def refresh_component_start(client, connection, qualified_window, *, runtime_id, expected_altitude_m,
                                  deadline, log, started, clock=time.monotonic,
                                  minimum_forward_ground_speed_m_s=None):
    """Read actual state after setup; never refresh a retained sample's receipt."""
    original = qualified_window[-1][0]
    previous_pose = connection.last_packet["vehicle_pose"]["px4_timestamp_us"]
    while True:
        remaining = deadline - clock()
        if remaining <= 0.:
            raise TimeoutError("native_component_start_refresh_deadline")
        packet = await asyncio.wait_for(client.observe(), timeout=remaining)
        log("observations.jsonl", dict(timestamp=clock()-started, value=packet, purpose="pre_projection_start_refresh"))
        if clock() >= deadline:
            raise TimeoutError("native_component_start_refresh_deadline")
        if (packet.get("runtime_id") != runtime_id or packet.get("fresh") is not True
                or packet.get("owner_confirmed") is not False or packet.get("rescue_active") is not False
                or packet.get("nav_state") != 4 or packet.get("phase_status_fresh") is not True
                or packet.get("release_pending") is not False or packet.get("neutral_drain_active") is not False):
            raise ValueError("native_component_start_refresh_unqualified")
        state = AircraftState.from_payload(packet["aircraft_state"])
        same_oldest = state.observed_at_monotonic_s == original.observed_at_monotonic_s
        # A composite update is current telemetry, not another timed stability sample.
        sample = stability_sample(state, packet, captured_at=clock())
        window = [*qualified_window[:-1], sample] if same_oldest else [*qualified_window, sample]
        pose = packet.get("vehicle_pose", {}).get("px4_timestamp_us")
        if (state.attitude_timing is None or original.attitude_timing is None
                or state.attitude_timing.quat_reset_counter != original.attitude_timing.quat_reset_counter
                or type(pose) is not int or pose < previous_pose
                or not stable_samples(window, expected_altitude_m=expected_altitude_m,
                    minimum_forward_ground_speed_m_s=minimum_forward_ground_speed_m_s)
                or (state != connection.get_aircraft_state() and not connection.commit_aircraft_state(state))
                or not connection.retain_packet(state, packet)):
            raise ValueError("native_component_start_refresh_not_stable")
        previous_pose = pose
        if not same_oldest:
            return state
        await asyncio.sleep(min(.05, max(0., deadline-clock())))


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
    if "pilot_transition" in kinds:
        pilot_transition_event(faults, duration)
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


def pursuit_response(response, initial_altitude):
    """Select measured pursuit rows, retaining the separate full native response."""
    active = [row for row in response if row.get("pursuit_active") is True]
    if not active:
        raise ValueError("native_component_pursuit_response_missing")
    return dict(samples=len(active), start_s=active[0]["timestamp"], end_s=active[-1]["timestamp"],
        range_start_m=active[0]["range_m"], range_end_m=active[-1]["range_m"],
        final_altitude_m=active[-1]["altitude_m"],
        minimum_altitude_m=min(row["altitude_m"] for row in active),
        maximum_altitude_error_m=max(abs(row["altitude_m"] - initial_altitude) for row in active),
        finite=all(math.isfinite(row["range_m"]) and math.isfinite(row["altitude_m"]) for row in active),
        scope="Fresh observed pursuit rows; independent native ownership/phase/ULog audit still required")


def transition_fence_checks(wire, witness):
    from tools.run_native_ownership_sih import wire_requests

    return dict(no_write_after_phase_witness=witness is not None and all(
        request["operation"] in ("hello", "bind", "observe")
        for request in wire_requests(wire, after=witness["timestamp"])))


def phase_exit_release_confirmed(handoff, acquisition, packet):
    from tools.run_native_ownership_sih import coherent_hold

    receipt = NativeReleaseReceipt.from_payload(handoff.get("release_receipt")).require_match(
        acquisition.identity, acquisition.runtime_id, acquisition.token, acquisition)
    if (handoff.get("local_sender_quiesced") is not True or not receipt.released
            or packet.get("release_receipt") != receipt.wire_payload()
            or packet.get("runtime_id") != acquisition.runtime_id or packet.get("fresh") is not True
            or packet.get("aircraft_state", {}).get("binding") != asdict(acquisition.identity.binding)
            or packet.get("owner_confirmed") is not False or packet.get("rescue_active") is not False
            or packet.get("phase_status_fresh") is not True or packet.get("release_pending") is not False
            or packet.get("neutral_drain_active") is not False):
        return False
    if receipt.outcome == "hold_confirmed":
        # Native conditional release can enter Hold while preserving the transition.
        return (handoff.get("executed") is True and handoff.get("reason") == "aircraft_transition_observed"
                and coherent_hold(packet, acquisition, 4))
    return handoff.get("executed") is False and handoff.get("reason") == "native_owner_already_released"


async def run(args, isolation):
    selected = component_profile(args.follower)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for directory in ("trace", "px4"):
        (output / directory).mkdir()
    world_clock = (WorldTargetClock.from_file(args.target_clock) if getattr(args, "target_clock", None) else None)
    if world_clock is not None and args.scenario is None:
        raise ValueError("native_component_target_clock_requires_scenario")
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
    started = time.monotonic()
    tool_bytes = Path(__file__).read_bytes()
    (output / "run_native_vector_sih.py").write_bytes(tool_bytes)
    (output / "manifest.json").write_text(json.dumps(dict(
        evidence_kind="px4_observed_" + isolation.get("simulator", "sih"), qualification="native_guidance_component",
        application_startup_qualified=False, revision=source, worktree_dirty=bool(patch),
        isolation=isolation, altitude_guidance=args.altitude, mount=args.mount,
        follower=selected.profile.mode, input_contract=selected.input_contract,
        simulated_tracker_input=True,
        argv=list(sys.argv), working_directory=str(Path.cwd()),
        configuration=configuration,
        parameter_snapshots={"before": "px4/parameters-before.txt", "after": "px4/parameters-after.txt"},
        expected_handoff_reason=args.expect_handoff,
        host_clock={"basis": "time.monotonic", "origin_s": started,
                    "wire_timestamp_semantics": "seconds_since_origin",
                    "trace_timestamp_semantics": "seconds_since_follow_start; follow-clock.json binds its offset"},
        tool_source_sha256=hashlib.sha256(tool_bytes).hexdigest(),
        tool_helpers={"wire_recorder": archive_wire_helper(output)},
        world_target=None if world_clock is None else world_clock.archive(output),
        transition_acceptance={"maximum_altitude_error_m": 2., "maximum_native_active_gap_s": .100,
                               "independent_ulog_audit_required": True},
    ), indent=2))
    logs = {}
    wire = []

    def log(name, value):
        if name == "wire.jsonl":
            value = {"timestamp": time.monotonic() - started, **value}
            wire.append(value)
        if name not in logs:
            logs[name] = (output / name).open("x")
        logs[name].write(json.dumps(value, allow_nan=False) + "\n")
        logs[name].flush()

    client = recorder = socket_directory = None
    commander = binding = fault_injection = pilot_fault = None
    failure_injection_enabled = None
    response = []
    result = dict(passed=False, reason="not_started")
    try:
        socket_directory = tempfile.TemporaryDirectory(prefix="pe-vec-")
        recorder = WireRecorder(Path(socket_directory.name) / "record.sock", args.socket, log)
        await recorder.__aenter__()
        client = NativeGuidanceClient(recorder.frontend)
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
                    if not window or state.sequence > window[-1][0].sequence:
                        window = (window + [stability_sample(state, packet, captured_at=time.monotonic())])[-7:]
                    if stable_samples(window, expected_altitude_m=args.test_altitude,
                            minimum_forward_ground_speed_m_s=getattr(args, "minimum_forward_ground_speed_m_s", None)):
                        break
                else:
                    window = []
            else:
                window = []
            await asyncio.sleep(.5)
        else:
            raise ValueError("stable_airborne_window_not_reached")
        log("stable-flight.jsonl", dict(timestamp=time.monotonic() - started, states=[asdict(s[0]) for s in window]))
        if getattr(args, "initial_phase", None) is not None and state.phase.value != args.initial_phase:
            raise ValueError("native_component_initial_phase_mismatch")
        require_component_phase(selected, state)
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
        if world_clock is not None:
            world_clock.require_matching_target(scenario_raw)
        if (selected.tracker_type is TrackerDataType.POSITION_2D
                and scenario_raw.get("mount_type") != args.mount):
            raise ValueError("native_component_fixed_camera_mount_mismatch")
        scenario_raw.update(name=output.name, mount_type=args.mount, initial_conditions={"vehicle_ned": origin})
        scenario_raw["evidence_provenance"] = "px4_" + isolation.get("simulator", "sih")
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
        transition = pilot_transition_event(scenario.faults, args.duration)
        transition_contract = None
        if transition:
            if (not state.is_vtol or transition.requested_phase is state.phase
                    or args.expect_handoff != "aircraft_transition_observed"
                    or args.altitude or args.altitude_tolerance != 2.):
                raise ValueError("native_component_transition_scenario_contract_mismatch")
            if scenario.target_at(args.duration + args.stable_timeout) is None:
                raise ValueError("native_component_post_transition_target_truth_missing")
            authority = {} if getattr(args, "build_repository", None) is None else {"build_repository": args.build_repository}
            transition_contract = transition_source_contract(isolation, **authority)
            (output / "transition-source-contract.json").write_text(json.dumps(transition_contract, indent=2))
        loss_windows = [(window.start_s, window.end_s) for window in fault_windows if window.kind == "target_loss"]
        airspeed_windows = tuple(window for window in fault_windows if window.kind == "airspeed_loss")
        if airspeed_windows:
            failure_injection_enabled = False
            require_airspeed_failure_injection(parameters_before, isolation)
            failure_injection_enabled = True
        projected = bind_component_fixture(selected, follower, scenario_raw, state, mount_type=args.mount,
                                           runtime_id=capabilities.runtime_id, run_id=output.name)

        def tracker_input(packet, state, target):
            return project_component_input(projected, packet, state, target, timestamp_s=time.time())

        guidance = follower.create_airframe_session(
            GuidanceSessionIdentity(output.name, aircraft, 1), capabilities,
            confirmation_s=config["Follower"]["AIRFRAME_PHASE_CONFIRMATION_S"],
            observation_timeout_s=.75, initial_phase=state.phase,
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
        state = await refresh_component_start(client, connection, window, runtime_id=capabilities.runtime_id,
            expected_altitude_m=args.test_altitude, deadline=started+args.stable_timeout, log=log, started=started,
            minimum_forward_ground_speed_m_s=getattr(args, "minimum_forward_ground_speed_m_s", None))
        initial_target = (world_clock.target_at_host(connection.last_packet["vehicle_pose"]["observed_at_monotonic_s"])
                          if world_clock is not None else scenario.target_at(0.))
        (output / "start-pose.json").write_text(json.dumps(dict(
            aircraft_state=asdict(state), vehicle_pose=connection.last_packet["vehicle_pose"],
            navigation_heading_rad=state.navigation_heading_rad, target_ned=initial_target,
            target_clock=None if world_clock is None else dict(target_id=world_clock.target_id,
                host_monotonic_origin_s=world_clock.origin_s)), indent=2))
        target_output[0] = tracker_input(connection.last_packet, state, initial_target)
        initial_evidence = target_evidence()
        if initial_evidence.state is not TargetEvidenceState.CONFIRMED:
            raise ValueError(initial_evidence.reason_code)
        def target_clock_current():
            if world_clock is not None:
                now = time.monotonic()
                world_clock.require_current(now=now)
                world_clock.require_coverage(now, args.duration+(args.stable_timeout if transition else 0.))

        target_clock_current()
        publications_before_acquire = connection.last_packet['publications']
        baseline = await binding.engage(before_dispatch=target_clock_current if world_clock is not None else None)
        (output / "acquisition.json").write_text(json.dumps(asdict(client.acquisition_context), indent=2))
        follower.bind_airframe_session(guidance)

        async def published(event):
            intent = event["command_intent"]
            log("trace/offboard_publish_trace.jsonl", dict(
                record_type="offboard_publish", timestamp=time.monotonic() - follow_start,
                publish_success=event["publish_status"]["last_publish_success"],
                publish_status=event["publish_status"],
                command_intent=None if intent is None else asdict(intent)))

        commander = OffboardCommander(connection, follower.setpoint_handler, command_rate_hz=20.,
                                      command_ttl_s=.3, command_transport=binding.transport,
                                      on_publish_result=published)
        if not commander.submit_intent(baseline):
            raise ValueError(commander.last_error)
        follow_start = time.monotonic()
        if world_clock is not None:
            scenario_raw = world_clock.slice_raw(scenario_raw, host_start_s=follow_start,
                duration_s=args.duration+(args.stable_timeout if transition else 0.))
            scenario_path.write_text(yaml.safe_dump(scenario_raw, sort_keys=False))
            scenario = VisualizationScenario.from_yaml(scenario_path)
        (output / "follow-clock.json").write_text(json.dumps(dict(
            host_origin_s=started, follow_offset_s=follow_start-started,
            target_time_offset_s=None if world_clock is None else follow_start-world_clock.origin_s), indent=2))
        if airspeed_windows:
            fault_injection = AirspeedLossInjection(args.socket, isolation, airspeed_windows, log=log, started=follow_start)
        if transition:
            pilot_fault = PilotTransitionInjection(args.socket, isolation, transition, state.phase,
                transition_contract, log=log, started=follow_start,
                build_repository=getattr(args, "build_repository", None))
        if not await commander.start():
            raise ValueError(commander.last_error)
        initial_altitude = state.relative_altitude_m
        pursuit_phase = state.phase
        initial_publications = commander.successful_publishes
        mc_request_applied = False
        handoff_reason = None
        handoff_time = None
        phase_witness = None
        terminal_before_cleanup = None
        previous_pose_timestamp = None
        while (elapsed := time.monotonic() - follow_start) < args.duration:
            if fault_injection is not None:
                await fault_injection.tick(elapsed)
            packet = connection.last_packet
            state = connection.get_aircraft_state()
            if pilot_fault is not None:
                if pilot_fault.requested:
                    phase_witness = transition_witness(wire, event=transition, acquisition=client.acquisition_context,
                        not_before_s=follow_start-started+transition.at_s, host_origin_s=started)
                    if phase_witness is not None:
                        # The relay can forward this reply before its existing
                        # transport observer has finished processing it.
                        completed = await wait_transition_terminal(binding, commander,
                            expected_reason=args.expect_handoff,
                            timeout_s=commander.publish_timeout_s+commander.command_period_s)
                        terminal_before_cleanup = binding.terminal_reason
                        handoff_reason, handoff_time = terminal_before_cleanup, elapsed
                        result["backend_terminal_reason_before_cleanup"] = terminal_before_cleanup
                        log("transition-terminal-proof.jsonl", dict(timestamp=elapsed,
                            backend_terminal_reason=terminal_before_cleanup, witness=phase_witness,
                            commander_status=completed))
                        break
            if state is None or not commander.running or commander.failed_publishes:
                raise ValueError("native_publication_or_state_unhealthy")
            if pilot_fault is not None:
                await pilot_fault.tick(elapsed, state, binding.owner_confirmed)
            if (args.mc_request is not None and not mc_request_applied and not binding.pursuit_paused
                    and state.phase is AirframePhase.MULTICOPTER):
                control = guidance.controls.current_control
                follower.update_session_control("requested_speed", args.mc_request, control.revision)
                mc_request_applied = True
                log("session-control-updates.jsonl", dict(timestamp=elapsed, control="requested_speed",
                    value=args.mc_request, guidance_identity=asdict(guidance.identity)))
            target = (world_clock.target_at_host(follow_start+elapsed) if world_clock is not None
                      else scenario.target_at(elapsed))
            pose_time = max(0., packet["vehicle_pose"]["observed_at_monotonic_s"] - follow_start)
            measurement_target = (world_clock.target_at_host(packet["vehicle_pose"]["observed_at_monotonic_s"])
                                  if world_clock is not None else scenario.target_at(pose_time))
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
                                 pose_observed_at=p["observed_at_monotonic_s"],
                                 pursuit_active=packet.get("owner_confirmed") is True and state.phase is pursuit_phase,
                                 authority_held=packet.get("owner_confirmed") is True))
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
        await stop_component_publisher(commander)
        native_publications = binding.transport.observed_publications
        handoff = await binding.stop(handoff_reason or "isolated_sih_complete")
        supervisor.record_handoff_result(success=handoff["executed"], detail=handoff["reason"])
        log("handoff.jsonl", dict(timestamp=time.monotonic() - follow_start, result=handoff,
                                 continuity=supervisor.get_status()))
        await client.connect()
        await client.bind(aircraft)
        packet = await client.observe()
        captured_at = time.monotonic()
        log("final-observation.jsonl", packet)
        release_observed_at = released_publications = None
        if pilot_fault is not None:
            _, previous_pose_timestamp, release_observed_at, released_publications = record_released_observation(
                packet, client.acquisition_context, captured_at=captured_at, follow_start=follow_start, log=log,
                scenario=scenario, previous_pose_timestamp_us=previous_pose_timestamp, world_clock=world_clock)
        after_stop = []
        for _ in range(5):
            await asyncio.sleep(.1)
            stopped_packet = await client.observe()
            captured_at = time.monotonic()
            after_stop.append(stopped_packet["publications"])
            log("post-stop-observations.jsonl", stopped_packet)
            if pilot_fault is not None:
                _, previous_pose_timestamp, release_observed_at, released_publications = record_released_observation(
                    stopped_packet, client.acquisition_context, captured_at=captured_at, follow_start=follow_start,
                    log=log, scenario=scenario, previous_pose_timestamp_us=previous_pose_timestamp,
                    release_observed_at=release_observed_at, previous_publications=released_publications,
                    world_clock=world_clock)
        post_transition = None
        if pilot_fault is not None:
            await pilot_fault.close()
            post_transition = await capture_post_transition(client, transition, client.acquisition_context,
                log=log, started=started, follow_start=follow_start, timeout_s=args.stable_timeout,
                scenario=scenario, response=response, previous_pose_timestamp_us=previous_pose_timestamp,
                release_observed_at=release_observed_at, previous_publications=released_publications,
                world_clock=world_clock)
            packet = post_transition["last_packet"]
            (output / "post-transition-settled.json").write_text(json.dumps(post_transition, indent=2))
        if world_clock is not None:
            scenario_raw = world_clock.slice_raw(scenario_raw, host_start_s=follow_start,
                duration_s=max(args.duration, max(row["timestamp"] for row in response)))
            scenario_path.write_text(yaml.safe_dump(scenario_raw, sort_keys=False))
        altitude_error = max(abs(row["altitude_m"] - initial_altitude) for row in response)
        pursuit = pursuit_response(response, initial_altitude)
        checks = dict(range_decreased=pursuit["range_end_m"] < pursuit["range_start_m"],
                      altitude_floor=pursuit["minimum_altitude_m"] >= follower.altitude_limits.min_altitude,
                      finite_observed_response=pursuit["finite"],
                      no_publication_after_stop=len(set(after_stop + [packet["publications"]])) == 1,
                      hold_confirmed=handoff["executed"],
                      no_publication_failure=commander.failed_publishes == 0,
                      expected_handoff=handoff_reason == args.expect_handoff)
        if pilot_fault is None:
            from tools.run_native_ownership_sih import coherent_hold

            checks["hold_confirmed"] = handoff["executed"] is True and coherent_hold(
                stopped_packet, client.acquisition_context, 4)
        if args.altitude:
            checks["altitude_guidance_response"] = pursuit["final_altitude_m"] < initial_altitude - .5
        else:
            checks["altitude_hold"] = pursuit["maximum_altitude_error_m"] <= args.altitude_tolerance
        if pilot_fault is not None:
            checks.pop("hold_confirmed")
            checks["phase_exit_release_confirmed"] = phase_exit_release_confirmed(
                handoff, client.acquisition_context, packet)
            checks.update(pilot_transition_checks(pilot_fault, phase_witness, terminal_before_cleanup,
                                                  args.expect_handoff, post_transition))
            checks.update(transition_fence_checks(wire, phase_witness))
        result = dict(passed=all(checks.values()), reason="component_scenario_complete", response_checks=checks,
                      scope="native_guidance_component_only", follower=selected.profile.mode,
                      input_contract=selected.input_contract, handoff=handoff,
                      successful_publications=commander.successful_publishes - initial_publications,
                      observed_native_publications=native_publications,
                      native_publication_counter=dict(before=publications_before_acquire, after=packet['publications']),
                      failed_publications=commander.failed_publishes, initial_relative_altitude_m=initial_altitude,
                      final_relative_altitude_m=packet["aircraft_state"]["relative_altitude_m"],
                      target_range_start_m=pursuit["range_start_m"], target_range_end_m=pursuit["range_end_m"],
                      maximum_altitude_change_m=altitude_error,
                      maximum_altitude_hold_error_m=None if args.altitude else pursuit["maximum_altitude_error_m"],
                      pursuit_response=pursuit,
                      full_native_response=dict(maximum_altitude_error_m=altitude_error,
                          range_start_m=response[0]["range_m"], range_end_m=response[-1]["range_m"],
                          includes_native_transition_after_release=True if pilot_fault is not None else False,
                          altitude_within_2m=altitude_error <= 2., performance_scope="diagnostic, independent of pursuit acceptance"),
                      required_altitude_hold_tolerance_m=None if args.altitude else args.altitude_tolerance,
                      phase_segments=phase_response_segments(response),
                      handoff_reason=handoff_reason, handoff_time_s=handoff_time,
                      expected_handoff_reason=args.expect_handoff,
                      application_startup_qualified=False)
        if pilot_fault is not None:
            result.update(backend_terminal_reason_before_cleanup=terminal_before_cleanup,
                transition_event=asdict(transition), fault_events=pilot_fault.events,
                independent_native_active_gap_audit={"required_maximum_s": .100, "verified": False},
                transition_qualified=False)
        if world_clock is not None:
            result["world_target"] = dict(target_id=world_clock.target_id,
                session_offset_s=follow_start-world_clock.origin_s,
                scenario_sha256=hashlib.sha256(world_clock.scenario_bytes).hexdigest())
    except Exception as error:
        result.update(passed=False, reason=f"{type(error).__name__}:{error}")
        raise
    finally:
        if pilot_fault is not None and binding is not None:
            result.setdefault("backend_terminal_reason_before_cleanup", binding.terminal_reason)
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
        if pilot_fault is not None:
            try:
                await pilot_fault.close()
            except Exception as error:
                result.update(passed=False, pilot_transition_task_error=str(error))
            result["pilot_transition_events"] = pilot_fault.events
        if client is not None:
            await client.close()
        if recorder is not None:
            await recorder.__aexit__()
        if socket_directory is not None:
            socket_directory.cleanup()
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--container", required=True)
    parser.add_argument("--instance", type=int, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--follower", default="gm_velocity_vector", help="Registered native FW profile; input follows its declared contract")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/config_default.yaml")
    parser.add_argument("--simulation-build-manifest", type=Path, help="Verify the running executable against a pinned source-built SIH or Gazebo bundle")
    parser.add_argument("--build-repository", type=Path, help="Explicit reviewed authority for the selected immutable simulation build")
    parser.add_argument("--scenario", type=Path, help="Version-2 world-target YAML; must match mount, altitude and actual airframe")
    parser.add_argument("--target-clock", type=Path, help="Immutable original YAML/target/host-clock artifact shared across explicit Starts")
    parser.add_argument("--expect-handoff", help="Expected production reason code; an absent or different handoff fails the test")
    parser.add_argument("--mount", choices=("HORIZONTAL", "VERTICAL"), required=True)
    parser.add_argument("--altitude", action="store_true")
    parser.add_argument("--duration", type=float, default=15.)
    parser.add_argument("--stable-timeout", type=float, default=90.)
    parser.add_argument("--test-altitude", type=float, default=30., help="Stable SIH altitude, home-relative metres")
    parser.add_argument("--altitude-tolerance", type=float, default=2., help="Maximum measured hold error, metres")
    parser.add_argument("--mc-request", type=float, help="Explicit simulated operator speed adjustment in initial VTOL MC")
    parser.add_argument("--initial-phase", choices=("multicopter", "fixed_wing"), help="Require a settled explicit-Start phase")
    args = parser.parse_args(argv)
    if not 1. <= args.duration <= 60. or not 1. <= args.stable_timeout <= 180.:
        parser.error("Scenario duration must be 1–60 s; stable timeout must be 1–180 s")
    if not 15. <= args.test_altitude <= 120. or not 0. < args.altitude_tolerance <= 10.:
        parser.error("SIH altitude must be 15–120 m; hold tolerance must be (0,10] m")
    if args.mc_request is not None and (not math.isfinite(args.mc_request) or args.mc_request < 0.):
        parser.error("MC request must be finite and nonnegative")
    try:
        component_profile(args.follower)
        if args.target_clock is not None:
            if args.scenario is None:
                parser.error("--target-clock requires an explicit --scenario")
            target_clock = WorldTargetClock.from_file(args.target_clock)
            target_clock.require_matching_target(yaml.safe_load(args.scenario.read_text()))
    except ValueError as error:
        parser.error(str(error))
    authority = {} if args.build_repository is None else {"build_repository": args.build_repository}
    isolation = verify_simulator(args.container, args.instance, args.socket,
        simulation_build_manifest=args.simulation_build_manifest, **authority)
    if not args.execute:
        print(json.dumps(dict(execute=False, isolation=isolation), indent=2))
        return
    result = asyncio.run(run(args, isolation))
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
