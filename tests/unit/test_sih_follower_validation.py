"""Tests for the unified SIH follower contract and evidence gate."""

import json
import hashlib
import os
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from classes.sih_visualization import VisualizationValidationError  # noqa: E402
from tools.run_sih_follower_validation import (  # noqa: E402
    normalize_harness_evidence,
    scenario_path,
    validate_px4_evidence,
    validate_scenario,
    write_failed_visualization,
    write_visualization,
)
from classes.sih_visualization import VisualizationScenario  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]


def native_case(root, *, altitude=False):
    raw = yaml.safe_load((ROOT / "tools/sih_visualization_scenarios/fw-navigation-native-image.yaml").read_text())
    raw["follower"]["altitude_control"] = altitude
    (root / "scenario.yaml").write_text(yaml.safe_dump(raw))
    scenario = VisualizationScenario.from_yaml(root / "scenario.yaml")
    fields = {"course_rad": 0., "equivalent_airspeed_m_s": 15., "height_rate_m_s": -1.} if altitude else {
        "course_rad": 0., "equivalent_airspeed_m_s": 15., "altitude_amsl_m": 519.}
    paths = {
        "px4/pose_trace.jsonl": [dict(timestamp=t, vehicle_ned=[40*t, 0., -30.],
            vehicle_quaternion=[1., 0., 0., 0.], native_fw_forward_ned=[1., 0., 0.]) for t in (0., .1, .2)],
        "trace/target_truth.jsonl": [dict(timestamp=t, target_ned=[80.+10*t, 0., -30.]) for t in (0., .1, .2)],
        "trace/offboard_publish_trace.jsonl": [dict(timestamp=t, record_type="offboard_publish", publish_success=True,
            command_intent={"control_type": "fixed_wing_external", "fields": fields}) for t in (0., .1, .2)],
        "trace/follower_state.jsonl": [dict(timestamp=t, state="ACTIVE", aircraft_phase="fixed_wing") for t in (0., .1, .2)],
    }
    for path, rows in paths.items():
        destination = root / path
        destination.parent.mkdir(exist_ok=True)
        destination.write_text("".join(json.dumps(row)+"\n" for row in rows))
    checks = {key: True for key in ("range_decreased", "altitude_floor", "finite_observed_response",
        "no_publication_after_stop", "hold_confirmed", "no_publication_failure", "expected_handoff",
        "altitude_guidance_response" if altitude else "altitude_hold")}
    result = dict(passed=True, scope="native_guidance_component_only", follower=scenario.follower_profile,
        input_contract=scenario.input_contract, application_startup_qualified=False, response_checks=checks,
        handoff={"executed": True, "local_sender_quiesced": True}, successful_publications=3, failed_publications=0)
    manifest = dict(evidence_kind="px4_observed_sih", qualification="native_guidance_component",
        application_startup_qualified=False, simulated_tracker_input=True, follower=scenario.follower_profile,
        input_contract=scenario.input_contract, mount=scenario.mount_type, altitude_guidance=altitude, configuration={})
    for name in ("config.yaml", "config_schema.yaml", "follower_commands.yaml"):
        contents = (f"retained: {name}\n").encode()
        (root / name).write_bytes(contents)
        manifest["configuration"][name] = {"path": name, "sha256": hashlib.sha256(contents).hexdigest()}
    (root / "manifest.json").write_text(json.dumps(manifest))
    (root / "result.json").write_text(json.dumps(result))
    return scenario, result, manifest


@pytest.mark.parametrize("altitude", [False, True])
def test_native_component_requires_and_displays_qualified_result(tmp_path, altitude):
    scenario, result, _ = native_case(tmp_path, altitude=altitude)
    summary = validate_px4_evidence(tmp_path, scenario)
    assert summary["qualification_result"] == result
    assert summary["qualification_scope"] == "native_guidance_component_only"
    assert summary["evidence_counts"]["pose"] == 3
    assert "not HTTP/App startup" in summary["claims"]
    output = write_visualization(tmp_path, scenario, summary)
    assert 'id="qualification">Scenario passed' in (output / "index.html").read_text()
    assert (output / "trace.csv").is_file() and (output / "summary.png").is_file()


