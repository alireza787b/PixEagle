"""Read-only SIH visualization data model and evidence alignment helpers.

This module consumes already-produced pose, target, tracker-command, and
Offboard-publication evidence. It never publishes commands and never integrates
command intent into a vehicle trajectory.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import yaml
from classes.aircraft_state import Quaternion, Vector3, finite_number, heading_frame_to_ned
from classes.follower_catalog import FollowerProfile, NATIVE_PHASE_CONTRACTS


class VisualizationValidationError(ValueError):
    """Evidence or scenario data cannot be safely visualized."""


@lru_cache(maxsize=1)
def _profile_contracts():
    path = Path(__file__).resolve().parents[2] / "configs/follower_commands.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["follower_profiles"]


def _expected_contract(profile: str, airframe: str):
    info = _profile_contracts().get(profile)
    if info is None:
        return None
    angular = "GIMBAL_ANGLES" in info.get("required_tracker_data", [])
    control = info["control_type"]
    input_type = "gimbal_angles" if angular else (
        "attitude_rate_image_position" if control == "attitude_rate" else "image_position_2d")
    try:
        declared = FollowerProfile.from_info(profile, info).phase_command_contracts
    except ValueError as error:
        raise VisualizationValidationError("Follower catalog contract is invalid") from error
    native = info.get("native_phase_contracts", {})
    if airframe == "vtol":
        if all(declared.get(phase) == contract for phase, contract in NATIVE_PHASE_CONTRACTS.items()):
            return airframe, input_type, "vtol_external"
        settled = {phase: contract for phase, contract in declared.items() if phase in {"multicopter", "fixed_wing"}}
        if len(settled) == 1:
            phase, contract = next(iter(settled.items()))
            return airframe, input_type, "gimbal_velocity_body" if angular and phase == "multicopter" else contract
    if airframe == "fixed_wing" and "fixed_wing" in native:
        return airframe, input_type, "fixed_wing_external"
    return info["airframe_phase"], input_type, "gimbal_velocity_body" if angular else control


@dataclass(frozen=True)
class ScenarioWaypoint:
    time_s: float
    position_ned: tuple[float, float, float]


@dataclass(frozen=True)
class VisualizationScenario:
    schema_version: int
    name: str
    rate_hz: float
    frame: str
    mount_type: str
    follower_profile: str
    follower_purpose: str
    input_contract: str
    command_contract: str
    lateral_guidance_mode: str
    altitude_control: bool
    requested_speed: Optional[float]
    initial_vehicle_ned: tuple[float, float, float]
    airframe: str
    speed_source_policy: str
    evidence_provenance: str
    stable_flight: dict[str, Any]
    acceptance: tuple[str, ...]
    limits: dict[str, float | None]
    target_waypoints: tuple[ScenarioWaypoint, ...]
    continuity_policy: dict[str, Any]
    faults: tuple[dict[str, Any], ...]
    expectations: tuple[str, ...]

    @classmethod
    def from_yaml(cls, path: Path) -> "VisualizationScenario":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise VisualizationValidationError(f"Cannot read scenario {path}: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise VisualizationValidationError("Scenario root must be an object")
        version = raw.get("schema_version", 0)
        if type(version) is not int or version not in (1, 2):
            raise VisualizationValidationError("Unsupported visualization scenario schema_version")
        frame = str(raw.get("frame", "local_ned"))
        if frame != "local_ned":
            raise VisualizationValidationError("Only local_ned visualization coordinates are supported")
        mount_type = str(raw.get("mount_type", "HORIZONTAL")).upper()
        if mount_type not in ("HORIZONTAL", "VERTICAL"):
            raise VisualizationValidationError("mount_type must be HORIZONTAL or VERTICAL")
        follower = raw.get("follower") or {}
        if not isinstance(follower, Mapping):
            raise VisualizationValidationError("follower must be an object")
        profile = str(follower.get("profile", ""))
        if not profile:
            raise VisualizationValidationError("follower.profile is required")
        follower_purpose = str(follower.get("purpose", "")).strip() or profile
        input_contract = str(follower.get("input_contract", "image_position_2d"))
        valid_input_contracts = {"image_position_2d", "gimbal_angles", "attitude_rate_image_position"}
        if input_contract not in valid_input_contracts:
            raise VisualizationValidationError(
                "follower.input_contract must be image_position_2d, gimbal_angles, or attitude_rate_image_position"
            )
        command_contract = str(follower.get("command_contract", "velocity_body_offboard"))
        valid_command_contracts = {"velocity_body_offboard", "attitude_rate", "gimbal_velocity_body",
                                   "fixed_wing_external", "vtol_external"}
        if command_contract not in valid_command_contracts:
            raise VisualizationValidationError(
                "follower.command_contract is unsupported"
            )
        native_contract = command_contract in {"fixed_wing_external", "vtol_external"}
        if native_contract and version < 2:
            raise VisualizationValidationError("Native command contracts require scenario schema_version 2")
        lateral_mode = str(follower.get("lateral_guidance_mode", "coordinated_turn"))
        if lateral_mode not in ("coordinated_turn", "sideslip"):
            raise VisualizationValidationError("follower.lateral_guidance_mode must be coordinated_turn or sideslip")
        rate_hz = float(raw.get("rate_hz", 20.0))
        if not math.isfinite(rate_hz) or not 0.0 < rate_hz <= 120.0:
            raise VisualizationValidationError("rate_hz must be finite and between 0 and 120")
        requested = follower.get("requested_speed")
        requested_speed = None if requested is None else float(requested)
        if requested_speed is not None and (not math.isfinite(requested_speed) or requested_speed < 0.0):
            raise VisualizationValidationError("follower.requested_speed must be finite and non-negative")
        initial = raw.get("initial_conditions") or {}
        if not isinstance(initial, Mapping):
            raise VisualizationValidationError("initial_conditions must be an object")
        initial_position = initial.get("vehicle_ned", [0.0, 0.0, 0.0])
        if not isinstance(initial_position, (list, tuple)) or len(initial_position) != 3:
            raise VisualizationValidationError("initial_conditions.vehicle_ned must contain three values")
        try:
            initial_vehicle_ned = tuple(float(value) for value in initial_position)
        except (TypeError, ValueError, OverflowError) as exc:
            raise VisualizationValidationError("initial_conditions.vehicle_ned must be numeric") from exc
        if not all(math.isfinite(value) for value in initial_vehicle_ned):
            raise VisualizationValidationError("initial_conditions.vehicle_ned must be finite")
        airframe = str(raw.get("airframe", "multicopter"))
        if airframe not in {"multicopter", "fixed_wing", "vtol"}:
            raise VisualizationValidationError("airframe must be multicopter, fixed_wing, or vtol")
        speed_source_policy = str(follower.get("speed_source_policy", "none"))
        if speed_source_policy not in {"none", "auto", "airspeed_only", "ground_speed_only", "native_auto"}:
            raise VisualizationValidationError("follower.speed_source_policy is invalid")
        if native_contract and speed_source_policy != "native_auto":
            raise VisualizationValidationError("Native FW/VTOL scenarios require automatic native speed-source semantics")
        evidence_provenance = str(raw.get("evidence_provenance", "synthetic_fixture"))
        if evidence_provenance not in {"synthetic_fixture", "px4_sih", "camera_field"}:
            raise VisualizationValidationError("evidence_provenance is invalid")
        stable_flight = raw.get("stable_flight") or {}
        if not isinstance(stable_flight, Mapping):
            raise VisualizationValidationError("stable_flight must be an object")
        constraints = raw.get("constraints") or {}
        if not isinstance(constraints, Mapping):
            raise VisualizationValidationError("constraints must be an object")
        limits = _read_limits(constraints)
        target = raw.get("target") or {}
        if not isinstance(target, Mapping):
            raise VisualizationValidationError("target must be an object")
        waypoints = _read_waypoints(target.get("waypoints"))
        continuity = raw.get("continuity_policy") or {}
        if not isinstance(continuity, Mapping):
            raise VisualizationValidationError("continuity_policy must be an object")
        faults = raw.get("faults") or []
        if not isinstance(faults, list) or not all(isinstance(item, Mapping) for item in faults):
            raise VisualizationValidationError("faults must be a list of objects")
        expectations = raw.get("expectations") or []
        if not isinstance(expectations, list) or not all(isinstance(item, str) for item in expectations):
            raise VisualizationValidationError("expectations must be a list of strings")
        acceptance = raw.get("acceptance") or []
        if not isinstance(acceptance, list) or not all(isinstance(item, str) for item in acceptance):
            raise VisualizationValidationError("acceptance must be a list of strings")
        expected = _expected_contract(profile, airframe)
        if expected and (airframe, input_contract, command_contract) != expected:
            raise VisualizationValidationError(
                f"{profile} contract must be airframe/input/command={expected}"
            )
        if airframe == "fixed_wing" and speed_source_policy == "none":
            raise VisualizationValidationError("fixed-wing scenarios require a speed_source_policy")
        return cls(
            schema_version=version,
            name=str(raw.get("name", path.stem)),
            rate_hz=rate_hz,
            frame=frame,
            mount_type=mount_type,
            follower_profile=profile,
            follower_purpose=follower_purpose,
            input_contract=input_contract,
            command_contract=command_contract,
            lateral_guidance_mode=lateral_mode,
            altitude_control=bool(follower.get("altitude_control", False)),
            requested_speed=requested_speed,
            initial_vehicle_ned=initial_vehicle_ned,
            airframe=airframe,
            speed_source_policy=speed_source_policy,
            evidence_provenance=evidence_provenance,
            stable_flight=dict(stable_flight),
            acceptance=tuple(acceptance),
            limits=limits,
            target_waypoints=waypoints,
            continuity_policy=dict(continuity),
            faults=tuple(dict(item) for item in faults),
            expectations=tuple(expectations),
        )

    def target_at(self, time_s: float) -> Optional[tuple[float, float, float]]:
        """Interpolate scenario truth; observed pose/commands are never interpolated."""
        if not self.target_waypoints:
            return None
        if time_s < self.target_waypoints[0].time_s or time_s > self.target_waypoints[-1].time_s:
            return None
        for left, right in zip(self.target_waypoints, self.target_waypoints[1:]):
            if left.time_s <= time_s <= right.time_s:
                span = right.time_s - left.time_s
                fraction = 0.0 if span <= 0.0 else (time_s - left.time_s) / span
                return tuple(
                    left.position_ned[index]
                    + fraction * (right.position_ned[index] - left.position_ned[index])
                    for index in range(3)
                )
        return self.target_waypoints[-1].position_ned


@dataclass
class VisualizationSample:
    timestamp: float
    target_ned: Optional[tuple[float, float, float]] = None
    target_timestamp_s: Optional[float] = None
    vehicle_ned: Optional[tuple[float, float, float]] = None
    vehicle_quaternion: Optional[tuple[float, float, float, float]] = None
    vehicle_forward_ned: Optional[tuple[float, float, float]] = None
    command_ned: Optional[tuple[float, float, float]] = None
    course_direction_ned: Optional[tuple[float, float, float]] = None
    command_contract: Optional[str] = None
    aircraft_phase: Optional[str] = None
    observed_eas_m_s: Optional[float] = None
    native_effective_eas_m_s: Optional[float] = None
    command: dict[str, float] = field(default_factory=dict)
    published: bool = False
    command_expected: Optional[bool] = None
    tracker_state: Optional[str] = None
    continuity_state: Optional[str] = None
    limiting_reason: Optional[str] = None
    requested_speed: Optional[float] = None
    effective_speed: Optional[float] = None
    speed_source: Optional[str] = None
    measurement_age_s: Optional[float] = None
    stale: bool = False
    events: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "target_ned": self.target_ned,
            "target_timestamp_s": self.target_timestamp_s,
            "vehicle_ned": self.vehicle_ned,
            "vehicle_quaternion": self.vehicle_quaternion,
            "vehicle_forward_ned": self.vehicle_forward_ned,
            "command_ned": self.command_ned,
            "course_direction_ned": self.course_direction_ned,
            "command_contract": self.command_contract,
            "aircraft_phase": self.aircraft_phase,
            "observed_eas_m_s": self.observed_eas_m_s,
            "native_effective_eas_m_s": self.native_effective_eas_m_s,
            "command": self.command,
            "published": self.published,
            "command_expected": self.command_expected,
            "tracker_state": self.tracker_state,
            "continuity_state": self.continuity_state,
            "limiting_reason": self.limiting_reason,
            "requested_speed": self.requested_speed,
            "effective_speed": self.effective_speed,
            "speed_source": self.speed_source,
            "measurement_age_s": self.measurement_age_s,
            "stale": self.stale,
            "events": self.events,
        }


def _read_limits(raw: Mapping[str, Any]) -> dict[str, float | None]:
    limits: dict[str, float | None] = {}
    for group_name, keys in {
        "velocity": ("forward", "right", "down"),
        "rate": ("yaw",),
    }.items():
        group = raw.get(group_name) or {}
        if not isinstance(group, Mapping):
            raise VisualizationValidationError(f"constraints.{group_name} must be an object")
        for key in keys:
            if key in group:
                value = float(group[key])
                if not math.isfinite(value) or value < 0.0:
                    raise VisualizationValidationError(
                        f"constraints.{group_name}.{key} must be finite and non-negative"
                    )
                limits[f"{group_name}_{key}"] = value
    altitude = raw.get("altitude") or {}
    if not isinstance(altitude, Mapping):
        raise VisualizationValidationError("constraints.altitude must be an object")
    for key in ("min", "max"):
        if key in altitude:
            if key == "max" and altitude[key] is None:
                limits['altitude_max'] = None
                continue
            value = float(altitude[key])
            if not math.isfinite(value):
                raise VisualizationValidationError(f"constraints.altitude.{key} must be finite")
            limits[f"altitude_{key}"] = value
    return limits


def _read_waypoints(raw: Any) -> tuple[ScenarioWaypoint, ...]:
    if not isinstance(raw, list) or len(raw) < 1:
        raise VisualizationValidationError("target.waypoints must contain at least one waypoint")
    result: list[ScenarioWaypoint] = []
    previous = -math.inf
    for item in raw:
        if not isinstance(item, Mapping):
            raise VisualizationValidationError("target waypoints must be objects")
        try:
            timestamp = float(item.get("time_s"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise VisualizationValidationError("target waypoint time_s must be numeric") from exc
        position = item.get("position_ned")
        if not isinstance(position, (list, tuple)) or len(position) != 3:
            raise VisualizationValidationError("target waypoint position_ned must contain three values")
        try:
            coordinates = tuple(float(value) for value in position)
        except (TypeError, ValueError, OverflowError) as exc:
            raise VisualizationValidationError("target waypoint coordinates must be numeric") from exc
        if not math.isfinite(timestamp) or timestamp < previous:
            raise VisualizationValidationError("target waypoint times must be finite and ordered")
        if not all(math.isfinite(value) for value in coordinates):
            raise VisualizationValidationError("target waypoint coordinates must be finite")
        result.append(ScenarioWaypoint(timestamp, coordinates))
        previous = timestamp
    return tuple(result)


def read_jsonl(path: Path, *, expected_record_type: Optional[str] = None) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    previous = -math.inf
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise VisualizationValidationError(f"{path}:{line_number} is not valid JSON: {exc}") from exc
        if not isinstance(record, Mapping):
            raise VisualizationValidationError(f"{path}:{line_number} must be an object")
        if expected_record_type and record.get("record_type") != expected_record_type:
            raise VisualizationValidationError(
                f"{path}:{line_number} record_type must be {expected_record_type!r}"
            )
        timestamp = _record_timestamp(record)
        if timestamp < previous:
            raise VisualizationValidationError(f"{path}:{line_number} timestamps are out of order")
        previous = timestamp
        records.append(dict(record))
    return records


def _record_timestamp(record: Mapping[str, Any]) -> float:
    try:
        timestamp = float(record["timestamp"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise VisualizationValidationError("trace record timestamp is missing or invalid") from exc
    if not math.isfinite(timestamp):
        raise VisualizationValidationError("trace record timestamp must be finite")
    return timestamp


def _vector(value: Any) -> Optional[tuple[float, float, float]]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        values = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError):
        return None
    return values if all(math.isfinite(item) for item in values) else None


def _nearest_fresh(records: list[dict[str, Any]], timestamp: float, max_age_s: float) -> Optional[dict[str, Any]]:
    candidate = None
    for record in records:
        if _record_timestamp(record) > timestamp:
            break
        candidate = record
    if candidate is None or timestamp - _record_timestamp(candidate) > max_age_s:
        return None
    return candidate


def load_evidence(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Load only read-only evidence files from an SIH report directory."""
    def first_existing(*relative_paths: str) -> Path:
        for relative in relative_paths:
            candidate = root / relative
            if candidate.is_file():
                return candidate
        return root / relative_paths[0]

    return {
        "pose": read_jsonl(first_existing(
            "px4/pose_trace.jsonl", "px4/vehicle_pose.jsonl", "px4/pose.jsonl",
        )),
        "target": read_jsonl(first_existing(
            "trace/target_truth.jsonl", "scenarios/target_truth.jsonl",
        )),
        "tracker": read_jsonl(
            first_existing("trace/tracker_command_trace.jsonl"),
            expected_record_type="tracker_command",
        ),
        "published": read_jsonl(
            first_existing("trace/offboard_publish_trace.jsonl"),
            expected_record_type="offboard_publish",
        ),
        "state": read_jsonl(first_existing("trace/follower_state.jsonl")),
    }


