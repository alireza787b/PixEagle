"""The simulated boresight producer uses real source and tracker contracts."""

from copy import deepcopy
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
import yaml

from classes.aircraft_state import Quaternion
from classes.app_controller import AppController
from classes.gimbal_geometry import body_line_of_sight
from classes.parameters import Parameters
from classes.tracker_output import TrackerDataType
from tools.mc_follower_sih import PoseProgress
from tools.sih_gimbal_world_target import SihGimbalWorldTarget
from tools.fixed_camera_world_target import MCScenario, evaluate_response, mc_input_family


@pytest.fixture
def environment(monkeypatch):
    previous = Parameters.get_runtime_config_snapshot()
    defaults = yaml.safe_load((Path(__file__).resolve().parents[2] / 'configs/config_default.yaml').read_text())
    now = [100.]
    monkeypatch.setattr('tools.sih_gimbal_world_target.time.monotonic', lambda: now[0])
    sources = []

    def build(mount, profile=None, altitude=False):
        config = deepcopy(defaults)
        config['GimbalTracker']['MOUNT_TYPE'] = mount
        if profile is not None:
            config['Follower']['FOLLOWER_MODE'] = profile
            config['Follower']['FollowerOverrides'].setdefault(profile.upper(), {})['ENABLE_ALTITUDE_CONTROL'] = altitude
        Parameters.publish_config_mapping(config)
        app = object.__new__(AppController)
        app._tracking_session_generation = 7
        app.following_active = False
        app.estimator = None
        source = SihGimbalWorldTarget(app, progress=PoseProgress())
        sources.append(source)
        return app, source

    try:
        yield build, now
    finally:
        for source in sources:
            source.close()
        Parameters.publish_config_mapping(previous)


def pose(now, source=(100, 110), *, position=(0., 0., -20.), quaternion=(1., 0., 0., 0.)):
    return dict(source_boot_ms=source, position_ned=position, quaternion_wxyz=quaternion, monotonic_s=now)


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_real_tracker_output_binds_real_runtime_without_synthetic_pixels(environment, mount):
    build, now = environment
    app, source = build(mount)
    now[0] += .01
    output = source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time())
    assert output.data_type is TrackerDataType.GIMBAL_ANGLES
    assert output.position_2d is output.image_measurement is None
    assert output.tracking_active and output.raw_data['usable_for_following']
    typed = output.gimbal_observation
    assert typed.source == source.runtime.angle_observation_context()
    assert typed.source.camera_id.startswith('sih-gimbal-world-target:')
    assert typed.target_generation == app._tracking_session_generation
    assert typed.geometry_revision == source.tracker._geometry_revision
    assert typed.bearing_semantics == 'camera_boresight'
    assert typed.physical_target_identity_confirmed is False
    assert source.provider.get_provider_metadata()['fixture_kind'] == 'simulated_boresight'
    assert 'guidance_capabilities' not in source.provider.get_provider_metadata()
    ray = body_line_of_sight(output.angular, mount)
    norm = (20. ** 2 + 4. ** 2 + 3. ** 2) ** .5
    assert ray == pytest.approx((20. / norm, 4. / norm, 3. / norm))
    assert app._freeze_following_observation_source() == app._follow_start_input_identity()


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('partial', [(120, 110), (100, 130), (100, 110)])
def test_partial_or_repeated_pose_preserves_original_target_receipts_and_sequence(environment, mount, partial):
    build, now = environment
    app, source = build(mount)
    now[0] += .01
    original = source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time())
    measurement = source.measurement
    now[0] += .1
    assert source.observe(pose(now[0], partial), (20., -6., -25.), epoch_s=time.time()) is None
    assert app.get_tracker_output() is original
    assert source.measurement == measurement
    assert source.provider.angle_sample_sequence == original.gimbal_observation.angle_receipt_sequence
    assert original.raw_data['measurement_target_ned'] == (20., 4., -17.)
    now[0] += .1
    progressed = source.observe(pose(now[0], (140, 150)), (20., -6., -25.), epoch_s=time.time())
    assert progressed.gimbal_observation.angle_receipt_sequence == 2
    assert progressed.raw_data['measurement_target_ned'] == (20., -6., -25.)


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('change,reason', [
    ({'source_boot_ms': (99, 120)}, 'backward'),
    ({'source_boot_ms': (100, 120), 'position_ned': (1., 0., -20.)}, 'rewritten'),
    ({'source_boot_ms': (120, 110), 'quaternion_wxyz': (0., 0., 0., 1.)}, 'rewritten'),
])
def test_component_rewrite_or_reorder_cannot_silently_revive(environment, mount, change, reason):
    build, now = environment
    _, source = build(mount)
    now[0] += .01
    source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time())
    now[0] += .1
    bad = {**pose(now[0]), **change}
    with pytest.raises((RuntimeError, ValueError), match=reason):
        source.observe(bad, (20., 4., -17.), epoch_s=time.time())
    assert source.runtime.angle_observation_context() is None
    with pytest.raises(ValueError, match='owner_invalid'):
        source.observe(pose(now[0], (140, 150)), (20., 4., -17.), epoch_s=time.time())


