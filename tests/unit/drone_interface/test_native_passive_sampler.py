"""Deterministic passive-source scheduling and RPC ownership races; no aircraft I/O."""

import asyncio
import time
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.native_guidance import NativeGuidanceClient, NativeGuidanceError
from tests.unit.drone_interface.test_aircraft_state_connection import connection
from tests.unit.drone_interface.test_native_observation_snapshot import sample


_REAL_MONOTONIC = time.monotonic


@pytest.fixture
def sampler(sample, monkeypatch):
    owner = sample.connection
    monkeypatch.setattr(time, "monotonic", _REAL_MONOTONIC)
    monkeypatch.setattr("classes.px4_interface_manager.time", SimpleNamespace(monotonic=lambda: sample.now[0]))
    owner._aircraft_state_owner._clock = lambda: sample.now[0]
    ticks, sleeping = asyncio.Queue(), asyncio.Queue()

    async def sleep(period):
        sleeping.put_nowait(period)
        await ticks.get()

    monkeypatch.setattr('classes.px4_interface_manager.asyncio.sleep', sleep)
    client = owner._native_guidance_client
    client.passive_observation_allowed = True
    client.observe = AsyncMock(return_value=sample.packet)
    client.abort = Mock()
    client.close = AsyncMock()
    owner.update_task = None
    owner.connection_monitor_task = None
    owner._telemetry_stream_tasks = {}
    owner._cancel_mavsdk_stream_tasks = AsyncMock(return_value=True)
    return SimpleNamespace(owner=owner, client=client, sample=sample, ticks=ticks, sleeping=sleeping)


async def at_tick(s):
    return await asyncio.wait_for(s.sleeping.get(), timeout=1.)


async def stop(s):
    task = getattr(s.owner, '_native_observation_task', None)
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_sampler_collects_source_history_without_ui_and_reuses_one_worker(sampler):
    s = sampler
    owner = s.owner
    owner._ensure_native_observation_task(s.client, s.sample.state.binding)
    task = owner._native_observation_task
    try:
        assert await at_tick(s) == .02
        owner._ensure_native_observation_task(s.client, s.sample.state.binding)
        assert owner._native_observation_task is task
        for index in range(1, 5):
            t = 100. + index * .02
            s.sample.now[0] = t
            state = replace(s.sample.state, sequence=index + 1, observed_at_monotonic_s=t)
            raw = replace(s.sample.raw, sample_timestamp_us=1_000_000 + index * 20_000,
                publication_timestamp_us=1_001_000 + index * 20_000, received_at_monotonic_s=t)
            s.client.observe.return_value = s.sample.packet | {'aircraft_state': asdict(state), 'source_attitude': asdict(raw)}
            s.ticks.put_nowait(None)
            await at_tick(s)
        records = owner.source_attitude_history.snapshot(binding=s.sample.state.binding,
            runtime_id=s.sample.caps.runtime_id, source_clock_id='clock-a', reset_counter=s.sample.raw.quat_reset_counter)
        assert [record[0].received_at_monotonic_s for record in records] == [100., 100.02, 100.04, 100.06, 100.08]
        assert all(call.kwargs == {'passive': True} for call in s.client.observe.await_args_list)
        assert owner._get_owned_task_status()['native_observer_alive'] is True
    finally:
        await stop(s)
    assert owner._get_owned_task_status()['all_stopped'] is True


@pytest.mark.asyncio
async def test_sampler_yields_owned_reads_then_resumes_without_recreating_worker(sampler):
    s = sampler
    s.owner._ensure_native_observation_task(s.client, s.sample.state.binding)
    task = s.owner._native_observation_task
    commit = Mock(wraps=s.owner.commit_native_observation)
    s.owner.commit_native_observation = commit
    try:
        await at_tick(s)
        s.client.observe.return_value = None
        s.ticks.put_nowait(None)
        await at_tick(s)
        commit.assert_not_called()
        s.client.observe.return_value = s.sample.packet
        s.ticks.put_nowait(None)
        await at_tick(s)
        commit.assert_called_once_with(s.sample.packet)
        assert s.owner._native_observation_task is task
    finally:
        await stop(s)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['client', 'binding', 'abort'])
