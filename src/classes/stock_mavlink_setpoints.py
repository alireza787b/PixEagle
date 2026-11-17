"""Pure standard-PX4 packet projection for the existing publication scheduler.

These packets neither acquire authority nor create an autonomous resend loop.
The command owner must validate session, phase, freshness and safety at dispatch.
"""

from dataclasses import dataclass
import json
import math

from classes.aircraft_state import Quaternion, Vector3, finite_number, heading_frame_to_ned
from classes.fixed_wing_mavlink_control import FixedWingAttitudeRequest

PX4_OFFBOARD_MODE = 6 << 16
PX4_HOLD_MODE = (4 << 16) | (3 << 24)


@dataclass(frozen=True)
class StockMavlinkPacket:
    message_name: str
    target_system: int
    target_component: int
    fields_json: str

    def sdk_message(self):
        from mavsdk_grpc.mavlink_direct import MavlinkMessage
        # The pinned server supplies its own source address when finalizing.
        return MavlinkMessage(self.message_name, 0, 0, self.target_system, self.target_component, self.fields_json)


def _packet(name, fields, *, system_id, component_id):
    if any(type(value) is not int or not 1 <= value <= 255 for value in (system_id, component_id)):
        raise ValueError("mavlink_target_route_invalid")
    return StockMavlinkPacket(name, system_id, component_id, json.dumps(fields, allow_nan=False, separators=(",", ":")))


def _boot_ms(now):
    value = finite_number(now, "command_clock")
    if value < 0:
        raise ValueError("command_clock_negative")
    return int(value * 1000.) % 2**32


def fixed_wing_attitude_packet(request, *, now, system_id, component_id):
    if not isinstance(request, FixedWingAttitudeRequest):
        raise ValueError("fixed_wing_attitude_request_invalid")
    for name, lower, upper in (("roll_deg", -180., 180.), ("pitch_deg", -90., 90.),
                               ("yaw_deg", -180., 180.), ("thrust", 0., 1.)):
        if not lower <= finite_number(getattr(request, name), name) <= upper:
            raise ValueError("fixed_wing_attitude_domain_invalid")
    q = Quaternion.from_euler(*(math.radians(value) for value in (
        request.roll_deg, request.pitch_deg, request.yaw_deg)))
    return _packet("SET_ATTITUDE_TARGET", dict(
        time_boot_ms=_boot_ms(now), type_mask=7, q=[q.w, q.x, q.y, q.z],
        body_roll_rate=0., body_pitch_rate=0., body_yaw_rate=0., thrust=request.thrust,
    ), system_id=system_id, component_id=component_id)


def multicopter_velocity_packet(fields, *, now, heading_rad, system_id, component_id,
                                hold_down_m=None):
    if (not isinstance(fields, dict)
            or set(fields) != {"vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s"}):
        raise ValueError("multicopter_command_contract_invalid")
    values = {name: finite_number(value, name) for name, value in fields.items()}
    velocity = Vector3(*(values[name] for name in ("vel_body_fwd", "vel_body_right", "vel_body_down")))
    # Ignore position, acceleration and absolute yaw. Keep yaw rate, preserving
    # the existing follower's exact command semantics (deg/s → rad/s once).
    mask = 1 | 2 | 4 | 64 | 128 | 256 | 1024
    frame, down = 8, 0.  # MAV_FRAME_BODY_NED is heading-only for velocity.
    if hold_down_m is not None:
        if velocity.z != 0.:
            raise ValueError("altitude_hold_conflicts_with_vertical_velocity")
        velocity = heading_frame_to_ned(velocity, heading_rad)
        frame, down = 1, finite_number(hold_down_m, "hold_down")
        mask = (mask & ~4) | 32  # Local NED Z position, XY velocity; ignore VZ.
    return _packet("SET_POSITION_TARGET_LOCAL_NED", dict(
        time_boot_ms=_boot_ms(now), coordinate_frame=frame, type_mask=mask,
        x=0., y=0., z=down, vx=velocity.x, vy=velocity.y, vz=velocity.z,
        afx=0., afy=0., afz=0., yaw=0., yaw_rate=math.radians(values["yawspeed_deg_s"]),
    ), system_id=system_id, component_id=component_id)


def offboard_mode_packet(*, system_id, component_id):
    """Standard PX4 DO_SET_MODE; acceptance still requires observed Offboard."""
    return _packet("COMMAND_LONG", dict(
        command=176, confirmation=0, param1=1., param2=6., param3=0.,
        param4=0., param5=0., param6=0., param7=0.,
    ), system_id=system_id, component_id=component_id)


def hold_mode_packet(*, system_id, component_id):
    """One Hold request, with no autonomous retry after a later takeover."""
    return _packet("COMMAND_LONG", dict(
        command=176, confirmation=0, param1=1., param2=4., param3=3.,
        param4=0., param5=0., param6=0., param7=0.,
    ), system_id=system_id, component_id=component_id)