def test_stale_pose_and_duplicate_progress_cannot_refresh_measurement(environment):
    build, now = environment
    _, source = build('HORIZONTAL')
    now[0] += .01
    original = source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time())
    now[0] += .51
    with pytest.raises(RuntimeError, match='expired'):
        source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time())
    assert original.gimbal_observation.angle_receipt_sequence == 1


def test_provider_restart_changes_runtime_source_but_manual_stop_does_not(environment):
    build, now = environment
    app, source = build('HORIZONTAL')
    now[0] += .01
    source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time())
    app._freeze_following_observation_source()
    identity = source.runtime.angle_source_identity()
    source.runtime.acquire('sih_component', 'stop')
    assert source.runtime.angle_source_identity() == identity
    source.provider.stop_listening()
    assert source.runtime.angle_observation_context() is None
    assert source.runtime.angle_source_identity() != identity
    assert not app._guidance_source_readiness(app.get_tracker_output())['ready']


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_nonzero_physical_attitude_is_used_once_without_display_offset(environment, mount):
    from classes.aircraft_state import Vector3
    build, now = environment
    app, source = build(mount)
    app.camera_yaw_offset = 80.
    quaternion = Quaternion.from_euler(.2, -.3, 1.)
    now[0] += .01
    output = source.observe(pose(now[0], quaternion=(quaternion.w, quaternion.x, quaternion.y, quaternion.z)),
                            (20., 4., -17.), epoch_s=time.time())
    ray = quaternion.rotate(Vector3(*body_line_of_sight(output.angular, mount)))
    norm = (20. ** 2 + 4. ** 2 + 3. ** 2) ** .5
    assert (ray.x, ray.y, ray.z) == pytest.approx((20. / norm, 4. / norm, 3. / norm))


@pytest.mark.parametrize('required,family', [(('GIMBAL_ANGLES',), 'angles'), (('POSITION_2D',), 'image'),
                                          (('POSITION_3D',), None)])
def test_input_dispatch_comes_from_declaration_not_a_profile_id(monkeypatch, required, family):
    monkeypatch.setattr('tools.fixed_camera_world_target.get_follower_profile', lambda _: SimpleNamespace(
        implementation_available=True, phase_command_contracts={'multicopter': 'velocity_body_offboard'},
        required_tracker_data=required))
    assert mc_input_family('renamed_future_strategy') == family


@pytest.mark.parametrize('altitude', [False, True])
def test_bearing_response_uses_actual_motion_and_correct_altitude_contract(altitude):
    from tools.run_sih_follower_validation import scenario_path
    scenario = MCScenario.from_yaml(scenario_path('gm_velocity_chase', altitude))
    target = (20., 4., -23. if altitude else -20.)
    records = [dict(position_ned=(0., 0., -20.), target_ned=target, altitude_m=20., yaw_rad=0.),
               dict(position_ned=(.2, 0., -20.2 if altitude else -20.), target_ned=target,
                    altitude_m=20.2 if altitude else 20., yaw_rad=.1)]
    fields = dict(vel_body_fwd=.1, vel_body_right=0., vel_body_down=-.1 if altitude else 0., yawspeed_deg_s=5.)
    publications = [dict(monotonic_s=t, success=True, fields=fields) for t in (1., 1.05)]
    def evaluate(rows, published=publications):
        return evaluate_response(scenario, rows, published,
            velocity_limits=dict(forward=.5, lateral=.5, vertical=.5, max_magnitude=1.),
            rate_limits_deg_s=dict(yawspeed_deg_s=45.), attitude_limits_deg={})
    result = evaluate(records)
    assert result['passed']
    assert 'observed_image_response' not in result['checks']
    assert result['checks']['observed_bearing_response']
    if altitude:
        assert result['checks']['observed_vertical_response']
    else:
        assert result['checks']['altitude_off_zero_intent']
        assert 'observed_vertical_response' not in result['checks']
        bad = [dict(row, fields={**fields, 'vel_body_down': .1}) for row in publications]
        assert not evaluate(records, bad)['passed']
    frozen = [dict(records[0], target_ned=(20., 8., target[2])),
              dict(records[0], target_ned=(20., 0., target[2]))]
    assert not evaluate(frozen)['checks']['observed_bearing_response']


