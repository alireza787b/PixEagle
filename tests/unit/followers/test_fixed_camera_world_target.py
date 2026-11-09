"""Analytical simulated image geometry and measured-only MC qualification gates."""

from __future__ import annotations

import copy
from dataclasses import replace
import math
from pathlib import Path

import pytest
import yaml

from classes.aircraft_state import Quaternion
from tools.fixed_camera_world_target import FixedCamera, MCScenario, evaluate_response, stable_hold_window
from tools.run_sih_follower_validation import MC_PROFILES, scenario_path


def camera(*, down=False, offset=(0., 0., 0.)):
    return FixedCamera.from_mapping(dict(
        forward_body=[0., 0., 1.] if down else [1., 0., 0.],
        right_body=[0., 1., 0.], down_body=[-1., 0., 0.] if down else [0., 0., 1.],
        offset_body_m=offset, horizontal_fov_deg=90., vertical_fov_deg=90.,
    ))


def test_forward_camera_has_analytical_right_down_image_coordinates():
    assert camera().project((0., 0., 0.), (1., 0., 0., 0.), (10., 2., 1.)) == pytest.approx((.2, .1))


def test_down_camera_maps_ground_ahead_to_image_up_and_right_to_image_right():
    assert camera(down=True).project((0., 0., -20.), (1., 0., 0., 0.), (4., 2., 0.)) == pytest.approx((.1, -.2))


def test_camera_offset_is_physical_body_translation():
    assert camera(offset=(1., 0., 0.)).project((0., 0., 0.), (1., 0., 0., 0.), (11., 2., 1.)) == pytest.approx((.2, .1))


def test_full_raw_quaternion_projection_matches_independent_euler_matrix():
    roll, pitch, yaw = .3, -.2, .7
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    # Independent aerospace FRD-to-NED Euler rotation of body ray (10, 2, 1).
    target = (
        cp * cy * 10 + (sr * sp * cy - cr * sy) * 2 + cr * sp * cy + sr * sy,
        cp * sy * 10 + (sr * sp * sy + cr * cy) * 2 + cr * sp * sy - sr * cy,
        -sp * 10 + sr * cp * 2 + cr * cp,
    )
    q = Quaternion.from_euler(roll, pitch, yaw)
    assert camera().project((0., 0., 0.), (q.w, q.x, q.y, q.z), target) == pytest.approx((.2, .1))


@pytest.mark.parametrize("target", [(-1., 0., 0.), (1., 2., 0.), (1., 0., 2.), (0., 0., 0.)])
def test_behind_out_of_view_or_zero_ray_has_no_fabricated_measurement(target):
    assert camera().project((0., 0., 0.), (1., 0., 0., 0.), target) is None


def test_invalid_extrinsics_and_attitude_fail_closed():
    raw = dict(forward_body=[1., 0., 0.], right_body=[1., 0., 0.], down_body=[0., 0., 1.],
               offset_body_m=[0., 0., 0.], horizontal_fov_deg=90., vertical_fov_deg=60.)
    with pytest.raises(ValueError, match="orthogonal"):
        FixedCamera.from_mapping(raw)
    with pytest.raises(ValueError, match="quaternion_not_unit"):
        camera().project((0., 0., 0.), (0., 0., 0., 0.), (10., 0., 0.))


@pytest.mark.parametrize("profile", sorted(MC_PROFILES))
def test_checked_in_mc_scenarios_have_explicit_executable_camera_contract(profile):
    scenario = MCScenario.from_yaml(scenario_path(profile))
    assert scenario.visual.follower_profile == profile
    assert scenario.camera.project(scenario.visual.initial_vehicle_ned, (1., 0., 0., 0.), scenario.target_at(0., (0., 0., 0.)))


def test_frozen_world_anchor_is_not_rebased_on_current_aircraft_pose():
    scenario = MCScenario.from_yaml(scenario_path("mc_velocity_chase"))
    anchor = (7., 8., -.2)
    target = scenario.target_at(2., anchor)
    at_start = scenario.camera.project((7., 8., -20.2), (1., 0., 0., 0.), target)
    later = scenario.camera.project((8., 9., -20.2), (1., 0., 0., 0.), target)
    assert at_start != later
    assert scenario.target_at(2., anchor) == target


