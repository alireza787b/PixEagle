"""Deterministic tests for the read-only SIH visualization pipeline."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from classes.sih_visualization import (  # noqa: E402
    VisualizationValidationError,
    VisualizationSample,
    VisualizationScenario,
    analyze_timeline,
    build_timeline,
    load_evidence,
    read_jsonl,
)
from tools.sih_visualizer import build_html, poll_live_pose  # noqa: E402
from tools.sih_visualization_catchup_fixture import write_catchup_evidence  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]


def test_scenarios_validate_and_interpolate_target_truth():
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/gimbal-vector-vertical.yaml"
    )
    assert scenario.mount_type == "VERTICAL"
    assert scenario.target_at(1.5) == pytest.approx((19.0, 4.0, -6.5))
    assert scenario.target_at(-1.0) is None


def test_combined_scenario_declares_airborne_initial_pose():
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/gimbal-vector-combined-catchup.yaml"
    )
    assert scenario.initial_vehicle_ned == pytest.approx((0.0, 0.0, -20.0))
    assert scenario.lateral_guidance_mode == "coordinated_turn"


@pytest.mark.parametrize(
    "filename",
    [
        "gimbal-vector-horizontal.yaml",
        "camera-chase-baseline.yaml",
        "gimbal-vector-catchup-horizontal.yaml",
        "gimbal-vector-catchup-vertical.yaml",
        "gimbal-vector-combined-catchup.yaml",
        "camera-chase-2d.yaml",
        "camera-position-2d.yaml",
        "camera-chase-2d.yaml",
        "camera-position-2d.yaml",
    ],
)
def test_all_initial_scenarios_validate(filename):
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios" / filename)
    assert scenario.target_waypoints


def test_scenario_rejects_unordered_waypoints(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """schema_version: 1
name: bad
frame: local_ned
mount_type: HORIZONTAL
follower: {profile: mc_velocity_chase}
target:
  waypoints:
    - {time_s: 1, position_ned: [0, 0, 0]}
    - {time_s: 0, position_ned: [1, 0, 0]}
