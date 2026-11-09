"""Tests for the unified SIH follower contract and evidence gate."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from classes.sih_visualization import VisualizationValidationError  # noqa: E402
from tools.run_sih_follower_validation import (  # noqa: E402
    normalize_harness_evidence,
    scenario_path,
    validate_px4_evidence,
    validate_scenario,
    write_failed_visualization,
)
from classes.sih_visualization import VisualizationScenario  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]


def test_all_registered_profiles_have_a_sih_scenario():
    profiles = {
        "mc_velocity_chase",
        "mc_velocity_ground",
        "mc_velocity_distance",
        "mc_velocity_position",
        "mc_attitude_rate",
        "fw_attitude_rate",
        "gm_velocity_chase",
        "gm_velocity_vector",
    }
    for profile in profiles:
        scenario = VisualizationScenario.from_yaml(scenario_path(profile))
        plan = validate_scenario(scenario)
        assert plan["profile"] == profile
        assert plan["evidence_provenance"] == "synthetic_fixture"


def test_harness_normalization_does_not_invent_target_truth(tmp_path):
    (tmp_path / "observations.jsonl").write_text(
        json.dumps({
            "timestamp": 1.0,
            "position_ned": [0.0, 0.0, -10.0],
            "body_to_ned_quaternion": [1.0, 0.0, 0.0, 0.0],
            "intent": {"vel_body_fwd": 1.0},
        }) + "\n",
        encoding="utf-8",
    )
    counts = normalize_harness_evidence(tmp_path)
    assert counts["pose"] == 1
    assert not (tmp_path / "trace" / "target_truth.jsonl").exists()


def test_harness_normalization_preserves_production_command_fields(tmp_path):
    (tmp_path / "tracker.jsonl").write_text(
        json.dumps({
            "timestamp": 1.0,
            "command_intent": {"fields": {"vel_body_fwd": 1.25, "vel_body_down": -0.5}},
        }) + "\n",
        encoding="utf-8",
    )
    counts = normalize_harness_evidence(tmp_path)
    assert counts["tracker"] == 1
    record = json.loads((tmp_path / "trace" / "tracker_command_trace.jsonl").read_text())
    assert record["command_intent"]["fields"] == {"vel_body_fwd": 1.25, "vel_body_down": -0.5}


def test_existing_canonical_capture_is_counted_and_never_replaced_by_legacy_alias(tmp_path):
    trace = tmp_path / "trace"
    trace.mkdir()
    canonical = trace / "offboard_publish_trace.jsonl"
    original = json.dumps({"record_type": "offboard_publish", "timestamp": 1., "publish_success": True}) + "\n"
    canonical.write_text(original)
    (tmp_path / "publish.jsonl").write_text(json.dumps({"timestamp": 2., "publish_status": {}}) + "\n")
    counts = normalize_harness_evidence(tmp_path)
    assert counts["published"] == 1
    assert canonical.read_text() == original


def test_px4_gate_rejects_command_only_evidence(tmp_path):
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/camera-chase-2d.yaml"
    )
    (tmp_path / "px4").mkdir()
    (tmp_path / "px4" / "pose_trace.jsonl").write_text(
        json.dumps({
            "timestamp": 1.0,
            "vehicle_ned": [0.0, 0.0, -10.0],
            "vehicle_quaternion": [1.0, 0.0, 0.0, 0.0],
        }) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "trace").mkdir()
    (tmp_path / "trace" / "offboard_publish_trace.jsonl").write_text(
        json.dumps({"record_type": "offboard_publish", "timestamp": 1.0, "publish_success": True}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(VisualizationValidationError, match="target_truth"):
        validate_px4_evidence(tmp_path, scenario)


def test_failed_run_keeps_visual_evidence_without_an_acceptance_claim(tmp_path):
    scenario = VisualizationScenario.from_yaml(scenario_path("mc_velocity_position"))
    (tmp_path / "px4").mkdir()
    pose = {"timestamp": 1., "vehicle_ned": [0., 0., -20.],
            "vehicle_quaternion": [1., 0., 0., 0.]}
    (tmp_path / "px4/pose_trace.jsonl").write_text(json.dumps(pose) + "\n")
    failure = {"passed": False, "checks": {"observed_stationary_drift": False},
               "metrics": {"maximum_horizontal_drift_m": 7.5}}
    (tmp_path / "result.json").write_text(json.dumps(failure))
    output = write_failed_visualization(tmp_path, scenario, RuntimeError("response failed"))
    html = (output / "index.html").read_text()
    assert 'id="qualification">Scenario failed' in html
    assert "Scenario passed" not in html
    assert (output / "summary.png").is_file()
    assert json.loads((output / "summary.json").read_text())["qualification_result"]["passed"] is False
    assert json.loads((tmp_path / "result.json").read_text()) == failure


def test_no_pose_cannot_be_rendered_as_observed_aircraft_motion(tmp_path):
    scenario = VisualizationScenario.from_yaml(scenario_path("mc_velocity_position"))
    assert write_failed_visualization(tmp_path, scenario, RuntimeError("no pose")) is None
    assert not (tmp_path / "visualization").exists()


def test_post_capture_acceptance_failure_also_renders_failed_evidence(tmp_path, monkeypatch):
    import tools.run_sih_follower_validation as entry
    output = tmp_path / "run"
    calls = []

    def capture(args, scenario):
        output.mkdir()
        (output / "scenario.yaml").write_bytes(entry.scenario_path(args.follower).read_bytes())

    def reject(*args):
        raise VisualizationValidationError("source gap")

    monkeypatch.setattr("sys.argv", ["runner", "--execute", "--follower", "mc_velocity_position",
                                     "--evidence-root", str(output)])
    monkeypatch.setattr(entry, "run_external", capture)
    monkeypatch.setattr(entry, "validate_px4_evidence", reject)
    monkeypatch.setattr(entry, "write_failed_visualization", lambda *args: calls.append(args))
    with pytest.raises(VisualizationValidationError, match="source gap"):
        entry.main()
    assert len(calls) == 1
    assert calls[0][0] == output
