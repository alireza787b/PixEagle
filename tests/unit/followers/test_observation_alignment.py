"""Synthetic association evidence; no sensor synchronization or flight authority."""

from dataclasses import FrozenInstanceError, replace
import math

import numpy as np
import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.frame_publisher import CaptureStamp
from classes.guidance_observation import CalibratedBearing, ImageMeasurement, ObservationProvenance, PinholeCalibration
from classes.image_bearing import image_to_body_bearing
from classes.observation_alignment import (
    AlignmentBinding, ExactSihSample, ReceiveTimeBounds,
    associate_received_bearing, associate_sih_bearing,
    require_current_bearing_association,
)
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing


@pytest.fixture
def state():
    return aircraft_state(attitude_timing=attitude_timing())


@pytest.fixture
def bearing():
    provenance = ObservationProvenance('camera-a', 3, 'geometry-a', 'calibration-a',
                                      CaptureStamp('epoch-a', '1', 100., 'fresh'))
    return CalibratedBearing(provenance, Vector3(1., .1, -.05).normalized())


@pytest.fixture
def binding(state, bearing):
    image = bearing.provenance
    return AlignmentBinding(image.source_id, image.capture.source_epoch, image.geometry_revision,
                             image.calibration_revision, image.target_generation, state.binding,
                             'native-a', state.attitude_timing.quat_reset_counter)


@pytest.fixture
def bounds(binding):
    return ReceiveTimeBounds(binding, (.02, .03), (.01, .02), .001, .05, 'measured-latency-fixture-1')


def sih(bearing, state, binding, **changes):
    sample = ExactSihSample(bearing.provenance, state, 'native-a', 'sih-projection-fixture-1')
    args = dict(binding=binding, now_monotonic_s=100.125, max_observation_age_s=.5,
                max_attitude_age_s=.5, previous=None, allow_simulation=True)
    args.update(changes)
    return associate_sih_bearing(bearing, sample, **args)


def received(bearing, state, binding, bounds, **changes):
    args = dict(native_runtime_id='native-a', binding=binding, now_monotonic_s=100.125,
                max_observation_age_s=.5, max_attitude_age_s=.5, bounds=bounds, previous=None)
    args.update(changes)
    return associate_received_bearing(bearing, state, **args)


def next_bearing(bearing, **changes):
    capture = replace(bearing.provenance.capture, **(dict(capture_id='2', captured_at=100.0625) | changes))
    return replace(bearing, provenance=replace(bearing.provenance, capture=capture))


def test_physical_capture_is_unqualified_without_explicit_bounds(bearing, state, binding):
    with pytest.raises(ValueError, match='physical_capture_timing_unqualified'):
        received(bearing, state, binding, None)


@pytest.mark.parametrize('now', [100.47, 100.49])
def test_retained_physical_image_result_must_revalidate_acquisition_age(bearing, state, binding, bounds, now):
    aligned = received(bearing, state, binding, bounds)
    with pytest.raises(ValueError, match='guidance_input_stale'):
        require_current_bearing_association(aligned, bearing.provenance, state, native_runtime_id='native-a',
            now_monotonic_s=now, max_observation_age_s=.5, max_attitude_age_s=.5)


@pytest.mark.parametrize('allow', [False, None, 1, 'true'])
def test_sih_pair_is_not_an_ordinary_live_qualification_option(bearing, state, binding, allow):
    with pytest.raises(ValueError, match='not_enabled'):
        sih(bearing, state, binding, allow_simulation=allow)


def test_sih_default_is_disabled_and_result_claims_only_observed_projection_pair(bearing, state, binding):
    sample = ExactSihSample(bearing.provenance, state, 'native-a', 'sih-fixture')
    with pytest.raises(ValueError, match='not_enabled'):
        associate_sih_bearing(bearing, sample, binding=binding, now_monotonic_s=100.125,
                              max_observation_age_s=.5, max_attitude_age_s=.5, previous=None)
    result = sih(bearing, state, binding)
    assert result.association_kind == 'sih_projection_pair'
    assert result.worst_case_skew_s is None and result.receive_bounds is None
    assert result.bearing.provenance is bearing.provenance
    assert result.attitude_state is state
    assert result.bearing.provenance.time_basis == 'backend_receipt'
    assert result.bearing.provenance.capture.captured_at == 100.
    with pytest.raises(FrozenInstanceError):
        result.direction_ned = Vector3(1., 0., 0.)


