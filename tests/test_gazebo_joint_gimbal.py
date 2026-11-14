"""Declared actuator chain tests, independent from tracker/mount transforms."""

import math

import pytest
from scipy.spatial.transform import Rotation

from classes.aircraft_state import Quaternion
from tools.gazebo_joint_gimbal import ZxyJointChain, rotation_zxy


@pytest.fixture
def chain():
    return ZxyJointChain(Quaternion.from_euler(.1, .2, 3.14), Quaternion.from_euler(0., 0., 3.14),
                         ((-1e16, 1e16), (-1.6, 1.6), (-math.pi, math.pi)))


@pytest.mark.parametrize('yaw', [-8., -math.pi, -1., 0., 1., math.pi, 8.])
@pytest.mark.parametrize('roll', [-math.pi/2, -.8, 0., .8, math.pi/2])
@pytest.mark.parametrize('pitch', [-2., -.5, 0., .5, 2.])
def test_stock_chain_orientation_matches_independent_rotation_library(yaw, roll, pitch):
    q = rotation_zxy(yaw, roll, pitch)
    expected = Rotation.from_euler('ZXY', [-yaw, -roll, pitch]).as_quat()
    actual = (q.x, q.y, q.z, q.w)
    assert abs(sum(a*b for a, b in zip(actual, expected))) == pytest.approx(1.)


@pytest.mark.parametrize('joints', [(1., .3, .5), (math.pi+.01, -.5, -1.),
    (-math.pi-.01, .5, 2.), (5., math.pi/2, .6), (-5., -math.pi/2, -.5)])
def test_inverse_keeps_nearest_measured_branch_through_wrap_and_poles(chain, joints):
    target = chain.targets(chain.forward(joints), joints)
    assert target == pytest.approx(joints, abs=1e-7)


def test_outside_mechanical_limits_is_not_silently_clamped(chain):
    limited = ZxyJointChain(chain.mount_to_body_flu, chain.sensor_to_camera_link_flu,
                            ((-.1, .1), (-.1, .1), (-.1, .1)))
    with pytest.raises(ValueError, match='unreachable'):
        limited.targets(chain.forward((1., .5, .5)), (0., 0., 0.))


@pytest.fixture
def attached_message():
    from types import SimpleNamespace as N
    def pose(name, position, yaw, parent):
        q=Quaternion.from_euler(0.,0.,yaw)
        return N(name=name,position=N(x=position[0],y=position[1],z=position[2]),
            orientation=N(w=q.w,x=q.x,y=q.y,z=q.z),header=N(stamp=N(sec=3,nsec=4000),
                data=[N(key='frame_id',value=[parent])]))
    return N(pose=[pose('carrier',(10.,20.,30.),math.pi/2,'world'),
        pose('carrier::base_link',(0.,0.,.4),0.,'carrier'),
        pose('carrier::camera_link',(.75,0.,1.1),math.pi,'carrier')])


def test_attached_observation_uses_actual_link_pose_and_declared_sensor_extrinsic(attached_message):
    from tools.gazebo_joint_gimbal import attached_observation
    p=attached_observation(attached_message,aircraft_model='carrier',body_link='base_link',camera_link='camera_link',
        sensor_pose_link_flu=(-.04,0.,-.16,0.,0.,math.pi),received_at=100.)
    assert p.timestamp_us==3_000_004
    assert (p.body_position_ned.x,p.body_position_ned.y,p.body_position_ned.z)==pytest.approx((20.,10.,-30.4))
    assert (p.camera_position_ned.x,p.camera_position_ned.y,p.camera_position_ned.z)==pytest.approx((20.79,10.,-30.94))
    assert (p.direction_ned.x,p.direction_ned.y,p.direction_ned.z)==pytest.approx((1.,0.,0.))


@pytest.mark.parametrize('fault',['missing','duplicate','time','parent'])
def test_attached_observation_does_not_replace_missing_or_mismatched_links(attached_message,fault):
    from tools.gazebo_joint_gimbal import attached_observation
    if fault=='missing':attached_message.pose.pop()
    if fault=='duplicate':attached_message.pose.append(attached_message.pose[-1])
    if fault=='time':attached_message.pose[-1].header.stamp.sec=4
    if fault=='parent':attached_message.pose[-1].header.data[0].value=['other_model']
    with pytest.raises(ValueError):
        attached_observation(attached_message,aircraft_model='carrier',body_link='base_link',camera_link='camera_link',
            sensor_pose_link_flu=(-.04,0.,-.16,0.,0.,math.pi),received_at=100.)
