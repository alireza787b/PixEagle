from dataclasses import replace

from classes.aircraft_state import AircraftBinding, AirframePhase
from classes.guidance_phase_session import GuidancePhaseSession, PhaseSessionState
from classes.native_guidance import GuidanceSessionIdentity, NativeCapabilities
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


def session():
    return GuidancePhaseSession(
        GuidanceSessionIdentity("follow-a", AircraftBinding("aircraft-a", "connection-1", 1), 1),
        NativeCapabilities("adapter-a", "px4-test", 2, True, True, False),
        confirmation_s=.5, observation_timeout_s=.75, transition_timeout_s=10.,
    )


def observe(owner, sequence, now, phase, *, target=True, authority=True, **changes):
    state = aircraft_state(sequence=sequence, observed_at_monotonic_s=now, phase=phase,
                           is_vtol=True, is_tailsitter=True, **changes)
    return owner.observe(state, now=now, target_confirmed=target, owner_confirmed=authority)


def test_same_session_survives_authorized_transition_but_pursuit_waits_for_confirmation():
    owner = session()
    assert not observe(owner, 1, 100, AirframePhase.MULTICOPTER).pursuit_allowed
    assert observe(owner, 2, 100.5, AirframePhase.MULTICOPTER).pursuit_allowed
    old_generation = owner.generation
    result = observe(owner, 3, 100.6, AirframePhase.VTOL_TRANSITION)
    assert result.transition_setpoints_required and not result.pursuit_allowed
    assert result.generation > old_generation
    for sequence, timestamp in enumerate([101, 101.5, 102, 102.5, 103, 103.5, 104, 104.5], 4):
        observe(owner, sequence, timestamp, AirframePhase.VTOL_TRANSITION)
    assert not observe(owner, 12, 105, AirframePhase.FIXED_WING).pursuit_allowed
    assert not observe(owner, 13, 105.5, AirframePhase.FIXED_WING, target=False).pursuit_allowed
    result = observe(owner, 14, 105.6, AirframePhase.FIXED_WING)
    assert result.pursuit_allowed
    assert owner.identity.follow_session_id == "follow-a"


def test_repeated_status_poll_cannot_complete_phase_confirmation():
    owner = session()
    observe(owner, 1, 100, AirframePhase.FIXED_WING)
    state = aircraft_state(is_vtol=True, sequence=1)
    result = owner.observe(state, now=100.2, target_confirmed=True, owner_confirmed=True)
    assert not result.pursuit_allowed
    assert owner.observe(state, now=101, target_confirmed=True, owner_confirmed=True).reason == "aircraft_state_stale"


def test_quadchute_never_restores_following_when_mc_telemetry_returns():
    owner = session()
    observe(owner, 1, 100, AirframePhase.FIXED_WING)
    observe(owner, 2, 100.5, AirframePhase.FIXED_WING)
    result = observe(owner, 3, 101, AirframePhase.MULTICOPTER, rescue_active=True)
    assert result.state is PhaseSessionState.ENDED
    assert observe(owner, 4, 102, AirframePhase.MULTICOPTER).reason == "aircraft_rescue_active"


def test_pilot_takeover_latches_end_and_does_not_resume_in_new_phase():
    owner = session()
    observe(owner, 1, 100, AirframePhase.MULTICOPTER)
    result = observe(owner, 2, 100.5, AirframePhase.MULTICOPTER, authority=False)
    assert result.reason == "control_owner_lost"
    assert not observe(owner, 3, 102, AirframePhase.FIXED_WING).pursuit_allowed


def test_phase_change_without_transition_observation_fails_closed():
    owner = session()
    observe(owner, 1, 100, AirframePhase.MULTICOPTER)
    observe(owner, 2, 100.5, AirframePhase.MULTICOPTER)
    assert observe(owner, 3, 101, AirframePhase.FIXED_WING).reason == "phase_changed_without_observed_transition"


def test_new_aircraft_cannot_take_over_old_session():
    owner = session()
    state = aircraft_state(binding=AircraftBinding("aircraft-b", "connection-1", 1))
    assert owner.observe(state, now=100, target_confirmed=True, owner_confirmed=True).reason == "aircraft_connection_changed"


def test_fresh_sample_after_a_long_gap_cannot_complete_a_confirmation_dwell():
    owner = session()
    observe(owner, 1, 100, AirframePhase.FIXED_WING)
    result = observe(owner, 2, 1000, AirframePhase.FIXED_WING)
    assert not result.pursuit_allowed
    assert result.reason == "aircraft_observation_gap"


def test_transition_flaps_cannot_renew_the_native_transition_deadline():
    owner = session()
    observe(owner, 1, 100., AirframePhase.MULTICOPTER)
    observe(owner, 2, 100.5, AirframePhase.MULTICOPTER)
    observe(owner, 3, 101., AirframePhase.VTOL_TRANSITION)
    sequence = 3
    for step in range(1, 21):
        sequence += 1
        phase = AirframePhase.FIXED_WING if step % 3 == 1 else AirframePhase.VTOL_TRANSITION
        result = observe(owner, sequence, 101. + step * .5, phase)
    assert result.reason == "vtol_transition_timeout"
    assert not observe(owner, sequence + 1, 111.5, AirframePhase.FIXED_WING).pursuit_allowed


def test_settled_phase_does_not_resume_without_confirmed_target():
    owner = session()
    observe(owner, 1, 100., AirframePhase.MULTICOPTER)
    observe(owner, 2, 100.5, AirframePhase.MULTICOPTER)
    observe(owner, 3, 101., AirframePhase.VTOL_TRANSITION)
    observe(owner, 4, 101.5, AirframePhase.FIXED_WING, target=False)
    result = observe(owner, 5, 102., AirframePhase.FIXED_WING, target=False)
    assert result.reason == "target_confirmation_pending"
    assert not result.pursuit_allowed
    assert owner._transition_started is None
