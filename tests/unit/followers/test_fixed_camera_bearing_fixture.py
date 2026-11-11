"""Synthetic optical samples paired with mocked native observed pose packets."""

from copy import deepcopy
from dataclasses import asdict, replace
import math

import numpy as np
import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.guidance_observation import PinholeCalibration
from classes.observation_alignment import AlignmentBinding
from classes.target_continuity import TargetEvidenceSnapshot, TargetEvidenceState
from classes.tracker_output import TrackerDataType
from tools.fixed_camera_bearing_fixture import FixedCameraBearingFixture
from tools.fixed_camera_world_target import FixedCamera
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing


def camera_and_calibration(mount='forward'):
    down = mount == 'down'
    camera = FixedCamera.from_mapping({
        'forward_body': [0., 0., 1.] if down else [1., 0., 0.],
        'right_body': [0., 1., 0.], 'down_body': [-1., 0., 0.] if down else [0., 0., 1.],
        'offset_body_m': [0., 0., 0.], 'horizontal_fov_deg': 90., 'vertical_fov_deg': 90.,
    })
    optical = Quaternion(math.sqrt(.5), 0., 0., math.sqrt(.5)) if down else Quaternion(.5, .5, .5, .5)
    calibration = PinholeCalibration('synthetic-camera', 'synthetic-optics-1', (640, 480),
                                     (320., 240.), (319.5, 239.5), optical, 'none')
    return camera, calibration


@pytest.fixture
def state():
    return aircraft_state(attitude_timing=attitude_timing())


@pytest.fixture
def clock():
    return [100.125]


@pytest.fixture
def make_fixture(clock, state):
    def make(mount='forward', **changes):
        camera, calibration = camera_and_calibration(mount)
        binding = AlignmentBinding('synthetic-camera', 'source-1', 'geometry-1', 'synthetic-optics-1',
                                    3, state.binding, 'native-1', 255)
        args = dict(camera=camera, calibration=calibration, binding=binding, fixture_revision='synthetic-fixture-1',
                    clock=lambda: clock[0], max_observation_age_s=.5, max_attitude_age_s=.5, allow_simulation=True)
        args.update(changes)
        return FixedCameraBearingFixture(**args)
    return make


def packet(state, *, position=(4., 5., -50.), timestamp=2_000_000, receipt=100.):
    q = state.attitude_body_to_ned
    return dict(fresh=True, runtime_id='native-1', aircraft_state=asdict(state),
                attitude_timing=asdict(state.attitude_timing), vehicle_pose={
                    'source': 'px4_dds_observed', 'vehicle_ned': list(position),
                    'quaternion_wxyz': [q.w, q.x, q.y, q.z], 'px4_timestamp_us': timestamp,
                    'observed_at_monotonic_s': receipt,
                })


def advanced(state, *, reset=255):
    return replace(state, sequence=2, observed_at_monotonic_s=100.25,
        attitude_timing=attitude_timing(publication_timestamp_us=1_250_000, sample_timestamp_us=1_240_000,
            publication_received_at_monotonic_s=100.25, sample_received_at_monotonic_s=100.25,
            quat_reset_counter=reset))


def rotation_matrix(roll, pitch, yaw):
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    return (np.array(((cy, -sy, 0), (sy, cy, 0), (0, 0, 1)))
            @ np.array(((cp, 0, sp), (0, 1, 0), (-sp, 0, cp)))
            @ np.array(((1, 0, 0), (0, cr, -sr), (0, sr, cr))))