""",
        encoding="utf-8",
    )
    with pytest.raises(VisualizationValidationError, match="ordered"):
        VisualizationScenario.from_yaml(path)


def test_read_jsonl_rejects_out_of_order_timestamps(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text(
        json.dumps({"timestamp": 2}) + "\n" + json.dumps({"timestamp": 1}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(VisualizationValidationError, match="out of order"):
        read_jsonl(path)


def test_build_timeline_keeps_pose_gaps_unknown_and_never_predicts_pose(tmp_path):
    root = tmp_path / "evidence"
    (root / "px4").mkdir(parents=True)
    (root / "trace").mkdir(parents=True)
    (root / "px4" / "pose_trace.jsonl").write_text(
        json.dumps({"timestamp": 0.0, "vehicle_ned": [1, 2, 3], "vehicle_quaternion": [1, 0, 0, 0]})
        + "\n",
        encoding="utf-8",
    )
    tracker = {
        "record_type": "tracker_command",
        "timestamp": 1.0,
        "tracker_output": {"tracking_active": True, "metadata": {"guidance_state": "vertical"}},
        "command_intent": {"reason": "test", "fields": {"vel_body_fwd": 1, "vel_body_down": 2}},
    }
    (root / "trace" / "tracker_command_trace.jsonl").write_text(json.dumps(tracker) + "\n", encoding="utf-8")
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/gimbal-vector-horizontal.yaml"
    )
    samples = build_timeline(scenario, load_evidence(root), max_pose_age_s=0.2)
    assert samples[-1].vehicle_ned is None
    assert samples[-1].stale is True
    assert samples[-1].target_ned is not None
    assert samples[-1].command["vel_body_down"] == 2


def test_analysis_flags_altitude_disabled_and_constraint_violation():
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/camera-chase-baseline.yaml"
    )
    sample = VisualizationSample(
        timestamp=1.0,
        command={"vel_body_fwd": 3.0, "vel_body_down": 1.0},
        effective_speed=3.16,
        stale=False,
    )
    summary = analyze_timeline(scenario, [sample])
    kinds = {flag["type"] for flag in summary["flags"]}
    assert "constraint_exceeded" in kinds
    assert "altitude_disabled_vertical_command" in kinds


def test_analysis_reports_observed_target_range():
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/gimbal-vector-horizontal.yaml"
    )
    summary = analyze_timeline(
        scenario,
        [
            VisualizationSample(timestamp=0.0, target_ned=(10.0, 0.0, 0.0), vehicle_ned=(0.0, 0.0, 0.0)),
            VisualizationSample(timestamp=1.0, target_ned=(5.0, 0.0, 0.0), vehicle_ned=(4.0, 0.0, 0.0)),
        ],
    )
    assert summary["target_range_m"] == {
        "start": pytest.approx(10.0),
        "end": pytest.approx(1.0),
        "minimum": pytest.approx(1.0),
        "samples": 2,
    }


@pytest.mark.parametrize(
    "filename",
    [
        "gimbal-vector-catchup-horizontal.yaml",
        "gimbal-vector-catchup-vertical.yaml",
        "gimbal-vector-combined-catchup.yaml",
    ],
)
def test_catchup_fixture_closes_observed_range(tmp_path, filename):
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios" / filename
    )
    evidence_root = tmp_path / filename.removesuffix(".yaml")
    fixture = write_catchup_evidence(scenario, evidence_root)
    summary = analyze_timeline(scenario, build_timeline(scenario, load_evidence(evidence_root)))
    assert fixture["requested_speed_m_s"] > fixture["target_speed_m_s"]
    assert fixture["range_end_m"] == pytest.approx(0.0)
    assert summary["target_range_m"]["end"] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("filename", "profile", "lateral_mode"),
    [
        ("camera-chase-2d.yaml", "mc_velocity_chase", "coordinated_turn"),
        ("camera-position-2d.yaml", "mc_velocity_position", "sideslip"),
    ],
)
def test_2d_followers_keep_horizontal_semantics_and_fault_states(
    tmp_path, filename, profile, lateral_mode
):
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios" / filename)
    assert scenario.follower_profile == profile
    assert scenario.lateral_guidance_mode == lateral_mode
    assert scenario.altitude_control is False
    evidence_root = tmp_path / filename.removesuffix(".yaml")
    write_catchup_evidence(scenario, evidence_root)
    samples = build_timeline(scenario, load_evidence(evidence_root))
    assert any(sample.tracker_state in {"target_lost", "reacquiring"} for sample in samples)
    assert all(abs(sample.command.get("vel_body_down", 0.0)) <= 1e-9 for sample in samples)


def test_evidence_loader_uses_existing_trace_contracts(tmp_path):
    root = tmp_path / "evidence"
    (root / "trace").mkdir(parents=True)
    (root / "trace" / "offboard_publish_trace.jsonl").write_text(
        json.dumps({"record_type": "offboard_publish", "timestamp": 1, "publish_success": True}) + "\n",
        encoding="utf-8",
    )
    loaded = load_evidence(root)
    assert loaded["published"][0]["publish_success"] is True


def test_live_adapter_uses_get_only_and_writes_pose(monkeypatch, tmp_path):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        calls.append((request.method, request.headers.get("Authorization"), timeout))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "tools.sih_visualizer.pose_from_mavlink2rest",
        lambda snapshot, system_id: ((1.0, 2.0, 3.0), (1.0, 0.0, 0.0, 0.0)),
    )
    output = tmp_path / "pose.jsonl"
    poll_live_pose("http://127.0.0.1:8080/v1/mavlink", 1, 0.01, "token", output, 0.02)
    record = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    assert calls[0][0] == "GET"
    assert calls[0][1] == "Bearer token"
    assert record["vehicle_ned"] == [1.0, 2.0, 3.0]


def test_html_report_contains_read_only_claim_labels():
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/gimbal-vector-horizontal.yaml"
    )
    html = build_html(scenario, [VisualizationSample(timestamp=0.0)], {"flags": []})
    assert "Read-only evidence viewer" in html
    assert "PX4 pose" in html
    assert "command intent" in html
    assert "targetHistory" in html
    assert "3D orbit" in html
    assert "history opacity" not in html
    assert "Follower:" in html
