"""Renderer contracts use synthetic fixtures, not claims of actual Gazebo flight."""

from dataclasses import replace
import json
import math
from types import SimpleNamespace

import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.gazebo_gimbal_source import GazeboGimbalPacket
from classes.gimbal_interface import GimbalInterface
from tools.gazebo_gimbal_model import ObservedGimbalPose
from tools.gazebo_gimbal_provider import RenderedGimbalSource, atomic_json, observed_pose, pose_request


@pytest.fixture
def source(tmp_path):
    tmp_path.chmod(0o700)
    return RenderedGimbalSource(dict(world='training', source_clock_id='clock', aircraft_model='quad_0',
        gimbal_config=dict(PROVIDER='topotek_sip_udp', MOUNT_TYPE='VERTICAL'),
        instrumentation_camera=dict(instance='test_camera', offset_body_frd_m=[0., 0., -.34],
            pointing_rate_deg_s=90., maximum_pose_gap_s=.25)), tmp_path, clock=lambda: 100.)


def pose():
    return ObservedGimbalPose(1_000_000, 100., Vector3(0., 0., -20.), Quaternion(1., 0., 0., 0.),
        Vector3(0., 0., -20.34), Quaternion(1., 0., 0., 0.))


def command(source, operation, **fields):
    value = dict(incarnation=source.incarnation, sequence=source.control_sequence + 1, operation=operation, **fields)
    atomic_json(source.private / 'operator-command.json', value)
    return value


def test_packets_encode_observed_camera_not_requested_rotation(source):
    source.process(pose())
    command(source, 'aim', azimuth_deg=90., elevation_deg=-45.)
    observation = replace(pose(), timestamp_us=1_100_000, received_at_monotonic_s=100.1)
    intent = source.process(observation)
    assert intent is not None
    # The camera has not moved in feedback. Both the wire angles and their stamp
    # must remain tied to that original measured pose, despite a new aim request.
    angle, status = [GazeboGimbalPacket.decode(raw) for raw in source.pending_packets]
    decoded = GimbalInterface()._parse_gimbal_packet(angle.sip_frame)
    assert decoded.angles.to_tuple() == (0., 90., 0.)
    assert angle.source_sample.timestamp_us == observation.timestamp_us
    assert angle.received_at_monotonic_s == observation.received_at_monotonic_s
    assert angle.source_sample.sequence < status.source_sample.sequence
    assert status.sip_frame == '#TPDP2rTRC0048'


def test_finite_lock_is_based_on_current_observed_aim_and_never_replayed(source):
    source.process(pose())
    current = replace(pose(), timestamp_us=1_100_000, received_at_monotonic_s=100.1)
    original = command(source, 'lock', range_m=40.)
    source.process(current)
    assert source.model.target_ned == Vector3(40., 0., -20.34)
    assert source.control_sequence == 1
    # Same unchanged operator file does not redefine the point after translation.
    source.process(replace(current, timestamp_us=1_200_000, received_at_monotonic_s=100.2,
        camera_position_ned=Vector3(10., 0., -20.)))
    assert source.model.target_ned == Vector3(40., 0., -20.34)
    # A new producer never consumes an old producer's lock file.
    new = RenderedGimbalSource(source.config, source.private)
    new.process(pose())
    assert new.control_sequence == 0 and new.model.target_ned is None
    assert json.loads((source.private / 'operator-command.json').read_text()) == original


@pytest.mark.parametrize('mutation', ['rewrite', 'gap', 'nan', 'unsupported', 'range'])
def test_invalid_operator_input_cannot_become_tracking(source, mutation):
    source.process(pose())
    value = command(source, 'aim', azimuth_deg=5., elevation_deg=-5.)
    source.process(replace(pose(), timestamp_us=1_100_000, received_at_monotonic_s=100.1))
    if mutation == 'rewrite': value['azimuth_deg'] = 10.
    if mutation == 'gap': value['sequence'] = 3
    if mutation == 'nan': value.update(sequence=2, elevation_deg=float('nan'))
    if mutation == 'unsupported': value = dict(incarnation=source.incarnation, sequence=2, operation='follow_start')
    if mutation == 'range': value = dict(incarnation=source.incarnation, sequence=2, operation='lock', range_m=-1.)
    (source.private / 'operator-command.json').write_text(json.dumps(value))
    source.process(replace(pose(), timestamp_us=1_200_000, received_at_monotonic_s=100.2))
    assert source.control_error and source.control_sequence == 1
    assert source.model.target_ned is None
    assert source.pending_packets is not None  # Live observed camera data survives bad UI input.


def test_loss_and_release_are_explicit_source_states_without_aircraft_actions(source):
    source.process(pose())
    for index, (operation, fields, expected) in enumerate([
        ('lock', {'range_m': 25.}, 'TRACKING_ACTIVE'), ('lost', {}, 'TARGET_LOST'), ('release', {}, 'DISABLED')], 1):
        command(source, operation, **fields)
        source.process(replace(pose(), timestamp_us=1_000_000 + index*100_000, received_at_monotonic_s=100. + index*.1))
        value = json.loads((source.private / 'operator-state.json').read_text())
        assert value['tracking_state'] == expected
        assert value['mechanics_qualified'] is False


def protobuf_pose(name, xyz, q, identifier):
    return SimpleNamespace(name=name, id=identifier,
        position=SimpleNamespace(**dict(zip(('x', 'y', 'z'), xyz))),
        orientation=SimpleNamespace(**dict(zip(('w', 'x', 'y', 'z'), q))))


def test_world_frame_roundtrip_has_no_airframe_or_mount_specific_rotation():
    body = protobuf_pose('quad_0', (2., 3., 4.), (1., 0., 0., 0.), 10)
    camera = protobuf_pose('camera', (2., 3., 5.), (math.cos(.2), 0., 0., math.sin(.2)), 20)
    message = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nsec=123_000_000)), pose=[body, camera])
    observed, identifier = observed_pose(message, aircraft_model='quad_0', camera_model='camera', received_at=100.)
    assert identifier == 20 and observed.timestamp_us == 1_123_000
    assert observed.body_position_ned == Vector3(3., 2., -4.)
    assert observed.camera_position_ned == Vector3(3., 2., -5.)
    # Supply intent equal to observation to isolate the conversion boundary.
    from tools.gazebo_gimbal_model import CameraPoseIntent
    intent = CameraPoseIntent(observed.camera_position_ned, observed.camera_to_ned, observed.timestamp_us)

    class Pose:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.position = SimpleNamespace()
            self.orientation = SimpleNamespace()

    request = pose_request(intent, camera_model='camera', camera_id=identifier, message_type=Pose)
    q = request.orientation
    assert (q.w, q.x, q.y, q.z) == pytest.approx((camera.orientation.w, 0., 0., camera.orientation.z))
    assert vars(request.position) == dict(x=2., y=3., z=5.)
    assert request.name == 'camera' and request.id == 20
