"""Focused tests for the shared tracker command-freshness contract."""

import time

from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.tracker_runtime_status import (
    evaluate_tracker_command_freshness,
    evaluate_tracker_runtime_status,
)


def _output(**raw_overrides) -> TrackerOutput:
    raw_data = {
        "has_output": True,
        "usable_for_following": True,
        "data_is_stale": False,
    }
    raw_data.update(raw_overrides)
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        position_2d=(0.1, -0.2),
        raw_data=raw_data,
    )


def test_prediction_only_always_overrides_an_inconsistent_usable_claim():
    status = evaluate_tracker_command_freshness(
        _output(prediction_only=True, freshness_reason="prediction_only")
    )

    assert status["status"] == "stale_output"
    assert status["data_is_stale"] is True
    assert status["usable_for_following"] is False
    assert status["reason_code"] == "prediction_only"


def test_provider_boolean_strings_are_normalized_without_truthiness_errors():
    status = evaluate_tracker_runtime_status(
        _output(
            usable_for_following="true",
            data_is_stale="false",
            prediction_only="false",
        )
    )

    assert status["status"] == "active_usable"
    assert status["usable_for_following"] is True


def test_missing_explicit_usability_remains_fail_closed():
    output = _output()
    output.raw_data.pop("usable_for_following")

    status = evaluate_tracker_command_freshness(output)

    assert status["status"] == "not_usable"
    assert status["usable_for_following"] is False
    assert status["reason_code"] == "tracker_unusable_for_following"