def _command_fields(record: Mapping[str, Any]) -> dict[str, float]:
    intent = record.get("command_intent") or {}
    fields = intent.get("fields") if isinstance(intent, Mapping) else None
    if not isinstance(fields, Mapping):
        fields = record.get("submitted_fields")
    if not isinstance(fields, Mapping):
        return {}
    result: dict[str, float] = {}
    for key in (
        "vel_body_fwd",
        "vel_body_right",
        "vel_body_down",
        "yawspeed_deg_s",
        "rollspeed_deg_s",
        "pitchspeed_deg_s",
        "thrust",
        "course_rad",
        "equivalent_airspeed_m_s",
        "height_rate_m_s",
        "altitude_amsl_m",
    ):
        if key in fields:
            try:
                value = float(fields[key])
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(value):
                result[key] = value
    return result


def _command_speed(command: Mapping[str, float]) -> Optional[float]:
    names = ("vel_body_fwd", "vel_body_right", "vel_body_down")
    if not all(name in command for name in names):
        return None
    return math.sqrt(sum(command[name] * command[name] for name in names))


def build_timeline(
    scenario: VisualizationScenario,
    evidence: Mapping[str, list[dict[str, Any]]],
    *,
    max_pose_age_s: float = 0.5,
    max_command_age_s: float = 0.5,
) -> list[VisualizationSample]:
    tracker = evidence.get("tracker", [])
    published = evidence.get("published", [])
    pose = evidence.get("pose", [])
    state = evidence.get("state", [])
    timestamps = sorted({
        _record_timestamp(record)
        for records in (tracker, published, pose, state, evidence.get("target", []))
        for record in records
    })
    result: list[VisualizationSample] = []
    released_owner_at = None
    for timestamp in timestamps:
        tracker_record = _nearest_fresh(tracker, timestamp, max_command_age_s)
        publish_record = _nearest_fresh(published, timestamp, max_command_age_s)
        pose_record = _nearest_fresh(pose, timestamp, max_pose_age_s)
        state_record = _nearest_fresh(state, timestamp, max_command_age_s)
        command_record = (publish_record if publish_record and publish_record.get("publish_success") is True
                          and _command_fields(publish_record) else tracker_record or publish_record or {})
        command = _command_fields(command_record)
        # A fresh observed Hold plus a stopped publisher proves that no command
        # is expected. Absence alone never proves release of command authority.
        release = state_record or {}
        released = (
            release.get("command_expected") is False
            and release.get("authority_state") == "INACTIVE"
            and release.get("observed_hold") is True
            and release.get("publisher_running") is False
            and release.get("publisher_task_active") is False
        )
        released_at = _optional_measurement(release.get("command_owner_released_at"))
        released = released and released_at is not None and released_at <= timestamp
        if release.get("command_expected") is True and release.get("authority_state") == "ACTIVE":
            released_owner_at = None
        elif released and released_owner_at is None:
            released_owner_at = released_at
        published_after_release = bool(
            released_owner_at is not None and publish_record and publish_record.get("publish_success") is True
            and _record_timestamp(publish_record) > released_owner_at
        )
        if released and not published_after_release:
            command = {}
        tracker_output = (tracker_record or {}).get("tracker_output") or {}
        command_intent = command_record.get("command_intent") or {}
        metadata = tracker_output.get("metadata") if isinstance(tracker_output, Mapping) else {}
        if not isinstance(metadata, Mapping):
            metadata = {}
        events: list[str] = []
        if published_after_release:
            events.append("publication_after_authority_release")
        state_events = (state_record or {}).get("events")
        if isinstance(state_events, list):
            events.extend(event for event in state_events if isinstance(event, str) and event)
        reason = command_intent.get("reason") if isinstance(command_intent, Mapping) else None
        if isinstance(reason, str) and reason:
            events.append(reason)
        if publish_record and publish_record.get("publish_success") is False:
            events.append("publish_failed")
        if publish_record and (publish_record.get("publish_status") or {}).get("failsafe_defaults_active") is True:
            events.append("fallback_defaults")
        target_record = _nearest_fresh(evidence.get("target", []), timestamp, max_command_age_s)
        target = _vector((target_record or {}).get("target_ned"))
        target_timestamp = _record_timestamp(target_record) if target is not None else None
        if target is None and not evidence.get("target"):
            target = _vector((tracker_record or {}).get("target_ned"))
            if target is not None:
                target_timestamp = _record_timestamp(tracker_record)
            else:
                target = scenario.target_at(timestamp)
                target_timestamp = timestamp if target is not None else None
        vehicle = _vector((pose_record or {}).get("vehicle_ned"))
        quaternion, forward, command_ned = _frame_vectors(pose_record or {}, command)
        contract = command_intent.get("control_type") or {
            "gimbal_velocity_body": "velocity_body_offboard", "velocity_body_offboard": "velocity_body_offboard",
            "attitude_rate": "attitude_rate", "fixed_wing_external": "fixed_wing_external",
        }.get(scenario.command_contract)
        aircraft_phase = (state_record or {}).get("aircraft_phase")
        native_scenario = scenario.command_contract in {"fixed_wing_external", "vtol_external"}
        legacy_fw_basis = (aircraft_phase is None and scenario.command_contract == "fixed_wing_external"
                           and contract == "fixed_wing_external")
        if native_scenario and (aircraft_phase == "fixed_wing" or legacy_fw_basis):
            # PX4 supplies its already transformed FW axis for tailsitters.
            # Absence remains unknown; never apply a second mount rotation.
            forward = _vector((pose_record or {}).get("native_fw_forward_ned"))
        course = command.get("course_rad")
        course_direction = None if course is None else (math.cos(course), math.sin(course), 0.)
        speed = _command_speed(command)
        requested_raw = tracker_record.get("requested_speed") if tracker_record else None
        try:
            requested_speed = None if requested_raw is None else float(requested_raw)
        except (TypeError, ValueError, OverflowError):
            requested_speed = None
        if requested_speed is not None and not math.isfinite(requested_speed):
            requested_speed = None
        source_raw = (
            (tracker_record or {}).get("speed_source")
            or metadata.get("speed_source")
            or metadata.get("speed_source_policy")
        )
        speed_source = str(source_raw) if source_raw else None
        age_raw = (tracker_record or {}).get("measurement_age_s", metadata.get("measurement_age_s"))
        try:
            measurement_age = None if age_raw is None else float(age_raw)
        except (TypeError, ValueError, OverflowError):
            measurement_age = None
        if measurement_age is not None and not math.isfinite(measurement_age):
            measurement_age = None
        sample = VisualizationSample(
            timestamp=timestamp,
            target_ned=target,
            target_timestamp_s=target_timestamp,
            vehicle_ned=vehicle,
            vehicle_quaternion=quaternion,
            vehicle_forward_ned=forward,
            command_ned=command_ned,
            course_direction_ned=course_direction,
            command_contract=contract,
            aircraft_phase=aircraft_phase,
            observed_eas_m_s=_optional_measurement((state_record or {}).get("observed_eas_m_s")),
            native_effective_eas_m_s=_optional_measurement((state_record or {}).get("native_effective_eas_m_s")),
            command=command,
            published=bool(publish_record and publish_record.get("publish_success") is True
                           and (not released or published_after_release)),
            command_expected=False if released else None,
            tracker_state=(
                metadata.get("guidance_state")
                or metadata.get("tracking_status")
                or tracker_output.get("tracking_state")
            ),
            continuity_state=state_record.get("state") if state_record else None,
            limiting_reason=(state_record or {}).get("limiting_reason") or metadata.get("limiting_reason") or reason,
            requested_speed=requested_speed,
            effective_speed=speed,
            speed_source=speed_source,
            measurement_age_s=measurement_age,
            stale=vehicle is None or (not released and tracker_record is None and publish_record is None),
            events=events,
        )
        result.append(sample)
    return result


