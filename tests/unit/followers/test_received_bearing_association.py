"""Explicit receipt-only fallback; never synthetic exposure/reset evidence."""

from dataclasses import replace
import math
from types import SimpleNamespace

import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.frame_publisher import CaptureStamp
from classes.guidance_observation import CalibratedBearing, ObservationProvenance
from classes.gimbal_bearing import ReceivedGimbalBearingResolver
from classes.gimbal_geometry import resolve_angle_geometry
from classes.observation_alignment import (
    associate_latest_received_bearing, bearing_intent_requires_update,
    require_current_bearing_association,
)
from tests.unit.followers.test_gimbal_observation_alignment import pair


def associate(bearing, state, *, previous=None, now=100.125, runtime="stock-a"):
    return associate_latest_received_bearing(bearing, state, native_runtime_id=runtime,
        now_monotonic_s=now, max_observation_age_s=.5, max_attitude_age_s=.5, previous=previous)


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
@pytest.mark.parametrize("attitude", [(0., 0., 0.), (.2, -.3, .4), (.2, math.pi/2-.001, -.3)])
def test_same_independent_mount_fixture_uses_physical_attitude_once_without_inventing_timing(mount, attitude):
    bearing, state, _ = pair(mount, attitude=attitude)
    state = replace(state, source="mavlink2rest_source_progress", attitude_timing=None)
    result = associate(bearing, state)
    expected = Vector3(20., 5., 8.).normalized()
    assert tuple(getattr(result.direction_ned, axis) for axis in ("x", "y", "z")) == pytest.approx(
        tuple(getattr(expected, axis) for axis in ("x", "y", "z")))
    assert result.association_kind == "latest_received_bearing"
    assert result.binding.quat_reset_counter is None
    assert result.attitude_state.attitude_timing is None
    assert result.source_time is None and result.receive_bounds is None and result.worst_case_skew_s is None
    assert result.bearing.provenance == bearing.provenance
    assert result.bearing.provenance.source_sample is None


def untimed_pair():
    bearing, state, _ = pair()
    return bearing, replace(state, attitude_timing=None)


def test_cached_bearing_keeps_original_world_ray_even_when_aircraft_attitude_changes():
    bearing, state = untimed_pair()
    original = associate(bearing, state)
    newer = replace(state, sequence=2, observed_at_monotonic_s=100.1,
                    attitude_body_to_ned=Quaternion.from_euler(0., 0., 1.))
    retained = associate(bearing, newer, previous=original)
    assert retained == original
    assert retained.attitude_state.observed_at_monotonic_s == 100.
    assert bearing_intent_requires_update(retained, original, newer, state, 1, 1)
    assert not bearing_intent_requires_update(retained, original, newer, newer, 1, 1)
    assert bearing_intent_requires_update(retained, original, newer, newer, 2, 1)


def test_tracking_status_progress_does_not_refresh_angle_or_associated_attitude():
    bearing, state = untimed_pair()
    first = associate(bearing, state)
    updated = replace(bearing, provenance=replace(bearing.provenance, tracking_received_at_monotonic_s=100.1))
    current = associate(updated, state, previous=first)
    assert current.bearing.provenance.tracking_received_at_monotonic_s == 100.1
    assert current.direction_ned == first.direction_ned
    assert current.attitude_state is first.attitude_state
    with pytest.raises(ValueError, match="stale"):
        associate(updated, replace(state, sequence=2, observed_at_monotonic_s=100.6), previous=current, now=100.6)


def test_new_angle_receipt_uses_new_quaternion_and_same_canonical_geometry():
    bearing, state = untimed_pair()
    first = associate(bearing, state)
    changed = replace(bearing, provenance=replace(bearing.provenance, angle_receipt_sequence=2,
        angle_received_at_monotonic_s=100.1, tracking_received_at_monotonic_s=100.1))
    newer = replace(state, sequence=2, observed_at_monotonic_s=100.1,
                    attitude_body_to_ned=Quaternion.from_euler(0., 0., 1.))
    result = associate(changed, newer, previous=first)
    assert result.direction_ned == newer.attitude_body_to_ned.rotate(changed.direction_body_frd).normalized()
    assert result.direction_ned != first.direction_ned


