"""Shared production strategy with independent world-target mount fixtures."""

from dataclasses import replace
import math
from unittest.mock import Mock

import pytest

from classes.aircraft_state import AirframePhase, GuidanceSessionIdentity, Quaternion, Vector3
from classes.command_intent import CommandIntent
from classes.follower_session_controls import SessionControl
from classes.gimbal_geometry import body_line_of_sight
from classes.gimbal_guidance import GimbalGuidanceCapabilities, GimbalGuidancePolicy
from classes.vector_guidance_session import VectorGuidanceSession
from classes.airframe_session_controls import AirframeSessionControls
from classes.native_guidance import NativeCapabilities
from classes.safety_types import AltitudeLimits
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target


CAPABILITIES = GimbalGuidanceCapabilities(known=True, supports_vertical=True, supports_reverse=True,
                                        supports_yaw_fallback=True)


def session(*, altitude=True, state=None):
    state = state or aircraft_state(is_vtol=True, is_tailsitter=True)
    now = [100.]
    identity = GuidanceSessionIdentity("follow", state.binding, 1)
    owner = VectorGuidanceSession(
        identity,
        NativeCapabilities("native", "test", 2, True, True, False),
        profile_name="gm_velocity_vector",
        controls=AirframeSessionControls.from_multicopter_control(identity,
            SessionControl("requested_speed", "3D speed", "m/s", 0., None, .5, 0., configured_maximum=6.)),
        supported_phases=frozenset({AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING, AirframePhase.VTOL_TRANSITION}),
        geometry_policy=GimbalGuidancePolicy(),
        altitude_control=altitude, altitude_limits=AltitudeLimits(5., 120., 2.), confirmation_s=.3,
        observation_timeout_s=.75, transition_timeout_s=10., clock=lambda: now[0],
    )
    return owner, now, state


def observe(owner, now, state, *, phase=None, target=True, authority=True):
    state = replace(state, sequence=state.sequence + 1, observed_at_monotonic_s=now[0],
                    phase=state.phase if phase is None else phase)
    return owner.observe(state, owner_confirmed=authority, target_confirmed=target), state


def settle(owner, now, state):
    _, state = observe(owner, now, state)
    now[0] += .31
    result, state = observe(owner, now, state)
    assert result.pursuit_allowed
    return state


def fixed_wing_session(*, altitude=True):
    state = aircraft_state(phase=AirframePhase.FIXED_WING)
    identity = GuidanceSessionIdentity('fw_fixture', state.binding, 1)
    now = [100.]
    owner = VectorGuidanceSession(
        identity, NativeCapabilities('native', 'test', 2, True, True, False),
        profile_name='fw_navigation_fixture', controls=AirframeSessionControls.for_fixed_wing(identity, step_m_s=.5),
        supported_phases=frozenset({AirframePhase.FIXED_WING}), geometry_policy=GimbalGuidancePolicy(),
        altitude_control=altitude, altitude_limits=AltitudeLimits(5., 120., 2.), confirmation_s=.3,
        observation_timeout_s=.75, transition_timeout_s=10., clock=lambda: now[0],
    )
    return owner, now, state


@pytest.mark.parametrize('altitude', [False, True])
def test_fw_only_session_uses_native_startup_and_shared_world_ray_objective(altitude):
    owner, now, state = fixed_wing_session(altitude=altitude)
    assert owner.controls.current_control is None
    _, state = observe(owner, now, state)
    baseline = owner.baseline()
    assert baseline.fields['equivalent_airspeed_m_s'] == 20.
    assert not any(field.startswith('vel_body_') for field in baseline.fields)
    now[0] += .31
    decision, state = observe(owner, now, state)
    assert decision.pursuit_allowed
    command = owner.calculate_ned(Vector3(1., .3, .1).normalized(), frame='ned')
    assert command.guidance_identity == owner.identity
    assert command.control_type == 'fixed_wing_external'
    assert command.fields['course_rad'] == pytest.approx(math.atan2(.3, 1.))
    assert command.fields['equivalent_airspeed_m_s'] == 20.
    if altitude:
        assert command.fields['height_rate_m_s'] < 0.
        assert 'altitude_amsl_m' not in command.fields
    else:
        assert command.fields['altitude_amsl_m'] == state.altitude_amsl_m
        assert 'height_rate_m_s' not in command.fields