def analyze_timeline(
    scenario: VisualizationScenario,
    samples: Iterable[VisualizationSample],
) -> dict[str, Any]:
    rows = list(samples)
    flags: list[dict[str, Any]] = []
    max_gap = 0.0
    target_ranges: list[float] = []
    target_speeds: list[float] = []
    previous = None
    previous_target: Optional[tuple[float, float, float]] = None
    previous_target_time: Optional[float] = None
    previous_yaw: Optional[float] = None
    previous_state: Optional[str] = None
    fresh_evidence_seen = False
    stale_after_fresh = 0
    for sample in rows:
        if previous is not None:
            max_gap = max(max_gap, sample.timestamp - previous)
            if sample.timestamp - previous > max(0.5, 2.0 / scenario.rate_hz):
                flags.append({"timestamp": sample.timestamp, "type": "command_or_pose_gap"})
        previous = sample.timestamp
        if sample.target_ned is not None and sample.vehicle_ned is not None:
            target_ranges.append(math.sqrt(sum(
                (target - vehicle) ** 2
                for target, vehicle in zip(sample.target_ned, sample.vehicle_ned)
            )))
        target_time = sample.target_timestamp_s if sample.target_timestamp_s is not None else sample.timestamp
        if sample.target_ned is not None and previous_target is not None and previous_target_time is not None:
            target_dt = target_time - previous_target_time
            # A held target record may appear at many publication timestamps.
            # Differentiate truth only when its own source timestamp advances.
            if target_dt > 0.:
                target_speeds.append(math.sqrt(sum(
                    ((target - prior) / target_dt) ** 2
                    for target, prior in zip(sample.target_ned, previous_target)
                )))
        if sample.target_ned is not None:
            previous_target = sample.target_ned
            previous_target_time = target_time
        else:
            previous_target = previous_target_time = None
        command = sample.command
        if "publication_after_authority_release" in sample.events:
            flags.append({"timestamp": sample.timestamp, "type": "publication_after_authority_release"})
        for field_name, limit_name in (
            ("vel_body_fwd", "velocity_forward"),
            ("vel_body_right", "velocity_right"),
            ("vel_body_down", "velocity_down"),
            ("yawspeed_deg_s", "rate_yaw"),
        ):
            limit = scenario.limits.get(limit_name)
            if limit is not None and abs(command.get(field_name, 0.0)) > limit + 1e-6:
                flags.append({
                    "timestamp": sample.timestamp,
                    "type": "constraint_exceeded",
                    "field": field_name,
                    "limit": limit,
                })
        if not scenario.altitude_control and (abs(command.get("vel_body_down", 0.0)) > 1e-6
                                             or abs(command.get("height_rate_m_s", 0.0)) > 1e-6):
            flags.append({"timestamp": sample.timestamp, "type": "altitude_disabled_vertical_command"})
        motion_states = {"hold", "target_lost", "reacquiring"}
        has_motion = any(abs(value) > 1e-6 for value in command.values())
        if (
            sample.requested_speed is not None
            and sample.effective_speed is not None
            and sample.tracker_state not in motion_states
            and sample.tracker_state != "target_caught"
            and not sample.limiting_reason
            and has_motion
        ):
            if abs(sample.requested_speed - sample.effective_speed) > max(0.1, abs(sample.requested_speed) * 0.25):
                flags.append({
                    "timestamp": sample.timestamp,
                    "type": "requested_effective_speed_difference",
                    "requested_speed": sample.requested_speed,
                    "effective_speed": sample.effective_speed,
                })
        yaw = command.get("yawspeed_deg_s")
        if yaw is not None and previous_yaw is not None:
            if abs(yaw) > 1e-6 and abs(previous_yaw) > 1e-6 and yaw * previous_yaw < 0:
                flags.append({"timestamp": sample.timestamp, "type": "yaw_sign_change"})
        previous_yaw = yaw if yaw is not None else previous_yaw
        if sample.tracker_state == "unreachable":
            flags.append({"timestamp": sample.timestamp, "type": "unsupported_guidance_state"})
        if previous_state == "yaw_first" and sample.tracker_state == "yaw_first" and abs(command.get("vel_body_fwd", 0.0)) > 1e-6:
            flags.append({"timestamp": sample.timestamp, "type": "yaw_first_translation_present"})
        previous_state = sample.tracker_state or previous_state
        if not sample.stale:
            fresh_evidence_seen = True
        elif fresh_evidence_seen:
            stale_after_fresh += 1
            flags.append({"timestamp": sample.timestamp, "type": "unknown_or_stale_evidence"})
    target_speed_summary = {
        "max": max(target_speeds) if target_speeds else None,
        "mean": sum(target_speeds) / len(target_speeds) if target_speeds else None,
        "samples": len(target_speeds),
    }
    if scenario.requested_speed is not None:
        speed_reference = scenario.requested_speed
        speed_reference_type = "requested_speed"
    elif scenario.follower_profile == "mc_velocity_chase":
        speed_reference = scenario.limits.get("velocity_forward")
        speed_reference_type = "forward_velocity_limit"
    elif scenario.follower_profile == "mc_velocity_position":
        forward = scenario.limits.get("velocity_forward")
        right = scenario.limits.get("velocity_right")
        speed_reference = math.hypot(forward, right) if forward is not None and right is not None else None
        speed_reference_type = "horizontal_velocity_limits"
    else:
        speed_reference = None
        speed_reference_type = None
    if (
        scenario.command_contract not in {"fixed_wing_external", "vtol_external"}
        and
        speed_reference is not None
        and target_speed_summary["max"] is not None
        and target_speed_summary["max"] > speed_reference * 1.05
    ):
        flags.append({
            "timestamp": rows[0].timestamp if rows else None,
            "type": "target_faster_than_speed_reference",
            "target_speed_max": target_speed_summary["max"],
            "speed_reference": speed_reference,
            "speed_reference_type": speed_reference_type,
        })
    return {
        "sample_count": len(rows),
        "time_start": rows[0].timestamp if rows else None,
        "time_end": rows[-1].timestamp if rows else None,
        "max_timestamp_gap_s": max_gap,
        "flags": flags,
        "state_counts": _counts(sample.tracker_state for sample in rows),
        "continuity_state_counts": _counts(sample.continuity_state for sample in rows),
        "phase_counts": _counts(sample.aircraft_phase for sample in rows),
        "command_contract_counts": _counts(sample.command_contract for sample in rows),
        "event_counts": _counts(event for sample in rows for event in sample.events),
        "pose_observed_samples": sum(sample.vehicle_ned is not None for sample in rows),
        "command_samples": sum(bool(sample.command) for sample in rows),
        "published_samples": sum(sample.published for sample in rows),
        "stale_after_fresh_samples": stale_after_fresh,
        "target_range_m": {
            "start": target_ranges[0] if target_ranges else None,
            "end": target_ranges[-1] if target_ranges else None,
            "minimum": min(target_ranges) if target_ranges else None,
            "samples": len(target_ranges),
        },
        "motion_summary": {
            "target_start_ned": next((sample.target_ned for sample in rows if sample.target_ned is not None), None),
            "target_end_ned": next((sample.target_ned for sample in reversed(rows) if sample.target_ned is not None), None),
            "px4_start_ned": next((sample.vehicle_ned for sample in rows if sample.vehicle_ned is not None), None),
            "px4_end_ned": next((sample.vehicle_ned for sample in reversed(rows) if sample.vehicle_ned is not None), None),
            "range_change_m": (
                target_ranges[-1] - target_ranges[0] if target_ranges else None
            ),
            "interpretation": (
                "PX4-observed pose is compared with independent target truth; command intent is not integrated into pose."
            ),
        },
        "target_speed_m_s": target_speed_summary,
        "speed_reference_m_s": speed_reference,
        "speed_reference_type": speed_reference_type,
        "claim_boundary": (
            "PX4 pose is observed truth; command vectors are intent and are never "
            "integrated into a predicted vehicle path"
        ),
    }


