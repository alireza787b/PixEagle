"""Periodic operator logs must agree with the canonical transport snapshot."""

import logging
from types import SimpleNamespace

import pytest

from classes.app_controller import AppController
from classes.parameters import Parameters


@pytest.mark.parametrize("connected", [False, True])
def test_system_status_uses_canonical_px4_connection(connected, monkeypatch, caplog):
    app = object.__new__(AppController)
    app.smart_mode_active = False
    app.tracking_started = False
    app.segmentation_active = False
    app.following_active = False
    app.mavlink_data_manager = SimpleNamespace(connection_state="connected")
    app.px4_interface = SimpleNamespace(
        connected=False,
        get_connection_status=lambda: {"connected": connected},
    )
    monkeypatch.setattr(Parameters, "MAVLINK_ENABLED", True)
    with caplog.at_level(logging.INFO):
        app._log_system_status()
    expected = "Connected" if connected else "Disconnected"
    assert f"MAVLink: Connected | PX4: {expected}" in caplog.text
    assert "Error generating system status" not in caplog.text
