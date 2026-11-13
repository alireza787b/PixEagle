"""Isolated native SIH harness gates; these tests never command an aircraft."""

from copy import deepcopy
from dataclasses import asdict, replace
import asyncio
import json
import hashlib
import math
import socket
import subprocess
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml

from classes.aircraft_state import AirframePhase, GuidanceSessionIdentity, Quaternion
from classes.follower import FollowerFactory
from classes.native_follow_binding import NativeFollowBinding
from classes.native_guidance import NativeCapabilities
from classes.parameters import Parameters
from classes.target_continuity import (
    ContinuityContext, ContinuityPolicy, IdentityVerdict, TargetContinuitySupervisor,
    TargetEvidenceSnapshot, TargetEvidenceState,
)
from classes.tracker_output import TrackerDataType
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing
from tests.unit.followers import test_fw_navigation_chase_follower as native_image_cases
from tools.run_native_vector_sih import (
    ROOT, AirspeedLossInjection, ObservationConnection, airspeed_fault_response_checks,
    archive_configuration, attach_component_observer, cleanup_component_run,
    component_fault_windows, component_loss_windows, component_profile,
    component_target_evidence, image_fixture, gimbal_fixture, bind_component_fixture,
    load_component_scenario, loss_tracker_output, measurement_time, measurement_world_target,
    native_airspeed_failure, native_parameters, observed_airspeed_status, observed_pose_record,
    phase_response_segments, require_airspeed_failure_injection,
    prepare_component_intent, project_component_input, stable_window,
    verify_simulator,
)
from tools import run_native_vector_sih as tool
from tests.fixtures.native_ownership import acquisition, release_receipt


native_follower_environment = native_image_cases.environment


def world_clock_fixture(tmp_path, monkeypatch, **changes):
    import hashlib

    boot = '11111111-1111-1111-1111-111111111111'
    monkeypatch.setattr(tool, 'host_boot_id', lambda: boot)
    raw = yaml.safe_load(component_profile('gm_velocity_vector').template.read_text())
    raw['target']['waypoints'] = [
        {'time_s': 0., 'position_ned': [10., 0., -30.]},
        {'time_s': 20., 'position_ned': [30., 20., -40.]},
        {'time_s': 120., 'position_ned': [130., 40., -30.]},
    ]
    source = tmp_path/'world.yaml'
    source.write_text(yaml.safe_dump(raw))
    artifact = dict(schema_version=1, target_id='same-moving-target', frame='local_ned',
        host_monotonic_origin_s=90., host_boot_id=boot, scenario_yaml='world.yaml',
        scenario_sha256=hashlib.sha256(source.read_bytes()).hexdigest()) | changes
    path = tmp_path/'clock.json'
    path.write_text(json.dumps(artifact))
    return path, source, raw


def test_two_session_slices_preserve_one_global_world_target_and_original_bytes(tmp_path, monkeypatch):
    path, source, raw = world_clock_fixture(tmp_path, monkeypatch)
    original_clock, original_yaml = path.read_bytes(), source.read_bytes()
    first = tool.WorldTargetClock.from_file(path, now=100.)
    second = tool.WorldTargetClock.from_file(path, now=115.)
    first.require_matching_target(raw)
    for session, start in ((first, 100.), (second, 115.)):
        sliced = session.slice_raw(raw, host_start_s=start, duration_s=30.)
        destination = tmp_path/('capture-'+str(start))
        destination.mkdir()
        metadata = session.archive(destination)
        assert (destination/metadata['clock_path']).read_bytes() == original_clock
        assert (destination/metadata['scenario_path']).read_bytes() == original_yaml
        assert metadata['target_id'] == 'same-moving-target'
        scenario_path = destination/'scenario.yaml'
        scenario_path.write_text(yaml.safe_dump(sliced))
        local = tool.VisualizationScenario.from_yaml(scenario_path)
        for time_s in (0., 5., 10., 30.):
            assert local.target_at(time_s) == pytest.approx(session.target_at_host(start+time_s))
        assert sliced['target']['waypoints'][0]['position_ned'] == session.target_at_host(start)
    assert first.target_at_host(100.) != second.target_at_host(115.)
    assert first.target_at_host(99.5) == pytest.approx(first.scenario.target_at(9.5))


@pytest.mark.parametrize('change', [
    {'schema_version': True}, {'schema_version': 2}, {'frame': 'body'}, {'target_id': ''},
    {'host_monotonic_origin_s': True}, {'host_monotonic_origin_s': float('inf')},
    {'host_monotonic_origin_s': -1.}, {'host_monotonic_origin_s': 101.},
    {'host_boot_id': '22222222-2222-2222-2222-222222222222'}, {'scenario_sha256': '0'*64},
    {'extra': 'ambiguous'},
])
def test_target_clock_rejects_invalid_changed_boot_or_future_origin(tmp_path, monkeypatch, change):
    path, _source, _raw = world_clock_fixture(tmp_path, monkeypatch, **change)
    with pytest.raises(ValueError):
        tool.WorldTargetClock.from_file(path, now=100.)


@pytest.mark.parametrize('change', ['artifact', 'yaml', 'boot', 'missing'])
def test_waited_start_cannot_reuse_changed_target_clock_or_source(tmp_path, monkeypatch, change):
    path, source, _raw = world_clock_fixture(tmp_path, monkeypatch)
    clock = tool.WorldTargetClock.from_file(path, now=100.)
    if change == 'artifact':
        path.write_bytes(path.read_bytes()+b'\n')
    elif change == 'yaml':
        source.write_bytes(source.read_bytes()+b'\n')
    elif change == 'boot':
        monkeypatch.setattr(tool, 'host_boot_id', lambda: '22222222-2222-2222-2222-222222222222')
    else:
        source.unlink()
    with pytest.raises(ValueError, match='target_clock_changed'):
        clock.require_current(now=101.)


def test_missing_global_coverage_and_changed_target_are_not_clamped_or_reanchored(tmp_path, monkeypatch):
    path, _source, raw = world_clock_fixture(tmp_path, monkeypatch)
    clock = tool.WorldTargetClock.from_file(path, now=100.)
    for receipt in (89.9, 210.1):
        with pytest.raises(ValueError, match='coverage_missing'):
            clock.target_at_host(receipt)
    for duration in (0., -1., float('nan')):
        with pytest.raises(ValueError):
            clock.slice_raw(raw, host_start_s=100., duration_s=duration)
    with pytest.raises(ValueError, match='coverage_missing'):
        clock.slice_raw(raw, host_start_s=200., duration_s=20.)
    changed = deepcopy(raw)
    changed['target']['waypoints'][0]['position_ned'][0] += 1.
    with pytest.raises(ValueError, match='target_changed'):
        clock.require_matching_target(changed)


async def test_transition_witness_waits_for_the_existing_attempt_without_submitting_or_completing_it():
    observed = asyncio.Event()
    binding = SimpleNamespace(terminal_reason=None)
    status = dict(terminal_failure=False, terminal_failure_reason=None, failed_publishes=0, running=True, task_active=True)

    def read_status():
        observed.set()
        return dict(status)

    commander = SimpleNamespace(get_status=read_status,
        submit_intent=Mock(side_effect=AssertionError('No intent after transition witness')),
        stop=Mock(side_effect=AssertionError('No synthetic terminal completion')))
    waiting = asyncio.create_task(tool.wait_transition_terminal(binding, commander,
        expected_reason='aircraft_transition_observed', timeout_s=.5))
    await observed.wait()
    assert not waiting.done()
    binding.terminal_reason = 'aircraft_transition_observed'
    status.update(terminal_failure=True, terminal_failure_reason='aircraft_transition_observed', running=False)
    await asyncio.sleep(0)
    assert not waiting.done()  # The original publisher attempt still owns its task.
    status['task_active'] = False
    completed = await waiting
    assert completed['terminal_failure_reason'] == 'aircraft_transition_observed'
    commander.submit_intent.assert_not_called()
    commander.stop.assert_not_called()


@pytest.mark.parametrize('change', ['missing', 'wrong_binding_reason', 'wrong_commander_reason', 'pending_task', 'failed_publish'])
async def test_missing_or_wrong_same_attempt_terminal_completion_fails(monkeypatch, change):
    clock = [100.]
    reason = None if change == 'missing' else 'aircraft_transition_observed'
    status = dict(terminal_failure=change != 'missing', terminal_failure_reason=reason,
        failed_publishes=0, running=False, task_active=change == 'pending_task')
    if change == 'wrong_binding_reason':
        reason = 'control_owner_lost'
    elif change == 'wrong_commander_reason':
        status['terminal_failure_reason'] = 'aircraft_state_stale'
    elif change == 'failed_publish':
        status['failed_publishes'] = 1

    async def advance(delay):
        clock[0] += delay

    monkeypatch.setattr(tool.asyncio, 'sleep', advance)
    with pytest.raises((ValueError, TimeoutError)):
        await tool.wait_transition_terminal(SimpleNamespace(terminal_reason=reason),
            SimpleNamespace(get_status=lambda: dict(status)), expected_reason='aircraft_transition_observed',
            timeout_s=.1, clock=lambda: clock[0])


def test_fw_only_component_supports_vtol_fw_scenario_but_refuses_actual_mc_start(tmp_path):
    selected = component_profile('fw_navigation_chase')
    assert selected.command_contract(is_vtol=True) == 'fixed_wing_external'
    tool.require_component_phase(selected, aircraft_state(phase=AirframePhase.FIXED_WING, is_vtol=True))
    with pytest.raises(ValueError, match='profile_phase_unavailable'):
        tool.require_component_phase(selected, aircraft_state(phase=AirframePhase.MULTICOPTER, is_vtol=True))
    raw = yaml.safe_load(selected.template.read_text())
    raw['airframe'] = 'vtol'
    path = tmp_path / 'fw-only.yaml'
    path.write_text(yaml.safe_dump(raw))
    assert load_component_scenario(path, mount='HORIZONTAL', altitude=False, duration=15., is_vtol=True,
                                   follower=selected.profile.mode)['follower']['command_contract'] == 'fixed_wing_external'


async def test_unavailable_observation_logs_the_real_reply_and_delegates_none_without_projection():
    original = AsyncMock(return_value=None)
    binding = SimpleNamespace(on_observation=original, transport=SimpleNamespace(on_observation=None))
    connection = SimpleNamespace(retain_packet=Mock(side_effect=AssertionError('No pose may be minted')))
    log = Mock()
    attach_component_observer(binding, connection, log, started=90., clock=lambda: 100.)
    packet = {'fresh': False, 'aircraft_state': None, 'owner_confirmed': False}
    assert await binding.transport.on_observation(None, packet, None) is None
    original.assert_awaited_once_with(None, packet, None)
    log.assert_called_once_with('observations.jsonl', dict(timestamp=10., value=packet, retained_for_projection=False))


def transition_event(**changes):
    return {'kind': 'pilot_transition', 'at_s': 4., 'requested_phase': 'fixed_wing'} | changes


def test_pilot_transition_is_one_explicit_nonwindow_event():
    event = tool.pilot_transition_event([transition_event()], 15.)
    assert event == tool.PilotTransitionEvent(4., AirframePhase.FIXED_WING)
    assert component_fault_windows([transition_event()], 15.) == ()
    assert tool.pilot_transition_event([], 15.) is None


@pytest.mark.parametrize('changes', [{'at_s': value} for value in (True, None, -1., 0., 15., float('nan'))]
                         + [{'requested_phase': value} for value in ('vtol_transition', 'unknown', '', None)]
                         + [{'duration_s': 2.}])
def test_invalid_transition_event_cannot_enter_the_control_path(changes):
    with pytest.raises(ValueError):
        tool.pilot_transition_event([transition_event(**changes)], 15.)


@pytest.mark.parametrize('extra', [transition_event(at_s=6.), {'kind': 'target_loss', 'at_s': 1., 'duration_s': 2.}])
def test_repeated_or_mixed_pilot_events_refuse(extra):
    with pytest.raises(ValueError, match='mixed_or_repeated'):
        component_fault_windows([transition_event(), extra], 15.)


@pytest.mark.parametrize('explicit_authority', [False, True])
def test_pilot_source_contract_reads_attested_constants_not_numeric_guesses(tmp_path, monkeypatch, explicit_authority):
    message = tmp_path / 'context/source/msg/versioned/VehicleStatus.msg'
    message.parent.mkdir(parents=True)
    message.write_text('uint8 VEHICLE_TYPE_ROTARY_WING = 21\nuint8 VEHICLE_TYPE_FIXED_WING = 22\n')
    verify = Mock()
    monkeypatch.setattr('tools.sih_baseline.verify_source', verify)
    monkeypatch.setattr(tool, 'verified_simulation_build', lambda path, **_: ('sih', {'manifest': str(path)}, {}))
    authority = {'build_repository': tmp_path/'authority'} if explicit_authority else {}
    contract = tool.transition_source_contract({'firmware_build': {'manifest': str(tmp_path/'sih-build-manifest.json')}}, **authority)
    assert contract['vehicle_types'] == {'multicopter': 21, 'fixed_wing': 22}
    verify.assert_called_once()
    assert verify.call_args.args[:2] == (tmp_path/'context/source', authority.get('build_repository', ROOT))
    assert len(contract['sha256']) == 64
    with pytest.raises(ValueError, match='verified_source_build'):
        tool.transition_source_contract({}, **authority)