def _counts(values: Iterable[Optional[str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _optional_measurement(value):
    try:
        return finite_number(value, "measurement") if value is not None else None
    except ValueError:
        return None


def _frame_vectors(pose: Mapping[str, Any], command: Mapping[str, float]):
    """Keep physical attitude and heading-frame command intent distinct."""
    rotation = None
    raw = pose.get("vehicle_quaternion")
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            rotation = Quaternion(*raw)
        except (ValueError, TypeError):
            pass
    quaternion = None if rotation is None else (rotation.w, rotation.x, rotation.y, rotation.z)
    physical_forward = rotation.rotate(Vector3(1., 0., 0.)) if rotation is not None else None
    forward = None if physical_forward is None else (physical_forward.x, physical_forward.y, physical_forward.z)
    heading = None
    try:
        heading = finite_number(pose["vehicle_heading_rad"], "vehicle_heading") if "vehicle_heading_rad" in pose else (
            rotation.heading_rad if rotation is not None else None)
    except (ValueError, TypeError):
        pass
    names = ("vel_body_fwd", "vel_body_right", "vel_body_down")
    if heading is None or not all(name in command for name in names):
        return quaternion, forward, None
    try:
        world = heading_frame_to_ned(Vector3(*(command[name] for name in names)), heading)
    except (ValueError, TypeError):
        return quaternion, forward, None
    return quaternion, forward, (world.x, world.y, world.z)


def write_csv(path: Path, samples: Iterable[VisualizationSample]) -> None:
    fields = [
        "timestamp", "target_n", "target_e", "target_d", "target_timestamp_s", "vehicle_n", "vehicle_e", "vehicle_d",
        "command_n", "command_e", "command_d",
        "course_rad", "equivalent_airspeed_m_s", "height_rate_m_s", "altitude_amsl_m",
        "command_contract", "aircraft_phase", "observed_eas_m_s", "native_effective_eas_m_s",
        "vel_body_fwd", "vel_body_right", "vel_body_down", "rollspeed_deg_s", "pitchspeed_deg_s",
        "yawspeed_deg_s", "thrust", "published", "command_expected", "tracker_state", "continuity_state",
        "limiting_reason", "requested_speed", "effective_speed", "speed_source",
        "measurement_age_s", "stale", "events",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for sample in samples:
            row = {field: "" for field in fields}
            row["timestamp"] = sample.timestamp
            row["target_timestamp_s"] = sample.target_timestamp_s if sample.target_timestamp_s is not None else ""
            if sample.target_ned:
                row.update(dict(zip(("target_n", "target_e", "target_d"), sample.target_ned)))
            if sample.vehicle_ned:
                row.update(dict(zip(("vehicle_n", "vehicle_e", "vehicle_d"), sample.vehicle_ned)))
            if sample.command_ned:
                row.update(dict(zip(("command_n", "command_e", "command_d"), sample.command_ned)))
            row.update(sample.command)
            row.update({
                "published": sample.published,
                "command_expected": sample.command_expected if sample.command_expected is not None else "",
                "command_contract": sample.command_contract,
                "aircraft_phase": sample.aircraft_phase,
                "observed_eas_m_s": sample.observed_eas_m_s,
                "native_effective_eas_m_s": sample.native_effective_eas_m_s,
                "tracker_state": sample.tracker_state or "",
                "continuity_state": sample.continuity_state or "",
                "limiting_reason": sample.limiting_reason or "",
                "requested_speed": sample.requested_speed if sample.requested_speed is not None else "",
                "effective_speed": sample.effective_speed if sample.effective_speed is not None else "",
                "speed_source": sample.speed_source or "",
                "measurement_age_s": sample.measurement_age_s if sample.measurement_age_s is not None else "",
                "stale": sample.stale,
                "events": ";".join(sample.events),
            })
            writer.writerow(row)
