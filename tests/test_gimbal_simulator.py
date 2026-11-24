"""Production-parser parity for the isolated angle stimulus, not camera mechanics."""
import math
import socket

import pytest

from classes.gimbal_geometry import body_bearing_to_angles, body_line_of_sight, resolve_angle_geometry
from classes.gimbal_interface import GimbalInterface
from classes.gimbal_types import TrackingState
from tools.gimbal_simulator import GimbalSimulator, SimulatorConfig, angle_hex


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('azimuth,depression', [(0., 0.), (25., -30.), (-75., 45.), (180., 90.), (-180., -90.)])
def test_aim_round_trips_through_the_canonical_geometry(mount, azimuth, depression):
    geometry = resolve_angle_geometry({}, mount)
    angles = body_bearing_to_angles(azimuth, depression, geometry)
    c, a, d = math.cos(math.radians(depression)), math.radians(azimuth), math.radians(depression)
    assert body_line_of_sight(angles, mount, geometry) == pytest.approx((c*math.cos(a), c*math.sin(a), math.sin(d)))


def test_vertical_center_is_the_existing_measured_forward_preset():
    assert body_bearing_to_angles(0., 0., resolve_angle_geometry({}, 'VERTICAL')) == (0., 90., 0.)


def test_inverse_respects_expert_axes_signs_offsets_and_retains_the_unused_channel():
    geometry = resolve_angle_geometry({'GEOMETRY_OVERRIDE': {
        'AZIMUTH_AXIS': 'PITCH', 'AZIMUTH_SIGN': 'NEGATIVE', 'AZIMUTH_ZERO_ADJUST_DEG': 10.,
        'DEPRESSION_AXIS': 'YAW', 'DEPRESSION_SIGN': 'POSITIVE', 'DEPRESSION_ZERO_ADJUST_DEG': 5.,
    }}, 'HORIZONTAL')
    angles = body_bearing_to_angles(20., 30., geometry, reference_angles=(0., 0., 7.))
    assert angles == (35., -10., 7.)
    assert body_line_of_sight(angles, 'HORIZONTAL', geometry) == pytest.approx((
        math.cos(math.radians(30.))*math.cos(math.radians(20.)),
        math.cos(math.radians(30.))*math.sin(math.radians(20.)), .5))


def test_encoder_matches_retained_hardware_packets_and_real_parser():
    peer = GimbalSimulator()
    peer.set_gimbal_angles(2.9, 3.62, 5.91)
    peer.set_tracking_state(TrackingState.TRACKING_ACTIVE)
    angle, status = peer._packets()
    assert angle == b'#tpGPCrGAC0122016A024F97'
    assert status == b'#TPDP2rTRC024A'
    parsed = GimbalInterface()._parse_gimbal_packet(angle)
    assert parsed.angles.to_tuple() == (2.9, 3.62, 5.91)
    assert GimbalInterface()._parse_gimbal_packet(status).tracking_status.state is TrackingState.TRACKING_ACTIVE


def test_queries_use_production_addresses_checksum_and_independent_freeze():
    peer, interface = GimbalSimulator(), GimbalInterface()
    angle_query = interface._build_command('G', 'r', 'GAC')
    status_query = interface._build_command('D', 'r', 'TRC')
    assert peer._process_command(angle_query) == peer._packets()[0]
    assert peer._process_command(status_query) == peer._packets()[1]
    assert peer._process_command(angle_query[:-2] + '00') is None
    assert peer._process_command(interface._build_command('G', 'r', 'GIC')) is None
    assert peer._process_command(b'\xff\x00') is None
    peer.freeze(angles=True)
    assert peer._process_command(angle_query) is None
    assert peer._process_command(status_query) is not None
    peer.freeze(status=True)
    assert peer._process_command(angle_query) is not None
    assert peer._process_command(status_query) is None


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -181., 181., True, '1'])
def test_invalid_angles_are_rejected_without_partial_update(value):
    peer = GimbalSimulator()
    before = peer.get_state()
    with pytest.raises(ValueError):
        peer.set_gimbal_angles(1., value, 0.)
    assert peer.get_state() == before
    with pytest.raises(ValueError):
        angle_hex(value)


def test_local_udp_feed_decodes_and_stop_joins_the_only_worker():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(('127.0.0.1', 0))
        receiver.settimeout(1.)
        peer = GimbalSimulator(SimulatorConfig(listen_port=0, broadcast_port=receiver.getsockname()[1],
            angle_period_s=.02, status_period_s=.03))
        peer.start()
        peer.set_gimbal_angles(-1., 90., -.5)
        parser, seen = GimbalInterface(), set()
        try:
            for _ in range(20):
                packet, address = receiver.recvfrom(4096)
                data = parser._parse_gimbal_packet(packet, source_ip=None)
                assert data is not None
                assert address[0] == '127.0.0.1'
                if data.angles is not None and data.angles.to_tuple() == (-1., 90., -.5):
                    seen.add('angles')
                if data.tracking_status is not None:
                    seen.add('status')
                if len(seen) == 2:
                    break
            assert seen == {'angles', 'status'}
        finally:
            peer.stop()
        assert not peer.running and peer._thread is None
