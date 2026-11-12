"""Ownership qualification tooling; synthetic packets never count as SIH evidence."""
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from classes.aircraft_state import AircraftBinding, GuidanceSessionIdentity
from classes.native_guidance import NativeGuidanceClient
from tests.fixtures.native_ownership import TOKEN, acquisition
from tests.unit.drone_interface import test_native_guidance as native_protocol_cases
from tests.unit.drone_interface.test_native_guidance import identity
from tests.unit.followers import test_fw_navigation_chase_follower as native_image_cases
from tools import run_native_ownership_sih as tool

FIXTURE = Path(__file__).parent / 'fixtures/native/owned-mode-status-before-arm.txt'
CONTRACT = {'external1': 23, 'hold': 4, 'states': {'acquired': 2, 'superseded': 8}}
native_server = native_protocol_cases.native_server
native_follower_environment = native_image_cases.environment


def source_sample():
    before_arm = tool.parse_owned_samples(FIXTURE.read_text())[0]
    owner = acquisition(GuidanceSessionIdentity('case', AircraftBinding(str(before_arm['autopilot_uid']), '1', 1), 1))
    active = before_arm | {
        'timestamp': 2000, 'source_clock_us': 2000, 'intention_revision': 8,
        'state': CONTRACT['states']['acquired'], 'token': owner.token, 'incarnation': owner.firmware_incarnation,
        'source_revision': owner.source_revision, 'source_nav_state_timestamp': owner.source_nav_state_timestamp,
        'source_nav_state': owner.source_nav_state, 'mode_id': owner.mode_id, 'registration_id': 42,
        'acquired_nav_state_timestamp': owner.activation_timestamp, 'owner_active': True,
        'nav_state': owner.mode_id, 'nav_state_timestamp': owner.activation_timestamp, 'armed': True,
    }
    retired = active | {'timestamp': 3000, 'source_clock_us': 3000, 'intention_revision': 9,
                       'state': CONTRACT['states']['superseded'], 'owner_active': False}
    return owner, active, retired


@pytest.mark.parametrize('phase,is_vtol', [(None, False), ('multicopter', False), ('fixed_wing', True)])
def test_baseline_refuses_missing_or_other_airframe_before_creating_a_follower(monkeypatch, phase, is_vtol):
    from classes.aircraft_state import AirframePhase
    from tests.unit.drone_interface.test_aircraft_state import aircraft_state

    state = None if phase is None else aircraft_state(phase=AirframePhase(phase), is_vtol=is_vtol)
    connection = SimpleNamespace(get_aircraft_state=lambda: state)
    factory = Mock(side_effect=AssertionError('wrong-airframe admission must precede follower creation'))
    monkeypatch.setattr(tool.FollowerFactory, 'create_follower', factory)
    with pytest.raises(ValueError, match='ownership_fixture_requires_pure_fixed_wing'):
        tool.create_session(None, connection, None, None, {}, None, None, run_started=0.)
    factory.assert_not_called()


def test_real_saved_px4_listener_timestamp_age_suffix_is_not_freshness():
    packet = tool.parse_owned_samples(FIXTURE.read_text())[0]
    assert packet['timestamp'] == 7268000
    assert packet['source_clock_us'] == 7268000
    assert packet['autopilot_uid'] == 5283920058631409231
    assert packet['registration_id'] == 0
    assert packet['state'] == 0
    assert packet['armed'] is False
    assert packet['available'] is True
    assert packet['token'] == '0' * 32
    changed_age = FIXTURE.read_text().replace('(0.056000 seconds ago)', '(9999.000000 seconds ago)')
    assert tool.parse_owned_samples(changed_age)[0] == packet


@pytest.mark.parametrize('replacement', ['', 'timestamp: NaN', 'timestamp: 7 (fresh)'])
def test_malformed_listener_timestamp_refuses(replacement):
    raw = FIXTURE.read_text().replace('timestamp: 7268000 (0.056000 seconds ago)', replacement)
    with pytest.raises(ValueError, match='status_missing:timestamp'):
        tool.parse_owned_samples(raw)


