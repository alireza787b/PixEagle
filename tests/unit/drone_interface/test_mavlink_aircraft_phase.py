"""Standard phase observations do not grant a follower or transport authority."""

import pytest

from classes.aircraft_identity import TelemetryAircraftIdentity
from classes.aircraft_state import AircraftKind, AirframePhase, airframe_phase_from_mavlink


def packet(heartbeat, phase_counter, phase=3, *, kind=19, uid=42):
    messages = {
        "HEARTBEAT": {"message": {"mavtype": kind, "autopilot": 12},
                      "status": {"time": {"counter": heartbeat}}},
        "AUTOPILOT_VERSION": {"message": {"uid": uid}},
    }
    if phase_counter is not None:
        messages["EXTENDED_SYS_STATE"] = {
            "message": {"vtol_state": phase},
            "status": {"time": {"counter": phase_counter}},
        }
    return {"vehicles": {"1": {"components": {"1": {"messages": messages}}}}}


def confirmed_owner(*, kind=19):
    owner = TelemetryAircraftIdentity(1, 1, 2.)
    owner.observe(packet(1, 10, kind=kind), now=10.)
    owner.observe(packet(2, 11, kind=kind), now=10.5)
    assert owner.phase_snapshot(connected=True, now=10.5)["fresh"]
    return owner


@pytest.mark.parametrize("raw,expected", [
    (1, AirframePhase.VTOL_TRANSITION), (2, AirframePhase.VTOL_TRANSITION),
    (3, AirframePhase.MULTICOPTER), (4, AirframePhase.FIXED_WING),
    ("MAV_VTOL_STATE_MC", AirframePhase.MULTICOPTER),
    ({"type": "MAV_VTOL_STATE_FW"}, AirframePhase.FIXED_WING),
    ({"type": "MAV_VTOL_STATE_TRANSITION_TO_MC"}, AirframePhase.VTOL_TRANSITION),
    (0, AirframePhase.UNKNOWN), (True, AirframePhase.UNKNOWN),
    (3., AirframePhase.UNKNOWN), (None, AirframePhase.UNKNOWN),
    ("Offboard", AirframePhase.UNKNOWN), ("VTOL_TAILSITTER", AirframePhase.UNKNOWN),
    ("MAV_VTOL_STATE_UNDEFINED", AirframePhase.UNKNOWN),
])
def test_vtol_phase_decodes_only_standard_state(raw, expected):
    assert airframe_phase_from_mavlink(AircraftKind.VTOL, raw) is expected


@pytest.mark.parametrize("kind,phase", [
    (AircraftKind.MULTICOPTER, AirframePhase.MULTICOPTER),
    (AircraftKind.FIXED_WING, AirframePhase.FIXED_WING),
    (AircraftKind.UNKNOWN, AirframePhase.UNKNOWN),
])
def test_native_aircraft_phase_does_not_require_vtol_message(kind, phase):
    assert airframe_phase_from_mavlink(kind) is phase


def test_heartbeat_progress_cannot_confirm_a_cached_vtol_phase():
    owner = TelemetryAircraftIdentity(1, 1, 2.)
    owner.observe(packet(1, 10), now=10.)
    owner.observe(packet(2, 10), now=10.5)
    assert owner.snapshot(connected=True, now=10.5)["fresh"]
    state = owner.phase_snapshot(connected=True, now=10.5)
    assert state["phase"] == "unknown"
    assert state["reason"] == "aircraft_phase_unconfirmed"
    owner.observe(packet(2, 11), now=10.6)
    state = owner.phase_snapshot(connected=True, now=10.6)
    assert state["fresh"] and state["phase"] == "multicopter"
    assert state["source"] == "EXTENDED_SYS_STATE"


def test_phase_expires_independently_of_advancing_heartbeat():
    owner = confirmed_owner()
    generation = owner.phase_snapshot(connected=True, now=10.5)["generation"]
    for count in range(3, 8):
        owner.observe(packet(count, 11), now=10.5 + (count - 2) * .5)
    assert owner.snapshot(connected=True, now=13.)["fresh"]
    state = owner.phase_snapshot(connected=True, now=13.)
    assert not state["fresh"] and state["reason"] == "aircraft_phase_stale"
    assert state["source_age_s"] == 2.5
    assert state["generation"] == generation
    owner.observe(packet(8, 12), now=13.1)
    assert owner.phase_snapshot(connected=True, now=13.1)["fresh"]


def test_advancing_phase_cannot_refresh_stale_aircraft_identity():
    owner = confirmed_owner()
    for count in range(12, 17):
        owner.observe(packet(2, count), now=10.5 + (count - 11) * .5)
    assert not owner.phase_snapshot(connected=True, now=13.)["fresh"]


