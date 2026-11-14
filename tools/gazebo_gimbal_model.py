"""Ideal stabilized pointing for training, driven by observed Gazebo poses.

This is not a measured FL-30 joint/motor model. Output is camera pose intent;
subsequent Gazebo pose feedback, never intent integration, supplies observations.
Aircraft poses are inputs only and are never predicted or modified here.
"""

from dataclasses import dataclass
import math

from classes.aircraft_state import Quaternion, Vector3, finite_number
from classes.gimbal_geometry import AngleGeometry, body_bearing_to_angles
from classes.gimbal_types import TrackingState


@dataclass(frozen=True)
class ObservedGimbalPose:
    timestamp_us: int
    received_at_monotonic_s: float
    body_position_ned: Vector3
    body_to_ned: Quaternion
    camera_position_ned: Vector3
    camera_to_ned: Quaternion

    def __post_init__(self):
        if type(self.timestamp_us) is not int or not 0 <= self.timestamp_us < 2**64:
            raise ValueError('gimbal_pose_time_invalid')
        if finite_number(self.received_at_monotonic_s, 'gimbal_pose_receipt') < 0:
            raise ValueError('gimbal_pose_receipt_invalid')
        if (not isinstance(self.body_position_ned, Vector3) or not isinstance(self.camera_position_ned, Vector3)
                or not isinstance(self.body_to_ned, Quaternion) or not isinstance(self.camera_to_ned, Quaternion)):
            raise ValueError('gimbal_pose_geometry_invalid')

    @property
    def direction_ned(self):
        return self.camera_to_ned.rotate(Vector3(1., 0., 0.)).normalized()

    def angles(self, geometry: AngleGeometry):
        q = self.body_to_ned
        inverse = Quaternion(q.w, -q.x, -q.y, -q.z)
        body = inverse.rotate(self.direction_ned)
        azimuth = math.degrees(math.atan2(body.y, body.x))
        depression = math.degrees(math.atan2(body.z, body.horizontal_magnitude))
        return body_bearing_to_angles(azimuth, depression, geometry)


@dataclass(frozen=True)
class IdealGimbalSettings:
    camera_offset_body_frd_m: Vector3
    pointing_rate_deg_s: float = 90.
    maximum_pose_gap_s: float = .25
    acquisition_tolerance_deg: float = 1.

    def __post_init__(self):
        if not isinstance(self.camera_offset_body_frd_m, Vector3):
            raise ValueError('gimbal_camera_offset_invalid')
        for name in ('pointing_rate_deg_s', 'maximum_pose_gap_s', 'acquisition_tolerance_deg'):
            if finite_number(getattr(self, name), name) <= 0:
                raise ValueError('gimbal_model_limit_invalid')


@dataclass(frozen=True)
class CameraPoseIntent:
    position_ned: Vector3
    camera_to_ned: Quaternion
    observation_timestamp_us: int


def _direction(azimuth_deg, elevation_deg):
    azimuth = math.radians(finite_number(azimuth_deg, 'gimbal_azimuth'))
    elevation = finite_number(elevation_deg, 'gimbal_elevation')
    if not -90. <= elevation <= 90.:
        raise ValueError('gimbal_elevation_out_of_range')
    elevation = math.radians(elevation)
    return Vector3(math.cos(elevation) * math.cos(azimuth),
                   math.cos(elevation) * math.sin(azimuth), -math.sin(elevation))


def _pointing_quaternion(direction, *, retained_heading_rad):
    heading = (retained_heading_rad if direction.horizontal_magnitude < 1e-9
               else math.atan2(direction.y, direction.x))
    pitch = -math.atan2(direction.z, direction.horizontal_magnitude)
    return Quaternion.from_euler(0., pitch, heading), heading


def _limited_rotation(observed, desired, maximum_angle_rad):
    start, end = tuple(getattr(observed, n) for n in ('w', 'x', 'y', 'z')), tuple(
        getattr(desired, n) for n in ('w', 'x', 'y', 'z'))
    dot = sum(a*b for a, b in zip(start, end))
    if dot < 0:
        end, dot = tuple(-value for value in end), -dot
    half_angle = math.acos(min(1., max(-1., dot)))
    if half_angle < 1e-10 or maximum_angle_rad >= 2 * half_angle:
        return desired
    fraction = maximum_angle_rad / (2 * half_angle)
    if dot > .9995:
        result = tuple(a + fraction * (b-a) for a, b in zip(start, end))
    else:
        denominator = math.sin(half_angle)
        first = math.sin((1-fraction) * half_angle) / denominator
        second = math.sin(fraction * half_angle) / denominator
        result = tuple(first*a + second*b for a, b in zip(start, end))
    magnitude = math.hypot(*result)
    return Quaternion(*(value / magnitude for value in result))