def test_same_epoch_accepted_intention_can_prove_retirement():
    owner, active, retired = source_sample()
    assert retired['nav_state_timestamp'] == active['nav_state_timestamp']
    assert tool.takeover_witness([retired], owner, active, superseded_state=CONTRACT['states']['superseded']) is retired


@pytest.mark.parametrize('field,value', [
    ('registration_id', 43), ('registration_id', 0), ('autopilot_uid', 123),
    ('source_clock_us', 2000), ('timestamp', 2000), ('intention_revision', 8),
    ('nav_state_timestamp', 201), ('nav_state', 4), ('token', 'c' * 32),
    ('owner_active', True), ('state', CONTRACT['states']['acquired']),
])
def test_wrong_or_missing_causal_witness_cannot_pass(field, value):
    owner, active, retired = source_sample()
    assert tool.takeover_witness([retired | {field: value}], owner, active,
                                superseded_state=CONTRACT['states']['superseded']) is None


def test_source_contract_reads_verified_constants_not_runtime_guesses(tmp_path, monkeypatch):
    root = tmp_path / 'context/source/msg/versioned'
    root.mkdir(parents=True)
    (root / 'VehicleStatus.msg').write_text('uint8 NAVIGATION_STATE_EXTERNAL1 = 31\nuint8 NAVIGATION_STATE_AUTO_LOITER = 43\n')
    (root / 'OwnedModeStatus.msg').write_text('uint8 STATE_ACQUIRED = 41\nuint8 STATE_SUPERSEDED = 42\n')
    verify = Mock()
    monkeypatch.setattr(tool, 'verify_source', verify)
    result = tool.source_contract(tmp_path / 'sih-build-manifest.json')
    assert result['external1'] == 31
    assert result['hold'] == 43
    assert result['states'] == {'acquired': 41, 'superseded': 42}
    verify.assert_called_once_with(tmp_path / 'context/source', tool.ROOT, tool.verify_extension)


async def test_dry_run_never_opens_owner_or_creates_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tool, 'verify_simulator', Mock(return_value={'verified': True}))
    monkeypatch.setattr(tool, 'source_contract', Mock(return_value=CONTRACT))
    acquire = Mock(side_effect=AssertionError('dry-run cannot create a client'))
    monkeypatch.setattr(tool, 'NativeGuidanceClient', acquire)
    output = tmp_path / 'evidence'
    assert tool.main(['--case', 'normal_stop', '--container', 'isolated', '--instance', '1',
                      '--socket', str(tmp_path / 'native.sock'), '--sih-build-manifest', str(tmp_path / 'build.json'),
                      '--output', str(output)]) == 0
    assert json.loads(capsys.readouterr().out)['execute'] is False
    assert not output.exists()
    acquire.assert_not_called()


@pytest.mark.parametrize('case', tool.CASES)
def test_execute_is_required_for_every_case(case, tmp_path, monkeypatch):
    monkeypatch.setattr(tool, 'verify_simulator', Mock(return_value={'verified': True}))
    monkeypatch.setattr(tool, 'source_contract', Mock(return_value=CONTRACT))
    run = Mock(side_effect=AssertionError('no execution without --execute'))
    monkeypatch.setattr(tool, 'run', run)
    assert tool.main(['--case', case, '--container', 'isolated', '--instance', '1',
                      '--socket', str(tmp_path / 'native.sock'), '--sih-build-manifest', str(tmp_path / 'build.json'),
                      '--output', str(tmp_path / case)]) == 0
    run.assert_not_called()


async def test_wire_recorder_preserves_real_production_client_protocol_and_eof(native_server, tmp_path):
    backend, requests, _ = native_server
    events, eof = [], asyncio.Event()

    def log(name, value):
        events.append(value)
        if value.get('direction') == 'request_forward_attempt' and value.get('eof'):
            eof.set()

    frontend = tmp_path / 'record.sock'
    async with tool.WireRecorder(frontend, backend, log):
        client = NativeGuidanceClient(frontend, clock=lambda: 100.)
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
        original = client.acquisition_context
        assert original is not None
        assert any(row.get('direction') == 'actual_backend_reply'
                   and row.get('value', {}).get('payload', {}).get('acquisition') == original.wire_payload() for row in events)
        client.abort()
        await asyncio.wait_for(eof.wait(), 1.)
        assert client.acquisition_context is original
    assert not frontend.exists()
    assert [row['operation'] for row in requests] == ['hello', 'engage']
    assert not any(row.get('value', {}).get('operation') == 'handoff' for row in events)