def stable_samples():
    return [dict(monotonic_s=index * .5, source_boot_ms=(index * 500 + 1, index * 500 + 2),
                 hold=True, airborne=True, velocity_ned=(0., 0., 0.), altitude_m=20.,
                 roll_deg=0., pitch_deg=0., yaw_rad=0.) for index in range(7)]


def test_stable_hold_requires_seven_actual_progressing_samples():
    assert stable_hold_window(stable_samples(), expected_altitude_m=20.)


@pytest.mark.parametrize("change", [
    {"source_boot_ms": (1, 2)}, {"airborne": False}, {"hold": False},
    {"velocity_ned": (.6, 0., 0.)}, {"velocity_ned": (0., 0., .3)},
    {"roll_deg": 4.}, {"pitch_deg": -4.}, {"yaw_rad": math.radians(.61)}, {"altitude_m": 20.11},
])
def test_repeated_pose_or_unsettled_aircraft_does_not_pass_hold_gate(change):
    samples = stable_samples()
    samples[-1].update(change)
    assert not stable_hold_window(samples, expected_altitude_m=20.)


def test_hold_gate_uses_all_samples_not_only_the_endpoints():
    samples = stable_samples()
    samples[2]["yaw_rad"] = math.radians(.4)
    samples[4]["yaw_rad"] = math.radians(-.4)
    assert not stable_hold_window(samples, expected_altitude_m=20.)
    samples = stable_samples()
    samples[3]["altitude_m"] = 20.11
    assert not stable_hold_window(samples, expected_altitude_m=20.)


@pytest.mark.parametrize("fault", [
    {"kind": "retarget", "at_s": 4., "duration_s": 1.},
    {"kind": "delayed_observation", "at_s": 4., "duration_s": .4},
    {"kind": "target_loss", "at_s": 4., "duration_s": 20.},
])
def test_unsupported_or_outside_fault_window_is_rejected(tmp_path, fault):
    raw = yaml.safe_load(scenario_path("mc_velocity_chase").read_text())
    raw["faults"] = [fault]
    raw["qualification"]["expected_handoff"] = True
    path = tmp_path / "fault.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        MCScenario.from_yaml(path)


def test_ground_fixture_refuses_same_altitude_target(tmp_path):
    raw = yaml.safe_load(scenario_path("mc_velocity_ground").read_text())
    raw["target"]["waypoints"][0]["position_ned"][2] = -20.
    path = tmp_path / "invalid-ground.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="below"):
        MCScenario.from_yaml(path)


def test_supported_loss_scenario_is_explicit_and_terminal():
    path = Path(scenario_path("mc_velocity_chase")).with_name("mc_velocity_chase-qualification-loss.yaml")
    scenario = MCScenario.from_yaml(path)
    assert scenario.expected_handoff
    assert scenario.loss_windows == ((4., 5.),)


@pytest.mark.parametrize("time_s", [0., 12., -1., float("nan")])
def test_takeover_outside_active_response_is_rejected(tmp_path, time_s):
    raw = yaml.safe_load(scenario_path("mc_velocity_chase").read_text())
    raw["faults"] = [{"kind": "pilot_takeover", "at_s": time_s}]
    raw["qualification"]["expected_handoff"] = True
    path = tmp_path / "takeover.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        MCScenario.from_yaml(path)


def test_takeover_is_explicit_and_not_a_loss_budget_reset(tmp_path):
    raw = yaml.safe_load(scenario_path("mc_velocity_chase").read_text())
    raw["faults"] = [{"kind": "pilot_takeover", "at_s": 6.}]
    raw["qualification"]["expected_handoff"] = True
    path = tmp_path / "takeover.yaml"
    path.write_text(yaml.safe_dump(raw))
    scenario = MCScenario.from_yaml(path)
    assert scenario.takeover_at_s == 6.
    assert scenario.loss_windows == ()
    raw["faults"].append({"kind": "target_loss", "at_s": 3., "duration_s": 1.})
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="separately"):
        MCScenario.from_yaml(path)