def rotation_matrix(roll, pitch, yaw):
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    return (np.array(((cy, -sy, 0), (sy, cy, 0), (0, 0, 1)))
            @ np.array(((cp, 0, sp), (0, 1, 0), (-sp, 0, cp)))
            @ np.array(((1, 0, 0), (0, cr, -sr), (0, sr, cr))))


@pytest.mark.parametrize('angles,tailsitter', [
    ((0., 0., 0.), False), ((.3, -.2, .4), False), ((-.25, .15, -.3), False),
    ((.2, -.1, 3.12), False), ((-.2, .1, -3.12), False),
    ((0., math.pi/2, .4), True), ((.2, math.pi/2-.001, -.3), True),
])
def test_exact_rendered_measurement_uses_its_raw_physical_quaternion_once(bearing, state, binding, angles, tailsitter):
    roll, pitch, yaw = angles
    aircraft = rotation_matrix(roll, pitch, yaw)
    # An independent optical basis: conventional forward camera, or an explicit
    # fixed camera looking along physical -Z for this synthetic tailsitter case.
    mount = (np.diag((1., -1., -1.)) if tailsitter
             else np.array(((0., 0., 1.), (1., 0., 0.), (0., 1., 0.))))
    mount_quaternion = Quaternion(0., 1., 0., 0.) if tailsitter else Quaternion(.5, .5, .5, .5)
    world = aircraft @ mount @ np.array((.12, -.08, 1.))
    world /= np.linalg.norm(world)
    optical = mount.T @ aircraft.T @ world
    pixel = (640. + 900.*optical[0]/optical[2], 480. + 850.*optical[1]/optical[2])
    calibration = PinholeCalibration('camera-a', 'calibration-a', (1280, 960), (900., 850.),
                                     (640., 480.), mount_quaternion, 'none')
    image = ImageMeasurement(bearing.provenance, pixel, (1280, 960), (1., 0., 0., 0., 1., 0.), True)
    measured = image_to_body_bearing(image, calibration)
    paired_state = replace(state, attitude_body_to_ned=Quaternion.from_euler(roll, pitch, yaw),
                           is_vtol=tailsitter, is_tailsitter=tailsitter)
    result = sih(measured, paired_state, binding)
    assert (result.direction_ned.x, result.direction_ned.y, result.direction_ned.z) == pytest.approx(world)
    assert result.direction_ned.magnitude == pytest.approx(1.)


@pytest.mark.parametrize('field,value', [
    ('source_id', 'another-camera'), ('source_epoch', 'another-epoch'),
    ('geometry_revision', 'another-geometry'), ('calibration_revision', 'another-calibration'),
    ('target_generation', 4), ('native_runtime_id', 'another-native'), ('quat_reset_counter', 0),
])
def test_all_expected_source_and_reset_bindings_are_checked(bearing, state, binding, field, value):
    with pytest.raises(ValueError):
        sih(bearing, state, replace(binding, **{field: value}))


def test_aircraft_reconnection_requires_new_binding(bearing, state, binding):
    changed = replace(state, binding=replace(state.binding, connection_generation='connection-2'))
    with pytest.raises(ValueError, match='aircraft_or_runtime_changed'):
        sih(bearing, changed, binding)


def test_sih_pair_cannot_attach_another_images_observed_state(bearing, state, binding):
    sample = ExactSihSample(next_bearing(bearing).provenance, state, 'native-a', 'sih-fixture')
    with pytest.raises(ValueError, match='sih_projection_observation_changed'):
        associate_sih_bearing(bearing, sample, binding=binding, now_monotonic_s=100.125,
                              max_observation_age_s=.5, max_attitude_age_s=.5, previous=None, allow_simulation=True)


