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
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import yaml


class VisualizationValidationError(ValueError):
    """Evidence or scenario data cannot be safely visualized."""


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
    altitude_control: bool
    requested_speed: Optional[float]
    limits: dict[str, float]
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
        if int(raw.get("schema_version", 0)) != 1:
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
        rate_hz = float(raw.get("rate_hz", 20.0))
        if not math.isfinite(rate_hz) or not 0.0 < rate_hz <= 120.0:
            raise VisualizationValidationError("rate_hz must be finite and between 0 and 120")
        requested = follower.get("requested_speed")
        requested_speed = None if requested is None else float(requested)
        if requested_speed is not None and (not math.isfinite(requested_speed) or requested_speed < 0.0):
            raise VisualizationValidationError("follower.requested_speed must be finite and non-negative")
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
        return cls(
            schema_version=1,
            name=str(raw.get("name", path.stem)),
            rate_hz=rate_hz,
            frame=frame,
            mount_type=mount_type,
            follower_profile=profile,
            altitude_control=bool(follower.get("altitude_control", False)),
            requested_speed=requested_speed,
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
    vehicle_ned: Optional[tuple[float, float, float]] = None
    vehicle_quaternion: Optional[tuple[float, float, float, float]] = None
    command: dict[str, float] = field(default_factory=dict)
    published: bool = False
    tracker_state: Optional[str] = None
    continuity_state: Optional[str] = None
    limiting_reason: Optional[str] = None
    requested_speed: Optional[float] = None
    effective_speed: Optional[float] = None
    stale: bool = False
    events: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "target_ned": self.target_ned,
            "vehicle_ned": self.vehicle_ned,
            "vehicle_quaternion": self.vehicle_quaternion,
            "command": self.command,
            "published": self.published,
            "tracker_state": self.tracker_state,
            "continuity_state": self.continuity_state,
            "limiting_reason": self.limiting_reason,
            "requested_speed": self.requested_speed,
            "effective_speed": self.effective_speed,
            "stale": self.stale,
            "events": self.events,
        }


def _read_limits(raw: Mapping[str, Any]) -> dict[str, float]:
    limits: dict[str, float] = {}
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
        return {}
    result: dict[str, float] = {}
    for key in ("vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s"):
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
        for records in (tracker, published, pose, state)
        for record in records
    })
    result: list[VisualizationSample] = []
    for timestamp in timestamps:
        tracker_record = _nearest_fresh(tracker, timestamp, max_command_age_s)
        publish_record = _nearest_fresh(published, timestamp, max_command_age_s)
        pose_record = _nearest_fresh(pose, timestamp, max_pose_age_s)
        state_record = _nearest_fresh(state, timestamp, max_command_age_s)
        command = _command_fields(tracker_record or publish_record or {})
        tracker_output = (tracker_record or {}).get("tracker_output") or {}
        command_intent = (tracker_record or {}).get("command_intent") or {}
        metadata = tracker_output.get("metadata") if isinstance(tracker_output, Mapping) else {}
        if not isinstance(metadata, Mapping):
            metadata = {}
        events: list[str] = []
        reason = command_intent.get("reason") if isinstance(command_intent, Mapping) else None
        if isinstance(reason, str) and reason:
            events.append(reason)
        if publish_record and publish_record.get("publish_success") is False:
            events.append("publish_failed")
        target = _vector((tracker_record or {}).get("target_ned"))
        if target is None:
            target_record = _nearest_fresh(evidence.get("target", []), timestamp, max_command_age_s)
            target = _vector((target_record or {}).get("target_ned"))
        if target is None:
            target = scenario.target_at(timestamp)
        vehicle = _vector((pose_record or {}).get("vehicle_ned"))
        quaternion = _vector((pose_record or {}).get("vehicle_quaternion"))
        if pose_record and isinstance(pose_record.get("vehicle_quaternion"), (list, tuple)):
            values = tuple(float(item) for item in pose_record["vehicle_quaternion"])
            quaternion = values if len(values) == 4 and all(math.isfinite(item) for item in values) else None
        speed = _command_speed(command)
        requested_raw = tracker_record.get("requested_speed") if tracker_record else None
        try:
            requested_speed = None if requested_raw is None else float(requested_raw)
        except (TypeError, ValueError, OverflowError):
            requested_speed = None
        if requested_speed is not None and not math.isfinite(requested_speed):
            requested_speed = None
        sample = VisualizationSample(
            timestamp=timestamp,
            target_ned=target,
            vehicle_ned=vehicle,
            vehicle_quaternion=quaternion,
            command=command,
            published=bool(publish_record and publish_record.get("publish_success") is True),
            tracker_state=(
                metadata.get("guidance_state")
                or metadata.get("tracking_status")
                or tracker_output.get("tracking_state")
            ),
            continuity_state=state_record.get("state") if state_record else None,
            limiting_reason=metadata.get("limiting_reason") or reason,
            requested_speed=requested_speed,
            effective_speed=speed,
            stale=pose_record is None or (tracker_record is None and publish_record is None),
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
    previous = None
    previous_yaw: Optional[float] = None
    previous_state: Optional[str] = None
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
        command = sample.command
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
        if not scenario.altitude_control and abs(command.get("vel_body_down", 0.0)) > 1e-6:
            flags.append({"timestamp": sample.timestamp, "type": "altitude_disabled_vertical_command"})
        if sample.requested_speed is not None and sample.effective_speed is not None:
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
        if sample.stale:
            flags.append({"timestamp": sample.timestamp, "type": "unknown_or_stale_evidence"})
    return {
        "sample_count": len(rows),
        "time_start": rows[0].timestamp if rows else None,
        "time_end": rows[-1].timestamp if rows else None,
        "max_timestamp_gap_s": max_gap,
        "flags": flags,
        "state_counts": _counts(sample.tracker_state for sample in rows),
        "event_counts": _counts(event for sample in rows for event in sample.events),
        "pose_observed_samples": sum(sample.vehicle_ned is not None for sample in rows),
        "command_samples": sum(bool(sample.command) for sample in rows),
        "published_samples": sum(sample.published for sample in rows),
        "target_range_m": {
            "start": target_ranges[0] if target_ranges else None,
            "end": target_ranges[-1] if target_ranges else None,
            "minimum": min(target_ranges) if target_ranges else None,
            "samples": len(target_ranges),
        },
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


def write_csv(path: Path, samples: Iterable[VisualizationSample]) -> None:
    fields = [
        "timestamp", "target_n", "target_e", "target_d", "vehicle_n", "vehicle_e", "vehicle_d",
        "vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s", "published",
        "tracker_state", "continuity_state", "limiting_reason", "effective_speed", "stale", "events",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for sample in samples:
            row = {field: "" for field in fields}
            row["timestamp"] = sample.timestamp
            if sample.target_ned:
                row.update(dict(zip(("target_n", "target_e", "target_d"), sample.target_ned)))
            if sample.vehicle_ned:
                row.update(dict(zip(("vehicle_n", "vehicle_e", "vehicle_d"), sample.vehicle_ned)))
            row.update(sample.command)
            row.update({
                "published": sample.published,
                "tracker_state": sample.tracker_state or "",
                "continuity_state": sample.continuity_state or "",
                "limiting_reason": sample.limiting_reason or "",
                "effective_speed": sample.effective_speed if sample.effective_speed is not None else "",
                "stale": sample.stale,
                "events": ";".join(sample.events),
            })
            writer.writerow(row)