def test_gimbal_scenario_rejects_image_optics_and_unqualified_faults(tmp_path):
    from tools.run_sih_follower_validation import scenario_path
    from classes.sih_visualization import VisualizationValidationError
    raw = yaml.safe_load(scenario_path('gm_velocity_chase').read_text())
    path = tmp_path / 'scenario.yaml'
    path.write_text(yaml.safe_dump({**raw, 'fixed_camera': {}}))
    with pytest.raises(VisualizationValidationError, match='invent image optics'):
        MCScenario.from_yaml(path)
    raw['faults'] = [dict(kind='stale_telemetry', at_s=4., duration_s=2.)]
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(VisualizationValidationError, match='does not support stale_telemetry'):
        MCScenario.from_yaml(path)


def test_simulated_provider_and_tracker_do_not_open_any_socket(environment, monkeypatch):
    def forbidden(*_, **__):
        raise AssertionError('simulated boresight producer attempted network IO')
    monkeypatch.setattr('socket.socket', forbidden)
    build, now = environment
    _, source = build('HORIZONTAL')
    now[0] += .01
    assert source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time()).gimbal_observation is not None


@pytest.mark.parametrize('profile', ['gm_velocity_chase', 'gm_velocity_vector'])
@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_real_producer_is_confirmed_by_current_component_consumer_then_source_retirement_is_visible(environment, profile, mount):
    from classes.follower import Follower
    from classes.target_continuity import ContinuityPolicy, TargetContinuitySupervisor, TargetEvidenceState
    build, now = environment
    app, source = build(mount, profile)
    app.following_execution_mode = 'PX4'
    app.px4_interface = SimpleNamespace(current_altitude=20., current_yaw=0., current_pitch=0., current_roll=0.,
        is_command_preview=False, is_command_connection_ready=lambda **_: True,
        get_guidance_attitude=lambda: (Quaternion(1., 0., 0., 0.), 0.))
    app.follower = Follower(app.px4_interface, (0., 0.))
    app.target_continuity = TargetContinuitySupervisor(ContinuityPolicy.resolve(Parameters.TargetContinuity, profile))
    app.target_continuity.reset_session(session_epoch=7, reason='pure_component_source_test')
    try:
        now[0] += .01
        output = source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time())
        assert app._target_evidence_snapshot(output).state is TargetEvidenceState.CONFIRMED
        app._freeze_following_observation_source()
        app.following_active = True
        source.provider.stop_listening()
        evidence = app._target_evidence_snapshot(output)
        assert evidence.state is TargetEvidenceState.UNCERTAIN
        assert evidence.observation_source_changed
    finally:
        app.follower.follower.release_session_controls()


