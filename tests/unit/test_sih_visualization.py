"""Deterministic tests for the read-only SIH visualization pipeline."""

import json
import csv
import math
import os
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from classes.sih_visualization import (  # noqa: E402
    VisualizationValidationError,
    VisualizationSample,
    VisualizationScenario,
    analyze_timeline,
    build_timeline,
    load_evidence,
    read_jsonl,
    write_csv,
)
from classes.follower_types import FollowerType  # noqa: E402
from tools.sih_visualization_gallery import build_gallery  # noqa: E402
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


def test_scenario_declares_distinct_input_and_command_contracts():
    camera = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/camera-chase-2d.yaml"
    )
    gimbal = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/gimbal-vector-horizontal.yaml"
    )
    assert camera.input_contract == "image_position_2d"
    assert camera.follower_purpose == "2D image-tracking forward pursuit"
    assert gimbal.input_contract == "gimbal_angles"
    assert camera.command_contract == "velocity_body_offboard"
    assert gimbal.command_contract == "gimbal_velocity_body"


def test_follower_contract_gallery_contains_all_registered_profiles():
    catalog = yaml.safe_load(
        (ROOT / "tools/sih_visualization_scenarios/follower-contracts.yaml").read_text(encoding="utf-8")
    )
    gallery = build_gallery(catalog, ROOT)
    assert {item["profile"] for item in catalog["followers"]} == {item.value for item in FollowerType}
    assert "mc_velocity_ground" in gallery
    assert "gimbal angles" in gallery
    assert "Read-only input-to-command guide" in gallery
    assert "Follower evidence" in gallery
    assert "Observed PX4 SIH" in gallery


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
        "camera-ground-2d.yaml",
        "camera-distance-2d.yaml",
        "mc-attitude-rate.yaml",
        "fw-attitude-rate.yaml",
    ],
)
def test_all_initial_scenarios_validate(filename):
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios" / filename)
    assert scenario.target_waypoints


@pytest.mark.parametrize(
    ("filename", "airframe", "input_contract", "command_contract"),
    [
        ("camera-ground-2d.yaml", "multicopter", "image_position_2d", "velocity_body_offboard"),
        ("camera-distance-2d.yaml", "multicopter", "image_position_2d", "velocity_body_offboard"),
        ("mc-attitude-rate.yaml", "multicopter", "attitude_rate_image_position", "attitude_rate"),
        ("fw-attitude-rate.yaml", "fixed_wing", "attitude_rate_image_position", "attitude_rate"),
    ],
)
def test_new_follower_scenarios_declare_airframe_and_command_contract(
    filename, airframe, input_contract, command_contract
):
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios" / filename)
    assert (scenario.airframe, scenario.input_contract, scenario.command_contract) == (
        airframe, input_contract, command_contract
    )
    if airframe == "fixed_wing":
        assert scenario.speed_source_policy == "auto"


def test_attitude_rate_report_preserves_rate_and_thrust_fields(tmp_path):
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/mc-attitude-rate.yaml"
    )
    evidence_root = tmp_path / "mc-attitude-rate"
    write_catchup_evidence(scenario, evidence_root)
    samples = build_timeline(scenario, load_evidence(evidence_root))
    assert any("rollspeed_deg_s" in sample.command for sample in samples)
    assert any("pitchspeed_deg_s" in sample.command for sample in samples)
    assert any("thrust" in sample.command for sample in samples)


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
    assert samples[-1].command_ned is None
    assert samples[-1].vehicle_forward_ned is None


