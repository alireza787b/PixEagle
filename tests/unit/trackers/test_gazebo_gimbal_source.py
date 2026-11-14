"""Private simulator input retains source receipts; ordinary UDP is unchanged."""

from dataclasses import asdict, replace
import json
import socket
import time
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from classes.capture_timing import SourceSampleStamp
from classes.gazebo_gimbal_source import (
    GazeboGimbalPacket, GazeboGimbalSettings, GazeboSipGimbalProvider, validate_gazebo_gimbal_config,
)
from classes.gimbal_interface import GimbalSourceError, ReceivedGimbalPacket
from classes.gimbal_provider import SipUdpGimbalProvider, create_gimbal_provider
from classes.gimbal_types import CameraObservationSource, GimbalAngleObservation


ANGLE = '#tpGPCrGAC0122016A024F97'
ACTIVE = '#TPDP2rTRC024A'


@pytest.fixture
def source():
    settings = GazeboGimbalSettings('/tmp/private-gimbal.sock', 'world-clock', 'training', .05)
    provider = GazeboSipGimbalProvider(settings)
    listener, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    listener.settimeout(.1)
    provider.listen_socket = listener
    try:
        yield provider, sender
    finally:
        listener.close()
        sender.close()


def packet(*, sequence=1, stamp=1_000_000, frame=ANGLE, receipt=None):
    return GazeboGimbalPacket('training',
        SourceSampleStamp('world-clock', 'producer-1', sequence, stamp, 'gazebo_sim_us'),
        time.monotonic() if receipt is None else receipt, frame)


def ingest(source, value):
    provider, sender = source
    sender.send(value.encode())
    received = provider._receive_packet()
    parsed = provider._parse_gimbal_packet(received.data, source_ip=received.source_ip)
    with provider.lock:
        return provider._ingest_parsed_data_locked(parsed, parsed.raw_packet, received=received)


def test_source_stamp_survives_parser_and_independent_status(source):
    original = packet()
    data = ingest(source, original)
    assert data.angles.to_tuple() == (2.9, 3.62, 5.91)
    assert data.source_sample == original.source_sample
    assert data.angle_sample_monotonic == original.received_at_monotonic_s
    status = packet(sequence=2, frame=ACTIVE)
    combined = ingest(source, status)
    assert combined.tracking_status.is_tracking_active()
    assert combined.tracking_sample_monotonic == status.received_at_monotonic_s
    assert combined.source_sample == original.source_sample
    assert combined.angle_sample_monotonic == original.received_at_monotonic_s
    assert combined.angle_sample_sequence == data.angle_sample_sequence


def test_queued_packets_are_not_restamped_fresh_at_ingestion(source):
    old = packet(receipt=time.monotonic() - 3.)
    assert ingest(source, old) is None
    data = ingest(source, packet(sequence=2, stamp=2_000_000, frame=ACTIVE))
    assert data.angles is None and data.source_sample is None
    assert data.tracking_status.is_tracking_active()


@pytest.mark.parametrize('mutation', [
    lambda p: replace(p, world='another-world'),
    lambda p: replace(p, received_at_monotonic_s=time.monotonic() + 2.),
    lambda p: replace(p, source_sample=replace(p.source_sample, clock_id='other-clock')),
    lambda p: replace(p, source_sample=replace(p.source_sample, source_incarnation='new-producer')),
    lambda p: replace(p, source_sample=replace(p.source_sample, sequence=1)),
    lambda p: replace(p, source_sample=replace(p.source_sample, timestamp_us=900_000)),
    lambda p: replace(p, source_sample=replace(p.source_sample, timestamp_us=1_000_000)),
    lambda p: replace(p, sip_frame=ANGLE[:-2] + '00'),
])
def test_identity_clock_reorder_and_protocol_failure_retire_input(source, mutation):
    ingest(source, packet())
    source[1].send(mutation(packet(sequence=2, stamp=2_000_000)).encode())
    with pytest.raises(GimbalSourceError):
        source[0]._receive_packet()


