"""Shared tracker runtime status evaluation.

This module keeps follower-facing tracker readiness semantics in one place.
Raw tracker metadata can be diagnostic, stale, or provider-specific; canonical
`usable_for_following` must remain fail-closed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


TRACKER_RUNTIME_CLAIM_BOUNDARY = (
    "PixEagle local tracker runtime status only; not PX4, SITL, HIL, "
    "field, or follower-response proof."
)

TRACKER_RUNTIME_STATUSES = {
    "no_output",
    "visible_output",
    "active_usable",
    "not_usable",
    "stale_output",
    "unavailable",
}


_UNSET = object()
_TRUE_TOKENS = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "active",
    "tracking",
    "tracking_active",
    "receiving",
    "usable",
}
_FALSE_TOKENS = {
    "0",
    "false",
    "no",
    "n",
    "off",
    "inactive",
    "disabled",
    "lost",
    "target_lost",
    "stale",
    "none",
    "null",
    "unusable",
    "not_usable",
}


def parse_bool_like(value: Any, default: bool = False) -> bool:
    """Parse booleans from tracker/provider metadata without bool('false')."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
        return default
    return bool(value)


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_defined(*values: Any) -> Any:
    for value in values:
        if value is not _UNSET and value is not None:
            return value
    return None


def _attr(obj: Any, name: str) -> Any:
    return getattr(obj, name, _UNSET)


def _enum_value(value: Any) -> Optional[str]:
    if value is None or value is _UNSET:
        return None
    enum_value = getattr(value, "value", None)
    return str(enum_value if enum_value is not None else value)


def _optional_str(value: Any) -> Optional[str]:
    if value is None or value is _UNSET:
        return None
    return str(value)


def _has_non_empty_value(value: Any) -> bool:
    if value is None or value is _UNSET:
        return False
    if isinstance(value, (str, bytes)):
        return len(value) > 0
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _output_field_names(tracker_output: Any) -> List[str]:
    fields = [
        "position_2d",
        "position_3d",
        "angular",
        "bbox",
        "normalized_bbox",
        "oriented_bbox",
        "polygon",
        "normalized_polygon",
        "velocity",
        "acceleration",
        "targets",
    ]
    return [
        field
        for field in fields
        if _has_non_empty_value(getattr(tracker_output, field, None))
    ]


def _selected_target_id(target_id: Any, targets: Any) -> Any:
    if target_id is not None and target_id is not _UNSET:
        return target_id
    if not isinstance(targets, list):
        return None
    for target in targets:
        if not isinstance(target, dict):
            continue
        if parse_bool_like(target.get("is_selected"), default=False):
            return _first_defined(
                target.get("target_id"),
                target.get("id"),
                target.get("track_id"),
            )
    return None


def tracker_runtime_unavailable_status(
    reason: str,
    *,
    timestamp: Optional[float] = None,
    configured_tracker: Optional[str] = None,
    tracker_type: Optional[str] = None,
    smart_mode_active: bool = False,
    following_active: bool = False,
) -> Dict[str, Any]:
    """Build a typed unavailable status when tracker output cannot be queried."""
    return {
        "schema_version": 1,
        "source": "tracker_runtime",
        "status": "unavailable",
        "consumer_guidance": "unavailable",
        "has_output": False,
        "active_tracking": False,
        "tracking_active": False,
        "usable_for_following": False,
        "data_is_stale": False,
        "reason": reason,
        "configured_tracker": configured_tracker,
        "active_tracker": None,
        "tracker_id": None,
        "tracker_type": tracker_type,
        "data_type": None,
        "provider": None,
        "protocol": None,
        "connection_status": None,
        "tracking_status": None,
        "target_count": 0,
        "selected_target_id": None,
        "output_fields": [],
        "smart_mode_active": smart_mode_active,
        "following_active": following_active,
        "claim_boundary": TRACKER_RUNTIME_CLAIM_BOUNDARY,
        "timestamp": timestamp or time.time(),
    }