@pytest.mark.parametrize('change', ['cached', 'old_image', 'future_image', 'old_state', 'future_packet', 'missing_timing'])
def test_stale_future_and_unmeasured_inputs_never_gain_association(bearing, state, binding, change):
    if change == 'cached':
        bearing = replace(bearing, provenance=replace(bearing.provenance,
            capture=replace(bearing.provenance.capture, state='cached')))
    elif change in ('old_image', 'future_image'):
        bearing = replace(bearing, provenance=replace(bearing.provenance,
            capture=replace(bearing.provenance.capture, captured_at=99. if change == 'old_image' else 101.)))
    elif change == 'old_state':
        state = replace(state, observed_at_monotonic_s=99.)
    elif change == 'future_packet':
        state = replace(state, attitude_timing=replace(state.attitude_timing,
            publication_received_at_monotonic_s=101.))
    else:
        state = replace(state, attitude_timing=None)
    with pytest.raises(ValueError):
        sih(bearing, state, binding)


@pytest.mark.parametrize('path', ['sih', 'received'])
def test_exact_duplicate_reuses_original_result_and_cannot_refresh_time(bearing, state, binding, bounds, path):
    call = lambda **kw: sih(bearing, state, binding, **kw) if path == 'sih' else received(bearing, state, binding, bounds, **kw)
    first = call()
    assert call(previous=first, now_monotonic_s=100.25) is first
    assert first.bearing.provenance.capture.captured_at == 100.
    with pytest.raises(ValueError):
        call(previous=first, now_monotonic_s=100.75)


@pytest.mark.parametrize('change', ['direction', 'state', 'receipt'])
def test_duplicate_capture_cannot_be_rebound_to_new_math_or_state(bearing, state, binding, change):
    previous = sih(bearing, state, binding)
    if change == 'direction':
        bearing = replace(bearing, direction_body_frd=Vector3(1., 0., 0.))
    elif change == 'state':
        state = replace(state, sequence=2)
    else:
        bearing = replace(bearing, provenance=replace(bearing.provenance,
            capture=replace(bearing.provenance.capture, captured_at=100.0625)))
    with pytest.raises(ValueError, match='capture_rewritten'):
        sih(bearing, state, binding, previous=previous)


def test_new_capture_can_use_the_same_still_fresh_explicit_attitude_packet(bearing, state, binding):
    first = sih(bearing, state, binding)
    second = sih(next_bearing(bearing), state, binding, previous=first)
    assert second.attitude_state is first.attitude_state
    assert second.attitude_state.attitude_timing.sample_received_at_monotonic_s == 100.


def test_progressing_observed_packet_and_image_advance_without_rebinding(bearing, state, binding, bounds):
    previous = received(bearing, state, binding, bounds)
    advanced = replace(state, sequence=2, observed_at_monotonic_s=100.0625,
        attitude_timing=attitude_timing(publication_timestamp_us=1_062_500, sample_timestamp_us=1_052_500,
            publication_received_at_monotonic_s=100.0625, sample_received_at_monotonic_s=100.0625))
    current = received(next_bearing(bearing), advanced, binding, bounds, previous=previous)
    assert current is not previous
    assert current.attitude_state is advanced
    assert current.bearing.provenance.capture.captured_at == 100.0625


def test_reissued_older_producer_sequence_cannot_gain_freshness_from_new_receipt(bearing, state, binding):
    first = sih(bearing, state, binding)
    second = sih(next_bearing(bearing), state, binding, previous=first)
    old_id = replace(bearing, provenance=replace(bearing.provenance,
        capture=replace(bearing.provenance.capture, captured_at=100.1)))
    with pytest.raises(ValueError, match='capture_reordered'):
        sih(old_id, state, binding, previous=second)