@pytest.mark.parametrize("quaternion,forward,command_ned", [
    ([math.sqrt(.5), 0., 0., math.sqrt(.5)], (0., 1., 0.), (0., 2., 0.)),
    ([math.cos(math.pi / 8), 0., math.sin(math.pi / 8), 0.],
     (math.sqrt(.5), 0., -math.sqrt(.5)), (2., 0., 0.)),
])
def test_report_distinguishes_physical_body_heading_from_mavlink_velocity_frame(
        quaternion, forward, command_ned, tmp_path):
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios/gimbal-vector-horizontal.yaml")
    evidence = {
        "pose": [{"timestamp": 0., "vehicle_ned": [0., 0., -20.], "vehicle_quaternion": quaternion}],
        "tracker": [{"timestamp": 0., "command_intent": {"fields": {
            "vel_body_fwd": 2., "vel_body_right": 0., "vel_body_down": 0., "yawspeed_deg_s": 0.,
        }}}],
    }
    samples = build_timeline(scenario, evidence)
    assert samples[0].vehicle_forward_ned == pytest.approx(forward, abs=1e-12)
    assert samples[0].command_ned == pytest.approx(command_ned, abs=1e-12)
    assert samples[0].vehicle_ned == (0., 0., -20.)
    output = tmp_path / "trace.csv"
    write_csv(output, samples)
    with output.open() as stream:
        row = next(csv.DictReader(stream))
    assert tuple(float(row[key]) for key in ("command_n", "command_e", "command_d")) == pytest.approx(command_ned, abs=1e-12)


@pytest.mark.parametrize("heading,expected", [(None, None), (math.pi / 2, (0., 2., 0.))])
def test_vertical_body_axis_cannot_invent_heading_for_the_command_arrow(heading, expected):
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios/gimbal-vector-horizontal.yaml")
    pose = {"timestamp": 0., "vehicle_ned": [0., 0., -20.],
            "vehicle_quaternion": [math.sqrt(.5), 0., math.sqrt(.5), 0.]}
    if heading is not None:
        pose["vehicle_heading_rad"] = heading
    samples = build_timeline(scenario, {"pose": [pose], "tracker": [{
        "timestamp": 0., "command_intent": {"fields": {
            "vel_body_fwd": 2., "vel_body_right": 0., "vel_body_down": 0.,
        }},
    }]})
    if expected is None:
        assert samples[0].command_ned is None
    else:
        assert samples[0].command_ned == pytest.approx(expected, abs=1e-12)
    assert samples[0].vehicle_forward_ned == pytest.approx((0., 0., -1.), abs=1e-12)


def test_submitted_defaults_replace_old_guidance_in_replay_without_fabricating_a_target_lock():
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios/camera-chase-2d.yaml")
    defaults = dict(vel_body_fwd=0., vel_body_right=0., vel_body_down=0., yawspeed_deg_s=0.)
    evidence = {
        "pose": [{"timestamp": 0., "vehicle_ned": [0., 0., -20.],
                  "vehicle_quaternion": [1., 0., 0., 0.]}],
        "tracker": [{"timestamp": 0., "command_intent": {"fields": {**defaults, "vel_body_fwd": 3.}}}],
        "published": [{"timestamp": 0., "publish_success": True, "command_intent": None,
                       "submitted_fields": defaults, "publish_status": {"failsafe_defaults_active": True}}],
    }
    sample = build_timeline(scenario, evidence)[0]
    assert sample.command == defaults
    assert "fallback_defaults" in sample.events


def released_owner_evidence():
    return {
        "pose": [{"timestamp": t, "vehicle_ned": [0., 0., -20.], "vehicle_quaternion": [1., 0., 0., 0.]}
                 for t in (0., .5, 1., 1.5)],
        "published": [{"timestamp": 0., "publish_success": True, "submitted_fields": {
            "vel_body_fwd": 1., "vel_body_right": 0., "vel_body_down": 0., "yawspeed_deg_s": 0.,
        }}],
        "state": [{"timestamp": t, "state": "INACTIVE", "authority_state": "INACTIVE",
                   "command_expected": False, "observed_hold": True, "publisher_running": False,
                   "publisher_task_active": False, "command_owner_released_at": .5}
                  for t in (.5, 1., 1.5)],
    }


