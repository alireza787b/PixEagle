"""One phase/strategy binding for the operator-facing Gimbal Vector follower.

This object produces intent only. It owns no publisher, target-loss timer,
camera transform or aircraft controller. MC math stays in the existing follower;
FW objectives use native PX4 navigation control. The application binds each new
generation to its publisher and existing continuity supervisor before submitting.
"""

from dataclasses import replace
import time
from typing import Callable

from classes.aircraft_state import AircraftLayout, AircraftState, AirframePhase, GuidanceSessionIdentity, Vector3, body_ray_to_heading_frame
from classes.airframe_session_controls import AirframeSessionControls
from classes.command_intent import CommandIntent
from classes.fixed_wing_vector_guidance import FixedWingCommand, FixedWingVectorGuidance
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy, UpperSpeedPolicy
from classes.follower_session_controls import SessionControl
from classes.gimbal_guidance import GimbalGuidanceCapabilities, GimbalGuidancePolicy
from classes.guidance_phase_session import GuidancePhaseSession, PhaseSessionState
from classes.native_guidance import NativeCapabilities, NativeTransitionCommand
from classes.safety_types import AltitudeLimits


class GimbalVectorSession:
    def __init__(self, identity: GuidanceSessionIdentity, capabilities: NativeCapabilities, *,
                 multicopter_control: SessionControl, geometry_policy: GimbalGuidancePolicy,
                 altitude_control: bool, altitude_limits: AltitudeLimits, confirmation_s: float,
                 observation_timeout_s: float, transition_timeout_s: float, clock=time.monotonic,
                 fixed_wing_policy: FixedWingGuidancePolicy | None = None,
                 expected_layout: AircraftLayout = AircraftLayout.AUTO):
        self.phase_owner = GuidancePhaseSession(
            identity, capabilities, confirmation_s=confirmation_s,
            observation_timeout_s=observation_timeout_s, transition_timeout_s=transition_timeout_s,
            expected_layout=expected_layout,
        )
        self.controls = AirframeSessionControls.from_multicopter_control(identity, multicopter_control)
        self.fixed_wing = FixedWingVectorGuidance(enable_altitude_control=altitude_control,
                                                geometry_policy=geometry_policy, policy=fixed_wing_policy,
                                                unrestricted_capability=capabilities.unrestricted_speed_supported)
        self.altitude_limits = altitude_limits
        self.clock = clock
        self._state = None
        self._engagement_altitude_reference = None
        self._last_fw_command = None
        self._transition_reference = None
        self.last_guidance = None

    @property
    def identity(self) -> GuidanceSessionIdentity:
        return self.phase_owner.identity

    @property
    def phase(self) -> AirframePhase:
        return self.phase_owner.phase

    @property
    def control_type(self) -> str:
        return {AirframePhase.MULTICOPTER: "velocity_body_offboard",
                AirframePhase.FIXED_WING: "fixed_wing_external",
                AirframePhase.VTOL_TRANSITION: "vtol_transition_external"}.get(self.phase, "unknown")

    def observe(self, state: AircraftState, *, owner_confirmed: bool, target_confirmed: bool):
        decision = self.phase_owner.observe(state, now=self.clock(), owner_confirmed=owner_confirmed,
                                            target_confirmed=target_confirmed)
        if decision.state is PhaseSessionState.ENDED:
            self.end(decision.reason)
            return decision
        if self._state is not None and state.sequence <= self._state.sequence:
            return decision
        try:
            if self._engagement_altitude_reference is None:
                self._engagement_altitude_reference = state
            if state.phase is AirframePhase.VTOL_TRANSITION and self._transition_reference is None:
                previous = self._state
                from_fw = previous is not None and previous.phase is AirframePhase.FIXED_WING
                course = (self._last_fw_command.course_rad if from_fw and self._last_fw_command is not None
                          else (previous or state).navigation_heading_rad)
                control = self.controls.current_control
                envelope = state.fixed_wing_envelope
                if envelope is None:
                    raise ValueError("fixed_wing_envelope_unavailable")
                request = control.value if from_fw and control is not None else envelope.trim_eas_m_s
                speed, _ = self.fixed_wing.resolve_speed(state, request)
                self._transition_reference = NativeTransitionCommand(course, speed)
            if self.controls.identity != self.identity:
                self.controls.enter_phase(self.identity, state, now=self.clock(),
                                          timeout_s=self.phase_owner.observation_timeout_s,
                                          unrestricted_verified=(
                                              self.phase_owner.capabilities.unrestricted_speed_supported
                                              and self.fixed_wing.policy.upper_speed_policy is UpperSpeedPolicy.NO_UPPER_SPEED_BOUND))
                if state.phase is AirframePhase.FIXED_WING:
                    self._last_fw_command = None
                    self.fixed_wing.begin_phase(self.identity, state, now=self.clock(),
                                               timeout_s=self.phase_owner.observation_timeout_s,
                                               altitude_reference=self._engagement_altitude_reference)
            elif state.phase is AirframePhase.FIXED_WING:
                self.controls.refresh_envelope(state, now=self.clock(),
                                               timeout_s=self.phase_owner.observation_timeout_s)
        except ValueError as error:
            self.end(str(error))
            raise
        self._state = state
        if decision.pursuit_allowed:
            self._transition_reference = None
            if state.phase is AirframePhase.MULTICOPTER:
                self._last_fw_command = None
        return decision

    def require_state(self) -> AircraftState:
        if self.phase_owner.state is PhaseSessionState.ENDED:
            raise ValueError("guidance_session_ended")
        state = self._state
        if state is None or not state.fresh(self.clock(), self.phase_owner.observation_timeout_s):
            raise ValueError("aircraft_state_stale")
        return state

    def baseline(self) -> CommandIntent:
        """Native phase-safe objective; this does not authorize target pursuit."""
        state = self.require_state()
        if self.phase is AirframePhase.MULTICOPTER:
            fields = dict.fromkeys(("vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s"), 0.)
        elif self.phase is AirframePhase.FIXED_WING:
            command = self.fixed_wing.level_command(
                state, requested_eas_m_s=self.controls.current_control.value,
                identity=self.identity, altitude_limits=self.altitude_limits, now=self.clock(),
                timeout_s=self.phase_owner.observation_timeout_s,
            )
            return replace(command.intent(self.identity, source=type(self).__name__),
                           reason="phase_confirmation_pending", created_at_monotonic_s=self.clock())
        elif self.phase is AirframePhase.VTOL_TRANSITION:
            reference = self._transition_reference
            if reference is None:
                raise ValueError("transition_reference_unavailable")
            speed, _ = self.fixed_wing.resolve_speed(state, reference.equivalent_airspeed_m_s)
            fields = replace(reference, equivalent_airspeed_m_s=speed).wire_payload()
        else:
            raise ValueError("aircraft_phase_unknown")
        return CommandIntent("gm_velocity_vector", self.control_type, fields, type(self).__name__,
                             reason="native_transition_in_progress" if state.phase is AirframePhase.VTOL_TRANSITION
                             else "phase_confirmation_pending", created_at_monotonic_s=self.clock(),
                             guidance_identity=self.identity)

    def calculate(self, physical_body_ray: Vector3, *, capabilities: GimbalGuidanceCapabilities,
                  multicopter_calculate: Callable[[Vector3], CommandIntent]) -> CommandIntent:
        state = self.require_state()
        if not capabilities.permits_ray(physical_body_ray):
            raise ValueError("provider_geometry_limit")
        if self.phase_owner.state is not PhaseSessionState.PURSUIT:
            return self.baseline()
        if self.phase is AirframePhase.FIXED_WING:
            self.last_guidance = self.fixed_wing.calculate(
                physical_body_ray, state, requested_eas_m_s=self.controls.current_control.value,
                identity=self.identity, altitude_limits=self.altitude_limits, now=self.clock(),
                timeout_s=self.phase_owner.observation_timeout_s,
            )
            self._last_fw_command = self.last_guidance.command
            return replace(self.last_guidance.command.intent(self.identity, source=type(self).__name__),
                           created_at_monotonic_s=self.clock())
        if self.phase is not AirframePhase.MULTICOPTER:
            raise ValueError("aircraft_phase_unknown")
        ray = body_ray_to_heading_frame(physical_body_ray.normalized(), state.attitude_body_to_ned,
                                        state.navigation_heading_rad)
        intent = multicopter_calculate(ray)
        if intent.control_type != "velocity_body_offboard":
            raise ValueError("multicopter_command_contract_invalid")
        return replace(intent, guidance_identity=self.identity)

    def end(self, reason: str) -> None:
        self.phase_owner.end(reason)
        self.controls.end()
        self._state = None
        self._engagement_altitude_reference = None
        self._last_fw_command = None
        self._transition_reference = None
        self.last_guidance = None

    def guard_native_fields(self, fields: dict) -> dict:
        state = self.require_state()
        if self.phase is AirframePhase.VTOL_TRANSITION:
            command = NativeTransitionCommand(**fields)
            speed, _ = self.fixed_wing.resolve_speed(state, command.equivalent_airspeed_m_s)
            return replace(command, equivalent_airspeed_m_s=speed).wire_payload()
        intent = CommandIntent("gm_velocity_vector", self.control_type, dict(fields), type(self).__name__,
                               guidance_identity=self.identity)
        command = self.fixed_wing.guard_command(
            FixedWingCommand.from_intent(intent), state, identity=self.identity,
            altitude_limits=self.altitude_limits, now=self.clock(), timeout_s=self.phase_owner.observation_timeout_s,
        )
        return command.intent(self.identity, source=type(self).__name__).fields
