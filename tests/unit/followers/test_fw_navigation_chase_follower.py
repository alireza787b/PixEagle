"""Native image strategy contracts; simulated pixels are not SIH flight proof."""

from copy import deepcopy
from dataclasses import asdict, replace
import math
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml

from classes.aircraft_state import AircraftStateOwner, AirframePhase, AirspeedObservation, GuidanceSessionIdentity, Quaternion, Vector3
from classes.app_controller import AppController
from classes.bearing_geometry_policy import BearingGeometryPolicy
from classes.follower import FollowerFactory
from classes.followers.fw_navigation_chase_follower import FWNavigationChaseFollower
from classes.guidance_observation import PinholeCalibration, ImageFrameContext
from classes.following_observation_source import project_following_observation_source
from classes.native_guidance import NativeCapabilities
from classes.native_follow_binding import NativeFollowBinding
from classes.observation_alignment import AlignmentBinding
from classes.offboard_commander import OffboardCommander
from classes.parameters import Parameters
from classes.safety_manager import get_safety_manager
from classes.setpoint_handler import SetpointHandler, validate_follower_command_schema
from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.target_continuity import ContinuityContext, ContinuityPolicy, TargetContinuitySupervisor, TargetEvidenceState
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing
from tools.fixed_camera_world_target import FixedCamera
from tools.fixed_camera_bearing_fixture import FixedCameraBearingFixture


ROOT = Path(__file__).resolve().parents[3]
PROFILE = "fixture_native_fw"
RUNTIME = "native-fixture"
GEOMETRY = BearingGeometryPolicy(.2, .3, 100., 80.)


@pytest.fixture
def environment(monkeypatch):
    previous = Parameters.get_runtime_config_snapshot()
    defaults = yaml.safe_load((ROOT / "configs/config_default.yaml").read_text())
    Parameters.publish_config_mapping(defaults)
    canonical = SetpointHandler.load_and_validate_schema(ROOT / "configs/follower_commands.yaml")
    profile = deepcopy(canonical["follower_profiles"]["fw_attitude_rate"])
    profile.update(control_type="fixed_wing_external", required_fields=[],
                   native_phase_contracts={"fixed_wing": "fixed_wing_external"},
                   display_name="Fixture native image FW", live_qualified_phases=[],
                   session_controls={"requested_speed": {"label": "Airspeed", "unit": "m/s", "step": .5}})
    canonical["follower_profiles"][PROFILE] = profile
    canonical["ui_config"]["profile_display_order"].append(PROFILE)
    monkeypatch.setattr(SetpointHandler, "_schema_cache", validate_follower_command_schema(canonical))
    FollowerFactory._initialize_registry()
    monkeypatch.setattr(FollowerFactory, "_follower_registry",
                        {**FollowerFactory._follower_registry, PROFILE: FWNavigationChaseFollower})
    now = [100.]

    def build(*, altitude=False, initial=(0., 0.), state=None, prepare=True, settle=True,
              tailsitter_camera=False, profile_name=PROFILE):
        config = deepcopy(defaults)
        section = canonical['follower_profiles'][profile_name]['config_section']
        config["Follower"]["FollowerOverrides"].setdefault(section, {})["ENABLE_ALTITUDE_CONTROL"] = altitude
        Parameters.publish_config_mapping(config)
        controller = SimpleNamespace(is_command_preview=False)
        follower = FWNavigationChaseFollower(controller, initial, geometry_policy=GEOMETRY, profile_name=profile_name)
        state = state or aircraft_state(attitude_timing=attitude_timing())
        result = SimpleNamespace(follower=follower, controller=controller, state=state, session=None,
                                 now=now, output=None, fixture=None)
        follower.bind_guidance_input_resolver(lambda output, current: result.fixture.resolve(output, current))
        if prepare:
            identity = GuidanceSessionIdentity("follow-fixture", state.binding, 1)
            result.session = follower.create_airframe_session(
                identity, NativeCapabilities(RUNTIME, "fixture", 2, True, False, False),
                confirmation_s=.3, observation_timeout_s=.75, transition_timeout_s=10., clock=lambda: now[0],
            )
            if settle:
                result.session.observe(state, owner_confirmed=True, target_confirmed=True)
                advance(result, .31)
                assert result.session.observe(result.state, owner_confirmed=True, target_confirmed=True).pursuit_allowed
                follower.bind_airframe_session(result.session)
        target(result, (100., 20., -45.), tailsitter_camera=tailsitter_camera)
        return result

    try:
        yield build
    finally:
        Parameters.publish_config_mapping(previous)