def evaluate_tracker_runtime_status(
    tracker_output: Any,
    *,
    timestamp: Optional[float] = None,
    configured_tracker: Optional[str] = None,
    tracker_type: Optional[str] = None,
    smart_mode_active: bool = False,
    following_active: bool = False,
) -> Dict[str, Any]:
    """
    Evaluate tracker output visibility and follower usability.

    `active_tracking` reports the tracker contract's current target-active
    state. `usable_for_following` is stricter: it requires active tracking,
    present output, explicit usability, and non-stale data.
    """
    now = timestamp or time.time()
    if tracker_output is None:
        return {
            "schema_version": 1,
            "source": "tracker_runtime",
            "status": "no_output",
            "consumer_guidance": "no_output",
            "has_output": False,
            "active_tracking": False,
            "tracking_active": False,
            "usable_for_following": False,
            "data_is_stale": False,
            "reason": "No tracker output available.",
            "configured_tracker": configured_tracker,
            "active_tracker": None,
            "tracker_id": None,
            "tracker_type": tracker_type,
            "data_type": None,
            "provider": None,
            "protocol": None,
            "connection_status": None,
            "tracking_status": None,
            "target_count": 0,
            "selected_target_id": None,
            "output_fields": [],
            "smart_mode_active": smart_mode_active,
            "following_active": following_active,
            "claim_boundary": TRACKER_RUNTIME_CLAIM_BOUNDARY,
            "timestamp": now,
        }

    raw_data = _dict_or_empty(getattr(tracker_output, "raw_data", None))
    metadata = _dict_or_empty(getattr(tracker_output, "metadata", None))
    output_fields = _output_field_names(tracker_output)
    targets = getattr(tracker_output, "targets", None)

    active_value = _first_defined(
        _attr(tracker_output, "tracking_active"),
        raw_data.get("tracking_active"),
        raw_data.get("gimbal_tracking_active"),
        metadata.get("tracking_active"),
    )
    active_tracking = parse_bool_like(active_value, default=False)

    explicit_has_output = _first_defined(
        raw_data.get("has_output"),
        metadata.get("has_output"),
    )
    if explicit_has_output is None:
        has_output = bool(output_fields)
    else:
        has_output = parse_bool_like(explicit_has_output, default=False)

    prediction_only = parse_bool_like(
        _first_defined(
            raw_data.get("prediction_only"),
            metadata.get("prediction_only"),
        ),
        default=False,
    )
    data_is_stale = prediction_only or parse_bool_like(
        _first_defined(
            raw_data.get("data_is_stale"),
            metadata.get("data_is_stale"),
            raw_data.get("stale"),
            raw_data.get("is_stale"),
            metadata.get("stale"),
        ),
        default=False,
    )

    explicit_usable = _first_defined(
        raw_data.get("usable_for_following"),
        metadata.get("usable_for_following"),
    )
    source_marks_usable = (
        parse_bool_like(explicit_usable, default=False)
        if explicit_usable is not None
        else False
    )

    usable_for_following = bool(
        source_marks_usable and active_tracking and has_output and not data_is_stale
    )

    if not has_output:
        status = "no_output"
        consumer_guidance = "no_output"
        reason = "No tracker output available."
    elif data_is_stale:
        status = "stale_output"
        consumer_guidance = "stale"
        reason = str(
            _first_defined(
                raw_data.get("freshness_reason"),
                metadata.get("freshness_reason"),
                "prediction_only" if prediction_only else None,
                "Tracker output is stale and not usable for following.",
            )
        )
    elif usable_for_following:
        status = "active_usable"
        consumer_guidance = "usable"
        reason = "Tracker output is active and usable for follower control."
    elif active_tracking:
        status = "not_usable"
        consumer_guidance = "not_usable"
        reason = str(
            _first_defined(
                raw_data.get("freshness_reason"),
                metadata.get("freshness_reason"),
                (
                    "Tracker output is active but not explicitly marked "
                    "usable for following."
                ),
            )
        )
    else:
        status = "visible_output"
        consumer_guidance = "diagnostic_only"
        reason = (
            "Tracker output is visible, but active target tracking is not confirmed."
        )

    tracker_id = getattr(tracker_output, "tracker_id", None)
    data_type = _enum_value(getattr(tracker_output, "data_type", None))
    target_count = len(targets) if isinstance(targets, list) else 0

    return {
        "schema_version": 1,
        "source": "tracker_runtime",
        "status": status,
        "consumer_guidance": consumer_guidance,
        "has_output": has_output,
        "active_tracking": active_tracking,
        "tracking_active": active_tracking,
        "usable_for_following": usable_for_following,
        "data_is_stale": data_is_stale,
        "reason": reason,
        "configured_tracker": configured_tracker,
        "active_tracker": tracker_id,
        "tracker_id": tracker_id,
        "tracker_type": _optional_str(tracker_type or raw_data.get("tracker_type")),
        "data_type": data_type,
        "provider": _optional_str(
            _first_defined(raw_data.get("provider"), metadata.get("provider"))
        ),
        "protocol": _optional_str(
            _first_defined(raw_data.get("protocol"), metadata.get("protocol"))
        ),
        "connection_status": _optional_str(
            _first_defined(
                raw_data.get("connection_status"),
                metadata.get("connection_status"),
            )
        ),
        "tracking_status": _optional_str(
            _first_defined(
                raw_data.get("tracking_status"),
                metadata.get("tracking_status"),
            )
        ),
        "target_count": target_count,
        "selected_target_id": _selected_target_id(
            getattr(tracker_output, "target_id", None),
            targets,
        ),
        "output_fields": output_fields,
        "smart_mode_active": smart_mode_active,
        "following_active": following_active,
        "claim_boundary": TRACKER_RUNTIME_CLAIM_BOUNDARY,
        "timestamp": now,
    }