def cli_transition_context(tmp_path):
    path = tmp_path / 'guidance.sock'
    path.touch()
    isolation = dict(container_id='verified-container', image_id='pinned-image', aircraft_uid='aircraft-a', instance=7,
        process={'args': ['/firmware/bin/px4']}, firmware_build={'manifest': str(tmp_path/'sih-build-manifest.json')})
    contract = {'vehicle_types': {'multicopter': 21, 'fixed_wing': 22}}
    status = '    timestamp: 4000000 (0.100 seconds ago)\n    vehicle_type: 21\n    is_vtol: True\n    in_transition_mode: False\n'
    return path, isolation, contract, status


@pytest.mark.parametrize('explicit_authority', [False, True])
def test_pilot_cli_rechecks_exact_runtime_and_opposite_actual_phase_once(tmp_path, monkeypatch, explicit_authority):
    path, isolation, contract, status = cli_transition_context(tmp_path)
    verifier = Mock(return_value=isolation)
    monkeypatch.setattr(tool, 'verify_simulator', verifier)
    monkeypatch.setattr(tool, 'command', Mock(return_value=status))
    cli = Mock(return_value=subprocess.CompletedProcess([], 0, 'requested', ''))
    monkeypatch.setattr(tool.subprocess, 'run', cli)
    event = tool.PilotTransitionEvent(4., AirframePhase.FIXED_WING)
    authority = {'build_repository': tmp_path/'authority'} if explicit_authority else {}
    result = tool.native_pilot_transition(path, isolation, event, AirframePhase.MULTICOPTER, contract, **authority)
    verifier.assert_called_once_with('verified-container', 7, path,
        simulation_build_manifest=tmp_path/'sih-build-manifest.json', **authority)
    assert cli.call_args.args[0] == ('docker', 'exec', '--user', str(path.stat().st_uid), 'verified-container',
        '/firmware/bin/px4-commander', '--instance', '7', 'transition')
    assert cli.call_count == 1 and result['before_vehicle_status'] == status


@pytest.mark.parametrize('change', ['stale', 'already_transitioning', 'wrong_phase', 'not_vtol', 'wrong_aircraft'])
@pytest.mark.parametrize('explicit_authority', [False, True])
def test_changed_pilot_cli_precondition_does_not_issue_transition(tmp_path, monkeypatch, change, explicit_authority):
    path, isolation, contract, status = cli_transition_context(tmp_path)
    checked = dict(isolation)
    if change == 'stale':
        status = status.replace('0.100', '9.000')
    elif change == 'already_transitioning':
        status = status.replace('in_transition_mode: False', 'in_transition_mode: True')
    elif change == 'wrong_phase':
        status = status.replace('vehicle_type: 21', 'vehicle_type: 22')
    elif change == 'not_vtol':
        status = status.replace('is_vtol: True', 'is_vtol: False')
    else:
        checked['aircraft_uid'] = 'replacement'
    monkeypatch.setattr(tool, 'verify_simulator', Mock(return_value=checked))
    monkeypatch.setattr(tool, 'command', Mock(return_value=status))
    cli = Mock(side_effect=AssertionError('No CLI action after changed precondition'))
    monkeypatch.setattr(tool.subprocess, 'run', cli)
    with pytest.raises(ValueError, match='changed'):
        tool.native_pilot_transition(path, isolation, tool.PilotTransitionEvent(4., AirframePhase.FIXED_WING),
                                     AirframePhase.MULTICOPTER, contract,
                                     **({'build_repository': tmp_path/'authority'} if explicit_authority else {}))
    cli.assert_not_called()


@pytest.mark.parametrize('returncode', [0, None, 1])
async def test_declared_pilot_request_is_not_retried_or_reversed(monkeypatch, returncode):
    cli = Mock(return_value={'returncode': returncode})
    monkeypatch.setattr(tool, 'native_pilot_transition', cli)
    event = tool.PilotTransitionEvent(4., AirframePhase.FIXED_WING)
    injection = tool.PilotTransitionInjection(None, {}, event, AirframePhase.MULTICOPTER, {},
        log=Mock(), started=96., clock=lambda: 100.)
    state = aircraft_state(phase=AirframePhase.MULTICOPTER, is_vtol=True)
    await injection.tick(3., state, True)
    cli.assert_not_called()
    await injection.tick(4., state, True)
    if returncode == 0:
        await injection.close()
    else:
        with pytest.raises(RuntimeError, match='command_unconfirmed'):
            await injection.close()
    await injection.tick(6., state, True)
    await injection.close()
    assert cli.call_count == 1 and injection.requested


def transition_packet(state, context, **changes):
    return dict(runtime_id=context.runtime_id, fresh=True, owner_confirmed=False, rescue_active=False,
        aircraft_state=asdict(state), vehicle_pose={'vehicle_ned': [0., 0., -50.],
            'px4_timestamp_us': int(state.observed_at_monotonic_s*1_000_000),
            'observed_at_monotonic_s': state.observed_at_monotonic_s,
            'quaternion_wxyz': list(asdict(state.attitude_body_to_ned).values()), 'source': 'px4_dds_observed'},
        publications=12,
        nav_state=4, release_receipt=release_receipt(context).wire_payload()) | changes


def test_terminal_proof_requires_real_fresh_paired_transition_not_a_cli_exit_or_new_owner():
    state = aircraft_state(phase=AirframePhase.VTOL_TRANSITION, is_vtol=True)
    context = acquisition(GuidanceSessionIdentity('case', state.binding, 1))
    packet = transition_packet(state, context)
    row = {'timestamp': 4.1, 'direction': 'actual_backend_reply', 'value': {'payload': packet}}
    event = tool.PilotTransitionEvent(4., AirframePhase.FIXED_WING)
    assert tool.transition_witness([row], event=event, acquisition=context, not_before_s=4., host_origin_s=96.) is row
    for changed in ({'fresh': False}, {'runtime_id': 'other'}, {'aircraft_state': None}):
        invalid = row | {'value': {'payload': packet | changed}}
        assert tool.transition_witness([invalid], event=event, acquisition=context, not_before_s=4., host_origin_s=96.) is None
    stale = row | {'value': {'payload': packet | {'aircraft_state': asdict(replace(state, observed_at_monotonic_s=90.))}}}
    assert tool.transition_witness([stale], event=event, acquisition=context, not_before_s=4., host_origin_s=96.) is None
    assert tool.transition_witness([row], event=event, acquisition=context, not_before_s=5., host_origin_s=96.) is None
    changed = row | {'value': {'payload': packet | {'release_receipt': release_receipt(replace(context, token='c'*32)).wire_payload()}}}
    with pytest.raises(RuntimeError, match='context'):
        tool.transition_witness([changed], event=event, acquisition=context, not_before_s=4., host_origin_s=96.)


def test_absent_or_generic_backend_terminal_cannot_pass_a_correct_native_transition():
    injection = SimpleNamespace(events=[{'command': {'returncode': 0}}])
    for reason in (None, 'native_command_owner_unavailable', 'control_owner_lost'):
        checks = tool.pilot_transition_checks(injection, {}, reason, 'aircraft_transition_observed', {'settled': True})
        assert checks['pilot_transition_command_succeeded']
        assert checks['pilot_transition_observed']
        assert not checks['backend_transition_ended']


@pytest.mark.parametrize('bad', ['owner', 'rescue', 'unconfirmed_receipt', 'wrong_token', 'publication'])
async def test_readonly_post_transition_rejects_reacquisition_and_unconfirmed_release(monkeypatch, bad):
    state = aircraft_state(phase=AirframePhase.FIXED_WING, is_vtol=True)
    context = acquisition(GuidanceSessionIdentity('case', state.binding, 1))
    packet = transition_packet(state, context)
    if bad == 'owner':
        packet['owner_confirmed'] = True
    elif bad == 'rescue':
        packet['rescue_active'] = True
    elif bad == 'unconfirmed_receipt':
        packet['release_receipt'] = release_receipt(context, outcome='unconfirmed').wire_payload()
    elif bad == 'wrong_token':
        packet['release_receipt'] = release_receipt(replace(context, token='c'*32)).wire_payload()
    client = SimpleNamespace(observe=AsyncMock(side_effect=[packet, packet | {'publications': 13}]))
    monkeypatch.setattr(tool, 'observed_pose_record', Mock(return_value=None))
    sleep = AsyncMock()
    monkeypatch.setattr(tool.asyncio, 'sleep', sleep)
    with pytest.raises((ValueError, RuntimeError)):
        await tool.capture_post_transition(client, tool.PilotTransitionEvent(4., AirframePhase.FIXED_WING), context,
            log=Mock(), started=90., follow_start=95., timeout_s=5., clock=lambda: 100.,
            scenario=SimpleNamespace(target_at=lambda _: (20., 0., -50.)), response=[])
    assert not hasattr(client, 'engage') and not hasattr(client, 'submit')


async def test_readonly_post_capture_settles_from_actual_progress_and_keeps_world_target(monkeypatch):
    state = aircraft_state(phase=AirframePhase.FIXED_WING, is_vtol=True)
    context = acquisition(GuidanceSessionIdentity('case', state.binding, 1))
    packets = [transition_packet(replace(state, sequence=i, observed_at_monotonic_s=100.+(i-1)*.5,
                   airspeed=replace(state.airspeed, observed_at_monotonic_s=100.+(i-1)*.5)), context)
               for i in range(1, 8)]
    client = SimpleNamespace(observe=AsyncMock(side_effect=packets))
    monkeypatch.setattr(tool, 'observed_pose_record', Mock(return_value=None))
    clock = [100.]

    async def advance(_delay):
        clock[0] += .5

    monkeypatch.setattr(tool.asyncio, 'sleep', advance)
    world_target = Mock(return_value=(20., 0., -50.))
    response, logs = [], []
    settled = await tool.capture_post_transition(client, tool.PilotTransitionEvent(4., AirframePhase.FIXED_WING), context,
        log=lambda name, row: logs.append((name, row)), started=90., follow_start=95., timeout_s=5., clock=lambda: clock[0],
        scenario=SimpleNamespace(target_at=world_target), response=response)
    assert settled['settled'] and settled['publications'] == 12 and len(settled['states']) == 7
    assert client.observe.await_count == 7
    assert all(row['range_m'] == 20. for row in response)
    world_target.assert_called_with(8.)
    assert all(row['target_ned'] == (20., 0., -50.) for name, row in logs if name == 'trace/target_truth.jsonl')


async def test_stale_pose_cannot_complete_readonly_settling_or_refresh_world_evidence(monkeypatch):
    state = aircraft_state(phase=AirframePhase.FIXED_WING, is_vtol=True, observed_at_monotonic_s=90.)
    context = acquisition(GuidanceSessionIdentity('case', state.binding, 1))
    client = SimpleNamespace(observe=AsyncMock(return_value=transition_packet(state, context)))
    clock, response = [100.], []

    async def advance(delay):
        clock[0] += delay

    monkeypatch.setattr(tool.asyncio, 'sleep', advance)
    target = Mock(side_effect=AssertionError('Stale pose must not mint target/pose response'))
    pose = Mock(side_effect=AssertionError('Stale pose must not be presented as a new sample'))
    monkeypatch.setattr(tool, 'observed_pose_record', pose)
    with pytest.raises(TimeoutError, match='settle_timeout'):
        await tool.capture_post_transition(client, tool.PilotTransitionEvent(4., AirframePhase.FIXED_WING), context,
            log=Mock(), started=90., follow_start=95., timeout_s=.2, clock=lambda: clock[0],
            scenario=SimpleNamespace(target_at=target), response=response)
    assert response == []
    target.assert_not_called()
    pose.assert_not_called()


async def test_pilot_stale_or_lost_owner_cannot_launch_the_declared_cli(monkeypatch):
    cli = Mock(side_effect=AssertionError('No transition after source/owner loss'))
    monkeypatch.setattr(tool, 'native_pilot_transition', cli)
    for state, owned in ((aircraft_state(phase=AirframePhase.MULTICOPTER, is_vtol=True,
                                       observed_at_monotonic_s=90.), True),
                         (aircraft_state(phase=AirframePhase.MULTICOPTER, is_vtol=True), False)):
        injection = tool.PilotTransitionInjection(None, {}, tool.PilotTransitionEvent(4., AirframePhase.FIXED_WING),
            AirframePhase.MULTICOPTER, {}, log=Mock(), started=96., clock=lambda: 100.)
        with pytest.raises(ValueError, match='pursuit_not_current'):
            await injection.tick(4., state, owned)
        await injection.close()
    cli.assert_not_called()


