"""Independent observations and physical/heading frame boundary regressions."""

from dataclasses import FrozenInstanceError, asdict, replace
import math

import pytest

from classes.aircraft_state import (
    AircraftBinding, AircraftState, AircraftStateOwner, AttitudeTiming, AirframePhase,
    AirspeedObservation, FixedWingEnvelope, Quaternion, Vector3, ned_to_heading_frame,
)
from classes.gimbal_geometry import body_line_of_sight
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target


def aircraft_state(**changes):
    values = dict(
        binding=AircraftBinding("aircraft-a", "connection-1", 1), sequence=1,
        source="px4_external_mode", observed_at_monotonic_s=100.0,
        phase=AirframePhase.FIXED_WING, is_vtol=False, is_tailsitter=False,
        rescue_active=False, attitude_body_to_ned=Quaternion(1.0, 0.0, 0.0, 0.0),
        velocity_ned_m_s=Vector3(20.0, 0.0, 0.0), relative_altitude_m=50.0,
        altitude_amsl_m=550.0, navigation_heading_rad=0.0,
        airspeed=AirspeedObservation("sensor", 20.0, 21.0, 100.0, True),
        fixed_wing_envelope=FixedWingEnvelope(12, 18, 30, 4, 5, math.radians(35), "px4", "params-1", 2., 2.),
    )
    return AircraftState(**(values | changes))


def test_connection_epoch_and_source_progress_cannot_be_refreshed_by_polling():
    clock = [100.0]
    owner = AircraftStateOwner(clock=lambda: clock[0])
    state = aircraft_state()
    assert not owner.commit(state)
    owner.bind(state.binding)
    assert owner.commit(state)
    clock[0] = 101.0
    assert not owner.commit(replace(state, observed_at_monotonic_s=101.0))
    assert owner.snapshot(timeout_s=0.5) is None
    assert owner.commit(replace(state, sequence=2, observed_at_monotonic_s=101.0))
    owner.bind(replace(state.binding, telemetry_generation=2))
    assert owner.snapshot(timeout_s=0.5) is None
    assert not owner.commit(replace(state, sequence=3, observed_at_monotonic_s=101.0))


def test_old_airspeed_does_not_become_fresh_with_a_new_pose():
    owner = AircraftStateOwner(clock=lambda: 101.0)
    state = aircraft_state(observed_at_monotonic_s=101.0)
    owner.bind(state.binding)
    assert owner.commit(state)
    assert owner.snapshot(timeout_s=0.5) is state
    assert owner.selected_airspeed(timeout_s=0.5).valid is False


def test_phase_progress_can_precede_pose_without_refreshing_measurement_age():
    clock = [100.]
    owner = AircraftStateOwner(clock=lambda: clock[0])
    state = aircraft_state(phase=AirframePhase.MULTICOPTER, is_vtol=True, is_tailsitter=True)
    owner.bind(state.binding)
    assert owner.commit(state)
    clock[0] = 100.1
    phase = replace(state, sequence=2, phase=AirframePhase.VTOL_TRANSITION)
    assert owner.commit(phase)
    assert owner.snapshot(timeout_s=.5).phase is AirframePhase.VTOL_TRANSITION
    assert owner.snapshot(timeout_s=.5).observed_at_monotonic_s == 100.
    assert not owner.commit(replace(phase, observed_at_monotonic_s=100.1))
    clock[0] = 101.
    assert owner.commit(replace(phase, sequence=3))
    assert owner.snapshot(timeout_s=.5) is None
    assert not owner.commit(replace(phase, sequence=4, observed_at_monotonic_s=99.))


def test_future_observation_and_changed_source_require_new_binding():
    owner = AircraftStateOwner(clock=lambda: 100.0)
    state = aircraft_state()
    owner.bind(state.binding)
    assert not owner.commit(replace(state, observed_at_monotonic_s=101.0))
    assert owner.commit(state)
    assert not owner.commit(replace(state, source="another_source", sequence=2))


def attitude_timing(**changes):
    values = dict(publication_timestamp_us=1_000_000, sample_timestamp_us=990_000,
                  publication_received_at_monotonic_s=100., sample_received_at_monotonic_s=100.,
                  quat_reset_counter=255, time_basis="px4_uxrce_adjusted_us")
    return AttitudeTiming(**(values | changes))


def test_attitude_timing_is_optional_frozen_and_strictly_decoded():
    payload = asdict(aircraft_state())
    payload.pop("attitude_timing")
    assert AircraftState.from_payload(payload).attitude_timing is None
    payload["attitude_timing"] = None
    assert AircraftState.from_payload(payload).attitude_timing is None
    timing = attitude_timing()
    payload["attitude_timing"] = asdict(timing)
    assert AircraftState.from_payload(payload).attitude_timing == timing
    with pytest.raises(FrozenInstanceError):
        timing.quat_reset_counter = 0
    payload["attitude_timing"]["unexpected"] = True
    with pytest.raises(ValueError, match="contract_invalid"):
        AircraftState.from_payload(payload)


