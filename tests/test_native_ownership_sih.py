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
from tools.native_sih_wire import WireRecorder, archive_wire_helper

FIXTURE = Path(__file__).parent / 'fixtures/native/owned-mode-status-before-arm.txt'
CONTRACT = {'external1': 23, 'hold': 4, 'states': {'acquired': 2, 'superseded': 8}}
native_server = native_protocol_cases.native_server
native_follower_environment = native_image_cases.environment


def test_shared_recorder_preserves_public_tool_alias_and_archives_exact_source(tmp_path):
    import hashlib
    import inspect

    assert tool.WireRecorder is WireRecorder
    artifact = archive_wire_helper(tmp_path)
    source = Path(inspect.getfile(WireRecorder)).read_bytes()
    assert (tmp_path / artifact['path']).read_bytes() == source
    assert artifact['sha256'] == hashlib.sha256(source).hexdigest()


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


@pytest.mark.parametrize('case', [case for case in tool.CASES if case != 'adapter_process_restart'])
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
    def publisher_stopped(**_):
        order.append('publisher_stopped')
        return True

    commander = SimpleNamespace(stop=AsyncMock(side_effect=publisher_stopped))
    await tool.quiesce(SimpleNamespace(baseline_producer=task, commander=commander))
    assert order == ['producer_joined', 'publisher_stopped']
    commander.stop.assert_awaited_once_with(publish_final=False)


@pytest.mark.parametrize('airframe', ['pure_fixed_wing', 'settled_vtol_mc', 'settled_vtol_fw'])
async def test_baseline_uses_production_binding_and_only_publisher_without_a_target(monkeypatch, native_follower_environment, airframe):
    import time
    from dataclasses import asdict
    from unittest.mock import AsyncMock

    from classes.command_dispatch_guard import validate_before_dispatch
    from classes.native_guidance import NativeCapabilities
    from classes.parameters import Parameters
    from classes.target_continuity import TargetEvidenceState
    from tests.fixtures.native_ownership import release_receipt
    from tests.unit.drone_interface.test_aircraft_state import aircraft_state

    mc = airframe == 'settled_vtol_mc'
    is_vtol = airframe != 'pure_fixed_wing'
    capabilities = NativeCapabilities('test-adapter', 'synthetic-fixture', 2, True, is_vtol, False, True, 23)
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
                               is_vtol=is_vtol, phase=tool.AirframePhase.MULTICOPTER if mc else tool.AirframePhase.FIXED_WING,
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
                                 run_started=time.monotonic(), airframe=airframe)
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


@pytest.mark.parametrize('phase,vtol,accepted', [
    ('multicopter', True, True), ('multicopter', False, False), ('fixed_wing', True, False),
    ('fixed_wing', False, False), ('vtol_transition', True, False),
])
def test_mc_path_requires_actual_settled_vtol_before_construction(phase, vtol, accepted):
    from tests.unit.drone_interface.test_aircraft_state import aircraft_state
    state = aircraft_state(phase=tool.AirframePhase(phase), is_vtol=vtol)
    if accepted:
        tool.require_airframe(state, 'settled_vtol_mc')
    else:
        with pytest.raises(ValueError, match='requires_settled_vtol_mc'):
            tool.require_airframe(state, 'settled_vtol_mc')


def restart_arguments(tmp_path):
    import hashlib
    helper = tmp_path / 'helper.py'
    helper.write_text('raise RuntimeError("must never execute during dry-run")\n')
    socket = tmp_path / 'native.sock'
    value = {'schema_version': 1, 'scope': 'isolated_sih_adapter_restart', 'container_id': 'owned-container',
             'socket': str(socket), 'runtime_directory': str(tmp_path),
             'helper': {'path': str(helper), 'sha256': hashlib.sha256(helper.read_bytes()).hexdigest()}}
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps(value))
    return SimpleNamespace(restart_plan=plan, socket=socket), value


