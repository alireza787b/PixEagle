"""Wire projection of already authorized intent, without starting a sender."""

from dataclasses import replace
import json
import math

import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.fixed_wing_mavlink_control import FixedWingAttitudeRequest
from classes.stock_mavlink_setpoints import (
    fixed_wing_attitude_packet, hold_mode_packet, multicopter_velocity_packet, offboard_mode_packet,
)


def request(**changes):
    return replace(FixedWingAttitudeRequest(10., -60., 20., .4, 30., 30., 22., "sensor", "forward", None), **changes)


def fields(**changes):
    return dict(vel_body_fwd=2., vel_body_right=1., vel_body_down=0., yawspeed_deg_s=30.) | changes


def test_fw_virtual_attitude_is_not_rotated_for_a_tailsitter_at_the_wire_boundary():
    packet = fixed_wing_attitude_packet(request(), now=10., system_id=42, component_id=1)
    wire = json.loads(packet.fields_json)
    assert packet.message_name == "SET_ATTITUDE_TARGET"
    assert packet.target_system == 42 and packet.target_component == 1
    assert wire["type_mask"] == 7  # Ignore all rates, use attitude + scalar thrust.
    assert wire["thrust"] == .4
    actual = Quaternion(*wire["q"]).rotate(Vector3(1., 0., 0.))
    expected = Quaternion.from_euler(math.radians(10), math.radians(-60), math.radians(20)).rotate(Vector3(1., 0., 0.))
    assert actual == expected
    sdk = packet.sdk_message()
    assert sdk.target_system_id == 42 and sdk.target_component_id == 1
    assert sdk.fields_json == packet.fields_json


@pytest.mark.parametrize("change", [dict(pitch_deg=-91), dict(roll_deg=181), dict(yaw_deg=181),
                                    dict(thrust=1.1), dict(thrust=-.1), dict(thrust=True), dict(pitch_deg=math.nan)])
def test_invalid_fw_packet_never_reaches_serialization(change):
    with pytest.raises(ValueError):
        fixed_wing_attitude_packet(request(**change), now=10., system_id=1, component_id=1)


def test_existing_mc_heading_velocity_and_yaw_rate_semantics_are_preserved():
    packet = multicopter_velocity_packet(fields(vel_body_down=.5), now=10., heading_rad=.5,
                                          system_id=1, component_id=1)
    wire = json.loads(packet.fields_json)
    assert wire["coordinate_frame"] == 8
    assert wire["type_mask"] == 1479
    assert (wire["vx"], wire["vy"], wire["vz"]) == (2., 1., .5)
    assert wire["yaw_rate"] == pytest.approx(math.pi / 6.)
    assert wire["type_mask"] & 1024 and not wire["type_mask"] & 2048


def test_mc_altitude_hold_uses_position_z_with_xy_velocity_not_zero_vertical_velocity():
    packet = multicopter_velocity_packet(fields(), now=10., heading_rad=math.pi/2.,
                                          hold_down_m=-40., system_id=1, component_id=1)
    wire = json.loads(packet.fields_json)
    assert wire["coordinate_frame"] == 1
    assert wire["type_mask"] == 1507
    assert wire["z"] == -40.
    assert wire["vx"] == pytest.approx(-1.)
    assert wire["vy"] == pytest.approx(2.)
    assert not wire["type_mask"] & 4
    assert wire["type_mask"] & 32


@pytest.mark.parametrize("change", [dict(vel_body_fwd=True), dict(vel_body_right=math.inf),
                                    dict(yawspeed_deg_s=math.nan)])
def test_invalid_mc_values_are_not_coerced(change):
    with pytest.raises(ValueError):
        multicopter_velocity_packet(fields(**change), now=10., heading_rad=0., system_id=1, component_id=1)


def test_altitude_hold_cannot_silently_drop_an_enabled_descent_command():
    with pytest.raises(ValueError, match="conflicts"):
        multicopter_velocity_packet(fields(vel_body_down=1.), now=10., heading_rad=0.,
                                     hold_down_m=-40., system_id=1, component_id=1)


@pytest.mark.parametrize("system,component", [(0, 1), (1, 0), (256, 1), (1, True), (1., 1)])
def test_target_route_never_defaults_to_broadcast(system, component):
    with pytest.raises(ValueError, match="route"):
        offboard_mode_packet(system_id=system, component_id=component)


def test_start_packet_is_standard_px4_mode_request_without_side_effect_or_authority_claim():
    packet = offboard_mode_packet(system_id=42, component_id=1)
    wire = json.loads(packet.fields_json)
    assert packet.message_name == "COMMAND_LONG"
    assert wire["command"] == 176
    assert (wire["param1"], wire["param2"], wire["param3"]) == (1., 6., 0.)


def test_wire_clock_wrap_does_not_reset_the_command_owners_monotonic_clock():
    packet = fixed_wing_attitude_packet(request(), now=2**32 / 1000. + .5, system_id=1, component_id=1)
    assert json.loads(packet.fields_json)["time_boot_ms"] == 500


def test_hold_packet_is_one_standard_mode_request_without_ack_or_ownership_claim():
    packet = hold_mode_packet(system_id=42, component_id=1)
    wire = json.loads(packet.fields_json)
    assert packet.message_name == "COMMAND_LONG"
    assert wire["command"] == 176 and wire["confirmation"] == 0
    assert (wire["param1"], wire["param2"], wire["param3"]) == (1., 4., 3.)