def test_run_archive_preserves_exact_configuration_and_schema_bytes(monkeypatch, tmp_path):
    source = tmp_path / "source"
    (source / "configs").mkdir(parents=True)
    commands = b"schema_version: 2\nfollower_profiles: {}\n"
    schema = b"title: Test configuration\ntype: object\n"
    (source / "configs/follower_commands.yaml").write_bytes(commands)
    (source / "configs/config_schema.yaml").write_bytes(schema)
    monkeypatch.setattr("tools.run_native_vector_sih.ROOT", source)
    output = tmp_path / "run"
    output.mkdir()
    (output / "config.yaml").write_bytes(b"FOLLOWER_CIRCUIT_BREAKER: false\n")
    first = archive_configuration(output)
    assert (output / "follower_commands.yaml").read_bytes() == commands
    assert (output / "config_schema.yaml").read_bytes() == schema
    assert set(first) == {"config.yaml", "config_schema.yaml", "follower_commands.yaml"}
    assert all(len(artifact["sha256"]) == 64 for artifact in first.values())
    (output / "config.yaml").write_bytes(b"FOLLOWER_CIRCUIT_BREAKER: true\n")
    second = archive_configuration(output)
    assert second["config.yaml"]["sha256"] != first["config.yaml"]["sha256"]
    assert second["follower_commands.yaml"] == first["follower_commands.yaml"]
    assert second["config_schema.yaml"] == first["config_schema.yaml"]


def test_parameter_snapshot_uses_only_verified_runtime_executable_sibling(monkeypatch, tmp_path):
    path = tmp_path / "native.sock"
    calls = []

    def read_command(*args):
        calls.append(args)
        return "SIH_F_T_MAX: 6.0\n"

    monkeypatch.setattr("tools.run_native_vector_sih.command", read_command)
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        isolation = {"container_id": "verified-container-id", "instance": 7,
                     "process": {"args": ["/firmware/bin/px4"]}}
        assert native_parameters(path, isolation) == "SIH_F_T_MAX: 6.0\n"
        assert calls == [("docker", "exec", "--user", str(path.stat().st_uid), "verified-container-id",
                          "/firmware/bin/px4-param", "--instance", "7", "show")]


@pytest.mark.parametrize('blocked,operation', [(True, 'off'), (False, 'ok')])
def test_airspeed_failure_uses_only_pinned_runtime_and_instance(monkeypatch, tmp_path, blocked, operation):
    path = tmp_path / 'native.sock'
    path.touch()
    run = Mock(return_value=subprocess.CompletedProcess([], 0, 'acknowledged', 'native CLI diagnostic'))
    monkeypatch.setattr('tools.run_native_vector_sih.subprocess.run', run)
    isolation = {'container_id': 'verified-container-id', 'instance': 7, 'process': {'args': ['/firmware/bin/px4']}}
    result = native_airspeed_failure(path, isolation, blocked)
    run.assert_called_once_with(('docker', 'exec', '--user', str(path.stat().st_uid), 'verified-container-id',
        '/firmware/bin/px4-failure', '--instance', '7', 'airspeed', operation, '-i', '1'),
        text=True, capture_output=True, timeout=15, check=False)
    assert result['returncode'] == 0 and result['stdout'] == 'acknowledged'
    assert result['stderr'] == 'native CLI diagnostic'
    assert result['finished_at_monotonic_s'] >= result['started_at_monotonic_s']


def test_airspeed_failure_timeout_is_retained_as_an_uncertain_cli_result(monkeypatch, tmp_path):
    path = tmp_path / 'native.sock'
    path.touch()
    monkeypatch.setattr('tools.run_native_vector_sih.subprocess.run',
                        Mock(side_effect=subprocess.TimeoutExpired('px4-failure', 15)))
    result = native_airspeed_failure(path, {
        'container_id': 'verified-id', 'instance': 7, 'process': {'args': ['/firmware/bin/px4']},
    }, True)
    assert result['returncode'] is None and result['error'].startswith('TimeoutExpired:')
    assert result['finished_at_monotonic_s'] >= result['started_at_monotonic_s']


@pytest.mark.parametrize('text', ['x     SYS_FAILURE_EN [1022,1539] : 1\n', 'SYS_FAILURE_EN: 1\n'])
def test_fault_injection_requires_enabled_read_only_parameter_and_verified_firmware(text):
    require_airspeed_failure_injection(text, {'firmware_build': {'binary_sha256': 'a'*64}})
    with pytest.raises(ValueError, match='verified_source_build'):
        require_airspeed_failure_injection(text, {'firmware_build': None})


@pytest.mark.parametrize('text', ['', 'SYS_FAILURE_EN: 0\n', 'SYS_FAILURE_EN: true\n',
                               'SYS_FAILURE_EN: 1.0\n', 'SYS_FAILURE_EN: 1\nSYS_FAILURE_EN: 1\n'])
def test_disabled_missing_or_ambiguous_failure_permission_is_refused(text):
    with pytest.raises(ValueError, match='failure_injection_disabled'):
        require_airspeed_failure_injection(text, {'firmware_build': {}})


@pytest.mark.parametrize('source,valid', [('sensor', True), ('ground_minus_wind', True), ('unavailable', False)])
def test_airspeed_trace_reports_actual_native_selection_and_controller_state(source, valid):
    state = aircraft_state()
    state = replace(state, airspeed=replace(state.airspeed, source=source, valid=valid,
                                           equivalent_m_s=20. if valid else None))
    assert observed_airspeed_status(state, {'airspeed_control_enabled': valid}) == {
        'speed_source': source, 'airspeed_valid': valid, 'airspeed_control_enabled': valid,
    }
    assert observed_airspeed_status(state, {})['airspeed_control_enabled'] is None


def airspeed_fault(*, log=lambda *args: None):
    windows = component_fault_windows([{'kind': 'airspeed_loss', 'at_s': 0., 'duration_s': .5}], 1.)
    return AirspeedLossInjection(None, {}, windows, log=log, started=time.monotonic())


@pytest.mark.asyncio
async def test_real_airspeed_fault_handler_keeps_async_control_work_running_during_cli(monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    commands = []

    def cli(_socket, _isolation, blocked):
        commands.append(blocked)
        if blocked:
            entered.set()
            assert finish.wait(timeout=2.)
        return {'returncode': 0, 'stdout': 'ack', 'stderr': ''}

    monkeypatch.setattr('tools.run_native_vector_sih.native_airspeed_failure', cli)
    events = []
    fault = airspeed_fault(log=lambda name, event: events.append((name, event)))
    try:
        await fault.tick(0.)
        assert await asyncio.to_thread(entered.wait, 1.)
        for _ in range(20):
            await asyncio.sleep(0)
            await fault.tick(.1)
        assert commands == [True] and not fault._task.done()
        finish.set()
        await asyncio.wait_for(fault._task, 1.)
        await fault.tick(.6)
    finally:
        finish.set()
        await fault.close()
    assert commands == [True, False]
    assert [event['phase'] for event in fault.events] == ['started', 'finished', 'started', 'finished']
    assert [event['operation'] for event in fault.events] == ['off', 'off', 'ok', 'ok']
    assert all(name == 'fault-events.jsonl' for name, _ in events)
    assert all(b['observed_at_monotonic_s'] >= a['observed_at_monotonic_s']
               for a, b in zip(fault.events, fault.events[1:]))
    assert not fault.active


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [RuntimeError('control_failed'), asyncio.CancelledError()])
async def test_control_failure_restores_active_airspeed_fault_without_another_tick(monkeypatch, error):
    commands = []
    monkeypatch.setattr('tools.run_native_vector_sih.native_airspeed_failure',
                        lambda _socket, _isolation, blocked: commands.append(blocked) or {'returncode': 0})
    fault = airspeed_fault()
    with pytest.raises(type(error)):
        try:
            await fault.tick(0.)
            await fault._task
            raise error
        finally:
            await fault.close()
    assert commands == [True, False] and not fault.active
    await fault.close()
    assert commands == [True, False]


@pytest.mark.asyncio
@pytest.mark.parametrize('failed_code', [1, None])
async def test_failed_or_uncertain_off_command_still_requires_restore(monkeypatch, failed_code):
    commands = []
    monkeypatch.setattr('tools.run_native_vector_sih.native_airspeed_failure',
                        lambda _socket, _isolation, blocked: commands.append(blocked) or
                        {'returncode': failed_code if blocked else 0})
    fault = airspeed_fault()
    await fault.tick(0.)
    with pytest.raises(RuntimeError, match='fault_command_failed'):
        await fault.close()
    assert commands == [True, False] and not fault.active
    assert fault.events[1]['command']['returncode'] == failed_code


def successful_fault_events():
    return [dict(phase='finished', operation=operation, timestamp=end, observed_at_monotonic_s=100.+end,
                 command={'returncode': 0, 'started_at_monotonic_s': 100.+start,
                          'finished_at_monotonic_s': 100.+end})
            for operation, start, end in [('off', 4., 4.1), ('ok', 12., 12.1)]]


def source_row(timestamp, source, *, valid=True, control=True):
    return dict(timestamp=timestamp, speed_source=source, airspeed_valid=valid, airspeed_control_enabled=control)


@pytest.mark.parametrize('degradation', [source_row(6., 'ground_minus_wind'),
                                       source_row(6., 'unavailable', valid=False, control=False)])
def test_fault_case_requires_actual_qualified_source_degradation_and_sensor_return(degradation):
    checks = airspeed_fault_response_checks([
        source_row(1., 'sensor'), degradation, source_row(13., 'sensor'),
    ], successful_fault_events())
    assert all(checks.values())


def test_noop_fault_command_cannot_pass_without_actual_source_change():
    checks = airspeed_fault_response_checks([
        source_row(1., 'sensor'), source_row(6., 'sensor'), source_row(13., 'sensor'),
    ], successful_fault_events())
    assert checks == dict(airspeed_fault_commands_succeeded=True, airspeed_source_degraded=False,
                          airspeed_sensor_restored=False)


@pytest.mark.parametrize('late_degradation', [source_row(13., 'ground_minus_wind'),
    source_row(13., 'unavailable', valid=False, control=False)])
def test_unrelated_degradation_after_restoration_cannot_qualify_the_injected_fault(late_degradation):
    checks = airspeed_fault_response_checks([
        source_row(1., 'sensor'), source_row(6., 'sensor'), late_degradation, source_row(16., 'sensor'),
    ], successful_fault_events())
    assert checks == dict(airspeed_fault_commands_succeeded=True, airspeed_source_degraded=False,
                          airspeed_sensor_restored=False)


@pytest.mark.parametrize('degradation', [source_row(6., 'unavailable', valid=False, control=True),
    source_row(6., 'unavailable', valid=False, control=None), source_row(6., 'ground_minus_wind', valid=False),
    source_row(6., 'ground_speed_proxy'), source_row(6., 'native_auto')])
def test_unqualified_sensorless_or_proxy_labels_cannot_pass_source_fault_acceptance(degradation):
    checks = airspeed_fault_response_checks([
        source_row(1., 'sensor'), degradation, source_row(13., 'sensor'),
    ], successful_fault_events())
    assert checks['airspeed_fault_commands_succeeded']
    assert not checks['airspeed_source_degraded'] and not checks['airspeed_sensor_restored']


@pytest.mark.parametrize('rows', [
    [source_row(1., 'sensor'), source_row(6., 'ground_minus_wind'), source_row(13., 'ground_minus_wind')],
    [source_row(1., 'sensor'), source_row(6., 'ground_minus_wind'), source_row(11., 'sensor')],
    [source_row(1., 'sensor'), source_row(6., 'ground_minus_wind'), source_row(13., 'sensor', valid=False)],
])
def test_sensor_return_must_be_valid_and_observed_after_the_restore_command(rows):
    checks = airspeed_fault_response_checks(rows, successful_fault_events())
    assert checks['airspeed_source_degraded']
    assert not checks['airspeed_sensor_restored']


def test_degradation_needs_a_sensor_baseline_and_cannot_precede_the_off_command():
    checks = airspeed_fault_response_checks([
        source_row(1., 'sensor'), source_row(3., 'ground_minus_wind'), source_row(13., 'sensor'),
    ], successful_fault_events())
    assert not checks['airspeed_source_degraded']
    checks = airspeed_fault_response_checks([
        source_row(1., 'ground_minus_wind'), source_row(6., 'ground_minus_wind'), source_row(13., 'sensor'),
    ], successful_fault_events())
    assert not checks['airspeed_source_degraded']


@pytest.mark.parametrize('kind', ['off_failed', 'restore_failed', 'restore_missing', 'missing_timing'])
def test_failed_incomplete_or_unproven_commands_cannot_pass_fault_acceptance(kind):
    events = successful_fault_events()
    if kind == 'restore_missing':
        events.pop()
    elif kind == 'missing_timing':
        events[0]['command'].pop('started_at_monotonic_s')
    else:
        events[int(kind == 'restore_failed')]['command']['returncode'] = 1
    checks = airspeed_fault_response_checks([
        source_row(1., 'sensor'), source_row(6., 'ground_minus_wind'), source_row(13., 'sensor'),
    ], events)
    assert not any(checks.values())