@pytest.mark.parametrize("kind", [19, 20, 22, 23])
def test_both_transition_directions_preserve_aircraft_kind(kind):
    owner = confirmed_owner(kind=kind)
    previous = owner.phase_snapshot(connected=True, now=10.5)["generation"]
    for index, (wire, phase) in enumerate([
        (1, "vtol_transition"), (4, "fixed_wing"),
        (2, "vtol_transition"), (3, "multicopter"),
    ], start=3):
        now = 10.5 + (index - 2) * .1
        owner.observe(packet(index, index + 9, wire, kind=kind), now=now)
        state = owner.phase_snapshot(connected=True, now=now)
        assert state["fresh"] and state["phase"] == phase
        assert state["generation"] > previous
        assert owner.aircraft_kind is AircraftKind.VTOL
        previous = state["generation"]


def test_changed_payload_without_counter_progress_cannot_confirm_phase():
    owner = confirmed_owner()
    owner.observe(packet(3, 11, 4), now=10.6)
    state = owner.phase_snapshot(connected=True, now=10.6)
    assert not state["fresh"] and state["phase"] == "unknown"
    owner.observe(packet(4, 12, 4), now=10.7)
    assert owner.phase_snapshot(connected=True, now=10.7)["phase"] == "fixed_wing"


@pytest.mark.parametrize("bad_counter", [1, 9, 10])
def test_reordered_phase_reply_preserves_high_watermark(bad_counter):
    owner = confirmed_owner()
    owner.observe(packet(3, bad_counter, 4), now=10.6)
    state = owner.phase_snapshot(connected=True, now=10.6)
    assert not state["fresh"] and state["source_counter"] == 11
    owner.observe(packet(4, bad_counter + 1, 4), now=10.7)
    assert not owner.phase_snapshot(connected=True, now=10.7)["fresh"]
    owner.observe(packet(5, 12, 4), now=10.8)
    assert owner.phase_snapshot(connected=True, now=10.8)["phase"] == "fixed_wing"


@pytest.mark.parametrize("counter,raw", [
    (None, 3), (11, None), (11, 0), (True, 3), (-1, 3),
])
def test_missing_invalid_phase_cannot_be_repaired_by_a_cached_reply(counter, raw):
    owner = confirmed_owner()
    owner.observe(packet(3, counter, raw), now=10.6)
    state = owner.phase_snapshot(connected=True, now=10.6)
    assert not state["fresh"] and state["source_counter"] == 11
    owner.observe(packet(4, 11), now=10.7)
    assert not owner.phase_snapshot(connected=True, now=10.7)["fresh"]
    owner.observe(packet(5, 12), now=10.8)
    assert owner.phase_snapshot(connected=True, now=10.8)["fresh"]


def test_replacement_identity_cannot_relabel_old_phase():
    owner = confirmed_owner()
    old = owner.phase_snapshot(connected=True, now=10.5)
    owner.observe(packet(1, 1, 4, uid=43), now=10.6)
    state = owner.phase_snapshot(connected=True, now=10.6)
    assert not state["fresh"] and state["generation"] != old["generation"]
    owner.observe(packet(2, 2, 4, uid=43), now=10.7)
    state = owner.phase_snapshot(connected=True, now=10.7)
    assert state["fresh"] and state["autopilot_uid"] == "43"
    assert state["connection_generation"] != old["connection_generation"]


def test_disconnect_and_future_receipt_cannot_authorize_a_phase():
    owner = confirmed_owner()
    assert not owner.phase_snapshot(connected=False, now=10.5)["fresh"]
    assert not owner.phase_snapshot(connected=True, now=10.4)["fresh"]
    owner.invalidate("disconnected")
    state = owner.phase_snapshot(connected=True, now=10.6)
    assert not state["fresh"] and state["phase"] == "unknown"
    assert state["source_counter"] is None


@pytest.mark.parametrize("kind,phase", [(1, "fixed_wing"), (2, "multicopter")])
def test_native_phase_freshness_uses_observed_heartbeat(kind, phase):
    owner = TelemetryAircraftIdentity(1, 1, 2.)
    owner.observe(packet(1, None, kind=kind), now=10.)
    assert not owner.phase_snapshot(connected=True, now=10.)["fresh"]
    owner.observe(packet(2, None, kind=kind), now=10.5)
    state = owner.phase_snapshot(connected=True, now=10.5)
    assert state["fresh"] and state["phase"] == phase
    assert state["source"] == "HEARTBEAT"


def test_phase_source_uses_selected_autopilot_route_only():
    owner = confirmed_owner()
    data = packet(3, 12)
    data["vehicles"]["1"]["components"]["191"] = {
        "messages": {"EXTENDED_SYS_STATE": {
            "message": {"vtol_state": 4}, "status": {"time": {"counter": 200}},
        }},
    }
    owner.observe(data, now=10.6)
    assert owner.phase_snapshot(connected=True, now=10.6)["phase"] == "multicopter"