class IdealStabilizedGimbal:
    """World pointing / finite-point lock; no optical detector or aircraft actions."""

    def __init__(self, settings: IdealGimbalSettings):
        if not isinstance(settings, IdealGimbalSettings):
            raise ValueError('gimbal_model_configuration_invalid')
        self.settings = settings
        self.tracking_state = TrackingState.DISABLED
        self.target_ned = None
        self._aim = Vector3(1., 0., 0.)
        self._heading = 0.
        self._previous = None
        self._manual = None

    def aim(self, azimuth_deg, elevation_deg):
        self._aim = _direction(azimuth_deg, elevation_deg)
        self.target_ned = None
        self.tracking_state = TrackingState.DISABLED
        self._manual = None

    def lock_point(self, target_ned: Vector3):
        if not isinstance(target_ned, Vector3):
            raise ValueError('gimbal_target_invalid')
        if self._previous is None:
            raise ValueError('gimbal_pose_unavailable')
        if math.dist((target_ned.x, target_ned.y, target_ned.z),
                     (self._previous.camera_position_ned.x, self._previous.camera_position_ned.y,
                      self._previous.camera_position_ned.z)) < .01:
            raise ValueError('gimbal_target_coincident')
        self.target_ned = target_ned
        self.tracking_state = TrackingState.TARGET_SELECTION
        self._manual = None

    def manual(self, axis, value, maximum_speed_deg_s):
        if (axis not in ('pan', 'tilt') or isinstance(value, bool)
                or not -1 <= finite_number(value, 'gimbal_manual_value') <= 1
                or not 0 < finite_number(maximum_speed_deg_s, 'gimbal_manual_speed') <= self.settings.pointing_rate_deg_s):
            raise ValueError('gimbal_manual_intent_invalid')
        if self.target_ned is not None:
            raise ValueError('gimbal_manual_requires_tracking_release')
        self._manual = (axis, value * maximum_speed_deg_s) if value else None

    def stop_manual(self):
        self._manual = None
        if self.target_ned is None and self._previous is not None:
            self._aim = self._previous.direction_ned

    def lose_target(self):
        if self.target_ned is None:
            raise ValueError('gimbal_target_unavailable')
        self.tracking_state = TrackingState.TARGET_LOST

    def release_target(self):
        if self._previous is not None:
            self._aim = self._previous.direction_ned
        self.target_ned = None
        self.tracking_state = TrackingState.DISABLED
        self._manual = None

    def observe(self, pose: ObservedGimbalPose):
        if not isinstance(pose, ObservedGimbalPose):
            raise ValueError('gimbal_pose_invalid')
        previous = self._previous
        if previous is not None:
            if pose.timestamp_us == previous.timestamp_us:
                if pose != previous:
                    raise ValueError('gimbal_pose_rewritten')
                return None
            dt = (pose.timestamp_us - previous.timestamp_us) * 1e-6
            if (not 0 < dt <= self.settings.maximum_pose_gap_s
                    or pose.received_at_monotonic_s <= previous.received_at_monotonic_s):
                raise ValueError('gimbal_pose_progress_invalid')
        else:
            dt = 0.
        offset = pose.body_to_ned.rotate(self.settings.camera_offset_body_frd_m)
        position = Vector3(pose.body_position_ned.x + offset.x, pose.body_position_ned.y + offset.y,
                           pose.body_position_ned.z + offset.z)
        direction = self._aim
        if self._manual is not None:
            ray = pose.direction_ned
            bearing = math.degrees(math.atan2(ray.y, ray.x))
            elevation = -math.degrees(math.atan2(ray.z, ray.horizontal_magnitude))
            axis, rate = self._manual
            if axis == 'pan':
                bearing += rate * dt
            else:
                elevation = min(90., max(-90., elevation + rate * dt))
            direction = self._aim = _direction(bearing, elevation)
        if self.target_ned is not None and self.tracking_state in (
                TrackingState.TARGET_SELECTION, TrackingState.TRACKING_ACTIVE):
            ray = Vector3(self.target_ned.x - pose.camera_position_ned.x,
                self.target_ned.y - pose.camera_position_ned.y, self.target_ned.z - pose.camera_position_ned.z)
            if ray.magnitude < .01:
                self.tracking_state = TrackingState.TARGET_LOST
                direction = pose.direction_ned
            else:
                direction = ray.normalized()
                dot = sum(a*b for a, b in zip(
                    (direction.x, direction.y, direction.z),
                    (pose.direction_ned.x, pose.direction_ned.y, pose.direction_ned.z)))
                if math.degrees(math.acos(min(1., max(-1., dot)))) <= self.settings.acquisition_tolerance_deg:
                    self.tracking_state = TrackingState.TRACKING_ACTIVE
        elif self.tracking_state is TrackingState.TARGET_LOST:
            # Lost lock reports loss; it does not secretly continue perfect target tracking.
            direction = previous.direction_ned if previous is not None else pose.direction_ned
        desired, self._heading = _pointing_quaternion(direction, retained_heading_rad=self._heading)
        orientation = _limited_rotation(pose.camera_to_ned, desired,
            math.radians(self.settings.pointing_rate_deg_s) * dt)
        self._previous = pose
        return CameraPoseIntent(position, orientation, pose.timestamp_us)
