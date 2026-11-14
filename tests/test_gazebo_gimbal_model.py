"""Ideal camera kinematics only; these tests never invent a vehicle pose trace."""

from dataclasses import replace
import math

import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.gimbal_geometry import body_line_of_sight, resolve_angle_geometry
from classes.gimbal_types import TrackingState
from tools.gazebo_gimbal_model import IdealGimbalSettings, IdealStabilizedGimbal, ObservedGimbalPose


def observed(**changes):
    return replace(ObservedGimbalPose(1_000_000, 100., Vector3(0., 0., -20.),
        Quaternion(1., 0., 0., 0.), Vector3(0., 0., -20.), Quaternion(1., 0., 0., 0.)), **changes)


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('attitude', [(0., 0., 0.), (.2, -.3, 1.2), (0., -math.pi/2, 0.)])
@pytest.mark.parametrize('camera', [(0., 0., 0.), (0., .5, 2.9), (0., -math.pi/2, 0.)])
def test_observed_camera_ray_roundtrips_canonical_mount_once(mount, attitude, camera):
    pose = observed(body_to_ned=Quaternion.from_euler(*attitude), camera_to_ned=Quaternion.from_euler(*camera))
    geometry = resolve_angle_geometry({}, mount)
    angles = pose.angles(geometry)
    body = Vector3(*body_line_of_sight(angles, mount, geometry))
    ray = pose.body_to_ned.rotate(body)
    assert (ray.x, ray.y, ray.z) == pytest.approx((pose.direction_ned.x, pose.direction_ned.y, pose.direction_ned.z))


def test_intent_is_not_reported_as_actual_camera_motion():
    model = IdealStabilizedGimbal(IdealGimbalSettings(Vector3(0., 0., 0.), pointing_rate_deg_s=60.))
    first = observed()
    model.observe(first)
    model.aim(90., 0.)
    next_pose = replace(first, timestamp_us=1_100_000, received_at_monotonic_s=100.1)
    intent = model.observe(next_pose)
    ray = intent.camera_to_ned.rotate(Vector3(1., 0., 0.))
    assert math.degrees(math.atan2(ray.y, ray.x)) == pytest.approx(6.)
    assert next_pose.direction_ned == first.direction_ned == Vector3(1., 0., 0.)
    # No Gazebo feedback: another intent is still bounded from the observed zero angle.
    intent = model.observe(replace(next_pose, timestamp_us=1_200_000, received_at_monotonic_s=100.2))
    ray = intent.camera_to_ned.rotate(Vector3(1., 0., 0.))
    assert math.degrees(math.atan2(ray.y, ray.x)) == pytest.approx(6.)


def test_finite_point_lock_compensates_aircraft_translation_and_rotation():
    model = IdealStabilizedGimbal(IdealGimbalSettings(Vector3(.2, 0., -.1), pointing_rate_deg_s=3600.))
    model.observe(observed())
    target = Vector3(40., 10., 0.)
    model.lock_point(target)
    pose = observed(timestamp_us=1_100_000, received_at_monotonic_s=100.1,
        body_position_ned=Vector3(5., 0., -20.), camera_position_ned=Vector3(5., 0., -20.),
        body_to_ned=Quaternion.from_euler(.3, -math.pi/2, .5))
    command = model.observe(pose)
    expected = Vector3(35., 10., 20.).normalized()
    ray = command.camera_to_ned.rotate(Vector3(1., 0., 0.))
    assert (ray.x, ray.y, ray.z) == pytest.approx((expected.x, expected.y, expected.z))
    assert model.target_ned is target
    assert model.tracking_state is TrackingState.TARGET_SELECTION
    # A pose request is intent, not observed acquisition. Only later feedback
    # centering the finite point can establish an active track.
    centered = replace(pose, timestamp_us=1_200_000, received_at_monotonic_s=100.2,
                       camera_to_ned=command.camera_to_ned)
    model.observe(centered)
    assert model.tracking_state is TrackingState.TRACKING_ACTIVE
    assert command.position_ned != pose.camera_position_ned


