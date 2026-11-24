"""Receipt/source contracts with real parsers and no transport or aircraft IO."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, replace
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from classes.app_controller import AppController
from classes.aircraft_state import Quaternion
from classes.camera_runtime import CameraRuntime
from classes.gimbal_provider import create_gimbal_provider
from classes.gimbal_types import GimbalAngleObservation
from classes.parameters import Parameters
from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.target_continuity import TargetEvidenceSnapshot, TargetEvidenceState
from classes.tracker_runtime_status import evaluate_tracker_command_freshness
from classes.trackers.gimbal_tracker import GimbalTracker
from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower


ANGLE = '#tpGPCrGAC0000000000005E'
ACTIVE = '#TPDP2rTRC024A'


def ingest(provider, wire):
    data = provider._parse_gimbal_packet(wire)
    with provider.lock:
        return provider._ingest_parsed_data_locked(data, wire)


@pytest.fixture
def environment(monkeypatch):
    previous = Parameters.get_runtime_config_snapshot()
    defaults = yaml.safe_load((Path(__file__).resolve().parents[3] / 'configs/config_default.yaml').read_text())
    now = [100.]
    monkeypatch.setattr('classes.gimbal_interface.time.monotonic', lambda: now[0])
    runtimes = []

    def build(mount='HORIZONTAL'):
        config = deepcopy(defaults)
        config['GimbalTracker'].update(ENABLED=True, MOUNT_TYPE=mount)
        Parameters.publish_config_mapping(config)
        app = object.__new__(AppController)
        app.estimator = None
        app._tracking_session_generation = 7
        app.current_tracker_type, app.smart_mode_active = 'Gimbal', False
        app.frame_publisher = SimpleNamespace(control_source_epoch='video-1')
        runtime = CameraRuntime(app, config['GimbalTracker'])
        runtime.provider = create_gimbal_provider(config['GimbalTracker'])
        fake_workers(monkeypatch)
        monkeypatch.setattr(runtime.provider, '_init_listening_socket', lambda: True)
        assert runtime.start()
        runtimes.append(runtime)
        app.camera_runtime = runtime
        app.tracker = GimbalTracker(None, None, app)
        app.tracker.monitoring_active = True
        app._tracker_requires_video_for_following = lambda: False
        now[0] += .05
        ingest(runtime.provider, ANGLE)
        ingest(runtime.provider, ACTIVE)
        return SimpleNamespace(app=app, runtime=runtime, provider=runtime.provider, tracker=app.tracker, now=now)

    try:
        yield build
    finally:
        for runtime in runtimes:
            runtime.close()
        Parameters.publish_config_mapping(previous)


def output(env):
    success, result = env.tracker.update(None)
    assert success
    return result


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_typed_boresight_preserves_raw_angles_and_independent_receipts_without_pixels(environment, mount):
    env = environment(mount)
    first = output(env)
    observation = first.gimbal_observation
    assert isinstance(observation, GimbalAngleObservation)
    assert observation.source == env.runtime.angle_observation_context()
    assert observation.angles_deg == first.angular == (0., 0., 0.)
    assert observation.target_generation == env.app._tracking_session_generation == 7
    assert observation.time_basis == 'backend_receipt'
    assert observation.bearing_semantics == 'camera_boresight'
    assert observation.physical_target_identity_confirmed is False
    assert first.position_2d is first.image_measurement is None
    assert not env.tracker.get_capabilities()['supports_normalization']
    env.now[0] += .1
    assert output(env).gimbal_observation is observation
    ingest(env.provider, ACTIVE)
    updated = output(env).gimbal_observation
    assert updated.angle_receipt_sequence == observation.angle_receipt_sequence
    assert updated.angle_received_at_monotonic_s == observation.angle_received_at_monotonic_s
    assert updated.tracking_received_at_monotonic_s > observation.tracking_received_at_monotonic_s
    assert env.app._tracking_session_generation == 7  # Handset TRC has no target ID.
    with pytest.raises(FrozenInstanceError):
        updated.target_generation = 8
    decoded = TrackerOutput.from_dict(json.loads(json.dumps(first.to_dict())))
    assert decoded.gimbal_observation == observation


def test_geometry_revision_tracks_canonical_mount_mapping(environment):
    horizontal = output(environment('HORIZONTAL')).gimbal_observation.geometry_revision
    vertical = output(environment('VERTICAL')).gimbal_observation.geometry_revision
    assert horizontal != vertical
    assert horizontal == output(environment('HORIZONTAL')).gimbal_observation.geometry_revision


def test_video_epoch_does_not_change_angle_owner_or_packet_identity(environment):
    env = environment()
    current = output(env)
    first = current.gimbal_observation
    env.app.get_tracker_output = lambda: current
    identity = env.app._freeze_following_observation_source()
    env.app.frame_publisher.control_source_epoch = 'video-2'
    assert env.app._follow_start_input_identity() == identity
    assert output(env).gimbal_observation is first


@pytest.mark.parametrize('mutation', ['target', 'owner'])
def test_race_during_provider_read_cannot_stamp_a_new_binding(environment, monkeypatch, mutation):
    env = environment()
    read = env.provider.get_current_data

    def racing_read():
        result = read()
        if mutation == 'target':
            env.app._advance_tracking_session_generation()
        else:
            env.runtime.close()
        return result

    monkeypatch.setattr(env.provider, 'get_current_data', racing_read)
    result = output(env)
    assert result.angular == (0., 0., 0.)
    assert result.gimbal_observation is None
    assert result.metadata['gimbal_observation_reason'] == 'gimbal_observation_owner_changed'
    assert not evaluate_tracker_command_freshness(result)['usable_for_following']
    assert TargetEvidenceSnapshot.from_tracker_output(result, session_epoch=env.app._tracking_session_generation).state is not TargetEvidenceState.CONFIRMED


def test_target_change_during_output_creation_is_unusable_on_normal_evidence_path(environment, monkeypatch):
    env = environment()

    def racing_output(*args, **kwargs):
        value = TrackerOutput(*args, **kwargs)
        env.app._advance_tracking_session_generation()
        return value

    monkeypatch.setattr('classes.trackers.gimbal_tracker.TrackerOutput', racing_output)
    result = output(env)
    assert result.gimbal_observation is None
    assert not evaluate_tracker_command_freshness(result)['usable_for_following']
    assert result.timestamp == result.raw_data['angle_sample_timestamp']
    assert TargetEvidenceSnapshot.from_tracker_output(result, session_epoch=env.app._tracking_session_generation).state is not TargetEvidenceState.CONFIRMED


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('follower_class', [GMVelocityChaseFollower, GMVelocityVectorFollower])
def test_new_metadata_keeps_existing_nonzero_angular_command_calculations(environment, mount, follower_class):
    env = environment(mount)
    angles = (20., 15., 0.) if mount == 'HORIZONTAL' else (0., 105., -20.)
    body = ('#tpGPCrGAC' + ''.join(f'{round(value * 100) & 65535:04X}' for value in angles)).encode('ascii')
    env.now[0] += .05
    ingest(env.provider, body + f'{sum(body) & 255:02X}'.encode('ascii'))
    current = output(env)
    assert current.angular == angles and current.position_2d is None
    assert evaluate_tracker_command_freshness(current)['usable_for_following']
    legacy = TrackerOutput(TrackerDataType.GIMBAL_ANGLES, current.timestamp, True, angular=angles)

    def calculate(value):
        controller = SimpleNamespace(current_altitude=50., is_command_preview=False,
            is_command_connection_ready=lambda **_: True,
            get_guidance_attitude=lambda: (Quaternion(1., 0., 0., 0.), 0.))
        follower = follower_class(controller, (0., 0.))
        follower.calculate_control_commands(value)
        return follower.get_last_command_intent().fields

    assert calculate(current) == pytest.approx(calculate(legacy))


def test_source_generation_rejects_old_receipts_until_actual_gac_progress(environment):
    env = environment()
    first = output(env)
    old_data = env.provider.get_current_data()
    env.app.get_tracker_output = lambda: first
    identity = env.app._freeze_following_observation_source()
    env.provider.stop()
    assert env.provider.start()
    assert env.app._follow_start_input_identity() != identity
    success, rejected = env.tracker._process_gimbal_data(old_data, True)
    assert success and rejected.gimbal_observation is None
    env.now[0] += .1
    new_data = ingest(env.provider, ANGLE)
    new_data.tracking_status = old_data.tracking_status
    new_data.tracking_sample_monotonic = old_data.tracking_sample_monotonic
    success, new = env.tracker._process_gimbal_data(new_data, True)
    assert success
    assert new.gimbal_observation.source != first.gimbal_observation.source
    assert new.gimbal_observation.angle_receipt_sequence > first.gimbal_observation.angle_receipt_sequence
    assert new.gimbal_observation.tracking_state is None
    assert new.gimbal_observation.tracking_received_at_monotonic_s is None
    assert new.metadata['gimbal_observation_reason'] == 'tracking_receipt_precedes_owner_generation'
    assert not evaluate_tracker_command_freshness(new)['usable_for_following']
    env.app._camera_selection_dispatched_wall_time = 0.
    env.app._camera_selection_dispatched_monotonic = 100.
    assert not env.app._camera_angle_sample_current(new, require_tracking=True)
    env.now[0] += .05
    ingest(env.provider, ACTIVE)
    assert env.app._camera_angle_sample_current(output(env), require_tracking=True)


def test_new_trc_cannot_attach_old_gac_to_new_owner_generation(environment):
    env = environment()
    old_data = env.provider.get_current_data()
    env.provider.stop()
    assert env.provider.start()
    env.now[0] += .1
    new_status = ingest(env.provider, ACTIVE)
    old_data.tracking_status = new_status.tracking_status
    old_data.tracking_sample_monotonic = new_status.tracking_sample_monotonic
    success, retired = env.tracker._process_gimbal_data(old_data, True)
    assert success
    assert retired.gimbal_observation is None
    assert retired.metadata['gimbal_observation_reason'] == 'gimbal_receipt_precedes_owner_generation'
    assert not evaluate_tracker_command_freshness(retired)['usable_for_following']


def test_same_object_restart_invalidates_startup_and_retarget_context(environment, monkeypatch):
    env = environment()
    first = output(env)
    env.app._camera_selection_dispatched_wall_time = 0.
    env.app._camera_selection_dispatched_monotonic = 100.
    assert env.app._camera_angle_sample_current(first, require_tracking=True)
    env.app.get_tracker_output = lambda: first
    identity = env.app._freeze_following_observation_source()
    fake_workers(monkeypatch)
    monkeypatch.setattr(env.provider, '_init_listening_socket', lambda: True)
    env.provider.stop_listening()
    assert env.runtime.start()
    assert env.provider.get_current_data() is None
    with pytest.raises(RuntimeError, match='following_input_context_changed'):
        env.app._require_follow_start_input_identity(identity, {}, stage='fixture')
    assert not env.app._camera_angle_sample_current(first, require_tracking=True)
    env.now[0] += .1
    ingest(env.provider, ANGLE)
    ingest(env.provider, ACTIVE)
    assert env.app._camera_angle_sample_current(output(env), require_tracking=True)


@pytest.mark.parametrize('change', ['sequence', 'receipt', 'angles', 'target'])
def test_existing_selection_guard_rejects_incoherent_typed_and_raw_snapshot(environment, change):
    env = environment()
    first = output(env)
    env.app._camera_selection_dispatched_wall_time = 0.
    env.app._camera_selection_dispatched_monotonic = 100.
    assert env.app._camera_angle_sample_current(first)
    if change == 'sequence':
        first.raw_data['angle_sample_sequence'] += 1
    elif change == 'receipt':
        first.raw_data['angle_sample_monotonic'] += .001
    elif change == 'angles':
        first.angular = (1., 0., 0.)
    else:
        env.app._advance_tracking_session_generation()
    assert not env.app._camera_angle_sample_current(first)


def fake_workers(monkeypatch):
    worker = SimpleNamespace(start=Mock(), join=Mock(), is_alive=lambda: False)
    monkeypatch.setattr('classes.gimbal_interface.threading.Thread', Mock(return_value=worker))
    monkeypatch.setattr('classes.gimbal_interface.time.sleep', lambda _: None)


@pytest.mark.parametrize('failure', ['socket', 'old_worker'])
def test_restart_failure_clears_both_receipts_and_never_publishes_owner(environment, monkeypatch, failure):
    env = environment()
    source = env.runtime.angle_observation_context()
    env.provider.running = False
    opening = Mock(return_value=False)
    monkeypatch.setattr(env.provider, '_init_listening_socket', opening)
    if failure == 'old_worker':
        env.provider.listener_thread = SimpleNamespace(is_alive=lambda: True, join=Mock())
    assert not env.runtime.start()
    assert env.runtime.angle_observation_context() is None
    assert env.provider.get_current_data() is None
    assert env.provider.current_angles is env.provider.current_tracking_status is None
    if failure == 'old_worker':
        opening.assert_not_called()
    assert source.source_generation != env.runtime._source_generation


def test_running_start_reuses_owner_and_receipts(environment):
    env = environment()
    first = output(env).gimbal_observation
    assert env.runtime.start()
    assert output(env).gimbal_observation is first


@pytest.mark.parametrize('operation', ['stop', 'detach'])
def test_command_stop_and_tracker_detach_do_not_change_angle_source(environment, operation):
    env = environment()
    first = output(env).gimbal_observation
    command_guard = env.runtime.guard()
    if operation == 'stop':
        env.runtime.acquire('fixture', 'stop')
    else:
        env.runtime.detach_tracker()
    assert env.runtime.guard()['camera_generation'] != command_guard['camera_generation']
    assert env.runtime.angle_observation_context() == first.source
    assert output(env).gimbal_observation is first


def test_direct_provider_aliases_change_source_and_invalidate_old_command_guards(environment):
    env = environment()
    first = output(env).gimbal_observation
    guard = env.runtime.guard()
    env.provider.stop()
    assert env.runtime.angle_observation_context() is None
    stopped = env.runtime.angle_source_identity()
    assert stopped is not None and stopped != first.source
    assert env.provider.start()
    assert env.provider.get_current_data() is None
    assert env.runtime.angle_observation_context() != first.source
    with pytest.raises(ValueError, match='changed'):
        env.runtime.validate_guard(guard)
    env.runtime.close()
    assert env.runtime.angle_observation_context() is None
    assert env.runtime.angle_source_identity() != stopped


def test_running_provider_replacement_is_refused_and_close_stops_original(environment, monkeypatch):
    env = environment()
    retired = env.provider
    source = env.runtime.angle_observation_context()
    replacement = create_gimbal_provider({'PROVIDER': 'topotek_sip_udp'})
    stopping = Mock(wraps=retired.stop_listening)
    monkeypatch.setattr(retired, 'stop_listening', stopping)
    with pytest.raises(ValueError, match='replacement_requires_new_owner'):
        env.runtime.provider = replacement
    assert env.runtime.get_provider() is retired
    assert env.runtime.angle_observation_context() == source
    env.runtime.close()
    stopping.assert_called_once_with()
    assert not retired.running


def test_standalone_metadata_has_no_invented_owner_or_target_generation(environment):
    env = environment()
    env.tracker._camera_runtime = None
    env.tracker.app_controller = None
    result = output(env)
    assert result.gimbal_observation.source is None
    assert result.gimbal_observation.target_generation is None
    assert result.position_2d is result.image_measurement is None
    assert result.metadata['gimbal_observation_reason'] == 'camera_owner_unavailable'


@pytest.mark.parametrize('operation', ['stop', 'detach', 'close'])
def test_blocked_start_never_blocks_stop_and_only_source_retirement_cancels_start(operation, monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    thread_factory = threading.Thread
    fake_workers(monkeypatch)
    provider = create_gimbal_provider({'PROVIDER': 'topotek_sip_udp'})

    def opening():
        entered.set()
        assert finish.wait(1.)
        return True

    monkeypatch.setattr(provider, '_init_listening_socket', opening)
    runtime = CameraRuntime(SimpleNamespace(), {'ENABLED': True})
    runtime.provider = provider
    results = []
    worker = thread_factory(target=lambda: results.append(runtime.start()))
    worker.start()
    closing = None
    try:
        assert entered.wait(1.)
        before = time.perf_counter()
        runtime.acquire('fixture', 'stop')
        assert runtime.angle_observation_context() is None
        assert time.perf_counter() - before < .1
        if operation == 'detach':
            runtime.detach_tracker()
        elif operation == 'close':
            close_entered = threading.Event()
            original_stop = provider.stop_listening

            def closing_stop():
                close_entered.set()
                original_stop()

            monkeypatch.setattr(provider, 'stop_listening', closing_stop)
            closing = thread_factory(target=runtime.close)
            closing.start()
            assert close_entered.wait(1.)
    finally:
        finish.set()
        worker.join(1.)
        if closing is not None:
            closing.join(1.)
    assert not worker.is_alive()
    assert results == [operation != 'close']
    assert (runtime.angle_observation_context() is None) == (operation == 'close')
    assert provider.running == (operation != 'close')
    runtime.close()


@pytest.mark.parametrize('changes', [
    {'angles_deg': (float('nan'), 0., 0.)}, {'angle_receipt_sequence': True},
    {'angle_received_at_monotonic_s': float('inf')}, {'target_generation': True},
    {'source': {}}, {'coordinate_system': 'spatial_fixed'},
])
def test_typed_observation_rejects_invalid_receipt_values(environment, changes):
    observation = output(environment()).gimbal_observation
    with pytest.raises(ValueError):
        replace(observation, **changes)


@pytest.mark.parametrize('changes', [{'position_2d': (0., 0.)}, {'angular': (1., 0., 0.)},
                                     {'data_type': TrackerDataType.POSITION_2D}])
def test_typed_receipt_cannot_be_attached_to_unrelated_pixels_or_angles(environment, changes):
    first = output(environment())
    with pytest.raises(ValueError, match='gimbal_observation_output_mismatch'):
        replace(first, **changes)


@pytest.mark.parametrize('change', ['missing', 'extra', 'source_list', 'source_extra', 'angles_none',
                                   'angles_bytes', 'angles_range', 'angles_mapping',
                                   'bool_receipt', 'nan_receipt', 'tracking_bool', 'tracking_nan',
                                   'source_generation_bool', 'false_as_int'])
def test_malformed_serialized_observation_has_stable_value_error(environment, change):
    payload = asdict(output(environment()).gimbal_observation)
    if change == 'missing':
        payload.pop('time_basis')
    elif change == 'extra':
        payload['invented_sample_time'] = 100.
    elif change == 'source_list':
        payload['source'] = []
    elif change == 'source_extra':
        payload['source']['video_epoch'] = 'unrelated'
    elif change == 'source_generation_bool':
        payload['source']['source_generation'] = True
    elif change == 'angles_none':
        payload['angles_deg'] = None
    elif change in ('angles_bytes', 'angles_range', 'angles_mapping'):
        payload['angles_deg'] = {'angles_bytes': bytes((0, 0, 0)), 'angles_range': range(3),
                                 'angles_mapping': {0: 'x', 1: 'y', 2: 'z'}}[change]
    elif change == 'false_as_int':
        payload['physical_target_identity_confirmed'] = 0
    elif change in ('tracking_bool', 'tracking_nan'):
        payload['tracking_received_at_monotonic_s'] = True if change == 'tracking_bool' else float('nan')
    else:
        payload['angle_received_at_monotonic_s'] = True if change == 'bool_receipt' else float('nan')
    with pytest.raises(ValueError):
        GimbalAngleObservation.from_dict(payload)


def test_unknown_provider_cannot_publish_a_qualified_source_context():
    provider = SimpleNamespace(running=True, manual_control=None)
    runtime = CameraRuntime(SimpleNamespace(), {'ENABLED': True})
    runtime.provider = provider
    assert runtime.start()
    assert runtime.angle_observation_context() is None
