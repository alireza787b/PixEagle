"""Kinematics for the declared stock Gazebo ZXY gimbal, not camera guidance.

Joint targets are actuator intent only. Camera/body pose feedback remains the
source of SIP angle observations. Other mechanical chains need their own
explicit model adapter; mount/protocol conventions remain in gimbal_geometry.
"""

from dataclasses import dataclass
import math

from classes.aircraft_state import Quaternion, Vector3, finite_number
from tools.gazebo_geometry import RigidPose, acquisition_us
from tools.gazebo_gimbal_model import ObservedGimbalPose


def inverse(q):
    return Quaternion(q.w, -q.x, -q.y, -q.z)


def rotation_zxy(yaw, roll, pitch):
    """Actual stock joint axes: -Z yaw, -X roll, +Y pitch, in FLU."""
    return Quaternion.from_euler(0., 0., -yaw).compose(
        Quaternion.from_euler(-roll, 0., 0.)).compose(Quaternion.from_euler(0., pitch, 0.))


def _near(angle, reference):
    return angle + 2 * math.pi * round((reference - angle) / (2 * math.pi))


def attached_observation(message, *, aircraft_model, body_link, camera_link, sensor_pose_link_flu, received_at):
    names = (aircraft_model, aircraft_model+'::'+body_link, aircraft_model+'::'+camera_link)
    selected = {}
    for pose in message.pose:
        if pose.name in names:
            if pose.name in selected:
                raise ValueError('gimbal_attached_pose_ambiguous')
            selected[pose.name] = pose
    if len(selected) != 3:
        raise ValueError('gimbal_attached_pose_missing')
    stamps = {acquisition_us(pose.header) for pose in selected.values()}
    if len(stamps) != 1:
        raise ValueError('gimbal_attached_pose_time_mismatch')
    for name in names[1:]:
        frame = [v for item in selected[name].header.data if item.key == 'frame_id' for v in item.value]
        if frame != [aircraft_model]:
            raise ValueError('gimbal_attached_pose_parent_changed')
    world = RigidPose.from_message(selected[aircraft_model])
    body = world.compose(RigidPose.from_message(selected[names[1]]))
    camera = world.compose(RigidPose.from_message(selected[names[2]])).compose(
        RigidPose.from_sdf(sensor_pose_link_flu))
    position, orientation = body.ned_frd()
    camera_position, camera_orientation = camera.ned_frd()
    return ObservedGimbalPose(next(iter(stamps)), received_at, position, orientation, camera_position, camera_orientation)


