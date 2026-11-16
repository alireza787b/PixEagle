"""Stock projection of the shared Vector session, phase and control contracts.

This composition creates no command connection, polling, recovery timer or mode
authority. Application admission remains separate from component capabilities.
"""

from dataclasses import dataclass, replace
import time

from classes.aircraft_state import AircraftState, AirframePhase, Vector3
from classes.command_intent import AltitudeHoldReference, CommandIntent
from classes.command_safety import validate_and_clamp_command_values
from classes.fixed_wing_mavlink_control import FixedWingMavlinkVectorControl
from classes.fixed_wing_guidance_policy import UpperSpeedPolicy
from classes.fixed_wing_vector_guidance import FixedWingCommand
from classes.guidance_phase_session import PhaseSessionState
from classes.stock_mavlink_setpoints import fixed_wing_attitude_packet, multicopter_velocity_packet
from classes.vector_guidance_session import VectorGuidanceSession


@dataclass(frozen=True)
class MavlinkGuidanceCapabilities:
    runtime_id: str
    fixed_wing_supported: bool
    multicopter_supported: bool
    multicopter_altitude_hold_supported: bool
    unrestricted_speed_supported: bool

    def __post_init__(self):
        if not isinstance(self.runtime_id, str) or not self.runtime_id:
            raise ValueError("mavlink_guidance_runtime_invalid")
        if any(type(getattr(self, key)) is not bool for key in self.__dataclass_fields__ if key != "runtime_id"):
            raise ValueError("mavlink_guidance_capability_invalid")
        if (self.multicopter_altitude_hold_supported and not self.multicopter_supported
                or self.unrestricted_speed_supported and not self.fixed_wing_supported):
            raise ValueError("mavlink_guidance_capability_inconsistent")

    @property
    def unrestricted_intent_supported(self):
        return self.unrestricted_speed_supported


class MavlinkVectorGuidanceSession(VectorGuidanceSession):
    def __init__(self, identity, capabilities: MavlinkGuidanceCapabilities, *, projection: FixedWingMavlinkVectorControl,
                 clock=time.monotonic, **kwargs):
        if (not isinstance(capabilities, MavlinkGuidanceCapabilities)
                or not isinstance(projection, FixedWingMavlinkVectorControl)):
            raise ValueError("mavlink_vector_projection_invalid")
        if (projection.policy.upper_speed_policy is UpperSpeedPolicy.NO_UPPER_SPEED_BOUND
                and not capabilities.unrestricted_speed_supported):
            raise ValueError("unrestricted_projection_not_qualified")
        super().__init__(identity, capabilities, fixed_wing_strategy=projection.direction, clock=clock, **kwargs)
        self.projection = projection
        self.last_projection = None

    def _synchronize_policy(self):
        control = self.controls.current_control
        if self.phase is AirframePhase.FIXED_WING and control is not None:
            self.projection.use_normal_envelope(not control.override_active)

    def calculate_ned(self, ray, *, frame):
        self._synchronize_policy()
        return super().calculate_ned(ray, frame=frame)

    def baseline(self):
        self._synchronize_policy()
        return super().baseline()

    def end(self, reason):
        decision = super().end(reason)
        self.projection.use_normal_envelope(False)
        self.last_projection = None
        return decision

    def priming_packet(self, observation):
        """Hold the frozen engagement reference before mode acquisition."""
        state = observation.state
        reference = self.prepare_engagement_reference(state)
        route = dict(system_id=observation.system_id, component_id=observation.component_id)
        if state.phase is AirframePhase.FIXED_WING:
            self.fixed_wing.begin_phase(self.identity, state, now=self.clock(),
                timeout_s=self.phase_owner.observation_timeout_s,
                altitude_reference=self._engagement_altitude_reference)
            speed, _ = self.fixed_wing.startup_speed(state, now=self.clock(), timeout_s=self.phase_owner.observation_timeout_s)
            command = self.fixed_wing.level_command(state, identity=self.identity, requested_eas_m_s=speed,
                altitude_limits=self.altitude_limits, now=self.clock(), timeout_s=self.phase_owner.observation_timeout_s)
            request = self.projection.project(command, state, identity=self.identity, altitude_limits=self.altitude_limits,
                now=self.clock(), timeout_s=self.phase_owner.observation_timeout_s)
            return fixed_wing_attitude_packet(request, now=self.clock(), **route)
        if state.phase is not AirframePhase.MULTICOPTER or not isinstance(observation.local_position_ned, Vector3):
            raise ValueError("mavlink_priming_contract_unavailable")
        down = observation.local_position_ned.z - (reference.altitude_amsl_m - state.altitude_amsl_m)
        return multicopter_velocity_packet(dict(vel_body_fwd=0., vel_body_right=0., vel_body_down=0., yawspeed_deg_s=0.),
            now=self.clock(), heading_rad=state.navigation_heading_rad, hold_down_m=down, **route)

    def packet(self, intent: CommandIntent, state: AircraftState, *, system_id, component_id,
               local_position_ned: Vector3 | None = None):
        current = self.require_state()
        self._synchronize_policy()
        self.last_projection = None
        if (not isinstance(intent, CommandIntent) or not isinstance(state, AircraftState)
                or state != current
                or not state.fresh(self.clock(), self.phase_owner.observation_timeout_s)
                or intent.profile_name != self.profile_name or intent.guidance_identity != self.identity
                or intent.control_type != self.control_type):
            raise ValueError("mavlink_guidance_intent_context_changed")
        if self.phase_owner.state is not PhaseSessionState.PURSUIT:
            baseline = self.baseline()
            if intent.fields != baseline.fields or intent.altitude_hold != baseline.altitude_hold:
                raise ValueError("phase_confirmation_pending")
        if self.phase is AirframePhase.FIXED_WING:
            guarded = replace(intent, fields=self.guard_native_fields(intent.fields))
            command = replace(FixedWingCommand.from_intent(guarded), upper_speed_policy=self.fixed_wing.policy.upper_speed_policy)
            request = self.projection.project(command, state, identity=self.identity, altitude_limits=self.altitude_limits,
                                              now=self.clock(), timeout_s=self.phase_owner.observation_timeout_s)
            packet = fixed_wing_attitude_packet(request, now=self.clock(), system_id=system_id, component_id=component_id)
            self.last_projection = request
            return packet
        if self.phase is not AirframePhase.MULTICOPTER or not self.phase_owner.capabilities.multicopter_supported:
            raise ValueError("multicopter_projection_unavailable")
        fields = validate_and_clamp_command_values("velocity_body_offboard", intent.fields, follower_name=self.profile_name)
        hold_down = None
        hold = intent.altitude_hold
        if hold is not None:
            if (not isinstance(hold, AltitudeHoldReference) or not isinstance(local_position_ned, Vector3)
                    or hold.reference_generation != state.altitude_reference_generation
                    or not self.phase_owner.capabilities.multicopter_altitude_hold_supported):
                raise ValueError("mavlink_altitude_reference_unavailable")
            self.altitude_limits.require_hold_target(hold.altitude_amsl_m, current_amsl_m=state.altitude_amsl_m,
                                                    current_relative_m=state.relative_altitude_m)
            hold_down = local_position_ned.z - (hold.altitude_amsl_m - state.altitude_amsl_m)
        elif not self.altitude_control:
            raise ValueError("mavlink_engagement_altitude_hold_required")
        return multicopter_velocity_packet(fields, now=self.clock(), heading_rad=state.navigation_heading_rad,
            hold_down_m=hold_down, system_id=system_id, component_id=component_id)
