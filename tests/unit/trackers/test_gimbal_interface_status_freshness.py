# tests/unit/trackers/test_gimbal_interface_status_freshness.py
"""Safety tests for Topotek SIP status freshness handling."""

import os
import sys
import time


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.gimbal_interface import GimbalInterface
from classes.gimbal_types import TrackingState


def test_angle_packets_do_not_reuse_stale_tracking_active_status():
    interface = GimbalInterface(connection_timeout=2.0)

    status_packet = interface._parse_gimbal_packet("#tpUD2rTRC02FF")
    assert status_packet.tracking_status.state == TrackingState.TRACKING_ACTIVE

    interface.last_tracking_update_time = (
        time.time() - interface.TRACKING_STATUS_FRESHNESS_TIMEOUT - 0.1
    )

    angle_packet = interface._parse_gimbal_packet("#tpUG2rGAC000000000000FF")

    assert angle_packet.angles is not None
    assert angle_packet.tracking_status is None


def test_angle_packets_can_include_fresh_tracking_active_status():
    interface = GimbalInterface(connection_timeout=2.0)

    status_packet = interface._parse_gimbal_packet("#tpUD2rTRC02FF")
    assert status_packet.tracking_status.state == TrackingState.TRACKING_ACTIVE

    angle_packet = interface._parse_gimbal_packet("#tpUG2rGAC000000000000FF")

    assert angle_packet.angles is not None
    assert angle_packet.tracking_status.state == TrackingState.TRACKING_ACTIVE