def advance(env, elapsed=.05, **changes):
    env.now[0] += elapsed
    timing = replace(env.state.attitude_timing,
                     publication_timestamp_us=env.state.attitude_timing.publication_timestamp_us + 50_000,
                     sample_timestamp_us=env.state.attitude_timing.sample_timestamp_us + 50_000,
                     publication_received_at_monotonic_s=env.now[0],
                     sample_received_at_monotonic_s=env.now[0])
    env.state = replace(env.state, sequence=env.state.sequence + 1,
                        observed_at_monotonic_s=env.now[0], attitude_timing=timing, **changes)


def target(env, world, *, generation=3, tailsitter_camera=False):
    mount = dict(forward_body=[0., 0., -1.], right_body=[1., 0., 0.], down_body=[0., -1., 0.]) if tailsitter_camera else dict(
        forward_body=[1., 0., 0.], right_body=[0., 1., 0.], down_body=[0., 0., 1.])
    camera = FixedCamera.from_mapping({**mount, "offset_body_m": [0., 0., 0.],
                                       "horizontal_fov_deg": 90., "vertical_fov_deg": 90.})
    q = env.state.attitude_body_to_ned
    revision = "camera-minus-z" if tailsitter_camera else "camera-forward"
    calibration = PinholeCalibration("simulated-camera", revision, (1280, 960), (640., 480.), (639.5, 479.5),
                                     Quaternion(0., 1., 0., 0.) if tailsitter_camera else Quaternion(.5, .5, .5, .5), "none")
    binding = AlignmentBinding("simulated-camera", "source-epoch", "full-frame", revision,
                                generation, env.state.binding, RUNTIME, env.state.attitude_timing.quat_reset_counter)
    env.fixture = FixedCameraBearingFixture(camera=camera, calibration=calibration, binding=binding,
        fixture_revision="independent-camera-fixture-1", clock=lambda: env.now[0],
        max_image_age_s=.75, max_attitude_age_s=.75, allow_simulation=True)
    packet = {"fresh": True, "runtime_id": RUNTIME, "aircraft_state": asdict(env.state),
        "attitude_timing": asdict(env.state.attitude_timing), "vehicle_pose": {
            "source": "px4_dds_observed", "observed_at_monotonic_s": env.now[0],
            "vehicle_ned": [0., 0., -50.], "quaternion_wxyz": [q.w, q.x, q.y, q.z],
            "px4_timestamp_us": env.state.sequence*50_000}}
    env.output = env.fixture.project(packet, env.state, world, timestamp_s=1.)
    assert env.output.image_measurement is not None, "Fixture target must be within the measured camera view"
    return env.output


def test_registered_foundation_still_has_no_live_phase_permission():
    schema = SetpointHandler.load_and_validate_schema(ROOT / "configs/follower_commands.yaml")
    assert schema["follower_profiles"]["fw_navigation_chase"]["live_qualified_phases"] == []
    assert schema["follower_profiles"]["fw_navigation_chase"]["control_type"] == "fixed_wing_external"