@pytest.mark.asyncio
@pytest.mark.parametrize('failed', [None, 'publisher', 'owner', 'fault'])
async def test_cleanup_quiesces_and_releases_owner_before_fault_cli_even_when_an_earlier_step_fails(failed):
    order = []

    async def step(name, **_):
        order.append(name)
        if failed == name:
            raise RuntimeError(f'{name}_failed')
        return True

    async def stop(**kw):
        return await step('publisher', **kw)

    async def handoff(reason):
        return await step('owner')

    async def restore():
        return await step('fault')

    commander = SimpleNamespace(running=True, stop=AsyncMock(side_effect=stop))
    binding = SimpleNamespace(owner_confirmed=True, stop=AsyncMock(side_effect=handoff))
    fault = SimpleNamespace(events=[], close=AsyncMock(side_effect=restore))
    result = {'passed': True}
    await cleanup_component_run(commander, binding, fault, result)
    assert order == ['publisher', 'owner', 'fault']
    assert result['passed'] is (failed is None)
    commander.stop.assert_awaited_once_with(publish_final=False)
    binding.stop.assert_awaited_once_with('isolated_sih_cleanup')
    fault.close.assert_awaited_once()


async def test_terminal_binding_still_reconciles_original_dispatched_acquisition_during_cleanup():
    original = SimpleNamespace(owner_confirmed=False, acquire_dispatched=True, stop=AsyncMock(return_value={
        'executed': False, 'release_receipt': {'outcome': 'owner_already_released'}}))
    commander = SimpleNamespace(running=False)
    result = {'passed': False}
    await cleanup_component_run(commander, original, None, result)
    original.stop.assert_awaited_once_with('isolated_sih_cleanup')
    assert result['passed'] is False


@pytest.mark.asyncio
async def test_cleanup_restores_fault_if_publisher_quiescence_is_cancelled():
    order = []

    async def stop(**_):
        order.append('publisher')
        raise asyncio.CancelledError

    async def handoff(_):
        order.append('owner')

    async def restore():
        order.append('fault')

    commander = SimpleNamespace(running=True, stop=stop)
    binding = SimpleNamespace(owner_confirmed=True, stop=handoff)
    fault = SimpleNamespace(events=[], close=restore)
    with pytest.raises(asyncio.CancelledError):
        await cleanup_component_run(commander, binding, fault, {'passed': False})
    assert order == ['publisher', 'owner', 'fault']


def image_scenario():
    return yaml.safe_load((ROOT / "tools/sih_visualization_scenarios/fw-navigation-native-image.yaml").read_text())


def native_image_context():
    now = [100.]
    state = aircraft_state(attitude_timing=attitude_timing())
    fixture = image_fixture(image_scenario(), state, runtime_id="native-fixture", run_id="image-test", clock=lambda: now[0])
    q = state.attitude_body_to_ned
    packet = dict(fresh=True, runtime_id="native-fixture", aircraft_state=asdict(state),
        attitude_timing=asdict(state.attitude_timing), vehicle_pose=dict(
            source="px4_dds_observed", vehicle_ned=[0., 0., -50.], quaternion_wxyz=[q.w, q.x, q.y, q.z],
            px4_timestamp_us=1_000_000, observed_at_monotonic_s=99.9))
    return SimpleNamespace(now=now, state=state, fixture=fixture, packet=packet)


def native_gimbal_context(mount='HORIZONTAL'):
    env = native_image_context()
    env.fixture = gimbal_fixture(env.state, mount_type=mount, runtime_id='native-fixture',
                                run_id='gimbal-test', clock=lambda: env.now[0])
    return env


@pytest.mark.asyncio
@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
async def test_delayed_setup_reads_actual_pose_before_projection_without_restamping_target(tmp_path, monkeypatch, mount):
    env = native_gimbal_context(mount)
    window = [replace(env.state, sequence=i+1, observed_at_monotonic_s=97.+i*.5,
        airspeed=replace(env.state.airspeed, observed_at_monotonic_s=97.+i*.5)) for i in range(7)]
    assert stable_window(window)
    # Initial state and source progress are real data, independent of setup work.
    env.state = window[-1]
    connection = ObservationConnection(env.state.binding, clock=lambda: env.now[0])
    env.packet['aircraft_state'] = asdict(env.state)
    assert connection.commit_aircraft_state(env.state) and connection.retain_packet(env.state, env.packet)
    artifact, source, _ = world_clock_fixture(tmp_path, monkeypatch)
    before = artifact.read_bytes(), source.read_bytes()
    target = tool.WorldTargetClock.from_file(artifact, now=100.)
    env.now[0] = 100.51
    old = project_component_input(env.fixture, env.packet, env.state, target.target_at_host(env.now[0]), timestamp_s=1.)
    assert old.metadata['projection_error'] == 'sih_projection_attitude_stale'
    current = replace(env.state, sequence=8, observed_at_monotonic_s=env.now[0],
        attitude_timing=replace(env.state.attitude_timing, publication_timestamp_us=1510000,
            sample_timestamp_us=1500000, publication_received_at_monotonic_s=env.now[0],
            sample_received_at_monotonic_s=env.now[0]))
    packet = deepcopy(env.packet)
    packet.update(aircraft_state=asdict(current), attitude_timing=asdict(current.attitude_timing),
        owner_confirmed=False, rescue_active=False, nav_state=4, phase_status_fresh=True,
        release_pending=False, neutral_drain_active=False)
    packet['vehicle_pose'].update(px4_timestamp_us=1510000, observed_at_monotonic_s=env.now[0])
    client, records = SimpleNamespace(observe=AsyncMock(return_value=packet)), []
    state = await tool.refresh_component_start(client, connection, window, runtime_id='native-fixture',
        expected_altitude_m=50., deadline=110., log=lambda n, v: records.append((n, v)),
        started=97., clock=lambda: env.now[0])
    fresh = project_component_input(env.fixture, connection.last_packet, state,
        target.target_at_host(env.now[0]), timestamp_s=2.)
    assert fresh.tracking_active and measurement_time(fresh) == 100.51
    assert fresh.raw_data['measurement_target_ned'] == tuple(target.target_at_host(100.51))
    assert target.target_at_host(100.) != target.target_at_host(100.51)
    assert (artifact.read_bytes(), source.read_bytes()) == before
    assert records[0][1]['purpose'] == 'pre_projection_start_refresh'
    client.observe.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['phase', 'owner', 'rescue', 'runtime', 'stale', 'deadline', 'late_reply'])
async def test_start_refresh_refuses_unqualified_or_expired_read_before_acquire(bad):
    env = native_image_context()
    env.state = replace(env.state, sequence=7)
    connection = ObservationConnection(env.state.binding, clock=lambda: env.now[0])
    env.packet['aircraft_state'] = asdict(env.state)
    assert connection.commit_aircraft_state(env.state) and connection.retain_packet(env.state, env.packet)
    window = [replace(env.state, sequence=i+1, observed_at_monotonic_s=97.+i*.5,
        airspeed=replace(env.state.airspeed, observed_at_monotonic_s=97.+i*.5)) for i in range(7)]
    assert stable_window(window)
    packet = deepcopy(env.packet)
    packet.update(owner_confirmed=False, rescue_active=False, nav_state=4, phase_status_fresh=True,
        release_pending=False, neutral_drain_active=False)
    if bad == 'phase': packet['aircraft_state']['phase'] = AirframePhase.VTOL_TRANSITION.value
    elif bad == 'owner': packet['owner_confirmed'] = True
    elif bad == 'rescue': packet['rescue_active'] = True
    elif bad == 'runtime': packet['runtime_id'] = 'replacement'
    elif bad == 'stale': env.now[0] = 101.
    elif bad == 'deadline': env.now[0] = 110.
    async def observe():
        if bad == 'late_reply': env.now[0] = 110.
        return packet
    client = SimpleNamespace(observe=AsyncMock(side_effect=observe), engage=AsyncMock())
    with pytest.raises((ValueError, TimeoutError)):
        await tool.refresh_component_start(client, connection, window, runtime_id='native-fixture',
            expected_altitude_m=50., deadline=110., log=lambda *args: None, started=97., clock=lambda: env.now[0])
    client.engage.assert_not_awaited()
    if bad == 'deadline': client.observe.assert_not_awaited()


@pytest.mark.parametrize('profile,kind', [('gm_velocity_vector', TrackerDataType.GIMBAL_ANGLES),
                                        ('fw_navigation_chase', TrackerDataType.POSITION_2D)])
def test_declared_native_input_binds_the_same_readonly_resolver_before_authority(profile, kind):
    env = native_image_context()
    follower = SimpleNamespace(bind_guidance_input_resolver=Mock())
    fixture = bind_component_fixture(component_profile(profile), follower, image_scenario(), env.state,
        mount_type='HORIZONTAL', runtime_id='native-fixture', run_id='explicit-fixture', clock=lambda: env.now[0])
    follower.bind_guidance_input_resolver.assert_called_once_with(fixture.resolve)
    output = project_component_input(fixture, env.packet, env.state, [100., 20., -40.], timestamp_s=1.)
    callback = follower.bind_guidance_input_resolver.call_args.args[0]
    assert callback(output, env.state).association_kind == 'sih_projection_pair'
    assert output.data_type is kind
    if kind is TrackerDataType.GIMBAL_ANGLES:
        assert output.image_measurement is output.position_2d is None
        assert output.gimbal_observation.provider_id == 'simulated_gimbal_world_target'


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_gimbal_component_retains_original_world_target_when_pose_only_advances(mount):
    env = native_gimbal_context(mount)
    original = project_component_input(env.fixture, env.packet, env.state, [100., 20., -40.], timestamp_s=1.)
    env.packet['vehicle_pose']['px4_timestamp_us'] += 1000
    retained = project_component_input(env.fixture, env.packet, env.state, [100., 21., -40.], timestamp_s=2.)
    assert retained is original
    assert measurement_time(retained) == 99.9
    assert measurement_world_target(retained, [100., 21., -40.]) == (100., 20., -40.)
    assert retained.gimbal_observation.tracking_received_at_monotonic_s == 99.9
    env.now[0] = 100.6
    unavailable = project_component_input(env.fixture, env.packet, env.state, [100., 21., -40.], timestamp_s=3.)
    assert unavailable.data_type is TrackerDataType.GIMBAL_ANGLES
    assert unavailable.gimbal_observation is unavailable.angular is None
    assert measurement_time(unavailable) is measurement_world_target(unavailable, [100., 21., -40.]) is None
    evidence = component_target_evidence(unavailable, input_owner=SimpleNamespace(), session_epoch=1, now=lambda: env.now[0])
    assert evidence.state is TargetEvidenceState.UNCERTAIN


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_real_native_gimbal_preengagement_qualifier_uses_the_explicit_fixture_resolver(mount):
    previous = Parameters.get_runtime_config_snapshot()
    config = yaml.safe_load((ROOT / 'configs/config_default.yaml').read_text())
    config['GimbalTracker']['MOUNT_TYPE'] = mount
    Parameters.publish_config_mapping(config)
    follower = None
    try:
        env = native_gimbal_context(mount)
        connection = ObservationConnection(env.state.binding, clock=lambda: env.now[0])
        assert connection.commit_aircraft_state(env.state)
        assert connection.retain_packet(env.state, env.packet)
        follower = FollowerFactory.create_follower('gm_velocity_vector', connection, (.5, .5))
        projected = bind_component_fixture(component_profile('gm_velocity_vector'), follower, {}, env.state,
            mount_type=mount, runtime_id='native-fixture', run_id='preengagement-test', clock=lambda: env.now[0])
        follower.create_airframe_session(GuidanceSessionIdentity('preengagement-test', env.state.binding, 1),
            NativeCapabilities('native-fixture', 'fixture', 2, True, False, False),
            confirmation_s=0., observation_timeout_s=.75, clock=lambda: env.now[0])
        output = project_component_input(projected, env.packet, env.state, [100., 20., -40.], timestamp_s=1.)
        owner = SimpleNamespace(follower=SimpleNamespace(follower=follower), px4_interface=connection)
        evidence = component_target_evidence(output, input_owner=owner, session_epoch=1, now=lambda: env.now[0])
        assert evidence.state is TargetEvidenceState.CONFIRMED
        assert follower._airframe_session_bound is False
        assert follower.get_last_command_intent() is None
    finally:
        if follower is not None:
            follower.release_session_controls()
        Parameters.publish_config_mapping(previous)


