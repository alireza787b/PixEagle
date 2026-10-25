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
