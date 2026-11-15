"""Source-bound read-only native snapshots; no SDK or aircraft actions."""

from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from classes.aircraft_state import GuidanceSessionIdentity
from classes.native_guidance import NativeCapabilities, NativeGuidanceError
from classes.source_time_alignment import SourceAttitudeSample
from tests.fixtures.native_ownership import start_context
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing
from tests.unit.drone_interface.test_aircraft_state_connection import connection


@pytest.fixture
def sample(connection, monkeypatch):
    now = [100.]
    monkeypatch.setattr('classes.px4_interface_manager.time.monotonic', lambda: now[0])
    connection.get_telemetry_stale_timeout_s = lambda: .5
    caps = NativeCapabilities('native-a', 'fixture', 2, True, True, False, True, 23, True, 'clock-a')
    connection._native_guidance_client = SimpleNamespace(capabilities=caps, session_identity=None)
    state = aircraft_state(binding=connection.get_aircraft_state_binding(), attitude_timing=attitude_timing())
    context = start_context(GuidanceSessionIdentity('preparing', state.binding, 0), runtime_id=caps.runtime_id)
    raw = SourceAttitudeSample(1_000_000, 1_001_000, (1., 0., 0., 0.),
        state.attitude_timing.quat_reset_counter, 100., 'px4_source_us')
    packet = dict(runtime_id=caps.runtime_id, fresh=True, rescue_active=False, owner_confirmed=False,
        aircraft_state=asdict(state), start_context=context.wire_payload(), source_attitude=asdict(raw))
    assert connection.commit_native_observation(packet)
    return SimpleNamespace(connection=connection, now=now, caps=caps, state=state, context=context,
                           raw=raw, packet=packet)


def test_original_context_and_raw_receipt_are_not_renewed_by_repeated_polls(sample):
    owner = sample.connection
    assert owner.native_start_context == sample.context
    sample.now[0] = 100.2
    assert owner.commit_native_observation(sample.packet)
    records = owner.source_attitude_history.snapshot(binding=sample.state.binding, runtime_id=sample.caps.runtime_id,
        source_clock_id='clock-a', reset_counter=sample.raw.quat_reset_counter)
    assert len(records) == 1 and records[0][0].received_at_monotonic_s == 100.
    sample.now[0] = 100.6
    assert owner.native_start_context is None


@pytest.mark.parametrize('change', ['runtime', 'binding', 'older_state', 'older_stale', 'older_malformed'])
def test_superseded_reply_cannot_clear_current_context_or_history(sample, change):
    packet = dict(sample.packet)
    if change == 'runtime':
        packet['runtime_id'] = 'superseded'
    elif change == 'binding':
        packet['aircraft_state'] = asdict(replace(sample.state,
            binding=replace(sample.state.binding, connection_generation='old-connection')))
    else:
        packet['aircraft_state'] = asdict(replace(sample.state, sequence=0))
        if change == 'older_stale':
            packet['fresh'] = False
        elif change == 'older_malformed':
            packet['start_context'] = {'wrong': 'fields'}
    assert not sample.connection.commit_native_observation(packet)
    assert sample.connection.native_start_context == sample.context
    assert sample.connection.source_attitude_history.snapshot(binding=sample.state.binding,
        runtime_id=sample.caps.runtime_id, source_clock_id='clock-a', reset_counter=sample.raw.quat_reset_counter)


def test_explicit_current_stale_observation_retires_start_context(sample):
    assert not sample.connection.commit_native_observation(sample.packet | {'fresh': False})
    assert sample.connection.native_start_context is None
    assert sample.connection.get_aircraft_state() is None
    assert sample.connection._aircraft_state_owner.snapshot(timeout_s=1.) == sample.state


def test_wrong_context_binding_refuses_before_committing_new_pose(sample):
    context = replace(sample.context, binding=replace(sample.state.binding, aircraft_uid='other'))
    packet = sample.packet | {'start_context': context.wire_payload(),
                             'aircraft_state': asdict(replace(sample.state, sequence=2))}
    with pytest.raises(NativeGuidanceError):
        sample.connection.commit_native_observation(packet)
    assert sample.connection.native_start_context is None
    assert sample.connection.get_aircraft_state() is None
    assert sample.connection._aircraft_state_owner.snapshot(timeout_s=1.) == sample.state


def test_acquisition_does_not_leave_a_passive_start_context_available(sample):
    sample.connection._native_guidance_client.session_identity = GuidanceSessionIdentity('active', sample.state.binding, 0)
    assert sample.connection.native_start_context is None


def test_an_explicit_null_context_does_not_reuse_the_previous_passive_context(sample):
    assert sample.connection.commit_native_observation(sample.packet | {'start_context': None})
    assert sample.connection.native_start_context is None