@pytest.mark.parametrize('phase,reason', [
    (AirframePhase.MULTICOPTER, 'phase_changed_without_observed_transition'),
    (AirframePhase.VTOL_TRANSITION, 'unsupported_aircraft_phase'),
])
def test_fw_only_session_ends_when_phase_changes_and_never_resumes(phase, reason):
    owner, now, state = fixed_wing_session()
    state = settle(owner, now, state)
    now[0] += .1
    state = replace(state, is_vtol=True)
    decision, state = observe(owner, now, state, phase=phase)
    assert not decision.pursuit_allowed
    assert decision.reason == reason
    assert not decision.transition_setpoints_required
    assert owner.controls.snapshot(client_contract_version=2) is None
    now[0] += .1
    decision, state = observe(owner, now, state, phase=AirframePhase.FIXED_WING)
    assert decision.reason == reason
    with pytest.raises(ValueError, match='guidance_session_ended'):
        owner.calculate_ned(Vector3(1., 0., 0.), frame='ned')


def test_fw_session_ned_entry_cannot_double_rotate_or_accept_another_frame(monkeypatch):
    owner, now, state = fixed_wing_session()
    settle(owner, now, state)
    monkeypatch.setattr(Quaternion, 'rotate', Mock(side_effect=AssertionError('world ray rotated again')))
    assert owner.calculate_ned(Vector3(1., 0., 0.), frame='ned').fields['course_rad'] == 0.
    with pytest.raises(ValueError, match='guidance_ray_frame_invalid'):
        owner.calculate_ned(Vector3(1., 0., 0.), frame='physical_body_frd')


@pytest.mark.parametrize('phases', [set(), [], frozenset(), frozenset({AirframePhase.UNKNOWN}), frozenset({'fixed_wing'})])
def test_supported_phase_declaration_is_explicit_and_typed(phases):
    owner, now, state = fixed_wing_session()
    with pytest.raises(ValueError, match='session_supported_phases_invalid'):
        VectorGuidanceSession(
            owner.identity, owner.phase_owner.capabilities, profile_name='fw_fixture', controls=owner.controls,
            supported_phases=phases, geometry_policy=GimbalGuidancePolicy(), altitude_control=True,
            altitude_limits=owner.altitude_limits, confirmation_s=.3, observation_timeout_s=.75, transition_timeout_s=10.,
        )


def test_controls_from_another_session_cannot_be_adopted():
    owner, now, state = fixed_wing_session()
    foreign = AirframeSessionControls.for_fixed_wing(replace(owner.identity, follow_session_id='other'), step_m_s=.5)
    with pytest.raises(ValueError, match='session_controls_binding_invalid'):
        VectorGuidanceSession(
            owner.identity, owner.phase_owner.capabilities, profile_name='fw_fixture', controls=foreign,
            supported_phases=frozenset({AirframePhase.FIXED_WING}), geometry_policy=GimbalGuidancePolicy(),
            altitude_control=True, altitude_limits=owner.altitude_limits, confirmation_s=.3,
            observation_timeout_s=.75, transition_timeout_s=10.,
        )


@pytest.mark.parametrize("altitude", [True, False])
def test_fw_uses_native_contract_and_never_calls_multicopter_math(altitude):
    owner, now, state = session(altitude=altitude)
    settle(owner, now, state)
    callback = Mock(side_effect=AssertionError("MC calculation called in FW"))
    intent = owner.calculate(Vector3(1., 0., .2), capabilities=CAPABILITIES, multicopter_calculate=callback)
    assert intent.control_type == "fixed_wing_external"
    assert intent.guidance_identity == owner.identity
    assert intent.fields["equivalent_airspeed_m_s"] == 20.
    assert intent.created_at_monotonic_s == now[0]
    if altitude:
        assert intent.fields["height_rate_m_s"] < 0
    else:
        assert intent.fields["altitude_amsl_m"] == 550.
    callback.assert_not_called()


