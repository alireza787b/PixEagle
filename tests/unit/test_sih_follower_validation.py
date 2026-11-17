"""Tests for the unified SIH follower contract and evidence gate."""

import json
import hashlib
import os
import sys
from pathlib import Path
from unittest.mock import Mock

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


def raw_capture_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
            and path.relative_to(root).parts[0] != "visualization" and path.relative_to(root) != Path("summary.json")}


@pytest.fixture
def readonly_cli(monkeypatch):
    import tools.run_sih_follower_validation as entry
    forbidden = Mock(side_effect=AssertionError("read-only validation attempted external execution or raw normalization"))
    monkeypatch.setattr(entry, "run_external", forbidden)
    monkeypatch.setattr(entry.subprocess, "run", forbidden)
    monkeypatch.setattr(entry, "normalize_harness_evidence", forbidden)
    monkeypatch.setattr(entry, "write_png", Mock())
    return entry


@pytest.mark.parametrize("explicit_profile", [False, True])
def test_readonly_cli_validates_native_ninth_profile_without_starting_any_process(
        tmp_path, monkeypatch, capsys, readonly_cli, explicit_profile):
    native_case(tmp_path)
    (tmp_path / "tracker.jsonl").write_text(json.dumps({"timestamp": 0., "command_intent": {"fields": {}}})+"\n")
    before = raw_capture_bytes(tmp_path)
    argv = ["validator", "--validate-existing", "--evidence-root", str(tmp_path)]
    if explicit_profile:
        argv += ["--follower", "fw_navigation_chase"]
    monkeypatch.setattr(sys, "argv", argv)
    assert readonly_cli.main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["mode"] == "validate_existing"
    assert response["follower"] == "fw_navigation_chase"
    assert 'id="qualification">Scenario passed' in (tmp_path / "visualization/index.html").read_text()
    assert (tmp_path / "visualization/trace.csv").is_file()
    assert not (tmp_path / "trace/tracker_command_trace.jsonl").exists()
    assert raw_capture_bytes(tmp_path) == before


@pytest.mark.parametrize("failure", ["malformed_result", "missing_result", "failed_result", "malformed_manifest"])
def test_readonly_cli_retains_failed_visualization_and_preserves_every_raw_byte(
        tmp_path, monkeypatch, readonly_cli, failure):
    _, result, _ = native_case(tmp_path)
    if failure == "malformed_result":
        (tmp_path / "result.json").write_text("{")
    elif failure == "missing_result":
        (tmp_path / "result.json").unlink()
    elif failure == "failed_result":
        result["passed"] = False
        (tmp_path / "result.json").write_text(json.dumps(result))
    else:
        (tmp_path / "manifest.json").write_text("{")
    before = raw_capture_bytes(tmp_path)
    monkeypatch.setattr(sys, "argv", ["validator", "--validate-existing", "--evidence-root", str(tmp_path)])
    with pytest.raises(VisualizationValidationError):
        readonly_cli.main()
    assert 'id="qualification">Scenario failed' in (tmp_path / "visualization/index.html").read_text()
    assert raw_capture_bytes(tmp_path) == before


def test_readonly_cli_rejects_optional_profile_mismatch_without_changing_capture(tmp_path, monkeypatch, readonly_cli):
    native_case(tmp_path)
    before = raw_capture_bytes(tmp_path)
    monkeypatch.setattr(sys, "argv", ["validator", "--validate-existing", "--evidence-root", str(tmp_path),
                                     "--follower", "mc_velocity_chase"])
    with pytest.raises(SystemExit) as error:
        readonly_cli.main()
    assert error.value.code == 2
    assert raw_capture_bytes(tmp_path) == before
    assert not (tmp_path / "visualization").exists()


@pytest.mark.parametrize("extra", [["--execute"], ["--enable-altitude-control"], ["--scenario", "other.yaml"],
                                   ["--simulation-build-manifest", "other.json"], ["--telemetry-source", "mavsdk"]])