def test_reordered_capture_and_old_binding_require_explicit_reset(bearing, state, binding):
    previous = sih(bearing, state, binding)
    reordered = replace(bearing, provenance=replace(bearing.provenance,
        capture=replace(bearing.provenance.capture, capture_id='2', captured_at=99.95)))
    with pytest.raises(ValueError, match='capture_reordered'):
        sih(reordered, state, binding, previous=previous)
    updated = next_bearing(bearing)
    updated = replace(updated, provenance=replace(updated.provenance, target_generation=4))
    new_binding = replace(binding, target_generation=4)
    with pytest.raises(ValueError, match='binding_changed'):
        sih(updated, state, new_binding, previous=previous)
    assert sih(updated, state, new_binding, previous=None).binding == new_binding


@pytest.mark.parametrize('change', [
    {'source': 'other-native-source', 'sequence': 2}, {'sequence': 0},
    {'sequence': 2, 'observed_at_monotonic_s': 99.95},
    {'sequence': 2, 'attitude_timing': attitude_timing(publication_timestamp_us=999_999)},
    {'sequence': 2, 'attitude_timing': attitude_timing(sample_timestamp_us=989_999)},
    {'sequence': 2, 'attitude_body_to_ned': Quaternion.from_euler(0., 0., .1)},
    {'sequence': 2, 'attitude_timing': attitude_timing(publication_timestamp_us=1_062_500,
        publication_received_at_monotonic_s=100.0625, sample_received_at_monotonic_s=100.0625)},
])
def test_attitude_progress_cannot_reorder_or_refresh_a_republished_sample(bearing, state, binding, change):
    previous = sih(bearing, state, binding)
    with pytest.raises(ValueError, match='attitude_reordered_or_rewritten'):
        sih(next_bearing(bearing), replace(state, **change), binding, previous=previous)


def test_native_first_sample_age_still_expires_after_republication(bearing, state, binding):
    republished = replace(state, sequence=2, observed_at_monotonic_s=100.6, attitude_timing=attitude_timing(
        publication_timestamp_us=1_600_000, publication_received_at_monotonic_s=100.6))
    image = replace(bearing, provenance=replace(bearing.provenance,
        capture=replace(bearing.provenance.capture, captured_at=100.6)))
    with pytest.raises(ValueError, match='attitude_stale'):
        sih(image, republished, binding, now_monotonic_s=100.625)


def test_explicit_receive_bounds_check_intervals_without_clock_invention(bearing, state, binding, bounds):
    result = received(bearing, state, binding, bounds)
    assert result.association_kind == 'bounded_receive_time'
    assert result.worst_case_skew_s == pytest.approx(.021)
    assert result.receive_bounds is bounds
    assert result.bearing.provenance.capture.captured_at == 100.
    offset = 10**15
    shifted = replace(state, attitude_timing=replace(state.attitude_timing,
        publication_timestamp_us=offset+1_000_000, sample_timestamp_us=offset+990_000))
    other = received(bearing, shifted, binding, bounds)
    assert other.direction_ned == result.direction_ned
    assert other.worst_case_skew_s == result.worst_case_skew_s


@pytest.mark.parametrize('change,error', [
    ({'attitude_sample_to_publication_receipt_s': (0., .005)}, 'contradicts_processing'),
    ({'observation_delay_s': (.125, .25)}, 'skew_exceeded'),
    ({'relative_clock_uncertainty_s': .0625}, 'skew_exceeded'),
])
def test_explicit_bounds_cannot_omit_processing_or_hide_skew(bearing, state, binding, bounds, change, error):
    with pytest.raises(ValueError, match=error):
        received(bearing, state, binding, replace(bounds, **change))


def test_bound_acquisition_age_is_conservative_beyond_receipt_age(bearing, state, binding, bounds):
    with pytest.raises(ValueError, match='camera_acquisition_stale'):
        received(bearing, state, binding, bounds, max_observation_age_s=.15)
    with pytest.raises(ValueError, match='attitude_acquisition_stale'):
        received(bearing, state, binding, bounds, max_attitude_age_s=.14)


