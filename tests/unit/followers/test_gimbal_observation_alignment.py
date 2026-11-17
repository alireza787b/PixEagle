"""Boresight association uses original GAC/TRC, never synthetic image metadata."""

from dataclasses import replace
import math

import numpy as np
import pytest

from classes.aircraft_state import Quaternion
from classes.gimbal_bearing import gimbal_to_body_bearing
from classes.gimbal_geometry import resolve_angle_geometry
from classes.gimbal_types import CameraObservationSource, GimbalAngleObservation
from classes.guidance_observation import bearing_receipt
from classes.observation_alignment import (
    AlignmentBinding, ExactSihSample, ReceiveTimeBounds,
    associate_received_bearing, associate_sih_bearing,
    require_current_bearing_association,
)
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target


def pair(mount='HORIZONTAL', *, attitude=(.2, -.1, .4), target=(20., 5., -12.)):
    state = aircraft_state(attitude_timing=attitude_timing(),
        attitude_body_to_ned=Quaternion.from_euler(*attitude))
    q = state.attitude_body_to_ned
    angles = camera_angles_for_world_target((0., 0., -20.), target, (q.w, q.x, q.y, q.z), mount)
    observation = GimbalAngleObservation(CameraObservationSource('owned-camera', 2), 3,
        'normalized-provider', 'mapping-a', angles, 'gimbal_body', 1, 100., 'TRACKING_ACTIVE', 100.)
    bearing = gimbal_to_body_bearing(observation, mount_type=mount,
        geometry=resolve_angle_geometry({}, mount), geometry_revision='mapping-a')
    binding = AlignmentBinding('owned-camera', 2, 'mapping-a', None, 3,
        state.binding, 'native-a', state.attitude_timing.quat_reset_counter, provider_id='normalized-provider')
    return bearing, state, binding


def sih(bearing, state, binding, *, previous=None, now=100.125, sample=None, allow=True):
    sample = sample or ExactSihSample(bearing.provenance, state, 'native-a', 'sih-boresight-fixture')
    return associate_sih_bearing(bearing, sample, binding=binding, now_monotonic_s=now,
        max_observation_age_s=.5, max_attitude_age_s=.5, previous=previous, allow_simulation=allow)


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('attitude', [(0., 0., 0.), (.2, -.3, .4), (-.4, .2, -3.12), (.3, -.2, 3.12),
                                      (.2, math.pi/2-.001, -.3)])
@pytest.mark.parametrize('target', [(20., 5., -12.), (-20., -.1, -20.), (0., 0., -2.)])
def test_both_mounts_use_observed_physical_attitude_once(mount, attitude, target):
    bearing, state, binding = pair(mount, attitude=attitude, target=target)
    result = sih(bearing, state, binding)
    expected = np.asarray(target) - np.asarray((0., 0., -20.))
    expected /= np.linalg.norm(expected)
    assert tuple(getattr(result.direction_ned, axis) for axis in ('x', 'y', 'z')) == pytest.approx(expected)
    assert result.bearing.provenance is bearing.provenance
    assert result.association_kind == 'sih_projection_pair'
    receipt = bearing_receipt(bearing.provenance)
    assert receipt.source_epoch == 2 and receipt.sample_id == 1
    assert receipt.calibration_revision is None
    assert not hasattr(bearing.provenance, 'capture')
    assert not hasattr(bearing.provenance, 'image_size_px')


def test_physical_gimbal_timing_requires_explicit_bounds_and_remains_receipt_based():
    bearing, state, binding = pair()
    kwargs = dict(native_runtime_id='native-a', binding=binding, now_monotonic_s=100.125,
        max_observation_age_s=.5, max_attitude_age_s=.5, previous=None)
    with pytest.raises(ValueError, match='physical_capture_timing_unqualified'):
        associate_received_bearing(bearing, state, **kwargs)
    bounds = ReceiveTimeBounds(binding, (.02, .03), (.01, .02), .001, .05, 'measured-delay-fixture')
    result = associate_received_bearing(bearing, state, bounds=bounds, **kwargs)
    assert result.association_kind == 'bounded_receive_time'
    assert result.bearing.provenance.time_basis == 'backend_receipt'
    assert result.bearing.provenance.angle_received_at_monotonic_s == 100.
    with pytest.raises(ValueError, match='skew_exceeded'):
        associate_received_bearing(bearing, state, bounds=replace(bounds, max_skew_s=.001), **kwargs)


