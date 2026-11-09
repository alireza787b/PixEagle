"""Analytical simulated image geometry and measured-only MC qualification gates."""

from __future__ import annotations

import copy
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