@pytest.mark.parametrize("change", ["missing_result", "malformed_result", "nonobject_result", "failed_result",
    "legacy_scope", "wrong_profile", "wrong_input", "claimed_startup", "empty_checks", "false_check",
    "nonboolean_check", "missing_altitude_check", "failed_handoff", "publisher_failure", "no_publications"])
def test_native_result_cannot_grant_acceptance_when_missing_failed_or_inconsistent(tmp_path, change):
    scenario, result, _ = native_case(tmp_path)
    path = tmp_path / "result.json"
    if change == "missing_result":
        path.unlink()
    elif change == "malformed_result":
        path.write_text("{")
    elif change == "nonobject_result":
        path.write_text("[]")
    else:
        if change == "failed_result":
            result["passed"] = False
        elif change == "legacy_scope":
            result["scope"] = "native_vector_component_only"
        elif change == "wrong_profile":
            result["follower"] = "gm_velocity_vector"
        elif change == "wrong_input":
            result["input_contract"] = "gimbal_angles"
        elif change == "claimed_startup":
            result["application_startup_qualified"] = True
        elif change == "empty_checks":
            result["response_checks"] = {}
        elif change == "false_check":
            result["response_checks"]["altitude_floor"] = False
        elif change == "nonboolean_check":
            result["response_checks"]["altitude_floor"] = 1
        elif change == "missing_altitude_check":
            result["response_checks"].pop("altitude_hold")
        elif change == "failed_handoff":
            result["handoff"]["executed"] = False
        elif change == "publisher_failure":
            result["failed_publications"] = 1
        else:
            result["successful_publications"] = 0
        path.write_text(json.dumps(result))
    with pytest.raises(VisualizationValidationError):
        validate_px4_evidence(tmp_path, scenario)


@pytest.mark.parametrize("change", ["missing_manifest", "malformed_manifest", "wrong_profile", "wrong_input",
    "wrong_mount", "wrong_altitude", "wrong_qualification", "claimed_optical_input", "different_scenario"])
def test_native_manifest_must_match_captured_and_requested_scenario(tmp_path, change):
    scenario, _, manifest = native_case(tmp_path)
    path = tmp_path / "manifest.json"
    if change == "missing_manifest":
        path.unlink()
    elif change == "malformed_manifest":
        path.write_text("{")
    elif change == "different_scenario":
        raw = yaml.safe_load((tmp_path / "scenario.yaml").read_text())
        raw["name"] = "different-run"
        (tmp_path / "scenario.yaml").write_text(yaml.safe_dump(raw))
    else:
        key, value = {"wrong_profile": ("follower", "gm_velocity_vector"), "wrong_input": ("input_contract", "gimbal_angles"),
            "wrong_mount": ("mount", "VERTICAL"), "wrong_altitude": ("altitude_guidance", True),
            "wrong_qualification": ("qualification", "physical_aircraft"),
            "claimed_optical_input": ("simulated_tracker_input", False)}[change]
        manifest[key] = value
        path.write_text(json.dumps(manifest))
    with pytest.raises(VisualizationValidationError):
        validate_px4_evidence(tmp_path, scenario)


@pytest.mark.parametrize("name", ["config.yaml", "config_schema.yaml", "follower_commands.yaml"])
@pytest.mark.parametrize("change", ["tampered", "missing", "outside_path"])
def test_native_configuration_checksums_bind_archived_bytes(tmp_path, name, change):
    scenario, _, manifest = native_case(tmp_path)
    if change == "tampered":
        (tmp_path / name).write_text("changed: true\n")
    elif change == "missing":
        (tmp_path / name).unlink()
    else:
        manifest["configuration"][name]["path"] = "../"+name
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(VisualizationValidationError, match="configuration checksum mismatch"):
        validate_px4_evidence(tmp_path, scenario)


@pytest.mark.parametrize("path,reason", [("px4/pose_trace.jsonl", "pose trace"),
    ("trace/target_truth.jsonl", "target_truth"), ("trace/offboard_publish_trace.jsonl", "publication records")])