def test_native_strategy_uses_one_real_handler_and_authoritative_safety(environment):
    env = environment()
    assert env.controller.setpoint_handler is env.follower.setpoint_handler
    assert env.follower.safety_manager is get_safety_manager()
    assert env.follower.setpoint_handler.fields == {}
    assert env.follower.enable_altitude_control is False
    assert env.follower.require_guidance_input(env.output, env.state) is None
    assert env.follower.setpoint_handler.get_last_command_intent() is None
    assert env.follower.follow_target(env.output)
    intent = env.follower.get_last_command_intent()
    assert intent is env.follower.setpoint_handler.get_last_command_intent()
    assert intent.control_type == "fixed_wing_external"
    assert intent.guidance_identity == env.session.identity
    assert set(intent.fields) == {"course_rad", "equivalent_airspeed_m_s", "altitude_amsl_m"}
    assert intent.fields["equivalent_airspeed_m_s"] == 20.
    assert intent.fields["equivalent_airspeed_m_s"] > env.follower.velocity_limits.max_magnitude


def test_readiness_requires_preparation_but_can_validate_before_mode_engagement(environment):
    env = environment(prepare=False)
    with pytest.raises(ValueError, match="native_guidance_session_unprepared"):
        env.follower.require_guidance_input(env.output, env.state)
    identity = GuidanceSessionIdentity("pending-follow", env.state.binding, 1)
    env.follower.create_airframe_session(identity, NativeCapabilities(RUNTIME, "fixture", 2, True, False, False),
        confirmation_s=.3, observation_timeout_s=.75, transition_timeout_s=10., clock=lambda: env.now[0])
    assert env.follower.require_guidance_input(env.output, env.state) is None
    assert env.follower.setpoint_handler.get_last_command_intent() is None
    assert not env.follower.follow_target(env.output)


@pytest.mark.parametrize("world", [(100., 20., -45.), (100., -20., -55.)])
def test_measured_image_supplies_correct_course_and_vertical_path(environment, world):
    env = environment(altitude=True)
    target(env, world)
    assert env.follower.follow_target(env.output)
    fields = env.follower.get_last_command_intent().fields
    assert fields["course_rad"] == pytest.approx(math.atan2(world[1], world[0]))
    assert fields["height_rate_m_s"] == pytest.approx(-20.*(world[2]+50.)/math.hypot(world[0], world[1]))
    assert fields["equivalent_airspeed_m_s"] == 20.


@pytest.mark.parametrize("angles,tailsitter", [((.3, -.2, .4), False), ((-.2, .15, -.3), False),
                                               ((.1, -math.pi/2+.01, .2), True)])
def test_full_raw_attitude_and_explicit_fixed_mount_match_independent_world_target(environment, angles, tailsitter):
    state = aircraft_state(attitude_body_to_ned=Quaternion.from_euler(*angles),
                           is_vtol=tailsitter, is_tailsitter=tailsitter, attitude_timing=attitude_timing())
    env = environment(altitude=True, state=state, tailsitter_camera=tailsitter)
    target(env, (100., 20., -45.), tailsitter_camera=tailsitter)
    assert env.follower.follow_target(env.output)
    fields = env.follower.get_last_command_intent().fields
    assert fields["course_rad"] == pytest.approx(math.atan2(20., 100.))
    assert fields["height_rate_m_s"] == pytest.approx(-100./math.hypot(100., 20.))


def test_altitude_disabled_keeps_engagement_height_for_targets_above_and_below(environment):
    env = environment()
    for world in ((100., 20., -60.), (100., 20., -40.)):
        advance(env)
        env.session.observe(env.state, owner_confirmed=True, target_confirmed=True)
        target(env, world)
        assert env.follower.follow_target(env.output)
        assert env.follower.get_last_command_intent().fields["altitude_amsl_m"] == 550.
        assert "height_rate_m_s" not in env.follower.get_last_command_intent().fields


def test_initial_pid_aim_coordinates_do_not_replace_the_actual_image_bearing(environment):
    env = environment(initial=(.8, -.7))
    assert env.follower.follow_target(env.output)
    assert env.follower.get_last_command_intent().fields["course_rad"] == pytest.approx(math.atan2(20., 100.))


