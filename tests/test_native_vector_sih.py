"""Isolated native SIH harness gates; these tests never command an aircraft."""

from copy import deepcopy
from dataclasses import asdict, replace
import asyncio
import json
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


native_follower_environment = native_image_cases.environment


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
            confirmation_s=0., observation_timeout_s=.75, transition_timeout_s=10., clock=lambda: env.now[0])
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
        confirmation_s=.3, observation_timeout_s=.75, transition_timeout_s=10., clock=lambda: env.now[0],
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
        if 'ownership_token' in kwargs:
            client.acquisition_token = kwargs['ownership_token']
            client.acquisition_context = acquisition(identity, token=client.acquisition_token, runtime_id='native-fixture')
            return {'owner_confirmed': True, 'runtime_id': 'native-fixture',
                    'acquisition': client.acquisition_context.wire_payload()}

    client.matches_acquisition = lambda original, runtime, token, known=None: (
        client.acquisition_context is not None and original == client.acquisition_context.identity
        and runtime == client.acquisition_context.runtime_id and token == client.acquisition_context.token
        and (known is None or known == client.acquisition_context))
    client.engage = AsyncMock(side_effect=own)
    client.advance_generation = AsyncMock(side_effect=own)
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
    with pytest.raises(ValueError, match="vtol_contract_unavailable"):
        selected.command_contract(is_vtol=True)


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
                    relative_altitude_m=30., velocity_ned_m_s=replace(sample.velocity_ned_m_s, z=0.))
            for n in range(7)]


def test_fw_stable_gate_requires_seven_consecutive_airborne_native_samples():
    states = flight_window()
    assert stable_window(states)
    assert not stable_window(states[:-1])
    assert not stable_window([replace(s, observed_at_monotonic_s=100. + n * .01)
                              for n, s in enumerate(states)])


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
def test_source_build_verifies_actual_process_bytes_without_a_checkout_path_convention(monkeypatch, tmp_path, matching):
    path = tmp_path / 'native.sock'
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        baseline = {'binary_sha256': 'a'*64, 'kind': 'verified_source_build'}
        monkeypatch.setattr('tools.sih_baseline.validate_build_manifest', lambda _: baseline)

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
            result = verify_simulator('sim', 0, path, sih_build_manifest=tmp_path/'manifest.json')
            assert result['firmware_build'] is baseline
            assert result['native_socket'] == '/runtime/native.sock'
        else:
            with pytest.raises(ValueError, match='differs from the verified source build'):
                verify_simulator('sim', 0, path, sih_build_manifest=tmp_path/'manifest.json')