@pytest.mark.parametrize('mount', ['forward', 'down'])
@pytest.mark.parametrize('angles', [(0., 0., 0.), (.2, -.15, .6), (-.2, .1, -3.12), (0., math.pi/2, .3)])
def test_both_explicit_mounts_recover_independent_world_bearing(make_fixture, state, mount, angles):
    owner = make_fixture(mount)
    state = replace(state, attitude_body_to_ned=Quaternion.from_euler(*angles),
                    is_vtol=angles[1] == math.pi/2, is_tailsitter=angles[1] == math.pi/2)
    body = np.array((-.5, 1., 10.)) if mount == 'down' else np.array((10., 1., .5))
    world = rotation_matrix(*angles) @ body
    target = tuple(np.array((4., 5., -50.)) + world)
    output = owner.project(packet(state), state, target, timestamp_s=1_700_000_000.)
    result = owner.resolve(output, state)
    assert output.data_type is TrackerDataType.POSITION_2D
    assert output.image_measurement.pixel_xy == pytest.approx((351.5, 251.5))
    assert output.position_2d == pytest.approx(((351.5-320.)/320., (251.5-240.)/240.))
    assert output.metadata['simulation_only'] is True
    assert result.association_kind == 'sih_projection_pair'
    assert (result.direction_ned.x, result.direction_ned.y, result.direction_ned.z) == pytest.approx(world/np.linalg.norm(world))
    assert result.attitude_state is state
    assert owner.last_sample.aircraft_state is state
    evidence = TargetEvidenceSnapshot.from_tracker_output(output, session_epoch=3, now_monotonic_s=100.125)
    assert evidence.state is TargetEvidenceState.CONFIRMED


def test_default_disabled_fixture_cannot_be_an_ordinary_live_source(make_fixture):
    with pytest.raises(ValueError, match='not_enabled'):
        make_fixture(allow_simulation=False)