def test_readonly_cli_excludes_execution_and_capture_overrides(tmp_path, monkeypatch, readonly_cli, extra):
    native_case(tmp_path)
    before = raw_capture_bytes(tmp_path)
    monkeypatch.setattr(sys, "argv", ["validator", "--validate-existing", "--evidence-root", str(tmp_path), *extra])
    with pytest.raises(SystemExit) as error:
        readonly_cli.main()
    assert error.value.code == 2
    assert raw_capture_bytes(tmp_path) == before
    assert not (tmp_path / "visualization").exists()


def test_readonly_cli_requires_an_existing_run_and_captured_scenario(tmp_path, monkeypatch, readonly_cli):
    for argv in (["validator", "--validate-existing"],
                 ["validator", "--validate-existing", "--evidence-root", str(tmp_path / "absent")]):
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as error:
            readonly_cli.main()
        assert error.value.code == 2
    assert not (tmp_path / "absent").exists()
    monkeypatch.setattr(sys, "argv", ["validator", "--validate-existing", "--evidence-root", str(tmp_path)])
    with pytest.raises(VisualizationValidationError, match="Cannot read scenario"):
        readonly_cli.main()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("argv", [[], ["--execute"], ["--follower", "unknown-profile"],
    ["--follower", "fw_navigation_chase"], ["--execute", "--follower", "fw_navigation_chase"]])
def test_original_cli_still_requires_supported_capture_profile(monkeypatch, readonly_cli, argv):
    monkeypatch.setattr(sys, "argv", ["validator", *argv])
    with pytest.raises(SystemExit) as error:
        readonly_cli.main()
    assert error.value.code == 2


def test_original_default_dryrun_remains_contract_only(monkeypatch, capsys, readonly_cli):
    monkeypatch.setattr(sys, "argv", ["validator", "--follower", "mc_velocity_position"])
    assert readonly_cli.main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["mode"] == "dry_run"
    assert response["scenario"]["profile"] == "mc_velocity_position"


@pytest.mark.parametrize('profile', ['gm_velocity_chase', 'gm_velocity_vector'])
@pytest.mark.parametrize('mount', ['horizontal', 'vertical'])
@pytest.mark.parametrize('altitude', ['off', 'on'])
def test_gimbal_dryrun_uses_declared_family_without_profile_dispatch_list(
        tmp_path, monkeypatch, capsys, readonly_cli, profile, mount, altitude):
    scenario = ROOT / f'tools/sih_visualization_scenarios/{profile}-qualification-{mount}-{altitude}.yaml'
    monkeypatch.setattr(readonly_cli, 'PROFILE_SCENARIOS', {})
    monkeypatch.setattr(sys, 'argv', ['runner', '--follower', profile, '--scenario', str(scenario),
        '--simulation-build-manifest', 'not-read-in-dryrun.json', '--evidence-root', str(tmp_path / 'new')])
    assert readonly_cli.main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['mode'] == 'dry_run'
    assert plan['scenario']['input_contract'] == 'gimbal_angles'
    assert plan['scenario']['mount_type'] == mount.upper()
    assert plan['scenario']['altitude_control'] is (altitude == 'on')
    assert not (tmp_path / 'new').exists()


def test_gimbal_execute_requires_source_attestation_before_any_host_launch(tmp_path, monkeypatch, readonly_cli):
    monkeypatch.setattr(sys, 'argv', ['runner', '--execute', '--follower', 'gm_velocity_chase',
                                     '--evidence-root', str(tmp_path / 'never-created')])
    with pytest.raises(SystemExit) as error:
        readonly_cli.main()
    assert error.value.code == 2
    assert not (tmp_path / 'never-created').exists()


