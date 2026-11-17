"""Explicit SIH boresight bearings from retained native pose; no camera IO."""

import math
from typing import Callable

from classes.aircraft_state import AircraftState
from classes.gimbal_bearing import gimbal_to_body_bearing
from classes.gimbal_geometry import AngleGeometry, resolve_angle_geometry
from classes.gimbal_types import CameraObservationSource, GimbalAngleObservation
from classes.observation_alignment import (
    AlignedBearing, AlignmentBinding, ExactSihSample, associate_sih_bearing, require_current_bearing_association,
)
from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.tracker_runtime_status import evaluate_tracker_command_freshness
from tools.native_pose_fixture import NativePoseFixture
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target


class GimbalBearingFixture:
    """One simulated source/provider/mapping binding and a read-only resolver."""

    tracker_type = TrackerDataType.GIMBAL_ANGLES

    def __init__(self, *, binding: AlignmentBinding, mount_type: str, geometry: AngleGeometry,
                 fixture_revision: str, clock: Callable[[], float], max_observation_age_s: float,
                 max_attitude_age_s: float, allow_simulation: bool = False):
        if type(allow_simulation) is not bool or not allow_simulation:
            raise ValueError('sih_projection_fixture_not_enabled')
        if (not isinstance(binding, AlignmentBinding) or type(binding.source_epoch) is not int
                or binding.calibration_revision is not None or binding.provider_id is None):
            raise ValueError('sih_gimbal_binding_invalid')
        if (mount_type not in {'HORIZONTAL', 'VERTICAL'} or not isinstance(geometry, AngleGeometry)
                or geometry != resolve_angle_geometry({}, mount_type)):
            raise ValueError('sih_gimbal_mapping_unsupported')
        if not isinstance(fixture_revision, str) or not fixture_revision.strip():
            raise ValueError('sih_projection_fixture_revision_invalid')
        self._poses = NativePoseFixture(binding=binding, clock=clock,
            max_observation_age_s=max_observation_age_s, max_attitude_age_s=max_attitude_age_s, allow_simulation=True)
        self._binding, self._mount, self._geometry = binding, mount_type, geometry
        self._fixture_revision = fixture_revision
        self._source = CameraObservationSource(binding.source_id, binding.source_epoch)
        self._output = self._observation = self._sample = self._alignment = None
        self._previous_alignment = self._raw_data = None
        self._target = self._timestamp = self._angles = None

    @property
    def last_sample(self) -> ExactSihSample | None:
        return self._sample

    @property
    def last_alignment(self) -> AlignedBearing | None:
        return self._alignment

    def project(self, packet: dict, state: AircraftState, target_ned: tuple[float, float, float],
                *, timestamp_s: float) -> TrackerOutput:
        """Pair a simulated boresight with actual pose, never a polled timestamp.

        Both source components must progress in this fixture; that conservative
        choice is not a physical gimbal sampling/synchronization requirement.
        timestamp_s is supplied epoch/display time. Receipts remain the original
        native pose acquisition receipt, without exposure or physical timing claims.
        """
        try:
            frame, progressing = self._poses.project(packet, state, target_ned, timestamp_s=timestamp_s)
            if not progressing:
                return self.retained_frame(state)[0]
            observation = sample = alignment = angles = None
            if math.dist(frame.position_ned, frame.target_ned) > 1e-6:
                angles = camera_angles_for_world_target(frame.position_ned, frame.target_ned,
                                                       frame.quaternion_wxyz, self._mount)
                observation = GimbalAngleObservation(self._source, self._binding.target_generation,
                    self._binding.provider_id, self._binding.geometry_revision, angles, 'gimbal_body',
                    frame.identity[0], frame.received_at_monotonic_s, 'TRACKING_ACTIVE', frame.received_at_monotonic_s)
                bearing = gimbal_to_body_bearing(observation, mount_type=self._mount,
                    geometry=self._geometry, geometry_revision=self._binding.geometry_revision)
                sample = ExactSihSample(observation, state, self._binding.native_runtime_id, self._fixture_revision)
                alignment = associate_sih_bearing(bearing, sample, binding=self._binding,
                    now_monotonic_s=self._poses.now(), max_observation_age_s=self._poses.observation_age,
                    max_attitude_age_s=self._poses.attitude_age, previous=self._previous_alignment, allow_simulation=True)
            visible = observation is not None
            output = TrackerOutput(TrackerDataType.GIMBAL_ANGLES, frame.timestamp_s, visible,
                tracker_id='simulated_gimbal_bearing', angular=angles, gimbal_observation=observation,
                target_id=self._binding.target_generation, raw_data={
                    'source': 'simulated_gimbal_bearing', 'has_output': visible,
                    'usable_for_following': visible, 'data_is_stale': False, 'identity_confirmed': visible,
                    'coordinate_system': 'gimbal_body', 'tracking_status': 'TRACKING_ACTIVE' if visible else 'TARGET_LOST',
                    'angle_sample_sequence': frame.identity[0] if visible else None,
                    'angle_sample_timestamp': frame.timestamp_s if visible else None,
                    'angle_sample_monotonic': frame.received_at_monotonic_s if visible else None,
                    'tracking_sample_timestamp': frame.timestamp_s if visible else None,
                    'tracking_sample_monotonic': frame.received_at_monotonic_s if visible else None,
                    'measurement_monotonic_s': frame.received_at_monotonic_s,
                    'measurement_time_basis': 'native_pose_receipt_for_sih_projection',
                    'measurement_target_ned': frame.target_ned if visible else None,
                    'pose_timestamp_us': frame.identity[0], 'attitude_sample_timestamp_us': frame.identity[1],
                    'attitude_publication_timestamp_us': state.attitude_timing.publication_timestamp_us,
                }, metadata={'simulation_only': True, 'fixture_revision': self._fixture_revision,
                    'fixture_kind': 'simulated_boresight', 'association_kind': 'sih_projection_pair',
                    'angle_sequence_basis': 'native_pose_timestamp_us_for_simulated_sample',
                    'timestamp_basis': 'supplied_display_epoch'})
            self._output, self._observation, self._sample, self._alignment = output, observation, sample, alignment
            self._target, self._timestamp, self._angles = frame.target_ned, frame.timestamp_s, angles
            self._raw_data = dict(output.raw_data)
            if alignment is not None:
                self._previous_alignment = alignment
            return output
        except (ValueError, TypeError, KeyError):
            self._output = self._observation = self._sample = self._alignment = None
            raise

    def _require_output(self, output):
        if (not isinstance(output, TrackerOutput) or output is not self._output
                or output.data_type is not TrackerDataType.GIMBAL_ANGLES
                or output.gimbal_observation is not self._observation
                or output.angular != self._angles or output.timestamp != self._timestamp
                or output.target_id != self._binding.target_generation
                or output.position_2d is not None or output.image_measurement is not None
                or output.raw_data != self._raw_data):
            raise ValueError('sih_projection_output_unavailable_or_changed')

    def retained_frame(self, current_state: AircraftState) -> tuple[TrackerOutput, tuple[float, float, float] | None]:
        self._poses.retained_frame(current_state)
        self._require_output(self._output)
        if self._alignment is not None:
            self.resolve(self._output, current_state)
        return self._output, self._target if self._observation is not None else None

    def resolve(self, output: TrackerOutput, current_state: AircraftState) -> AlignedBearing:
        now = self._poses.now()
        self._poses.require_state(current_state, now)
        self._require_output(output)
        if self._alignment is None or self._sample is None or not evaluate_tracker_command_freshness(output)['usable_for_following']:
            raise ValueError('sih_projection_output_unavailable_or_changed')
        result = associate_sih_bearing(self._alignment.bearing, self._sample, binding=self._binding,
            now_monotonic_s=now, max_observation_age_s=self._poses.observation_age,
            max_attitude_age_s=self._poses.attitude_age, previous=self._alignment, allow_simulation=True)
        require_current_bearing_association(result, self._observation, current_state,
            native_runtime_id=self._binding.native_runtime_id, now_monotonic_s=now,
            max_observation_age_s=self._poses.observation_age, max_attitude_age_s=self._poses.attitude_age)
        return result

    __call__ = resolve