def test_duplicate_measurement_readiness_and_processing_cannot_renew_intent(environment):
    env = environment()
    assert env.follower.follow_target(env.output)
    original = env.follower.get_last_command_intent()
    env.now[0] += .1
    assert env.follower.require_guidance_input(env.output, env.state) is None
    assert env.follower.follow_target(env.output)
    repeated = env.follower.get_last_command_intent()
    assert repeated.created_at_monotonic_s == original.created_at_monotonic_s
    assert repeated.fields == original.fields
    assert env.output.image_measurement.provenance.capture.captured_at == original.created_at_monotonic_s


def test_new_authoritative_state_recalculates_a_retained_world_bearing_without_restamping_image(environment):
    env = environment(altitude=True)
    assert env.follower.follow_target(env.output)
    original = env.follower.get_last_command_intent()
    measurement, alignment = env.output.image_measurement, env.fixture.last_alignment
    advance(env, .35, velocity_ned_m_s=Vector3(10., 0., 0.),
            attitude_body_to_ned=Quaternion.from_euler(.1, -.2, .3), navigation_heading_rad=.3,
            fixed_wing_envelope=replace(env.state.fixed_wing_envelope, maximum_eas_m_s=16., trim_eas_m_s=14.))
    assert env.session.observe(env.state, owner_confirmed=True, target_confirmed=True).pursuit_allowed
    assert env.follower.follow_target(env.output)
    updated = env.follower.get_last_command_intent()
    assert updated.created_at_monotonic_s == env.now[0] > original.created_at_monotonic_s
    assert updated.fields['course_rad'] == original.fields['course_rad']
    assert updated.fields['equivalent_airspeed_m_s'] == 16.
    assert updated.fields['height_rate_m_s'] == pytest.approx(original.fields['height_rate_m_s']/2)
    assert env.output.image_measurement is measurement and env.fixture.last_alignment is alignment


def test_accepted_aggregate_source_progress_does_not_require_restamping_its_oldest_measurement(environment):
    env = environment()
    assert env.follower.follow_target(env.output)
    original_state = env.state
    env.now[0] += .1
    env.state = replace(env.state, sequence=env.state.sequence+1)
    env.session.observe(env.state, owner_confirmed=True, target_confirmed=True)
    assert env.follower.follow_target(env.output)
    assert env.follower.get_last_command_intent().created_at_monotonic_s == env.now[0]
    assert env.state.observed_at_monotonic_s == original_state.observed_at_monotonic_s
    assert env.output.image_measurement.provenance.capture.captured_at == original_state.observed_at_monotonic_s


@pytest.mark.parametrize('change', ['receipt_only', 'source', 'sequence_backwards'])
def test_changed_receipt_or_rewritten_state_cannot_become_controller_progress(environment, change):
    env = environment()
    assert env.follower.follow_target(env.output)
    original = env.follower.get_last_command_intent()
    env.now[0] += .1
    changed = {'observed_at_monotonic_s': env.now[0]}
    if change == 'source':
        changed.update(sequence=env.state.sequence+1, source='superseded_source')
    elif change == 'sequence_backwards':
        changed.update(sequence=env.state.sequence-1)
    env.session._state = replace(env.state, **changed)
    assert not env.follower.follow_target(env.output)
    assert env.follower.get_last_command_intent() is None
    assert env.follower._last_guidance_intent == original


