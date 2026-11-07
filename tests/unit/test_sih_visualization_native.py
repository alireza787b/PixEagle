"""Native phase reports preserve course/EAS semantics and observed geometry."""

import csv
from dataclasses import replace
import math
from pathlib import Path

import pytest
import yaml

from classes.sih_visualization import (
    VisualizationScenario, VisualizationValidationError, analyze_timeline, build_timeline, write_csv,
)
from tools.sih_visualizer import build_html, write_png


ROOT = Path(__file__).resolve().parents[2]
NATIVE_SCENARIO = ROOT / "tools/sih_visualization_scenarios/gimbal-vector-native-fw.yaml"


def native_evidence():
    return {
        "pose": [{"timestamp": 0., "vehicle_ned": [0., 0., -30.],
                  "vehicle_quaternion": [math.sqrt(.5), 0., math.sqrt(.5), 0.],
                  "native_fw_forward_ned": [1., 0., 0.]}],
        "target": [{"timestamp": 0., "target_ned": [80., 0., -30.]}],
        "tracker": [{"timestamp": 0., "requested_speed": 16., "target_ned": [999., 0., 0.],
                     "command_intent": {"control_type": "fixed_wing_external", "fields": {
                         "course_rad": 0., "equivalent_airspeed_m_s": 16., "altitude_amsl_m": 519.}}}],
        "published": [{"timestamp": 0., "publish_success": True, "command_intent": {
            "control_type": "fixed_wing_external", "fields": {
                "course_rad": math.pi / 2, "equivalent_airspeed_m_s": 15., "altitude_amsl_m": 519.}}}],
        "state": [{"timestamp": 0., "aircraft_phase": "fixed_wing", "state": "active",
                   "observed_eas_m_s": 14.8, "native_effective_eas_m_s": 15.}],
    }


def test_native_scenario_uses_versioned_registered_command_contract():
    scenario = VisualizationScenario.from_yaml(NATIVE_SCENARIO)
    assert scenario.schema_version == 2
    assert scenario.command_contract == "fixed_wing_external"
    assert scenario.speed_source_policy == "native_auto"
    assert scenario.altitude_control is False


@pytest.mark.parametrize("changes,reason", [
    ({"schema_version": 1}, "schema_version 2"),
    ({"schema_version": True}, "schema_version"),
    ({"follower": {"speed_source_policy": "ground_speed_only"}}, "native speed-source"),
    ({"follower": {"profile": "gm_velocity_chase"}}, "contract must be"),
    ({"follower": {"input_contract": "image_position_2d"}}, "contract must be"),
])
def test_native_scenario_rejects_legacy_or_incompatible_contracts(tmp_path, changes, reason):
    raw = yaml.safe_load(NATIVE_SCENARIO.read_text())
    for key, value in changes.items():
        if key == "follower":
            raw[key].update(value)
        else:
            raw[key] = value
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(VisualizationValidationError, match=reason):
        VisualizationScenario.from_yaml(path)


def test_native_report_uses_submitted_course_and_independent_target_not_eas_as_velocity(tmp_path):
    scenario = VisualizationScenario.from_yaml(NATIVE_SCENARIO)
    sample = build_timeline(scenario, native_evidence())[0]
    assert sample.command["equivalent_airspeed_m_s"] == 15.
    assert sample.course_direction_ned == pytest.approx((0., 1., 0.), abs=1e-12)
    assert sample.command_ned is None
    assert sample.effective_speed is None
    assert sample.requested_speed == 16.
    assert sample.target_ned == (80., 0., -30.)
    assert sample.vehicle_forward_ned == (1., 0., 0.)  # PX4 already resolved tailsitter frame.
    assert sample.vehicle_quaternion[2] == pytest.approx(math.sqrt(.5))
    assert sample.observed_eas_m_s == 14.8
    assert sample.native_effective_eas_m_s == 15.
    output = tmp_path / "trace.csv"
    write_csv(output, [sample])
    with output.open() as stream:
        row = next(csv.DictReader(stream))
    assert row["effective_speed"] == row["command_n"] == ""
    assert float(row["equivalent_airspeed_m_s"]) == 15.
    assert float(row["target_timestamp_s"]) == 0.
    assert row["aircraft_phase"] == "fixed_wing"
    assert row["command_contract"] == "fixed_wing_external"


def test_native_fw_axis_is_unknown_without_px4_frame_evidence():
    scenario = VisualizationScenario.from_yaml(NATIVE_SCENARIO)
    evidence = native_evidence()
    del evidence["pose"][0]["native_fw_forward_ned"]
    sample = build_timeline(scenario, evidence)[0]
    assert sample.vehicle_forward_ned is None
    assert sample.vehicle_quaternion is not None