@dataclass(frozen=True)
class ZxyJointChain:
    mount_to_body_flu: Quaternion
    sensor_to_camera_link_flu: Quaternion
    limits_rad: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]

    def __post_init__(self):
        if (not isinstance(self.mount_to_body_flu, Quaternion)
                or not isinstance(self.sensor_to_camera_link_flu, Quaternion)
                or len(self.limits_rad) != 3):
            raise ValueError('gimbal_joint_chain_invalid')
        for low, high in self.limits_rad:
            if finite_number(low, 'joint_lower_limit') >= finite_number(high, 'joint_upper_limit'):
                raise ValueError('gimbal_joint_limits_invalid')

    def forward(self, joints):
        if len(joints) != 3:
            raise ValueError('gimbal_joint_positions_invalid')
        return self.mount_to_body_flu.compose(rotation_zxy(*joints)).compose(self.sensor_to_camera_link_flu)

    def pointing_targets(self, ray_body_flu, measured_joints):
        """Constrain the optical ray, not unmeasured image-roll stabilization.

        With roll fixed, pitch solves A*sin(p)+B*cos(p)+C=ray.z;
        yaw aligns the remaining horizontal projection. Keep the nearest valid
        measured branch, trying neutral/pole-compatible roll when necessary.
        """
        measured = tuple(finite_number(v, 'measured_joint') for v in measured_joints)
        if len(measured) != 3 or not isinstance(ray_body_flu, Vector3):
            raise ValueError('gimbal_joint_target_invalid')
        ray = inverse(self.mount_to_body_flu).rotate(ray_body_flu.normalized())
        sensor = self.sensor_to_camera_link_flu.rotate(Vector3(1., 0., 0.))
        radial = math.hypot(sensor.x, sensor.z)
        if radial < 1e-9:
            raise ValueError('gimbal_sensor_axis_unsupported')
        low_roll, high_roll = self.limits_rad[1]
        rolls = (measured[1], 0., math.atan2(-ray.z * sensor.y, radial), low_roll, high_roll)
        candidates = []
        for roll in rolls:
            if not low_roll <= roll <= high_roll:
                continue
            a, b, c = -math.cos(roll)*sensor.x, math.cos(roll)*sensor.z, -math.sin(roll)*sensor.y
            amplitude = math.hypot(a, b)
            if amplitude < 1e-9 or abs(ray.z-c) > amplitude+1e-10:
                continue
            phase = math.atan2(b, a)
            angle = math.asin(min(1., max(-1., (ray.z-c)/amplitude)))
            for pitch in (angle-phase, math.pi-angle-phase):
                pitch = _near(pitch, measured[2])
                intermediate = Quaternion.from_euler(-roll, 0., 0.).compose(
                    Quaternion.from_euler(0., pitch, 0.)).rotate(sensor)
                yaw = (measured[0] if ray.horizontal_magnitude < 1e-8 else
                    _near(math.atan2(intermediate.y, intermediate.x)-math.atan2(ray.y, ray.x), measured[0]))
                target = (yaw, roll, pitch)
                if not all(low-1e-8 <= value <= high+1e-8
                           for value, (low, high) in zip(target, self.limits_rad)):
                    continue
                actual = rotation_zxy(*target).rotate(sensor)
                if math.dist((actual.x, actual.y, actual.z), (ray.x, ray.y, ray.z)) <= 1e-7:
                    candidates.append(target)
        if not candidates:
            raise ValueError('gimbal_joint_direction_unreachable')
        return min(candidates, key=lambda target: sum((a-b)**2 for a, b in zip(target, measured)))

    def targets(self, sensor_to_body_flu, measured_joints):
        if not isinstance(sensor_to_body_flu, Quaternion) or len(measured_joints) != 3:
            raise ValueError('gimbal_joint_target_invalid')
        measured = tuple(finite_number(v, 'measured_joint') for v in measured_joints)
        q = inverse(self.mount_to_body_flu).compose(sensor_to_body_flu).compose(inverse(self.sensor_to_camera_link_flu))
        x, y, z = (q.rotate(v) for v in (Vector3(1., 0., 0.), Vector3(0., 1., 0.), Vector3(0., 0., 1.)))
        b = math.asin(min(1., max(-1., y.z)))
        if math.hypot(y.x, y.y) > 1e-7:
            a, c = math.atan2(-y.x, y.y), math.atan2(-x.z, z.z)
        else:
            # At the ZXY pole, yaw/pitch are coupled. Retain measured yaw,
            # rather than choosing a new zero heading at every sample.
            a = -measured[0]
            remaining = inverse(Quaternion.from_euler(b, 0., 0.)).compose(
                inverse(Quaternion.from_euler(0., 0., a))).compose(q)
            forward = remaining.rotate(Vector3(1., 0., 0.))
            c = math.atan2(-forward.z, forward.x)
        alternatives = [(a, b, c), (a+math.pi, math.pi-b, c+math.pi)]
        candidates = []
        for angles in alternatives:
            target = tuple(_near(value, previous) for value, previous in zip(
                (-angles[0], -angles[1], angles[2]), measured))
            if not all(low-1e-8 <= value <= high+1e-8
                       for value, (low, high) in zip(target, self.limits_rad)):
                continue
            reconstructed = self.forward(target)
            alignment = abs(sum(getattr(reconstructed, name)*getattr(sensor_to_body_flu, name)
                                for name in ('w', 'x', 'y', 'z')))
            if alignment < 1.-1e-8:
                continue
            candidates.append(target)
        if not candidates:
            raise ValueError('gimbal_joint_direction_unreachable')
        return min(candidates, key=lambda target: sum((a-b)**2 for a, b in zip(target, measured)))