def test_repeated_pose_poll_keeps_original_source_receipt_capture_and_display_time(make_fixture, state, clock):
    owner = make_fixture()
    observed = packet(state)
    output = owner.project(observed, state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    before = owner(output, state)
    clock[0] = 100.25
    duplicate = owner.project(observed, state, (14., 5., -50.), timestamp_s=1_700_000_100.)
    assert duplicate is output
    assert duplicate.timestamp == 1_700_000_000.
    assert duplicate.image_measurement.provenance.capture.captured_at == 100.
    assert duplicate.image_measurement.provenance.capture.capture_id == '2000000'
    assert owner.resolve(duplicate, state) is before
    assert output.raw_data['pose_timestamp_us'] == 2_000_000
    assert output.raw_data['attitude_sample_timestamp_us'] == 990_000


def test_current_quaternion_progress_cannot_reorient_the_old_frame(make_fixture, state, clock):
    owner = make_fixture()
    output = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    first = owner.resolve(output, state)
    current = replace(advanced(state), attitude_body_to_ned=Quaternion.from_euler(.2, -.3, 1.))
    clock[0] = 100.375
    assert owner.resolve(output, current) is first
    assert first.direction_ned == Vector3(1., 0., 0.)
    assert first.attitude_state.attitude_body_to_ned == Quaternion(1., 0., 0., 0.)


def test_progressing_pose_builds_new_evidence_and_retires_old_output(make_fixture, state, clock):
    owner = make_fixture()
    old = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    current = advanced(state)
    clock[0] = 100.375
    new = owner.project(packet(current, timestamp=2_250_000, receipt=100.25), current,
                        (14., 5., -50.), timestamp_s=1_700_000_000.25)
    assert new.image_measurement.provenance.capture.capture_id == '2250000'
    assert new.image_measurement.provenance.capture.captured_at == 100.25
    assert owner.resolve(new, current).attitude_state is current
    with pytest.raises(ValueError, match='unavailable_or_changed'):
        owner.resolve(old, current)


@pytest.mark.parametrize('target', [(-6., 5., -50.), (14., 25., -50.), (14., 5., -30.),
                                     (4., 5., -50.), (14., 15., -50.)])
def test_behind_out_of_fov_and_pixel_boundary_have_missing_evidence_not_clamped(make_fixture, state, target):
    owner = make_fixture()
    output = owner.project(packet(state), state, target, timestamp_s=1_700_000_000.)
    assert not output.tracking_active
    assert output.position_2d is None and output.image_measurement is None
    assert owner.last_sample is None and owner.last_alignment is None
    assert TargetEvidenceSnapshot.from_tracker_output(output, session_epoch=3).state is TargetEvidenceState.ABSENT
    with pytest.raises(ValueError, match='unavailable_or_changed'):
        owner.resolve(output, state)


@pytest.mark.parametrize('change', ['stale', 'unknown_source', 'wrong_quaternion', 'missing_timing',
                                  'wrong_runtime', 'wrong_state', 'rewritten_timing', 'missing_pose'])
def test_unqualified_native_pose_cannot_produce_or_retain_a_bearing(make_fixture, state, change):
    owner = make_fixture()
    original = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    value = packet(state)
    if change == 'stale':
        value['vehicle_pose']['observed_at_monotonic_s'] = 99.
    elif change == 'unknown_source':
        value['vehicle_pose']['source'] = 'display_attitude'
    elif change == 'wrong_quaternion':
        value['vehicle_pose']['quaternion_wxyz'] = [.5, .5, .5, .5]
    elif change == 'missing_timing':
        value['attitude_timing'] = None
    elif change == 'wrong_runtime':
        value['runtime_id'] = 'native-restarted'
    elif change == 'wrong_state':
        value['aircraft_state']['sequence'] += 1
    elif change == 'rewritten_timing':
        value['attitude_timing']['sample_received_at_monotonic_s'] = 99.9
    else:
        value.pop('vehicle_pose')
    with pytest.raises(ValueError):
        owner.project(value, state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    with pytest.raises(ValueError, match='unavailable_or_changed|owner_invalidated'):
        owner.resolve(original, state)


def test_display_offset_metadata_is_never_applied_to_physical_quaternion(make_fixture, state):
    owner = make_fixture()
    value = packet(state)
    value['vehicle_pose']['repr_offset_q'] = [0., 0., 1., 0.]
    output = owner.project(value, state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    assert owner(output, state).direction_ned == Vector3(1., 0., 0.)


def test_source_reset_runtime_and_retarget_need_explicit_new_owner(make_fixture, state):
    owner = make_fixture()
    old = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    reset = replace(state, attitude_timing=replace(state.attitude_timing, quat_reset_counter=0))
    with pytest.raises(ValueError, match='binding_changed'):
        owner.resolve(old, reset)
    camera, calibration = camera_and_calibration()
    rebound = AlignmentBinding('synthetic-camera', 'source-2', 'geometry-2', 'synthetic-optics-1',
                               4, reset.binding, 'native-restarted', 0)
    new_owner = make_fixture(binding=rebound)
    value = packet(reset)
    value['runtime_id'] = 'native-restarted'
    output = new_owner.project(value, reset, (14., 6., -50.), timestamp_s=1_700_000_001.)
    assert output.target_id == 4
    assert output.image_measurement.provenance.capture.source_epoch == 'source-2'
    assert new_owner.resolve(output, reset).binding is rebound
    with pytest.raises(ValueError, match='unavailable_or_changed'):
        new_owner.resolve(old, reset)


def test_changing_target_without_pose_progress_retains_original_target_truth(make_fixture, state):
    owner = make_fixture()
    target = (14., 5., -50.)
    original = owner.project(packet(state), state, target, timestamp_s=1_700_000_000.)
    assert owner.project(packet(state), state, (14., 6., -50.), timestamp_s=1_700_000_001.) is original
    assert owner.retained_frame(state) == (original, target)
    assert original.raw_data['measurement_target_ned'] == target


@pytest.mark.parametrize('component', ['position', 'attitude'])
@pytest.mark.parametrize('target', [(14., 8., -50.), (-6., 5., -50.)])
def test_partial_source_progress_retains_original_frame_pair_target_and_clocks(
        make_fixture, state, clock, component, target):
    owner = make_fixture()
    measured_target = (14., 5., -50.)
    original = owner.project(packet(state), state, measured_target, timestamp_s=1_700_000_000.)
    measurement, sample, alignment = original.image_measurement, owner.last_sample, owner.last_alignment
    raw = deepcopy(original.raw_data)
    if component == 'position':
        current = state
        value = packet(current, position=(5., 6., -50.), timestamp=2_250_000, receipt=100.25)
    else:
        current = replace(advanced(state), attitude_body_to_ned=Quaternion.from_euler(.2, -.3, 1.))
        value = packet(current, receipt=100.25)
    clock[0] = 100.375
    assert owner.project(value, current, target, timestamp_s=1_700_000_001.) is original
    assert owner.retained_frame(current) == (original, measured_target)
    assert original.image_measurement is measurement
    assert owner.last_sample is sample and owner.last_alignment is alignment
    assert owner.resolve(original, current) is alignment
    assert alignment.attitude_state is state
    assert original.timestamp == 1_700_000_000.
    assert original.raw_data == raw
    assert measurement.provenance.capture.capture_id == '2000000'
    assert measurement.provenance.capture.captured_at == 100.
    assert alignment.direction_ned == Vector3(1., 0., 0.)


def test_new_absent_frame_and_partial_progress_do_not_resurrect_previous_target(make_fixture, state, clock):
    owner = make_fixture()
    visible = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    current = advanced(state)
    clock[0] = 100.375
    missing = owner.project(packet(current, timestamp=2_250_000, receipt=100.25), current,
                            (-6., 5., -50.), timestamp_s=1_700_000_000.25)
    assert missing.image_measurement is None
    assert missing.raw_data['measurement_target_ned'] is None
    assert owner.retained_frame(current) == (missing, None)
    partial = packet(current, timestamp=2_300_000, receipt=100.3)
    assert owner.project(partial, current, (14., 5., -50.), timestamp_s=1_700_000_000.3) is missing
    assert owner.retained_frame(current) == (missing, None)
    with pytest.raises(ValueError, match='unavailable_or_changed'):
        owner.resolve(visible, current)


def test_partial_pose_progress_or_reordered_pose_cannot_refresh_measurement(make_fixture, state):
    owner = make_fixture()
    value = packet(state)
    first = owner.project(value, state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    partial = deepcopy(value)
    partial['vehicle_pose']['px4_timestamp_us'] += 1
    assert owner.project(partial, state, (14., 5., -50.), timestamp_s=1_700_000_001.) is first
    partial['vehicle_pose']['px4_timestamp_us'] = 1_999_999
    with pytest.raises(ValueError, match='pose_reordered'):
        owner.project(partial, state, (14., 5., -50.), timestamp_s=1_700_000_001.)
    with pytest.raises(ValueError, match='owner_invalidated'):
        owner.project(value, state, (14., 5., -50.), timestamp_s=1_700_000_001.)
    with pytest.raises(ValueError, match='owner_invalidated'):
        owner.retained_frame(state)


@pytest.mark.parametrize('component', ['position', 'attitude'])
@pytest.mark.parametrize('after_partial', [False, True])
def test_component_rewrite_invalidates_owner_even_when_other_component_progresses(
        make_fixture, state, clock, component, after_partial):
    owner = make_fixture()
    owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    current = advanced(state)
    clock[0] = 100.375
    if component == 'position':
        timestamp = 2_250_000 if after_partial else 2_000_000
        if after_partial:
            owner.project(packet(state, timestamp=timestamp, receipt=100.25), state,
                          (14., 6., -50.), timestamp_s=1_700_000_001.)
        value = packet(current, position=(5., 5., -50.), timestamp=timestamp, receipt=100.25)
    else:
        if after_partial:
            owner.project(packet(current, receipt=100.25), current,
                          (14., 6., -50.), timestamp_s=1_700_000_001.)
        else:
            current = replace(state, sequence=2, observed_at_monotonic_s=100.25)
        current = replace(current, attitude_body_to_ned=Quaternion.from_euler(.1, .2, .3))
        value = packet(current, timestamp=2_250_000, receipt=100.25)
    with pytest.raises(ValueError, match='pose_rewritten'):
        owner.project(value, current, (14., 6., -50.), timestamp_s=1_700_000_001.)
    with pytest.raises(ValueError, match='owner_invalidated'):
        owner.retained_frame(current)
    fresh = replace(advanced(state), attitude_timing=attitude_timing(
        publication_timestamp_us=1_300_000, sample_timestamp_us=1_290_000,
        publication_received_at_monotonic_s=100.3, sample_received_at_monotonic_s=100.3))
    with pytest.raises(ValueError, match='owner_invalidated'):
        owner.project(packet(fresh, timestamp=2_300_000, receipt=100.3), fresh,
                      (14., 5., -50.), timestamp_s=1_700_000_001.)


def test_reordering_after_partial_progress_cannot_hide_above_last_projected_timestamp(make_fixture, state):
    owner = make_fixture()
    owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    owner.project(packet(state, timestamp=2_250_000), state, (14., 6., -50.), timestamp_s=1_700_000_001.)
    with pytest.raises(ValueError, match='pose_reordered'):
        owner.project(packet(state, timestamp=2_100_000), state, (14., 6., -50.), timestamp_s=1_700_000_001.)


@pytest.mark.parametrize('through_project', [False, True])
def test_retained_frame_expires_at_original_receipt_despite_new_partial_receipt(
        make_fixture, state, clock, through_project):
    owner = make_fixture(max_attitude_age_s=2.)
    original = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    clock[0] = 100.625
    with pytest.raises(ValueError, match='frame_stale'):
        if through_project:
            owner.project(packet(state, timestamp=2_625_000, receipt=100.625), state,
                          (14., 6., -50.), timestamp_s=1_700_000_001.)
        else:
            owner.retained_frame(state)
    assert original.timestamp == 1_700_000_000.
    assert original.raw_data['measurement_monotonic_s'] == 100.
    assert original.image_measurement.provenance.capture.captured_at == 100.


@pytest.mark.parametrize('missing', [False, True])
def test_retained_target_metadata_tampering_rejects_frame(make_fixture, state, missing):
    owner = make_fixture()
    target = (-6., 5., -50.) if missing else (14., 5., -50.)
    output = owner.project(packet(state), state, target, timestamp_s=1_700_000_000.)
    output.raw_data['measurement_target_ned'] = (14., 6., -50.)
    with pytest.raises(ValueError, match='unavailable_or_changed'):
        owner.retained_frame(state)
    with pytest.raises(ValueError, match='unavailable_or_changed'):
        owner.resolve(output, state)


def test_old_pair_expires_even_when_current_aircraft_observation_is_fresh(make_fixture, state, clock):
    owner = make_fixture()
    old = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    current = replace(state, sequence=2, observed_at_monotonic_s=100.75,
        attitude_timing=attitude_timing(publication_timestamp_us=1_750_000, sample_timestamp_us=1_740_000,
            publication_received_at_monotonic_s=100.75, sample_received_at_monotonic_s=100.75))
    clock[0] = 100.875
    with pytest.raises(ValueError, match='observation_receipt_stale_or_future|attitude_stale'):
        owner.resolve(old, current)


@pytest.mark.parametrize('change', [
    {'focal_length_px': (319.5, 240.)}, {'principal_point_px': (320., 240.)},
    {'source_id': 'other-camera'}, {'revision': 'other-calibration'},
    {'optical_to_body': Quaternion(1., 0., 0., 0.)},
])
def test_projection_and_explicit_calibration_must_match(make_fixture, change):
    camera, calibration = camera_and_calibration()
    with pytest.raises(ValueError, match='mismatch'):
        make_fixture(calibration=replace(calibration, **change))


def test_modified_output_cannot_use_another_pixel_or_claim_new_epoch_time(make_fixture, state):
    owner = make_fixture()
    output = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    output.timestamp += 1
    with pytest.raises(ValueError, match='unavailable_or_changed'):
        owner.resolve(output, state)


def test_resolver_refuses_a_different_aircraft_observation_source(make_fixture, state):
    owner = make_fixture()
    output = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    with pytest.raises(ValueError, match='aircraft_source_changed'):
        owner.resolve(output, replace(state, source='different-source'))


def test_raw_native_payload_can_attach_its_validated_top_level_timing(make_fixture, state):
    owner = make_fixture()
    value = packet(state)
    value['aircraft_state'].pop('attitude_timing')
    output = owner.project(value, state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    assert owner.resolve(output, state).attitude_state is state
