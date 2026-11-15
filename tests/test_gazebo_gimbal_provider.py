"""Renderer contracts use synthetic fixtures, not claims of actual Gazebo flight."""

from dataclasses import replace
import json
import math
import socket
from types import SimpleNamespace

import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.gazebo_gimbal_source import GazeboGimbalPacket
from classes.gimbal_interface import GimbalInterface
from tools.gazebo_gimbal_model import ObservedGimbalPose
from tools.gazebo_gimbal_provider import RenderedGimbalSource, atomic_json, send_latest_packets


@pytest.fixture
def source(tmp_path):
    tmp_path.chmod(0o700)
    return RenderedGimbalSource(dict(world='training', source_clock_id='clock', aircraft_model='quad_0',
        gimbal_config=dict(PROVIDER='topotek_sip_udp', MOUNT_TYPE='VERTICAL'),
        camera_mount=dict(frame='base_link_flu', pose=[0.,0.,0.,0.,0.,0.]),
        articulated_geometry=dict(body_link='base_link',camera_link='camera_link',
            sensor_pose_link_flu=[0.,0.,0.,0.,0.,0.], limits_rad=[[-10.,10.],[-1.,1.],[-3.,3.]],
            joint_names=['yaw_joint','roll_joint','pitch_joint'])), tmp_path, clock=lambda: 100.)


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
        ('lock', {'range_m': 25.}, 'TARGET_SELECTION'), ('lost', {}, 'TARGET_LOST'), ('release', {}, 'DISABLED')], 1):
        command(source, operation, **fields)
        source.process(replace(pose(), timestamp_us=1_000_000 + index*100_000, received_at_monotonic_s=100. + index*.1))
        value = json.loads((source.private / 'operator-state.json').read_text())
        assert value['tracking_state'] == expected
        assert value['mechanics_qualified'] is False


def test_telemetry_is_bounded_without_reducing_pose_processing(source):
    source.process(pose())
    first = source.pending_packets
    source.pending_packets = None
    source.process(replace(pose(), timestamp_us=1_004_000, received_at_monotonic_s=100.004))
    assert source.pending_packets is None
    assert source.latest_pose.timestamp_us == 1_004_000
    source.process(replace(pose(), timestamp_us=1_024_000, received_at_monotonic_s=100.024))
    assert source.pending_packets != first
    assert GazeboGimbalPacket.decode(source.pending_packets[0]).source_sample.timestamp_us == 1_024_000
    source.pending_packets = None
    command(source, 'lock', range_m=40.)
    source.process(replace(pose(), timestamp_us=1_028_000, received_at_monotonic_s=100.028))
    assert source.pending_packets is not None  # State changes are immediate.


def test_slow_telemetry_consumer_drops_samples_without_disconnect():
    sender, receiver = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    with sender, receiver:
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        sender.setblocking(False)
        receiver.setblocking(False)
        while send_latest_packets(sender, (b'old' * 100,)):
            pass
        assert send_latest_packets(sender, (b'dropped',)) == 0
        while True:
            try:
                receiver.recv(4096)
            except BlockingIOError:
                break
        assert send_latest_packets(sender, (b'fresh',)) == 1
        assert receiver.recv(4096) == b'fresh'


@pytest.mark.parametrize('observation_hz', [5, 10, 20, 60, 250])
def test_rate_changes_preserve_measured_time_and_bounded_delivery(source, observation_hz):
    delivered = []
    for index in range(observation_hz + 1):
        timestamp = 1_000_000 + round(index * 1_000_000 / observation_hz)
        observation = replace(pose(), timestamp_us=timestamp,
            received_at_monotonic_s=100. + index / observation_hz)
        source.process(observation)
        if source.pending_packets:
            packet = GazeboGimbalPacket.decode(source.pending_packets[0])
            assert packet.source_sample.timestamp_us == observation.timestamp_us
            assert packet.received_at_monotonic_s == observation.received_at_monotonic_s
            delivered.append(packet)
            source.pending_packets = None
    assert 2 <= len(delivered) <= min(observation_hz + 1, 51)
    assert source.latest_pose.timestamp_us == 2_000_000
    assert source.model.pose_gaps == 0
