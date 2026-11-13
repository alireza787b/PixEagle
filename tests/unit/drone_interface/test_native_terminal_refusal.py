"""Synthetic current-protocol projection of a recorded observe/intent race.

The immutable R5 fixture records protocol 3. Only this local test server's
capabilities and reply envelopes use the current protocol; acquisition receipts,
identities and race evidence remain recorded values. This is not a new PX4 capture.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

import pytest

from classes.aircraft_state import AircraftState, AircraftStateOwner
from classes.command_dispatch_guard import DispatchRefused, DispatchRefusalKind
from classes.native_follow_binding import NativeFollowBinding
from classes.native_guidance import (
    PROTOCOL_VERSION, NativeBackendRefusal, NativeCapabilities, NativeGuidanceClient, NativeGuidanceError,
)
from classes.offboard_commander import OffboardCommander
from classes.target_continuity import ContinuityContext, ContinuityPolicy, TargetContinuitySupervisor
from tests.unit.core_app.test_fixed_wing_continuity import evidence
from tests.unit.core_app.test_native_follow_binding import CONFIG
from tests.unit.followers.test_vector_guidance_session import session

FIXTURE = json.loads((Path(__file__).parents[2] / 'fixtures/native/transition-intent-refusal-r5.json').read_text())
PROJECTED_CAPABILITIES = FIXTURE['capabilities'] | {'multicopter_altitude_hold_supported': True}


@pytest.fixture
async def race_server():
    requests, writers = [], []
    behavior = dict(refuse=False, exited=False, reply_changes={}, observation_changes={}, capabilities_changes={},
                    delay_release=False, refusal_delay_s=0., reached=asyncio.Event(), release=asyncio.Event())

    async def handle(reader, writer):
        writers.append(writer)
        try:
            while raw := await reader.readline():
                request = json.loads(raw)
                requests.append(request)
                operation = request['operation']
                if operation == 'hello':
                    payload = PROJECTED_CAPABILITIES | (behavior['capabilities_changes'] if behavior['exited'] else {})
                elif operation == 'bind':
                    payload = {'bound': True}
                elif operation == 'engage':
                    acq = FIXTURE['released_observation']['value']['payload']['release_receipt']['acquisition']
                    assert request['payload']['identity'] == acq['identity']
                    assert request['payload']['token'] == acq['token']
                    payload = dict(owner_confirmed=True, runtime_id=acq['runtime_id'], acquisition=acq)
                elif operation == 'intent' and behavior['refuse']:
                    if behavior['refusal_delay_s']:
                        await asyncio.sleep(behavior['refusal_delay_s'])
                    behavior['exited'] = True
                    reply = {**FIXTURE['refusal']['value'], 'protocol_version': PROTOCOL_VERSION,
                             'request_id': request['request_id'],
                             'generation': request['generation']} | behavior['reply_changes']
                    for key in list(reply):
                        if reply[key] == '__missing__':
                            del reply[key]
                    writer.write(json.dumps(reply).encode() + b'\n')
                    await writer.drain()
                    continue
                elif operation == 'intent':
                    payload = dict(accepted_sequence=request['payload']['sequence'], owner_confirmed=True)
                elif operation == 'observe':
                    source = 'released_observation' if behavior['exited'] else 'healthy_observation'
                    payload = deepcopy(FIXTURE[source]['value']['payload'])
                    if behavior['exited']:
                        payload.update(behavior['observation_changes'])
                        if behavior['delay_release']:
                            behavior['reached'].set()
                            await behavior['release'].wait()
                else:
                    raise AssertionError('Unexpected write: ' + operation)
                reply = dict(protocol_version=PROTOCOL_VERSION, request_id=request['request_id'], generation=request['generation'],
                             success=True, payload=payload)
                writer.write(json.dumps(reply).encode() + b'\n')
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    with tempfile.TemporaryDirectory(prefix='pe-refusal-') as directory:
        path = Path(directory) / 'control.sock'
        server = await asyncio.start_unix_server(handle, str(path))
        try:
            yield path, requests, behavior
        finally:
            behavior['release'].set()
            server.close()
            await server.wait_closed()
            for writer in writers:
                writer.close()
            await asyncio.gather(*(writer.wait_closed() for writer in writers), return_exceptions=True)


async def binding_for_race(race_server, monkeypatch):
    path, requests, behavior = race_server
    payload = deepcopy(FIXTURE['healthy_observation']['value']['payload'])
    payload['aircraft_state']['attitude_timing'] = payload['attitude_timing']
    state = AircraftState.from_payload(payload['aircraft_state'])
    context = FIXTURE['released_observation']['value']['payload']['release_receipt']['acquisition']
    guidance, now, _ = session(state=state, session_id=context['identity']['follow_session_id'])
    now[0] = FIXTURE['released_observation']['value']['payload']['attitude_timing']['publication_received_at_monotonic_s'] + .001
    guidance.phase_owner.capabilities = NativeCapabilities.from_payload(PROJECTED_CAPABILITIES)
    states = AircraftStateOwner(clock=lambda: now[0])
    states.bind(state.binding)
    states.commit(state)
    connection = SimpleNamespace(get_aircraft_state=lambda: states.snapshot(timeout_s=.75),
                                 commit_aircraft_state=states.commit)
    client = NativeGuidanceClient(path, request_timeout_s=.2, clock=lambda: now[0])
    await client.connect()
    await client.bind(state.binding)
    monkeypatch.setattr('classes.native_follow_binding.make_ownership_token', lambda: context['token'])
    continuity = TargetContinuitySupervisor(ContinuityPolicy.from_mapping(CONFIG), clock=lambda: now[0])
    continuity.reset_session(session_epoch=1, reason='start')
    base = ContinuityContext('PX4_NATIVE', state.phase, 'fixed_wing_external', True, True, True, vehicle_yaw_deg=0.)
    binding = NativeFollowBinding(guidance, connection, client, continuity, profile_name='gm_velocity_vector',
        continuity_config=CONFIG, target_evidence=lambda: evidence(), context=lambda: base,
        circuit_breaker=lambda: False, clock=lambda: now[0])
    intent = await binding.engage()
    return binding, client, requests, behavior, intent, now


async def test_recorded_fw_race_projected_to_current_protocol_is_terminal_without_false_publication_failure(race_server, monkeypatch):
    binding, client, requests, behavior, intent, now = await binding_for_race(race_server, monkeypatch)
    monkeypatch.setattr('classes.offboard_commander.time', SimpleNamespace(monotonic=lambda: now[0]))
    events = []
    commander = OffboardCommander(None, None, command_transport=binding.transport, on_publish_result=events.append)
    assert commander.submit_intent(intent)
    assert await commander.publish_once()
    before = len(requests)
    behavior['refuse'] = True
    assert await commander.publish_once() is False
    assert [r['operation'] for r in requests[before:]] == ['observe', 'intent', 'hello', 'bind', 'observe']
    assert binding.terminal_reason == 'aircraft_transition_observed'
    assert commander.failed_publishes == 0 and commander.successful_publishes == 1
    assert commander.terminal_failure_reason == 'aircraft_transition_observed'
    assert not commander.running and client.session_identity is None
    assert binding.transport.last_published_intent is None
    assert commander.get_published_intent() is None
    refusal = binding.transport.last_backend_refusal
    assert refusal.operation == 'intent' and refusal.code == 'native_pursuit_ended'
    refused_request = [r for r in requests if r['request_id'] == refusal.request_id and r['generation'] == refusal.generation][-1]
    assert refused_request['operation'] == 'intent'
    event = events[-1]
    assert event['publication_attempted'] is False and event['submitted_fields'] is None
    assert event['publish_status']['last_publish_success'] is None
    details = event['publish_status']['last_dispatch_refusal']['details']
    assert details == refusal.admission_details()
    assert details['native_request_attempted'] is True and details['native_request_refused'] is True
    assert details['native_publication_admitted'] is False
    details['code'] = 'mutated_by_trace_consumer'
    assert commander.get_status()['last_dispatch_refusal']['details'] == refusal.admission_details()
    assert binding.transport._sequence == 1
    writes = [r for r in requests if r['operation'] in {'engage', 'intent', 'handoff', 'phase'}]
    with pytest.raises(NativeGuidanceError):
        await binding.transport.publish(intent, reason='obsolete', ttl_s=.5)
    assert [r for r in requests if r['operation'] in {'engage', 'intent', 'handoff', 'phase'}] == writes
    await client.close()


@pytest.mark.parametrize('changes', [
    {'success': '__missing__'}, {'success': 0}, {'success': 1}, {'success': True}, {'success': 'false'}, {'success': None},
    {'error_code': '__missing__'}, {'error_code': ''}, {'error_code': False},
    {'error_code': 'contains spaces'}, {'error_code': 'x' * 129},
    {'request_id': True}, {'request_id': 999}, {'generation': True}, {'generation': 999},
    {'protocol_version': 2}, {'protocol_version': 3}, {'payload': {}},
])
async def test_malformed_refusal_never_starts_reconciliation(race_server, monkeypatch, changes):
    binding, client, requests, behavior, intent, _ = await binding_for_race(race_server, monkeypatch)
    behavior.update(refuse=True, reply_changes=changes)
    before = len(requests)
    with pytest.raises(NativeGuidanceError) as error:
        await binding.transport.publish(intent, reason='heartbeat', ttl_s=.5)
    assert not isinstance(error.value, NativeBackendRefusal)
    assert [r['operation'] for r in requests[before:]] == ['observe', 'intent']
    assert binding.terminal_reason is None and client.session_identity is None
    await client.close()


@pytest.mark.parametrize('change', ['stale', 'runtime', 'uid', 'token', 'incarnation', 'epoch', 'rescue',
                                    'phase_stale', 'owner_active', 'wrong_runtime_capability'])
async def test_refusal_evidence_cannot_hide_unmatched_or_stale_authority(race_server, monkeypatch, change):
    binding, client, requests, behavior, intent, now = await binding_for_race(race_server, monkeypatch)
    changed = deepcopy(FIXTURE['released_observation']['value']['payload'])
    if change == 'stale':
        changed['aircraft_state']['observed_at_monotonic_s'] = now[0] - 1.
    elif change == 'runtime':
        changed['runtime_id'] = 'replacement'
    elif change == 'uid':
        changed['aircraft_state']['binding']['aircraft_uid'] = 'replacement'
    elif change in {'token', 'incarnation', 'epoch'}:
        key = {'token': 'token', 'incarnation': 'firmware_incarnation', 'epoch': 'activation_timestamp'}[change]
        changed['release_receipt']['acquisition'][key] = 999999999 if change == 'epoch' else 'e' * 32
    elif change == 'rescue':
        changed['rescue_active'] = True
    elif change == 'phase_stale':
        changed['phase_status_fresh'] = False
    elif change == 'owner_active':
        changed['owner_confirmed'] = True
    else:
        behavior['capabilities_changes'] = {'runtime_id': 'replacement'}
    behavior.update(refuse=True, observation_changes=changed)
    with pytest.raises(NativeGuidanceError):
        await binding.transport.publish(intent, reason='heartbeat', ttl_s=.5)
    assert binding.terminal_reason != 'aircraft_transition_observed'
    assert client.session_identity is None
    assert [r['operation'] for r in requests].count('engage') == 1
    assert [r['operation'] for r in requests].count('intent') == 1
    assert not any(r['operation'] in {'handoff', 'phase'} for r in requests)
    await client.close()


@pytest.mark.parametrize('outcome', ['return_intent', 'superseded'])
async def test_existing_callback_must_classify_terminal_and_cannot_resume_after_refusal(race_server, monkeypatch, outcome):
    binding, client, requests, behavior, intent, _ = await binding_for_race(race_server, monkeypatch)
    async def does_not_end(state, observation, candidate):
        if outcome == 'superseded' and observation['owner_confirmed'] is False:
            raise DispatchRefused('target_replaced', DispatchRefusalKind.SUPERSEDED)
        return intent
    binding.transport.on_observation = does_not_end
    behavior['refuse'] = True
    with pytest.raises(NativeBackendRefusal):
        await binding.transport.publish(intent, reason='heartbeat', ttl_s=.5)
    assert client.session_identity is None and binding.terminal_reason is None
    await client.close()


async def test_reconciliation_cannot_restore_a_replacement(race_server, monkeypatch):
    binding, client, requests, behavior, intent, _ = await binding_for_race(race_server, monkeypatch)
    behavior.update(refuse=True, delay_release=True)
    task = asyncio.create_task(binding.transport.publish(intent, reason='heartbeat', ttl_s=.5))
    await asyncio.wait_for(behavior['reached'].wait(), .5)
    replacement = replace(client.acquisition_context, token='f' * 32)
    client._acquisition = replacement
    client._ownership_token = replacement.token
    behavior['release'].set()
    with pytest.raises(NativeGuidanceError, match='context_replaced'):
        await task
    assert client.acquisition_context is replacement and client.acquisition_token == replacement.token
    assert binding.terminal_reason is None
    await client.close()


async def test_delayed_refusal_leaves_only_original_request_deadline_for_evidence(race_server, monkeypatch):
    binding, client, requests, behavior, intent, _ = await binding_for_race(race_server, monkeypatch)
    behavior.update(refuse=True, refusal_delay_s=.12, delay_release=True)
    with pytest.raises(NativeGuidanceError, match='release_unconfirmed'):
        await binding.transport.publish(intent, reason='heartbeat', ttl_s=.5)
    refusal = binding.transport.last_backend_refusal
    assert asyncio.get_running_loop().time() < refusal.deadline + .07
    assert behavior['reached'].is_set() and client.session_identity is None
    assert binding.terminal_reason is None
    assert [r['operation'] for r in requests].count('intent') == 1
    await client.close()


async def test_existing_publish_timeout_cancels_read_only_evidence_without_terminal_promotion(race_server, monkeypatch):
    binding, client, requests, behavior, intent, now = await binding_for_race(race_server, monkeypatch)
    monkeypatch.setattr('classes.offboard_commander.time', SimpleNamespace(monotonic=lambda: now[0]))
    behavior.update(refuse=True, delay_release=True)
    commander = OffboardCommander(None, None, command_transport=binding.transport, publish_timeout_s=.1)
    assert commander.submit_intent(intent)
    assert await commander.publish_once() is False
    assert behavior['reached'].is_set()
    assert commander.failed_publishes == 1 and commander.successful_publishes == 0
    assert 'deadline' in commander.last_error and not commander.terminal_failure
    assert binding.terminal_reason is None and client.session_identity is None
    assert [r['operation'] for r in requests].count('intent') == 1
    await client.close()


@pytest.mark.parametrize('interrupt', ['cancel', 'abort_generation'])
async def test_original_generation_fence_and_cancellation_survive_refusal_reconciliation(race_server, monkeypatch, interrupt):
    binding, client, requests, behavior, intent, _ = await binding_for_race(race_server, monkeypatch)
    behavior.update(refuse=True, delay_release=True)
    task = asyncio.create_task(binding.transport.publish(intent, reason='heartbeat', ttl_s=.5))
    await asyncio.wait_for(behavior['reached'].wait(), .5)
    context = client.acquisition_context
    if interrupt == 'cancel':
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        client.abort()
        behavior['release'].set()
        with pytest.raises(NativeGuidanceError, match='context_replaced'):
            await task
    assert client.acquisition_context == context and client.session_identity is None
    assert binding.terminal_reason is None
    assert [r['operation'] for r in requests].count('engage') == 1
    assert [r['operation'] for r in requests].count('intent') == 1
    await client.close()


@pytest.mark.parametrize('phase,reason', [('fixed_wing', 'control_owner_lost'),
                                        ('unknown', 'aircraft_phase_unknown')])
async def test_original_callback_reasons_are_never_rewritten_to_transition(race_server, monkeypatch, phase, reason):
    binding, client, requests, behavior, intent, _ = await binding_for_race(race_server, monkeypatch)
    changed = deepcopy(FIXTURE['released_observation']['value']['payload'])
    changed['aircraft_state']['phase'] = phase
    changed['nav_state'] = 5
    changed['release_receipt'].update(outcome='owner_already_released', observed_nav_state=5)
    behavior.update(refuse=True, observation_changes=changed)
    with pytest.raises(DispatchRefused) as error:
        await binding.transport.publish(intent, reason='heartbeat', ttl_s=.5)
    assert error.value.reason_code == reason and error.value.kind is DispatchRefusalKind.TERMINAL
    assert binding.terminal_reason == reason and client.session_identity is None
    assert not any(r['operation'] == 'handoff' for r in requests)
    await client.close()


async def test_other_correlated_backend_refusals_keep_normal_failure_accounting(race_server, monkeypatch):
    binding, client, requests, behavior, intent, now = await binding_for_race(race_server, monkeypatch)
    monkeypatch.setattr('classes.offboard_commander.time', SimpleNamespace(monotonic=lambda: now[0]))
    behavior.update(refuse=True, reply_changes={'error_code': 'native_ownership_lost'})
    commander = OffboardCommander(None, None, command_transport=binding.transport)
    assert commander.submit_intent(intent)
    assert await commander.publish_once() is False
    assert commander.failed_publishes == 1 and commander.successful_publishes == 0
    assert commander.last_dispatch_refusal is None and binding.terminal_reason is None
    assert [r['operation'] for r in requests].count('hello') == 1
    await client.close()
