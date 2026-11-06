"""Observed flight-phase lifecycle for one Vector follow session.

This owner does not request a VTOL transition or implement a target-loss timer.
The existing continuity supervisor owns target budgets; native PX4 owns the
transition dynamics. A terminal interruption is latched until a new session.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from classes.aircraft_state import AircraftState, AirframePhase, GuidanceSessionIdentity, finite_number
from classes.native_guidance import NativeCapabilities


class PhaseSessionState(str, Enum):
    STARTING = "starting"
    PURSUIT = "pursuit"
    TRANSITION = "transition"
    CONFIRMING = "confirming_phase"
    ENDED = "ended"


@dataclass(frozen=True)
class PhaseDecision:
    state: PhaseSessionState
    phase: AirframePhase
    generation: int
    pursuit_allowed: bool
    transition_setpoints_required: bool
    reason: str


class GuidancePhaseSession:
    def __init__(self, identity: GuidanceSessionIdentity, capabilities: NativeCapabilities, *,
                 confirmation_s: float, observation_timeout_s: float, transition_timeout_s: float):
        if finite_number(confirmation_s, "phase_confirmation") < 0:
            raise ValueError("phase_confirmation_negative")
        if finite_number(observation_timeout_s, "observation_timeout") <= 0:
            raise ValueError("observation_timeout_not_positive")
        if finite_number(transition_timeout_s, "transition_timeout") <= 0:
            raise ValueError("transition_timeout_not_positive")
        self.identity = identity
        self.capabilities = capabilities
        self.confirmation_s = confirmation_s
        self.observation_timeout_s = observation_timeout_s
        self.transition_timeout_s = transition_timeout_s
        self.state = PhaseSessionState.STARTING
        self.phase = AirframePhase.UNKNOWN
        self.generation = identity.guidance_generation
        self._sequence = -1
        self._last_observed_at = None
        self._candidate_phase = None
        self._candidate_started = None
        self._transition_started = None
        self._reason = "not_started"

    def end(self, reason: str) -> PhaseDecision:
        if self.state is not PhaseSessionState.ENDED:
            self.state = PhaseSessionState.ENDED
            self._advance_generation()
            self._reason = reason
        return self._decision()

    def observe(self, observation: AircraftState, *, now: float, owner_confirmed: bool,
                target_confirmed: bool) -> PhaseDecision:
        if self.state is PhaseSessionState.ENDED:
            return self._decision()
        if observation.binding != self.identity.binding:
            return self.end("aircraft_connection_changed")
        if not observation.fresh(now, self.observation_timeout_s):
            return self.end("aircraft_state_stale")
        if observation.rescue_active:
            return self.end("aircraft_rescue_active")
        if owner_confirmed is not True:
            return self.end("control_owner_lost")
        if observation.phase is AirframePhase.UNKNOWN:
            return self.end("aircraft_phase_unknown")
        if observation.sequence <= self._sequence:
            return self._decision()
        if (self._last_observed_at is not None and observation.observed_at_monotonic_s
                - self._last_observed_at > self.observation_timeout_s):
            return self.end("aircraft_observation_gap")
        if self._last_observed_at is not None and observation.observed_at_monotonic_s <= self._last_observed_at:
            return self.end("aircraft_observation_reordered")
        self._sequence = observation.sequence
        self._last_observed_at = observation.observed_at_monotonic_s

        if self._transition_started is not None and now - self._transition_started >= self.transition_timeout_s:
            return self.end("vtol_transition_timeout")

        if observation.phase is AirframePhase.VTOL_TRANSITION:
            if not observation.is_vtol or not self.capabilities.vtol_transition_supported:
                return self.end("vtol_transition_unavailable")
            if self.phase is not observation.phase:
                self._advance_generation()
            self.phase = observation.phase
            if self._transition_started is None:
                self._transition_started = now
            self.state = PhaseSessionState.TRANSITION
            self._candidate_phase = None
            self._candidate_started = None
            self._reason = "native_transition_in_progress"
            return self._decision()

        if self.state is PhaseSessionState.PURSUIT:
            if observation.phase is not self.phase:
                return self.end("phase_changed_without_observed_transition")
            return self._decision()

        if observation.phase is AirframePhase.FIXED_WING and not self.capabilities.fixed_wing_supported:
            return self.end("native_fixed_wing_unavailable")
        if self._candidate_phase is not observation.phase:
            self._advance_generation()
            self._candidate_phase = observation.phase
            self._candidate_started = now
        self.phase = observation.phase
        self.state = PhaseSessionState.CONFIRMING
        self._reason = "phase_confirmation_pending"
        if now - self._candidate_started >= self.confirmation_s:
            self._transition_started = None
            if target_confirmed is True:
                self.state = PhaseSessionState.PURSUIT
                self._reason = "phase_and_target_confirmed"
            else:
                self._reason = "target_confirmation_pending"
        return self._decision()

    def _advance_generation(self) -> None:
        self.generation += 1
        self.identity = replace(self.identity, guidance_generation=self.generation)

    def _decision(self) -> PhaseDecision:
        return PhaseDecision(self.state, self.phase, self.generation,
                             self.state is PhaseSessionState.PURSUIT,
                             self.state is PhaseSessionState.TRANSITION, self._reason)