def test_observed_hold_after_publisher_release_keeps_pose_without_fabricating_commands(tmp_path):
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios/camera-chase-2d.yaml")
    samples = build_timeline(scenario, released_owner_evidence())
    assert samples[0].command["vel_body_fwd"] == 1.
    for sample in samples[1:]:
        assert sample.command_expected is False
        assert sample.command == {}
        assert sample.command_ned is None
        assert sample.effective_speed is None
        assert not sample.published
        assert not sample.stale
        assert sample.vehicle_ned == (0., 0., -20.)
    assert analyze_timeline(scenario, samples)["stale_after_fresh_samples"] == 0
    write_csv(tmp_path / "trace.csv", samples)
    with (tmp_path / "trace.csv").open() as stream:
        assert list(csv.DictReader(stream))[-1]["command_expected"] == "False"


@pytest.mark.parametrize("changed_field,value", [
    ("observed_hold", False), ("publisher_running", True), ("publisher_task_active", True),
    ("authority_state", "ACTIVE"), ("command_expected", True), ("command_owner_released_at", None),
])
def test_missing_active_command_remains_a_failure_without_complete_release_evidence(changed_field, value):
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios/camera-chase-2d.yaml")
    evidence = released_owner_evidence()
    for row in evidence["state"]:
        row[changed_field] = value
    assert analyze_timeline(scenario, build_timeline(scenario, evidence))["stale_after_fresh_samples"] > 0


def test_old_release_cannot_hide_missing_pose_new_active_session_or_late_publication():
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios/camera-chase-2d.yaml")
    evidence = released_owner_evidence()
    evidence["pose"] = evidence["pose"][:2]
    assert build_timeline(scenario, evidence)[-1].stale
    evidence = released_owner_evidence()
    evidence["state"][-1] = {"timestamp": 1.5, "state": "ACTIVE", "command_expected": True}
    assert build_timeline(scenario, evidence)[-1].stale
    evidence = released_owner_evidence()
    evidence["published"].append({**evidence["published"][0], "timestamp": 1.})
    samples = build_timeline(scenario, evidence)
    late = next(sample for sample in samples if sample.timestamp == 1.)
    assert late.published
    assert late.command["vel_body_fwd"] == 1.
    assert any(flag["type"] == "publication_after_authority_release"
               for flag in analyze_timeline(scenario, samples)["flags"])
    evidence["pose"].append({**evidence["pose"][-1], "timestamp": 3.})
    evidence["published"].append({**evidence["published"][0], "timestamp": 3.})
    late = build_timeline(scenario, evidence)[-1]
    assert "publication_after_authority_release" in late.events


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


def test_analysis_reports_target_speed_and_underpowered_reference():
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/camera-chase-2d.yaml"
    )
    summary = analyze_timeline(
        scenario,
        [
            VisualizationSample(timestamp=0.0, target_ned=(0.0, 0.0, 0.0)),
            VisualizationSample(timestamp=1.0, target_ned=(4.0, 0.0, 0.0)),
        ],
    )
    assert summary["target_speed_m_s"]["max"] == pytest.approx(4.0)
    assert summary["speed_reference_m_s"] == pytest.approx(3.5)
    assert any(flag["type"] == "target_faster_than_speed_reference" for flag in summary["flags"])


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
    fixture = write_catchup_evidence(scenario, evidence_root)
    samples = build_timeline(scenario, load_evidence(evidence_root))
    assert any(sample.tracker_state in {"target_lost", "reacquiring"} for sample in samples)
    assert all(abs(sample.command.get("vel_body_down", 0.0)) <= 1e-9 for sample in samples)
    if profile == "mc_velocity_chase":
        assert fixture["range_end_m"] < 1.0
        assert any(sample.tracker_state == "target_caught" for sample in samples)