def test_restart_dry_run_pins_helper_but_never_creates_a_backend(tmp_path, monkeypatch, capsys):
    args, _ = restart_arguments(tmp_path)
    monkeypatch.setattr(tool, 'verify_simulator', Mock(return_value={'container_id': 'owned-container'}))
    monkeypatch.setattr(tool, 'source_contract', Mock(return_value=CONTRACT))
    forbidden = Mock(side_effect=AssertionError('no restart, backend or helper in dry-run'))
    monkeypatch.setattr(tool, 'run', forbidden)
    output = tmp_path / 'capture'
    assert tool.main(['--case', 'adapter_process_restart', '--airframe', 'settled_vtol_mc',
        '--restart-plan', str(args.restart_plan), '--socket', str(args.socket), '--container', 'owned-container',
        '--instance', '0', '--sih-build-manifest', str(tmp_path / 'build.json'), '--output', str(output)]) == 0
    assert json.loads(capsys.readouterr().out)['execute'] is False
    forbidden.assert_not_called()
    assert not output.exists()


@pytest.mark.parametrize('change', ['container', 'socket', 'helper', 'extra'])
def test_restart_helper_never_adopts_another_plan_or_modified_source(tmp_path, change):
    args, value = restart_arguments(tmp_path)
    if change == 'container':
        value['container_id'] = 'other'
    elif change == 'socket':
        value['socket'] = str(tmp_path / 'other.sock')
    elif change == 'helper':
        Path(value['helper']['path']).write_text('different')
    else:
        value['allow_force'] = True
    args.restart_plan.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='restart_(plan_mismatch|helper_changed)'):
        tool.restart_plan(args, {'container_id': 'owned-container'})


def old_intent_wire(context):
    return [{'timestamp': .1, 'direction': 'request_forward_attempt', 'value': {'operation': 'intent', 'payload': {
        'identity': tool.asdict(context.identity), 'token': context.token, 'phase': 'multicopter', 'sequence': 7,
        'created_at_monotonic_s': 10., 'expires_at_monotonic_s': 10.3,
        'command': {'velocity_north_m_s': 0., 'velocity_east_m_s': 0., 'velocity_down_m_s': 0., 'yaw_rate_rad_s': 0.}}}}]


def captured_owned(context):
    return {'token': [int(context.token[:16], 16), int(context.token[16:], 16)],
            'incarnation': [int(context.firmware_incarnation[:16], 16), int(context.firmware_incarnation[16:], 16)],
            'autopilot_uid': int(context.identity.binding.aircraft_uid), 'source_revision': context.source_revision,
            'source_nav_state': context.source_nav_state, 'source_nav_state_timestamp': context.source_nav_state_timestamp,
            'mode_id': context.mode_id, 'acquired_nav_state_timestamp': context.activation_timestamp,
            'owner_active': True, 'state': CONTRACT['states']['acquired']}


def test_retained_negative_intent_uses_actual_old_wire_without_refresh():
    context = acquisition(identity())
    retained = tool.retained_mc_intent(old_intent_wire(context), context)
    assert retained.created_at_monotonic_s == 10.
    assert retained.expires_at_monotonic_s == 10.3
    assert retained.sequence == 7
    with pytest.raises(ValueError, match='original_intent_mismatch'):
        tool.retained_mc_intent(old_intent_wire(context), replace(context, token='f' * 32))


async def test_original_probes_use_real_client_runtime_fence_then_local_identity_not_expiry(native_server):
    backend, requests, behavior = native_server
    client = NativeGuidanceClient(backend, clock=lambda: 100.)
    await client.connect()
    await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
    actual = client.acquisition_context
    client.abort()
    behavior['capabilities'] = native_protocol_cases.CAPABILITIES | {'runtime_id': 'new-adapter'}
    session = SimpleNamespace(client=client, acquisition=actual)
    boundary = len(requests)
    result = await tool.stale_original_probes(session, tool.retained_mc_intent(old_intent_wire(actual), actual), Mock())
    assert result == {'reconciliation': 'native_release_runtime_changed',
                      'intent': 'native_session_stale', 'handoff': 'native_session_stale'}
    assert [row['operation'] for row in requests[boundary:]] == ['hello']
    assert client.session_identity is None
    assert client.acquisition_context is actual
    await client.close()


