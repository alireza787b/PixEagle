"""Standard source clocks and physical/FW frames; no command or network calls."""

from copy import deepcopy
import math

import pytest

from classes.aircraft_state import AircraftBinding, AircraftKind, AirframePhase, Quaternion
from classes.mavlink_aircraft_state import MavlinkAircraftStateSource, MavlinkMessageProgress, mode_observed_after_request


def packet(counter, message):
    return {"message": message, "status": {"time": {"counter": counter}}}


def messages(counter, *, quaternion=None, kind=2, height_mm=40000):
    q = quaternion or Quaternion.from_euler(.1, .2, .3)
    boot = counter * 100
    return {
        "HEARTBEAT": packet(counter, {"mavtype": kind, "autopilot": 12}),
        "ATTITUDE_QUATERNION": packet(counter, dict(time_boot_ms=boot, q1=q.w, q2=q.x, q3=q.y, q4=q.z)),
        "LOCAL_POSITION_NED": packet(counter, dict(time_boot_ms=boot, x=1., y=2., z=-40., vx=10., vy=2., vz=1.)),
        "GLOBAL_POSITION_INT": packet(counter, dict(time_boot_ms=boot, alt=height_mm + 500000, relative_alt=height_mm)),
        "VFR_HUD": packet(counter, {"airspeed": 15.}),
    }


def context(*, generation="1", phase="multicopter", age=.1):
    return dict(identity={"autopilot_uid": "42", "connection_generation": generation, "fresh": True},
                phase={"phase": phase, "fresh": True, "source_age_s": age, "generation": 1,
                       "source_observed_at_monotonic_s": 10.1},
                kind=AircraftKind.MULTICOPTER)


def confirmed(*, inputs=None, **changes):
    source = MavlinkAircraftStateSource()
    ctx = context(**changes)
    source.observe(messages(1, **(inputs or {})), now=10., **ctx)
    source.observe(messages(2, **(inputs or {})), now=10.1, **ctx)
    return source, ctx


def snapshot(source, ctx, *, now=10.2, binding=None, epoch=None):
    return source.snapshot(binding or AircraftBinding("42", "sdk-1", 1),
                           source_epoch=epoch or source.epoch, identity=ctx["identity"],
                           phase=ctx["phase"], now=now, timeout_s=1.)


def test_standard_observation_preserves_physical_quaternion_units_and_original_receipts():
    source, ctx = confirmed()
    state = snapshot(source, ctx)
    assert state.phase is AirframePhase.MULTICOPTER
    assert state.attitude_body_to_ned == Quaternion.from_euler(.1, .2, .3)
    assert state.navigation_heading_rad == pytest.approx(.3)
    assert state.relative_altitude_m == 40.
    assert state.altitude_amsl_m == 540.
    assert state.velocity_ned_m_s.z == 1.
    assert state.observed_at_monotonic_s == 10.1
    assert state.airspeed.observed_at_monotonic_s == 10.1
    assert state.attitude_timing is None  # MAVLink does not provide DDS estimator sample/reset evidence.
    assert snapshot(source, ctx, now=10.9).observed_at_monotonic_s == 10.1
    assert snapshot(source, ctx, now=10.9) == state
    assert source.local_position().z == -40.


@pytest.mark.parametrize("name", MavlinkAircraftStateSource.REQUIRED)
def test_heartbeat_or_other_message_progress_cannot_refresh_a_cached_pose_component(name):
    source, ctx = confirmed()
    for counter in range(3, 14):
        current = messages(counter)
        current[name] = messages(2)[name]
        source.observe(current, now=10.1 + counter * .1, **ctx)
    assert snapshot(source, ctx, now=11.4) is None


@pytest.mark.parametrize("alter", [
    lambda ctx: ctx["identity"].update(fresh=False),
    lambda ctx: ctx["identity"].update(autopilot_uid="43"),
    lambda ctx: ctx["phase"].update(fresh=False),
    lambda ctx: ctx["phase"].update(generation=2),
    lambda ctx: ctx["phase"].update(source_age_s=1.1),
    lambda ctx: ctx["phase"].update(source_age_s=-.1),
    lambda ctx: ctx["phase"].update(source_age_s=math.nan),
])
def test_stale_mismatched_or_unobserved_source_cannot_create_aircraft_state(alter):
    source, ctx = confirmed()
    alter(ctx)
    assert snapshot(source, ctx) is None


def test_reconnect_does_not_reuse_a_previous_source_epoch_or_its_cached_samples():
    source, ctx = confirmed()
    old_epoch = source.epoch
    ctx = context(generation="2")
    source.observe(messages(1), now=10.2, **ctx)
    assert snapshot(source, ctx) is None
    source.observe(messages(2), now=10.3, **ctx)
    assert snapshot(source, ctx, epoch=old_epoch) is None
    assert snapshot(source, ctx, now=10.4).observed_at_monotonic_s == pytest.approx(10.1)