def test_native_verdict_never_substitutes_for_required_raw_evidence(tmp_path, path, reason):
    scenario, _, _ = native_case(tmp_path)
    (tmp_path / path).unlink()
    with pytest.raises(VisualizationValidationError, match=reason):
        validate_px4_evidence(tmp_path, scenario)


def test_native_success_never_bypasses_raw_pose_or_command_gaps(tmp_path):
    scenario, _, _ = native_case(tmp_path)
    target = tmp_path / "trace/target_truth.jsonl"
    with target.open("a") as stream:
        stream.write(json.dumps(dict(timestamp=1.5, target_ned=[90., 0., -30.]))+"\n")
    with pytest.raises(VisualizationValidationError, match="stale pose or command gaps"):
        validate_px4_evidence(tmp_path, scenario)


@pytest.mark.parametrize("change", ["missing", "malformed", "failed", "contradictory_trace"])
def test_failed_native_validation_retains_failed_report_and_original_result(tmp_path, change):
    scenario, result, _ = native_case(tmp_path)
    path = tmp_path / "result.json"
    if change == "missing":
        path.unlink()
    elif change == "malformed":
        path.write_text("{")
    elif change == "failed":
        result["response_checks"]["hold_confirmed"] = False
        path.write_text(json.dumps(result))
    else:
        trace = tmp_path / "trace/offboard_publish_trace.jsonl"
        with trace.open("a") as stream:
            stream.write(json.dumps(dict(timestamp=.3, record_type="offboard_publish", publish_success=False))+"\n")
    original = path.read_bytes() if path.is_file() else None
    with pytest.raises(VisualizationValidationError) as failure:
        validate_px4_evidence(tmp_path, scenario)
    output = write_failed_visualization(tmp_path, scenario, failure.value)
    assert 'id="qualification">Scenario failed' in (output / "index.html").read_text()
    assert "Scenario passed" not in (output / "index.html").read_text()
    assert json.loads((output / "summary.json").read_text())["qualification_result"]["passed"] is False
    assert (path.read_bytes() if path.is_file() else None) == original


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


@pytest.mark.parametrize("late_publish", [False, True])
def test_px4_gate_distinguishes_released_owner_from_obsolete_publication(tmp_path, late_publish):
    scenario = VisualizationScenario.from_yaml(scenario_path("mc_velocity_position"))
    paths = {
        "px4/pose_trace.jsonl": [dict(timestamp=t, vehicle_ned=[0., 0., -20.],
                                      vehicle_quaternion=[1., 0., 0., 0.]) for t in (0., .5, 1.)],
        "trace/target_truth.jsonl": [dict(timestamp=t, target_ned=[5., 0., -20.]) for t in (0., .5, 1.)],
        "trace/offboard_publish_trace.jsonl": [dict(timestamp=0., record_type="offboard_publish", publish_success=True,
            submitted_fields=dict(vel_body_fwd=0., vel_body_right=0., vel_body_down=0., yawspeed_deg_s=0.))],
        "trace/follower_state.jsonl": [dict(timestamp=t, state="INACTIVE", authority_state="INACTIVE",
            command_expected=False, observed_hold=True, publisher_running=False, publisher_task_active=False,
            command_owner_released_at=.5) for t in (.5, 1.)],
    }
    if late_publish:
        paths["trace/offboard_publish_trace.jsonl"].append({
            **paths["trace/offboard_publish_trace.jsonl"][0], "timestamp": 1.,
        })
    for path, rows in paths.items():
        target = tmp_path / path
        target.parent.mkdir(exist_ok=True)
        target.write_text("".join(json.dumps(row) + "\n" for row in rows))
    (tmp_path / "result.json").write_text(json.dumps({
        "passed": True, "scope": "actual_mc_follower_component_only", "follower": "mc_velocity_position",
    }))
    if late_publish:
        with pytest.raises(VisualizationValidationError):
            validate_px4_evidence(tmp_path, scenario)
    else:
        assert validate_px4_evidence(tmp_path, scenario)["stale_after_fresh_samples"] == 0


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