@pytest.mark.parametrize("change", [
    {"angle_receipt_sequence": 0}, {"angle_received_at_monotonic_s": 99.},
    {"tracking_state": "TARGET_LOST"}, {"tracking_received_at_monotonic_s": 99.},
    {"target_generation": 4}, {"provider_id": "other-provider"}, {"geometry_revision": "other-mapping"},
])
def test_stale_or_rebound_provider_cannot_reuse_an_old_association(change):
    bearing, state = untimed_pair()
    first = associate(bearing, state)
    with pytest.raises(ValueError):
        changed = replace(bearing, provenance=replace(bearing.provenance, **change))
        associate(changed, state, previous=first)


def test_rewritten_same_sequence_cannot_rotate_a_cached_angle():
    bearing, state = untimed_pair()
    first = associate(bearing, state)
    with pytest.raises(ValueError, match="reordered_or_rewritten"):
        associate(bearing, replace(state, attitude_body_to_ned=Quaternion.from_euler(0., 0., 1.)), previous=first)
    changed = replace(bearing, direction_body_frd=Vector3(1., 0., 0.))
    with pytest.raises(ValueError, match="capture_rewritten"):
        associate(changed, state, previous=first)


def test_runtime_or_aircraft_change_cannot_relabel_a_retained_ray():
    bearing, state = untimed_pair()
    first = associate(bearing, state)
    with pytest.raises(ValueError):
        associate(bearing, state, previous=first, runtime="stock-b")
    with pytest.raises(ValueError):
        associate(bearing, replace(state, binding=replace(state.binding, connection_generation="other")), previous=first)


def test_image_camera_reuses_same_receipt_contract_without_gimbal_or_fake_exposure_fields():
    _, state = untimed_pair()
    provenance = ObservationProvenance("fixed-camera", 1, "geometry-a", "calibration-a",
        CaptureStamp("stream-a", "frame-1", 100., "fresh"))
    bearing = CalibratedBearing(provenance, Vector3(1., 0., 0.))
    result = associate(bearing, state)
    assert result.bearing.provenance is provenance
    assert result.binding.calibration_revision == "calibration-a"
    assert result.association_kind == "latest_received_bearing"


def test_receipt_fallback_cannot_masquerade_as_a_timed_association():
    bearing, state, _ = pair()
    with pytest.raises(ValueError, match="contract_invalid"):
        associate(bearing, state)
    result = associate(bearing, replace(state, attitude_timing=None))
    for kind in ("sih_projection_pair", "bounded_receive_time", "bounded_source_time"):
        with pytest.raises(ValueError):
            replace(result, association_kind=kind)
    with pytest.raises(ValueError):
        require_current_bearing_association(result, bearing.provenance, state, native_runtime_id="stock-a",
            now_monotonic_s=100.125, max_observation_age_s=.5, max_attitude_age_s=.5)


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
def test_owned_resolver_checks_mapping_and_target_generations_without_owning_recovery(mount):
    bearing, state, _ = pair(mount)
    state = replace(state, attitude_timing=None)
    observation = bearing.provenance
    resolver = ReceivedGimbalBearingResolver(source=observation.source, provider_id=observation.provider_id,
        mount=mount, geometry=resolve_angle_geometry({}, mount), binding=state.binding,
        runtime_id="stock-a", timeout_s=.5, clock=lambda: 100.125)
    observation = replace(observation, geometry_revision=resolver.geometry_revision)
    first = resolver(SimpleNamespace(gimbal_observation=observation), state)
    current = replace(state, sequence=2, observed_at_monotonic_s=100.1,
        attitude_body_to_ned=Quaternion.from_euler(0., 0., 1.))
    assert resolver(SimpleNamespace(gimbal_observation=observation), current).direction_ned == first.direction_ned
    retarget = replace(observation, target_generation=4, angle_receipt_sequence=2, angle_received_at_monotonic_s=100.1)
    assert resolver(SimpleNamespace(gimbal_observation=retarget), current).binding.target_generation == 4
    with pytest.raises(ValueError, match="target_generation_obsolete"):
        resolver(SimpleNamespace(gimbal_observation=observation), current)
    with pytest.raises(ValueError, match="gimbal_binding_changed"):
        resolver(SimpleNamespace(gimbal_observation=replace(retarget, geometry_revision="other")), current)
