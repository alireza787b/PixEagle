"""Stock source joins the existing connection owner, not a parallel poller."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.mavlink_aircraft_state import MavlinkGuidanceObservation
from classes.mavlink_guidance_source import MavlinkGuidanceSource
from classes.native_guidance import NativeGuidanceError
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.unit.drone_interface.test_aircraft_state_connection import connection  # noqa: F401
from tests.unit.drone_interface.test_mavlink_guidance_source import parameters


def manager_fixture(connection):
    state = aircraft_state(binding=connection.get_aircraft_state_binding(), source="mavlink2rest_source_progress")
    observation = MavlinkGuidanceObservation(state, (state.binding.aircraft_uid, "rest-1"), 1, 1,
        False, 4 << 16, 100., None, 1, 1)
    manager = SimpleNamespace(get_aircraft_state_source_epoch=lambda: observation.source_epoch,
        get_guidance_observation=lambda *args, **kwargs: replace(observation,
            state=replace(observation.state, fixed_wing_envelope=kwargs.get("envelope"))))
    return manager, observation


def test_cached_poll_read_preserves_the_same_source_clock_and_owner(connection):
    manager, observation = manager_fixture(connection)
    connection._mavlink_guidance_source = MavlinkGuidanceSource(manager, observation.state.binding,
        observation.source_epoch, current_binding=connection.get_aircraft_state_binding)
    owner = connection._aircraft_state_owner
    assert connection.get_aircraft_state() == replace(observation.state, fixed_wing_envelope=None)
    assert connection.get_aircraft_state() == replace(observation.state, fixed_wing_envelope=None)
    assert connection._aircraft_state_owner is owner
    assert owner.snapshot(timeout_s=2.).observed_at_monotonic_s == 100.


def test_telemetry_epoch_change_discards_stock_source_instead_of_relabeling_old_pose(connection):
    manager, observation = manager_fixture(connection)
    connection._mavlink_guidance_source = MavlinkGuidanceSource(manager, observation.state.binding,
        observation.source_epoch, current_binding=connection.get_aircraft_state_binding)
    assert connection.get_aircraft_state() == replace(observation.state, fixed_wing_envelope=None)
    connection._telemetry_generation += 1
    assert connection.get_aircraft_state() is None


@pytest.mark.asyncio
async def test_parameter_preparation_uses_existing_identity_and_never_dispatches_a_flight_action(connection):
    manager, observation = manager_fixture(connection)
    connection.mavlink_data_manager = manager
    connection.is_command_connection_ready = lambda: True
    connection.drone = SimpleNamespace(param=SimpleNamespace(
        get_param_float=AsyncMock(side_effect=lambda name: parameters()[name])))
    # A prior passive source may be replaced; no previously owned mode exists.
    assert connection.commit_aircraft_state(replace(observation.state, source="prior-passive-source"))
    source = await connection.prepare_mavlink_guidance(lookahead_m=50.)
    assert connection.mavlink_guidance_source is source
    assert connection.get_aircraft_state().fixed_wing_envelope.minimum_eas_m_s == 12.
    assert connection.native_guidance_client is None
    assert source.start_context.phase == observation.state.phase


@pytest.mark.asyncio
async def test_stock_source_cannot_be_overwritten_by_a_passive_native_refresh(connection):
    connection._mavlink_guidance_source = object()
    with pytest.raises(NativeGuidanceError, match="transport_already_prepared"):
        await connection.prepare_native_guidance(Path("/unused/native.sock"))


@pytest.mark.asyncio
async def test_active_native_owner_is_never_replaced_by_stock_preparation(connection):
    connection._native_guidance_client = SimpleNamespace(session_identity=object(), abort=Mock())
    with pytest.raises(ValueError, match="owner_already_active"):
        await connection.prepare_mavlink_guidance(lookahead_m=50.)
    connection._native_guidance_client.abort.assert_not_called()


def test_reconnect_clears_the_stock_source_and_original_binding(connection):
    connection._mavlink_guidance_source = object()
    connection._advance_connection_generation()
    assert connection.mavlink_guidance_source is None