def test_retarget_offsets_are_independent_world_truth_and_do_not_reanchor_to_the_drone():
    path = scenario_path("mc_velocity_chase").with_name("mc_velocity_chase-qualification-retarget.yaml")
    scenario = MCScenario.from_yaml(path)
    anchor = (10., 20., -1.)
    for at, shift in ((3., 0.), (4., -3.), (4.2, -2.), (8., 0.)):
        original = scenario.visual.target_at(at)
        target = scenario.target_at(at, anchor)
        assert target == pytest.approx(tuple(original[i] + anchor[i] + (shift if i == 1 else 0.) for i in range(3)))
    assert not scenario.expected_handoff


def test_rate_retarget_scenario_cannot_enable_an_unimplemented_continuity_strategy(tmp_path):
    raw = yaml.safe_load(scenario_path("mc_attitude_rate").read_text())
    raw["faults"] = [{"kind": "retarget", "at_s": 4., "target_offset_ned": [0., 1., 0.]}]
    path = tmp_path / "rates.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="requires Stop"):
        MCScenario.from_yaml(path)


def test_stale_control_telemetry_scenario_declares_a_bounded_terminal_outage():
    scenario = MCScenario.from_yaml(scenario_path("mc_velocity_chase").with_name("mc_velocity_chase-qualification-stale.yaml"))
    assert scenario.telemetry_outage == (6., 3.)
    assert scenario.expected_handoff


def response_inputs():
    scenario = MCScenario.from_yaml(scenario_path("mc_velocity_position"))
    # Synthetic analysis fixtures only. These do not become qualification artifacts.
    observations = [dict(position_ned=(0., 0., -20.), target_ned=(18., 4., -20.),
                         quaternion_wxyz=(1., 0., 0., 0.), altitude_m=20., roll_deg=0., pitch_deg=0.),
                    dict(position_ned=(0., 0., -20.), target_ned=(18., 4., -20.),
                         quaternion_wxyz=(math.cos(.05), 0., 0., math.sin(.05)),
                         altitude_m=20., roll_deg=0., pitch_deg=0.)]
    publications = [dict(success=True, monotonic_s=timestamp,
                         fields=dict(vel_body_fwd=0., vel_body_right=0., vel_body_down=0., yawspeed_deg_s=5.))
                    for timestamp in (10., 10.05)]
    kwargs = dict(velocity_limits=dict(forward=.5, lateral=.5, vertical=.5, max_magnitude=1.),
                  rate_limits_deg_s=dict(yawspeed_deg_s=10., pitchspeed_deg_s=45., rollspeed_deg_s=45.),
                  attitude_limits_deg=dict(roll=35., pitch=35.))
    return scenario, observations, publications, kwargs


def test_response_requires_observed_alignment_not_just_successful_commands():
    scenario, observations, publications, kwargs = response_inputs()
    assert evaluate_response(scenario, observations, publications, **kwargs)["passed"]
    observations[1] = copy.deepcopy(observations[0])
    report = evaluate_response(scenario, observations, publications, **kwargs)
    assert not report["passed"]
    assert not report["checks"]["observed_image_response"]


def test_response_rejects_altitude_off_command_or_saved_limit_violation():
    scenario, observations, publications, kwargs = response_inputs()
    publications[0]["fields"]["vel_body_down"] = .1
    report = evaluate_response(scenario, observations, publications, **kwargs)
    assert not report["checks"]["altitude_off_zero_intent"]
    publications[0]["fields"]["yawspeed_deg_s"] = 11.
    assert not evaluate_response(scenario, observations, publications, **kwargs)["checks"]["saved_rate_bounds"]


@pytest.mark.parametrize("alter,accepted", [
    ({}, True),
    ({"attempted": True}, False),
    ({"attempted": None}, False),
    ({"command_ready": True}, False),
    ({"submitted_fields": {}}, False),
    ({"monotonic_s": 9.}, False),
    ({"monotonic_s": 13.081}, False),
])
def test_only_explicit_pre_submission_refusals_after_a_telemetry_fault_are_expected(alter, accepted):
    scenario, observations, publications, kwargs = response_inputs()
    scenario = replace(scenario, telemetry_outage=(6., 3.))
    refusal = dict(success=False, monotonic_s=10.1, attempted=False, fields=None,
                   submitted_fields=None, command_ready=False)
    refusal.update(alter)
    report = evaluate_response(scenario, observations, publications + [refusal], **kwargs,
                               expected_rejection_after_monotonic_s=10.08)
    assert report["passed"] is accepted
    assert report["metrics"]["pre_submission_rejection_count"] == (1 if refusal["attempted"] is False else 0)


