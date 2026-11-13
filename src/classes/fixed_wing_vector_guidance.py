"""World-ray objectives for native PX4 fixed-wing guidance, not a flight controller.

PX4 owns TECS, turn coordination, actuator authority and the effective envelope.
This module never converts an image/gimbal angle directly into pitch or thrust.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math

from classes.aircraft_state import AircraftState, AirframePhase, GuidanceSessionIdentity, Vector3, finite_number
from classes.command_intent import CommandIntent
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy, UpperSpeedPolicy
from classes.bearing_geometry_policy import BearingGeometryPolicy
from classes.safety_types import AltitudeLimits


@dataclass(frozen=True)
class FixedWingCommand:
    """A complete FW objective. Exactly one native vertical input is finite."""

    course_rad: float
    equivalent_airspeed_m_s: float
    height_rate_m_s: float | None
    altitude_amsl_m: float | None
    upper_speed_policy: UpperSpeedPolicy = UpperSpeedPolicy.PX4_CONFIGURED_MAX

    def __post_init__(self):
        finite_number(self.course_rad, "course")
        if finite_number(self.equivalent_airspeed_m_s, "equivalent_airspeed") <= 0:
            raise ValueError("fixed_wing_speed_not_positive")
        if (self.height_rate_m_s is None) == (self.altitude_amsl_m is None):
            raise ValueError("fixed_wing_vertical_contract_invalid")
        if self.height_rate_m_s is not None:
            finite_number(self.height_rate_m_s, "height_rate")
        if self.altitude_amsl_m is not None:
            finite_number(self.altitude_amsl_m, "altitude_amsl")
        if not isinstance(self.upper_speed_policy, UpperSpeedPolicy):
            raise ValueError("upper_speed_policy_invalid")

    def wire_payload(self) -> dict:
        result = asdict(self)
        result["upper_speed_policy"] = self.upper_speed_policy.value
        return result

    def intent(self, identity: GuidanceSessionIdentity, *, profile_name: str, source: str) -> CommandIntent:
        if self.upper_speed_policy is not UpperSpeedPolicy.PX4_CONFIGURED_MAX:
            # The firmware extension must join this contract before this policy
            # can pass through shared continuity. Never discard its ownership.
            raise ValueError("unrestricted_native_contract_not_qualified")
        fields = {"course_rad": self.course_rad, "equivalent_airspeed_m_s": self.equivalent_airspeed_m_s}
        if self.height_rate_m_s is not None:
            fields["height_rate_m_s"] = self.height_rate_m_s
        else:
            fields["altitude_amsl_m"] = self.altitude_amsl_m
        return CommandIntent(profile_name, "fixed_wing_external", fields, source,
                             guidance_identity=identity)

    @classmethod
    def field_variants(cls) -> dict[str, frozenset[str]]:
        """Return the exact field sets accepted by the native FW contract."""
        common = frozenset({"course_rad", "equivalent_airspeed_m_s"})
        return {
            "height_rate": common | {"height_rate_m_s"},
            "altitude": common | {"altitude_amsl_m"},
        }

    @classmethod
    def from_intent(cls, intent: CommandIntent) -> FixedWingCommand:
        if (intent.control_type != "fixed_wing_external" or intent.guidance_identity is None
                or intent.altitude_hold is not None):
            raise ValueError("native_fixed_wing_intent_invalid")
        fields = intent.fields
        if set(fields) not in cls.field_variants().values():
            raise ValueError("native_fixed_wing_fields_invalid")
        return cls(fields["course_rad"], fields["equivalent_airspeed_m_s"],
                   fields.get("height_rate_m_s"), fields.get("altitude_amsl_m"))


@dataclass(frozen=True)
class FixedWingGuidanceResult:
    command: FixedWingCommand
    geometry_state: str
    limiting_reason: str | None
    speed_source: str
    observed_eas_m_s: float | None


class FixedWingVectorGuidance:
    """Produce feasible navigation objectives from physical-body or NED rays."""

    def __init__(self, *, enable_altitude_control: bool, geometry_policy: BearingGeometryPolicy,
                 policy: FixedWingGuidancePolicy | None = None, unrestricted_capability: bool = False):
        if type(enable_altitude_control) is not bool:
            raise ValueError("altitude_control_invalid")
        if not isinstance(geometry_policy, BearingGeometryPolicy):
            raise ValueError("bearing_geometry_policy_invalid")
        self.enable_altitude_control = enable_altitude_control
        self.geometry_policy = geometry_policy
        self.requested_policy = policy if policy is not None else FixedWingGuidancePolicy()
        if not isinstance(self.requested_policy, FixedWingGuidancePolicy):
            raise ValueError("fixed_wing_guidance_policy_invalid")
        self.policy = self.requested_policy.resolve_native(unrestricted_capability)
        self.policy_reason = ("unrestricted_speed_not_supported"
                              if self.policy != self.requested_policy else None)
        self._unrestricted_verified = unrestricted_capability
        self._identity = None
        self._hold_altitude_amsl = None
        self._last_course = None
        self._vertical = False
        self._rearward_turn_sign = None
        self._altitude_reference_generation = None

    def reset(self) -> None:
        self._identity = None
        self._hold_altitude_amsl = None
        self._last_course = None
        self.reset_target_state()
        self._altitude_reference_generation = None

    def reset_target_state(self) -> None:
        """Forget target classifiers, retaining the last feasible recovery course.

        A validated retarget is not a new flight session or altitude reference.
        Speed controls and recovery deadlines are owned outside this planner.
        """
        self._vertical = False
        self._rearward_turn_sign = None

    def begin_phase(self, identity: GuidanceSessionIdentity, state: AircraftState, *, now: float, timeout_s: float,
                    altitude_reference: AircraftState | None = None) -> None:
        self._require_state(state, now=now, timeout_s=timeout_s)
        if identity.binding != state.binding or state.phase is not AirframePhase.FIXED_WING:
            raise ValueError("guidance_phase_binding_invalid")
        # This historical snapshot supplies only the engagement altitude/reference,
        # never current telemetry. A phase change must not ratchet Hold downward.
        reference = state if altitude_reference is None else altitude_reference
        if reference.binding != state.binding:
            raise ValueError("guidance_phase_binding_invalid")
        if reference.altitude_reference_generation != state.altitude_reference_generation:
            raise ValueError("altitude_reference_changed")
        self.reset()
        self._identity = identity
        self._hold_altitude_amsl = reference.altitude_amsl_m
        self._altitude_reference_generation = reference.altitude_reference_generation

    @staticmethod
    def startup_speed(state: AircraftState, *, now: float, timeout_s: float) -> tuple[float, str]:
        FixedWingVectorGuidance._require_state(state, now=now, timeout_s=timeout_s)
        envelope = state.fixed_wing_envelope
        airspeed = state.airspeed
        if airspeed.fresh(now, timeout_s):
            value, source = airspeed.equivalent_m_s, airspeed.source
        else:
            value, source = envelope.trim_eas_m_s, "px4_trim_reference"
        return min(envelope.maximum_eas_m_s, max(envelope.minimum_eas_m_s, value)), source

    @staticmethod
    def _require_state(state: AircraftState, *, now: float, timeout_s: float) -> None:
        finite_number(now, "guidance_clock")
        if finite_number(timeout_s, "guidance_timeout") <= 0:
            raise ValueError("guidance_timeout_not_positive")
        if not state.fresh(now, timeout_s):
            raise ValueError("aircraft_state_stale")
        if state.rescue_active:
            raise ValueError("aircraft_rescue_active")
        if state.phase is not AirframePhase.FIXED_WING:
            raise ValueError("fixed_wing_phase_required")
        if state.fixed_wing_envelope is None:
            raise ValueError("fixed_wing_envelope_unavailable")

    def calculate(
        self, body_ray: Vector3, state: AircraftState, *, requested_eas_m_s: float,
        identity: GuidanceSessionIdentity, altitude_limits: AltitudeLimits, now: float, timeout_s: float,
    ) -> FixedWingGuidanceResult:
        """Compatibility entry: normalize physical FRD and rotate to NED once."""
        self._require_state(state, now=now, timeout_s=timeout_s)
        ray = state.attitude_body_to_ned.rotate(body_ray.normalized())
        return self.calculate_ned(
            ray, state, frame="ned", requested_eas_m_s=requested_eas_m_s,
            identity=identity, altitude_limits=altitude_limits, now=now, timeout_s=timeout_s,
        )

    def calculate_ned(
        self, ray_ned: Vector3, state: AircraftState, *, frame: str, requested_eas_m_s: float,
        identity: GuidanceSessionIdentity, altitude_limits: AltitudeLimits, now: float, timeout_s: float,
    ) -> FixedWingGuidanceResult:
        """Consume a unit NED ray without rotating it using the current attitude.

        Callers own measurement-time alignment and pursuit authorization. The
        current state still supplies the native envelope and altitude guards.
        """
        self._require_state(state, now=now, timeout_s=timeout_s)
        if frame != "ned":
            raise ValueError("guidance_ray_frame_invalid")
        if (not isinstance(ray_ned, Vector3)
                or not math.isclose(ray_ned.magnitude, 1.0, rel_tol=0.0, abs_tol=1e-9)):
            raise ValueError("guidance_ray_not_unit")
        envelope = state.fixed_wing_envelope
        effective_speed, speed_reason = self.resolve_speed(state, requested_eas_m_s, self.policy.upper_speed_policy,
                                                          self._unrestricted_verified)
        self._require_binding(identity, state)

        ray = ray_ned
        horizontal = ray.horizontal_magnitude
        enter, leave = (self.geometry_policy.vertical_enter_horizontal_norm,
                        self.geometry_policy.vertical_exit_horizontal_norm)
        self._vertical = horizontal < leave if self._vertical else horizontal <= enter
        limiting = speed_reason or self.policy_reason
        if self._vertical:
            course = self._last_course if self._last_course is not None else state.navigation_heading_rad
            geometry = "vertical_path_limited"
            limiting = "fixed_wing_vertical_ray"
        else:
            course = math.atan2(ray.y, ray.x)
            error = math.atan2(math.sin(course - state.navigation_heading_rad),
                               math.cos(course - state.navigation_heading_rad))
            if abs(error) <= math.radians(self.geometry_policy.forward_reentry_bearing_deg):
                self._rearward_turn_sign = None
            elif (self._rearward_turn_sign is None
                  and abs(error) >= math.radians(self.geometry_policy.rearward_entry_bearing_deg)):
                self._rearward_turn_sign = math.copysign(1.0, error)
            if self._rearward_turn_sign is not None:
                # An intermediate course within 100 degrees removes the native
                # shortest-turn ambiguity around +/-pi without commanding bank.
                turn = min(abs(error), math.radians(self.geometry_policy.rearward_entry_bearing_deg))
                course = state.navigation_heading_rad + self._rearward_turn_sign * turn
                geometry = "coordinated_turn"
            else:
                geometry = "forward"
            course = math.atan2(math.sin(course), math.cos(course))
            self._last_course = course

        if self.enable_altitude_control:
            if self._vertical:
                height_rate = -math.copysign(envelope.sink_rate_m_s if ray.z >= 0
                                             else envelope.climb_rate_m_s, ray.z)
            else:
                # This is a ground-track slope, not EAS multiplied by a ray.
                # Wind compensation/energy control stay inside native PX4.
                height_rate = -state.velocity_ned_m_s.horizontal_magnitude * ray.z / horizontal
            height_rate = min(envelope.climb_rate_m_s, max(-envelope.sink_rate_m_s, height_rate))
            height_rate, altitude_reason = self._guard_altitude(height_rate, state, altitude_limits)
            limiting = altitude_reason or limiting
            altitude = None
        else:
            height_rate, altitude = None, self._hold_altitude(state, altitude_limits)
        airspeed = state.airspeed
        available = airspeed.fresh(now, timeout_s)
        return FixedWingGuidanceResult(
            command=FixedWingCommand(course, effective_speed, height_rate, altitude, self.policy.upper_speed_policy),
            geometry_state=geometry, limiting_reason=limiting,
            speed_source=airspeed.source if available else "native_airspeedless",
            observed_eas_m_s=airspeed.equivalent_m_s if available else None,
        )

    @staticmethod
    def resolve_speed(state: AircraftState, requested_eas_m_s: float,
                      upper_speed_policy: UpperSpeedPolicy = UpperSpeedPolicy.PX4_CONFIGURED_MAX,
                      unrestricted_capability: bool = False) -> tuple[float, str | None]:
        envelope = state.fixed_wing_envelope
        if envelope is None:
            raise ValueError("fixed_wing_envelope_unavailable")
        requested = finite_number(requested_eas_m_s, "requested_speed")
        if requested <= 0:
            raise ValueError("fixed_wing_request_not_positive")
        # The native load-dependent floor may rise while turning. Keep the
        # session request intact and report the effective native constraint;
        # never end a valid session merely because its previous request is now
        # below the changing envelope.
        effective_speed = max(requested, envelope.minimum_eas_m_s)
        speed_reason = "native_minimum_speed" if effective_speed > requested else None
        if not isinstance(upper_speed_policy, UpperSpeedPolicy):
            raise ValueError("upper_speed_policy_invalid")
        if upper_speed_policy is UpperSpeedPolicy.NO_UPPER_SPEED_BOUND:
            if unrestricted_capability is not True:
                raise ValueError("unrestricted_speed_not_supported")
        elif effective_speed > envelope.maximum_eas_m_s:
            effective_speed = envelope.maximum_eas_m_s
            speed_reason = "native_maximum_speed"

        return effective_speed, speed_reason

    def _require_binding(self, identity: GuidanceSessionIdentity, state: AircraftState) -> None:
        if self._identity is None or identity != self._identity or state.binding != identity.binding:
            raise ValueError("guidance_phase_binding_changed")
        if self._altitude_reference_generation != state.altitude_reference_generation:
            raise ValueError("altitude_reference_changed")

    def _hold_altitude(self, state: AircraftState, limits: AltitudeLimits) -> float:
        altitude = self._hold_altitude_amsl
        if limits.safety_enabled:
            self._guard_altitude(0.0, state, limits)
            target_relative = altitude - (state.altitude_amsl_m - state.relative_altitude_m)
            if not limits.contains(target_relative):
                raise ValueError("altitude_hold_target_outside_limits")
        return altitude

    def level_command(self, state: AircraftState, *, identity: GuidanceSessionIdentity,
                      requested_eas_m_s: float, altitude_limits: AltitudeLimits,
                      now: float, timeout_s: float) -> FixedWingCommand:
        """Phase-safe baseline without consuming an invented target observation."""
        self._require_state(state, now=now, timeout_s=timeout_s)
        self._require_binding(identity, state)
        speed, _ = self.resolve_speed(state, requested_eas_m_s, self.policy.upper_speed_policy, self._unrestricted_verified)
        if self.enable_altitude_control:
            self._guard_altitude(0., state, altitude_limits)
            height_rate, altitude = 0., None
        else:
            height_rate, altitude = None, self._hold_altitude(state, altitude_limits)
        return FixedWingCommand(self._last_course if self._last_course is not None else state.navigation_heading_rad,
                                speed, height_rate, altitude, self.policy.upper_speed_policy)

    def guard_command(self, command: FixedWingCommand, state: AircraftState, *, identity: GuidanceSessionIdentity,
                      altitude_limits: AltitudeLimits, now: float, timeout_s: float) -> FixedWingCommand:
        """Reapply the same native/altitude envelope after shared continuity blending."""
        self._require_state(state, now=now, timeout_s=timeout_s)
        self._require_binding(identity, state)
        if command.upper_speed_policy is not self.policy.upper_speed_policy:
            raise ValueError("fixed_wing_guidance_policy_changed")
        speed, _ = self.resolve_speed(state, command.equivalent_airspeed_m_s, self.policy.upper_speed_policy,
                                     self._unrestricted_verified)
        if not self.enable_altitude_control:
            if command.height_rate_m_s is not None or command.altitude_amsl_m != self._hold_altitude(state, altitude_limits):
                raise ValueError("fixed_wing_altitude_hold_contract_changed")
            return replace(command, equivalent_airspeed_m_s=speed)
        if command.height_rate_m_s is None:
            raise ValueError("fixed_wing_vertical_path_contract_changed")
        envelope = state.fixed_wing_envelope
        rate = min(envelope.climb_rate_m_s, max(-envelope.sink_rate_m_s, command.height_rate_m_s))
        rate, _ = self._guard_altitude(rate, state, altitude_limits)
        return replace(command, equivalent_airspeed_m_s=speed, height_rate_m_s=rate)

    @staticmethod
    def _guard_altitude(height_rate: float, state: AircraftState,
                        limits: AltitudeLimits) -> tuple[float, str | None]:
        if not limits.safety_enabled:
            return height_rate, None
        altitude = state.relative_altitude_m
        if not limits.contains(altitude):
            raise ValueError("altitude_hard_limit")
        if altitude <= limits.min_altitude + limits.warning_buffer and height_rate < 0:
            return 0.0, "altitude_lower_warning_band"
        if limits.above_maximum(altitude, buffer=limits.warning_buffer, inclusive=True) and height_rate > 0:
            return 0.0, "altitude_upper_warning_band"
        envelope = state.fixed_wing_envelope
        acceleration = envelope.vertical_acceleration_limit_m_s2
        response = envelope.altitude_response_time_s
        if acceleration is None or response is None:
            raise ValueError("native_vertical_response_unavailable")
        # Native settings provide a conservative lookahead, not proof of a
        # physically achieved stopping distance. Both measured vertical motion
        # and the requested path must be considered before reaching the band.
        down = max(0., state.velocity_ned_m_s.z, -height_rate)
        up = max(0., -state.velocity_ned_m_s.z, height_rate)
        downward_margin = down * response + down * down / (2 * acceleration)
        upward_margin = up * response + up * up / (2 * acceleration)
        if altitude - downward_margin <= limits.min_altitude + limits.warning_buffer and height_rate < 0:
            return 0., "altitude_descent_response_limited"
        if limits.above_maximum(altitude + upward_margin, buffer=limits.warning_buffer, inclusive=True) and height_rate > 0:
            return 0., "altitude_climb_response_limited"
        return height_rate, None
