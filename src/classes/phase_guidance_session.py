"""Shared phase, control and frozen-altitude ownership.

The existing phase observer and session controls own their contracts. This
composition adds no publisher, target-loss deadline or pursuit controller.
"""

from dataclasses import replace
import time

from classes.aircraft_state import AircraftLayout, AircraftState, AirframePhase, GuidanceSessionIdentity
from classes.airframe_session_controls import AirframeSessionControls
from classes.command_intent import AltitudeHoldReference, CommandIntent
from classes.guidance_phase_session import GuidancePhaseSession, PhaseDecision, PhaseSessionState
from classes.guidance_phase_session import GuidanceCapabilities
from classes.safety_types import AltitudeLimits


class PhaseGuidanceSession:
    def __init__(self, identity: GuidanceSessionIdentity, capabilities: GuidanceCapabilities, *,
                 profile_name: str, controls: AirframeSessionControls,
                 supported_phases: frozenset[AirframePhase], altitude_control: bool,
                 altitude_limits: AltitudeLimits, confirmation_s: float,
                 observation_timeout_s: float, clock=time.monotonic,
                 expected_layout: AircraftLayout = AircraftLayout.AUTO, initial_phase: AirframePhase | None = None):
        if not isinstance(controls, AirframeSessionControls) or controls.identity != identity:
            raise ValueError("session_controls_binding_invalid")
        if (not isinstance(supported_phases, frozenset) or not supported_phases
                or any(not isinstance(phase, AirframePhase) for phase in supported_phases)
                or not supported_phases.issubset({AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING})):
            raise ValueError("session_supported_phases_invalid")
        self.profile_name = profile_name
        self.supported_phases = supported_phases
        self.phase_owner = GuidancePhaseSession(
            identity, capabilities, confirmation_s=confirmation_s,
            observation_timeout_s=observation_timeout_s, expected_layout=expected_layout, initial_phase=initial_phase,
        )
        self.controls = controls
        self._altitude_control = altitude_control
        self.altitude_limits = altitude_limits
        self.clock = clock
        self._state = None
        self._engagement_altitude_reference = None
        self._unrestricted_speed_verified = False

    @property
    def identity(self) -> GuidanceSessionIdentity:
        return self.phase_owner.identity

    @property
    def altitude_control(self) -> bool:
        return self._altitude_control

    @property
    def phase(self) -> AirframePhase:
        return self.phase_owner.phase

    @property
    def control_type(self) -> str:
        return "velocity_body_offboard" if self.phase is AirframePhase.MULTICOPTER else "unknown"

    def prepare_engagement_reference(self, state: AircraftState) -> AltitudeHoldReference:
        """Freeze before acquisition; later observations cannot ratchet this target."""
        if self.phase_owner.state is PhaseSessionState.ENDED:
            raise ValueError("guidance_session_ended")
        if (state.binding != self.identity.binding or state.rescue_active
                or not state.fresh(self.clock(), self.phase_owner.observation_timeout_s)
                or state.phase not in self.supported_phases):
            raise ValueError("native_engagement_state_unavailable")
        if state.phase is AirframePhase.MULTICOPTER and not self.phase_owner.capabilities.multicopter_altitude_hold_supported:
            raise ValueError("native_mc_altitude_hold_unavailable")
        reference = self._engagement_altitude_reference or state
        if (reference.binding != state.binding
                or reference.altitude_reference_generation != state.altitude_reference_generation):
            raise ValueError("altitude_reference_changed")
        self.altitude_limits.require_hold_target(
            reference.altitude_amsl_m, current_amsl_m=state.altitude_amsl_m,
            current_relative_m=state.relative_altitude_m)
        self._engagement_altitude_reference = reference
        return AltitudeHoldReference(reference.altitude_amsl_m, reference.altitude_reference_generation)

    def _multicopter_intent(self, intent: CommandIntent, state: AircraftState) -> CommandIntent:
        hold = None
        if (not self.altitude_control
                or self.phase_owner.state is not PhaseSessionState.PURSUIT):
            if intent.fields.get("vel_body_down") != 0.:
                raise ValueError("native_vertical_contract_invalid")
            hold = self.prepare_engagement_reference(state)
        return replace(intent, profile_name=self.profile_name, guidance_identity=self.identity, altitude_hold=hold)

    def observe(self, state: AircraftState, *, owner_confirmed: bool, target_confirmed: bool):
        decision = self.phase_owner.observe(state, now=self.clock(), owner_confirmed=owner_confirmed,
                                            target_confirmed=target_confirmed)
        if decision.state is PhaseSessionState.ENDED:
            self.end(decision.reason)
            return decision
        if state.phase not in self.supported_phases:
            return self.end("unsupported_aircraft_phase")
        if self._state is not None and state.sequence <= self._state.sequence:
            return decision
        try:
            self.prepare_engagement_reference(state)
            if self._state is None:
                self._start_phase(state)
            else:
                self._refresh_phase(state)
        except ValueError as error:
            self.end(str(error))
            raise
        self._state = state
        return decision

    def _start_phase(self, state: AircraftState) -> None:
        self.controls.enter_phase(self.identity, state, now=self.clock(),
                                  timeout_s=self.phase_owner.observation_timeout_s,
                                  unrestricted_verified=self._unrestricted_speed_verified)

    def _refresh_phase(self, state: AircraftState) -> None:
        """MC keeps its existing canonical control envelope."""

    def require_state(self) -> AircraftState:
        if self.phase_owner.state is PhaseSessionState.ENDED:
            raise ValueError("guidance_session_ended")
        state = self._state
        if state is None or not state.fresh(self.clock(), self.phase_owner.observation_timeout_s):
            raise ValueError("aircraft_state_stale")
        return state

    def baseline(self) -> CommandIntent:
        """A held zero-translation objective does not authorize target pursuit."""
        state = self.require_state()
        if self.phase is not AirframePhase.MULTICOPTER:
            raise ValueError("aircraft_phase_unknown")
        fields = dict.fromkeys(("vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s"), 0.)
        intent = CommandIntent(self.profile_name, self.control_type, fields, type(self).__name__,
                               reason="phase_confirmation_pending", created_at_monotonic_s=self.clock(),
                               guidance_identity=self.identity)
        return self._multicopter_intent(intent, state)

    def multicopter_intent(self, intent: CommandIntent) -> CommandIntent:
        """Bind an existing follower's calculated fields; apply no pursuit transform."""
        state = self.require_state()
        if (self.phase is not AirframePhase.MULTICOPTER or intent.control_type != "velocity_body_offboard"
                or set(intent.fields) != {"vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s"}):
            raise ValueError("multicopter_command_contract_invalid")
        if self.phase_owner.state is not PhaseSessionState.PURSUIT:
            return self.baseline()
        return self._multicopter_intent(intent, state)

    def end(self, reason: str) -> PhaseDecision:
        decision = self.phase_owner.end(reason)
        self.controls.end()
        self._state = None
        self._engagement_altitude_reference = None
        return decision