def test_terminal_disconnect_clears_observations_and_notifies_owner(source):
    provider, sender = source
    ingest(source, packet())
    events = []
    provider.set_lifecycle_observer(lambda event, token: events.append(event))
    sender.close()
    provider.running = True
    provider._listener_loop()
    assert not provider.running
    assert provider.get_current_data() is None
    assert provider.get_connection_status() == 'error'
    assert events == ['stopping']


def test_truncated_envelope_is_terminal(source):
    source[1].send(b' ' * 4097)
    with pytest.raises(GimbalSourceError, match='truncated'):
        source[0]._receive_packet()


def test_normal_udp_factory_does_not_gain_source_time_or_simulated_controls():
    provider = create_gimbal_provider({})
    assert type(provider) is SipUdpGimbalProvider
    parsed = provider._parse_gimbal_packet(ANGLE)
    received = ReceivedGimbalPacket(ANGLE.encode(), '127.0.0.1', time.monotonic())
    data = provider._ingest_parsed_data_locked(parsed, parsed.raw_packet, received=received)
    assert data.source_sample is None
    assert provider.get_provider_metadata()['transport'] == 'udp'


def test_factory_reuses_provider_protocol_and_rejects_manual_controls(source):
    settings = asdict(source[0].settings)
    provider = create_gimbal_provider(dict(GAZEBO_INPUT=settings))
    assert isinstance(provider, GazeboSipGimbalProvider)
    assert provider.provider_id == source[0].provider_id == 'topotek_sip_udp'
    assert provider.manual_control is None and not provider.requires_queries
    assert not provider._send_command('unused')
    assert not provider.selection_modes()
    assert provider.get_provider_metadata()['mechanics_qualified'] is False
    with pytest.raises(ValueError, match='controls_unsupported'):
        create_gimbal_provider(dict(GAZEBO_INPUT=settings, CONTROL_ENABLED=True))


@pytest.mark.parametrize('changes', [dict(socket_path='relative.sock'), dict(max_attitude_skew_s=True),
    dict(max_attitude_skew_s=0), dict(source_clock_id=''), dict(world=' world')])
def test_settings_validation_shared_by_startup_and_config(changes, source):
    value = dict(asdict(source[0].settings), **changes)
    with pytest.raises(ValueError):
        validate_gazebo_gimbal_config(dict(GAZEBO_INPUT=value))


def test_optional_stamp_round_trip_and_legacy_observation():
    original = GimbalAngleObservation(CameraObservationSource('camera', 1), 2, 'topotek_sip_udp',
        'geometry', (0., 90., 0.), 'gimbal_body', 1, 100., 'TRACKING_ACTIVE', 100.,
        source_sample=packet(receipt=100.).source_sample)
    value = json.loads(json.dumps(asdict(original)))
    assert GimbalAngleObservation.from_dict(value) == original
    value.pop('source_sample')
    assert GimbalAngleObservation.from_dict(value) == replace(original, source_sample=None)
    value['source_sample'] = dict(asdict(original.source_sample), timestamp_us=True)
    with pytest.raises(ValueError):
        GimbalAngleObservation.from_dict(value)


def test_startup_and_config_sync_preview_share_simulator_validation(source):
    from classes.config_service import ConfigService
    from classes.parameters import Parameters

    defaults = yaml.safe_load((Path(__file__).resolve().parents[3] / 'configs/config_default.yaml').read_text())
    candidate = deepcopy(defaults)
    candidate['GimbalTracker']['GAZEBO_INPUT'] = asdict(source[0].settings)
    assert ConfigService.get_instance().validate_config_mapping(candidate).valid
    Parameters._validate_dependent_config(candidate, strict=True)
    candidate['GimbalTracker']['CONTROL_ENABLED'] = True
    result = ConfigService.get_instance().validate_config_mapping(candidate)
    assert not result.valid and any('controls_unsupported' in message for message in result.errors)
    with pytest.raises(RuntimeError, match='controls_unsupported'):
        Parameters._validate_dependent_config(candidate, strict=True)