async def test_reselection_rejects_incompatible_registered_mode_before_cli(monkeypatch):
    owner, _, _ = source_sample()
    session = SimpleNamespace(acquisition=replace(owner, mode_id=24))
    cli = Mock(side_effect=AssertionError('must not inject into an assumed mode'))
    monkeypatch.setattr(tool, 'user_mode', cli)
    with pytest.raises(ValueError, match='ext1_registration_mismatch'):
        await tool.retired_owner(None, None, session, CONTRACT, lambda *args: None)
    cli.assert_not_called()


def test_negative_wire_evidence_separates_old_and_new_acquisition():
    events = [
        {'timestamp': 1., 'direction': 'request_forward_attempt', 'value': {'operation': 'intent', 'payload': {'token': 'old'}}},
        {'timestamp': 2., 'direction': 'request_forward_attempt', 'value': {'operation': 'intent', 'payload': {'token': 'new'}}},
        {'timestamp': 3., 'direction': 'actual_backend_reply', 'value': {'success': True}},
    ]
    assert tool.wire_requests(events, after=1.5, before=2.5) == [events[1]['value']]


async def test_quiesce_joins_stimulus_before_stopping_the_only_publisher():
    order = []

    async def producer():
        try:
            await asyncio.Event().wait()
        finally:
            order.append('producer_joined')

    from unittest.mock import AsyncMock
    task = asyncio.create_task(producer())
    await asyncio.sleep(0)
    commander = SimpleNamespace(stop=AsyncMock(side_effect=lambda **_: order.append('publisher_stopped') or True))
    await tool.quiesce(SimpleNamespace(baseline_producer=task, commander=commander))
    assert order == ['producer_joined', 'publisher_stopped']
    commander.stop.assert_awaited_once_with(publish_final=False)


async def test_baseline_uses_production_binding_and_only_publisher_without_a_target(monkeypatch, native_follower_environment):
    import time
    from dataclasses import asdict
    from unittest.mock import AsyncMock

    from classes.command_dispatch_guard import validate_before_dispatch
    from classes.native_guidance import NativeCapabilities
    from classes.parameters import Parameters
    from classes.target_continuity import TargetEvidenceState
    from tests.fixtures.native_ownership import release_receipt
    from tests.unit.drone_interface.test_aircraft_state import aircraft_state

    capabilities = NativeCapabilities('test-adapter', 'synthetic-fixture', 2, True, False, False, True, 23)
    aircraft = identity().binding
    client = SimpleNamespace(session_identity=None, acquisition_context=None, acquisition_token=None)
    sequence = [0]

    async def engage(owner, **kwargs):
        validate_before_dispatch(kwargs['before_dispatch'])
        validate_before_dispatch(kwargs['on_mode_dispatch'])
        client.acquisition_token = kwargs['ownership_token']
        client.acquisition_context = acquisition(owner, token=client.acquisition_token)
        client.session_identity = owner
        return {'owner_confirmed': True, 'runtime_id': capabilities.runtime_id,
                'acquisition': client.acquisition_context.wire_payload()}

    async def observe():
        now = time.monotonic()
        sequence[0] += 1
        state = aircraft_state(binding=aircraft, sequence=sequence[0], observed_at_monotonic_s=now,
                               airspeed=replace(aircraft_state().airspeed, observed_at_monotonic_s=now))
        return {'owner_confirmed': True, 'fresh': True, 'rescue_active': False, 'aircraft_state': asdict(state),
                'publications': sequence[0], 'vehicle_pose': {'px4_timestamp_us': sequence[0],
                'observed_at_monotonic_s': now, 'vehicle_ned': [0., 0., -50.], 'quaternion_wxyz': [1., 0., 0., 0.],
                'source': 'px4_dds_observed'}}

    client.engage, client.observe = AsyncMock(side_effect=engage), AsyncMock(side_effect=observe)
    client.submit = AsyncMock()
    client.handoff = AsyncMock(side_effect=lambda *args, **kwargs: release_receipt(client.acquisition_context))
    client.abort = Mock(side_effect=lambda: setattr(client, 'session_identity', None))
    client.matches_acquisition = lambda owner, runtime, token, known=None: (
        client.acquisition_context is not None and client.acquisition_context.identity == owner
        and client.acquisition_context.runtime_id == runtime and client.acquisition_token == token
        and (known is None or known == client.acquisition_context))
    connection = tool.ObservationConnection(aircraft)
    first = await observe()
    assert connection.commit_aircraft_state(tool.AircraftState.from_payload(first['aircraft_state']))
    config = Parameters.get_runtime_config_snapshot()
    log = Mock()
    session = tool.create_session(client, connection, capabilities, identity(), config,
                                 tool.component_profile('gm_velocity_vector').profile, log,
                                 run_started=time.monotonic())
    assert session.binding._target_evidence().state is TargetEvidenceState.ABSENT
    try:
        await tool.activate_session(session, log)
        await tool.drive(session, config['Follower']['AIRFRAME_PHASE_CONFIRMATION_S'] + .1, log)
        assert not session.guidance.phase_owner._decision().pursuit_allowed
        assert session.commander.successful_publishes > 0
        assert connection.last_packet['vehicle_pose']['px4_timestamp_us'] > 1
        assert client.submit.call_args.kwargs['acquisition'] == session.acquisition
        await tool.quiesce(session)
        assert (await session.binding.stop('unit_cleanup'))['executed']
        client.handoff.assert_awaited_once()
    finally:
        await tool.quiesce(session)
        session.binding.abort('unit_finally')