def test_confirming_and_transition_use_phase_safe_contracts_without_pursuit():
    owner, now, state = session(state=aircraft_state(phase=AirframePhase.MULTICOPTER,
                                                   is_vtol=True, is_tailsitter=True))
    _, state = observe(owner, now, state)
    callback = Mock(side_effect=AssertionError("pursuit called before confirmation"))
    baseline = owner.calculate(Vector3(1., 0., 0.), capabilities=CAPABILITIES, multicopter_calculate=callback)
    assert set(baseline.fields.values()) == {0.}
    mc_generation = owner.identity.guidance_generation
    now[0] += .1
    result, state = observe(owner, now, state, phase=AirframePhase.VTOL_TRANSITION)
    assert result.transition_setpoints_required
    intent = owner.calculate(Vector3(-1., 0., 0.), capabilities=CAPABILITIES, multicopter_calculate=callback)
    assert intent.control_type == "vtol_transition_external"
    assert intent.fields["equivalent_airspeed_m_s"] == 18.
    assert intent.guidance_identity.guidance_generation > mc_generation
    assert owner.controls.snapshot(client_contract_version=2) is None
    callback.assert_not_called()


def test_transition_course_is_latched_across_tailsitter_yaw_wrapping_and_phase_flaps():
    owner, now, state = session(state=aircraft_state(phase=AirframePhase.MULTICOPTER,
                                                   is_vtol=True, is_tailsitter=True,
                                                   navigation_heading_rad=.7))
    state = settle(owner, now, state)
    for phase, heading in ((AirframePhase.VTOL_TRANSITION, 3.13),
                            (AirframePhase.VTOL_TRANSITION, -3.13),
                            (AirframePhase.FIXED_WING, 1.2),
                            (AirframePhase.VTOL_TRANSITION, -2.)):
        now[0] += .1
        state = replace(state, navigation_heading_rad=heading)
        _, state = observe(owner, now, state, phase=phase)
        if phase is AirframePhase.VTOL_TRANSITION:
            assert owner.baseline().fields["course_rad"] == .7
            assert owner.baseline().fields["equivalent_airspeed_m_s"] == 18.


def test_transition_retains_fw_request_with_current_native_bounds_and_no_deadline_reset():
    owner, now, state = session()
    state = settle(owner, now, state)
    control = owner.controls.current_control
    owner.controls.update(25., identity=owner.identity, expected_revision=control.revision)
    command = owner.calculate(Vector3(1., 1., 0.), capabilities=CAPABILITIES, multicopter_calculate=Mock())
    course = command.fields["course_rad"]
    now[0] += .1
    _, state = observe(owner, now, state, phase=AirframePhase.VTOL_TRANSITION)
    assert owner.baseline().fields == {"course_rad": course, "equivalent_airspeed_m_s": 25.}
    now[0] += .1
    state = replace(state, navigation_heading_rad=-2.,
                    fixed_wing_envelope=replace(state.fixed_wing_envelope, maximum_eas_m_s=22.))
    _, state = observe(owner, now, state)
    assert owner.baseline().fields == {"course_rad": course, "equivalent_airspeed_m_s": 22.}


def test_return_to_mc_discards_old_fw_course_before_a_later_front_transition():
    owner, now, state = session()
    state = settle(owner, now, state)
    old = owner.calculate(Vector3(1., 1., 0.), capabilities=CAPABILITIES, multicopter_calculate=Mock())
    for phase in (AirframePhase.VTOL_TRANSITION, AirframePhase.MULTICOPTER):
        now[0] += .1
        _, state = observe(owner, now, state, phase=phase)
    now[0] += .31
    state = replace(state, navigation_heading_rad=-1.)
    _, state = observe(owner, now, state)
    now[0] += .1
    state = replace(state, navigation_heading_rad=2.)
    _, state = observe(owner, now, state, phase=AirframePhase.VTOL_TRANSITION)
    assert owner.baseline().fields["course_rad"] == -1.
    assert owner.baseline().fields["course_rad"] != old.fields["course_rad"]