def test_only_coherent_accepted_native_packet_can_replace_projected_pose():
    env = native_image_context()
    connection = ObservationConnection(env.state.binding, clock=lambda: env.now[0])
    assert connection.commit_aircraft_state(env.state)
    assert connection.retain_packet(env.state, env.packet)
    retained = connection.last_packet
    incoming = replace(env.state, sequence=0)
    reordered = deepcopy(env.packet)
    reordered["aircraft_state"] = asdict(incoming)
    reordered["vehicle_pose"]["vehicle_ned"] = [100., 100., -40.]
    assert not connection.commit_aircraft_state(incoming)
    accepted = connection.get_aircraft_state()
    assert accepted == env.state
    assert not connection.retain_packet(accepted, reordered)
    assert not connection.retain_packet(incoming, reordered)
    assert connection.last_packet is retained
    output = project_component_input(env.fixture, connection.last_packet, accepted, [100., 20., -40.], timestamp_s=1.)
    assert output.image_measurement is not None


def test_rewritten_attitude_timing_packet_does_not_become_a_stable_gate_sample():
    env = native_image_context()
    connection = ObservationConnection(env.state.binding, clock=lambda: env.now[0])
    assert connection.commit_aircraft_state(env.state)
    assert connection.retain_packet(env.state, env.packet)
    rewritten = replace(env.state, sequence=2, attitude_timing=replace(env.state.attitude_timing,
        sample_timestamp_us=env.state.attitude_timing.sample_timestamp_us-1))
    packet = deepcopy(env.packet)
    packet["aircraft_state"] = asdict(rewritten)
    assert not connection.commit_aircraft_state(rewritten)
    assert not connection.retain_packet(rewritten, packet)
    assert not connection.retain_packet(connection.get_aircraft_state(), packet)
    assert connection.last_packet is env.packet
    assert connection.retain_packet(env.state, env.packet)


@pytest.mark.usefixtures("native_follower_environment")
async def test_engagement_and_publication_share_accepted_image_observation_before_first_projection():
    from tests.fixtures.native_ownership import acquisition
    env = native_image_context()
    connection = ObservationConnection(env.state.binding, clock=lambda: env.now[0])
    assert connection.commit_aircraft_state(env.state)
    assert connection.retain_packet(env.state, env.packet)
    follower = FollowerFactory.create_follower("fw_navigation_chase", connection, (.5, .5))
    follower.bind_guidance_input_resolver(env.fixture.resolve)
    guidance = follower.create_airframe_session(
        GuidanceSessionIdentity("image-start", env.state.binding, 1),
        NativeCapabilities("native-fixture", "fixture", 2, True, False, False, True, 23),
        confirmation_s=.3, observation_timeout_s=.75, clock=lambda: env.now[0],
    )
    output = project_component_input(env.fixture, env.packet, env.state, [100., 20., -40.], timestamp_s=1.)
    input_owner = SimpleNamespace(follower=SimpleNamespace(follower=follower), px4_interface=connection)
    config = Parameters.get_runtime_config_snapshot()["TargetContinuity"]
    supervisor = TargetContinuitySupervisor(ContinuityPolicy.resolve(config, "fw_navigation_chase", env.state.phase),
                                            clock=lambda: env.now[0])
    supervisor.reset_session(session_epoch=1, reason="test_start")
    base = ContinuityContext("PX4_NATIVE", env.state.phase, "fixed_wing_external", True, False, True)
    client = SimpleNamespace(session_identity=None, acquisition_token=None, acquisition_context=None, abort=Mock(), submit=AsyncMock())

    async def own(identity, **kwargs):
        from classes.command_dispatch_guard import validate_before_dispatch
        validate_before_dispatch(kwargs.get('before_dispatch'))
        validate_before_dispatch(kwargs.get('on_mode_dispatch'))
        client.session_identity = identity
        client.acquisition_token = kwargs['ownership_token']
        client.acquisition_context = acquisition(identity, token=client.acquisition_token, runtime_id='native-fixture')
        return {'owner_confirmed': True, 'runtime_id': 'native-fixture',
                'acquisition': client.acquisition_context.wire_payload()}

    client.matches_acquisition = lambda original, runtime, token, known=None: (
        client.acquisition_context is not None and original == client.acquisition_context.identity
        and runtime == client.acquisition_context.runtime_id and token == client.acquisition_context.token
        and (known is None or known == client.acquisition_context))
    client.engage = AsyncMock(side_effect=own)
    env.now[0] = 100.1
    current = replace(env.state, sequence=2, observed_at_monotonic_s=100.1,
        attitude_timing=replace(env.state.attitude_timing, publication_timestamp_us=1_100_000,
            sample_timestamp_us=1_090_000, publication_received_at_monotonic_s=100.1,
            sample_received_at_monotonic_s=100.1))
    packet = deepcopy(env.packet)
    packet.update(aircraft_state=asdict(current), attitude_timing=asdict(current.attitude_timing),
                  owner_confirmed=True, rescue_active=False, nav_state=23, nav_state_timestamp=100)
    packet["vehicle_pose"].update(px4_timestamp_us=1_050_000, observed_at_monotonic_s=100.1,
                                   vehicle_ned=[2., 0., -50.])
    client.observe = AsyncMock(return_value=packet)
    binding = NativeFollowBinding(guidance, connection, client, supervisor, profile_name="fw_navigation_chase",
        continuity_config=config, target_evidence=lambda: component_target_evidence(
            output, input_owner=input_owner, session_epoch=1, now=lambda: env.now[0]),
        context=lambda: base, circuit_breaker=lambda: False, clock=lambda: env.now[0])
    logs = []
    attach_component_observer(binding, connection, lambda name, value: logs.append((name, value)),
                              started=100., clock=lambda: env.now[0])
    assert binding.on_observation is binding.transport.on_observation
    baseline = await binding.engage()
    assert connection.get_aircraft_state() == current
    assert connection.last_packet is packet
    follower.bind_airframe_session(guidance)
    first = project_component_input(env.fixture, connection.last_packet, connection.get_aircraft_state(),
                                    [100., 20., -40.], timestamp_s=2.)
    assert first.image_measurement.provenance.capture.capture_id == "1050000"
    assert measurement_time(first) == 100.1
    assert logs[0][1]["retained_for_projection"] is True
    await binding.transport.on_observation(current, packet, baseline)
    assert len(logs) == 2
    client.submit.assert_not_called()
    binding.abort("test_complete")


def test_pose_trace_uses_actual_receipt_and_does_not_refresh_on_repeated_polls():
    env = native_image_context()
    baseline = observed_pose_record(env.packet, follow_start=100., previous_timestamp_us=None)
    assert baseline["timestamp"] == pytest.approx(-.1)
    assert baseline["observed_at_monotonic_s"] == 99.9
    assert baseline["timestamp_basis"] == "native_pose_acquisition_receipt"
    repeated = deepcopy(env.packet)
    repeated["vehicle_pose"]["observed_at_monotonic_s"] = 100.2
    assert observed_pose_record(repeated, follow_start=100., previous_timestamp_us=1_000_000) is None
    repeated["vehicle_pose"]["px4_timestamp_us"] += 50_000
    fresh = observed_pose_record(repeated, follow_start=100., previous_timestamp_us=1_000_000)
    assert fresh["timestamp"] == pytest.approx(.2)
    assert fresh["vehicle_ned"] == baseline["vehicle_ned"]
    with pytest.raises(ValueError, match="pose_reordered"):
        observed_pose_record(env.packet, follow_start=100., previous_timestamp_us=1_050_000)


@pytest.mark.parametrize("timestamp", [0, -1, True, 1., None, 2**64])
def test_pose_trace_rejects_invalid_native_timestamp(timestamp):
    env = native_image_context()
    env.packet["vehicle_pose"]["px4_timestamp_us"] = timestamp
    with pytest.raises(ValueError, match="pose_timestamp_invalid"):
        observed_pose_record(env.packet, follow_start=100., previous_timestamp_us=None)


@pytest.mark.parametrize("profile,contract,data_type", [
    ("gm_velocity_vector", "gimbal_angles", TrackerDataType.GIMBAL_ANGLES),
    ("fw_navigation_chase", "image_position_2d", TrackerDataType.POSITION_2D),
])
def test_native_component_input_is_selected_from_registered_contract(profile, contract, data_type):
    selected = component_profile(profile)
    assert selected.input_contract == contract
    assert selected.tracker_type is data_type
    assert selected.command_contract(is_vtol=False) == "fixed_wing_external"
    assert selected.template.is_file()


def test_component_adapter_is_not_keyed_by_follower_identifier(monkeypatch):
    original = component_profile("fw_navigation_chase").profile
    renamed = replace(original, mode="new_calibrated_image_profile", native_phase_contracts=())
    monkeypatch.setattr("tools.run_native_vector_sih.get_follower_profile", lambda name: renamed)
    selected = component_profile(renamed.mode)
    assert selected.profile is renamed
    assert selected.tracker_type is TrackerDataType.POSITION_2D
    assert selected.command_contract(is_vtol=True) == "fixed_wing_external"
    with pytest.raises(ValueError, match="profile_phase_unavailable"):
        tool.require_component_phase(selected, aircraft_state(phase=AirframePhase.MULTICOPTER, is_vtol=True))


@pytest.mark.parametrize("profile", ["mc_velocity_chase", "fw_attitude_rate", "gm_velocity_chase"])
def test_native_component_rejects_unsupported_production_contracts(profile):
    with pytest.raises(ValueError, match="native_component_profile_unavailable"):
        component_profile(profile)


def test_native_component_rejects_unsupported_input_without_follower_name_checks(monkeypatch):
    profile = replace(component_profile("fw_navigation_chase").profile, required_tracker_data=("VELOCITY",))
    monkeypatch.setattr("tools.run_native_vector_sih.get_follower_profile", lambda name: profile)
    with pytest.raises(ValueError, match="input_unsupported"):
        component_profile("any-name")


def test_explicit_image_scenario_preserves_contract_and_independent_target():
    selected = component_profile("fw_navigation_chase")
    raw = load_component_scenario(selected.template, mount="HORIZONTAL", altitude=False,
        duration=20., is_vtol=False, follower=selected.profile.mode)
    assert raw["follower"]["input_contract"] == "image_position_2d"
    assert raw["follower"]["speed_source_policy"] == "native_auto"
    assert raw["target"] == image_scenario()["target"]
    assert raw["pinhole_calibration"]["image_size_px"] == [1280, 720]


@pytest.mark.parametrize("change", ["missing_camera", "missing_calibration", "extra_calibration", "gimbal_input",
                                    "wrong_profile", "velocity_command", "wrong_airframe", "wrong_mount"])
def test_image_scenario_rejects_incompatible_or_implicit_optics(tmp_path, change):
    raw = image_scenario()
    if change == "missing_camera":
        raw.pop("fixed_camera")
    elif change == "missing_calibration":
        raw.pop("pinhole_calibration")
    elif change == "extra_calibration":
        raw["pinhole_calibration"]["infer_from_fov"] = True
    elif change == "gimbal_input":
        raw["follower"]["input_contract"] = "gimbal_angles"
    elif change == "wrong_profile":
        raw["follower"]["profile"] = "gm_velocity_vector"
    elif change == "velocity_command":
        raw["follower"]["command_contract"] = "velocity_body_offboard"
    elif change == "wrong_airframe":
        raw["airframe"] = "multicopter"
    else:
        raw["mount_type"] = "VERTICAL"
    path = tmp_path / "image.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        load_component_scenario(path, mount="HORIZONTAL", altitude=False, duration=20.,
            is_vtol=False, follower="fw_navigation_chase")


def test_image_fixture_requires_matching_explicit_optics_before_authority():
    raw = image_scenario()
    raw["pinhole_calibration"]["focal_length_px"][0] = 800.
    with pytest.raises(ValueError, match="intrinsics_fov_mismatch"):
        image_fixture(raw, aircraft_state(attitude_timing=attitude_timing()),
            runtime_id="native-fixture", run_id="bad-optics", clock=lambda: 100.)
    with pytest.raises(ValueError, match="attitude_timing_unavailable"):
        image_fixture(image_scenario(), aircraft_state(), runtime_id="native-fixture", run_id="no-timing")


def test_component_projection_retains_pose_receipt_and_exact_quaternion_pair():
    env = native_image_context()
    output = project_component_input(env.fixture, env.packet, env.state, [100., 20., -40.], timestamp_s=1.)
    assert measurement_time(output) == 99.9
    aligned = env.fixture.resolve(output, env.state)
    direction = aligned.direction_ned
    length = math.sqrt(100.**2 + 20.**2 + 10.**2)
    assert (direction.x, direction.y, direction.z) == pytest.approx((100./length, 20./length, 10./length))
    env.now[0] = 100.1
    later = replace(env.state, sequence=2, observed_at_monotonic_s=100.1,
        attitude_body_to_ned=Quaternion.from_euler(.1, .2, .3), attitude_timing=replace(env.state.attitude_timing,
            publication_timestamp_us=1_100_000, sample_timestamp_us=1_090_000,
            publication_received_at_monotonic_s=100.1, sample_received_at_monotonic_s=100.1))
    assert env.fixture.resolve(output, later).direction_ned == direction
    duplicate = project_component_input(env.fixture, env.packet, env.state, [100., 20., -40.], timestamp_s=2.)
    assert duplicate is output
    assert measurement_time(duplicate) == 99.9