def test_bounds_cannot_move_between_source_bindings(bearing, state, binding, bounds):
    other = replace(bounds, binding=replace(binding, source_epoch='another-epoch'))
    with pytest.raises(ValueError, match='bounds_binding_changed'):
        received(bearing, state, binding, other)


def test_republished_total_delay_bounds_must_include_the_original_sample_receipt(bearing, state, binding, bounds):
    inconsistent = replace(state, attitude_timing=replace(state.attitude_timing,
        sample_received_at_monotonic_s=99.75))
    with pytest.raises(ValueError, match='contradicts_first_receipt'):
        received(bearing, inconsistent, binding, bounds)


@pytest.mark.parametrize('change', [
    {'observation_delay_s': (-.1, .1)}, {'observation_delay_s': (.2, .1)}, {'observation_delay_s': (0., math.inf)},
    {'observation_delay_s': (False, .1)}, {'attitude_sample_to_publication_receipt_s': (0., math.nan)},
    {'relative_clock_uncertainty_s': -1.}, {'relative_clock_uncertainty_s': math.nan},
    {'relative_clock_uncertainty_s': True}, {'max_skew_s': 0.}, {'max_skew_s': math.inf},
    {'evidence_revision': ''},
])
def test_latency_bounds_require_finite_explicit_values_and_evidence(bounds, change):
    with pytest.raises(ValueError):
        replace(bounds, **change)


@pytest.mark.parametrize('change', [
    {'now_monotonic_s': math.inf}, {'max_observation_age_s': 0.}, {'max_attitude_age_s': math.nan},
])
def test_alignment_age_checks_are_strictly_finite(bearing, state, binding, change):
    with pytest.raises(ValueError):
        sih(bearing, state, binding, **change)


@pytest.mark.parametrize('change', [
    {'binding': None}, {'bearing': None}, {'attitude_state': None}, {'direction_ned': 'ned'},
    {'direction_ned': Vector3(2., 0., 0.)}, {'direction_ned': Vector3(0., 1., 0.)},
    {'association_kind': 'unknown'}, {'evidence_revision': ''}, {'worst_case_skew_s': 0.},
])
def test_constructed_sih_result_requires_valid_typed_geometry_and_qualification(bearing, state, binding, change):
    result = sih(bearing, state, binding)
    with pytest.raises(ValueError):
        replace(result, **change)


def test_result_constructor_rejects_mismatched_bindings_and_missing_attitude(bearing, state, binding, bounds):
    result = sih(bearing, state, binding)
    for change in ({'binding': replace(binding, target_generation=4)},
                   {'binding': replace(binding, quat_reset_counter=0)},
                   {'attitude_state': replace(state, attitude_timing=None)},
                   {'receive_bounds': bounds}):
        with pytest.raises(ValueError):
            replace(result, **change)


@pytest.mark.parametrize('change', [
    {'receive_bounds': None}, {'evidence_revision': 'other-evidence'},
    {'worst_case_skew_s': 0.}, {'worst_case_skew_s': math.nan}, {'worst_case_skew_s': True},
    {'worst_case_skew_s': 1.}, {'association_kind': 'sih_projection_pair'},
])
def test_constructed_received_result_cannot_forge_bounds_or_interval_skew(bearing, state, binding, bounds, change):
    result = received(bearing, state, binding, bounds)
    with pytest.raises(ValueError):
        replace(result, **change)


def test_new_capture_cannot_silently_change_a_bindings_timing_qualification(bearing, state, binding, bounds):
    prior_sih = sih(bearing, state, binding)
    current = next_bearing(bearing, captured_at=100.015625)
    with pytest.raises(ValueError, match='qualification_changed'):
        received(current, state, binding, bounds, previous=prior_sih)
    prior_receive = received(bearing, state, binding, bounds)
    for updated in (replace(bounds, evidence_revision='new-bench-evidence'),
                    replace(bounds, max_skew_s=.0625)):
        with pytest.raises(ValueError, match='qualification_changed'):
            received(current, state, binding, updated, previous=prior_receive)
    assert received(current, state, binding, bounds, previous=None)