async def test_delayed_source_reply_cannot_commit_after_owner_replacement(sampler, change):
    s = sampler
    started, release = asyncio.Event(), asyncio.Event()

    async def observe(**kwargs):
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            # Simulate a transport that finishes its already received packet during cancellation.
            await release.wait()
        return s.sample.packet

    s.client.observe.side_effect = observe
    commit = Mock(wraps=s.owner.commit_native_observation)
    s.owner.commit_native_observation = commit
    s.owner._ensure_native_observation_task(s.client, s.sample.state.binding)
    task = s.owner._native_observation_task
    try:
        await at_tick(s)
        s.ticks.put_nowait(None)
        await asyncio.wait_for(started.wait(), 1.)
        if change == 'client':
            s.owner._native_guidance_client = SimpleNamespace(capabilities=s.sample.caps)
        elif change == 'binding':
            s.owner._telemetry_generation += 1
        else:
            s.owner._abort_native_guidance()
        release.set()
        await asyncio.wait_for(task, 1.)
        commit.assert_not_called()
    finally:
        release.set()
        await stop(s)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['rescue', 'owner', 'transport'])
async def test_bad_passive_source_retires_context_without_restamping_or_retry_actions(sampler, failure):
    s = sampler
    if failure == 'transport':
        s.client.observe.side_effect = NativeGuidanceError('native_transport_failed')
    else:
        key, value = {'rescue': ('rescue_active', True), 'owner': ('owner_confirmed', True)}[failure]
        s.client.observe.return_value = s.sample.packet | {key: value}
    s.owner._ensure_native_observation_task(s.client, s.sample.state.binding)
    await at_tick(s)
    s.ticks.put_nowait(None)
    await asyncio.wait_for(s.owner._native_observation_task, 1.)
    assert s.owner.native_guidance_client is None
    assert s.owner.native_start_context is None
    assert s.owner.get_aircraft_state() is None
    assert not s.owner.source_attitude_history.snapshot(binding=s.sample.state.binding,
        runtime_id=s.sample.caps.runtime_id, source_clock_id='clock-a', reset_counter=s.sample.raw.quat_reset_counter)
    s.client.abort.assert_called_once()
    s.client.observe.assert_awaited_once_with(passive=True)


@pytest.mark.asyncio
async def test_stale_passive_status_blocks_admission_and_recovers_without_reconnecting_or_actions(sampler):
    s = sampler
    s.owner._ensure_native_observation_task(s.client, s.sample.state.binding)
    task = s.owner._native_observation_task
    try:
        await at_tick(s)
        s.client.observe.return_value = s.sample.packet | {'fresh': False, 'aircraft_state': None}
        for _ in range(3):
            s.ticks.put_nowait(None)
            await at_tick(s)
            assert s.owner.native_guidance_client is s.client
            assert s.owner.native_start_context is None
            assert s.owner.get_aircraft_state() is None
            assert not s.owner.source_attitude_history.snapshot(binding=s.sample.state.binding,
                runtime_id=s.sample.caps.runtime_id, source_clock_id='clock-a', reset_counter=s.sample.raw.quat_reset_counter)
        s.client.observe.return_value = s.sample.packet
        s.ticks.put_nowait(None)
        await at_tick(s)
        assert s.owner.get_aircraft_state() == s.sample.state
        assert s.owner.native_start_context is not None
        assert s.owner._native_observation_task is task
        s.client.abort.assert_not_called()
        assert all(call.kwargs == {'passive': True} for call in s.client.observe.await_args_list)
    finally:
        await stop(s)


