# tests/unit/trackers/test_gimbal_provider.py
"""Tests for the gimbal input provider contract and factory."""

import os
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.gimbal_provider import (
    SipUdpGimbalProvider,
    UnknownGimbalProviderError,
    canonicalize_gimbal_provider,
    create_gimbal_provider,
    list_supported_gimbal_providers,
)
from classes.gimbal_types import CoordinateSystem


def test_supported_provider_list_is_canonical():
    assert list_supported_gimbal_providers() == ["topotek_sip_udp"]


@pytest.mark.parametrize(
    "alias",
    ["topotek_sip_udp", "sip_udp", "topotek", "topotek_sip", " TOPOTEK "],
)
def test_provider_aliases_resolve_to_topotek_sip(alias):
    assert canonicalize_gimbal_provider(alias) == "topotek_sip_udp"


def test_unknown_provider_fails_closed():
    with pytest.raises(UnknownGimbalProviderError):
        canonicalize_gimbal_provider("mavlink_gimbal_v2")


def test_factory_creates_topotek_sip_provider_without_starting_network_io():
    provider = create_gimbal_provider(
        {
            "PROVIDER": "topotek_sip_udp",
            "LISTEN_PORT": 19004,
            "UDP_HOST": "127.0.0.1",
            "UDP_PORT": 19003,
            "CONNECTION_TIMEOUT": 3.5,
        }
    )

    assert isinstance(provider, SipUdpGimbalProvider)
    assert provider.listen_port == 19004
    assert provider.gimbal_ip == "127.0.0.1"
    assert provider.control_port == 19003
    assert provider.DATA_FRESHNESS_TIMEOUT == 3.5
    assert provider.running is False


def test_provider_metadata_names_protocol_and_packet_families():
    provider = create_gimbal_provider(
        {
            "PROVIDER": "topotek_sip_udp",
            "LISTEN_PORT": 19004,
            "UDP_HOST": "127.0.0.1",
            "UDP_PORT": 19003,
        }
    )

    metadata = provider.get_provider_metadata()

    assert metadata["provider"] == "topotek_sip_udp"
    assert metadata["protocol"] == "topotek_sip_udp"
    assert metadata["transport"] == "udp"
    assert metadata["packet_families"] == ["GAC", "GIC", "TRC", "OFT"]


def test_topotek_provider_validates_normalized_angle_ranges():
    provider = create_gimbal_provider(
        {
            "PROVIDER": "topotek_sip_udp",
            "LISTEN_PORT": 19004,
            "UDP_HOST": "127.0.0.1",
            "UDP_PORT": 19003,
        }
    )

    valid_edge = provider._parse_hex_angles_direct(
        "465000000000",
        CoordinateSystem.GIMBAL_BODY,
    )
    out_of_range = provider._parse_hex_angles_direct(
        "465100000000",
        CoordinateSystem.GIMBAL_BODY,
    )

    assert valid_edge is not None
    assert valid_edge.yaw == 180.0
    assert out_of_range is None


def test_provider_health_reports_emergency_hold_without_fresh_data():
    provider = create_gimbal_provider(
        {
            "PROVIDER": "topotek_sip_udp",
            "LISTEN_PORT": 19004,
            "UDP_HOST": "127.0.0.1",
            "UDP_PORT": 19003,
            "CONNECTION_TIMEOUT": 2.0,
        }
    )

    health = provider.get_health_status()

    assert health["status"] == "disconnected"
    assert health["is_fresh"] is False
    assert health["connection_status"] == "disconnected"
    assert health["recommendation"] == "emergency_hold"
    assert health["is_tracking_active"] is False