def test_status_progress_cannot_refresh_or_rotate_the_retained_angle():
    bearing, state, binding = pair()
    first = sih(bearing, state, binding)
    updated = replace(bearing, provenance=replace(bearing.provenance, tracking_received_at_monotonic_s=100.1))
    current = sih(updated, state, binding, previous=first)
    assert current.bearing.provenance.tracking_received_at_monotonic_s == 100.1
    assert bearing_receipt(current.bearing.provenance).received_at_monotonic_s == 100.
    assert current.direction_ned == first.direction_ned
    with pytest.raises(ValueError, match='capture_rewritten'):
        sih(updated, replace(state, attitude_body_to_ned=Quaternion.from_euler(0., 0., 1.)), binding,
            previous=current)
    with pytest.raises(ValueError, match='receipt_stale_or_future'):
        sih(updated, state, binding, previous=current, now=100.51)


@pytest.mark.parametrize('change', [
    {'angle_receipt_sequence': 2, 'angle_received_at_monotonic_s': 99.9},
    {'angle_receipt_sequence': 1, 'angle_received_at_monotonic_s': 100.01},
    {'tracking_received_at_monotonic_s': 99.9},
    {'angles_deg': (1., 2., 3.)},
])
def test_changed_or_reordered_angle_and_status_packets_refuse(change):
    bearing, state, binding = pair()
    original = sih(bearing, state, binding)
    changed = gimbal_to_body_bearing(replace(bearing.provenance, **change), mount_type='HORIZONTAL',
        geometry=resolve_angle_geometry({}, 'HORIZONTAL'), geometry_revision='mapping-a')
    with pytest.raises(ValueError):
        sih(changed, state, binding, previous=original)


@pytest.mark.parametrize('change', [
    {'tracking_state': 'TARGET_LOST'}, {'tracking_state': None, 'tracking_received_at_monotonic_s': None},
    {'tracking_received_at_monotonic_s': 100.2}, {'tracking_received_at_monotonic_s': 99.},
    {'angle_received_at_monotonic_s': 100.2}, {'angle_received_at_monotonic_s': 99.},
])
def test_angle_and_tracking_receipts_are_independently_required(change):
    bearing, state, binding = pair()
    with pytest.raises(ValueError):
        sih(replace(bearing, provenance=replace(bearing.provenance, **change)), state, binding)


@pytest.mark.parametrize('change', [
    {'source_id': 'other-camera'}, {'source_epoch': 3}, {'geometry_revision': 'other-mapping'},
    {'target_generation': 4}, {'native_runtime_id': 'other-native'}, {'quat_reset_counter': 0},
    {'provider_id': 'different-provider'},
])
def test_original_source_target_runtime_and_reset_remain_bound(change):
    bearing, state, binding = pair()
    with pytest.raises(ValueError):
        sih(bearing, state, replace(binding, **change))


def test_gimbal_conversion_requires_owned_original_mapping_and_sih_is_explicit():
    bearing, state, binding = pair()
    with pytest.raises(ValueError, match='geometry_changed'):
        gimbal_to_body_bearing(bearing.provenance, mount_type='HORIZONTAL',
            geometry=resolve_angle_geometry({}, 'HORIZONTAL'), geometry_revision='other-mapping')
    with pytest.raises(ValueError, match='ownership_unavailable'):
        replace(bearing, provenance=replace(bearing.provenance, source=None))
    with pytest.raises(ValueError, match='not_enabled'):
        sih(bearing, state, binding, allow=False)
    sample = ExactSihSample(replace(bearing.provenance, angle_receipt_sequence=2), state,
        'native-a', 'sih-boresight-fixture')
    with pytest.raises(ValueError, match='observation_changed'):
        sih(bearing, state, binding, sample=sample)


