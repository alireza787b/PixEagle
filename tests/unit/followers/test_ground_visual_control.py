"""Down-camera geometry and raw Ground image control; no closed-loop qualification."""

from copy import deepcopy
import math
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
import yaml

from classes.follower import FollowerFactory
from classes.parameters import Parameters
from classes.tracker_output import TrackerDataType, TrackerOutput
from tools.fixed_camera_world_target import FixedCamera


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[3]
LEGACY = {
    "COORDINATE_CORRECTIONS_ENABLED": True,
    "IS_CAMERA_GIMBALED": False,
    "BASE_ADJUSTMENT_FACTOR_X": 0.1,
    "BASE_ADJUSTMENT_FACTOR_Y": 0.1,
    "ALTITUDE_FACTOR": 0.005,
}


def down_camera():
    return FixedCamera.from_mapping({
        "forward_body": [0., 0., 1.], "right_body": [0., 1., 0.], "down_body": [-1., 0., 0.],
        "offset_body_m": [0., 0., 0.], "horizontal_fov_deg": 90., "vertical_fov_deg": 60.,
    })


@pytest.mark.parametrize("axis", ["roll", "pitch"])
@pytest.mark.parametrize("degrees", [-5., -1., 1., 5.])
@pytest.mark.parametrize("height", [10., 40.])
def test_down_camera_tilt_matches_independent_axis_rotation(axis, degrees, height):
    angle = math.radians(degrees)
    q = ((math.cos(angle / 2), math.sin(angle / 2), 0., 0.) if axis == "roll"
         else (math.cos(angle / 2), 0., math.sin(angle / 2), 0.))
    projected = down_camera().project((0., 0., -height), q, (0., 0., 0.))
    expected = ((math.tan(angle) / math.tan(math.radians(45.)), 0.) if axis == "roll"
                else (0., math.tan(angle) / math.tan(math.radians(30.))))
    assert projected == pytest.approx(expected)


@pytest.mark.parametrize("axis", ["roll", "pitch"])
@pytest.mark.parametrize("degrees", [-5., 5.])
def test_off_axis_ground_projection_keeps_depth_coupling(axis, degrees):
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    if axis == "roll":
        north, east, down = 4., 3. * c + 20. * s, -3. * s + 20. * c
        q = (math.cos(angle / 2), math.sin(angle / 2), 0., 0.)
    else:
        north, east, down = 4. * c - 20. * s, 3., 4. * s + 20. * c
        q = (math.cos(angle / 2), 0., math.sin(angle / 2), 0.)
    expected = (east / down / math.tan(math.radians(45.)),
                -north / down / math.tan(math.radians(30.)))
    assert down_camera().project((0., 0., -20.), q, (4., 3., 0.)) == pytest.approx(expected)


@pytest.fixture
def ground_factory():
    previous = Parameters.get_runtime_config_snapshot()
    defaults = yaml.safe_load((ROOT / "configs/config_default.yaml").read_text())

    def build(*, legacy=None, aim=(0., 0.), height=20., roll=0., pitch=0.):
        config = deepcopy(defaults)
        config["Follower"]["General"]["ENABLE_ALTITUDE_CONTROL"] = False
        config["MC_VELOCITY_GROUND"].update(legacy or {})
        config["PID"]["PID_GAINS"]["mc_vel_forward"] = {"p": .7, "i": 0., "d": 0.}
        config["PID"]["PID_GAINS"]["mc_vel_lateral"] = {"p": .2, "i": 0., "d": 0.}
        Parameters.publish_config_mapping(config)
        # Also cover a stale in-memory mapping, beyond the publisher's retirement filtering.
        Parameters.MC_VELOCITY_GROUND.update(legacy or {})
        for name, value in (legacy or {}).items():
            assert Parameters.MC_VELOCITY_GROUND[name] == value

        def no_attitude_heuristic():
            pytest.fail("Raw Ground image control must not request the retired attitude correction")

        controller = SimpleNamespace(
            is_command_preview=False, current_altitude=height, current_roll=roll,
            current_pitch=pitch, current_ground_speed=0., get_orientation=no_attitude_heuristic,
            is_command_connection_ready=lambda **kwargs: True,
        )
        return FollowerFactory.create_follower("mc_velocity_ground", controller, aim)

    try:
        yield build
    finally:
        Parameters.publish_config_mapping(previous)


def observe(follower, coords):
    follower.calculate_control_commands(TrackerOutput(
        TrackerDataType.POSITION_2D, timestamp=time.time(), tracking_active=True,
        position_2d=coords, confidence=1., tracker_id="ground_geometry_test",
    ))
    return follower.get_last_command_intent().fields


@pytest.mark.parametrize("height", [5., 20., 100.])
@pytest.mark.parametrize("aim,coords", [((0., 0.), (.2, -.2)), ((.2, -.3), (.4, -.5)), ((.2, -.3), (.2, -.3))])
def test_legacy_enabled_values_cannot_change_raw_image_commands(ground_factory, height, aim, coords):
    baseline = observe(ground_factory(aim=aim, height=height), coords)
    legacy = {**LEGACY, "BASE_ADJUSTMENT_FACTOR_X": 37., "BASE_ADJUSTMENT_FACTOR_Y": 51., "ALTITUDE_FACTOR": 2.}
    follower = ground_factory(legacy=legacy, aim=aim, height=height, roll=8., pitch=-7.)
    fields = observe(follower, coords)
    assert fields == pytest.approx(baseline)
    assert fields["vel_body_right"] == pytest.approx(.2 * (coords[0] - aim[0]))
    assert fields["vel_body_fwd"] == pytest.approx(-.7 * (coords[1] - aim[1]))
    assert fields["vel_body_down"] == 0.
    assert fields["yawspeed_deg_s"] == 0.
    status = follower.get_control_status()["configuration"]
    assert "gimbal_corrections_enabled" not in status
    assert "coordinate_corrections_enabled" not in status


def test_ground_command_axes_reduce_independently_projected_level_image_error(ground_factory):
    camera = down_camera()
    vehicle, target = (0., 0., -20.), (4., 3., 0.)
    measured = camera.project(vehicle, (1., 0., 0., 0.), target)
    fields = observe(ground_factory(), measured)
    assert fields["vel_body_fwd"] > 0.
    assert fields["vel_body_right"] > 0.
    forward_pose, right_pose = (.25, 0., -20.), (0., .25, -20.)
    forward_image = camera.project(forward_pose, (1., 0., 0., 0.), target)
    right_image = camera.project(right_pose, (1., 0., 0., 0.), target)
    assert abs(forward_image[1]) < abs(measured[1])
    assert abs(right_image[0]) < abs(measured[0])