@pytest.mark.parametrize('profile', ['gm_velocity_chase', 'gm_velocity_vector'])
@pytest.mark.parametrize('mount', ['horizontal', 'vertical'])
@pytest.mark.parametrize('altitude', ['off', 'on'])
@pytest.mark.parametrize('fault,expected_handoff', [
    ([dict(kind='retarget', at_s=8., target_offset_ned=[0., 2., 0.])], False),
    ([dict(kind='target_loss', at_s=8., duration_s=1.)], False),
    ([dict(kind='target_loss', at_s=8., duration_s=9.)], True),
    ([dict(kind='pilot_takeover', at_s=12.)], True),
])
def test_gimbal_fault_dry_run_is_validated_without_any_host_or_container_launch(
        tmp_path, monkeypatch, capsys, readonly_cli, profile, mount, altitude, fault, expected_handoff):
    source = ROOT / f'tools/sih_visualization_scenarios/{profile}-qualification-{mount}-{altitude}.yaml'
    raw = yaml.safe_load(source.read_text())
    raw['faults'] = fault
    raw['qualification']['expected_handoff'] = expected_handoff
    scenario = tmp_path / 'fault.yaml'
    scenario.write_text(yaml.safe_dump(raw))
    monkeypatch.setattr(sys, 'argv', ['runner', '--follower', profile, '--scenario', str(scenario),
        '--simulation-build-manifest', 'not-read-before-scenario-validation.json', '--evidence-root', str(tmp_path / 'new')])
    assert readonly_cli.main() == 0
    assert json.loads(capsys.readouterr().out)['mode'] == 'dry_run'
    readonly_cli.run_external.assert_not_called()
    assert not (tmp_path / 'new').exists()


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


def retained_fault_capture(root, kind, *, angles=False):
    source = scenario_path('gm_velocity_vector') if angles else scenario_path('mc_velocity_chase')
    raw = yaml.safe_load(source.read_text())
    fault = dict(kind=kind, at_s=8.)
    if kind in {'target_loss', 'stale_telemetry'}:
        fault['duration_s'] = 1.
    raw['faults'] = [fault]
    raw['qualification']['expected_handoff'] = True
    (root / 'scenario.yaml').write_text(yaml.safe_dump(raw))
    scenario = VisualizationScenario.from_yaml(root / 'scenario.yaml')
    reason = {'target_loss': 'tracker_unusable_for_following', 'pilot_takeover': 'offboard_mode_exited',
              'stale_telemetry': 'vehicle_state_stale'}[kind]
    result = dict(passed=True, scope='actual_mc_follower_component_only', follower=scenario.follower_profile,
                  handoff=dict(reason_code=reason, result='stopped' if kind == 'pilot_takeover' else 'confirmed_hold'))
    output = dict(data_type='gimbal_angles' if angles else 'position_2d', tracking_active=False,
                  has_output=angles, usable_for_following=False)
    if angles:
        output['gimbal_observation'] = dict(tracking_state='TARGET_LOST')
    paths = {
        'px4/pose_trace.jsonl': [dict(timestamp=t, vehicle_ned=[0., 0., -20.],
                                      vehicle_quaternion=[1., 0., 0., 0.]) for t in (0., .1, .2)],
        'trace/target_truth.jsonl': [dict(timestamp=t, target_ned=[18., 0., -20.]) for t in (0., .1, .2)],
        'trace/offboard_publish_trace.jsonl': [dict(timestamp=t, record_type='offboard_publish', publish_success=True,
            submitted_fields=dict(vel_body_fwd=.1, vel_body_right=0., vel_body_down=0., yawspeed_deg_s=0.)) for t in (0., .1, .2)],
        'trace/tracker_command_trace.jsonl': [dict(timestamp=.1, record_type='tracker_command', tracker_output=output,
            dispatch_accepted=False, continuity=dict(authority_state='HANDOFF_PENDING', handoff_request=dict(reason_code=reason)))],
        'trace/follower_state.jsonl': [dict(timestamp=.2, state='INACTIVE', reason_code='handoff_confirmed')],
        'fault-events.jsonl': [dict(timestamp=.05, event=kind, mode='Hold' if kind == 'pilot_takeover' else None)],
    }
    for name, rows in paths.items():
        path = root / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    (root / 'result.json').write_text(json.dumps(result))
    if kind == 'pilot_takeover':
        (root / 'takeover-cleanup.json').write_text(json.dumps(dict(errors=[], sender_quiesce=dict(
            authority_released=True, local_sender_quiesced=True, vehicle_hold_acknowledged=False))))
    return scenario, result


