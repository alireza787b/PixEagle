"""Observed flight-phase lifecycle for one Vector follow session.

This owner does not request a VTOL transition or implement a target-loss timer.
The existing continuity supervisor owns target budgets; native PX4 owns the
transition dynamics. A terminal interruption is latched until a new session.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol
from classes.aircraft_state import AircraftLayout, AircraftState, AirframePhase, GuidanceSessionIdentity, finite_number


class GuidanceCapabilities(Protocol):
    """Strategy support, separate from each transport's authority receipts."""

    runtime_id: str
    fixed_wing_supported: bool
    multicopter_supported: bool
    multicopter_altitude_hold_supported: bool
    unrestricted_speed_supported: bool


class PhaseSessionState(str, Enum):
    STARTING = "starting"
    PURSUIT = "pursuit"
    CONFIRMING = "confirming_phase"
    ENDED = "ended"


@dataclass(frozen=True)
class PhaseDecision:
    state: PhaseSessionState
    phase: AirframePhase
    generation: int
    pursuit_allowed: bool
    reason: str


class GuidancePhaseSession:
    def __init__(self, identity: GuidanceSessionIdentity, capabilities: GuidanceCapabilities, *,
                 confirmation_s: float, observation_timeout_s: float,
                 expected_layout: AircraftLayout = AircraftLayout.AUTO, initial_phase: AirframePhase | None = None):
        if finite_number(confirmation_s, "phase_confirmation") < 0:
            raise ValueError("phase_confirmation_negative")
        if finite_number(observation_timeout_s, "observation_timeout") <= 0:
            raise ValueError("observation_timeout_not_positive")
        if initial_phase is not None and (not isinstance(initial_phase, AirframePhase)
                                          or initial_phase not in {AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING}):
            raise ValueError("initial_aircraft_phase_unavailable")
        self.identity = identity
        if not isinstance(expected_layout, AircraftLayout):
            raise ValueError("aircraft_layout_invalid")
        self.expected_layout = expected_layout
        self.capabilities = capabilities
        self.confirmation_s = confirmation_s
        self.observation_timeout_s = observation_timeout_s
        self.initial_phase = initial_phase
        self.state = PhaseSessionState.STARTING
        self.phase = AirframePhase.UNKNOWN
        self.generation = identity.guidance_generation
        self._sequence = -1
        self._last_observed_at = None
        self._candidate_started = None
        self._reason = "not_started"

    @property
    def reason(self) -> str:
        return self._reason

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
        if observation.phase is AirframePhase.UNKNOWN:
            return self.end("aircraft_phase_unknown")
        if not self.expected_layout.matches(observation):
            return self.end("aircraft_layout_mismatch")
        owner_lost = owner_confirmed is not True
        if owner_lost and observation.phase is not AirframePhase.VTOL_TRANSITION:
            return self.end("control_owner_lost")
        if observation.sequence <= self._sequence:
            return self.end("control_owner_lost") if owner_lost else self._decision()
        if (self._last_observed_at is not None and observation.observed_at_monotonic_s
                - self._last_observed_at > self.observation_timeout_s):
            return self.end("aircraft_observation_gap")
        # A new status packet can precede the next pose sample. Aggregate
        # progress advances, while the oldest measurement keeps its real age.
        if self._last_observed_at is not None and observation.observed_at_monotonic_s < self._last_observed_at:
            return self.end("aircraft_observation_reordered")
        self._sequence = observation.sequence
        self._last_observed_at = observation.observed_at_monotonic_s

        if observation.phase is AirframePhase.VTOL_TRANSITION:
            return self.end("aircraft_transition_observed")
        selected = self.initial_phase or (observation.phase if self.phase is AirframePhase.UNKNOWN else self.phase)
        if observation.phase is not selected:
            return self.end("aircraft_phase_changed")
        self.phase = selected
        if self.state is PhaseSessionState.PURSUIT:
            return self._decision()

        if observation.phase is AirframePhase.FIXED_WING and not self.capabilities.fixed_wing_supported:
            return self.end("native_fixed_wing_unavailable")
        if self._candidate_started is None:
            self._candidate_started = now
        self.phase = observation.phase
        self.state = PhaseSessionState.CONFIRMING
        self._reason = "phase_confirmation_pending"
        if now - self._candidate_started >= self.confirmation_s:
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
                             self._reason)