def test_vtol_report_changes_contract_only_from_current_intent(tmp_path):
    raw = yaml.safe_load(NATIVE_SCENARIO.read_text())
    raw["airframe"] = "vtol"
    raw["follower"]["command_contract"] = "vtol_external"
    path = tmp_path / "vtol.yaml"
    path.write_text(yaml.safe_dump(raw))
    scenario = VisualizationScenario.from_yaml(path)
    evidence = native_evidence()
    evidence["published"][0]["command_intent"] = {
        "control_type": "vtol_transition_external", "fields": {
            "course_rad": .5, "equivalent_airspeed_m_s": 15.,
        }}
    sample = build_timeline(scenario, evidence)[0]
    assert sample.command_contract == "vtol_transition_external"
    assert sample.command_ned is None
    assert sample.course_direction_ned is not None
    evidence["published"][0]["command_intent"].pop("control_type")
    assert build_timeline(scenario, evidence)[0].command_contract is None


def test_native_report_does_not_mask_pose_or_command_gaps():
    scenario = VisualizationScenario.from_yaml(NATIVE_SCENARIO)
    evidence = native_evidence()
    evidence["state"].append({"timestamp": 2., "aircraft_phase": "fixed_wing"})
    samples = build_timeline(scenario, evidence)
    assert samples[-1].stale is True
    assert samples[-1].vehicle_ned is None
    assert samples[-1].command == {}
    assert samples[-1].course_direction_ned is None
    evidence["pose"][0].pop("vehicle_ned")
    assert build_timeline(scenario, evidence)[0].stale is True


def test_target_speed_uses_truth_timestamps_not_interleaved_publication_times():
    scenario = VisualizationScenario.from_yaml(NATIVE_SCENARIO)
    evidence = native_evidence()
    evidence["target"] = [{"timestamp": t, "target_ned": [80. + 6. * t, 0., -30.]}
                          for t in (0., .05, .10)]
    evidence["pose"] += [{"timestamp": t, "vehicle_ned": [0., 0., -30.]}
                         for t in (.035, .085)]
    samples = build_timeline(scenario, evidence)
    summary = analyze_timeline(scenario, samples)
    assert summary["target_speed_m_s"]["max"] == pytest.approx(6.)
    assert summary["target_speed_m_s"]["mean"] == pytest.approx(6.)
    assert summary["target_speed_m_s"]["samples"] == 2
    assert [row.target_timestamp_s for row in samples] == [0., 0., .05, .05, .1]


def test_imported_truth_gap_is_unknown_instead_of_replaced_by_scenario_motion():
    scenario = VisualizationScenario.from_yaml(NATIVE_SCENARIO)
    evidence = native_evidence()
    evidence["pose"].append({"timestamp": 2., "vehicle_ned": [0., 0., -30.]})
    sample = build_timeline(scenario, evidence)[-1]
    assert sample.target_ned is None
    assert sample.target_timestamp_s is None


def test_recovery_events_and_reason_come_from_authoritative_continuity_trace():
    scenario = VisualizationScenario.from_yaml(NATIVE_SCENARIO)
    evidence = native_evidence()
    evidence["state"][0].update(state="COASTING", events=["injected_target_loss"],
                                limiting_reason="tracker_unusable_for_following")
    sample = build_timeline(scenario, evidence)[0]
    assert sample.limiting_reason == "tracker_unusable_for_following"
    assert "injected_target_loss" in sample.events
    summary = analyze_timeline(scenario, [sample])
    assert summary["continuity_state_counts"] == {"COASTING": 1}


def test_trace_reader_retains_zero_measurement_age():
    scenario = VisualizationScenario.from_yaml(NATIVE_SCENARIO)
    evidence = native_evidence()
    evidence["tracker"][0]["measurement_age_s"] = 0.
    evidence["tracker"][0]["tracker_output"] = {"metadata": {"measurement_age_s": .2}}
    assert build_timeline(scenario, evidence)[0].measurement_age_s == 0.


def test_native_analysis_distinguishes_eas_reference_and_altitude_suppression():
    scenario = replace(VisualizationScenario.from_yaml(NATIVE_SCENARIO), requested_speed=15.)
    evidence = native_evidence()
    evidence["target"].append({"timestamp": 1., "target_ned": [120., 0., -30.]})
    evidence["published"][0]["command_intent"]["fields"] = {
        "course_rad": 0., "equivalent_airspeed_m_s": 15., "height_rate_m_s": -2.,
    }
    summary = analyze_timeline(scenario, build_timeline(scenario, evidence))
    flags = {flag["type"] for flag in summary["flags"]}
    assert "altitude_disabled_vertical_command" in flags
    assert "target_faster_than_speed_reference" not in flags  # EAS isn't ground speed.
    assert summary["command_contract_counts"]["fixed_wing_external"] >= 1


def test_native_html_and_png_include_phase_specific_commands(tmp_path):
    pytest.importorskip("matplotlib")
    scenario = VisualizationScenario.from_yaml(NATIVE_SCENARIO)
    samples = build_timeline(scenario, native_evidence())
    html = build_html(scenario, samples, analyze_timeline(scenario, samples))
    assert "EAS request" in html
    assert "course intent" in html
    assert "native EAS reference" in html
    assert "observed EAS" in html
    assert "quatRotate" not in html
    assert "fetch(" not in html
    assert '<script src=' not in html  # Saved reports work offline.
    output = tmp_path / "summary.png"
    write_png(output, scenario, samples)
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