VELOCITY_PROFILES = sorted(MC_PROFILES - {"mc_attitude_rate"})


def altitude_scenario_path(profile):
    return scenario_path(profile).with_name(f"{profile}-qualification-altitude.yaml")


@pytest.mark.parametrize("profile", VELOCITY_PROFILES)
def test_altitude_scenarios_declare_visible_vertical_stimulus_without_relaxing_gates(profile):
    baseline = MCScenario.from_yaml(scenario_path(profile))
    scenario = MCScenario.from_yaml(altitude_scenario_path(profile))
    assert scenario.visual.altitude_control
    assert scenario.minimum_vertical_response_m == .1
    assert scenario.duration_s == baseline.duration_s
    assert scenario.visual.stable_flight == baseline.visual.stable_flight
    assert scenario.altitude_tolerance_m == baseline.altitude_tolerance_m
    assert scenario.position_tolerance_m == baseline.position_tolerance_m
    assert max(abs(point.position_ned[2] - scenario.visual.initial_vehicle_ned[2])
               for point in scenario.visual.target_waypoints) > scenario.minimum_vertical_response_m
    for point in scenario.visual.target_waypoints:
        assert scenario.camera.project(scenario.visual.initial_vehicle_ned, (1., 0., 0., 0.), point.position_ned) is not None
    if profile == "mc_velocity_ground":
        assert all(-point.position_ned[2] < scenario.visual.limits["altitude_min"]
                   for point in scenario.visual.target_waypoints)


@pytest.mark.parametrize("qualification", [{}, {"minimum_vertical_response_m": .1}])
def test_altitude_enabled_same_height_target_cannot_qualify(tmp_path, qualification):
    raw = yaml.safe_load(scenario_path("mc_velocity_position").read_text())
    raw["follower"]["altitude_control"] = True
    raw["qualification"].update(qualification)
    path = tmp_path / "unexcited-altitude.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="minimum_vertical_response_m|vertical target stimulus"):
        MCScenario.from_yaml(path)


def test_altitude_flag_cannot_bypass_missing_stimulus_with_dataclass_replacement():
    scenario = MCScenario.from_yaml(scenario_path("mc_velocity_position"))
    with pytest.raises(ValueError, match="vertical target stimulus"):
        replace(scenario, visual=replace(scenario.visual, altitude_control=True), minimum_vertical_response_m=.1)


@pytest.mark.parametrize("minimum", [0., -.1, float("nan"), float("inf")])
def test_altitude_minimum_response_requires_a_positive_finite_distance(tmp_path, minimum):
    raw = yaml.safe_load(altitude_scenario_path("mc_velocity_position").read_text())
    raw["qualification"]["minimum_vertical_response_m"] = minimum
    path = tmp_path / "invalid-minimum.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        MCScenario.from_yaml(path)


def altitude_response_inputs(profile="mc_velocity_position", *, target_z=-23., observed_z=-20.2):
    _, observations, publications, kwargs = response_inputs()
    scenario = MCScenario.from_yaml(altitude_scenario_path(profile))
    for row in observations:
        row["target_ned"] = (18., 4., target_z) if profile != "mc_velocity_ground" else (4., 3., target_z)
    observations[-1]["position_ned"] = (0., 0., observed_z)
    observations[-1]["altitude_m"] = -observed_z
    for row in publications:
        row["fields"]["vel_body_down"] = math.copysign(.2, target_z + 20.)
    if profile == "mc_velocity_chase":
        observations[-1]["position_ned"] = (.2, 0., observed_z)
        for row in publications:
            row["fields"]["vel_body_fwd"] = .2
    if profile == "mc_velocity_ground":
        observations[-1]["position_ned"] = (.2, .2, observed_z)
        observations[-1]["quaternion_wxyz"] = (1., 0., 0., 0.)
        for row in publications:
            row["fields"].update(vel_body_fwd=.2, vel_body_right=.2, yawspeed_deg_s=0.)
    return scenario, observations, publications, kwargs