def test_typed_result_cannot_retain_lost_tracking_or_bypass_a_current_estimator_reset():
    bearing, state, binding = pair()
    aligned = sih(bearing, state, binding)
    lost = replace(bearing, provenance=replace(bearing.provenance, tracking_state='TARGET_LOST'))
    with pytest.raises(ValueError, match='tracking_invalid'):
        replace(aligned, bearing=lost)
    kwargs = dict(native_runtime_id='native-a', now_monotonic_s=100.125,
                  max_observation_age_s=.5, max_attitude_age_s=.5)
    require_current_bearing_association(aligned, bearing.provenance, state, **kwargs)
    changed = replace(state, attitude_timing=replace(state.attitude_timing,
        quat_reset_counter=(state.attitude_timing.quat_reset_counter + 1) % 256))
    with pytest.raises(ValueError, match='aircraft_or_reset_changed'):
        require_current_bearing_association(aligned, bearing.provenance, changed, **kwargs)
    with pytest.raises(ValueError, match='aircraft_or_runtime_changed'):
        require_current_bearing_association(aligned, bearing.provenance, state,
            **(kwargs | {'native_runtime_id': 'other-native'}))


def test_new_angle_sequence_cannot_change_provider_under_the_original_binding():
    bearing, state, binding = pair()
    changed = replace(bearing, provenance=replace(bearing.provenance, provider_id='different-provider',
        angle_receipt_sequence=2, angle_received_at_monotonic_s=100.05))
    with pytest.raises(ValueError, match='observation_binding_changed'):
        sih(changed, state, binding)


@pytest.mark.parametrize('now', [100.47, 100.49])
def test_cached_physical_result_expires_at_the_original_bounded_acquisition_age(now):
    bearing, state, binding = pair()
    bounds = ReceiveTimeBounds(binding, (.02, .03), (.01, .02), .001, .05, 'measured-delay-fixture')
    aligned = associate_received_bearing(bearing, state, bounds=bounds, native_runtime_id='native-a',
        binding=binding, now_monotonic_s=100.125, max_observation_age_s=.5,
        max_attitude_age_s=.5, previous=None)
    with pytest.raises(ValueError, match='guidance_input_stale'):
        require_current_bearing_association(aligned, bearing.provenance, state, native_runtime_id='native-a',
            now_monotonic_s=now, max_observation_age_s=.5, max_attitude_age_s=.5)


def test_current_aircraft_state_cannot_precede_the_associated_sample():
    bearing, state, binding = pair()
    aligned = sih(bearing, state, binding)
    with pytest.raises(ValueError, match='reordered_or_rewritten'):
        require_current_bearing_association(aligned, bearing.provenance, replace(state, sequence=0),
            native_runtime_id='native-a', now_monotonic_s=100.125,
            max_observation_age_s=.5, max_attitude_age_s=.5)


def test_republished_attitude_cannot_rewrite_the_same_sample_quaternion():
    bearing, state, binding = pair()
    aligned = sih(bearing, state, binding)
    timing = replace(state.attitude_timing, publication_timestamp_us=1_050_000,
                     publication_received_at_monotonic_s=100.05)
    rewritten = replace(state, sequence=2, observed_at_monotonic_s=100.05,
        attitude_timing=timing, attitude_body_to_ned=Quaternion.from_euler(.1, .2, .3))
    with pytest.raises(ValueError, match='reordered_or_rewritten'):
        require_current_bearing_association(aligned, bearing.provenance, rewritten, native_runtime_id='native-a',
            now_monotonic_s=100.125, max_observation_age_s=.5, max_attitude_age_s=.5)
    newer_angle = replace(bearing, provenance=replace(bearing.provenance,
        angle_receipt_sequence=2, angle_received_at_monotonic_s=100.05))
    with pytest.raises(ValueError, match='attitude_reordered_or_rewritten'):
        sih(newer_angle, rewritten, binding, previous=aligned)