def test_lost_target_does_not_claim_perfect_observations_or_renew_lock():
    model = IdealStabilizedGimbal(IdealGimbalSettings(Vector3(0., 0., 0.), pointing_rate_deg_s=3600.))
    pose = observed()
    model.observe(pose)
    model.lock_point(Vector3(20., 10., 0.))
    model.lose_target()
    command = model.observe(replace(pose, timestamp_us=1_100_000, received_at_monotonic_s=100.1))
    assert command.camera_to_ned.rotate(Vector3(1., 0., 0.)) == pose.direction_ned
    assert model.tracking_state is TrackingState.TARGET_LOST
    model.release_target()
    assert model.target_ned is None and model.tracking_state is TrackingState.DISABLED


@pytest.mark.parametrize('changes', [dict(timestamp_us=999_999),
    dict(received_at_monotonic_s=99.), dict(camera_to_ned=Quaternion.from_euler(0., 0., .1))])
def test_clock_reset_gap_and_rewritten_pose_fail_instead_of_becoming_motion(changes):
    model = IdealStabilizedGimbal(IdealGimbalSettings(Vector3(0., 0., 0.)))
    model.observe(observed())
    with pytest.raises(ValueError):
        model.observe(observed(**changes))


def test_paused_pose_does_not_advance_motion_or_receipt():
    model = IdealStabilizedGimbal(IdealGimbalSettings(Vector3(0., 0., 0.)))
    pose = observed()
    model.observe(pose)
    model.aim(90., -90.)
    assert model.observe(pose) is None


def test_vertical_pointing_keeps_heading_continuous():
    model = IdealStabilizedGimbal(IdealGimbalSettings(Vector3(0., 0., 0.), pointing_rate_deg_s=3600.))
    pose = observed()
    model.observe(pose)
    model.aim(70., 0.)
    q = model.observe(replace(pose, timestamp_us=1_100_000, received_at_monotonic_s=100.1)).camera_to_ned
    model.aim(-110., -90.)
    q = model.observe(replace(pose, timestamp_us=1_200_000, received_at_monotonic_s=100.2, camera_to_ned=q)).camera_to_ned
    down = q.rotate(Vector3(1., 0., 0.))
    assert (down.x, down.y, down.z) == pytest.approx((0., 0., 1.))
    # Horizontal camera-right remains at the previous heading near the pole.
    right = q.rotate(Vector3(0., 1., 0.))
    assert math.atan2(-right.x, right.y) == pytest.approx(math.radians(70.))


def test_reaching_the_point_reports_loss_without_an_undefined_ray():
    model = IdealStabilizedGimbal(IdealGimbalSettings(Vector3(0., 0., 0.)))
    model.observe(observed())
    model.lock_point(Vector3(20., 0., -20.))
    intent = model.observe(observed(timestamp_us=1_100_000, received_at_monotonic_s=100.1,
        camera_position_ned=Vector3(20., 0., -20.)))
    assert intent is not None and model.tracking_state is TrackingState.TARGET_LOST


def test_observation_gap_rebases_from_feedback_without_replaying_manual_movement():
    model = IdealStabilizedGimbal(IdealGimbalSettings(Vector3(0., 0., 0.)))
    pose = observed()
    model.observe(pose)
    model.manual('pan', 1., 30.)
    after_gap = replace(pose, timestamp_us=1_500_000, received_at_monotonic_s=100.5)
    intent = model.observe(after_gap)
    assert model.pose_gaps == 1 and model._manual is None
    assert intent.camera_to_ned == after_gap.camera_to_ned
    later = model.observe(replace(after_gap, timestamp_us=1_600_000, received_at_monotonic_s=100.6))
    assert later.camera_to_ned == after_gap.camera_to_ned
    assert model.tracking_state is TrackingState.DISABLED


def test_observation_gap_keeps_a_scene_target_without_claiming_motor_motion():
    model = IdealStabilizedGimbal(IdealGimbalSettings(Vector3(0., 0., 0.)))
    pose = observed()
    model.observe(pose)
    target = Vector3(10., 10., 0.)
    model.lock_point(target)
    after_gap = replace(pose, timestamp_us=1_500_000, received_at_monotonic_s=100.5)
    command = model.observe(after_gap)
    assert command.camera_to_ned == after_gap.camera_to_ned
    assert model.target_ned is target and model.tracking_state is TrackingState.TARGET_SELECTION