def publication_environment(env, monkeypatch):
    """Compose real ownership/continuity/publication classes with an in-memory adapter."""
    monkeypatch.setattr('classes.offboard_commander.time', SimpleNamespace(monotonic=lambda: env.now[0]))
    states = AircraftStateOwner(clock=lambda: env.now[0])
    states.bind(env.state.binding)
    assert states.commit(env.state)
    connection = SimpleNamespace(get_aircraft_state=lambda: states.snapshot(timeout_s=.75),
                                 commit_aircraft_state=states.commit)
    client = SimpleNamespace(session_identity=env.session.identity, submit=AsyncMock(), abort=Mock(),
                             handoff=AsyncMock(return_value={'hold_observed': True}))
    client.observe = AsyncMock(side_effect=lambda: {
        'aircraft_state': asdict(connection.get_aircraft_state()), 'fresh': True,
        'owner_confirmed': True, 'rescue_active': False,
    })
    continuity = TargetContinuitySupervisor(ContinuityPolicy.resolve(
        Parameters.TargetContinuity, env.follower.profile_name, AirframePhase.FIXED_WING), clock=lambda: env.now[0])
    continuity.reset_session(session_epoch=0, reason='component_test')
    app = object.__new__(AppController)
    app.follower = SimpleNamespace(follower=env.follower)
    app.px4_interface, app.target_continuity = connection, continuity
    app.get_tracker_output = lambda: env.output
    measured = env.output.image_measurement
    app.tracking_input_context = ImageFrameContext(measured.provenance, measured.image_size_px, measured.image_to_calibration)
    app.frame_publisher = SimpleNamespace(stream_id=measured.provenance.source_id,
        control_source_epoch=measured.provenance.capture.source_epoch)
    app._following_observation_source = project_following_observation_source(measured)
    app._following_session_id = env.session.identity.follow_session_id
    base = ContinuityContext('PX4_NATIVE', AirframePhase.FIXED_WING, 'fixed_wing_external',
                             True, True, True, guidance_identity=env.session.identity)
    binding = NativeFollowBinding(env.session, connection, client, continuity, profile_name=env.follower.profile_name,
        continuity_config=Parameters.TargetContinuity, target_evidence=lambda: app._target_evidence_snapshot(env.output),
        context=lambda: base, circuit_breaker=lambda: False, clock=lambda: env.now[0])
    commander = OffboardCommander(connection, env.follower.setpoint_handler,
                                  command_transport=binding.transport, command_ttl_s=.3)

    async def dispatch():
        evidence = app._target_evidence_snapshot(env.output)
        nominal = None
        if evidence.state is TargetEvidenceState.CONFIRMED:
            assert env.follower.follow_target(env.output)
            nominal = env.follower.get_last_command_intent()
        decision = continuity.evaluate(evidence, binding.context(base), nominal)
        assert decision.handoff_request is None
        intent = replace(decision.authorized_intent, fields=env.follower.prepare_authorized_command(
            decision.authorized_intent.fields, loss_decay=False))
        assert commander.submit_intent(intent)
        continuity.record_authorized_intent(intent)
        assert await commander.publish_once()
        return evidence, intent

    return SimpleNamespace(commander=commander, continuity=continuity, client=client,
                           states=states, dispatch=dispatch)


@pytest.mark.asyncio
async def test_progressing_state_keeps_publication_until_original_image_expiry_then_shared_recovery(environment, monkeypatch):
    env = environment(altitude=True, profile_name='fw_navigation_chase')
    run = publication_environment(env, monkeypatch)
    measured = env.output.image_measurement
    _, original = await run.dispatch()
    for elapsed in (.35, .2):
        advance(env, elapsed)
        assert run.states.commit(env.state)
        assert env.session.observe(env.state, owner_confirmed=True, target_confirmed=True).pursuit_allowed
        evidence, intent = await run.dispatch()
        assert evidence.state is TargetEvidenceState.CONFIRMED
        assert intent.created_at_monotonic_s == env.now[0] > original.created_at_monotonic_s
        assert env.output.image_measurement is measured
        run.client.handoff.assert_not_awaited()
    advance(env, .25)
    assert run.states.commit(env.state)
    env.session.observe(env.state, owner_confirmed=True, target_confirmed=True)
    evidence, recovery = await run.dispatch()
    assert evidence.state is TargetEvidenceState.UNCERTAIN
    assert recovery.reason == 'bounded_fixed_wing_recovery'
    assert recovery.fields['height_rate_m_s'] == 0.
    assert recovery.created_at_monotonic_s == env.now[0]
    assert run.continuity.get_status()['authority_state'] == 'COASTING'
    assert run.commander.stale_intent_resets == 0
    run.client.handoff.assert_not_awaited()
    deadline = run.continuity._loss_deadline
    advance(env, .2)
    assert run.states.commit(env.state)
    env.session.observe(env.state, owner_confirmed=True, target_confirmed=True)
    await run.dispatch()
    assert run.continuity._loss_deadline == deadline
    assert env.output.image_measurement is measured