@pytest.mark.parametrize("changes", [
    {"publication_timestamp_us": 0}, {"publication_timestamp_us": True},
    {"publication_timestamp_us": 2**64}, {"sample_timestamp_us": 0},
    {"sample_timestamp_us": 1_000_001}, {"sample_timestamp_us": 990_000.},
    {"publication_received_at_monotonic_s": math.nan},
    {"publication_received_at_monotonic_s": math.inf},
    {"sample_received_at_monotonic_s": -1.},
    {"sample_received_at_monotonic_s": True},
    {"sample_received_at_monotonic_s": 100.1},
    {"quat_reset_counter": -1}, {"quat_reset_counter": 256},
    {"quat_reset_counter": True}, {"time_basis": "px4_boot_us"},
])
def test_attitude_timing_rejects_invalid_source_receipts_reset_and_clock_basis(changes):
    with pytest.raises(ValueError):
        attitude_timing(**changes)


@pytest.mark.parametrize("offset", [0, 1_700_000_000_000_000])
def test_attitude_timing_checks_processing_and_delivery_age_without_clock_alignment(offset):
    timing = attitude_timing(publication_timestamp_us=offset + 1_000_000,
                             sample_timestamp_us=offset + 100_000)
    assert timing.fresh(100.05, 1.)
    assert not timing.fresh(100.2, 1.)
    assert not timing.fresh(99.9, 1.)
    with pytest.raises(ValueError, match="timeout"):
        timing.fresh(100., 0)


def test_republished_attitude_preserves_sample_receipt_and_expires_independently_of_aggregate():
    owner = AircraftStateOwner(clock=lambda: 101.01)
    timing = attitude_timing()
    state = aircraft_state(attitude_timing=timing)
    owner.bind(state.binding)
    assert owner.commit(state)
    republished = replace(timing, publication_timestamp_us=1_010_000,
                          publication_received_at_monotonic_s=100.5, quat_reset_counter=0)
    progressed = replace(state, sequence=2, observed_at_monotonic_s=100.5, attitude_timing=republished)
    assert owner.commit(progressed)
    assert owner.snapshot(timeout_s=1.) is progressed
    assert progressed.attitude_timing.quat_reset_counter == 0
    assert not progressed.attitude_timing.fresh(101.01, 1.)
    assert not owner.commit(replace(progressed, sequence=3, attitude_timing=replace(
        republished, sample_received_at_monotonic_s=100.5)))
    assert owner.commit(replace(progressed, sequence=3, attitude_timing=None))
    assert not owner.commit(replace(progressed, sequence=4, attitude_timing=replace(
        republished, sample_received_at_monotonic_s=100.5)))
    assert not owner.commit(replace(progressed, sequence=4, attitude_timing=replace(
        republished, sample_timestamp_us=980_000)))
    advanced = replace(republished, publication_timestamp_us=1_100_000, sample_timestamp_us=1_090_000,
                       publication_received_at_monotonic_s=101., sample_received_at_monotonic_s=101.)
    assert owner.commit(replace(progressed, sequence=4, attitude_timing=advanced))


def test_duplicate_publication_cannot_change_its_quaternion_or_reset_counter():
    owner = AircraftStateOwner(clock=lambda: 100.5)
    state = aircraft_state(attitude_timing=attitude_timing())
    owner.bind(state.binding)
    assert owner.commit(state)
    assert owner.commit(replace(state, sequence=2, phase=AirframePhase.MULTICOPTER))
    assert not owner.commit(replace(state, sequence=3, attitude_timing=replace(
        state.attitude_timing, quat_reset_counter=0)))
    assert not owner.commit(replace(state, sequence=3, attitude_body_to_ned=Quaternion(0., 1., 0., 0.)))
    assert not owner.commit(replace(state, sequence=3, attitude_timing=replace(
        state.attitude_timing, publication_received_at_monotonic_s=100.5)))


def test_future_attitude_receipt_is_rejected_and_new_binding_resets_progress():
    owner = AircraftStateOwner(clock=lambda: 100.)
    state = aircraft_state(attitude_timing=attitude_timing())
    owner.bind(state.binding)
    future = replace(state.attitude_timing, publication_received_at_monotonic_s=100.1)
    assert not owner.commit(replace(state, attitude_timing=future))
    assert owner.commit(state)
    binding = replace(state.binding, telemetry_generation=2)
    owner.bind(binding)
    reset = attitude_timing(publication_timestamp_us=100, sample_timestamp_us=90, quat_reset_counter=0)
    assert owner.commit(replace(state, binding=binding, attitude_timing=reset))


