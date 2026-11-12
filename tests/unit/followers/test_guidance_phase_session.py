from dataclasses import replace

import pytest

from classes.aircraft_state import AircraftBinding, AircraftLayout, AirframePhase
from classes.guidance_phase_session import GuidancePhaseSession, PhaseSessionState
from classes.native_guidance import GuidanceSessionIdentity, NativeCapabilities
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


def session(*, initial_phase=None):
    return GuidancePhaseSession(
        GuidanceSessionIdentity("follow-a", AircraftBinding("aircraft-a", "connection-1", 1), 1),
        NativeCapabilities("adapter-a", "px4-test", 2, True, True, False),
        confirmation_s=.5, observation_timeout_s=.75, initial_phase=initial_phase,
    )


def observe(owner, sequence, now, phase, *, target=True, authority=True, **changes):
    state = aircraft_state(sequence=sequence, observed_at_monotonic_s=now, phase=phase,
                           is_vtol=True, is_tailsitter=True, **changes)
    return owner.observe(state, now=now, target_confirmed=target, owner_confirmed=authority)


@pytest.mark.parametrize("phase", [AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING])
def test_transition_ends_original_identity_once_and_never_resumes(phase):
    owner = session()
    identity = owner.identity
    assert not observe(owner, 1, 100, phase).pursuit_allowed
    assert observe(owner, 2, 100.5, phase).pursuit_allowed
    assert owner.identity == identity
    result = observe(owner, 3, 100.6, AirframePhase.VTOL_TRANSITION)
    assert result.state is PhaseSessionState.ENDED
    assert result.reason == "aircraft_transition_observed"
    assert result.generation == identity.guidance_generation + 1
    for sequence, next_phase in enumerate((AirframePhase.FIXED_WING, AirframePhase.MULTICOPTER), 4):
        assert observe(owner, sequence, 100.7, next_phase) == result


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
    assert observe(owner, 3, 101, AirframePhase.FIXED_WING).reason == "aircraft_phase_changed"


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


def test_startup_waits_for_confirmed_target_without_rotating_identity():
    owner = session()
    identity = owner.identity
    observe(owner, 1, 100., AirframePhase.FIXED_WING, target=False)
    result = observe(owner, 2, 100.5, AirframePhase.FIXED_WING, target=False)
    assert result.reason == "target_confirmation_pending"
    assert owner.identity == identity
    assert observe(owner, 3, 100.6, AirframePhase.FIXED_WING).pursuit_allowed
    assert owner.identity == identity


def test_initial_phase_is_pinned_before_first_observation():
    owner = session(initial_phase=AirframePhase.FIXED_WING)
    assert observe(owner, 1, 100., AirframePhase.MULTICOPTER).reason == "aircraft_phase_changed"


@pytest.mark.parametrize("fault,reason", [
    (None, "aircraft_transition_observed"),
    ("binding", "aircraft_connection_changed"),
    ("stale", "aircraft_state_stale"),
    ("rescue", "aircraft_rescue_active"),
    ("layout", "aircraft_layout_mismatch"),
    ("gap", "aircraft_observation_gap"),
    ("duplicate", "control_owner_lost"),
])
def test_current_transition_reason_survives_coincident_release_without_overriding_safety(fault, reason):
    owner = session(initial_phase=AirframePhase.FIXED_WING)
    observe(owner, 1, 100., AirframePhase.FIXED_WING)
    observe(owner, 2, 100.5, AirframePhase.FIXED_WING)
    now = 102. if fault == "gap" else 100.6
    state = aircraft_state(sequence=3, observed_at_monotonic_s=now,
        phase=AirframePhase.VTOL_TRANSITION, is_vtol=True, is_tailsitter=True)
    if fault == "binding":
        state = replace(state, binding=AircraftBinding("other", "connection-1", 1))
    elif fault == "stale":
        state = replace(state, observed_at_monotonic_s=99.)
    elif fault == "rescue":
        state = replace(state, rescue_active=True)
    elif fault == "layout":
        owner.expected_layout = AircraftLayout.FIXED_WING
    elif fault == "duplicate":
        state = replace(state, sequence=2)
    result = owner.observe(state, now=now, owner_confirmed=False, target_confirmed=True)
    assert result.state is PhaseSessionState.ENDED
    assert result.reason == reason
    assert not result.pursuit_allowed