async def test_kill_boundary_failure_does_not_run_unconditional_old_hold(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    context = source_sample()[0]
    session = SimpleNamespace(acquisition=context, clock_domain=tool.read_monotonic_domain())
    monkeypatch.setattr(tool, 'quiesce', AsyncMock())
    calls = []
    async def step(args, isolation, log, operation):
        calls.append(operation)
        if operation == 'kill_a':
            raise ValueError('death_or_socket_proof_failed')
        return restart_clock_capture(context)
    monkeypatch.setattr(tool, 'restart_step', step)
    progress = {'original_cleanup_read_only': False}
    with pytest.raises(ValueError, match='death_or_socket_proof_failed'):
        await tool.process_restart(None, None, session, old_intent_wire(context), lambda *args: 1., progress,
                                   contract=CONTRACT)
    assert progress['original_cleanup_read_only'] is True
    assert calls == ['capture', 'kill_a']


async def test_original_source_mismatch_refuses_before_signal_or_publisher_changes(monkeypatch):
    from unittest.mock import AsyncMock
    context = source_sample()[0]
    captured = captured_owned(replace(context, token='f' * 32))
    step = AsyncMock(return_value={'owned': captured})
    monkeypatch.setattr(tool, 'restart_step', step)
    quiesce = AsyncMock(side_effect=AssertionError('source refusal must precede process actions'))
    monkeypatch.setattr(tool, 'quiesce', quiesce)
    progress = {'original_cleanup_read_only': False}
    with pytest.raises(ValueError, match='original_source_mismatch'):
        await tool.process_restart(None, None, SimpleNamespace(acquisition=context), old_intent_wire(context),
                                   Mock(), progress, contract=CONTRACT)
    assert step.await_count == 1 and step.call_args.args[-1] == 'capture'
    quiesce.assert_not_awaited()
    assert progress['original_cleanup_read_only'] is False


@pytest.mark.parametrize('correlated_cleanup', [True, False])
async def test_restart_separates_unknown_a_from_clean_backend_c_without_an_extra_old_handoff(
        tmp_path, monkeypatch, correlated_cleanup):
    from unittest.mock import AsyncMock

    from tests.fixtures.native_ownership import release_receipt
    original = source_sample()[0]
    replacement = replace(original, runtime_id='new-runtime', token='c' * 32,
        identity=replace(original.identity, binding=replace(original.identity.binding, connection_generation='clean-c')))
    client = SimpleNamespace(acquisition_context=original, close=AsyncMock())
    binding = SimpleNamespace(abort=Mock(), stop=AsyncMock(side_effect=tool.NativeGuidanceError('native_connection_unavailable')))
    session = SimpleNamespace(acquisition=original, client=client, binding=binding, run_started=10.,
                              clock_domain=tool.read_monotonic_domain())
    quiesced, order = [False], []
    async def quiesce(_):
        quiesced[0] = True
        order.append('quiesced')
    async def step(args, isolation, log, operation):
        order.append(operation)
        if operation == 'kill_a':
            assert quiesced[0] is False  # Keep the actual lease alive until the adapter crash.
        capture = restart_clock_capture(original)
        return {**capture, 'runtime_id': replacement.runtime_id, 'policy_matched': True,
                'signal_at_monotonic_s': 10.2, 'signal_begin_at_monotonic_s': 10.2,
                'clock_domains': capture['clock_domains'], 'death': {'original': capture['adapter_a']}}
    def child(argv, **kwargs):
        assert quiesced[0] is True
        assert order.index('recovery_ready') < order.index('prepare_c')
        output = Path(argv[argv.index('--output') + 1])
        output.mkdir()
        result = {'passed': True, 'final_release': {'local_sender_quiesced': True,
            'release_receipt': release_receipt(replacement).wire_payload()}} if correlated_cleanup else {'passed': True}
        (output / 'result.json').write_text(json.dumps(result))
        (output / 'acquisitions.jsonl').write_text(json.dumps({'acquisition': tool.asdict(replacement)}) + '\n')
        return SimpleNamespace(returncode=0, stdout='retained child result', stderr='')
    monkeypatch.setattr(tool, 'quiesce', quiesce)
    monkeypatch.setattr(tool, 'restart_step', step)
    monkeypatch.setattr(tool, 'stale_original_probes', AsyncMock())
    monkeypatch.setattr(tool.subprocess, 'run', child)
    args = SimpleNamespace(output=tmp_path, container='owned', instance=0, socket=tmp_path / 'native.sock',
        sih_build_manifest=tmp_path / 'build.json', config=tmp_path / 'config.yaml', follower='gm_velocity_vector',
        duration=3., test_altitude=30., stable_timeout=90., case='adapter_process_restart')
    progress = {'original_cleanup_read_only': False}
    call = tool.process_restart(args, {}, session, accepted_wire(original), lambda *args: 1., progress,
                                contract=CONTRACT)
    if correlated_cleanup:
        result = await call
        assert result['passed'] is True
        assert result['original_a']['released'] is False
        assert result['fresh_c']['final_release']['release_receipt']['acquisition']['runtime_id'] == 'new-runtime'
        assert order[-1] == 'final_identity'
    else:
        with pytest.raises(ValueError, match='fresh_cleanup_unconfirmed'):
            await call
    binding.stop.assert_awaited_once_with('ownership_restart_original_cleanup')
    assert client.acquisition_context is original
    assert progress['original_cleanup_read_only'] is True


def accepted_wire(context):
    engage = {'operation': 'engage', 'protocol_version': tool.PROTOCOL_VERSION, 'generation': 2, 'request_id': 3,
              'payload': {'identity': tool.asdict(context.identity), 'token': context.token}}
    intent = old_intent_wire(context)[0]['value'] | {'protocol_version': tool.PROTOCOL_VERSION,
                                                   'generation': 2, 'request_id': 4}
    def row(timestamp, direction, value):
        return {'timestamp': timestamp, 'connection': 1, 'direction': direction, 'value': value}
    return [row(.01, 'request_forward_attempt', engage),
        row(.02, 'actual_backend_reply', {'protocol_version': tool.PROTOCOL_VERSION, 'generation': 2, 'request_id': 3,
            'success': True, 'payload': {'owner_confirmed': True, 'runtime_id': context.runtime_id,
                                        'acquisition': context.wire_payload()}}),
        row(.1, 'request_forward_attempt', intent),
        row(.12, 'actual_backend_reply', {'protocol_version': tool.PROTOCOL_VERSION, 'generation': 2, 'request_id': 4,
            'success': True, 'payload': {'owner_confirmed': True, 'accepted_sequence': 7}})]


def restart_clock_capture(context):
    from copy import deepcopy
    host = tool.read_monotonic_domain()
    helper, adapter = deepcopy(host), deepcopy(host)
    helper['pid'], adapter['pid'] = 30, 20
    for value in (helper, adapter):
        for namespace in value['namespaces'].values():
            namespace['inode'] += 1
    return {'owned': captured_owned(context), 'adapter_a': {'pid': 20},
            'clock_domains': {'host': host, 'helper': helper, 'adapter': adapter}}


def lease_proof(events, context, **changes):
    capture = restart_clock_capture(context)
    values = {'signal_at_monotonic_s': 10.2, 'signal_begin_at_monotonic_s': 10.2, 'run_started': 10.,
              'capture': capture, 'signal_domains': capture['clock_domains'],
              'host_clock': capture['clock_domains']['host']} | changes
    return tool.accepted_intent_at_signal(events, context, **values)


def test_live_signal_proof_uses_actual_original_ack_and_archived_host_origin_without_restamp():
    context = source_sample()[0]
    proof = lease_proof(accepted_wire(context), context)
    assert proof['request_key'] == (1, 2, 4) and proof['engage_key'] == (1, 2, 3)
    assert proof['ack_at_monotonic_s'] == pytest.approx(10.12)
    assert proof['intent_created_at_monotonic_s'] == 10.
    assert proof['intent_expires_at_monotonic_s'] == 10.3
    assert proof['remaining_original_lease_s'] == pytest.approx(.1)


@pytest.mark.parametrize('change', ['missing_ack', 'after_signal', 'connection', 'generation', 'request_id',
    'sequence', 'bool_sequence', 'owner_false', 'success_false', 'identity', 'token', 'phase',
    'engage_context', 'engage_runtime', 'protocol', 'repeated_request'])
def test_live_signal_proof_refuses_unpaired_or_other_context_ack(change):
    context = source_sample()[0]
    rows = accepted_wire(context)
    reply = rows[-1]
    if change == 'missing_ack':
        rows.pop()
    elif change == 'after_signal':
        reply['timestamp'] = .21
    elif change == 'connection':
        reply['connection'] = 2
    elif change in ('generation', 'request_id'):
        reply['value'][change] += 1
    elif change == 'sequence':
        reply['value']['payload']['accepted_sequence'] = 8
    elif change == 'bool_sequence':
        reply['value']['payload']['accepted_sequence'] = True
    elif change == 'owner_false':
        reply['value']['payload']['owner_confirmed'] = False
    elif change == 'success_false':
        reply['value']['success'] = False
    elif change in ('identity', 'token', 'phase'):
        rows[-2]['value']['payload'][change] = {'identity': {}, 'token': 'f' * 32, 'phase': 'fixed_wing'}[change]
    elif change == 'engage_context':
        rows[1]['value']['payload']['acquisition']['source_revision'] += 1
    elif change == 'engage_runtime':
        rows[1]['value']['payload']['runtime_id'] = 'replacement'
    elif change == 'protocol':
        reply['value']['protocol_version'] -= 1
    else:
        rows.insert(3, rows[2])
    with pytest.raises(ValueError):
        lease_proof(rows, context)


@pytest.mark.parametrize('expiry', [10.15, 10.2])
def test_latest_accepted_intent_expired_at_signal_fails_even_with_newer_unacked_request(expiry):
    from copy import deepcopy
    context = source_sample()[0]
    rows = accepted_wire(context)
    rows[2]['value']['payload']['expires_at_monotonic_s'] = expiry
    newer = deepcopy(rows[2])
    newer['timestamp'] = .16
    newer['value']['request_id'] = 5
    newer['value']['payload'].update(sequence=8, created_at_monotonic_s=10.16, expires_at_monotonic_s=11.)
    rows.append(newer)
    with pytest.raises(ValueError, match='accepted_intent_expired_before_signal'):
        lease_proof(rows, context)


def test_latest_actual_accepted_deadline_wins_over_an_older_longer_deadline():
    from copy import deepcopy
    context = source_sample()[0]
    rows = accepted_wire(context)
    newer = deepcopy(rows[2:])
    newer[0]['timestamp'], newer[1]['timestamp'] = .14, .16
    for row in newer:
        row['value']['request_id'] = 5
    newer[0]['value']['payload'].update(sequence=8, created_at_monotonic_s=10.14, expires_at_monotonic_s=10.19)
    newer[1]['value']['payload']['accepted_sequence'] = 8
    with pytest.raises(ValueError, match='accepted_intent_expired_before_signal'):
        lease_proof(rows + newer, context)


def test_signal_proof_refuses_unknown_host_container_clock_relationship():
    context = source_sample()[0]
    capture = restart_clock_capture(context)
    capture['clock_domains']['helper']['timens_offsets'] = 'monotonic 1 0\nboottime 0 0\n'
    with pytest.raises(ValueError, match='signal_clock_unqualified'):
        lease_proof(accepted_wire(context), context, capture=capture)


@pytest.mark.parametrize('change', ['missing', 'boot', 'offset', 'children', 'pid', 'target_namespace'])
def test_signal_proof_recomputes_required_original_clock_evidence(change):
    from copy import deepcopy
    context = source_sample()[0]
    capture = restart_clock_capture(context)
    signal_domains = deepcopy(capture['clock_domains'])
    if change == 'missing':
        signal_domains = None
    elif change == 'boot':
        signal_domains['helper']['boot_id'] = '12345678-1234-1234-1234-123456789abc'
    elif change == 'offset':
        signal_domains['adapter']['timens_offsets'] = 'monotonic 1 0\nboottime 0 0\n'
    elif change == 'children':
        signal_domains['helper']['namespaces']['time_for_children']['inode'] += 1
    elif change == 'pid':
        signal_domains['adapter']['pid'] += 1
    else:
        for namespace in signal_domains['adapter']['namespaces'].values():
            namespace['inode'] += 1
    with pytest.raises(ValueError, match='signal_clock_unqualified'):
        lease_proof(accepted_wire(context), context, capture=capture, signal_domains=signal_domains)


def test_ack_during_signal_syscall_bracket_cannot_be_claimed_pre_signal():
    context = source_sample()[0]
    with pytest.raises(ValueError, match='accepted_intent_not_observed_before_signal'):
        lease_proof(accepted_wire(context), context, signal_begin_at_monotonic_s=10.11)


def test_syscall_scheduling_delay_past_original_expiry_cannot_qualify_live_crash():
    context = source_sample()[0]
    with pytest.raises(ValueError, match='accepted_intent_expired_before_signal'):
        lease_proof(accepted_wire(context), context, signal_at_monotonic_s=10.31)


async def test_releasing_neutral_drain_source_cannot_qualify_crash_before_signal(monkeypatch):
    from unittest.mock import AsyncMock
    context = source_sample()[0]
    source = captured_owned(context) | {'state': CONTRACT['states']['acquired'] + 1}
    step = AsyncMock(return_value={'owned': source})
    monkeypatch.setattr(tool, 'restart_step', step)
    with pytest.raises(ValueError, match='original_source_mismatch'):
        await tool.process_restart(None, None, SimpleNamespace(acquisition=context), accepted_wire(context),
            Mock(), {'original_cleanup_read_only': False}, contract=CONTRACT)
    assert step.await_count == 1


@pytest.mark.parametrize('change', ['missing', 'boot', 'offset', 'children', 'pid', 'wire_host'])
async def test_unqualified_restart_clock_refuses_before_process_signal(monkeypatch, change):
    from unittest.mock import AsyncMock
    context = source_sample()[0]
    capture = restart_clock_capture(context)
    host_clock = tool.read_monotonic_domain()
    if change == 'missing':
        capture['clock_domains'] = {}
    elif change == 'boot':
        capture['clock_domains']['helper']['boot_id'] = '12345678-1234-1234-1234-123456789abc'
    elif change == 'offset':
        capture['clock_domains']['adapter']['timens_offsets'] = 'monotonic 1 0\nboottime 0 0\n'
    elif change == 'children':
        capture['clock_domains']['helper']['namespaces']['time_for_children']['inode'] += 1
    elif change == 'pid':
        capture['clock_domains']['adapter']['pid'] += 1
    else:
        host_clock['pid'] += 1
    session = SimpleNamespace(acquisition=context, clock_domain=host_clock)
    calls = []
    async def step(args, isolation, log, operation):
        calls.append(operation)
        if operation == 'kill_a':
            raise AssertionError('clock qualification must precede destruction')
        return capture
    monkeypatch.setattr(tool, 'restart_step', step)
    monkeypatch.setattr(tool, 'quiesce', AsyncMock())
    progress = {'original_cleanup_read_only': False}
    with pytest.raises(ValueError, match='clock_unqualified'):
        await tool.process_restart(None, None, session, old_intent_wire(context), Mock(), progress,
                                   contract=CONTRACT)
    assert calls == ['capture']
    assert progress['original_cleanup_read_only'] is False


@pytest.mark.parametrize('airframe', ['pure_fixed_wing', 'settled_vtol_mc', 'settled_vtol_fw'])
async def test_replacement_run_keeps_selected_airframe_at_both_session_boundaries(tmp_path, monkeypatch, airframe):
    import time
    from dataclasses import asdict
    from unittest.mock import AsyncMock

    from classes.native_guidance import NativeCapabilities, NativeGuidanceError
    from tests.fixtures.native_ownership import release_receipt
    from tests.unit.drone_interface.test_aircraft_state import aircraft_state

    mc = airframe == 'settled_vtol_mc'
    is_vtol = airframe != 'pure_fixed_wing'
    capabilities = NativeCapabilities('test-adapter', 'synthetic-fixture', 2, True, is_vtol, False, True, 23)
    client = SimpleNamespace(acquisition_context=None)
    client.connect = AsyncMock(return_value=capabilities)

    async def bind(aircraft):
        client.binding = aircraft

    client.bind = AsyncMock(side_effect=bind)
    client.close = AsyncMock()

    async def observe():
        receipt = release_receipt(client.acquisition_context,
                                  timestamp=client.acquisition_context.activation_timestamp + 100)
        return {'fresh': True, 'owner_confirmed': False, 'rescue_active': False, 'nav_state': 4,
                'nav_state_timestamp': receipt.observed_nav_state_timestamp, 'publications': 2,
                'release_receipt': receipt.wire_payload(),
                'phase_source_health': {'vehicle_status_timeout_s': 1., 'vehicle_status_age_s': 0.}}

    client.observe = AsyncMock(side_effect=observe)
    monkeypatch.setattr(tool, 'NativeGuidanceClient', Mock(return_value=client))

    class Recorder:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(tool, 'WireRecorder', Recorder)
    monkeypatch.setattr(tool, 'native_parameters', Mock(return_value='synthetic parameter snapshot'))
    monkeypatch.setattr(tool, 'archive_configuration', Mock(return_value={}))
    monkeypatch.setattr(tool.Parameters, 'load_config', Mock())
    stable_airframes, session_airframes, sessions = [], [], []

    async def stable(client, connection, *, airframe='pure_fixed_wing', **kwargs):
        state = aircraft_state(binding=client.binding, sequence=len(stable_airframes) + 1,
                               observed_at_monotonic_s=time.monotonic(), relative_altitude_m=30.,
                               is_vtol=is_vtol, phase=tool.AirframePhase.MULTICOPTER if mc else tool.AirframePhase.FIXED_WING)
        # The real production validator refuses the wrong replacement strategy.
        tool.require_airframe(state, airframe)
        assert connection.commit_aircraft_state(state)
        stable_airframes.append(airframe)

    def create(client, connection, capabilities, owner, config, profile, log, *, run_started,
               airframe='pure_fixed_wing'):
        tool.require_airframe(connection.get_aircraft_state(), airframe)
        session_airframes.append(airframe)
        context = acquisition(owner, token=f'{len(sessions) + 1:032x}',
                              activation_timestamp=200 + len(sessions) * 100)
        session = SimpleNamespace(acquisition=context, commander=SimpleNamespace(successful_publishes=1))

        async def stop(reason):
            if client.acquisition_context != context:
                raise NativeGuidanceError('native_session_replaced')
            return {'executed': True, 'release_receipt': asdict(release_receipt(
                context, timestamp=context.activation_timestamp + 100))}

        session.binding = SimpleNamespace(stop=AsyncMock(side_effect=stop), abort=Mock())
        sessions.append(session)
        return session

    async def activate(session, log):
        client.acquisition_context = session.acquisition

    monkeypatch.setattr(tool, 'stable_aircraft', AsyncMock(side_effect=stable))
    monkeypatch.setattr(tool, 'create_session', Mock(side_effect=create))
    monkeypatch.setattr(tool, 'activate_session', AsyncMock(side_effect=activate))
    monkeypatch.setattr(tool, 'drive', AsyncMock())
    monkeypatch.setattr(tool, 'confirmed_source', AsyncMock())
    monkeypatch.setattr(tool, 'retired_owner', AsyncMock(return_value=(None, 0.)))
    monkeypatch.setattr(tool, 'reconcile', AsyncMock(side_effect=lambda session, log:
        release_receipt(session.acquisition, outcome='owner_already_released')))
    monkeypatch.setattr(tool, 'user_mode', AsyncMock())
    monkeypatch.setattr(tool, 'quiesce', AsyncMock())
    config = tmp_path / 'config.yaml'
    config.write_text('Follower: {}\n')
    output = tmp_path / 'evidence'
    args = SimpleNamespace(output=output, config=config, follower='gm_velocity_vector',
                           case='stale_cleanup_new_acquisition', airframe=airframe, socket=tmp_path / 'native.sock',
                           stable_timeout=1., test_altitude=30., duration=.01)
    result = await tool.run(args, {'aircraft_uid': '123'}, CONTRACT)
    assert result['passed'] is True, result
    assert result['response_checks']['late_cleanup_rejected'] is True
    assert result['response_checks']['distinct_acquisition'] is True
    assert result['response_checks']['same_semantic_identity'] is True
    assert result['response_checks']['replacement_preserved'] is True
    assert stable_airframes == session_airframes == [airframe, airframe]
    assert len(sessions) == 2 and client.acquisition_context == sessions[1].acquisition
    assert json.loads((output / 'manifest.json').read_text())['airframe'] == airframe


@pytest.mark.parametrize('airframe,phase,is_vtol,accepted', [
    ('pure_fixed_wing', 'fixed_wing', False, True),
    ('pure_fixed_wing', 'fixed_wing', True, False),
    ('pure_fixed_wing', 'multicopter', False, False),
    ('settled_vtol_mc', 'multicopter', True, True),
    ('settled_vtol_mc', 'multicopter', False, False),
    ('settled_vtol_mc', 'fixed_wing', True, False),
    ('settled_vtol_mc', 'vtol_transition', True, False),
    ('settled_vtol_fw', 'fixed_wing', True, True),
    ('settled_vtol_fw', 'fixed_wing', False, False),
    ('settled_vtol_fw', 'multicopter', True, False),
    ('settled_vtol_fw', 'vtol_transition', True, False),
])
def test_explicit_airframe_requires_its_actual_kind_and_settled_phase(airframe, phase, is_vtol, accepted):
    from tests.unit.drone_interface.test_aircraft_state import aircraft_state

    state = aircraft_state(phase=tool.AirframePhase(phase), is_vtol=is_vtol)
    if accepted:
        tool.require_airframe(state, airframe)
    else:
        with pytest.raises(ValueError, match='ownership_fixture_requires_' + airframe):
            tool.require_airframe(state, airframe)


@pytest.mark.parametrize('airframe', ['pure_fixed_wing', 'settled_vtol_fw'])
def test_restart_cli_still_refuses_every_non_mc_airframe_before_external_operations(tmp_path, monkeypatch, capsys, airframe):
    forbidden = Mock(side_effect=AssertionError('wrong restart airframe must refuse before external operations'))
    monkeypatch.setattr(tool, 'verify_simulator', forbidden)
    monkeypatch.setattr(tool, 'run', forbidden)
    with pytest.raises(SystemExit) as error:
        tool.main(['--case', 'adapter_process_restart', '--airframe', airframe,
            '--restart-plan', str(tmp_path / 'plan.json'), '--socket', str(tmp_path / 'native.sock'),
            '--container', 'synthetic-fixture', '--instance', '0',
            '--sih-build-manifest', str(tmp_path / 'manifest.json'), '--output', str(tmp_path / 'output')])
    assert error.value.code == 2
    assert 'adapter_process_restart requires --airframe settled_vtol_mc' in capsys.readouterr().err
    forbidden.assert_not_called()