@pytest.mark.asyncio
async def test_existing_telemetry_cleanup_joins_sampler_and_reports_stopped(sampler):
    s = sampler
    s.owner._ensure_native_observation_task(s.client, s.sample.state.binding)
    await at_tick(s)
    assert s.owner._get_owned_task_status()['alive_count'] == 1
    assert await s.owner._cancel_telemetry_update_task()
    assert s.owner._native_observation_task.done()
    assert s.owner._get_owned_task_status()['all_stopped'] is True
    s.client.observe.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['owned', 'pending'])
async def test_passive_observe_rechecks_ownership_after_waiting_for_rpc_lock(state):
    client = NativeGuidanceClient(Path('/synthetic/native.sock'))
    client._exchange = AsyncMock()
    await client._lock.acquire()
    task = asyncio.create_task(client.observe(passive=True))
    queued = asyncio.Event()
    asyncio.get_running_loop().call_soon(queued.set)
    await queued.wait()
    if state == 'owned':
        client._identity = object()
    else:
        client._acquisition_pending = True
    client._lock.release()
    assert await asyncio.wait_for(task, 1.) is None
    client._exchange.assert_not_called()
    assert not client.passive_observation_allowed


@pytest.mark.asyncio
async def test_immediate_rediscovery_cannot_be_left_without_sampler_by_cancelling_old_worker(sampler, monkeypatch):
    s = sampler
    owner = s.owner
    owner._ensure_native_observation_task(s.client, s.sample.state.binding)
    await at_tick(s)
    original = owner._native_observation_task
    owner._abort_native_guidance()
    replacement = SimpleNamespace(capabilities=None, session_identity=None,
        passive_observation_allowed=True, observe=AsyncMock(return_value=s.sample.packet),
        abort=Mock(), close=AsyncMock())
    async def connect():
        replacement.capabilities = s.sample.caps
        return s.sample.caps
    replacement.connect = AsyncMock(side_effect=connect)
    replacement.bind = AsyncMock()
    monkeypatch.setattr('classes.px4_interface_manager.NativeGuidanceClient', lambda path: replacement)
    try:
        await owner.prepare_native_guidance(Path('/synthetic/native.sock'))
        await asyncio.gather(original, return_exceptions=True)
        assert owner._native_observation_task is not original
        assert not owner._native_observation_task.done()
        assert await at_tick(s) == .02
    finally:
        await stop(s)


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['owned', 'pending'])
async def test_prepare_queued_behind_acquisition_cannot_close_owner_or_commit_passive_state(sampler, state):
    s = sampler
    client = NativeGuidanceClient(Path('/synthetic/native.sock'))
    client.capabilities = s.sample.caps
    client._exchange = AsyncMock()
    client.close = AsyncMock()
    s.owner._native_guidance_client = client
    s.owner.commit_native_observation = Mock()
    await client._lock.acquire()
    task = asyncio.create_task(s.owner.prepare_native_guidance(client.socket_path))
    queued = asyncio.Event()
    asyncio.get_running_loop().call_soon(queued.set)
    await queued.wait()
    if state == 'owned':
        client._identity = object()
    else:
        client._acquisition_pending = True
    client._lock.release()
    assert await asyncio.wait_for(task, 1.) == s.sample.caps
    assert s.owner.native_guidance_client is client
    client._exchange.assert_not_called()
    client.close.assert_not_called()
    s.owner.commit_native_observation.assert_not_called()


@pytest.mark.asyncio
async def test_sampler_does_not_commit_a_reply_after_acquisition_begins(sampler):
    s = sampler
    async def observe(**kwargs):
        s.client.passive_observation_allowed = False
        return s.sample.packet
    s.client.observe.side_effect = observe
    s.owner.commit_native_observation = Mock()
    s.owner._ensure_native_observation_task(s.client, s.sample.state.binding)
    try:
        await at_tick(s)
        s.ticks.put_nowait(None)
        await at_tick(s)
        s.owner.commit_native_observation.assert_not_called()
        s.client.abort.assert_not_called()
    finally:
        await stop(s)
