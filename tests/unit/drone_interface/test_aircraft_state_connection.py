from dataclasses import replace
from dataclasses import asdict
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.px4_interface_manager import PX4InterfaceManager
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


@pytest.fixture
def connection():
    # These methods use no MAVSDK I/O. Keep their owner/connection identity real
    # while isolating the existing transport setup from observation tests.
    from classes.aircraft_state import AircraftStateOwner
    instance = PX4InterfaceManager.__new__(PX4InterfaceManager)
    instance._aircraft_state_owner = AircraftStateOwner(clock=lambda: 100.)
    instance._native_guidance_client = None
    instance._native_guidance_lock = asyncio.Lock()
    instance._telemetry_generation = 1
    instance._connection_generation = 1
    instance._aircraft_identity_revision = 0
    instance._aircraft_identity = {"autopilot_uid": "aircraft-a", "hardware_uid": None}
    instance._telemetry_connection_generation = 1
    instance.get_connection_status = lambda: {"connected": True}
    return instance


def test_connection_owns_snapshot_and_rebind_invalidates_old_source(connection):
    binding = connection.get_aircraft_state_binding()
    state = aircraft_state(binding=binding)
    assert connection.commit_aircraft_state(state)
    assert connection.get_aircraft_state() is state
    connection._advance_connection_generation()
    assert connection.get_aircraft_state() is None
    assert not connection.commit_aircraft_state(replace(state, sequence=2))


def test_new_telemetry_producer_cannot_reuse_a_prior_native_snapshot(connection):
    state = aircraft_state(binding=connection.get_aircraft_state_binding())
    assert connection.commit_aircraft_state(state)
    connection._advance_telemetry_generation(connection.connection_generation)
    assert connection.get_aircraft_state() is None
    assert not connection.commit_aircraft_state(state)


def test_identity_change_and_disconnect_cannot_relabel_retained_pose(connection):
    state = aircraft_state(binding=connection.get_aircraft_state_binding())
    assert connection.commit_aircraft_state(state)
    connection._aircraft_identity_revision += 1
    connection._aircraft_identity = {"autopilot_uid": "aircraft-b", "hardware_uid": None}
    assert connection.get_aircraft_state() is None
    assert not connection.commit_aircraft_state(state)
    connection.get_connection_status = lambda: {"connected": False}
    assert connection.get_aircraft_state_binding() is None


@pytest.mark.asyncio
async def test_native_preparation_is_observation_only_and_reconnect_revokes_its_owner(connection, monkeypatch):
    from classes.native_guidance import NativeCapabilities

    state = aircraft_state(binding=connection.get_aircraft_state_binding())
    capabilities = NativeCapabilities('runtime', 'fixture', 2, True, True, False, True, 23)
    client = SimpleNamespace(session_identity=None, capabilities=None,
                             bind=AsyncMock(), observe=AsyncMock(return_value={
                                 'runtime_id': capabilities.runtime_id, 'start_context': None, 'source_attitude': None,
                                 "fresh": True, "rescue_active": False, "owner_confirmed": False, "aircraft_state": asdict(state),
                             }), close=AsyncMock(), abort=Mock())
    async def connect():
        client.capabilities = capabilities
        return capabilities
    client.connect = AsyncMock(side_effect=connect)
    monkeypatch.setattr("classes.px4_interface_manager.NativeGuidanceClient", lambda path: client)
    assert await connection.prepare_native_guidance(Path("/private/guidance.sock")) == capabilities
    assert connection.get_aircraft_state() == state
    client.bind.assert_awaited_once_with(state.binding)
    client.close.assert_not_called()
    assert connection.native_guidance_client is client
    connection._advance_telemetry_generation(connection.connection_generation)
    client.abort.assert_called_once()
    assert connection.native_guidance_client is None
    assert connection.get_aircraft_state() is None


@pytest.mark.asyncio
async def test_native_preparation_refuses_aircraft_changed_during_status_read(connection, monkeypatch):
    state = aircraft_state(binding=connection.get_aircraft_state_binding())
    async def changed_aircraft():
        connection._aircraft_identity_revision += 1
        return {"fresh": True, "rescue_active": False, "owner_confirmed": False, "aircraft_state": asdict(state)}
    client = SimpleNamespace(session_identity=None, capabilities=None, connect=AsyncMock(), bind=AsyncMock(),
                             observe=changed_aircraft, close=AsyncMock())
    monkeypatch.setattr("classes.px4_interface_manager.NativeGuidanceClient", lambda path: client)
    with pytest.raises(RuntimeError, match="connection_changed"):
        await connection.prepare_native_guidance(Path("/private/guidance.sock"))
    assert connection.native_guidance_client is None
    client.close.assert_awaited_once()