def component_follower(app, monkeypatch, profile):
    import asyncio
    from classes.follower import Follower
    from classes.target_continuity import AirframePhase, ContinuityContext, ContinuityPolicy, TargetContinuitySupervisor
    app.following_execution_mode = 'PX4'
    app.px4_interface = SimpleNamespace(current_altitude=20., current_yaw=0., current_pitch=0., current_roll=0.,
        is_command_preview=False, is_command_connection_ready=lambda **_: True,
        get_guidance_attitude=lambda: (Quaternion(1., 0., 0., 0.), 0.))
    app.follower = Follower(app.px4_interface, (0., 0.))
    app._follower_state_lock = asyncio.Lock()
    app._following_stopping = False
    app.target_continuity = TargetContinuitySupervisor(ContinuityPolicy.resolve(Parameters.TargetContinuity, profile), clock=time.monotonic)
    app.target_continuity.reset_session(session_epoch=7, reason='pure_component_fault_test')
    submitted = []
    def submit_intent(intent, **_):
        submitted.append(intent)
        return True

    app.offboard_commander = SimpleNamespace(submit_intent=submit_intent,
        get_status=lambda: {'failsafe_defaults_active': False})
    context = ContinuityContext(execution_mode='PX4', airframe_phase=AirframePhase.MULTICOPTER,
        control_type='velocity_body_offboard', vehicle_state_fresh=True, offboard_active=True,
        publisher_healthy=True, vehicle_yaw_deg=0.)
    monkeypatch.setattr(app, '_build_target_continuity_context', lambda: context)
    monkeypatch.setattr(app, '_ensure_continuity_watchdog', lambda: None)
    return submitted


@pytest.mark.asyncio
@pytest.mark.parametrize('profile', ['gm_velocity_chase', 'gm_velocity_vector'])
@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('altitude', [False, True])
async def test_received_loss_and_recovery_reuse_real_producer_and_supervisor(
        environment, monkeypatch, profile, mount, altitude):
    build, now = environment
    app, source = build(mount, profile, altitude)
    submitted = component_follower(app, monkeypatch, profile)
    try:
        now[0] += .01
        output = source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time())
        app._freeze_following_observation_source()
        app.following_active = True
        assert await app._dispatch_tracker_output_on_flight_loop(output)
        owner, session = source.runtime.angle_source_identity(), app._following_session_id
        states = []
        for index, (dt, lost) in enumerate(((.1, True), (.5, True), (.1, False), (.6, False), (.6, False)), 1):
            now[0] += dt
            output = source.observe(pose(now[0], (100 + 20*index, 110 + 20*index)),
                                    (20., 4., -17.), epoch_s=time.time(), lost=lost)
            assert output.image_measurement is output.position_2d is None
            assert output.gimbal_observation.tracking_state == ('TARGET_LOST' if lost else 'TRACKING_ACTIVE')
            assert await app._dispatch_tracker_output_on_flight_loop(output)
            status = app.get_target_continuity_status()
            states.append(status['authority_state'])
            if lost:
                assert status['episode_id'] == 1
                assert submitted[-1].fields['yawspeed_deg_s'] == 0.
                assert submitted[-1].fields['vel_body_down'] == 0.
        assert states == ['COASTING', 'COASTING', 'REACQUIRING', 'REACQUIRING', 'ACTIVE']
        assert app.following_active
        assert source.runtime.angle_source_identity() == owner
        assert app._following_session_id == session
        assert app._tracking_session_generation == 7
    finally:
        app.follower.follower.release_session_controls()


@pytest.mark.asyncio
@pytest.mark.parametrize('profile', ['gm_velocity_chase', 'gm_velocity_vector'])
@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('altitude', [False, True])
async def test_received_loss_expires_original_saved_budget_without_source_replacement(
        environment, monkeypatch, profile, mount, altitude):
    build, now = environment
    app, source = build(mount, profile, altitude)
    component_follower(app, monkeypatch, profile)
    try:
        now[0] += .01
        original = source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time())
        app._freeze_following_observation_source()
        app.following_active = True
        assert await app._dispatch_tracker_output_on_flight_loop(original)
        owner = source.runtime.angle_source_identity()
        now[0] += .1
        loss = source.observe(pose(now[0], (120, 130)), (20., 4., -17.), epoch_s=time.time(), lost=True)
        assert await app._dispatch_tracker_output_on_flight_loop(loss)
        episode = app.get_target_continuity_status()['episode_id']
        now[0] += app.target_continuity.policy.max_coast_time_s + .01
        loss = source.observe(pose(now[0], (140, 150)), (20., 4., -17.), epoch_s=time.time(), lost=True)
        decision = app.target_continuity.evaluate(app._target_evidence_snapshot(loss), app._build_target_continuity_context())
        assert decision.handoff_request.reason_code == 'maximum_coast_time_reached'
        assert decision.authorized_intent is None
        assert app.get_target_continuity_status()['episode_id'] == episode
        assert source.runtime.angle_source_identity() == owner
        assert app._tracking_session_generation == 7
    finally:
        app.follower.follower.release_session_controls()


