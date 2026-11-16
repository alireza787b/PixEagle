"""Vector pursuit strategies over the shared native phase/session owner."""

from dataclasses import replace
import time
from typing import Callable

from classes.aircraft_state import AircraftLayout, AircraftState, AirframePhase, GuidanceSessionIdentity, Vector3, body_ray_to_heading_frame
from classes.airframe_session_controls import AirframeSessionControls
from classes.bearing_geometry_policy import BearingGeometryPolicy
from classes.command_intent import CommandIntent
from classes.fixed_wing_vector_guidance import FixedWingCommand, FixedWingVectorGuidance
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy, UpperSpeedPolicy
from classes.gimbal_guidance import GimbalObservationLimits
from classes.guidance_phase_session import PhaseDecision, PhaseSessionState
from classes.guidance_phase_session import GuidanceCapabilities
from classes.phase_guidance_session import PhaseGuidanceSession
from classes.safety_types import AltitudeLimits


class VectorGuidanceSession(PhaseGuidanceSession):
    def __init__(self, identity: GuidanceSessionIdentity, capabilities: GuidanceCapabilities, *,
                 profile_name: str, controls: AirframeSessionControls,
                 supported_phases: frozenset[AirframePhase], geometry_policy: BearingGeometryPolicy,
                 altitude_control: bool, altitude_limits: AltitudeLimits, confirmation_s: float,
                 observation_timeout_s: float, clock=time.monotonic,
                 fixed_wing_policy: FixedWingGuidancePolicy | None = None,
                 expected_layout: AircraftLayout = AircraftLayout.AUTO, initial_phase: AirframePhase | None = None,
                 fixed_wing_strategy: FixedWingVectorGuidance | None = None):
        super().__init__(identity, capabilities, profile_name=profile_name, controls=controls,
                         supported_phases=supported_phases, altitude_control=altitude_control,
                         altitude_limits=altitude_limits, confirmation_s=confirmation_s,
                         observation_timeout_s=observation_timeout_s, clock=clock,
                         expected_layout=expected_layout, initial_phase=initial_phase)
        if fixed_wing_strategy is not None and (not isinstance(fixed_wing_strategy, FixedWingVectorGuidance)
                or fixed_wing_strategy.enable_altitude_control is not altitude_control):
            raise ValueError("fixed_wing_strategy_contract_invalid")
        self.fixed_wing = fixed_wing_strategy or FixedWingVectorGuidance(enable_altitude_control=altitude_control,
                                                geometry_policy=geometry_policy, policy=fixed_wing_policy,
                                                unrestricted_capability=capabilities.unrestricted_speed_supported)
        self.last_guidance = None

    @property
    def altitude_control(self) -> bool:
        return self.fixed_wing.enable_altitude_control

    @property
    def control_type(self) -> str:
        return {AirframePhase.MULTICOPTER: "velocity_body_offboard",
                AirframePhase.FIXED_WING: "fixed_wing_external"}.get(self.phase, "unknown")

    def _start_phase(self, state: AircraftState) -> None:
        self._unrestricted_speed_verified = (self.phase_owner.capabilities.unrestricted_speed_supported
            and self.fixed_wing.policy.upper_speed_policy is UpperSpeedPolicy.NO_UPPER_SPEED_BOUND)
        super()._start_phase(state)
        if state.phase is AirframePhase.FIXED_WING:
            self.fixed_wing.begin_phase(self.identity, state, now=self.clock(),
                                       timeout_s=self.phase_owner.observation_timeout_s,
                                       altitude_reference=self._engagement_altitude_reference)

    def _refresh_phase(self, state: AircraftState) -> None:
        if state.phase is AirframePhase.FIXED_WING:
            self.controls.refresh_envelope(state, now=self.clock(),
                                          timeout_s=self.phase_owner.observation_timeout_s)

    def baseline(self) -> CommandIntent:
        if self.phase is not AirframePhase.FIXED_WING:
            return super().baseline()
        state = self.require_state()
        command = self.fixed_wing.level_command(
            state, requested_eas_m_s=self.controls.current_control.value,
            identity=self.identity, altitude_limits=self.altitude_limits, now=self.clock(),
            timeout_s=self.phase_owner.observation_timeout_s,
        )
        return replace(self._command_intent(command),
                       reason="phase_confirmation_pending", created_at_monotonic_s=self.clock())

    def calculate(self, physical_body_ray: Vector3, *, observation_limits: GimbalObservationLimits,
                  multicopter_calculate: Callable[[Vector3], CommandIntent]) -> CommandIntent:
        state = self.require_state()
        if not observation_limits.permits_ray(physical_body_ray):
            raise ValueError("gimbal_observation_limit")
        if self.phase_owner.state is not PhaseSessionState.PURSUIT:
            return self.baseline()
        if self.phase is AirframePhase.FIXED_WING:
            result = self.fixed_wing.calculate(
                physical_body_ray, state, requested_eas_m_s=self.controls.current_control.value,
                identity=self.identity, altitude_limits=self.altitude_limits, now=self.clock(),
                timeout_s=self.phase_owner.observation_timeout_s,
            )
            return self._fixed_wing_intent(result)
        if self.phase is not AirframePhase.MULTICOPTER:
            raise ValueError("aircraft_phase_unknown")
        ray = body_ray_to_heading_frame(physical_body_ray.normalized(), state.attitude_body_to_ned,
                                        state.navigation_heading_rad)
        intent = multicopter_calculate(ray)
        if intent.control_type != "velocity_body_offboard":
            raise ValueError("multicopter_command_contract_invalid")
        return self._multicopter_intent(intent, state)

    def calculate_ned(self, ray: Vector3, *, frame: str) -> CommandIntent:
        """Accept an already associated world ray; never infer camera/attitude timing."""
        state = self.require_state()
        if self.phase is not AirframePhase.FIXED_WING:
            raise ValueError("fixed_wing_phase_required")
        if self.phase_owner.state is not PhaseSessionState.PURSUIT:
            return self.baseline()
        result = self.fixed_wing.calculate_ned(
            ray, state, frame=frame, requested_eas_m_s=self.controls.current_control.value,
            identity=self.identity, altitude_limits=self.altitude_limits, now=self.clock(),
            timeout_s=self.phase_owner.observation_timeout_s,
        )
        return self._fixed_wing_intent(result)

    def _fixed_wing_intent(self, result) -> CommandIntent:
        self.last_guidance = result
        return replace(self._command_intent(result.command),
                       created_at_monotonic_s=self.clock())

    def _command_intent(self, command):
        return command.intent(self.identity, profile_name=self.profile_name, source=type(self).__name__,
            allow_unrestricted=getattr(self.phase_owner.capabilities, "unrestricted_intent_supported", False) is True)

    def reset_target_state(self) -> None:
        """A new target clears geometry history without renewing session authority."""
        self.require_state()
        self.fixed_wing.reset_target_state()
        self.last_guidance = None

    def end(self, reason: str) -> PhaseDecision:
        decision = super().end(reason)
        self.fixed_wing.reset()
        self.last_guidance = None
        return decision

    def guard_native_fields(self, fields: dict) -> dict:
        state = self.require_state()
        intent = CommandIntent(self.profile_name, self.control_type, dict(fields), type(self).__name__,
                               guidance_identity=self.identity)
        command = FixedWingCommand.from_intent(intent)
        if getattr(self.phase_owner.capabilities, "unrestricted_intent_supported", False) is True:
            command = replace(command, upper_speed_policy=self.fixed_wing.policy.upper_speed_policy)
        control = self.controls.current_control
        if control is None:
            raise ValueError("session_control_unavailable")
        # Retained recovery/blended commands cannot undo an acknowledged
        # reduction. PX4's native resolver still owns the dynamic speed floor.
        command = replace(command, equivalent_airspeed_m_s=min(command.equivalent_airspeed_m_s, control.value))
        command = self.fixed_wing.guard_command(
            command, state, identity=self.identity,
            altitude_limits=self.altitude_limits, now=self.clock(), timeout_s=self.phase_owner.observation_timeout_s,
        )
        return self._command_intent(command).fields