@pytest.mark.asyncio
async def test_frozen_aircraft_state_and_duplicate_image_cannot_renew_publisher_ttl(environment, monkeypatch):
    env = environment(profile_name='fw_navigation_chase')
    run = publication_environment(env, monkeypatch)
    _, original = await run.dispatch()
    env.now[0] += .35
    evidence, duplicate = await run.dispatch()
    assert evidence.state is TargetEvidenceState.CONFIRMED
    assert duplicate.created_at_monotonic_s == original.created_at_monotonic_s
    assert run.client.submit.await_count == 1
    run.client.handoff.assert_awaited_once_with(env.session.identity, reason='manual', before_dispatch=None)
    assert run.commander.stale_intent_resets == 1


def test_stale_or_missing_input_invalidates_intent_without_inventing_a_command(environment):
    env = environment()
    assert env.follower.follow_target(env.output)
    old = env.follower.get_last_command_intent()
    for _ in range(2):
        advance(env, .4)
        assert env.session.observe(env.state, owner_confirmed=True, target_confirmed=True).pursuit_allowed
    assert not env.follower.follow_target(env.output)
    assert env.follower.get_last_command_intent() is None
    assert env.follower.setpoint_handler.get_last_command_intent() is None
    assert env.follower.setpoint_handler.fields == old.fields
    assert not hasattr(env.follower, "_geometry_invalid")
    assert not hasattr(env.follower, "_safety_rejection")


def test_stale_cached_resolver_result_cannot_bypass_freshness(environment):
    env = environment()
    aligned = env.fixture.resolve(env.output, env.state)
    env.follower._input_resolver = lambda *_: aligned
    assert env.follower.follow_target(env.output)
    for _ in range(2):
        advance(env, .4)
        env.session.observe(env.state, owner_confirmed=True, target_confirmed=True)
    assert not env.follower.follow_target(env.output)
    assert env.follower.get_last_command_intent() is None
    assert env.follower._telemetry_metadata["guidance_input_reason"] == "guidance_input_stale"


def test_legitimate_speed_edit_recalculates_without_renewing_the_image_measurement(environment):
    env = environment()
    assert env.follower.follow_target(env.output)
    before = env.follower.get_last_command_intent()
    stamp = env.output.image_measurement.provenance.capture
    env.now[0] += .1
    env.follower.update_session_control("requested_speed", 22., env.follower.session_controls()[0]["revision"])
    assert env.follower.follow_target(env.output)
    updated = env.follower.get_last_command_intent()
    assert updated.fields["equivalent_airspeed_m_s"] == 22.
    assert updated.created_at_monotonic_s > before.created_at_monotonic_s
    assert env.output.image_measurement.provenance.capture is stamp


def test_rewritten_same_capture_is_not_treated_as_a_new_measurement(environment):
    env = environment()
    assert env.follower.follow_target(env.output)
    previous = env.fixture.last_alignment
    ray = Vector3(1., -.2, .1).normalized()
    rewritten = replace(previous, bearing=replace(previous.bearing, direction_body_frd=ray),
                         direction_ned=previous.attitude_state.attitude_body_to_ned.rotate(ray))
    output = replace(env.output, image_measurement=replace(env.output.image_measurement,
                      pixel_xy=(env.output.image_measurement.pixel_xy[0]-10., env.output.image_measurement.pixel_xy[1])))
    env.follower._input_resolver = lambda *_: rewritten
    assert not env.follower.follow_target(output)
    assert env.follower.get_last_command_intent() is None
    assert env.follower._telemetry_metadata["guidance_input_reason"] == "guidance_capture_rewritten"