@pytest.mark.parametrize("value", [True, math.nan, math.inf, -math.inf])
def test_nonfinite_and_boolean_measurements_are_rejected(value):
    with pytest.raises(ValueError):
        Vector3(value, 0, 0)
    with pytest.raises(ValueError):
        aircraft_state(relative_altitude_m=value)


def test_groundspeed_cannot_be_labelled_as_airspeed():
    with pytest.raises(ValueError, match="airspeed_source"):
        AirspeedObservation("ground_speed_proxy", 20, 20, 100, True)
    with pytest.raises(ValueError, match="tailsitter_requires_vtol"):
        aircraft_state(is_tailsitter=True)
    with pytest.raises(ValueError, match="quaternion_not_unit"):
        Quaternion(0, 0, 0, 0)


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
@pytest.mark.parametrize("target", [(25, 5, -4), (-25, 5, -4), (0, 0, 20), (0, 0, -20), (-20, -.001, 5)])
@pytest.mark.parametrize("quaternion", [
    (1, 0, 0, 0),
    (math.cos(.3), 0, math.sin(.3), 0),
    (math.cos(.2), math.sin(.2), 0, 0),
    (math.cos(.4), 0, 0, math.sin(.4)),
    (-math.cos(.3), 0, -math.sin(.3), 0),
])
def test_both_mounts_recover_independent_world_target_with_tilt(mount, quaternion, target):
    angles = camera_angles_for_world_target((0, 0, 0), target, quaternion, mount)
    body = Vector3(*body_line_of_sight(angles, mount))
    world = Quaternion(*quaternion).rotate(body)
    expected = Vector3(*target).normalized()
    assert (world.x, world.y, world.z) == pytest.approx((expected.x, expected.y, expected.z))


def test_mavlink_heading_frame_preserves_ned_down_at_nonzero_pitch():
    q = Quaternion(math.cos(math.pi / 8), 0, math.sin(math.pi / 8), 0)
    world = q.rotate(Vector3(1, 0, 0))
    heading = ned_to_heading_frame(world, q.heading_rad)
    assert heading.x == pytest.approx(math.sqrt(.5))
    assert heading.z == pytest.approx(-math.sqrt(.5))
    assert heading != Vector3(1, 0, 0)


def test_tailsitter_rotation_is_attitude_not_a_second_installation_mapping():
    # Physical FRD pitched -90 degrees maps physical up into FW forward.
    q = Quaternion(math.sqrt(.5), 0, -math.sqrt(.5), 0)
    ray = q.rotate(Vector3(0, 0, -1))
    assert (ray.x, ray.y, ray.z) == pytest.approx((1, 0, 0), abs=1e-12)


def test_normalizing_large_finite_direction_does_not_overflow_to_zero():
    ray = Vector3(1.7e308, 1.7e308, 1.7e308).normalized()
    assert ray.magnitude == pytest.approx(1)


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
def test_tailsitter_virtual_fw_frame_is_invariant_with_combined_yaw_roll_and_pitch(mount):
    # Independent Hamilton multiplication establishes q_NF = q_NB * q_BF.
    # The camera preset still produces a physical-body ray exactly once.
    def multiply(left, right):
        w, x, y, z = left
        a, b, c, d = right
        return (w*a-x*b-y*c-z*d, w*b+x*a+y*d-z*c,
                w*c-x*d+y*a+z*b, w*d+x*c-y*b+z*a)

    q_nb = multiply(multiply((math.cos(.35), 0, 0, math.sin(.35)),
                             (math.cos(-.55), 0, math.sin(-.55), 0)),
                    (math.cos(.2), math.sin(.2), 0, 0))
    q_bf = (math.sqrt(.5), 0, math.sqrt(.5), 0)
    q_nf = multiply(q_nb, q_bf)
    angles = (15, 10, 0) if mount == "HORIZONTAL" else (0, 100, -15)
    physical_ray = Vector3(*body_line_of_sight(angles, mount))
    virtual_ray = Quaternion(q_bf[0], -q_bf[1], -q_bf[2], -q_bf[3]).rotate(physical_ray)
    direct = Quaternion(*q_nb).rotate(physical_ray)
    via_virtual = Quaternion(*q_nf).rotate(virtual_ray)
    assert (direct.x, direct.y, direct.z) == pytest.approx((via_virtual.x, via_virtual.y, via_virtual.z))
    wrong_double_rotation = Quaternion(*q_nf).rotate(physical_ray)
    assert (direct.x, direct.y, direct.z) != pytest.approx(
        (wrong_double_rotation.x, wrong_double_rotation.y, wrong_double_rotation.z))
