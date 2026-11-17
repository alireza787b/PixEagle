"""Isolated-SIH synthetic image bearings from actual retained native pose.

No camera, network, aircraft command, or flight model is owned here. The caller
supplies independent target truth and both explicit synthetic camera models.
Create a new fixture for a new source/target/runtime/reset binding.
"""

import math
from typing import Callable

from classes.aircraft_state import AircraftState, Vector3, finite_number
from classes.frame_publisher import CaptureStamp
from classes.guidance_observation import ImageMeasurement, ObservationProvenance, PinholeCalibration
from classes.image_bearing import image_to_body_bearing
from classes.observation_alignment import (
    AlignedBearing, AlignmentBinding, ExactSihSample, associate_sih_bearing, require_current_bearing_association,
)
from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.tracker_runtime_status import evaluate_tracker_command_freshness
from tools.fixed_camera_world_target import FixedCamera
from tools.native_pose_fixture import NativePoseFixture


class FixedCameraBearingFixture:
    """One explicit simulated source binding, with a read-only bearing resolver."""

    tracker_type = TrackerDataType.POSITION_2D

    def __init__(
        self, *, camera: FixedCamera, calibration: PinholeCalibration,
        binding: AlignmentBinding, fixture_revision: str, clock: Callable[[], float],
        max_observation_age_s: float, max_attitude_age_s: float, allow_simulation: bool = False,
    ):
        if type(allow_simulation) is not bool or not allow_simulation:
            raise ValueError('sih_projection_fixture_not_enabled')
        if (not isinstance(camera, FixedCamera) or not isinstance(calibration, PinholeCalibration)
                or not isinstance(binding, AlignmentBinding) or not callable(clock)):
            raise ValueError('sih_projection_fixture_contract_invalid')
        if not isinstance(fixture_revision, str) or not fixture_revision.strip():
            raise ValueError('sih_projection_fixture_revision_invalid')
        for value in (max_observation_age_s, max_attitude_age_s):
            if finite_number(value, 'sih_projection_age_limit') <= 0:
                raise ValueError('sih_projection_age_limit_not_positive')
        self._camera = FixedCamera.from_mapping({
            **{name: [getattr(getattr(camera, name), axis) for axis in ('x', 'y', 'z')]
               for name in ('forward_body', 'right_body', 'down_body')},
            'offset_body_m': [camera.offset_body.x, camera.offset_body.y, camera.offset_body.z],
            'horizontal_fov_deg': camera.horizontal_fov_deg, 'vertical_fov_deg': camera.vertical_fov_deg,
        })
        if calibration.source_id != binding.source_id or calibration.revision != binding.calibration_revision:
            raise ValueError('sih_projection_calibration_binding_mismatch')
        for optical, expected in ((Vector3(1., 0., 0.), camera.right_body),
                                  (Vector3(0., 1., 0.), camera.down_body),
                                  (Vector3(0., 0., 1.), camera.forward_body)):
            actual = calibration.optical_to_body.rotate(optical)
            if any(not math.isclose(getattr(actual, axis), getattr(expected, axis), abs_tol=1e-9)
                   for axis in ('x', 'y', 'z')):
                raise ValueError('sih_projection_optical_mount_mismatch')
        width, height = calibration.image_size_px
        fx, fy = calibration.focal_length_px
        cx, cy = calibration.principal_point_px
        if not all(math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9) for actual, expected in (
                (2*fx*math.tan(math.radians(camera.horizontal_fov_deg)/2), width),
                (2*fy*math.tan(math.radians(camera.vertical_fov_deg)/2), height),
                (cx, (width-1)/2), (cy, (height-1)/2))):
            raise ValueError('sih_projection_intrinsics_fov_mismatch')
        self._calibration, self._binding = calibration, binding
        self._fixture_revision, self._clock = fixture_revision, clock
        self._image_age, self._attitude_age = max_observation_age_s, max_attitude_age_s
        self._poses = NativePoseFixture(binding=binding, clock=clock,
            max_observation_age_s=max_observation_age_s, max_attitude_age_s=max_attitude_age_s, allow_simulation=True)
        self._target = None
        self._output = self._measurement = self._sample = self._alignment = None
        self._previous_alignment = None
        self._output_timestamp = self._position_2d = None

    @property
    def last_sample(self) -> ExactSihSample | None:
        return self._sample

    @property
    def last_alignment(self) -> AlignedBearing | None:
        return self._alignment

    def project(self, packet: dict, state: AircraftState, target_ned: tuple[float, float, float], *, timestamp_s: float) -> TrackerOutput:
        """Project one progressing observed pose; timestamp_s is epoch/display time.

        CaptureStamp retains the native pose's monotonic receipt, not exposure
        time. This fixture waits for both pose and attitude source progress; that
        is a fixture choice, not a camera synchronization law. Partial/duplicate
        polls retain the original frame and its projected target until expiry.
        FOV describes synthetic pixel boundaries, not physical optics.
        """
        try:
            frame, progressing = self._poses.project(packet, state, target_ned, timestamp_s=timestamp_s)
            if not progressing:
                return self.retained_frame(state)[0]
            now = self._poses.now()
            identity, values, receipt, target = (frame.identity, (frame.position_ned, frame.quaternion_wxyz),
                                                frame.received_at_monotonic_s, frame.target_ned)
            normalized = self._camera.project(values[0], values[1], target)
            measurement = sample = alignment = position_2d = None
            if normalized is not None:
                width, height = self._calibration.image_size_px
                fx, fy = self._calibration.focal_length_px
                cx, cy = self._calibration.principal_point_px
                pixel = (cx + normalized[0]*fx*math.tan(math.radians(self._camera.horizontal_fov_deg)/2),
                         cy + normalized[1]*fy*math.tan(math.radians(self._camera.vertical_fov_deg)/2))
                if 0 <= pixel[0] <= width-1 and 0 <= pixel[1] <= height-1:
                    provenance = ObservationProvenance(self._binding.source_id, self._binding.target_generation,
                        self._binding.geometry_revision, self._binding.calibration_revision,
                        CaptureStamp(self._binding.source_epoch, str(identity[0]), receipt, 'fresh'))
                    measurement = ImageMeasurement(provenance, pixel, (width, height), (1., 0., 0., 0., 1., 0.), True)
                    bearing = image_to_body_bearing(measurement, self._calibration)
                    sample = ExactSihSample(provenance, state, self._binding.native_runtime_id, self._fixture_revision)
                    alignment = associate_sih_bearing(bearing, sample, binding=self._binding, now_monotonic_s=now,
                        max_observation_age_s=self._image_age, max_attitude_age_s=self._attitude_age,
                        previous=self._previous_alignment, allow_simulation=True)
                    position_2d = ((pixel[0]-width/2)/(width/2), (pixel[1]-height/2)/(height/2))
            visible = measurement is not None
            output = TrackerOutput(TrackerDataType.POSITION_2D, timestamp_s, visible,
                tracker_id='simulated_fixed_camera_bearing', position_2d=position_2d,
                confidence=1. if visible else None, target_id=self._binding.target_generation,
                image_measurement=measurement, raw_data={
                    'source': 'simulated_fixed_camera_bearing', 'has_output': visible,
                    'usable_for_following': visible, 'data_is_stale': False, 'identity_confirmed': visible,
                    'measurement_monotonic_s': receipt, 'measurement_time_basis': 'native_pose_receipt_for_sih_projection',
                    'measurement_target_ned': target if visible else None,
                    'pose_timestamp_us': identity[0], 'attitude_sample_timestamp_us': identity[1],
                    'attitude_publication_timestamp_us': state.attitude_timing.publication_timestamp_us,
                }, metadata={'simulation_only': True, 'fixture_revision': self._fixture_revision,
                             'association_kind': 'sih_projection_pair', 'timestamp_basis': 'supplied_display_epoch'})
            self._target = target
            self._output, self._measurement, self._sample, self._alignment = output, measurement, sample, alignment
            self._output_timestamp, self._position_2d = timestamp_s, position_2d
            if alignment is not None:
                self._previous_alignment = alignment
            return output
        except (ValueError, TypeError, KeyError):
            self._output = self._measurement = self._sample = self._alignment = None
            raise

    def _require_output(self, output):
        if (not isinstance(output, TrackerOutput) or output is not self._output
                or output.image_measurement is not self._measurement or output.timestamp != self._output_timestamp
                or output.position_2d != self._position_2d or output.target_id != self._binding.target_generation
                or output.data_type is not TrackerDataType.POSITION_2D
                or not isinstance(output.raw_data, dict)
                or output.raw_data.get('measurement_target_ned') != (self._target if self._measurement else None)):
            raise ValueError('sih_projection_output_unavailable_or_changed')

    def retained_frame(self, current_state: AircraftState) -> tuple[TrackerOutput, tuple[float, float, float] | None]:
        """Return the original frame and measured target without advancing clocks.

        An actual missing-target frame retains absence, with no measurement
        target. Current pose/target updates never alter this retained evidence.
        """
        self._poses.retained_frame(current_state)
        self._require_output(self._output)
        if self._alignment is not None:
            self.resolve(self._output, current_state)
        return self._output, self._target if self._measurement else None

    def resolve(self, output: TrackerOutput, current_state: AircraftState) -> AlignedBearing:
        """Validate current identity/age while retaining the original paired quaternion."""
        now = self._poses.now()
        self._poses.require_state(current_state, now)
        self._require_output(output)
        if self._alignment is None or self._sample is None or not evaluate_tracker_command_freshness(output)['usable_for_following']:
            raise ValueError('sih_projection_output_unavailable_or_changed')
        result = associate_sih_bearing(self._alignment.bearing, self._sample, binding=self._binding,
            now_monotonic_s=now, max_observation_age_s=self._image_age, max_attitude_age_s=self._attitude_age,
            previous=self._alignment, allow_simulation=True)
        require_current_bearing_association(result, self._measurement.provenance, current_state,
            native_runtime_id=self._binding.native_runtime_id, now_monotonic_s=now,
            max_observation_age_s=self._image_age, max_attitude_age_s=self._attitude_age)
        return result

    __call__ = resolve