def test_phase_changes_preserve_separate_speed_requests_and_reject_old_editors():
    owner, now, state = session(state=aircraft_state(phase=AirframePhase.MULTICOPTER,
                                                   is_vtol=True, is_tailsitter=True))
    state = settle(owner, now, state)
    mc_identity = owner.identity
    control = owner.controls.current_control
    owner.controls.update(3., identity=mc_identity, expected_revision=control.revision)
    now[0] += .1
    _, state = observe(owner, now, state, phase=AirframePhase.VTOL_TRANSITION)
    now[0] += .1
    _, state = observe(owner, now, state, phase=AirframePhase.FIXED_WING)
    now[0] += .31
    _, state = observe(owner, now, state)
    assert owner.controls.current_control.value == 20.
    with pytest.raises(ValueError, match="identity_stale"):
        owner.controls.update(4., identity=mc_identity, expected_revision=owner.controls.current_control.revision)
    for phase in (AirframePhase.VTOL_TRANSITION, AirframePhase.MULTICOPTER):
        now[0] += .1
        _, state = observe(owner, now, state, phase=phase)
    now[0] += .31
    result, state = observe(owner, now, state)
    assert result.pursuit_allowed
    assert owner.controls.current_control.value == 3.


def test_vtol_altitude_hold_keeps_session_engagement_reference_across_phase_cycles():
    owner, now, state = session(altitude=False, state=aircraft_state(
        phase=AirframePhase.MULTICOPTER, is_vtol=True, is_tailsitter=True))
    state = settle(owner, now, state)
    engagement_altitude = state.altitude_amsl_m
    for phase, altitude in [(AirframePhase.VTOL_TRANSITION, 548.), (AirframePhase.FIXED_WING, 547.),
                            (AirframePhase.VTOL_TRANSITION, 548.), (AirframePhase.MULTICOPTER, 548.),
                            (AirframePhase.VTOL_TRANSITION, 546.), (AirframePhase.FIXED_WING, 545.)]:
        now[0] += .1
        state = replace(state, altitude_amsl_m=altitude)
        _, state = observe(owner, now, state, phase=phase)
        if phase is not AirframePhase.VTOL_TRANSITION:
            now[0] += .31
            _, state = observe(owner, now, state)
        if phase is AirframePhase.FIXED_WING:
            command = owner.calculate(Vector3(1., 0., .2), capabilities=CAPABILITIES,
                                      multicopter_calculate=Mock())
            assert command.fields["altitude_amsl_m"] == engagement_altitude


def test_transition_cannot_recapture_a_changed_altitude_reference():
    owner, now, state = session(altitude=False, state=aircraft_state(
        phase=AirframePhase.MULTICOPTER, is_vtol=True, is_tailsitter=True))
    state = settle(owner, now, state)
    now[0] += .1
    _, state = observe(owner, now, state, phase=AirframePhase.VTOL_TRANSITION)
    now[0] += .1
    state = replace(state, altitude_reference_generation=state.altitude_reference_generation + 1)
    with pytest.raises(ValueError, match="altitude_reference_changed"):
        observe(owner, now, state, phase=AirframePhase.FIXED_WING)
    with pytest.raises(ValueError, match="guidance_session_ended"):
        owner.baseline()


@pytest.mark.parametrize("reason", ["takeover", "rescue", "stale", "stop"])
def test_ended_session_never_produces_new_commands_or_resumes(reason):
    owner, now, state = session()
    state = settle(owner, now, state)
    if reason == "stop":
        owner.end("operator_stop")
    else:
        now[0] += 1. if reason == "stale" else .1
        if reason == "rescue":
            state = replace(state, rescue_active=True)
        owner.observe(state, owner_confirmed=reason != "takeover", target_confirmed=True)
    with pytest.raises(ValueError, match="session_ended"):
        owner.calculate(Vector3(1., 0., 0.), capabilities=CAPABILITIES, multicopter_calculate=Mock())
    assert owner.controls.snapshot(client_contract_version=2) is None
    _, state = observe(owner, now, state)
    with pytest.raises(ValueError, match="session_ended"):
        owner.baseline()