@pytest.mark.parametrize("profile,target_z,observed_z", [
    (profile, target_z, observed_z)
    for profile in VELOCITY_PROFILES if profile != "mc_velocity_ground"
    for target_z, observed_z in [(-23., -20.2), (-17., -19.8)]
] + [("mc_velocity_ground", 0., -19.8)])
def test_response_requires_actual_target_directed_vertical_movement(profile, target_z, observed_z):
    scenario, observations, publications, kwargs = altitude_response_inputs(profile, target_z=target_z, observed_z=observed_z)
    report = evaluate_response(scenario, observations, publications, **kwargs)
    assert report["checks"]["observed_vertical_response"]
    assert report["metrics"]["vertical_response_work_m"] == pytest.approx(.2)
    assert report["metrics"]["minimum_vertical_response_m"] == .1
    assert report["passed"]


@pytest.mark.parametrize("observed_z", [-20., -19.8, -20.05])
def test_vertical_commands_without_sufficient_correct_observed_motion_fail(observed_z):
    scenario, observations, publications, kwargs = altitude_response_inputs(observed_z=observed_z)
    report = evaluate_response(scenario, observations, publications, **kwargs)
    assert report["checks"]["observed_image_response"]
    assert not report["checks"]["observed_vertical_response"]
    assert not report["passed"]


def test_pitch_alignment_cannot_substitute_for_vertical_aircraft_response():
    scenario, observations, publications, kwargs = altitude_response_inputs(observed_z=-20.)
    # Correct yaw and pitch align the image without moving the aircraft.
    yaw = math.atan2(4., 18.)
    pitch = math.atan2(3., math.hypot(18., 4.))
    q = Quaternion.from_euler(0., pitch, yaw)
    observations[-1]["quaternion_wxyz"] = (q.w, q.x, q.y, q.z)
    observations[-1]["pitch_deg"] = math.degrees(pitch)
    before = scenario.camera.project(observations[0]["position_ned"], observations[0]["quaternion_wxyz"], observations[0]["target_ned"])
    after = scenario.camera.project(observations[-1]["position_ned"], observations[-1]["quaternion_wxyz"], observations[-1]["target_ned"])
    assert sum(value ** 2 for value in after) < sum(value ** 2 for value in before)
    report = evaluate_response(scenario, observations, publications, **kwargs)
    assert report["checks"]["observed_image_response"]
    assert report["metrics"]["vertical_response_work_m"] == 0.
    assert not report["checks"]["observed_vertical_response"]
    assert not report["passed"]


def test_target_only_height_closure_cannot_substitute_for_aircraft_motion():
    scenario, observations, publications, kwargs = altitude_response_inputs(observed_z=-20.)
    observations[-1]["target_ned"] = (18., 4., -22.)
    report = evaluate_response(scenario, observations, publications, **kwargs)
    assert report["metrics"]["vertical_response_work_m"] == 0.
    assert not report["checks"]["observed_vertical_response"]


def test_wrong_way_aircraft_motion_fails_even_when_target_motion_closes_height_gap():
    scenario, observations, publications, kwargs = altitude_response_inputs(observed_z=-19.8)
    observations[-1]["target_ned"] = (18., 4., -22.)
    report = evaluate_response(scenario, observations, publications, **kwargs)
    assert report["metrics"]["vertical_response_work_m"] == pytest.approx(-.2)
    assert not report["checks"]["observed_vertical_response"]


def test_vertical_motion_during_loss_does_not_count_as_observed_target_response():
    scenario, observations, publications, kwargs = altitude_response_inputs()
    observations[-1]["loss_active"] = True
    report = evaluate_response(scenario, observations, publications, **kwargs)
    assert report["metrics"]["vertical_response_work_m"] == 0.
    assert not report["checks"]["observed_vertical_response"]


def test_direct_rate_profile_keeps_its_distinct_altitude_and_thrust_contract():
    scenario = MCScenario.from_yaml(scenario_path("mc_attitude_rate"))
    scenario = replace(scenario, visual=replace(scenario.visual, altitude_control=True))
    _, observations, _, kwargs = response_inputs()
    publications = [dict(success=True, monotonic_s=timestamp,
                         fields=dict(rollspeed_deg_s=0., pitchspeed_deg_s=0., yawspeed_deg_s=5., thrust=.5))
                    for timestamp in (10., 10.05)]
    report = evaluate_response(scenario, observations, publications, **kwargs)
    assert "observed_vertical_response" not in report["checks"]
    assert report["checks"]["thrust_normalized"]
    assert report["checks"]["observed_attitude_envelope"]
