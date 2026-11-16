"""Experimental MAVLink projection of shared FW ray/speed guidance.

This component does not acquire authority, publish, or advertise live support.
PX4 retains attitude/rate control. Unlike the native FW interface, explicit
attitude/thrust requires this companion speed/path controller; it is not TECS.
"""

from dataclasses import dataclass
import math

from classes.aircraft_state import (
    AircraftState, FixedWingEnvelope, GuidanceSessionIdentity, Vector3, finite_number, fixed_wing_control_attitude,
)
from classes.bearing_geometry_policy import BearingGeometryPolicy
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy, UpperSpeedPolicy
from classes.fixed_wing_vector_guidance import FixedWingCommand, FixedWingVectorGuidance
from classes.safety_types import AltitudeLimits


FIXED_WING_MAVLINK_PARAMETERS = (
    "FW_AIRSPD_MIN", "FW_AIRSPD_TRIM", "FW_AIRSPD_MAX", "FW_THR_MIN", "FW_THR_TRIM", "FW_THR_MAX",
    "FW_P_LIM_MIN", "FW_P_LIM_MAX", "FW_R_LIM", "FW_T_CLMB_R_SP", "FW_T_SINK_R_SP", "FW_T_VERT_ACC", "FW_T_ALT_TC",
)


def resolve_mavlink_configuration(parameters, *, revision, lookahead_m):
    """Derive control/envelope values from one aircraft parameter snapshot.

    This is not a measured load-dependent minimum or a copy of PX4's performance
    model. No local airframe defaults substitute for missing aircraft limits.
    """
    try:
        p = {name: finite_number(parameters[name], name) for name in FIXED_WING_MAVLINK_PARAMETERS}
    except (KeyError, TypeError) as error:
        raise ValueError("fixed_wing_parameters_incomplete") from error
    envelope = FixedWingEnvelope(p["FW_AIRSPD_MIN"], p["FW_AIRSPD_TRIM"], p["FW_AIRSPD_MAX"],
        p["FW_T_CLMB_R_SP"], p["FW_T_SINK_R_SP"], math.radians(p["FW_R_LIM"]),
        "stock_px4_parameter_snapshot", revision, p["FW_T_VERT_ACC"], p["FW_T_ALT_TC"])
    tuning = FixedWingMavlinkTuning(lookahead_m, 1. / envelope.trim_eas_m_s,
        p["FW_THR_MIN"], p["FW_THR_TRIM"], p["FW_THR_MAX"], math.radians(p["FW_P_LIM_MIN"]),
        math.radians(p["FW_P_LIM_MAX"]), p["FW_T_ALT_TC"])
    return envelope, tuning


@dataclass(frozen=True)
class FixedWingMavlinkTuning:
    """Explicit resolved aircraft/controller values; no second parameter store."""

    lookahead_m: float
    speed_gain_per_m_s: float
    throttle_min: float
    throttle_trim: float
    throttle_max: float
    pitch_min_rad: float
    pitch_max_rad: float
    altitude_time_constant_s: float

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            finite_number(getattr(self, name), name)
        if (self.lookahead_m <= 0 or self.speed_gain_per_m_s <= 0 or self.altitude_time_constant_s <= 0
                or not 0 <= self.throttle_min <= self.throttle_trim <= self.throttle_max <= 1
                or not -math.pi / 2 < self.pitch_min_rad < self.pitch_max_rad < math.pi / 2):
            raise ValueError("fixed_wing_mavlink_tuning_invalid")


@dataclass(frozen=True)
class FixedWingAttitudeRequest:
    """PX4 FW virtual attitude frame, including tailsitters; thrust is normalized."""

    roll_deg: float
    pitch_deg: float
    yaw_deg: float
    thrust: float
    requested_speed_m_s: float
    effective_speed_m_s: float
    observed_speed_m_s: float
    speed_basis: str
    geometry_state: str
    limiting_reason: str | None