@pytest.mark.parametrize('disconnected', [False, True])
async def test_retired_owner_uses_actual_source_proof_and_handles_only_terminal_socket_loss(monkeypatch, disconnected):
    from unittest.mock import AsyncMock

    from classes.native_guidance import NativeGuidanceError
    owner, active, retired = source_sample()
    monkeypatch.setattr(tool, 'confirmed_source', AsyncMock(return_value=active))
    monkeypatch.setattr(tool, 'observe_status', AsyncMock(return_value=[retired]))
    monkeypatch.setattr(tool, 'user_mode', AsyncMock())
    observe = AsyncMock(side_effect=NativeGuidanceError('native_disconnected')) if disconnected else AsyncMock(return_value={'owner_confirmed': False})
    client = SimpleNamespace(observe=observe, session_identity=None)
    binding = SimpleNamespace(abort=Mock(), on_observation=Mock(side_effect=AssertionError('no fabricated state')))
    session = SimpleNamespace(acquisition=owner, client=client, binding=binding,
                              commander=SimpleNamespace(stop=AsyncMock(return_value=True)), baseline_producer=None)
    records = []
    def log(name, value):
        records.append((name, value))
        return float(len(records))
    witness, _ = await tool.retired_owner(None, None, session, CONTRACT, log)
    assert witness == retired
    binding.abort.assert_called_once_with('ownership_fixture_confirmed_source_release')
    binding.on_observation.assert_not_called()
    assert any(name == 'takeover-witness.jsonl' for name, _ in records)


async def test_retired_owner_never_accepts_a_missing_same_epoch_witness(monkeypatch):
    from unittest.mock import AsyncMock
    owner, active, retired = source_sample()
    monkeypatch.setattr(tool, 'confirmed_source', AsyncMock(return_value=active))
    monkeypatch.setattr(tool, 'observe_status', AsyncMock(return_value=[retired | {'nav_state_timestamp': 201}]))
    monkeypatch.setattr(tool, 'user_mode', AsyncMock())
    binding = SimpleNamespace(abort=Mock())
    session = SimpleNamespace(acquisition=owner, client=SimpleNamespace(observe=AsyncMock(return_value={'owner_confirmed': False})),
                              binding=binding, commander=SimpleNamespace(stop=AsyncMock(return_value=True)), baseline_producer=None)
    with pytest.raises(ValueError, match='same_epoch_retirement_not_observed'):
        await tool.retired_owner(None, None, session, CONTRACT, lambda *args: 0.)
    binding.abort.assert_not_called()