def test_repeat_observation_cannot_refresh_cached_aircraft_state():
    owner, now, state = session()
    state = settle(owner, now, state)
    now[0] += .2
    owner.observe(replace(state, observed_at_monotonic_s=now[0]), owner_confirmed=True, target_confirmed=True)
    now[0] += .6
    with pytest.raises(ValueError, match="aircraft_state_stale"):
        owner.baseline()


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
@pytest.mark.parametrize("attitude,heading", [(Quaternion(1., 0., 0., 0.), 0.),
                                              (Quaternion(math.cos(.35), 0., math.sin(.35), 0.), 0.),
                                              (Quaternion(math.cos(.3), math.sin(.3), 0., 0.), 0.),
                                              (Quaternion(math.cos(.4), 0., 0., math.sin(.4)), .8)])
def test_physical_ray_uses_full_attitude_once_before_heading_velocity_boundary(mount, attitude, heading):
    owner, now, state = session(state=aircraft_state(phase=AirframePhase.MULTICOPTER,
                                                    is_vtol=True, is_tailsitter=True,
                                                    attitude_body_to_ned=attitude, navigation_heading_rad=heading))
    settle(owner, now, state)
    target = (30., 10., 12.)
    angles = camera_angles_for_world_target((0., 0., 0.), target,
                                            (attitude.w, attitude.x, attitude.y, attitude.z), mount)
    physical_ray = Vector3(*body_line_of_sight(angles, mount))
    seen = []

    def multicopter_calculate(ray):
        seen.append(ray)
        return CommandIntent("gm_velocity_vector", "velocity_body_offboard",
                             dict(vel_body_fwd=ray.x, vel_body_right=ray.y, vel_body_down=ray.z,
                                  yawspeed_deg_s=0.), "existing_mc_follower")

    intent = owner.calculate(physical_ray, capabilities=CAPABILITIES, multicopter_calculate=multicopter_calculate)
    north, east, down = target
    expected = Vector3(math.cos(heading) * north + math.sin(heading) * east,
                       -math.sin(heading) * north + math.cos(heading) * east, down).normalized()
    assert (seen[0].x, seen[0].y, seen[0].z) == pytest.approx((expected.x, expected.y, expected.z))
    assert intent.guidance_identity == owner.identity


def test_fw_limits_are_checked_on_physical_provider_ray_before_world_rotation():
    owner, now, state = session()
    settle(owner, now, state)
    limits = replace(CAPABILITIES, azimuth_limits_deg=(-45., 45.))
    with pytest.raises(ValueError, match="provider_geometry_limit"):
        owner.calculate(Vector3(0., 1., 0.), capabilities=limits, multicopter_calculate=Mock())


def test_level_baseline_does_not_change_rearward_turn_latch_or_target_geometry():
    owner, now, state = session()
    settle(owner, now, state)
    for y in (.01, -.01):
        intent = owner.calculate(Vector3(-1., y, .1), capabilities=CAPABILITIES, multicopter_calculate=Mock())
        assert intent.fields["course_rad"] > 0.
        baseline = owner.baseline()
        assert baseline.fields["course_rad"] == intent.fields["course_rad"]
        assert baseline.fields["height_rate_m_s"] == 0.


def test_incomplete_native_envelope_cannot_leave_a_partially_bound_session():
    owner, now, state = session()
    with pytest.raises(ValueError, match="envelope_unavailable"):
        observe(owner, now, replace(state, fixed_wing_envelope=None))
    assert owner.controls.snapshot(client_contract_version=2) is None
    with pytest.raises(ValueError, match="session_ended"):
        owner.baseline()


