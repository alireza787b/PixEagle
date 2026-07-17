"""Normalized tracker/follower trace artifact helpers.

These helpers serialize tracker output and follower command intent evidence
into JSONL records that can be attached to SITL or deterministic tracker smoke
runs. They do not send commands or mutate runtime state.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import time
from typing import Any, Iterable

from classes.command_intent import CommandIntent
from classes.tracker_output import TrackerOutput


TRACE_SCHEMA_VERSION = 1


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _first_mapping_value(
    *mappings: dict[str, Any],
    key: str,
    default: Any = None,
) -> Any:
    for mapping in mappings:
        if isinstance(mapping, dict) and key in mapping:
            return mapping[key]
    return default


def tracker_output_summary(tracker_output: TrackerOutput) -> dict[str, Any]:
    """Return stable, bounded tracker fields for trace artifacts."""
    raw_data = dict(tracker_output.raw_data or {})
    metadata = dict(tracker_output.metadata or {})
    has_output = _first_mapping_value(
        raw_data,
        metadata,
        key="has_output",
        default=bool(
            tracker_output.has_position_data()
            or tracker_output.bbox
            or tracker_output.targets
        ),
    )
    return {
        "tracker_id": tracker_output.tracker_id,
        "data_type": tracker_output.data_type.value,
        "timestamp": tracker_output.timestamp,
        "tracking_active": bool(tracker_output.tracking_active),
        "has_output": bool(has_output),
        "usable_for_following": _first_mapping_value(
            raw_data,
            metadata,
            key="usable_for_following",
        ),
        "data_is_stale": _first_mapping_value(
            raw_data,
            metadata,
            key="data_is_stale",
        ),
        "freshness_reason": _first_mapping_value(
            raw_data,
            metadata,
            key="freshness_reason",
        ),
        "position_2d": _jsonable(tracker_output.position_2d),
        "bbox": _jsonable(tracker_output.bbox),
        "normalized_bbox": _jsonable(tracker_output.normalized_bbox),
        "geometry_type": tracker_output.geometry_type,
        "oriented_bbox": _jsonable(tracker_output.oriented_bbox),
        "polygon": _jsonable(tracker_output.polygon),
        "normalized_polygon": _jsonable(tracker_output.normalized_polygon),
        "angular": _jsonable(tracker_output.angular),
        "velocity": _jsonable(tracker_output.velocity),
        "acceleration": _jsonable(tracker_output.acceleration),
        "confidence": tracker_output.confidence,
        "target_id": tracker_output.target_id,
        "targets": _jsonable(tracker_output.targets),
        "quality_metrics": _jsonable(tracker_output.quality_metrics),
    }


def command_intent_summary(intent: CommandIntent | None) -> dict[str, Any] | None:
    """Return stable command intent fields for trace artifacts."""
    if intent is None:
        return None
    return {
        "profile_name": intent.profile_name,
        "control_type": intent.control_type,
        "source": intent.source,
        "reason": intent.reason,
        "created_at_utc": intent.created_at_utc,
        "fields": _jsonable(intent.fields),
    }


def build_tracker_command_trace_record(
    *,
    frame_index: int,
    tracker_output: TrackerOutput,
    command_intent: CommandIntent | None,
    dispatch_accepted: bool,
    source: str,
    frame_status: dict[str, Any] | None = None,
    offboard_commander: dict[str, Any] | None = None,
    timestamp: float | None = None,
) -> dict[str, Any]:
    """Build one normalized tracker-to-command trace record."""
    record_time = float(timestamp if timestamp is not None else time.time())
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "record_type": "tracker_command",
        "timestamp": record_time,
        "frame_index": int(frame_index),
        "source": source,
        "tracker_output": tracker_output_summary(tracker_output),
        "command_intent": command_intent_summary(command_intent),
        "dispatch_accepted": bool(dispatch_accepted),
        "frame_status": _jsonable(frame_status or {}),
        "offboard_commander": _jsonable(offboard_commander or {}),
        "claim_boundary": (
            "Tracker/follower trace evidence only; this record does not prove PX4, "
            "SITL, HIL, field, or real-aircraft behavior."
        ),
    }


def build_offboard_publish_trace_record(
    *,
    sequence: int,
    command_intent: CommandIntent | None,
    publish_status: dict[str, Any] | None,
    source: str,
    timestamp: float | None = None,
) -> dict[str, Any]:
    """Build one normalized record from an actual commander publish result.

    ``publish_status`` must describe the completed MAVSDK publication attempt.
    Intent acceptance or a pre-publication commander snapshot is not publication
    evidence. Failed attempts may be recorded for diagnostics, but strict SITL
    validation accepts only records whose derived ``publish_success`` is ``True``.
    """
    record_time = float(timestamp if timestamp is not None else time.time())
    status = dict(publish_status or {})
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "record_type": "offboard_publish",
        "timestamp": record_time,
        "sequence": int(sequence),
        "source": source,
        "command_intent": command_intent_summary(command_intent),
        "publish_status": _jsonable(status),
        "publish_success": status.get("last_publish_success"),
        "claim_boundary": (
            "Offboard publication trace evidence only; this record does not prove "
            "PX4, SITL, HIL, field, or real-aircraft behavior."
        ),
    }


def write_trace_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    """Write normalized trace records as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            _jsonable(record),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        for record in records
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def append_trace_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append one normalized trace record as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        _jsonable(record),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


class TrackerTraceRecorder:
    """Append-only recorder for validation-gated tracker/offboard traces."""

    def __init__(
        self,
        *,
        tracker_command_trace_path: Path,
        offboard_publish_trace_path: Path,
        source: str,
    ) -> None:
        self.tracker_command_trace_path = tracker_command_trace_path
        self.offboard_publish_trace_path = offboard_publish_trace_path
        self.source = source

    def record_tracker_command(
        self,
        *,
        frame_index: int,
        tracker_output: TrackerOutput,
        command_intent: CommandIntent | None,
        dispatch_accepted: bool,
        frame_status: dict[str, Any] | None = None,
        offboard_commander: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = build_tracker_command_trace_record(
            frame_index=frame_index,
            tracker_output=tracker_output,
            command_intent=command_intent,
            dispatch_accepted=dispatch_accepted,
            source=self.source,
            frame_status=frame_status,
            offboard_commander=offboard_commander,
        )
        append_trace_jsonl(self.tracker_command_trace_path, record)
        return record

    def record_offboard_publish(
        self,
        *,
        sequence: int,
        command_intent: CommandIntent | None,
        publish_status: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Record a completed OffboardCommander publication result."""
        record = build_offboard_publish_trace_record(
            sequence=sequence,
            command_intent=command_intent,
            publish_status=publish_status,
            source=self.source,
        )
        append_trace_jsonl(self.offboard_publish_trace_path, record)
        return record