@pytest.mark.asyncio
@pytest.mark.parametrize('profile', ['gm_velocity_chase', 'gm_velocity_vector'])
@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('altitude', [False, True])
async def test_simulated_retarget_requires_real_post_boundary_receipts_and_preserves_budget(
        environment, monkeypatch, profile, mount, altitude):
    from tools.mc_follower_sih import apply_simulated_retarget
    build, now = environment
    app, source = build(mount, profile, altitude)
    component_follower(app, monkeypatch, profile)
    try:
        now[0] += .01
        original = source.observe(pose(now[0]), (20., 4., -17.), epoch_s=time.time())
        app._freeze_following_observation_source()
        app.following_active = True
        assert await app._dispatch_tracker_output_on_flight_loop(original)
        owner, pin, session = source.runtime.angle_source_identity(), app._following_observation_source, app._following_session_id
        controls = app.follower.follower.session_controls()
        original_measurement = source.measurement
        now[0] += .05
        app._camera_selection_pending = True
        with pytest.raises(ValueError, match='selection_pending'):
            await apply_simulated_retarget(app, family='angles', coordinates=None, target_ned=(20., -3., -17.))
        assert app._tracking_session_generation == 7
        assert app._camera_selection_pending is True
        app._camera_selection_pending = False
        first = await apply_simulated_retarget(app, family='angles', coordinates=None, target_ned=(20., -3., -17.))
        assert first['selection_kind'] == 'simulated_target_generation'
        assert first['physical_selection_api_qualified'] is False
        assert app._tracking_session_generation == 8
        assert not app._camera_angle_sample_current(original, require_tracking=True)
        assert source.measurement == original_measurement
        assert source.observe(pose(now[0]), (20., -3., -17.), epoch_s=time.time()) is None
        assert app.get_tracker_output() is original
        assert source.provider.angle_sample_sequence == 1
        now[0] += .1
        output = source.observe(pose(now[0], (120, 130)), (20., -3., -17.), epoch_s=time.time())
        assert app._camera_angle_sample_current(output, require_tracking=True)
        assert await app._dispatch_tracker_output_on_flight_loop(output)
        pending = app.get_target_continuity_status()
        now[0] += .1
        second = await apply_simulated_retarget(app, family='angles', coordinates=None, target_ned=(20., -2., -17.))
        assert second['after']['episode_id'] == first['after']['episode_id'] == pending['episode_id']
        assert second['after']['loss_elapsed_s'] >= pending['loss_elapsed_s']
        assert second['after']['coast_distance_m'] >= pending['coast_distance_m']
        assert app._tracking_session_generation == 9
        assert not app._camera_angle_sample_current(output, require_tracking=True)
        for index, dt in enumerate((.1, .6, .6), 2):
            now[0] += dt
            output = source.observe(pose(now[0], (100 + 20*index, 110 + 20*index)),
                                    (20., -2., -17.), epoch_s=time.time())
            assert await app._dispatch_tracker_output_on_flight_loop(output)
        assert app.get_target_continuity_status()['authority_state'] == 'ACTIVE'
        assert source.runtime.angle_source_identity() == owner
        assert app._following_observation_source == pin and app._following_session_id == session
        assert app.follower.follower.session_controls() == controls
        original_prepare = app._prepare_following_target_transition
        # Start another real pending episode, then expose a deadline-only bug
        # whose public elapsed/distance/episode fields do not change.
        await apply_simulated_retarget(app, family='angles', coordinates=None, target_ned=(20., -1., -17.))
        def extend_deadline(reason):
            result = original_prepare(reason)
            app.target_continuity._loss_deadline += 1.
            return result
        monkeypatch.setattr(app, '_prepare_following_target_transition', extend_deadline)
        with pytest.raises(ValueError, match='renewed_recovery_budget'):
            await apply_simulated_retarget(app, family='angles', coordinates=None, target_ned=(20., 0., -17.))
        monkeypatch.setattr(app, '_prepare_following_target_transition', original_prepare)
        source.provider.stop_listening()
        with pytest.raises(ValueError, match='source_unavailable'):
            await apply_simulated_retarget(app, family='angles', coordinates=None, target_ned=(20., 1., -17.))
        assert app._tracking_session_generation == 11
    finally:
        app.follower.follower.release_session_controls()
