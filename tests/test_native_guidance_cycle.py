"""Synthetic closed-log/orchestration checks; never start Docker or a simulator."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest
import yaml

from classes.aircraft_state import AircraftBinding, GuidanceSessionIdentity, AirframePhase
from tests.fixtures.native_ownership import acquisition, release_receipt
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tools import run_native_guidance_cycle as cycle
from tools import run_native_vector_sih as vector
from tools.native_guidance_evidence import ownership_interval


def context(name='first', *, token='1', timestamp=200000, connection='same-app-connection'):
    identity = GuidanceSessionIdentity(name, AircraftBinding('42', connection, 1), 1)
    return acquisition(identity, token=token.zfill(32), activation_timestamp=timestamp)


def synthetic_log(*, phase=400000, end=400000, filled_native_topic=False):
    stamps = np.arange(100000, 1000001, 50000, dtype=np.int64)
    active = (stamps >= 200000) & (stamps < end)
    owned = dict(timestamp=stamps, autopilot_uid=np.full(len(stamps), 42),
        owner_active=active, rescue_active=np.zeros(len(stamps)), registration_id=np.ones(len(stamps)),
        source_revision=np.full(len(stamps), 7), source_nav_state_timestamp=np.full(len(stamps), 100),
        source_nav_state=np.full(len(stamps), 4), acquired_nav_state_timestamp=np.full(len(stamps), 200000),
        nav_state=np.where(active, 23, 4), **{'incarnation[0]': np.zeros(len(stamps)),
        'incarnation[1]': np.full(len(stamps), 2), 'token[0]': np.zeros(len(stamps)),
        'token[1]': np.where(stamps >= 200000, 1, 0)})
    pub_end = end if filled_native_topic else min(end, phase)
    pose = dict(timestamp=stamps, timestamp_sample=stamps.copy(), ref_alt=np.full(len(stamps), 500.), ref_timestamp=np.ones(len(stamps)),
        z=np.where(stamps < phase, -30., -47.))
    for field in ['x', 'y', 'vx', 'vy', 'vz']: pose[field] = np.zeros(len(stamps))
    for field in ['xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid']:
        pose[field] = np.ones(len(stamps))
    for field in ['xy_reset_counter', 'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter', 'heading_reset_counter']:
        pose[field] = np.zeros(len(stamps))
    attitude = dict(timestamp=stamps, timestamp_sample=stamps,
        **{'q[0]': np.ones(len(stamps)), 'q[1]': np.zeros(len(stamps)),
           'q[2]': np.zeros(len(stamps)), 'q[3]': np.zeros(len(stamps))})
    data = {'owned_mode_status': owned, 'vehicle_local_position': pose,
        'vehicle_local_position_groundtruth': {key: pose[key].copy() for key in ['timestamp', 'x', 'y', 'z', 'vx', 'vy', 'vz']},
        'home_position': dict(timestamp=np.array([100000]), valid_alt=np.array([True]), alt=np.array([500.])),
        'vehicle_attitude': attitude, 'trajectory_setpoint': dict(timestamp=np.arange(200000, pub_end, 50000)),
        'vehicle_status': dict(timestamp=stamps, in_transition_mode=stamps >= phase,
                               nav_state=np.where(active, 23, 4),
                               nav_state_timestamp=np.where(stamps < 200000, 100, np.where(stamps < end, 200000, end)),
                               vehicle_type=np.where(stamps < phase, 1, 2))}
    return SimpleNamespace(get_dataset=lambda name: SimpleNamespace(data=data[name]),
        dropouts=[], file_corruption=False), data


def audit(log, count=4):
    ctx = context()
    receipt = release_receipt(ctx, outcome='owner_already_released', nav_state=23, timestamp=ctx.activation_timestamp)
    return ownership_interval(log, asdict(ctx), asdict(receipt),
        vehicle_type=1, initial_altitude_m=30., phase_exit_required=True, publication_counter_delta=count)


def test_native_zoom_is_separate_without_peak_subtraction_but_authority_gate_is_hard():
    log, data = synthetic_log()
    result = audit(log)
    assert result['passed'] and result['maximum_pursuit_altitude_error_m'] == 0.
    assert max(abs(data['vehicle_local_position']['z'] + 30)) == 17.
    assert result['pursuit_interval_us'] == result['retained_authority_interval_us'] == [200000, 400000]
    log, _ = synthetic_log(end=800000)
    result = audit(log)
    assert not result['passed'] and result['checks']['pursuit_altitude_within_2m']
    assert not result['checks']['authority_publication_gaps_within_100ms']
    assert result['retained_authority_interval_us'] == [200000, 800000]


def test_shared_native_topic_cannot_fill_a_drain_gap_or_replace_missing_counter_attribution():
    log, _ = synthetic_log(end=800000, filled_native_topic=True)
    result = audit(log)
    assert result['checks']['authority_publication_gaps_within_100ms']
    assert not result['checks']['native_publication_source_attributed'] and not result['passed']
    log, _ = synthetic_log()
    assert not audit(log, count=None)['passed']


def test_status_publication_is_not_the_acquisition_or_exit_epoch():
    log, data = synthetic_log()
    data['owned_mode_status']['timestamp'] = data['owned_mode_status']['timestamp'].copy() + 4000
    result = audit(log)
    assert result['passed'] and result['pursuit_interval_us'] == [200000, 400000]
    assert result['first_active_status_publication_us'] == 204000
    assert result['inactive_status_publication_us'] == 404000
    assert result['native_mode_exit_epoch_us'] == 400000


@pytest.mark.parametrize('bad', ['reactivated', 'token', 'flags', 'reset', 'reference', 'attitude', 'clock', 'dropout', 'raw_x', 'truth_vx'])
def test_bad_native_source_or_pose_cannot_qualify_by_phase_masking(bad):
    log, data = synthetic_log()
    if bad == 'reactivated': data['owned_mode_status']['owner_active'][-1] = True
    elif bad == 'token': data['owned_mode_status']['token[1]'][2:6] = 3
    elif bad == 'flags': data['vehicle_local_position']['z_valid'][3] = False
    elif bad == 'reset': data['vehicle_local_position']['z_reset_counter'][3] = 1
    elif bad == 'reference': data['vehicle_local_position']['ref_alt'][3] += 1.
    elif bad == 'attitude': data['vehicle_attitude']['q[0]'][3] = np.nan
    elif bad == 'clock': data['vehicle_local_position']['timestamp'][3] = data['vehicle_local_position']['timestamp'][2]
    elif bad == 'raw_x': data['vehicle_local_position']['x'][3] = np.nan
    elif bad == 'truth_vx': data['vehicle_local_position_groundtruth']['vx'][3] = np.nan
    else: log.dropouts = [1]
    try:
        result = audit(log)
    except ValueError:
        return
    assert not result['passed']


def test_stale_native_position_sample_fails_even_when_publication_and_height_are_fresh():
    log, data = synthetic_log()
    for item in data.values():
        for key in ['timestamp', 'timestamp_sample']:
            if key in item: item[key] = item[key].copy() + 1000000
    data['owned_mode_status']['acquired_nav_state_timestamp'] += 1000000
    epochs = data['vehicle_status']['nav_state_timestamp']
    data['vehicle_status']['nav_state_timestamp'] = np.where(epochs >= 200000, epochs + 1000000, epochs)
    data['vehicle_local_position']['timestamp_sample'] -= 800000
    ctx = replace(context(), activation_timestamp=1200000)
    receipt = release_receipt(ctx, outcome='owner_already_released', nav_state=23, timestamp=ctx.activation_timestamp)
    result = ownership_interval(log, asdict(ctx), asdict(receipt), vehicle_type=1,
        initial_altitude_m=30., phase_exit_required=True, publication_counter_delta=4)
    assert result['maximum_pursuit_altitude_error_m'] == 0.
    assert not result['checks']['full_raw_pose_finite_and_fresh'] and not result['passed']


def test_native_motion_and_late_hold_or_intent_cannot_make_pursuit_checks_pass():
    rows = [dict(timestamp=0., altitude_m=30., range_m=100., pursuit_active=True),
        dict(timestamp=1., altitude_m=29.9, range_m=101., pursuit_active=True),
        dict(timestamp=2., altitude_m=47., range_m=1., pursuit_active=False)]
    original = deepcopy(rows)
    active = vector.pursuit_response(rows, 30.)
    assert active['range_end_m'] > active['range_start_m'] and active['final_altitude_m'] == 29.9
    assert rows == original and max(x['altitude_m'] for x in rows) == 47.
    for operation in ['intent', 'handoff', 'engage']:
        wire = [dict(direction='request_forward_attempt', timestamp=2.1,
                     value=dict(operation=operation, payload={}))]
        assert not vector.transition_fence_checks(wire, {'timestamp': 2.})['no_write_after_phase_witness']


def test_new_session_does_not_require_a_network_reconnect_but_does_require_new_authority():
    first, second = context(), context('second', token='3', timestamp=500000)
    cycle.require_fresh_start(asdict(first), asdict(second))
    for changed in [replace(second, token=first.token), replace(second, identity=first.identity),
                    replace(second, activation_timestamp=first.activation_timestamp)]:
        with pytest.raises(ValueError): cycle.require_fresh_start(asdict(first), asdict(changed))


@pytest.mark.parametrize('outcome', ['hold_confirmed', 'owner_already_released'])
@pytest.mark.parametrize('bad', [None, 'active', 'stale', 'receipt', 'executed', 'reason', 'hold_epoch'])
def test_phase_exit_accepts_both_correlated_native_outcomes_without_a_new_handoff(outcome, bad):
    ctx = context()
    held = outcome == 'hold_confirmed'
    receipt = release_receipt(ctx, outcome=outcome, nav_state=4 if held else 23,
                              timestamp=400000 if held else ctx.activation_timestamp)
    handoff = dict(release_receipt=asdict(receipt), local_sender_quiesced=True, executed=held,
        reason='aircraft_transition_observed' if held else 'native_owner_already_released')
    packet = dict(release_receipt=asdict(receipt), runtime_id=ctx.runtime_id, fresh=True,
        aircraft_state=dict(binding=asdict(ctx.identity.binding)), owner_confirmed=False, rescue_active=False,
        phase_status_fresh=True, release_pending=False, neutral_drain_active=False,
        nav_state=4 if held else 6, nav_state_timestamp=400000)
    if bad == 'active': packet['owner_confirmed'] = True
    elif bad == 'stale': packet['fresh'] = False
    elif bad == 'receipt': packet['release_receipt'] = None
    elif bad == 'executed': handoff['executed'] = not held
    elif bad == 'reason': handoff['reason'] = 'ordinary_stop'
    elif bad == 'hold_epoch': packet['nav_state_timestamp'] += 1
    assert vector.phase_exit_release_confirmed(handoff, ctx, packet) is (
        bad is None or bad == 'hold_epoch' and not held)
    # Retirement cannot authorize any new intent/handoff, for either native outcome.
    wire = [dict(timestamp=2.1, direction='request_forward_attempt', value={'operation': 'handoff', 'payload': {}})]
    assert not vector.transition_fence_checks(wire, {'timestamp': 2.})['no_write_after_phase_witness']


def test_dry_run_and_invalid_fixture_never_stage_or_launch(tmp_path, monkeypatch, capsys):
    launch = Mock(side_effect=AssertionError('runtime in dry-run'))
    monkeypatch.setattr(cycle.base, 'verified_runtime', launch)
    output = tmp_path / 'absent'
    assert cycle.main(['--mount', 'HORIZONTAL', '--output', str(output)]) == 0
    assert not output.exists() and not launch.called
    assert json.loads(capsys.readouterr().out)['execute'] is False
    raw = json.loads(cycle.CASE.read_text());raw['mc']['transition_at_s'] = float('nan')
    path = tmp_path / 'invalid.json';path.write_text(json.dumps(raw))
    with pytest.raises(ValueError): cycle.case(path)


def test_one_actual_pose_anchor_and_clock_are_preserved_across_the_two_scenarios(tmp_path, monkeypatch):
    monkeypatch.setattr(vector, 'host_boot_id', lambda: '11111111-1111-1111-1111-111111111111')
    state = aircraft_state(binding=AircraftBinding('42', 'conn', 1), is_vtol=True, navigation_heading_rad=.3)
    initial = dict(aircraft_state=asdict(state), vehicle_pose=dict(vehicle_ned=[10., 20., -30.]))
    paths, artifact = cycle.world_scenarios(tmp_path, initial, 'VERTICAL', cycle.case(cycle.CASE), clock=lambda: 100.)
    original = artifact.read_bytes()
    target = vector.WorldTargetClock.from_file(artifact, now=101.)
    for path in paths:
        raw = yaml.safe_load(path.read_text());target.require_matching_target(raw)
        assert raw['mount_type'] == 'VERTICAL' and raw['evidence_provenance'] == 'px4_gazebo'
    for now in (101., 140.):
        target.require_current(now=now)
        assert target.target_at_host(now) != target.target_at_host(now + 1.)
    assert artifact.read_bytes() == original


@pytest.mark.parametrize('phase', [AirframePhase.VTOL_TRANSITION, AirframePhase.UNKNOWN, AirframePhase.MULTICOPTER])
def test_transition_unknown_or_old_phase_never_selects_the_fresh_fw_start(phase):
    packet = dict(aircraft_state=asdict(aircraft_state(phase=phase, is_vtol=True)), owner_confirmed=False,
        rescue_active=False, phase_status_fresh=True, release_pending=False, neutral_drain_active=False)
    checks = {key: True for key in ['phase_exit_release_confirmed', 'no_write_after_phase_witness',
        'no_publication_after_stop', 'no_publication_failure', 'pilot_transition_command_succeeded',
        'requested_phase_settled', 'backend_transition_ended']}
    assert not cycle.next_start_allowed({'response_checks': checks}, {'last_packet': packet})


def test_explicit_build_authority_reaches_component_cli_before_a_client(tmp_path, monkeypatch):
    verify = Mock(return_value={'simulator': 'gazebo'})
    monkeypatch.setattr(vector, 'verify_simulator', verify)
    client = Mock(side_effect=AssertionError('client in dry-run'))
    monkeypatch.setattr(vector, 'NativeGuidanceClient', client)
    manifest, authority = tmp_path / 'build.json', tmp_path / 'authority'
    vector.main(['--container', 'original', '--instance', '0', '--socket', str(tmp_path/'native.sock'),
        '--output', str(tmp_path/'out'), '--mount', 'HORIZONTAL', '--simulation-build-manifest', str(manifest),
        '--build-repository', str(authority)])
    verify.assert_called_once_with('original', 0, tmp_path/'native.sock', simulation_build_manifest=manifest,
                                  build_repository=authority)
    assert not client.called


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['qualified', 'unknown_native_attribution', 'component_failure'])
async def test_real_cycle_flow_keeps_native_zoom_separate_and_cleanup_unconditional(tmp_path, monkeypatch, outcome):
    import pyulog

    output = tmp_path / 'fresh-run'
    initial = dict(aircraft_state=asdict(aircraft_state(is_vtol=True, phase=AirframePhase.MULTICOPTER)),
                   vehicle_pose=dict(vehicle_ned=[0., 0., -30.]))
    def cleanup():
        folder = output / 'simulator/rootfs';folder.mkdir(parents=True)
        (folder / 'synthetic.ulg').write_bytes(b'SYNTHETIC parser fixture; never native evidence')
        return []
    runtime = SimpleNamespace(output=output, manifest={'build': {}}, socket=tmp_path/'socket',
        primary='original-primary', isolation={}, start=lambda: output.mkdir(), verify=Mock(),
        clock=Mock(return_value={'incarnation': '2'.zfill(32), 'source_clock_us': 100000}),
        cleanup=Mock(side_effect=cleanup))
    monkeypatch.setattr(cycle.base, 'verified_runtime', Mock(return_value=(runtime, {}, 'gazebo')))
    client = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(cycle, 'NativeGuidanceClient', Mock(return_value=client))
    monkeypatch.setattr(cycle.base, 'admit_native_runtime', AsyncMock(return_value=(SimpleNamespace(runtime_id='test'), None)))
    monkeypatch.setattr(cycle.base, 'wait_stable', AsyncMock(return_value=initial))
    clock = output / 'original-clock.json'
    monkeypatch.setattr(cycle, 'world_scenarios', Mock(return_value=([tmp_path/'mc.yaml', tmp_path/'fw.yaml'], clock)))
    monkeypatch.setattr(vector, 'transition_source_contract', Mock(return_value={'vehicle_types': {'multicopter': 1, 'fixed_wing': 2}}))
    contexts = [context('mc'), context('fw', token='3', timestamp=500000)]
    calls = []
    async def component(args, isolation):
        calls.append(args)
        if outcome == 'component_failure': raise RuntimeError('component publication failed')
        args.output.mkdir()
        ctx = contexts[len(calls)-1]
        (args.output/'acquisition.json').write_text(json.dumps(asdict(ctx)))
        checks = {key: True for key in ('phase_exit_release_confirmed', 'no_write_after_phase_witness',
            'no_publication_after_stop', 'no_publication_failure', 'pilot_transition_command_succeeded',
            'requested_phase_settled', 'backend_transition_ended')}
        if len(calls) == 1:
            packet = dict(aircraft_state=asdict(aircraft_state(is_vtol=True, phase=AirframePhase.FIXED_WING)),
                owner_confirmed=False, rescue_active=False, phase_status_fresh=True,
                release_pending=False, neutral_drain_active=False)
            (args.output/'post-transition-settled.json').write_text(json.dumps({'last_packet': packet}))
        return dict(passed=True, response_checks=checks, handoff={'release_receipt': asdict(release_receipt(ctx, timestamp=800000))},
                    initial_relative_altitude_m=30., native_publication_counter={'before': 0, 'after': 4})
    monkeypatch.setattr(vector, 'run', component)
    fake_log = SimpleNamespace(last_timestamp=1000000, get_dataset=lambda _: SimpleNamespace(data={
        'incarnation[0]': [0, 0, 0], 'incarnation[1]': [2, 2, 2],
        'token[0]': [0, 0, 0], 'token[1]': [1, 3, 3], 'owner_active': [True, True, False]}))
    monkeypatch.setattr(pyulog, 'ULog', lambda _: fake_log)
    monkeypatch.setattr(cycle.base, 'audit_ulog', Mock(return_value={'passed': False, 'maximum_excursion_m': 17.}))
    monkeypatch.setattr(cycle, 'ownership_interval', Mock(return_value={
        'passed': outcome != 'unknown_native_attribution', 'source_attribution': 'UNKNOWN' if outcome == 'unknown_native_attribution' else 'corroborated'}))
    result = await cycle.execute(SimpleNamespace(mount='HORIZONTAL', config=tmp_path/'config',
        build_repository=None, simulation_build_manifest=tmp_path/'build.json'), cycle.case(cycle.CASE))
    runtime.cleanup.assert_called_once()
    assert client.close.await_count == 1
    assert result['passed'] is (outcome == 'qualified')
    if outcome == 'component_failure':
        assert len(calls) == 1 and 'component publication failed' in str(result['errors'])
    else:
        assert [call.initial_phase for call in calls] == ['multicopter', 'fixed_wing']
        assert calls[0].target_clock == calls[1].target_clock == clock
        assert result['full_native_capture']['passed'] is False
        assert result['application_startup_qualified'] is result['same_application_connection_qualified'] is False
