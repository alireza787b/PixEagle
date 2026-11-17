"""Synthetic boresight measurements use the shared strict native pose owner."""

from copy import deepcopy
from dataclasses import replace
import math

import numpy as np
import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.gimbal_geometry import resolve_angle_geometry
from classes.observation_alignment import AlignmentBinding
from classes.target_continuity import TargetEvidenceSnapshot, TargetEvidenceState
from classes.tracker_output import TrackerDataType
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing
from tests.unit.followers.test_fixed_camera_bearing_fixture import packet, advanced
from tools.gimbal_bearing_fixture import GimbalBearingFixture


@pytest.fixture
def state():
    return aircraft_state(attitude_timing=attitude_timing())


@pytest.fixture
def clock():
    return [100.125]


@pytest.fixture
def make_fixture(state, clock):
    def make(mount='HORIZONTAL', **changes):
        binding = AlignmentBinding('simulated-gimbal', 2, 'canonical-mapping', None, 3,
            state.binding, 'native-1', 255, provider_id='simulated-provider')
        args = dict(binding=binding, mount_type=mount, geometry=resolve_angle_geometry({}, mount),
            fixture_revision='simulated-boresight-v1', clock=lambda: clock[0],
            max_observation_age_s=.5, max_attitude_age_s=.5, allow_simulation=True)
        args.update(changes)
        return GimbalBearingFixture(**args)
    return make


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('angles', [(0., 0., 0.), (.2, -.15, .6), (-.2, .1, -3.12), (0., math.pi/2, .3)])
@pytest.mark.parametrize('target', [(14., 7., -52.), (-6., 5., -50.), (4., 5., -20.)])
def test_both_mounts_pair_independent_world_truth_with_exact_physical_pose(make_fixture, state, mount, angles, target):
    owner = make_fixture(mount)
    state = replace(state, attitude_body_to_ned=Quaternion.from_euler(*angles),
                    is_vtol=angles[1] == math.pi/2, is_tailsitter=angles[1] == math.pi/2)
    observed = packet(state)
    observed['vehicle_pose']['repr_offset_q'] = [0., 0., 1., 0.]
    output = owner.project(observed, state, target, timestamp_s=1_700_000_000.)
    result = owner.resolve(output, state)
    expected = np.asarray(target) - (4., 5., -50.)
    expected /= np.linalg.norm(expected)
    assert output.data_type is TrackerDataType.GIMBAL_ANGLES
    assert output.position_2d is output.image_measurement is None
    assert output.gimbal_observation is owner.last_sample.observation_provenance
    assert output.gimbal_observation.provider_id == 'simulated-provider'
    assert output.gimbal_observation.source.source_generation == 2
    assert result.attitude_state is state
    assert result.association_kind == 'sih_projection_pair'
    assert (result.direction_ned.x, result.direction_ned.y, result.direction_ned.z) == pytest.approx(expected)
    assert output.metadata['fixture_kind'] == 'simulated_boresight'
    assert output.gimbal_observation.time_basis == 'backend_receipt'
    assert output.gimbal_observation.physical_target_identity_confirmed is False
    assert TargetEvidenceSnapshot.from_tracker_output(output, session_epoch=3,
        now_monotonic_s=100.125).state is TargetEvidenceState.CONFIRMED


def test_simulation_opt_in_and_canonical_mapping_are_explicit(make_fixture):
    with pytest.raises(ValueError, match='not_enabled'):
        make_fixture(allow_simulation=False)
    with pytest.raises(ValueError, match='mapping_unsupported'):
        make_fixture(geometry=replace(resolve_angle_geometry({}, 'HORIZONTAL'), azimuth_sign=-1))


@pytest.mark.parametrize('progress', ['duplicate', 'pose_only', 'attitude_only'])
def test_polling_and_partial_pose_preserve_original_target_and_both_receipts(make_fixture, state, clock, progress):
    owner = make_fixture()
    original = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    paired = owner.resolve(original, state)
    current = advanced(state) if progress == 'attitude_only' else state
    observed = packet(current, timestamp=2_250_000 if progress == 'pose_only' else 2_000_000, receipt=100.25)
    clock[0] = 100.375
    retained = owner.project(observed, current, (14., 8., -48.), timestamp_s=1_700_000_100.)
    assert retained is original
    assert retained.timestamp == 1_700_000_000.
    assert retained.gimbal_observation.angle_received_at_monotonic_s == 100.
    assert retained.gimbal_observation.tracking_received_at_monotonic_s == 100.
    assert retained.gimbal_observation.angle_receipt_sequence == 2_000_000
    assert owner.retained_frame(current) == (original, (14., 5., -50.))
    assert owner.resolve(retained, current) is paired


def test_new_current_quaternion_cannot_rotate_old_boresight(make_fixture, state, clock):
    owner = make_fixture()
    output = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    first = owner.resolve(output, state)
    current = replace(advanced(state), attitude_body_to_ned=Quaternion.from_euler(.2, -.3, 1.))
    clock[0] = 100.375
    assert owner.resolve(output, current) is first
    assert first.direction_ned == Vector3(1., 0., 0.)


