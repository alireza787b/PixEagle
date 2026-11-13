"""Connection-owned passive native discovery; synthetic I/O, no authority."""
import asyncio
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.aircraft_state import AircraftKind, AirframePhase
from classes.app_controller import AppController
from classes.native_guidance import NativeCapabilities, NativeGuidanceClient, NativeGuidanceError
from classes.parameters import Parameters
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.unit.drone_interface.test_aircraft_state_connection import connection

pytestmark = pytest.mark.unit


def native_client(connection):
    caps = NativeCapabilities('runtime-a', 'synthetic', 2, True, True, False, True, 23)
    state = aircraft_state(binding=connection.get_aircraft_state_binding(), is_vtol=False)
    client = SimpleNamespace(capabilities=None, session_identity=None, bind=AsyncMock(),
                             close=AsyncMock(), abort=Mock())
    async def connect():
        client.capabilities = caps
        return caps
    client.connect = AsyncMock(side_effect=connect)
    client.observe = AsyncMock(return_value=dict(runtime_id=caps.runtime_id,
        start_context=None, source_attitude=None, fresh=True, owner_confirmed=False,
        rescue_active=False, aircraft_state=asdict(state)))
    return client, state


def controller(connection, monkeypatch):
    app = AppController.__new__(AppController)
    app._flight_event_loop = asyncio.get_running_loop()
    app._follower_state_lock = asyncio.Lock()
    app.following_active = False
    app.px4_interface = connection
    app._native_follow_binding = None
    connection.get_aircraft_kind = Mock(return_value=AircraftKind.FIXED_WING)
    monkeypatch.setattr(Parameters, 'FOLLOWER_EXECUTION_MODE', 'PX4')
    monkeypatch.setattr(Parameters, 'AIRFRAME_LAYOUT', 'AUTO', raising=False)
    return app


async def test_two_passive_polls_reuse_one_client_and_snapshot_owner(connection, monkeypatch):
    app = controller(connection, monkeypatch); client, state = native_client(connection)
    factory = Mock(return_value=client)
    monkeypatch.setattr('classes.px4_interface_manager.NativeGuidanceClient', factory)
    owner = connection._aircraft_state_owner
    await asyncio.gather(*(app.refresh_native_following_state('gm_velocity_vector') for _ in range(2)))
    assert factory.call_count == client.connect.await_count == client.bind.await_count == 1
    assert client.observe.await_count == 2 and connection.get_aircraft_state() == state
    assert connection._aircraft_state_owner is owner and connection.native_guidance_client is client
    client.close.assert_not_awaited()


@pytest.mark.parametrize('condition', ['mc', 'unknown', 'mavsdk_profile', 'disconnected',
    'active', 'binding', 'stopping', 'cleanup', 'shutdown', 'preview'])
async def test_status_never_starts_adapter_for_ineligible_or_owned_paths(connection, monkeypatch, condition):
    app = controller(connection, monkeypatch); mode = 'gm_velocity_vector'
    connection.prepare_native_guidance = AsyncMock(side_effect=AssertionError('unwanted native observation'))
    if condition in ('mc', 'unknown'):
        connection.get_aircraft_kind.return_value = AircraftKind.MULTICOPTER if condition == 'mc' else AircraftKind.UNKNOWN
    elif condition == 'mavsdk_profile': mode = 'mc_velocity_position'
    elif condition == 'disconnected': connection.get_connection_status = lambda: {'connected': False}
    elif condition == 'active': app.following_active = True
    elif condition == 'binding': app._native_follow_binding = object()
    elif condition == 'stopping': app._following_stopping = True
    elif condition == 'cleanup': app._following_offboard_cleanup_required = True
    elif condition == 'shutdown': app.shutdown_flag = True
    elif condition == 'preview': monkeypatch.setattr(Parameters, 'FOLLOWER_EXECUTION_MODE', 'COMMAND_PREVIEW')
    await app.refresh_native_following_state(mode)
    connection.prepare_native_guidance.assert_not_awaited()


async def test_implemented_native_profile_can_observe_while_start_remains_unqualified(connection, monkeypatch):
    from classes.follower_catalog import get_follower_profile

    app = controller(connection, monkeypatch)
    profile = replace(get_follower_profile('fw_navigation_chase'), live_qualified_phases=())
    assert not profile.live_eligibility.eligible
    monkeypatch.setattr('classes.follower_catalog.get_follower_profile', lambda _: profile)
    connection.prepare_native_guidance = AsyncMock()
    await app.refresh_native_following_state('fw_navigation_chase')
    connection.prepare_native_guidance.assert_awaited_once()
    assert not app.following_active


async def test_metadata_not_vector_name_selects_native_observation(connection, monkeypatch):
    from classes.follower_catalog import get_follower_profile
    app = controller(connection, monkeypatch)
    profile = replace(get_follower_profile('gm_velocity_vector'), mode='future_qualified_native')
    monkeypatch.setattr('classes.follower_catalog.get_follower_profile', lambda _: profile)
    connection.prepare_native_guidance = AsyncMock()
    await app.refresh_native_following_state('future_qualified_native')
    connection.prepare_native_guidance.assert_awaited_once()


