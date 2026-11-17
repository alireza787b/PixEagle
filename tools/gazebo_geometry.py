"""Gazebo ENU/FLU boundary, shared by camera instrumentation and observations."""

from dataclasses import dataclass
import math

from classes.aircraft_state import Quaternion, Vector3


ENU_TO_NED = Quaternion(0., math.sqrt(.5), math.sqrt(.5), 0.)
FLU_TO_FRD = Quaternion(0., 1., 0., 0.)


@dataclass(frozen=True)
class RigidPose:
    position: Vector3
    rotation: Quaternion

    @classmethod
    def from_message(cls, value):
        p, q = value.position, value.orientation
        return cls(Vector3(p.x, p.y, p.z), Quaternion(q.w, q.x, q.y, q.z))

    @classmethod
    def from_sdf(cls, pose):
        if len(pose) != 6:
            raise ValueError('gazebo_extrinsic_pose_invalid')
        return cls(Vector3(*pose[:3]), Quaternion.from_euler(*pose[3:]))

    def compose(self, other):
        offset = self.rotation.rotate(other.position)
        p = self.position
        return RigidPose(Vector3(p.x+offset.x, p.y+offset.y, p.z+offset.z), self.rotation.compose(other.rotation))

    def ned_frd(self):
        p = self.position
        return Vector3(p.y, p.x, -p.z), ENU_TO_NED.compose(self.rotation).compose(FLU_TO_FRD)


def acquisition_us(header):
    stamp = header.stamp
    if stamp.sec < 0 or not 0 <= stamp.nsec < 1_000_000_000:
        raise ValueError('gazebo_pose_stamp_invalid')
    return stamp.sec*1_000_000 + stamp.nsec//1000
