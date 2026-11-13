"""Original native Start intent is immutable; these tests acquire no aircraft."""

from dataclasses import FrozenInstanceError, asdict, replace
from unittest.mock import Mock

import pytest

from classes.aircraft_state import AirframePhase
from classes.native_guidance import NativeCapabilities, NativeGuidanceClient, NativeGuidanceError, NativeStartContext
from tests.fixtures.native_ownership import acquisition, start_context, TOKEN
from tests.unit.drone_interface.test_native_guidance import ALTITUDE_REFERENCE, CAPABILITIES, identity, native_server


@pytest.mark.parametrize('change', [
    {'runtime_id': 'replacement'}, {'mode_id': 24}, {'registration_id': 9001},
    {'intention_revision': 8}, {'source_nav_state': 5}, {'source_nav_state_timestamp': 101},
    {'firmware_incarnation': 'a' * 32}, {'phase_source_instance': 8}, {'phase_revision': 2},
])
def test_context_id_binds_semantic_history_including_mode_epoch(change):
    original = start_context(identity(), phase='multicopter')
    assert replace(original, **change).context_id != original.context_id
    assert NativeStartContext.from_payload(original.wire_payload()) == original
    with pytest.raises(FrozenInstanceError):
        original.phase_revision = 2


@pytest.mark.parametrize('change', [
    {'version': True}, {'version': 2}, {'registration_id': 0}, {'intention_revision': True},
    {'source_nav_state_timestamp': 0}, {'source_nav_state_timestamp': 1.5},
    {'phase_source_instance': 0}, {'phase_revision': 0}, {'phase': 'vtol_transition'},
    {'phase': 'unknown'}, {'sequence': 123}, {'source_nav_state': 23},
])
def test_invalid_or_query_created_context_cannot_qualify_start(change):
    payload = start_context(identity(), phase='multicopter').wire_payload() | change
    with pytest.raises(NativeGuidanceError):
        NativeStartContext.from_payload(payload)


def test_healthy_payload_reads_do_not_churn_id_or_require_pose_fields():
    context = start_context(identity())
    ids = {NativeStartContext.from_payload(context.wire_payload()).context_id for _ in range(100)}
    assert ids == {context.context_id}
    assert not {'sequence', 'observed_at_monotonic_s', 'timestamp'} & context.wire_payload().keys()
    assert 'source_nav_state_timestamp' in context.wire_payload()
    with pytest.raises(NativeGuidanceError, match='context_changed'):
        context.require_match(identity().binding, context.runtime_id, phase=AirframePhase.MULTICOPTER)


async def test_missing_original_context_refuses_before_any_engage_rpc(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path)
    dispatched = Mock()
    try:
        await client.connect()
        with pytest.raises(NativeGuidanceError, match='native_start_context_required'):
            await client.engage(identity(), circuit_breaker_active=False, altitude_reference=ALTITUDE_REFERENCE,
                                on_mode_dispatch=dispatched)
        assert [request['operation'] for request in requests] == ['hello']
        dispatched.assert_not_called()
        assert client.acquisition_context is None and client.acquisition_token is None
    finally:
        await client.close()


async def test_engage_transmits_and_receipt_echoes_the_original_context(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path)
    original = start_context(identity())
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN,
                            altitude_reference=ALTITUDE_REFERENCE, start_context=original)
        assert requests[-1]['payload']['start_context'] == original.wire_payload()
        assert client.acquisition_context.start_context == original
    finally:
        await client.close()


async def test_replacement_start_context_in_correlated_ack_is_not_adopted(native_server):
    path, _, behavior = native_server
    original = start_context(identity())
    context = replace(original, phase_source_instance=7, phase_revision=2)
    behavior['engage_reply'] = {'acquisition': acquisition(identity(), start=context).wire_payload()}
    client = NativeGuidanceClient(path)
    try:
        await client.connect()
        with pytest.raises(NativeGuidanceError, match='native_start_context_changed'):
            await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN,
                                altitude_reference=ALTITUDE_REFERENCE, start_context=original)
        assert client.session_identity is None
    finally:
        await client.close()


@pytest.mark.parametrize('change', [
    {'runtime_id': 'other-runtime'}, {'phase': 'multicopter', 'phase_source_instance': 7, 'phase_revision': 1},
    {'binding': {'aircraft_uid': 'other', 'connection_generation': '1', 'telemetry_generation': 1}},
])
async def test_passive_observation_context_must_match_that_same_packet(native_server, change):
    path, _, behavior = native_server
    behavior['owner_confirmed'] = False
    behavior['observation'] = {'start_context': start_context(identity()).wire_payload() | change}
    client = NativeGuidanceClient(path)
    try:
        await client.connect()
        with pytest.raises(NativeGuidanceError, match='native_observation_invalid'):
            await client.observe()
    finally:
        await client.close()


@pytest.mark.parametrize('clock_id', [True, 1, '', 'world with spaces', 'a' * 129])
def test_clock_label_is_optional_but_malformed_labels_refuse(clock_id):
    with pytest.raises(NativeGuidanceError, match='native_source_clock_identity_invalid'):
        NativeCapabilities.from_payload(CAPABILITIES | {'source_clock_id': clock_id})
    assert NativeCapabilities.from_payload(CAPABILITIES).source_clock_id is None
    assert NativeCapabilities.from_payload(CAPABILITIES | {'source_clock_id': 'world:123'}).source_clock_id == 'world:123'