@pytest.mark.parametrize('change', ['active', 'disconnect', 'teardown'])
async def test_status_waiting_for_lifecycle_lock_cannot_observe_new_owner(connection, monkeypatch, change):
    app = controller(connection, monkeypatch)
    retained = aircraft_state(binding=connection.get_aircraft_state_binding())
    assert connection.commit_aircraft_state(retained)
    connection.prepare_native_guidance = AsyncMock()
    async with app._follower_state_lock:
        pending = asyncio.create_task(app.refresh_native_following_state('gm_velocity_vector'))
        await asyncio.sleep(0)
        assert not pending.done()
        if change == 'active': app._native_follow_binding = object()
        elif change == 'disconnect': connection.get_connection_status = lambda: {'connected': False}
        else: app._following_stopping = True
    await pending
    connection.prepare_native_guidance.assert_not_awaited()
    if change != 'disconnect': assert connection.get_aircraft_state() == retained


@pytest.mark.parametrize('failure', ['stale', 'rescue', 'owner', 'transport', 'runtime'])
async def test_passive_failure_retires_client_and_clears_only_current_native_snapshot(connection, monkeypatch, failure):
    client, state = native_client(connection)
    monkeypatch.setattr('classes.px4_interface_manager.NativeGuidanceClient', Mock(return_value=client))
    await connection.prepare_native_guidance(Path('/private/guidance.sock'))
    if failure in ('transport', 'runtime'):
        # The real client rejects changed runtime before returning an observation.
        client.observe.side_effect = NativeGuidanceError('native_observation_invalid' if failure == 'runtime' else 'native_connection_unavailable')
    else:
        packet = dict(fresh=True, rescue_active=failure == 'rescue', owner_confirmed=failure == 'owner',
            aircraft_state=asdict(replace(state, sequence=2,
                observed_at_monotonic_s=90. if failure == 'stale' else 100.)))
        client.observe.return_value = packet
    with pytest.raises(NativeGuidanceError): await connection.prepare_native_guidance(Path('/private/guidance.sock'))
    assert connection.native_guidance_client is connection.get_aircraft_state() is None
    client.close.assert_awaited_once()
    assert client.connect.await_count == client.bind.await_count == 1


async def test_active_client_cannot_be_polled_or_rebound_directly(connection):
    client, _ = native_client(connection);client.session_identity = object()
    connection._native_guidance_client = client
    with pytest.raises(NativeGuidanceError, match='already_owned'):
        await connection.prepare_native_guidance(Path('/private/guidance.sock'))
    client.observe.assert_not_awaited();client.connect.assert_not_awaited();client.bind.assert_not_awaited()
    client.close.assert_not_awaited()


async def test_real_client_runtime_change_retires_passive_binding_before_any_commit(connection):
    state = aircraft_state(binding=connection.get_aircraft_state_binding())
    assert connection.commit_aircraft_state(state)
    client = NativeGuidanceClient(Path('/never-opened-native.sock'))
    client.capabilities = NativeCapabilities('runtime-a', 'synthetic', 2, True, True, False, True, 23)
    client._exchange = AsyncMock(return_value=dict(runtime_id='runtime-b', fresh=True,
        rescue_active=False, owner_confirmed=False, release_receipt=None,
        aircraft_state=asdict(replace(state, sequence=2))))
    connection._native_guidance_client = client
    with pytest.raises(NativeGuidanceError, match='native_observation_invalid'):
        await connection.prepare_native_guidance(Path('/never-opened-native.sock'))
    assert connection.get_aircraft_state() is connection.native_guidance_client is client.capabilities is None
    assert client.session_identity is None and connection.get_connection_status()['connected']
    client._exchange.assert_awaited_once_with('observe', {})


@pytest.mark.parametrize('change', ['connection', 'telemetry', 'identity'])
async def test_old_native_reply_cannot_commit_or_clear_replacement_generation(connection, monkeypatch, change):
    client, old = native_client(connection);entered, release = asyncio.Event(), asyncio.Event()
    async def delayed():
        entered.set();await release.wait()
        return dict(fresh=True, owner_confirmed=False, rescue_active=False, aircraft_state=asdict(old))
    client.observe.side_effect = delayed
    monkeypatch.setattr('classes.px4_interface_manager.NativeGuidanceClient', lambda _: client)
    pending = asyncio.create_task(connection.prepare_native_guidance(Path('/private/guidance.sock')))
    await entered.wait()
    if change == 'connection':
        connection._advance_connection_generation()
        connection._aircraft_identity = {'autopilot_uid': 'aircraft-a', 'hardware_uid': None}
    elif change == 'telemetry': connection._advance_telemetry_generation(connection.connection_generation)
    else:
        connection._aircraft_identity_revision += 1
        connection._aircraft_identity = {'autopilot_uid': 'replacement', 'hardware_uid': None}
    replacement = replace(old, binding=connection.get_aircraft_state_binding(), sequence=9)
    assert connection.commit_aircraft_state(replacement)
    release.set()
    with pytest.raises(NativeGuidanceError, match='connection_changed'): await pending
    assert connection.get_aircraft_state() == replacement
    assert connection.native_guidance_client is None
    client.close.assert_awaited_once()


async def test_cancelled_passive_read_does_not_leave_ready_cached_pose(connection, monkeypatch):
    client, state = native_client(connection)
    monkeypatch.setattr('classes.px4_interface_manager.NativeGuidanceClient', lambda _: client)
    await connection.prepare_native_guidance(Path('/private/guidance.sock'))
    entered = asyncio.Event()
    async def pending():
        entered.set();await asyncio.Event().wait()
    client.observe.side_effect = pending
    task = asyncio.create_task(connection.prepare_native_guidance(Path('/private/guidance.sock')))
    await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert connection.get_aircraft_state() is connection.native_guidance_client is None
    client.close.assert_awaited_once()