class FixedWingMavlinkVectorControl:
    def __init__(self, *, tuning: FixedWingMavlinkTuning, geometry: BearingGeometryPolicy,
                 policy: FixedWingGuidancePolicy, enable_altitude_control: bool):
        if not isinstance(tuning, FixedWingMavlinkTuning) or not isinstance(policy, FixedWingGuidancePolicy):
            raise ValueError("fixed_wing_mavlink_policy_invalid")
        self.tuning = tuning
        self.configured_policy = policy
        self.policy = policy
        unbounded = policy.upper_speed_policy is UpperSpeedPolicy.NO_UPPER_SPEED_BOUND
        self.direction = FixedWingVectorGuidance(
            enable_altitude_control=enable_altitude_control, geometry_policy=geometry, policy=policy,
            unrestricted_capability=unbounded, vertical_limits_enabled=not unbounded, path_speed_basis="magnitude",
        )

    def begin(self, identity: GuidanceSessionIdentity, state: AircraftState, *, now: float, timeout_s: float):
        self.direction.begin_phase(identity, state, now=now, timeout_s=timeout_s)

    def reset(self):
        self.direction.reset()
        self.use_normal_envelope(False)

    def use_normal_envelope(self, normal: bool):
        """Session Restore changes the effective policy, never saved settings."""
        if type(normal) is not bool:
            raise ValueError("fixed_wing_normal_envelope_invalid")
        policy = FixedWingGuidancePolicy() if normal else self.configured_policy
        self.policy = policy
        self.direction.policy = policy
        self.direction.vertical_limits_enabled = policy.upper_speed_policy is not UpperSpeedPolicy.NO_UPPER_SPEED_BOUND

    @staticmethod
    def speed_feedback(state: AircraftState, *, now: float, timeout_s: float) -> tuple[float, str]:
        if state.airspeed.fresh(now, timeout_s):
            return state.airspeed.equivalent_m_s, state.airspeed.source
        # This is explicitly a navigation-speed proxy, never measured airspeed
        # or evidence that the aircraft has a known aerodynamic stall margin.
        return state.velocity_ned_m_s.magnitude, "ground_speed_proxy"

    def calculate(self, ray_ned: Vector3, state: AircraftState, *, identity: GuidanceSessionIdentity,
                  requested_speed_m_s: float, altitude_limits: AltitudeLimits,
                  now: float, timeout_s: float) -> FixedWingAttitudeRequest:
        if not isinstance(ray_ned, Vector3):
            raise ValueError("guidance_ray_not_unit")
        result = self.direction.calculate_ned(ray_ned.normalized(), state, frame="ned", identity=identity,
            requested_eas_m_s=requested_speed_m_s, altitude_limits=altitude_limits, now=now, timeout_s=timeout_s)
        return self.project(result.command, state, identity=identity, altitude_limits=altitude_limits,
            now=now, timeout_s=timeout_s, geometry=result.geometry_state, requested_speed_m_s=requested_speed_m_s,
            limiting_reason=result.limiting_reason)

    def project(self, command: FixedWingCommand, state: AircraftState, *, identity: GuidanceSessionIdentity,
                altitude_limits: AltitudeLimits, now: float, timeout_s: float,
                geometry="flight_path", requested_speed_m_s=None, limiting_reason=None) -> FixedWingAttitudeRequest:
        """Project a shared nominal/recovery objective at the final boundary."""
        self.direction.require_state(state, now=now, timeout_s=timeout_s)
        self.direction.require_binding(identity, state)
        if not isinstance(command, FixedWingCommand):
            raise ValueError("fixed_wing_command_contract_invalid")
        command = self.direction.guard_command(command, state, identity=identity,
            altitude_limits=altitude_limits, now=now, timeout_s=timeout_s)
        course = command.course_rad
        envelope = state.fixed_wing_envelope
        unbounded = self.policy.upper_speed_policy is UpperSpeedPolicy.NO_UPPER_SPEED_BOUND
        requested = finite_number(command.equivalent_airspeed_m_s if requested_speed_m_s is None
                                  else requested_speed_m_s, "requested_speed")
        speed, limiting = FixedWingVectorGuidance.resolve_speed(
            state, requested, self.policy.upper_speed_policy, unrestricted_capability=unbounded,
        )
        limiting = limiting_reason or limiting
        observed, speed_basis = self.speed_feedback(state, now=now, timeout_s=timeout_s)
        velocity = state.velocity_ned_m_s
        horizontal = velocity.horizontal_magnitude
        measured_path = math.atan2(-velocity.z, horizontal)
        if self.direction.enable_altitude_control:
            height_rate = command.height_rate_m_s
        else:
            height_rate = (command.altitude_amsl_m - state.altitude_amsl_m) / self.tuning.altitude_time_constant_s
            height_rate = min(envelope.climb_rate_m_s, max(-envelope.sink_rate_m_s, height_rate))
        height_rate, altitude_reason = self.direction.guard_altitude(height_rate, state, altitude_limits)
        limiting = altitude_reason or limiting
        path = math.asin(max(-1., min(1., height_rate / max(velocity.magnitude, envelope.minimum_eas_m_s))))

        # Give climbing authority back continuously between native minimum and
        # trim. A speed deficit reduces climb rather than requesting a slower FW.
        if path > 0:
            margin = max(0., observed - envelope.minimum_eas_m_s)
            span = envelope.trim_eas_m_s - envelope.minimum_eas_m_s
            authority = min(1., margin / span) if span > 0 else float(margin > 0)
            if authority < 1.:
                path *= authority
                limiting = "climb_speed_priority"

        control_attitude = fixed_wing_control_attitude(state.attitude_body_to_ned,
                                                       is_tailsitter=state.is_tailsitter)
        forward = control_attitude.rotate(Vector3(1., 0., 0.))
        pitch = math.atan2(-forward.z, forward.horizontal_magnitude) + path - measured_path
        # Euler pitch has a geometric domain, even when the operational pitch
        # envelope is unrestricted. This is not an arbitrary dive-angle limit.
        pitch = max(-math.pi / 2, min(math.pi / 2, pitch))
        if not unbounded:
            bounded_pitch = max(self.tuning.pitch_min_rad, min(self.tuning.pitch_max_rad, pitch))
            if bounded_pitch != pitch:
                limiting = limiting or "configured_pitch_limit"
            pitch = bounded_pitch
        course_observable = horizontal > velocity.magnitude * self.direction.geometry_policy.vertical_enter_horizontal_norm
        current_course = math.atan2(velocity.y, velocity.x) if course_observable else state.navigation_heading_rad
        error = math.atan2(math.sin(course - current_course), math.cos(course - current_course))
        acceleration = observed * (observed * (2 * math.sin(error) / self.tuning.lookahead_m))
        bank = max(-envelope.bank_limit_rad, min(envelope.bank_limit_rad, math.atan2(acceleration, 9.80665)))
        thrust = self.tuning.throttle_trim + self.tuning.speed_gain_per_m_s * (speed - observed)
        if observed <= envelope.minimum_eas_m_s:
            thrust = self.tuning.throttle_max
            limiting = "underspeed_recovery"
        if path < 0 and self.policy.min_dive_throttle is not None:
            thrust = max(thrust, self.policy.min_dive_throttle)
        thrust = max(self.tuning.throttle_min, min(self.tuning.throttle_max, thrust))
        # Course feedback preserves a required crab angle rather than forcing
        # the nose onto the ground-track bearing in crosswind.
        heading = math.atan2(math.sin(state.navigation_heading_rad + error),
                             math.cos(state.navigation_heading_rad + error))
        return FixedWingAttitudeRequest(
            math.degrees(bank), math.degrees(pitch), math.degrees(heading), thrust,
            requested, speed, observed, speed_basis, geometry, limiting,
        )
