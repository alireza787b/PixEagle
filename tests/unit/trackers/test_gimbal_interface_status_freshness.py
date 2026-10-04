# tests/unit/trackers/test_gimbal_interface_status_freshness.py
"""Safety tests for Topotek SIP status freshness handling."""

import os
import sys
import time


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.gimbal_interface import GimbalInterface
from classes.gimbal_types import TrackingState


STATUS_PACKET = "#TPDP2rTRC024A"
ANGLE_PACKET = "#tpGPCrGAC0000000000005E"


def _ingest(interface, packet):
    parsed = interface._parse_gimbal_packet(packet)
    assert parsed is not None
    with interface.lock:
        return interface._ingest_parsed_data_locked(parsed, packet)


def test_interleaved_packets_compose_one_fresh_snapshot():
    interface = GimbalInterface(
        connection_timeout=2.0,
        tracking_status_timeout=2.0,
    )

    status_only = _ingest(interface, STATUS_PACKET)
    assert status_only.angles is None
    assert status_only.tracking_status.state == TrackingState.TRACKING_ACTIVE

    coherent = _ingest(interface, ANGLE_PACKET)

    assert coherent.angles is not None
    assert coherent.tracking_status.state == TrackingState.TRACKING_ACTIVE


def test_packet_parser_does_not_mutate_provider_state_before_ingest():
    interface = GimbalInterface()

    parsed = interface._parse_gimbal_packet(STATUS_PACKET)

    assert parsed is not None
    assert parsed.tracking_status.state == TrackingState.TRACKING_ACTIVE
    assert interface.current_tracking_status is None
    assert interface.last_tracking_update_time is None


def test_status_only_packet_does_not_evict_fresh_angles():
    interface = GimbalInterface(
        connection_timeout=2.0,
        tracking_status_timeout=2.0,
    )

    _ingest(interface, ANGLE_PACKET)
    coherent = _ingest(interface, STATUS_PACKET)

    assert coherent.angles is not None
    assert coherent.tracking_status.state == TrackingState.TRACKING_ACTIVE


def test_angle_packet_does_not_refresh_stale_tracking_status():
    interface = GimbalInterface(
        connection_timeout=2.0,
        tracking_status_timeout=1.0,
    )

    _ingest(interface, STATUS_PACKET)
    interface.last_tracking_update_time = (
        time.time() - interface.TRACKING_STATUS_FRESHNESS_TIMEOUT - 0.1
    )
    angle_only = _ingest(interface, ANGLE_PACKET)

    assert angle_only.angles is not None
    assert angle_only.tracking_status is None


def test_status_packet_does_not_refresh_stale_angles():
    interface = GimbalInterface(
        connection_timeout=1.0,
        tracking_status_timeout=2.0,
    )

    _ingest(interface, ANGLE_PACKET)
    interface.last_data_time = (
        time.time() - interface.DATA_FRESHNESS_TIMEOUT - 0.1
    )
    status_only = _ingest(interface, STATUS_PACKET)

    assert status_only.angles is None
    assert status_only.tracking_status.state == TrackingState.TRACKING_ACTIVE


def test_status_and_snapshot_processing_cannot_refresh_angle_receipt(monkeypatch):
    interface = GimbalInterface()
    now = [100.0]
    monkeypatch.setattr('classes.gimbal_interface.time.monotonic', lambda: now[0])
    first = _ingest(interface, ANGLE_PACKET)
    receipt = first.angles.timestamp
    now[0] += 0.2
    next_data = _ingest(interface, STATUS_PACKET)
    assert next_data.angles.timestamp == receipt
    assert next_data.angle_sample_sequence == first.angle_sample_sequence == 1
    assert next_data.angle_sample_monotonic == 100.0
    assert next_data.tracking_sample_monotonic == 100.2
    snapshot = interface.get_current_data()
    assert snapshot.angle_sample_sequence == 1
    assert snapshot.angle_sample_monotonic == 100.0
    now[0] += 0.2
    renewed = _ingest(interface, ANGLE_PACKET)
    assert renewed.angle_sample_sequence == 2
    assert renewed.angle_sample_monotonic == 100.4


def test_backward_wall_clock_cannot_keep_expired_angles_live(monkeypatch):
    interface = GimbalInterface(connection_timeout=1.0)
    mono = [100.0]
    wall = [1000.0]
    monkeypatch.setattr('classes.gimbal_interface.time.monotonic', lambda: mono[0])
    monkeypatch.setattr('classes.gimbal_interface.time.time', lambda: wall[0])
    _ingest(interface, ANGLE_PACKET)
    mono[0] = 102.0
    wall[0] = 999.0
    assert interface.get_current_data() is None
