import pytest

from classes.aircraft_identity import TelemetryAircraftIdentity
from classes.aircraft_state import AircraftKind, aircraft_kind_from_mavlink


@pytest.mark.parametrize("raw,expected", [
    ("MAV_TYPE_QUADROTOR", AircraftKind.MULTICOPTER),
    ("MAV_TYPE_FIXED_WING", AircraftKind.FIXED_WING),
    ("MAV_TYPE_VTOL_TAILSITTER_DUOROTOR", AircraftKind.VTOL),
    ("MAV_TYPE_VTOL_FIXEDROTOR", AircraftKind.VTOL),
    ("MAV_TYPE_GENERIC", AircraftKind.UNKNOWN),
])
def test_actual_rest_heartbeat_separates_message_name_and_aircraft_type(raw, expected):
    message = {"type": "HEARTBEAT", "mavtype": {"type": raw},
               "autopilot": {"type": "MAV_AUTOPILOT_PX4"}, "custom_mode": 50593792,
               "base_mode": "MAV_MODE_FLAG_STABILIZE_ENABLED | MAV_MODE_FLAG_CUSTOM_MODE_ENABLED"}
    assert aircraft_kind_from_mavlink(message) is expected


def test_malformed_rest_type_cannot_fall_back_to_another_type_field():
    assert aircraft_kind_from_mavlink({"mavtype": None, "type": 19}) is AircraftKind.UNKNOWN


@pytest.mark.parametrize("raw,expected", [
    (1, AircraftKind.FIXED_WING), (2, AircraftKind.MULTICOPTER), (43, AircraftKind.MULTICOPTER),
    (20, AircraftKind.VTOL), (22, AircraftKind.VTOL), (47, AircraftKind.VTOL),
    ({"type": "MAV_TYPE_VTOL_TAILSITTER_QUADROTOR"}, AircraftKind.VTOL),
    ({"type": {"type": "MAV_TYPE_VTOL_TAILSITTER_QUADROTOR"}, "autopilot": 12}, AircraftKind.VTOL),
    ({"mavpackettype": "HEARTBEAT", "type": 1, "autopilot": 12}, AircraftKind.FIXED_WING),
    ("MAV_TYPE_VTOL_QUADROTOR", AircraftKind.VTOL), ("MAV_TYPE_QUADROTOR", AircraftKind.MULTICOPTER),
    (True, AircraftKind.UNKNOWN), (1., AircraftKind.UNKNOWN), (None, AircraftKind.UNKNOWN),
    ("gm_velocity_vector", AircraftKind.UNKNOWN), ("Offboard", AircraftKind.UNKNOWN),
    ("MAV_TYPE_CAMERA", AircraftKind.UNKNOWN), (255, AircraftKind.UNKNOWN),
])
def test_observed_aircraft_kind_uses_wire_type_and_does_not_guess_phase(raw, expected):
    assert aircraft_kind_from_mavlink(raw) is expected


def payload(kind, counter):
    return {"vehicles": {"1": {"components": {"1": {"messages": {
        "HEARTBEAT": {"message": {"type": "HEARTBEAT", "mavtype": kind, "autopilot": 12},
                      "status": {"time": {"counter": counter}}},
        "AUTOPILOT_VERSION": {"message": {"uid": 42}},
    }}}}}}


def test_aircraft_kind_changes_require_fresh_identity_confirmation():
    owner = TelemetryAircraftIdentity(1, 1, 2.)
    owner.observe(payload(2, 1), now=10.)
    owner.observe(payload(2, 2), now=10.1)
    assert owner.aircraft_kind is AircraftKind.MULTICOPTER
    assert owner.snapshot(connected=True, now=10.2)["fresh"]
    generation = owner.generation
    owner.observe(payload(20, 3), now=10.3)
    assert owner.aircraft_kind is AircraftKind.VTOL
    assert owner.generation > generation
    assert not owner.snapshot(connected=True, now=10.3)["fresh"]
    owner.observe(payload(20, 4), now=10.4)
    assert owner.snapshot(connected=True, now=10.4)["fresh"]
    owner.invalidate("disconnected")
    assert owner.aircraft_kind is AircraftKind.UNKNOWN