@pytest.mark.parametrize('kind', ['target_loss', 'pilot_takeover', 'stale_telemetry'])
def test_retained_faults_accept_existing_legacy_witnesses_without_new_fields(tmp_path, kind):
    scenario, _ = retained_fault_capture(tmp_path, kind)
    before = raw_capture_bytes(tmp_path)
    assert validate_px4_evidence(tmp_path, scenario, normalize=False)['qualification_result']['passed']
    assert raw_capture_bytes(tmp_path) == before


@pytest.mark.parametrize('kind', ['target_loss', 'pilot_takeover', 'stale_telemetry'])
def test_retained_faults_reject_cleanup_only_success_without_rewriting_raw_evidence(tmp_path, kind):
    scenario, result = retained_fault_capture(tmp_path, kind)
    result['handoff'] = dict(reason_code='operator_stop', result='confirmed_hold')
    (tmp_path / 'result.json').write_text(json.dumps(result))
    before = raw_capture_bytes(tmp_path)
    with pytest.raises(VisualizationValidationError, match='fault_outcome_unproven'):
        validate_px4_evidence(tmp_path, scenario, normalize=False)
    assert raw_capture_bytes(tmp_path) == before


@pytest.mark.parametrize('angles', [False, True])
def test_retained_loss_requires_received_loss_not_only_a_scheduled_event(tmp_path, angles):
    scenario, _ = retained_fault_capture(tmp_path, 'target_loss', angles=angles)
    trace = tmp_path / 'trace/tracker_command_trace.jsonl'
    row = json.loads(trace.read_text())
    row['tracker_output'].update(tracking_active=True, has_output=True, usable_for_following=True)
    if angles:
        row['tracker_output']['gimbal_observation']['tracking_state'] = 'TRACKING_ACTIVE'
    trace.write_text(json.dumps(row)+'\n')
    before = raw_capture_bytes(tmp_path)
    with pytest.raises(VisualizationValidationError, match='fault_outcome_unproven'):
        validate_px4_evidence(tmp_path, scenario, normalize=False)
    assert raw_capture_bytes(tmp_path) == before


@pytest.mark.parametrize('method', ['action.hold', 'offboard.stop'])
def test_retained_takeover_rejects_additional_actual_mode_calls(tmp_path, method):
    scenario, _ = retained_fault_capture(tmp_path, 'pilot_takeover')
    (tmp_path / 'sdk-mode-calls.jsonl').write_text(''.join(json.dumps(dict(timestamp=t, method=name))+'\n'
        for t, name in ((.06, 'action.hold'), (.07, method))))
    with pytest.raises(VisualizationValidationError, match='fault_outcome_unproven'):
        validate_px4_evidence(tmp_path, scenario, normalize=False)


def test_retained_failed_pre_cleanup_verdict_cannot_be_replaced_by_successful_cleanup(tmp_path):
    scenario, result = retained_fault_capture(tmp_path, 'target_loss')
    (tmp_path / 'fault-outcome-before-cleanup.json').write_text(json.dumps(dict(
        following_active=True, handoff=None, checks=dict(fault_handoff_before_operator_cleanup=False))))
    before = raw_capture_bytes(tmp_path)
    with pytest.raises(VisualizationValidationError, match='fault_outcome_unproven'):
        validate_px4_evidence(tmp_path, scenario, normalize=False)
    assert result['passed']
    assert raw_capture_bytes(tmp_path) == before


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