@pytest.mark.parametrize("raw", [{"usable_for_following": False}, {"prediction_only": True}, {"data_is_stale": True}])
def test_canonical_tracker_freshness_still_precedes_calibrated_guidance(environment, raw):
    env = environment()
    aligned = env.fixture.resolve(env.output, env.state)
    env.follower._input_resolver = lambda *_: aligned
    output = replace(env.output, raw_data={**env.output.raw_data, **raw})
    assert not env.follower.follow_target(output)
    assert env.follower.get_last_command_intent() is None


@pytest.mark.parametrize("bad", ["missing_image", "lost", "angles"])
def test_nonmeasured_and_incompatible_inputs_cannot_become_native_objectives(environment, bad):
    env = environment()
    output = env.output
    if bad == "missing_image":
        output = replace(output, image_measurement=None)
    elif bad == "lost":
        output = replace(output, tracking_active=False)
    else:
        output = TrackerOutput(TrackerDataType.GIMBAL_ANGLES, 1., True, angular=(0., 0., 0.),
                               image_measurement=output.image_measurement)
    assert not env.follower.follow_target(output)
    assert env.follower.get_last_command_intent() is None


@pytest.mark.parametrize("bad", ["missing", "untyped", "wrong_image", "wrong_runtime"])
def test_resolver_must_supply_this_exact_image_aircraft_and_runtime(environment, bad):
    env = environment()
    aligned = env.fixture.resolve(env.output, env.state)
    if bad == "missing":
        env.follower._input_resolver = None
    elif bad == "untyped":
        env.follower._input_resolver = lambda *_: {}
    elif bad == "wrong_image":
        previous = env.output
        advance(env)
        target(env, (100., 20., -45.))
        assert env.output.image_measurement.provenance != previous.image_measurement.provenance
        env.follower._input_resolver = lambda *_: aligned
    else:
        wrong = replace(aligned, binding=replace(aligned.binding, native_runtime_id="another-runtime"))
        env.follower._input_resolver = lambda *_: wrong
    assert not env.follower.follow_target(env.output)
    assert env.follower.get_last_command_intent() is None


@pytest.mark.parametrize("phase", [AirframePhase.MULTICOPTER, AirframePhase.VTOL_TRANSITION])
def test_leaving_fw_ends_session_and_cannot_generate_or_edit(environment, phase):
    state = aircraft_state(is_vtol=True, is_tailsitter=True, attitude_timing=attitude_timing())
    env = environment(state=state)
    advance(env, phase=phase)
    result = env.session.observe(env.state, owner_confirmed=True, target_confirmed=True)
    assert not result.pursuit_allowed
    assert not env.follower.follow_target(env.output)
    control = env.follower.session_controls()
    assert control == []
    with pytest.raises(ValueError):
        env.follower.update_session_control("requested_speed", 18., 1)


def test_speed_control_uses_native_eas_envelope_and_retained_commands_respect_reduction(environment):
    env = environment()
    control = env.follower.session_controls()[0]
    assert (control["value"], control["minimum"], control["maximum"], control["step"]) == (20., 12., 30., .5)
    assert control["speed_basis"] == "equivalent_airspeed"
    assert env.follower.follow_target(env.output)
    retained = env.follower.get_last_command_intent().fields
    env.follower.update_session_control("requested_speed", 16., control["revision"])
    fields = env.follower.prepare_authorized_command(retained, loss_decay=True)
    assert fields["equivalent_airspeed_m_s"] == 16.
    assert set(fields) == set(retained)
    assert not any(name.startswith("vel_body") or "yawspeed" in name for name in fields)
    with pytest.raises(ValueError, match="out_of_range"):
        env.follower.update_session_control("requested_speed", 0., env.follower.session_controls()[0]["revision"])
    with pytest.raises(ValueError, match="revision_stale"):
        env.follower.update_session_control("requested_speed", 18., control["revision"])
    with pytest.raises(ValueError, match="native_fixed_wing_fields_invalid"):
        env.follower.prepare_authorized_command({**retained, "vel_body_down": 0.}, loss_decay=False)