@pytest.mark.parametrize("altitude", [True, False])
def test_final_fw_guard_applies_native_limits_without_mc_speed_or_axis_clamps(altitude):
    owner, now, state = session(altitude=altitude)
    state = settle(owner, now, state)
    fields = owner.baseline().fields | {"equivalent_airspeed_m_s": 50.}
    if altitude:
        fields["height_rate_m_s"] = -50.
    guarded = owner.guard_native_fields(fields)
    assert guarded["equivalent_airspeed_m_s"] == 20.
    if altitude:
        assert guarded["height_rate_m_s"] == -5.
        now[0] += .1
        observe(owner, now, replace(state, relative_altitude_m=6.))
        assert owner.guard_native_fields(fields)["height_rate_m_s"] == 0.
    else:
        assert guarded["altitude_amsl_m"] == 550.
        with pytest.raises(ValueError, match="hold_contract_changed"):
            owner.guard_native_fields(fields | {"altitude_amsl_m": 500.})


def test_recovery_command_cannot_restore_a_speed_above_the_acknowledged_fw_request():
    owner, now, state = session(altitude=False)
    state = settle(owner, now, state)
    retained = owner.baseline().fields
    control = owner.controls.current_control
    owner.controls.update(15., identity=owner.identity, expected_revision=control.revision, recovering=True)
    assert owner.guard_native_fields(retained)["equivalent_airspeed_m_s"] == 15.
    now[0] += .1
    observe(owner, now, replace(state, fixed_wing_envelope=replace(state.fixed_wing_envelope,
                                                                 minimum_eas_m_s=18.)))
    assert owner.controls.current_control.value == 15.
    assert owner.guard_native_fields(retained)["equivalent_airspeed_m_s"] == 18.


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
@pytest.mark.parametrize("phase", [AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING])
def test_registered_vector_follower_uses_one_phase_session_and_correct_command_contract(mount, phase):
    import time
    from types import SimpleNamespace
    from classes.follower import FollowerFactory
    from classes.tracker_output import TrackerDataType, TrackerOutput

    controller = SimpleNamespace(current_altitude=50., current_yaw=0., current_roll=0., current_pitch=0.,
                                 is_command_connection_ready=lambda **_: True)
    follower = FollowerFactory.create_follower("gm_velocity_vector", controller, (0., 0.))
    follower.mount_type = mount
    # Match the canonical geometry to this explicit test installation.
    from classes.gimbal_geometry import resolve_angle_geometry
    follower.angle_geometry = resolve_angle_geometry({}, mount)
    follower.angle_deadzone = 0.
    follower.angle_smoothing_alpha = 1.
    follower.enable_altitude_control = True
    follower.guidance_capabilities = CAPABILITIES
    follower.guidance_classifier.update_capabilities(CAPABILITIES)
    state = aircraft_state(phase=phase, is_vtol=True, is_tailsitter=True,
                           attitude_body_to_ned=Quaternion(math.cos(.2), 0., math.sin(.2), 0.))
    owner, now, state = session(state=state)
    state = settle(owner, now, state)
    follower.bind_airframe_session(owner)

    assert follower._session_controls == {}
    assert follower.get_airframe_phase() == phase.value
    assert follower.session_controls()[0]["guidance_generation"] == owner.identity.guidance_generation
    if phase is AirframePhase.MULTICOPTER:
        current = owner.controls.current_control
        follower.update_session_control("requested_speed", 2., current.revision)
        assert owner.controls.current_control.value == 2.
    target = (40., 0., 10.)
    q = state.attitude_body_to_ned
    angles = camera_angles_for_world_target((0., 0., 0.), target, (q.w, q.x, q.y, q.z), mount)
    follower.calculate_control_commands(TrackerOutput(TrackerDataType.GIMBAL_ANGLES, time.time(), True,
                                                      angular=angles))
    intent = follower.get_last_command_intent()
    assert intent.guidance_identity == owner.identity
    assert intent.control_type == owner.control_type
    if phase is AirframePhase.MULTICOPTER:
        assert intent.fields["vel_body_down"] > 0.
        assert intent.fields["vel_body_fwd"] > 0.
    else:
        assert intent.fields["height_rate_m_s"] < 0.
        assert "vel_body_fwd" not in intent.fields
        assert follower.limit_authorized_command(intent.fields)["equivalent_airspeed_m_s"] == 20.
    follower.emergency_stop()
    assert follower.get_last_command_intent() is None
    assert follower.session_controls() == []


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
def test_phase_change_retires_old_ray_and_command_contract(mount):
    import time
    from types import SimpleNamespace
    from classes.follower import FollowerFactory
    from classes.gimbal_geometry import resolve_angle_geometry
    from classes.tracker_output import TrackerDataType, TrackerOutput

    follower = FollowerFactory.create_follower("gm_velocity_vector", SimpleNamespace(current_altitude=50.), (0., 0.))
    follower.mount_type = mount
    follower.angle_geometry = resolve_angle_geometry({}, mount)
    follower.angle_deadzone = 0.
    follower.angle_smoothing_alpha = .1
    owner, now, state = session(state=aircraft_state(phase=AirframePhase.MULTICOPTER,
                                                   is_vtol=True, is_tailsitter=True))
    state = settle(owner, now, state)
    follower.bind_airframe_session(owner)

    def calculate(target):
        q = state.attitude_body_to_ned
        angles = camera_angles_for_world_target((0., 0., 0.), target, (q.w, q.x, q.y, q.z), mount)
        follower.calculate_control_commands(TrackerOutput(TrackerDataType.GIMBAL_ANGLES, time.time(), True,
            angular=angles, metadata={"guidance_capabilities": {
                "known": True, "supports_vertical": True, "supports_reverse": True, "supports_yaw_fallback": True}}))
        return follower.get_last_command_intent()

    control = owner.controls.current_control
    follower.update_session_control("requested_speed", 2., control.revision)
    calculate((40., 0., 0.))
    now[0] += .1
    _, state = observe(owner, now, state, phase=AirframePhase.VTOL_TRANSITION)
    now[0] += .1
    state = replace(state, attitude_body_to_ned=Quaternion.from_euler(0., math.pi / 2, 0.))
    _, state = observe(owner, now, state, phase=AirframePhase.FIXED_WING)
    now[0] += .31
    _, state = observe(owner, now, state)
    identity = owner.identity
    speed = owner.controls.current_control.value
    command = calculate((40., 20., 8.))
    assert command.fields["course_rad"] == pytest.approx(math.atan2(20., 40.), abs=1e-9)
    assert command.fields["height_rate_m_s"] < 0.
    assert owner.identity == identity
    assert owner.controls.current_control.value == speed
    # Normal observations in the same phase still use the configured filter.
    second = calculate((40., 40., 8.))
    assert command.fields["course_rad"] < second.fields["course_rad"] < math.pi / 4
    follower.record_submitted_command(second.fields)
    assert follower._session_velocity_envelope() is None
    now[0] += .1
    _, state = observe(owner, now, state, phase=AirframePhase.VTOL_TRANSITION)
    now[0] += .1
    state = replace(state, attitude_body_to_ned=Quaternion(1., 0., 0., 0.))
    _, state = observe(owner, now, state, phase=AirframePhase.MULTICOPTER)
    # A paused MC baseline must never read velocity keys from a FW course/EAS command.
    baseline = follower.limit_session_control_command(owner.baseline().fields)
    baseline = follower.limit_authorized_command(baseline)
    assert all(value == 0. for value in baseline.values())
    follower.record_submitted_command(baseline)
    now[0] += .31
    _, state = observe(owner, now, state)
    assert owner.controls.current_control.value == 2.
    resumed = calculate((40., 20., 0.))
    bounded = follower.limit_authorized_command(follower.limit_session_control_command(resumed.fields))
    assert all(math.isfinite(value) for value in bounded.values())
    assert 0. < math.hypot(*(bounded[k] for k in ('vel_body_fwd', 'vel_body_right', 'vel_body_down'))) < 2.