def test_evidence_loader_uses_existing_trace_contracts(tmp_path):
    root = tmp_path / "evidence"
    (root / "trace").mkdir(parents=True)
    (root / "trace" / "offboard_publish_trace.jsonl").write_text(
        json.dumps({"record_type": "offboard_publish", "timestamp": 1, "publish_success": True}) + "\n",
        encoding="utf-8",
    )
    loaded = load_evidence(root)
    assert loaded["published"][0]["publish_success"] is True


def test_timeline_separates_proposed_submitted_px4_setpoint_and_observed_velocity(tmp_path):
    scenario = VisualizationScenario.from_yaml(
        ROOT / "tools/sih_visualization_scenarios/gimbal-vector-horizontal.yaml"
    )
    proposal = {"vel_body_fwd": 8, "vel_body_right": 0, "vel_body_down": 1}
    submitted = {"vel_body_fwd": 4, "vel_body_right": 0, "vel_body_down": 0}
    intent = {"reason": "normal_following", "fields": proposal}
    traces = {
        "trace/tracker_command_trace.jsonl": [
            {"record_type": "tracker_command", "timestamp": 0.0, "requested_speed": 8,
             "command_intent": intent},
        ],
        "trace/offboard_publish_trace.jsonl": [
            {"record_type": "offboard_publish", "timestamp": 0.1, "publish_success": True,
             "command_intent": intent, "submitted_fields": submitted},
            {"record_type": "offboard_publish", "timestamp": 0.2, "publish_success": False,
             "command_intent": intent, "submitted_fields": submitted},
        ],
        "px4/pose_trace.jsonl": [
            {"timestamp": 0.0, "vehicle_ned": [2, 0, -10], "velocity_ned": [3.6, .1, .02]},
            {"timestamp": 1.0, "vehicle_ned": [5, 0, -10]},
        ],
        "px4/velocity_setpoint_trace.jsonl": [
            {"record_type": "px4_velocity_setpoint", "timestamp": 0.1,
             "velocity_ned": [3.8, 0, 0]},
        ],
    }
    for relative_path, records in traces.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    proposed, published, failed, later = build_timeline(scenario, load_evidence(tmp_path))
    assert proposed.command_source == "proposal"
    assert proposed.command == proposal
    assert proposed.px4_velocity_setpoint_ned is None
    assert published.published
    assert published.command_source == "submitted"
    assert published.requested_speed == 8
    assert published.effective_speed == 4
    assert published.px4_velocity_setpoint_ned == (3.8, 0, 0)
    assert published.vehicle_velocity_ned == (3.6, .1, .02)
    assert published.limiting_reason is None
    assert "normal_following" in published.events
    assert not failed.published
    assert failed.command_source == "proposal"
    assert failed.command == proposal
    assert "publish_failed" in failed.events
    assert later.vehicle_ned == (5, 0, -10)
    assert later.vehicle_velocity_ned is None
    assert later.px4_velocity_setpoint_ned is None
    csv_path = tmp_path / "trace.csv"
    write_csv(csv_path, [published])
    with csv_path.open() as source:
        row = next(csv.DictReader(source))
    assert row["command_source"] == "submitted"
    assert float(row["px4_velocity_setpoint_n"]) == 3.8
    assert float(row["observed_velocity_n"]) == 3.6


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
    assert "quatRotate" not in html
    assert "native ? sample.course_direction_ned : sample.command_ned" in html
    assert "sample.vehicle_forward_ned" in html


@pytest.mark.parametrize("passed,label", [(True, "Scenario passed"), (False, "Scenario failed")])
def test_report_verdict_requires_an_explicit_qualification_result(passed, label):
    scenario = VisualizationScenario.from_yaml(ROOT / "tools/sih_visualization_scenarios/camera-chase-2d.yaml")
    summary = {"qualification_result": {"passed": passed}, "flags": []}
    html = build_html(scenario, [VisualizationSample(timestamp=0.)], summary)
    assert f'id="qualification">{label}' in html
    replay = build_html(scenario, [VisualizationSample(timestamp=0.)], {"flags": []})
    assert 'id="qualification">Replay only' in replay