def test_progressing_pose_retires_old_output_and_uses_original_packet_receipt(make_fixture, state, clock):
    owner = make_fixture()
    old = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    current = advanced(state)
    clock[0] = 100.375
    fresh = owner.project(packet(current, timestamp=2_250_000, receipt=100.25), current,
                          (14., 8., -48.), timestamp_s=1_700_000_000.25)
    assert fresh.gimbal_observation.angle_receipt_sequence == 2_250_000
    assert fresh.gimbal_observation.angle_received_at_monotonic_s == 100.25
    assert owner.resolve(fresh, current).attitude_state is current
    with pytest.raises(ValueError, match='unavailable_or_changed'):
        owner.resolve(old, current)


@pytest.mark.parametrize('change', ['runtime', 'unknown_source', 'quaternion', 'state', 'timing', 'reorder'])
def test_bad_native_packet_cannot_retain_or_revive_old_output(make_fixture, state, change):
    owner = make_fixture()
    original = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    bad = deepcopy(packet(state))
    if change == 'runtime': bad['runtime_id'] = 'new-runtime'
    elif change == 'unknown_source': bad['vehicle_pose']['source'] = 'display_attitude'
    elif change == 'quaternion': bad['vehicle_pose']['quaternion_wxyz'] = [.5, .5, .5, .5]
    elif change == 'state': bad['aircraft_state']['sequence'] += 1
    elif change == 'timing': bad['attitude_timing'] = None
    else: bad['vehicle_pose']['px4_timestamp_us'] -= 1
    with pytest.raises(ValueError):
        owner.project(bad, state, (14., 5., -50.), timestamp_s=1_700_000_001.)
    with pytest.raises(ValueError, match='owner_invalidated'):
        owner.resolve(original, state)


@pytest.mark.parametrize('component', ['position', 'attitude'])
def test_same_component_timestamp_cannot_change_when_the_other_progresses(make_fixture, state, clock, component):
    owner = make_fixture()
    owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    current = advanced(state) if component == 'position' else replace(state, sequence=2,
        attitude_body_to_ned=Quaternion.from_euler(.1, .2, .3))
    clock[0] = 100.375
    bad = packet(current, position=(5., 5., -50.), timestamp=2_000_000 if component == 'position' else 2_250_000)
    with pytest.raises(ValueError, match='pose_rewritten'):
        owner.project(bad, current, (14., 5., -50.), timestamp_s=1_700_000_001.)
    with pytest.raises(ValueError, match='owner_invalidated'):
        owner.retained_frame(current)


@pytest.mark.parametrize('change', ['reset', 'aircraft', 'source'])
def test_current_state_identity_cannot_rebind_an_existing_fixture(make_fixture, state, change):
    owner = make_fixture()
    output = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    current = (replace(state, attitude_timing=replace(state.attitude_timing, quat_reset_counter=0)) if change == 'reset'
               else replace(state, binding=replace(state.binding, aircraft_uid='other-aircraft')) if change == 'aircraft'
               else replace(state, source='different-state-source'))
    with pytest.raises(ValueError, match='binding_changed|source_changed'):
        owner.resolve(output, current)


@pytest.mark.parametrize('change', ['provider', 'geometry', 'source', 'target', 'receipt', 'sequence', 'display'])
def test_tampered_observation_or_receipts_cannot_be_resolved(make_fixture, state, change):
    owner = make_fixture()
    output = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    observation = output.gimbal_observation
    if change == 'provider': output.gimbal_observation = replace(observation, provider_id='other-provider')
    elif change == 'geometry': output.gimbal_observation = replace(observation, geometry_revision='other-mapping')
    elif change == 'source': output.gimbal_observation = replace(observation, source=replace(observation.source, source_generation=3))
    elif change == 'target': output.raw_data['measurement_target_ned'] = (14., 8., -50.)
    elif change == 'receipt': output.raw_data['angle_sample_monotonic'] = 100.1
    elif change == 'sequence': output.raw_data['angle_sample_sequence'] += 1
    else: output.timestamp += 1
    with pytest.raises(ValueError, match='unavailable_or_changed'):
        owner.resolve(output, state)


def test_retained_frame_and_pose_keep_strict_original_age_limits(make_fixture, state, clock):
    owner = make_fixture(max_attitude_age_s=2.)
    output = owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_000.)
    clock[0] = 100.625
    with pytest.raises(ValueError, match='frame_stale'):
        owner.project(packet(state, timestamp=2_625_000, receipt=100.625), state,
                      (14., 8., -50.), timestamp_s=1_700_000_001.)
    assert output.gimbal_observation.angle_received_at_monotonic_s == 100.


def test_coincident_target_retains_actual_absence_without_resurrecting_old_target(make_fixture, state):
    owner = make_fixture()
    absent = owner.project(packet(state), state, (4., 5., -50.), timestamp_s=1_700_000_000.)
    assert not absent.tracking_active
    assert absent.angular is absent.gimbal_observation is None
    assert owner.last_sample is owner.last_alignment is None
    assert owner.project(packet(state), state, (14., 5., -50.), timestamp_s=1_700_000_001.) is absent
    assert owner.retained_frame(state) == (absent, None)
    with pytest.raises(ValueError, match='unavailable_or_changed'):
        owner.resolve(absent, state)