def test_partial_projection_retains_original_measurement_and_target_truth():
    env = native_image_context()
    output = project_component_input(env.fixture, env.packet, env.state, [100., 20., -40.], timestamp_s=1.)
    assert output.image_measurement is not None
    retained = project_component_input(env.fixture, env.packet, env.state, [100., 21., -40.], timestamp_s=2.)
    assert retained is output
    assert measurement_time(retained) == 99.9
    assert measurement_world_target(retained, [100., 21., -40.]) == (100., 20., -40.)
    assert env.fixture.retained_frame(env.state) == (output, (100., 20., -40.))


def test_projected_age_expiry_is_uncertain_without_a_new_measurement():
    env = native_image_context()
    output = project_component_input(env.fixture, env.packet, env.state, [100., 20., -40.], timestamp_s=1.)
    assert output.image_measurement is not None
    env.now[0] = 101.
    unavailable = project_component_input(env.fixture, env.packet, env.state, [100., 21., -40.], timestamp_s=2.)
    evidence = component_target_evidence(unavailable, input_owner=None, session_epoch=3, now=lambda: 101.)
    assert evidence.state is TargetEvidenceState.UNCERTAIN
    assert unavailable.image_measurement is None
    assert unavailable.position_2d is None
    assert measurement_time(unavailable) is None
    assert measurement_world_target(unavailable, [100., 21., -40.]) is None
    assert unavailable.raw_data["freshness_reason"] == "sih_projection_attitude_stale"


def test_projection_identity_failure_remains_a_guard_failure():
    env = native_image_context()
    env.packet["runtime_id"] = "superseded-runtime"
    with pytest.raises(ValueError, match="native_packet_invalid"):
        project_component_input(env.fixture, env.packet, env.state, [100., 20., -40.], timestamp_s=1.)


def test_component_evidence_uses_production_read_only_qualifier_and_original_receipt():
    env = native_image_context()
    output = project_component_input(env.fixture, env.packet, env.state, [100., 20., -40.], timestamp_s=1.)
    calls = []

    def qualify(observation, state):
        calls.append((observation, state))
        env.fixture.resolve(observation, state)

    owner = SimpleNamespace(follower=SimpleNamespace(follower=SimpleNamespace(require_guidance_input=qualify)),
                            px4_interface=SimpleNamespace(get_aircraft_state=lambda: env.state))
    fresh = component_target_evidence(output, input_owner=owner, session_epoch=3, now=lambda: 100.)
    assert fresh.state is TargetEvidenceState.CONFIRMED
    assert fresh.observed_at_monotonic_s == 99.9
    assert calls == [(output, env.state)]
    env.now[0] = 101.
    stale = component_target_evidence(output, input_owner=owner, session_epoch=3, now=lambda: 101.)
    assert stale.state is TargetEvidenceState.UNCERTAIN
    assert stale.identity_verdict is IdentityVerdict.UNCONFIRMED
    assert stale.reason_code == "sih_projection_attitude_stale"
    assert stale.observed_at_monotonic_s == fresh.observed_at_monotonic_s
    absent = component_target_evidence(loss_tracker_output(TrackerDataType.POSITION_2D),
        input_owner=owner, session_epoch=3, now=lambda: 101.)
    assert absent.state is TargetEvidenceState.ABSENT
    assert len(calls) == 2


@pytest.mark.parametrize("data_type", [TrackerDataType.POSITION_2D, TrackerDataType.GIMBAL_ANGLES])
def test_generic_loss_has_no_fabricated_input_or_sample_time(data_type):
    output = loss_tracker_output(data_type)
    assert output.data_type is data_type
    assert output.image_measurement is None and output.angular is None and output.position_2d is None
    assert measurement_time(output) is None
    assert TargetEvidenceSnapshot.from_tracker_output(output, session_epoch=1).state is TargetEvidenceState.ABSENT
    with pytest.raises(ValueError, match="loss_input_unsupported"):
        loss_tracker_output(TrackerDataType.VELOCITY_AWARE)


def test_native_final_guard_preserves_typed_fields_identity_and_intent_timestamp(native_follower_environment):
    env = native_follower_environment()
    assert env.follower.follow_target(env.output)
    intent = env.follower.get_last_command_intent()
    original = deepcopy(intent.fields)
    guarded = prepare_component_intent(env.follower, intent, loss_decay=True)
    assert guarded.fields == original
    assert intent.fields == original
    assert guarded.guidance_identity is intent.guidance_identity
    assert guarded.created_at_monotonic_s == intent.created_at_monotonic_s
    assert set(guarded.fields) == {"course_rad", "equivalent_airspeed_m_s", "altitude_amsl_m"}
    env.follower.release_session_controls()
    with pytest.raises(ValueError, match="ended"):
        prepare_component_intent(env.follower, intent, loss_decay=False)


def test_initial_image_evidence_qualifies_prepared_real_session_before_any_mode_observation(native_follower_environment):
    env = native_follower_environment(settle=False)
    owner = SimpleNamespace(follower=SimpleNamespace(follower=env.follower),
                            px4_interface=SimpleNamespace(get_aircraft_state=lambda: env.state))
    with pytest.raises(ValueError, match="aircraft_state_stale"):
        env.session.require_state()
    initial_phase_state = env.session.phase_owner.state
    evidence = component_target_evidence(env.output, input_owner=owner, session_epoch=1, now=lambda: env.now[0])
    assert evidence.state is TargetEvidenceState.CONFIRMED
    assert env.session.phase_owner.state is initial_phase_state
    assert env.follower.get_last_command_intent() is None
    assert not env.follower.follow_target(env.output)
    with pytest.raises(ValueError, match="aircraft_state_stale"):
        env.session.require_state()


def flight_window():
    sample = aircraft_state(phase=AirframePhase.FIXED_WING, is_vtol=False, is_tailsitter=False)
    return [replace(sample, observed_at_monotonic_s=100. + n * .5, sequence=n,
                    airspeed=replace(sample.airspeed, observed_at_monotonic_s=100. + n * .5),
                    relative_altitude_m=30., velocity_ned_m_s=replace(sample.velocity_ned_m_s, z=0.))
            for n in range(7)]


def test_fw_stable_gate_requires_seven_consecutive_airborne_native_samples():
    states = flight_window()
    assert stable_window(states)
    assert not stable_window(states[:-1])
    assert not stable_window([replace(s, observed_at_monotonic_s=100. + n * .01)
                              for n, s in enumerate(states)])


def sensorless_flight_window():
    return [replace(state, airspeed=replace(state.airspeed, source="unavailable", valid=False,
                                            equivalent_m_s=None, true_m_s=None))
            for state in flight_window()]


def test_sensorless_stability_requires_explicit_matching_native_control_feedback():
    states = sensorless_flight_window()
    assert not stable_window(states)
    assert stable_window(states, native_airspeed_control_enabled=[False] * len(states))
    for flags in ([False] * 6, [False] * 6 + [True], [False] * 6 + [None], [0] * 7):
        assert not stable_window(states, native_airspeed_control_enabled=flags)
    assert all(state.airspeed.equivalent_m_s is None and not state.airspeed.valid for state in states)


def test_sensorless_stability_never_bypasses_a_valid_low_or_stale_airspeed():
    states = flight_window()
    for airspeed in (replace(states[-1].airspeed, equivalent_m_s=1.),
                     replace(states[-1].airspeed, observed_at_monotonic_s=100.)):
        assert not stable_window(states[:-1] + [replace(states[-1], airspeed=airspeed)],
                                 native_airspeed_control_enabled=[False] * 7)
    states = sensorless_flight_window()
    for airspeed in (replace(states[-1].airspeed, source="sensor"),
                     replace(states[-1].airspeed, equivalent_m_s=20.),
                     replace(states[-1].airspeed, true_m_s=20.),
                     replace(states[-1].airspeed, observed_at_monotonic_s=100.)):
        assert not stable_window(states[:-1] + [replace(states[-1], airspeed=airspeed)],
                                 native_airspeed_control_enabled=[False] * 7)


def test_qualified_wind_estimate_is_not_relabelled_sensorless_or_groundspeed():
    states = [replace(state, airspeed=replace(state.airspeed, source="ground_minus_wind"))
              for state in flight_window()]
    assert stable_window(states)
    assert stable_window(states, native_airspeed_control_enabled=[True] * 7)
    assert all(state.airspeed.source == "ground_minus_wind" for state in states)


@pytest.mark.parametrize("sensorless", [False, True])
def test_independent_airspeed_receipt_may_be_newer_than_aggregate_state_receipt(sensorless):
    states = sensorless_flight_window() if sensorless else flight_window()
    controls = [False] * len(states) if sensorless else None
    newer = [replace(state, airspeed=replace(state.airspeed,
               observed_at_monotonic_s=state.observed_at_monotonic_s + .05)) for state in states]
    assert stable_window(newer, native_airspeed_control_enabled=controls)
    distant = replace(newer[-1], airspeed=replace(newer[-1].airspeed,
                       observed_at_monotonic_s=newer[-1].observed_at_monotonic_s + 2.))
    assert not stable_window(newer[:-1] + [distant], native_airspeed_control_enabled=controls)


@pytest.mark.parametrize("change", ["sequence", "clock", "gap", "binding", "source", "altitude_reference"])
def test_stability_cannot_bridge_missing_progress_or_changed_aircraft_context(change):
    states = flight_window()
    last = states[-1]
    replacements = {
        "sequence": {"sequence": states[-2].sequence},
        "clock": {"observed_at_monotonic_s": states[-2].observed_at_monotonic_s},
        "gap": {"observed_at_monotonic_s": last.observed_at_monotonic_s + 2.},
        "binding": {"binding": replace(last.binding, connection_generation=last.binding.connection_generation + "-new")},
        "source": {"source": "replaced_native_source"},
        "altitude_reference": {"altitude_reference_generation": last.altitude_reference_generation + 1},
    }
    assert not stable_window(states[:-1] + [replace(last, **replacements[change])])


@pytest.mark.parametrize("changes", [
    {"relative_altitude_m": .1}, {"phase": AirframePhase.VTOL_TRANSITION, "is_vtol": True}, {"rescue_active": True},
    {"fixed_wing_envelope": None},
])
def test_native_gate_never_substitutes_for_ground_or_rescue_readiness(changes):
    states = flight_window()
    states[-1] = replace(states[-1], **changes)
    assert not stable_window(states)


def test_fw_stable_gate_rejects_underspeed_climb_and_altitude_excursions():
    states = flight_window()
    for state in (replace(states[-1], airspeed=replace(states[-1].airspeed, equivalent_m_s=1.)),
                  replace(states[-1], velocity_ned_m_s=replace(states[-1].velocity_ned_m_s, z=-3.)),
                  replace(states[-1], relative_altitude_m=35.)):
        assert not stable_window(states[:-1] + [state])


def test_stable_flight_cannot_complete_on_the_way_to_the_selected_test_altitude():
    states = flight_window()
    assert stable_window(states, expected_altitude_m=30.)
    assert not stable_window(states, expected_altitude_m=50.)


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
def test_world_target_input_preserves_actual_pose_sample_time(mount):
    env = native_gimbal_context(mount)
    env.packet['vehicle_pose']['observed_at_monotonic_s'] = 99.8
    tracker = env.fixture.project(env.packet, env.state, (50., 5., -20.), timestamp_s=1.)
    assert tracker.raw_data["angle_sample_monotonic"] == 99.8
    assert tracker.raw_data["usable_for_following"] is True
    env.now[0] = 101.
    with pytest.raises(ValueError, match="stale"):
        env.fixture.project(env.packet, env.state, (50., 5., -20.), timestamp_s=2.)
    env.now[0] = 99.
    with pytest.raises(ValueError, match="stale"):
        env.fixture.project(env.packet, env.state, (50., 5., -20.), timestamp_s=2.)


def test_vtol_mc_stable_gate_uses_hover_telemetry_without_fw_airspeed():
    from classes.aircraft_state import Vector3
    states = [replace(s, phase=AirframePhase.MULTICOPTER, is_vtol=True,
                      velocity_ned_m_s=Vector3(0., 0., 0.), airspeed=replace(s.airspeed, valid=False))
              for s in flight_window()]
    assert stable_window(states, expected_altitude_m=30.)
    assert not stable_window(states[:-1] + [replace(states[-1], navigation_heading_rad=1.)])
    assert not stable_window(states[:-1] + [replace(states[-1], velocity_ned_m_s=Vector3(1., 0., 0.))])
    assert not stable_window([replace(s, is_vtol=False) for s in states])