def test_home_reference_change_invalidates_altitude_reference_without_moving_the_saved_target():
    source, ctx = confirmed()
    original = snapshot(source, ctx)
    data = messages(3)
    data["GLOBAL_POSITION_INT"]["message"]["alt"] += 10000
    source.observe(data, now=10.3, **ctx)
    new = snapshot(source, ctx, now=10.4)
    assert new.altitude_reference_generation > original.altitude_reference_generation
    assert new.relative_altitude_m == original.relative_altitude_m
    assert new.altitude_amsl_m == original.altitude_amsl_m + 10.


@pytest.mark.parametrize("kind", [19, 20, 23, "MAV_TYPE_VTOL_QUADROTOR"])
def test_tailsitter_fw_heading_is_virtual_but_camera_quaternion_remains_physical(kind):
    physical = Quaternion.from_euler(0., -math.pi / 2., .3)
    source = MavlinkAircraftStateSource()
    ctx = context(phase="fixed_wing")
    ctx["kind"] = AircraftKind.VTOL
    for counter in [1, 2]:
        source.observe(messages(counter, quaternion=physical, kind=kind), now=10 + counter * .1, **ctx)
    state = snapshot(source, ctx, now=10.3)
    assert state.is_vtol and state.is_tailsitter
    assert state.navigation_heading_rad == pytest.approx(.3)
    assert state.attitude_body_to_ned == physical


def test_new_transition_is_exposed_without_relabeling_it_as_a_steady_phase():
    source, ctx = confirmed()
    ctx["phase"].update(phase="vtol_transition", generation=2)
    ctx["kind"] = AircraftKind.VTOL
    source.observe(messages(3, kind=22), now=10.3, **ctx)
    assert snapshot(source, ctx, now=10.4).phase is AirframePhase.VTOL_TRANSITION


@pytest.mark.parametrize("field,value", [("relative_alt", 40.), ("alt", math.inf)])
def test_malformed_relative_altitude_is_not_coerced_or_defaulted(field, value):
    source, ctx = confirmed()
    data = messages(3)
    data["GLOBAL_POSITION_INT"]["message"][field] = value
    source.observe(data, now=10.3, **ctx)
    assert snapshot(source, ctx, now=10.4) is None


def test_message_progress_uses_both_counter_and_source_time_without_rewriting_receipts():
    progress = MavlinkMessageProgress(time_field="time_boot_ms")
    first = packet(1, {"time_boot_ms": 100, "value": 1})
    assert not progress.observe(first, 10.)
    second = packet(2, {"time_boot_ms": 200, "value": 2})
    assert progress.observe(second, 10.1)
    saved = progress.sample
    duplicate = deepcopy(second)
    duplicate["status"]["time"]["counter"] = 3
    assert not progress.observe(duplicate, 10.2)
    assert progress.sample == saved
    assert not progress.observe(first, 10.3)
    assert progress.sample is None
    assert not progress.observe(second, 10.4)
    assert progress.sample is None
    assert progress.observe(packet(4, {"time_boot_ms": 300, "value": 3}), 10.5)


def test_mode_confirmation_requires_a_matching_source_and_a_post_request_heartbeat():
    flight = dict(fresh=True, autopilot_uid="42", connection_generation="1", flight_mode=393216,
                  flight_mode_observed_at_monotonic_s=10.)
    kwargs = dict(source_epoch=("42", "1"), expected_mode=393216, requested_at=10.1)
    assert not mode_observed_after_request(flight, **kwargs)
    flight["flight_mode_observed_at_monotonic_s"] = 10.2
    assert mode_observed_after_request(flight, **kwargs)
    flight["connection_generation"] = "2"
    assert not mode_observed_after_request(flight, **kwargs)


def test_airspeed_only_progress_advances_state_without_refreshing_pose_or_phase():
    source, ctx = confirmed()
    old = snapshot(source, ctx)
    data = messages(2)
    data["VFR_HUD"] = packet(3, {"airspeed": 17.})
    source.observe(data, now=10.3, **ctx)
    new = snapshot(source, ctx, now=10.4)
    assert new.sequence > old.sequence
    assert new.observed_at_monotonic_s == old.observed_at_monotonic_s
    assert new.airspeed.equivalent_m_s == 17.
    data.pop("VFR_HUD")
    source.observe(data, now=10.5, **ctx)
    unavailable = snapshot(source, ctx, now=10.6)
    assert not unavailable.airspeed.valid
    source.observe(data, now=10.7, **ctx)
    assert snapshot(source, ctx, now=10.8) == unavailable