def evaluate_tracker_command_freshness(tracker_output: Any) -> Dict[str, Any]:
    """Return the canonical follower-command assessment for one tracker output.

    Tracker implementations own measurement timing and provider-specific loss
    policy. This function only normalizes their explicit output contract, so a
    camera tracker, an AI tracker, and an external gimbal cannot drift into
    separate controller-side boolean rules.
    """
    status = evaluate_tracker_runtime_status(tracker_output)
    reason_code: Optional[str] = None

    if not status["usable_for_following"]:
        raw_data = _dict_or_empty(getattr(tracker_output, "raw_data", None))
        metadata = _dict_or_empty(getattr(tracker_output, "metadata", None))
        reason_code = _optional_str(
            _first_defined(
                raw_data.get("freshness_reason"),
                metadata.get("freshness_reason"),
            )
        )
        if not reason_code:
            explicit_usable = _first_defined(
                raw_data.get("usable_for_following"),
                metadata.get("usable_for_following"),
            )
            explicit_stale = _first_defined(
                raw_data.get("data_is_stale"),
                metadata.get("data_is_stale"),
                raw_data.get("stale"),
                raw_data.get("is_stale"),
                metadata.get("stale"),
            )
            explicit_prediction = _first_defined(
                raw_data.get("prediction_only"),
                metadata.get("prediction_only"),
            )
            if explicit_usable is not None and not parse_bool_like(
                explicit_usable,
                default=False,
            ):
                reason_code = "tracker_unusable_for_following"
            elif parse_bool_like(explicit_stale, default=False):
                reason_code = "tracker_data_stale"
            elif parse_bool_like(explicit_prediction, default=False):
                reason_code = "prediction_only"

        if not reason_code:
            reason_code = {
                "no_output": "tracker_output_missing",
                "stale_output": "tracker_data_stale",
                "not_usable": "tracker_unusable_for_following",
                "visible_output": "tracking_inactive",
                "unavailable": "tracker_output_unavailable",
            }.get(status["status"], "tracker_unusable_for_following")

    return {**status, "reason_code": reason_code}