def test_component_world_target_is_not_reanchored_to_the_aircraft(tmp_path):
    from tools.run_native_vector_sih import ROOT
    raw = yaml.safe_load((ROOT / "tools/sih_visualization_scenarios/gimbal-vector-native-fw.yaml").read_text())
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw))
    loaded = load_component_scenario(path, mount="VERTICAL", altitude=False, duration=20., is_vtol=False)
    assert loaded["target"] == raw["target"]
    for changes in ({"mount": "HORIZONTAL"}, {"altitude": True}, {"duration": 60.}, {"is_vtol": True}):
        kwargs = dict(mount="VERTICAL", altitude=False, duration=20., is_vtol=False) | changes
        with pytest.raises(ValueError, match="scenario_contract_mismatch|target_does_not_cover_run"):
            load_component_scenario(path, **kwargs)
    raw["faults"] = [{"type": "loss", "start_s": 1., "end_s": 2.}]
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="fault_injection_not_implemented"):
        load_component_scenario(path, mount="VERTICAL", altitude=False, duration=20., is_vtol=False)


def test_phase_analysis_keeps_separate_repeated_mc_spans_and_actual_range_divergence():
    rows = [dict(timestamp=t, phase=phase, range_m=distance, altitude_m=altitude)
            for t, phase, distance, altitude in [(0., "multicopter", 100., 30.),
                                                (1., "multicopter", 105., 30.1),
                                                (2., "vtol_transition", 106., 29.),
                                                (3., "fixed_wing", 90., 28.),
                                                (4., "multicopter", 95., 29.)]]
    spans = phase_response_segments(rows)
    assert [s["phase"] for s in spans] == ["multicopter", "vtol_transition", "fixed_wing", "multicopter"]
    assert spans[0]["range_end_m"] > spans[0]["range_start_m"]
    assert spans[0]["altitude_max_m"] == 30.1
    assert spans[0]["samples"] == 2
    assert spans[-1]["start_s"] == 4.


def test_loss_stimulus_has_no_target_angle_or_manufactured_measurement_timestamp():
    output = loss_tracker_output()
    evidence = TargetEvidenceSnapshot.from_tracker_output(output, session_epoch=1)
    assert evidence.state is TargetEvidenceState.ABSENT
    assert output.angular is None
    assert "angle_sample_monotonic" not in output.raw_data
    assert output.raw_data["usable_for_following"] is False


def test_adjacent_loss_windows_remain_one_uninterrupted_absence():
    windows = component_loss_windows([
        dict(kind="target_loss", at_s=2., duration_s=1.),
        dict(kind="target_loss", at_s=1., duration_s=1.),
    ], 10.)
    assert windows == [(1., 2.), (2., 3.)]
    assert all(any(start <= at < end for start, end in windows) for at in [1., 1.9, 2., 2.9])
    assert not any(start <= 3. < end for start, end in windows)


@pytest.mark.parametrize("at,length", [(-1., 1.), (0., 0.), (True, 1.), (1., False),
                                       (float("nan"), 1.), (1., float("inf")), (9., 2.)])
def test_loss_windows_reject_invalid_or_uncovered_intervals(at, length):
    with pytest.raises(ValueError, match="loss_window_invalid"):
        component_loss_windows([dict(kind="target_loss", at_s=at, duration_s=length)], 10.)


def test_loss_windows_reject_overlap_and_unimplemented_faults():
    with pytest.raises(ValueError, match="windows_overlap"):
        component_loss_windows([dict(kind="target_loss", at_s=1., duration_s=2.),
                                dict(kind="target_loss", at_s=2., duration_s=2.)], 10.)
    with pytest.raises(ValueError, match="fault_injection_not_implemented"):
        component_loss_windows([dict(kind="pilot_takeover", at_s=1., duration_s=2.)], 10.)


def test_airspeed_windows_are_typed_bounded_and_do_not_reanchor_target(tmp_path):
    raw = image_scenario()
    raw['faults'] = [dict(kind='airspeed_loss', at_s=2., duration_s=3.)]
    original = deepcopy(raw)
    path = tmp_path / 'scenario.yaml'
    path.write_text(yaml.safe_dump(raw))
    loaded = load_component_scenario(path, mount='HORIZONTAL', altitude=False, duration=10.,
                                     is_vtol=False, follower='fw_navigation_chase')
    assert loaded['target'] == original['target']
    assert raw == original
    window, = component_fault_windows(raw['faults'], 10.)
    assert (window.kind, window.start_s, window.end_s) == ('airspeed_loss', 2., 5.)
    target = component_fault_windows([dict(kind='target_loss', at_s=1., duration_s=2.)], 10.)
    assert [(row.start_s, row.end_s) for row in target] == component_loss_windows(
        [dict(kind='target_loss', at_s=1., duration_s=2.)], 10.)


@pytest.mark.parametrize('at,length', [(-1., 1.), (0., 0.), (True, 1.), (1., False),
                                      (float('nan'), 1.), (1., float('inf')), (9., 2.)])
def test_airspeed_fault_rejects_invalid_or_uncovered_intervals(at, length):
    with pytest.raises(ValueError, match='loss_window_invalid'):
        component_fault_windows([dict(kind='airspeed_loss', at_s=at, duration_s=length)], 10.)


@pytest.mark.parametrize('faults,code', [
    ([dict(kind='target_loss', at_s=1., duration_s=2.), dict(kind='airspeed_loss', at_s=4., duration_s=1.)], 'families_mixed'),
    ([dict(kind='airspeed_loss', at_s=1., duration_s=2.), dict(kind='airspeed_loss', at_s=2., duration_s=2.)], 'windows_overlap'),
    ([dict(kind='airspeed_loss', at_s=1., duration_s=2., instance=2)], 'loss_window_invalid'),
    ([dict(kind=['airspeed_loss'], at_s=1., duration_s=2.)], 'injection_not_implemented'),
    ([None], 'injection_not_implemented'),
])
def test_fault_family_scope_and_shape_are_closed(faults, code):
    with pytest.raises(ValueError, match=code):
        component_fault_windows(faults, 10.)


@pytest.mark.parametrize('duration', [True, 0., -1., float('nan'), float('inf')])
def test_fault_run_duration_must_be_finite_and_positive(duration):
    with pytest.raises(ValueError, match='fault_duration_invalid'):
        component_fault_windows([dict(kind='airspeed_loss', at_s=0., duration_s=1.)], duration)


@pytest.mark.parametrize("unsafe", ["host_network", "bridge_network", "container_network", "privileged", "devices", "ports", None])
def test_simulator_isolation_is_checked_before_control(monkeypatch, tmp_path, unsafe):
    path = tmp_path / "native.sock"
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(path))
    inspect = {
        "Id": "container-id", "Image": "sha256:test-image",
        "HostConfig": {"NetworkMode": "none", "Privileged": False, "Devices": []},
        "NetworkSettings": {"Ports": {}},
        "Mounts": [{"Source": str(tmp_path), "Destination": "/sih"}],
    }
    if unsafe == "host_network":
        inspect["HostConfig"]["NetworkMode"] = "host"
    if unsafe in {"bridge_network", "container_network"}:
        inspect["HostConfig"]["NetworkMode"] = "bridge" if unsafe == "bridge_network" else "container:unverified"
    if unsafe == "privileged":
        inspect["HostConfig"]["Privileged"] = True
    if unsafe == "devices":
        inspect["HostConfig"]["Devices"] = [{"PathOnHost": "/dev/ttyUSB0"}]
    if unsafe == "ports":
        inspect["NetworkSettings"]["Ports"] = {"14550/udp": []}
    calls = []

    def read_command(*args):
        calls.append(args)
        if args[1] == "inspect":
            return json.dumps([inspect])
        if "python3" in args:
            return json.dumps([dict(args=["/src/build/px4_sitl_sih/bin/px4", "-i", "7"],
                                    model="sihsim_airplane", cwd="/sih/rootfs")])
        return "autopilot_uid: 123456789\n"

    monkeypatch.setattr("tools.run_native_vector_sih.command", read_command)
    try:
        if unsafe:
            with pytest.raises(ValueError, match="isolated container"):
                verify_simulator("sim", 7, path)
            assert len(calls) == 1
        else:
            info = verify_simulator("sim", 7, path)
            assert info["aircraft_uid"] == "123456789"
            assert info["native_socket"] == "/sih/native.sock"
            assert all("arm" not in call and "takeoff" not in call for call in calls)
    finally:
        listener.close()


@pytest.mark.parametrize('matching', [True, False])
@pytest.mark.parametrize('explicit_authority', [False, True])
def test_source_build_verifies_actual_process_bytes_without_a_checkout_path_convention(monkeypatch, tmp_path, matching, explicit_authority):
    path = tmp_path / 'native.sock'
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        (tmp_path/'manifest.json').write_text(json.dumps({'kind': 'pixeagle_sih_build'}))
        baseline = {'binary_sha256': 'a'*64, 'kind': 'verified_source_build',
                    'manifest_sha256': hashlib.sha256((tmp_path/'manifest.json').read_bytes()).hexdigest()}
        validator = Mock(return_value=baseline)
        monkeypatch.setattr('tools.sih_baseline.validate_build_manifest', validator)
        authority = {'build_repository': tmp_path/'authority'} if explicit_authority else {}

        def read_command(*args):
            if args[1] == 'inspect':
                return json.dumps([{'Id': 'sim-id', 'Image': 'native-runtime-image',
                    'HostConfig': {'NetworkMode': 'none', 'Privileged': False, 'Devices': []},
                    'NetworkSettings': {'Ports': {}},
                    'Mounts': [{'Source': str(tmp_path), 'Destination': '/runtime'}]}])
            if 'python3' in args:
                assert args[-1] == 'verify'
                return json.dumps([{'args': ['/firmware/bin/px4', '-d', '-i', '0'],
                    'model': 'sihsim_airplane', 'cwd': '/runtime/rootfs',
                    'binary_sha256': ('a' if matching else 'b')*64}])
            assert '/firmware/bin/px4-listener' in args
            return 'autopilot_uid: 123456789\n'

        monkeypatch.setattr('tools.run_native_vector_sih.command', read_command)
        if matching:
            result = verify_simulator('sim', 0, path, simulation_build_manifest=tmp_path/'manifest.json', **authority)
            assert result['firmware_build'] is baseline
            assert result['native_socket'] == '/runtime/native.sock'
        else:
            with pytest.raises(ValueError, match='differs from the verified source build'):
                verify_simulator('sim', 0, path, simulation_build_manifest=tmp_path/'manifest.json', **authority)
        validator.assert_called_once_with(tmp_path/'manifest.json',
            **({'repository': authority['build_repository']} if explicit_authority else {}))


def test_explicit_build_authority_without_manifest_cannot_downgrade_to_legacy_inspection(tmp_path, monkeypatch):
    command = Mock(side_effect=AssertionError('No container inspection without the manifest'))
    monkeypatch.setattr(tool, 'command', command)
    with pytest.raises(ValueError, match='requires a verified build manifest'):
        verify_simulator('sim', 0, tmp_path/'native.sock', build_repository=tmp_path/'authority')
    path, isolation, contract, _ = cli_transition_context(tmp_path)
    isolation['firmware_build'] = None
    with pytest.raises(ValueError, match='requires a verified build manifest'):
        tool.native_pilot_transition(path, isolation, tool.PilotTransitionEvent(4., AirframePhase.FIXED_WING),
                                    AirframePhase.MULTICOPTER, contract, build_repository=tmp_path/'authority')
    command.assert_not_called()


def test_real_derived_manifest_requires_explicit_context_without_changing_default_authority(tmp_path, monkeypatch):
    from tests.unit.test_sih_baseline import build_manifest
    from tools import sih_baseline
    from tools.px4_functional import select_regression, source_authority

    _, record = select_regression(ROOT, 'fw-mode-transition-heading')
    original_root = tool.ROOT
    with source_authority(ROOT, 'baseline', record) as authority:
        manifest_path, manifest, image = build_manifest(authority, tmp_path/'derived-build')
        monkeypatch.setattr(sih_baseline, 'command', lambda *args: json.dumps([image]))
        path = tmp_path/'native.sock'
        calls = []
        def read_command(*args):
            calls.append(args)
            if args[1] == 'inspect':
                return json.dumps([{'Id':'sim-id','Image':'combined-ros-runtime',
                    'HostConfig':{'NetworkMode':'none','Privileged':False,'Devices':[]},
                    'NetworkSettings':{'Ports':{}},
                    'Mounts':[{'Source':str(tmp_path),'Destination':'/runtime'}]}])
            if 'python3' in args:
                return json.dumps([dict(args=['/firmware/bin/px4','-i','0'],model='sihsim_xvert',
                    cwd='/runtime/rootfs',binary_sha256=manifest['artifacts']['binary_sha256'])])
            return 'autopilot_uid: 123456789\n'
        monkeypatch.setattr(tool, 'command', read_command)
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(path))
            for supplied in [{}, {'build_repository':ROOT}]:
                with pytest.raises(ValueError, match='reviewed build recipe'):
                    verify_simulator('sim',0,path,simulation_build_manifest=manifest_path,**supplied)
            assert not any('python3' in call for call in calls)
            checked = verify_simulator('sim',0,path,simulation_build_manifest=manifest_path,build_repository=authority)
            assert checked['firmware_build']['firmware']['extension_sha256'] == manifest['firmware']['extension_sha256']
            assert checked['image_id'] != checked['firmware_build']['image_id']
            assert checked['process']['binary_sha256'] == manifest['artifacts']['binary_sha256']
            assert tool.ROOT == original_root
            with pytest.raises(ValueError, match='reviewed build recipe'):
                verify_simulator('sim',0,path,simulation_build_manifest=manifest_path)


