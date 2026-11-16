"""Application evidence requires measured closure and actual recovery."""

from copy import deepcopy

import pytest

from tools.run_stock_follow_application_sih import application_metrics


def evidence():
    return [dict(following_active=True, vehicle_ned=[position, 0., -40.], target_ned=[20., 0., -40.],
        elapsed_s=float(index), target_lost=index == 1, follower_input_reason=None,
        continuity={"authority_state": "COASTING" if index == 1 else "ACTIVE"})
        for index, position in enumerate((0., 3., 8.))]


def test_only_observed_pose_can_establish_closure_and_altitude_hold():
    rows = evidence()
    assert application_metrics(rows, altitude_control=False)["passed"]
    stationary = deepcopy(rows)
    for row in stationary:
        row["vehicle_ned"] = [0., 0., -40.]
        row["command_ned"] = [100., 0., 0.]
    assert not application_metrics(stationary, altitude_control=False)["passed"]


@pytest.mark.parametrize("fault", ["missing_pose", "no_recovery", "stale_input", "altitude_drift"])
def test_submission_success_cannot_hide_missing_or_failed_aircraft_evidence(fault):
    rows = evidence()
    if fault == "missing_pose":
        rows = []
    elif fault == "no_recovery":
        rows[-1]["continuity"]["authority_state"] = "COASTING"
    elif fault == "stale_input":
        rows[-1]["follower_input_reason"] = "guidance_input_stale"
    else:
        rows[-1]["vehicle_ned"][2] -= 10.
    assert not application_metrics(rows, altitude_control=False)["passed"]
