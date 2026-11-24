"""Shared session controls and phase lifecycle with stock packet projection."""

from dataclasses import replace
import json
import math

import pytest

from classes.aircraft_state import AirframePhase, GuidanceSessionIdentity, Quaternion, Vector3
from classes.airframe_session_controls import AirframeSessionControls
from classes.command_intent import CommandIntent
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy, UpperSpeedPolicy
from classes.fixed_wing_mavlink_control import FixedWingMavlinkVectorControl
from classes.gimbal_guidance import GimbalGuidancePolicy
from classes.guidance_phase_session import PhaseSessionState
from classes.mavlink_vector_guidance_session import MavlinkGuidanceCapabilities, MavlinkVectorGuidanceSession
from classes.safety_types import AltitudeLimits
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.unit.followers.test_fixed_wing_mavlink_control import tuning


def setup(*, unbounded=False, altitude=True, mc=False, confirming=False):
    state = aircraft_state(phase=AirframePhase.MULTICOPTER if mc else AirframePhase.FIXED_WING)
    identity = GuidanceSessionIdentity("follow-a", state.binding, 0)
    caps = MavlinkGuidanceCapabilities("mavlink-session-a", True, True, True, unbounded)
    policy = FixedWingGuidancePolicy(UpperSpeedPolicy.NO_UPPER_SPEED_BOUND if unbounded
                                    else UpperSpeedPolicy.PX4_CONFIGURED_MAX)
    geometry = GimbalGuidancePolicy().geometry
    projection = FixedWingMavlinkVectorControl(tuning=tuning(), geometry=geometry,
                                              policy=policy, enable_altitude_control=altitude)
    controls = AirframeSessionControls(identity, multicopter_startup_m_s=0., multicopter_ceiling_m_s=6., step_m_s=.5)
    session = MavlinkVectorGuidanceSession(identity, caps, projection=projection,
        profile_name="gm_velocity_vector", controls=controls,
        supported_phases=frozenset({AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING}),
        geometry_policy=geometry, altitude_control=altitude, altitude_limits=AltitudeLimits(3., 120., 2.),
        confirmation_s=.5 if confirming else 0., observation_timeout_s=.5, clock=lambda: 100.,
        fixed_wing_policy=policy, initial_phase=state.phase)
    session.observe(state, owner_confirmed=True, target_confirmed=True)
    return session, state


def wire(session, state, intent, **kwargs):
    return json.loads(session.packet(intent, state, system_id=1, component_id=1, **kwargs).fields_json)


def test_fw_uses_shared_requested_speed_and_projects_the_same_world_ray():
    session, state = setup(unbounded=True)
    control = session.controls.current_control
    session.controls.update(60., identity=session.identity, expected_revision=control.revision)
    intent = session.calculate_ned(Vector3(.5, 0., math.sqrt(3)/2), frame="ned")
    assert intent.control_type == "fixed_wing_external"
    assert intent.guidance_identity == session.identity
    assert intent.fields["equivalent_airspeed_m_s"] == 60.
    packet = wire(session, state, intent)
    assert packet["thrust"] == 1.
    assert packet["type_mask"] == 7
    # Shared source policy and one strategy instance, not parallel planners.
    assert session.fixed_wing is session.projection.direction


def test_retained_nominal_or_recovery_intent_cannot_undo_acknowledged_speed_reduction():
    session, state = setup(unbounded=True)
    session.controls.update(60., identity=session.identity, expected_revision=session.controls.current_control.revision)
    intent = session.calculate_ned(Vector3(1., 0., 0.), frame="ned")
    session.controls.update(20., identity=session.identity, expected_revision=session.controls.current_control.revision)
    assert wire(session, state, intent)["thrust"] == pytest.approx(.6)


def test_normal_control_does_not_offer_an_unqualified_unbounded_override():
    session, _ = setup()
    control = session.controls.current_control
    assert control.minimum == 12. and control.maximum == 30.
    with pytest.raises(ValueError):
        session.controls.update(60., identity=session.identity, expected_revision=control.revision)
    assert session.controls.snapshot(client_contract_version=1) is None
    assert session.controls.snapshot(client_contract_version=2)["aircraft_phase"] == "fixed_wing"


@pytest.mark.parametrize("change", [
    {"phase": AirframePhase.VTOL_TRANSITION, "is_vtol": True},
    {"phase": AirframePhase.MULTICOPTER}, {"rescue_active": True},
])
def test_phase_or_rescue_change_ends_session_and_invalidates_old_editors_and_packets(change):
    session, state = setup(unbounded=True)
    intent = session.calculate_ned(Vector3(1., 0., 0.), frame="ned")
    old_identity = session.identity
    old_control = session.controls.current_control
    session.observe(replace(state, sequence=state.sequence + 1, **change), owner_confirmed=True, target_confirmed=True)
    assert session.phase_owner.state is PhaseSessionState.ENDED
    with pytest.raises(ValueError):
        wire(session, state, intent)
    with pytest.raises(ValueError):
        session.controls.update(25., identity=old_identity, expected_revision=old_control.revision)