def test_sensorless_uses_native_trim_and_valid_low_airspeed_keeps_native_minimum(environment):
    env = environment(state=aircraft_state(airspeed=AirspeedObservation("unavailable", None, None, 100., False),
                                         attitude_timing=attitude_timing()))
    assert env.follower.session_controls()[0]["value"] == 18.
    env = environment(state=aircraft_state(airspeed=AirspeedObservation("sensor", 8., 9., 100., True),
                                         attitude_timing=attitude_timing()))
    assert env.follower.session_controls()[0]["value"] == 12.


def test_retarget_clears_target_memory_without_replacing_owner_speed_or_altitude_reference(environment):
    env = environment()
    assert env.follower.follow_target(env.output)
    identity = env.session.identity
    control = env.follower.session_controls()[0]
    env.session.fixed_wing._vertical = True
    env.session.fixed_wing._rearward_turn_sign = -1.
    assert env.follower.prepare_for_target_transition("accepted_retarget")
    assert env.follower.get_last_command_intent() is None
    assert env.follower.setpoint_handler.fields == {}
    assert env.session.identity == identity
    assert env.follower.session_controls()[0] == control
    advance(env)
    env.session.observe(env.state, owner_confirmed=True, target_confirmed=True)
    target(env, (100., -20., -45.), generation=4)
    assert env.follower.follow_target(env.output)
    assert env.follower.get_last_command_intent().fields["course_rad"] < 0.
    assert env.follower.get_last_command_intent().fields["altitude_amsl_m"] == 550.


def test_stop_is_terminal_for_old_callbacks_controls_and_session_binding(environment):
    env = environment()
    assert env.follower.follow_target(env.output)
    old_session = env.session
    env.follower.release_session_controls()
    assert not env.follower.follow_target(env.output)
    assert env.follower.session_controls() == []
    assert env.follower.get_last_command_intent() is None
    assert env.follower.setpoint_handler.get_last_command_intent() is None
    with pytest.raises(ValueError, match="binding_invalid"):
        env.follower.bind_airframe_session(old_session)
    with pytest.raises(ValueError, match="follow_session_ended"):
        env.follower.update_session_control("requested_speed", 18., 1)
    with pytest.raises(ValueError, match="already_bound"):
        env.follower.bind_guidance_input_resolver(lambda *_: None)


def test_pilot_takeover_invalidates_old_inputs_and_intent_without_requesting_another_mode(environment):
    env = environment()
    assert env.follower.follow_target(env.output)
    assert not env.session.observe(env.state, owner_confirmed=False, target_confirmed=True).pursuit_allowed
    assert not env.follower.follow_target(env.output)
    assert env.follower.get_last_command_intent() is None
    with pytest.raises(ValueError, match="guidance_session_ended"):
        env.follower.require_guidance_input(env.output, env.state)
    assert vars(env.controller).keys() == {"is_command_preview", "setpoint_handler"}


def test_async_resolver_cannot_leak_pending_work_into_the_sync_guidance_path(environment):
    env = environment()

    async def resolve_later():
        return env.fixture.resolve(env.output, env.state)

    pending = resolve_later()
    env.follower._input_resolver = lambda *_: pending
    assert not env.follower.follow_target(env.output)
    assert inspect.getcoroutinestate(pending) == "CORO_CLOSED"
    assert env.follower.get_last_command_intent() is None


def test_unexpected_resolver_failure_is_visible_and_cannot_leave_an_old_intent(environment, caplog):
    env = environment()
    assert env.follower.follow_target(env.output)

    def failed_resolver(*args):
        raise RuntimeError("fixture processing failure")

    env.follower._input_resolver = failed_resolver
    assert not env.follower.follow_target(env.output)
    assert env.follower.get_last_command_intent() is None
    assert env.follower.setpoint_handler.get_last_command_intent() is None
    assert env.follower._telemetry_metadata["guidance_input_reason"] == "guidance_calculation_failed"
    assert "Native image guidance calculation failed" in caplog.text