def test_vtol_component_group_requires_settled_strategies_without_transition_pursuit():
    selected = component_profile("gm_velocity_vector")
    assert set(selected.profile.phase_command_contracts) == {"multicopter", "fixed_wing"}
    assert selected.command_contract(is_vtol=True) == "vtol_external"


def retained_post_release_fixture():
    from pathlib import Path
    return json.loads((Path(__file__).parent/'fixtures/native_post_release_observations.json').read_text())


def write_projection_evidence(root, evidence):
    paths = {'pose': 'px4/pose_trace.jsonl', 'target': 'trace/target_truth.jsonl',
             'state': 'trace/follower_state.jsonl', 'published': 'trace/offboard_publish_trace.jsonl',
             'tracker': 'trace/tracker_command_trace.jsonl'}
    for key, name in paths.items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(row)+'\n' for row in evidence.get(key, [])))


def test_actual_post_stop_packets_close_the_retained_replay_gap_without_invented_commands(tmp_path):
    from classes.native_guidance import NativeAcquisitionContext
    from classes.sih_visualization import VisualizationScenario, analyze_timeline, build_timeline, load_evidence
    fixture = retained_post_release_fixture()
    scenario_path = tmp_path/'scenario.yaml'
    scenario_path.write_text(yaml.safe_dump(fixture['scenario']))
    scenario = VisualizationScenario.from_yaml(scenario_path)
    old = {key: fixture['prefix_evidence'][key]+fixture['suffix_evidence'][key]
           for key in fixture['prefix_evidence']}
    write_projection_evidence(tmp_path, old)
    old_summary = analyze_timeline(scenario, build_timeline(scenario, load_evidence(tmp_path)))
    assert old_summary['stale_after_fresh_samples'] == 1
    assert old_summary['max_timestamp_gap_s'] == pytest.approx(.6175315040018177)
    assert any(row['type'] == 'command_or_pose_gap' for row in old_summary['flags'])
    current = deepcopy(fixture['prefix_evidence'])
    names = {'px4/pose_trace.jsonl': 'pose', 'trace/target_truth.jsonl': 'target',
             'trace/follower_state.jsonl': 'state'}
    logged = []
    def log(name, row):
        logged.append(name)
        current[names[name]].append(row)
    context = NativeAcquisitionContext.from_payload(fixture['acquisition'])
    previous_pose, released_at, count = current['pose'][-1]['px4_timestamp_us'], None, None
    packets_before = deepcopy(fixture['observations'])
    for observation in fixture['observations']:
        packet = observation['packet']
        _, previous_pose, released_at, count = tool.record_released_observation(
            packet, context, captured_at=observation['captured_at_monotonic_s'],
            follow_start=fixture['follow_start_monotonic_s'], log=log, scenario=scenario,
            previous_pose_timestamp_us=previous_pose, release_observed_at=released_at, previous_publications=count)
        assert current['pose'][-1]['observed_at_monotonic_s'] == packet['vehicle_pose']['observed_at_monotonic_s']
        assert current['state'][-1]['aircraft_observed_at_monotonic_s'] == packet['aircraft_state']['observed_at_monotonic_s']
        assert current['state'][-1]['captured_at_monotonic_s'] == observation['captured_at_monotonic_s']
    # The final confirmation already contains the first later capture's retained pose sample.
    assert current['pose'][-1]['px4_timestamp_us'] == fixture['suffix_evidence']['pose'][0]['px4_timestamp_us']
    write_projection_evidence(tmp_path, current)
    samples = build_timeline(scenario, load_evidence(tmp_path))
    summary = analyze_timeline(scenario, samples)
    assert summary['stale_after_fresh_samples'] == 0
    assert not any(row['type'] in {'command_or_pose_gap', 'publication_after_authority_release'}
                   for row in summary['flags'])
    assert all(not row.published and not row.command for row in samples if row.timestamp >= released_at)
    assert fixture['observations'] == packets_before
    assert set(logged) == set(names) and current['tracker'] == []
    assert len({row['px4_timestamp_us'] for row in current['pose']}) == len(current['pose'])


@pytest.mark.parametrize('bad', ['missing_pose', 'stale_pose', 'stale_state', 'not_fresh'])
def test_missing_or_stale_actual_post_stop_sample_keeps_the_replay_unknown(tmp_path, bad):
    from classes.native_guidance import NativeAcquisitionContext
    from classes.sih_visualization import VisualizationScenario, analyze_timeline, build_timeline, load_evidence
    fixture = retained_post_release_fixture()
    context = NativeAcquisitionContext.from_payload(fixture['acquisition'])
    logged = []
    original_pose = fixture['prefix_evidence']['pose'][-1]['px4_timestamp_us']
    target = Mock(side_effect=AssertionError('No target projection can legitimize unavailable observed pose'))
    for observation in fixture['observations']:
        packet = deepcopy(observation['packet'])
        if bad == 'missing_pose':
            packet['vehicle_pose'] = None
        elif bad == 'stale_pose':
            packet['vehicle_pose']['observed_at_monotonic_s'] -= 10.
        elif bad == 'stale_state':
            packet['aircraft_state']['observed_at_monotonic_s'] -= 10.
        else:
            packet['fresh'] = False
        state, previous, _, count = tool.record_released_observation(
            packet, context, captured_at=observation['captured_at_monotonic_s'],
            follow_start=fixture['follow_start_monotonic_s'], log=lambda *row: logged.append(row),
            scenario=SimpleNamespace(target_at=target), previous_pose_timestamp_us=original_pose)
        assert state is None and previous == original_pose and count == 251
    assert not logged
    target.assert_not_called()
    path = tmp_path/'scenario.yaml'
    path.write_text(yaml.safe_dump(fixture['scenario']))
    evidence = {key: fixture['prefix_evidence'][key]+fixture['suffix_evidence'][key]
                for key in fixture['prefix_evidence']}
    write_projection_evidence(tmp_path, evidence)
    scenario = VisualizationScenario.from_yaml(path)
    assert analyze_timeline(scenario, build_timeline(scenario, load_evidence(tmp_path)))['stale_after_fresh_samples'] == 1


def test_duplicate_actual_pose_identity_never_refreshes_movement_evidence():
    from classes.native_guidance import NativeAcquisitionContext
    fixture = retained_post_release_fixture()
    context = NativeAcquisitionContext.from_payload(fixture['acquisition'])
    logged = []
    original_pose = fixture['prefix_evidence']['pose'][-1]['px4_timestamp_us']
    for observation in fixture['observations']:
        packet = deepcopy(observation['packet'])
        packet['vehicle_pose']['px4_timestamp_us'] = original_pose
        _, stamp, _, _ = tool.record_released_observation(packet, context,
            captured_at=observation['captured_at_monotonic_s'], follow_start=fixture['follow_start_monotonic_s'],
            scenario=SimpleNamespace(target_at=lambda _: (180., 35., -30.)),
            log=lambda *row: logged.append(row), previous_pose_timestamp_us=original_pose)
        assert stamp == original_pose
    assert not any(name == 'px4/pose_trace.jsonl' for name, _ in logged)
    assert all(row['command_expected'] is False for name, row in logged if name == 'trace/follower_state.jsonl')


@pytest.mark.parametrize('bad', ['owner', 'runtime', 'token', 'unconfirmed', 'binding', 'publication'])
def test_post_stop_projection_needs_original_release_proof_before_any_inactive_record(bad):
    from classes.native_guidance import NativeAcquisitionContext
    fixture = retained_post_release_fixture()
    sample = deepcopy(fixture['observations'][0])
    packet = sample['packet']
    context = NativeAcquisitionContext.from_payload(fixture['acquisition'])
    if bad == 'owner':
        packet['owner_confirmed'] = True
    elif bad == 'runtime':
        packet['runtime_id'] = 'replacement-runtime'
    elif bad == 'token':
        packet['release_receipt']['acquisition']['token'] = 'a'*32
    elif bad == 'unconfirmed':
        packet['release_receipt']['outcome'] = 'unconfirmed'
    elif bad == 'binding':
        packet['aircraft_state']['binding']['aircraft_uid'] = 'replacement-aircraft'
    else:
        packet['publications'] += 1
    log = Mock()
    with pytest.raises((ValueError, RuntimeError)):
        tool.record_released_observation(packet, context, captured_at=sample['captured_at_monotonic_s'],
            follow_start=fixture['follow_start_monotonic_s'], log=log,
            scenario=SimpleNamespace(target_at=lambda _: (180., 35., -30.)), previous_publications=251)
    log.assert_not_called()


async def test_later_readonly_capture_preserves_post_stop_publication_cursor():
    from classes.native_guidance import NativeAcquisitionContext
    fixture = retained_post_release_fixture()
    sample = deepcopy(fixture['observations'][-1])
    context = NativeAcquisitionContext.from_payload(fixture['acquisition'])
    sample['packet']['publications'] += 1
    client = SimpleNamespace(observe=AsyncMock(return_value=sample['packet']))
    logs = []
    with pytest.raises(ValueError, match='publication_after_release'):
        await tool.capture_post_transition(client, tool.PilotTransitionEvent(8., AirframePhase.FIXED_WING), context,
            log=lambda *row: logs.append(row), started=fixture['follow_start_monotonic_s'],
            follow_start=fixture['follow_start_monotonic_s'], timeout_s=1.,
            scenario=SimpleNamespace(target_at=lambda _: (180., 35., -30.)), response=[],
            previous_publications=251, previous_pose_timestamp_us=sample['packet']['vehicle_pose']['px4_timestamp_us'],
            release_observed_at=8.6, clock=lambda: sample['captured_at_monotonic_s'])
    assert [name for name, _ in logs] == ['post-transition-observations.jsonl']
    assert logs[0][1]['value'] is sample['packet']  # Raw original packet is retained before projection validation.


async def test_later_readonly_capture_does_not_reemit_the_final_confirmation_pose(monkeypatch):
    from classes.native_guidance import NativeAcquisitionContext
    fixture = retained_post_release_fixture()
    sample = fixture['observations'][-1]
    context = NativeAcquisitionContext.from_payload(fixture['acquisition'])
    client = SimpleNamespace(observe=AsyncMock(return_value=sample['packet']))
    logs, now = [], [sample['captured_at_monotonic_s']]
    async def advance(_):
        now[0] += .2
    monkeypatch.setattr(tool.asyncio, 'sleep', advance)
    with pytest.raises(TimeoutError, match='settle_timeout'):
        await tool.capture_post_transition(client, tool.PilotTransitionEvent(8., AirframePhase.FIXED_WING), context,
            log=lambda *row: logs.append(row), started=fixture['follow_start_monotonic_s'],
            follow_start=fixture['follow_start_monotonic_s'], timeout_s=.1,
            scenario=SimpleNamespace(target_at=lambda _: (180., 35., -30.)), response=[],
            previous_publications=251, previous_pose_timestamp_us=sample['packet']['vehicle_pose']['px4_timestamp_us'],
            release_observed_at=8.6, clock=lambda: now[0])
    assert client.observe.await_count == 1
    assert not any(name == 'px4/pose_trace.jsonl' for name, _ in logs)
    states = [row for name, row in logs if name == 'trace/follower_state.jsonl']
    assert states[0]['command_owner_released_at'] == 8.6
    assert states[0]['pose_timestamp_us'] == sample['packet']['vehicle_pose']['px4_timestamp_us']


async def test_failed_existing_commander_join_cannot_claim_inactive_projection(monkeypatch):
    from classes.offboard_commander import OffboardCommander
    release, entered = asyncio.Event(), asyncio.Event()
    async def retained_task():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await release.wait()
    task = asyncio.create_task(retained_task())
    await entered.wait()
    original_wait = asyncio.wait
    async def elapsed_existing_budget(tasks, *, timeout):
        return await original_wait(tasks, timeout=0.)
    monkeypatch.setattr(asyncio, 'wait', elapsed_existing_budget)
    commander = OffboardCommander(SimpleNamespace(), SimpleNamespace(profile_name='unit'), command_rate_hz=20.,
                                  command_ttl_s=.5, publish_timeout_s=.25)
    commander.running, commander._task = True, task
    project = Mock(side_effect=AssertionError('Failed join cannot produce an inactive/result projection'))
    try:
        with pytest.raises(RuntimeError, match='publisher_not_quiesced'):
            await tool.stop_component_publisher(commander)
            project()
        assert commander._task is task and not task.done()
        assert 'ignored cancellation' in commander.last_error
        project.assert_not_called()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