async def test_partial_start_cleanup_runs_before_wire_recorder_closes(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from classes.native_guidance import NativeGuidanceError
    events = []
    monkeypatch.setattr(tool, 'time', SimpleNamespace(monotonic=lambda: 1234.5))
    class Recorder:
        def __init__(self, *args):
            pass
        async def __aenter__(self):
            manifest = json.loads((output / 'manifest.json').read_text())
            assert manifest['host_clock'] == {'basis': 'time.monotonic', 'origin_s': 1234.5,
                                              'wire_timestamp_semantics': 'seconds_since_origin'}
            events.append('recorder_open')
        async def __aexit__(self, *_):
            events.append('recorder_closed')
    output = tmp_path / 'evidence'
    config_path = tmp_path / 'config.yaml'
    config_path.write_text('Follower: {}\n')
    args = SimpleNamespace(output=output, config=config_path, follower='gm_velocity_vector', case='normal_stop',
                           socket=tmp_path / 'native.sock', stable_timeout=1., test_altitude=30., duration=1.)
    from classes.native_guidance import NativeCapabilities
    client = SimpleNamespace(connect=AsyncMock(return_value=NativeCapabilities('fixture', 'fixture', 2, True, False, False, True, 23)),
                             bind=AsyncMock(), close=AsyncMock(side_effect=lambda: events.append('client_closed')))
    monkeypatch.setattr(tool, 'WireRecorder', Recorder)
    monkeypatch.setattr(tool, 'NativeGuidanceClient', Mock(return_value=client))
    monkeypatch.setattr(tool, 'native_parameters', Mock(return_value='unchanged'))
    monkeypatch.setattr(tool, 'archive_configuration', Mock(return_value={}))
    monkeypatch.setattr(tool.Parameters, 'load_config', Mock())
    monkeypatch.setattr(tool, 'stable_aircraft', AsyncMock())
    binding = SimpleNamespace(stop=AsyncMock())
    async def release(*args):
        assert 'recorder_open' in events and 'recorder_closed' not in events
        assert json.loads((output / 'pre-cleanup-result.json').read_text())['passed'] is False
        events.append('original_released')
        return {'executed': False, 'local_sender_quiesced': True, 'errors': []}
    binding.stop.side_effect = release
    session = SimpleNamespace(binding=binding)
    monkeypatch.setattr(tool, 'create_session', Mock(return_value=session))
    monkeypatch.setattr(tool, 'activate_session', AsyncMock(side_effect=NativeGuidanceError('start_failed_after_dispatch')))
    monkeypatch.setattr(tool, 'quiesce', AsyncMock(side_effect=lambda session: events.append('publisher_joined')))
    result = await tool.run(args, {'aircraft_uid': '123'}, CONTRACT)
    assert result['passed'] is False
    assert 'start_failed_after_dispatch' in result['reason']
    assert events.index('publisher_joined') < events.index('original_released') < events.index('recorder_closed')


async def test_independent_cli_runs_off_the_publisher_event_loop(monkeypatch):
    import threading
    event_loop_thread = threading.get_ident()
    def cli(*args):
        assert threading.get_ident() != event_loop_thread
        return {'returncode': 0, 'stdout': 'actual fixture command', 'stderr': ''}
    monkeypatch.setattr(tool, 'isolated_cli', cli)
    records = []
    await tool.user_mode(SimpleNamespace(socket=None), {}, lambda name, record: records.append(record), 'auto:loiter',
                         purpose='independent_cleanup_after_verdict')
    assert records[0]['role'] == 'independent_simulated_operator'
    assert records[0]['purpose'] == 'independent_cleanup_after_verdict'


@pytest.mark.parametrize('closed_at,expected', [(.2, True), (1.1, False)])
def test_eof_proof_requires_actual_backend_close_before_command_expiry(closed_at, expected):
    events = [
        {'timestamp': .1, 'connection': 1, 'direction': 'request_forward_attempt',
         'value': {'operation': 'intent', 'payload': {'expires_at_monotonic_s': 11.}}},
        {'timestamp': closed_at, 'connection': 1, 'direction': 'backend_socket_closed'},
        {'timestamp': .15, 'connection': 2, 'direction': 'backend_socket_closed'},
    ]
    assert tool.eof_precedes_intent_expiry(events, after=.15, run_started=10.) is expected


@pytest.mark.parametrize('hold_line,accepted', [
    ('uint8 NAVIGATION_STATE_AUTO_LOITER = 4 # Auto loiter mode', True),
    ('uint8 NAVIGATION_STATE_AUTO_LOITER = 4.0 # invalid float', False),
    ('uint8 NAVIGATION_STATE_AUTO_LOITER = 4junk # invalid integer', False),
])
def test_pinned_enum_inline_comment_keeps_integer_validation(tmp_path, monkeypatch, hold_line, accepted):
    root = tmp_path / 'context/source/msg/versioned'
    root.mkdir(parents=True)
    (root / 'VehicleStatus.msg').write_text('uint8 NAVIGATION_STATE_EXTERNAL1 = 23\n' + hold_line + '\n')
    (root / 'OwnedModeStatus.msg').write_text('uint8 STATE_ACQUIRED = 2 # acquired\nuint8 STATE_SUPERSEDED = 8\n')
    monkeypatch.setattr(tool, 'verify_source', Mock())
    if accepted:
        assert tool.source_contract(tmp_path / 'sih-build-manifest.json')['hold'] == 4
    else:
        with pytest.raises(ValueError, match='external_constant_missing'):
            tool.source_contract(tmp_path / 'sih-build-manifest.json')


def test_real_confirmed_owner_eof_wire_subset_keeps_only_actual_requests():
    fixture = Path(__file__).parent / 'fixtures/native/confirmed-owner-eof-wire-subset.jsonl'
    events = [json.loads(line) for line in fixture.read_text().splitlines()]
    eof = events[0]
    assert eof['direction'] == 'request_forward_attempt'
    assert eof['eof'] is True
    assert type(eof['connection']) is int
    assert 'value' not in eof
    requests = tool.wire_requests(events, after=eof['timestamp'])
    assert [request['operation'] for request in requests] == ['hello', 'bind', 'observe', 'observe']
    assert all(request['protocol_version'] == 2 for request in requests)
    outcomes = [event['value']['payload']['release_receipt']['outcome'] for event in events
                if event.get('direction') == 'actual_backend_reply'
                and event.get('value', {}).get('payload', {}).get('release_receipt')]
    assert outcomes == ['unconfirmed', 'hold_confirmed']


@pytest.mark.parametrize('record,reason', [
    ({}, 'wire_request_invalid'),
    ({'value': None}, 'wire_request_invalid'),
    ({'value': []}, 'wire_request_invalid'),
    ({'value': {'operation': 'observe'}}, 'wire_request_invalid'),
    ({'value': {'operation': '', 'payload': {}}}, 'wire_request_invalid'),
    ({'value': {'operation': 'observe', 'payload': []}}, 'wire_request_invalid'),
    ({'eof': False}, 'wire_eof_invalid'),
    ({'eof': 1}, 'wire_eof_invalid'),
    ({'eof': True, 'value': {'operation': 'handoff', 'payload': {}}}, 'wire_eof_invalid'),
])
def test_malformed_actual_wire_requests_are_never_silently_ignored(record, reason):
    event = {'timestamp': 1., 'connection': 1, 'direction': 'request_forward_attempt', **record}
    with pytest.raises(ValueError, match=reason):
        tool.wire_requests([event], after=0.)


def hold_arrival_packets():
    path = Path(__file__).parent / 'fixtures/native/same-mode-hold-arrival-subset.jsonl'
    packets = [json.loads(line) for line in path.read_text().splitlines()]
    context = tool.NativeAcquisitionContext.from_payload(packets[0]['release_receipt']['acquisition'])
    return context, packets


@pytest.mark.parametrize('receipt_first', [True, False])
async def test_read_only_hold_wait_accepts_either_source_arrival_order_then_convergence(receipt_first):
    from copy import deepcopy
    from unittest.mock import AsyncMock
    context, packets = hold_arrival_packets()
    first, converged = deepcopy(packets[0]), deepcopy(packets[1])
    if not receipt_first:
        first = deepcopy(converged)
        first['release_receipt']['observed_nav_state'] = context.mode_id
        first['release_receipt']['observed_nav_state_timestamp'] = context.activation_timestamp
    clock = [0.]
    async def pause(delay):
        clock[0] += delay
    client = SimpleNamespace(observe=AsyncMock(side_effect=[first, converged]))
    logs = []
    observed, counts = await tool.wait_for_coherent_hold(client, context, CONTRACT['hold'],
        lambda name, value: logs.append((name, value)), clock=lambda: clock[0], pause=pause)
    assert observed is converged
    assert counts == [1732, 1732]
    assert client.observe.await_count == 2
    assert [call for call in client.observe.call_args_list] == [(), ()]
    window = next(value for name, value in logs if name == 'hold-coherence-window.jsonl')
    assert window['converged'] is True
    assert window['maximum_wait_s'] == pytest.approx(1. - first['phase_source_health']['vehicle_status_age_s'])
    assert window['budget_source'] == 'initial_vehicle_status_remaining_freshness'


async def test_hold_wait_timeout_never_renews_budget_from_later_packets_or_replays_commands():
    from copy import deepcopy
    from unittest.mock import AsyncMock
    context, packets = hold_arrival_packets()
    first = deepcopy(packets[0])
    first['phase_source_health'].update(vehicle_status_timeout_s=.25, vehicle_status_age_s=.05)
    later = deepcopy(first)
    later['phase_source_health'].update(vehicle_status_timeout_s=1000., vehicle_status_age_s=0.)
    clock = [0.]
    async def pause(delay):
        clock[0] += delay
    client = SimpleNamespace(observe=AsyncMock(side_effect=[first, later]))
    logs = []
    with pytest.raises(ValueError, match='hold_coherence_timeout'):
        await tool.wait_for_coherent_hold(client, context, CONTRACT['hold'],
            lambda name, value: logs.append((name, value)), clock=lambda: clock[0], pause=pause)
    assert client.observe.await_count == 2
    window = next(value for name, value in logs if name == 'hold-coherence-window.jsonl')
    assert window['converged'] is False
    assert window['maximum_wait_s'] == pytest.approx(.2)
    assert window['elapsed_s'] == pytest.approx(.2)


async def test_wait_preserves_publication_growth_so_invariant_samples_cannot_hide_it():
    from copy import deepcopy
    from unittest.mock import AsyncMock
    context, packets = hold_arrival_packets()
    first, converged = deepcopy(packets[0]), deepcopy(packets[1])
    converged['publications'] += 1
    clock = [0.]
    async def pause(delay):
        clock[0] += delay
    client = SimpleNamespace(observe=AsyncMock(side_effect=[first, converged]))
    _, counts = await tool.wait_for_coherent_hold(client, context, CONTRACT['hold'], lambda *args: None,
                                                clock=lambda: clock[0], pause=pause)
    assert counts == [1732, 1733]
    assert len(set(counts + [1733] * 5)) == 2


@pytest.mark.parametrize('budget,age', [(None, 0.), (True, 0.), (1., -1.), (1., 1.)])
async def test_hold_wait_requires_a_valid_existing_status_budget(budget, age):
    from copy import deepcopy
    from unittest.mock import AsyncMock
    context, packets = hold_arrival_packets()
    packet = deepcopy(packets[0])
    packet['phase_source_health'].update(vehicle_status_timeout_s=budget, vehicle_status_age_s=age)
    client = SimpleNamespace(observe=AsyncMock(return_value=packet))
    with pytest.raises(ValueError):
        await tool.wait_for_coherent_hold(client, context, CONTRACT['hold'], lambda *args: None)
    assert client.observe.await_count == 1
