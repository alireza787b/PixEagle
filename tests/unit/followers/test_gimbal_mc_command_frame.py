"""Physical mount rays and yaw-only MAVLink velocity frames must not be confused."""

import math
from unittest.mock import Mock

import pytest

from classes.aircraft_state import Quaternion, Vector3, body_ray_to_heading_frame
from classes.command_preview import CommandPreviewController
from classes.px4_interface_manager import PX4InterfaceManager
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target
from tests.unit.followers.test_gm_velocity_vector_control import _build_follower_stub, _run_normalization


@pytest.mark.parametrize("angles,ray,expected", [
    ((math.pi / 2, 0., 0.), (0., 1., 0.), (0., 0., 1.)),
    ((0., math.pi / 2, 0.), (1., 0., 0.), (0., 0., -1.)),
    ((0., 0., math.pi / 2), (1., 0., 0.), (0., 1., 0.)),
])
def test_euler_boundary_uses_independent_axis_direction_fixtures(angles, ray, expected):
    world = Quaternion.from_euler(*angles).rotate(Vector3(*ray))
    assert (world.x, world.y, world.z) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
@pytest.mark.parametrize("euler", [(20., 35., 130.), (-25., -15., -179.), (0., 0., 180.)])
@pytest.mark.parametrize("altitude", [True, False])
def test_unbound_mc_vector_follows_world_ray_with_tilt_without_vertical_redistribution(mount, euler, altitude):
    follower = _build_follower_stub(enable_altitude_control=altitude, current_velocity_magnitude=3.)
    follower.mount_type = mount
    # The fixture independently inverts the world target into provider angles.
    physical = Quaternion.from_euler(*(math.radians(value) for value in euler))
    yaw = math.radians(euler[2])
    follower.px4_controller.get_guidance_attitude = lambda: (physical, yaw)
    target = (20. * math.cos(yaw) - 8. * math.sin(yaw),
              20. * math.sin(yaw) + 8. * math.cos(yaw), 10.)
    angles = camera_angles_for_world_target((0., 0., 0.), target,
                                           (physical.w, physical.x, physical.y, physical.z), mount)
    command = _run_normalization(follower, *angles)
    # Horizontal coordinates are the rotation by heading alone, not full attitude.
    norm = math.hypot(*target)
    expected_fwd = 3. * (math.cos(yaw) * target[0] + math.sin(yaw) * target[1]) / norm
    expected_right = 3. * (-math.sin(yaw) * target[0] + math.cos(yaw) * target[1]) / norm
    assert command["vel_body_fwd"] == pytest.approx(expected_fwd)
    assert command["vel_body_right"] == pytest.approx(expected_right)
    assert command["vel_body_down"] == pytest.approx(3. * target[2] / norm if altitude else 0.)


@pytest.mark.parametrize("source", ["mavsdk", "mavlink2rest"])
def test_existing_telemetry_owner_supplies_physical_attitude_without_camera_yaw_offset(source, monkeypatch):
    monkeypatch.setattr("classes.px4_interface_manager.time.monotonic", lambda: 100.)
    controller = object.__new__(PX4InterfaceManager)
    controller.is_command_connection_ready = Mock(return_value=True)
    controller.get_telemetry_stale_timeout_s = lambda: .5
    controller._attitude_receipt_monotonic_s = 99.9
    controller._telemetry_source_active = source
    controller.camera_yaw_offset = 30.
    controller.current_yaw = 50. if source == "mavsdk" else 20.
    controller.current_pitch = 35.
    controller.current_roll = -20.
    attitude, heading = controller.get_guidance_attitude()
    assert heading == pytest.approx(math.radians(20.))
    assert attitude.heading_rad == pytest.approx(heading)
    expected = math.cos(math.radians(35.)), 0., -math.sin(math.radians(35.))
    ray = body_ray_to_heading_frame(Vector3(1., 0., 0.), attitude, heading)
    assert (ray.x, ray.y, ray.z) == pytest.approx(expected, abs=1e-12)
    controller.is_command_connection_ready.assert_called_once_with(require_fresh_telemetry=True)
    for receipt in (None, True, math.nan, 99., 100.1):
        controller._attitude_receipt_monotonic_s = receipt
        with pytest.raises(ValueError, match="attitude_stale"):
            controller.get_guidance_attitude()


def test_preview_attitude_is_explicit_synthetic_and_uses_the_same_frame_boundary():
    controller = CommandPreviewController()
    controller.current_pitch = 30.
    controller.current_yaw = -100.
    attitude, heading = controller.get_guidance_attitude()
    ray = body_ray_to_heading_frame(Vector3(1., 0., 0.), attitude, heading)
    assert (ray.x, ray.y, ray.z) == pytest.approx((math.sqrt(3.) / 2., 0., -.5), abs=1e-12)
    assert controller.is_command_preview is True
