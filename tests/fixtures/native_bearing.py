"""Explicit deterministic boresight/attitude pairing, without capture or IO."""

from classes.gimbal_bearing import gimbal_to_body_bearing
from classes.gimbal_types import CameraObservationSource, GimbalAngleObservation
from classes.observation_alignment import AlignmentBinding, ExactSihSample, associate_sih_bearing
from classes.tracker_output import TrackerDataType, TrackerOutput


def associated_gimbal_output(follower, owner, state, angles, *, receipt, sequence=1):
    observation = GimbalAngleObservation(CameraObservationSource('component-source', 0), 0,
        'component-boresight', 'component-mapping', tuple(angles), 'gimbal_body', sequence,
        receipt, 'TRACKING_ACTIVE', receipt)
    output = TrackerOutput(TrackerDataType.GIMBAL_ANGLES, receipt, True,
        angular=tuple(angles), gimbal_observation=observation,
        raw_data={'has_output': True, 'usable_for_following': True,
                  'angle_sample_monotonic': receipt, 'data_is_stale': False})
    bearing = gimbal_to_body_bearing(observation, mount_type=follower.mount_type,
        geometry=follower.angle_geometry, geometry_revision='component-mapping')
    runtime = owner.phase_owner.capabilities.runtime_id
    binding = AlignmentBinding('component-source', 0, 'component-mapping', None, 0,
        state.binding, runtime, state.attitude_timing.quat_reset_counter, provider_id='component-boresight')
    aligned = associate_sih_bearing(bearing, ExactSihSample(observation, state, runtime, 'deterministic-component'),
        binding=binding, now_monotonic_s=owner.clock(), max_observation_age_s=.75,
        max_attitude_age_s=.75, previous=None, allow_simulation=True)
    return output, aligned