def test_takeover_cannot_be_repaired_by_later_returning_offboard_or_target_status():
    session, state = setup()
    session.observe(replace(state, sequence=state.sequence + 1), owner_confirmed=False, target_confirmed=True)
    session.observe(replace(state, sequence=state.sequence + 2), owner_confirmed=True, target_confirmed=True)
    assert session.phase_owner.state is PhaseSessionState.ENDED


def test_confirmation_cannot_publish_a_pursuit_command_before_the_target_and_phase_gate():
    session, state = setup(confirming=True)
    baseline = session.baseline()
    assert wire(session, state, baseline)["thrust"] > 0.
    forged = replace(baseline, fields={**baseline.fields, "course_rad": 1.})
    with pytest.raises(ValueError, match="confirmation_pending"):
        wire(session, state, forged)


def test_mc_altitude_disabled_preserves_frozen_engagement_altitude_in_local_ned():
    session, state = setup(mc=True, altitude=False)
    baseline = session.baseline()
    packet = wire(session, state, baseline, local_position_ned=Vector3(0., 0., -50.))
    assert packet["type_mask"] == 1507 and packet["z"] == -50.
    # Measurement/reference changes are separate: one metre drift is corrected,
    # rather than ratcheting the engagement altitude to the newest aircraft pose.
    state = replace(state, sequence=state.sequence + 1, altitude_amsl_m=549., relative_altitude_m=49.)
    session.observe(state, owner_confirmed=True, target_confirmed=True)
    intent = session.multicopter_intent(CommandIntent("gm_velocity_vector", "velocity_body_offboard",
        dict(vel_body_fwd=.1, vel_body_right=0., vel_body_down=0., yawspeed_deg_s=0.), "test", created_at_monotonic_s=100.))
    packet = wire(session, state, intent, local_position_ned=Vector3(0., 0., -49.))
    assert packet["z"] == -50.
    assert packet["vx"] == .1


def test_mc_altitude_hold_requires_the_original_reference_and_a_current_position():
    session, state = setup(mc=True, altitude=False)
    baseline = session.baseline()
    with pytest.raises(ValueError, match="altitude_reference"):
        wire(session, state, baseline)
    bad = replace(baseline, altitude_hold=replace(baseline.altitude_hold, reference_generation=1))
    with pytest.raises(ValueError, match="altitude_reference"):
        wire(session, state, bad, local_position_ned=Vector3(0., 0., -50.))


def test_packet_cannot_use_an_older_but_still_fresh_aircraft_snapshot():
    session, state = setup()
    intent = session.calculate_ned(Vector3(1., 0., 0.), frame="ned")
    session.observe(replace(state, sequence=state.sequence + 1), owner_confirmed=True, target_confirmed=True)
    with pytest.raises(ValueError, match="context_changed"):
        wire(session, state, intent)


def test_restore_reinstates_speed_and_vertical_envelopes_without_accelerating_a_lower_request():
    session, state = setup(unbounded=True)
    state = replace(state, sequence=state.sequence + 1, relative_altitude_m=1000., altitude_amsl_m=1500.)
    session.altitude_limits = AltitudeLimits(3., None, 2.)
    session.observe(state, owner_confirmed=True, target_confirmed=True)
    assert session.controls.current_control.override_active
    intent = session.calculate_ned(Vector3(.5, 0., math.sqrt(3)/2), frame="ned")
    before = wire(session, state, intent)
    assert not session.projection.direction.vertical_limits_enabled
    assert Quaternion(*before["q"]).rotate(Vector3(1., 0., 0.)).z > .8
    value = session.controls.current_control.value
    restored = session.controls.update(None, identity=session.identity,
        expected_revision=session.controls.current_control.revision, recovering=True)
    assert restored.value == value
    assert not restored.override_active
    after = wire(session, state, intent)  # Even a retained old intent is guarded.
    assert session.projection.direction.vertical_limits_enabled
    assert session.projection.policy.upper_speed_policy is UpperSpeedPolicy.PX4_CONFIGURED_MAX
    assert Quaternion(*after["q"]).rotate(Vector3(1., 0., 0.)).z < .3
    # A new explicit manual request re-enables the configured private policy,
    # matching the existing session override contract. Public policy stays bounded.
    session.controls.update(value + .5, identity=session.identity, expected_revision=restored.revision)
    wire(session, state, intent)
    assert not session.projection.direction.vertical_limits_enabled
    session.controls.update(40., identity=session.identity, expected_revision=session.controls.current_control.revision)
    wire(session, state, intent)
    assert not session.projection.direction.vertical_limits_enabled


def test_end_also_revokes_direct_use_of_the_retained_projection():
    session, state = setup()
    command = session.fixed_wing.level_command(state, identity=session.identity, requested_eas_m_s=20.,
        altitude_limits=session.altitude_limits, now=100., timeout_s=.5)
    identity = session.identity
    session.end("operator_stop")
    with pytest.raises(ValueError, match="binding_changed"):
        session.projection.project(command, state, identity=identity, altitude_limits=session.altitude_limits,
                                   now=100., timeout_s=.5)
