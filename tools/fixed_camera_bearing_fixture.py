"""Isolated-SIH synthetic image bearings from actual retained native pose.

No camera, network, aircraft command, or flight model is owned here. The caller
supplies independent target truth and both explicit synthetic camera models.
Create a new fixture for a new source/target/runtime/reset binding.
"""

from dataclasses import asdict
import math
from typing import Callable

from classes.aircraft_state import AircraftState, Quaternion, Vector3, finite_number
from classes.frame_publisher import CaptureStamp
from classes.guidance_observation import ImageMeasurement, ObservationProvenance, PinholeCalibration
from classes.image_bearing import image_to_body_bearing
from classes.observation_alignment import AlignedBearing, AlignmentBinding, ExactSihSample, associate_sih_bearing
from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.tracker_runtime_status import evaluate_tracker_command_freshness
from tools.fixed_camera_world_target import FixedCamera


class FixedCameraBearingFixture:
    """One explicit simulated source binding, with a read-only bearing resolver."""

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
        self._pose_identity = self._target = None
        self._observed_identity = self._observed_values = None
        self._output = self._measurement = self._sample = self._alignment = None
        self._previous_alignment = None
        self._output_timestamp = self._position_2d = None
        self._frame_state = self._pose_receipt = None
        self._invalidated = False

    @property
    def last_sample(self) -> ExactSihSample | None:
        return self._sample

    @property
    def last_alignment(self) -> AlignedBearing | None:
        return self._alignment

    def _require_state(self, state, now):
        if (not isinstance(state, AircraftState) or state.binding != self._binding.aircraft_binding
                or state.attitude_timing is None
                or state.attitude_timing.quat_reset_counter != self._binding.quat_reset_counter):
            self._invalidated = True
            raise ValueError('sih_projection_aircraft_binding_changed')
        if self._frame_state is not None and state.source != self._frame_state.source:
            self._invalidated = True
            raise ValueError('sih_projection_aircraft_source_changed')
        if not state.fresh(now, self._attitude_age) or not state.attitude_timing.fresh(now, self._attitude_age):
            raise ValueError('sih_projection_attitude_stale')

    def _pose(self, packet, state, now):
        try:
            return self._decode_pose(packet, state, now)
        except (ValueError, TypeError, KeyError) as error:
            if str(error) not in {'sih_projection_attitude_stale', 'sih_projection_pose_stale',
                                  'sih_projection_native_state_unavailable'}:
                self._invalidated = True
            raise

    def _decode_pose(self, packet, state, now):
        self._require_state(state, now)
        if not isinstance(packet, dict) or packet.get('runtime_id') != self._binding.native_runtime_id:
            raise ValueError('sih_projection_native_packet_invalid')
        if packet.get('fresh') is False:
            raise ValueError('sih_projection_native_state_unavailable')
        if packet.get('fresh') is not True:
            raise ValueError('sih_projection_native_packet_invalid')
        payload = packet.get('aircraft_state')
        if not isinstance(payload, dict) or packet.get('attitude_timing') != asdict(state.attitude_timing):
            raise ValueError('sih_projection_native_state_mismatch')
        decoded = dict(payload)
        if decoded.get('attitude_timing') is None:
            decoded['attitude_timing'] = packet['attitude_timing']
        if AircraftState.from_payload(decoded) != state:
            raise ValueError('sih_projection_native_state_mismatch')
        pose = packet.get('vehicle_pose')
        if not isinstance(pose, dict) or pose.get('source') != 'px4_dds_observed':
            raise ValueError('sih_projection_pose_unavailable')
        received = finite_number(pose.get('observed_at_monotonic_s'), 'sih_pose_receipt')
        if received < 0 or not 0 <= now-received <= min(self._image_age, self._attitude_age):
            raise ValueError('sih_projection_pose_stale')
        position, raw_q = pose.get('vehicle_ned'), pose.get('quaternion_wxyz')
        if (not isinstance(position, (list, tuple)) or len(position) != 3
                or not isinstance(raw_q, (list, tuple)) or len(raw_q) != 4):
            raise ValueError('sih_projection_pose_invalid')
        position = tuple(finite_number(value, 'sih_pose_position') for value in position)
        quaternion = Quaternion(*raw_q)
        if quaternion != state.attitude_body_to_ned:
            raise ValueError('sih_projection_physical_quaternion_mismatch')
        timestamp = pose.get('px4_timestamp_us')
        if type(timestamp) is not int or not 0 < timestamp < 2**64:
            raise ValueError('sih_projection_pose_timestamp_invalid')
        identity = (timestamp, state.attitude_timing.sample_timestamp_us)
        return identity, (position, tuple(raw_q)), received

    def project(self, packet: dict, state: AircraftState, target_ned: tuple[float, float, float], *, timestamp_s: float) -> TrackerOutput:
        """Project one progressing observed pose; timestamp_s is epoch/display time.

        CaptureStamp retains the native pose's monotonic receipt, not exposure
        time. This fixture waits for both pose and attitude source progress; that
        is a fixture choice, not a camera synchronization law. Partial/duplicate
        polls retain the original frame and its projected target until expiry.
        FOV describes synthetic pixel boundaries, not physical optics.
        """
        try:
            if self._invalidated:
                raise ValueError('sih_projection_owner_invalidated')
            now = finite_number(self._clock(), 'sih_projection_clock')
            if finite_number(timestamp_s, 'sih_projection_display_epoch') <= 0:
                raise ValueError('sih_projection_display_epoch_invalid')
            if not isinstance(target_ned, tuple) or len(target_ned) != 3:
                raise ValueError('sih_projection_target_invalid')
            target = tuple(finite_number(value, 'sih_target_ned') for value in target_ned)
            identity, values, receipt = self._pose(packet, state, now)
            if self._observed_identity is not None:
                if any(current < before for current, before in zip(identity, self._observed_identity)):
                    self._invalidated = True
                    raise ValueError('sih_projection_pose_reordered')
                if any(current == before and value != old for current, before, value, old in
                       zip(identity, self._observed_identity, values, self._observed_values)):
                    self._invalidated = True
                    raise ValueError('sih_projection_pose_rewritten')
            self._observed_identity, self._observed_values = identity, values
            if self._pose_identity is not None:
                if not all(current > before for current, before in zip(identity, self._pose_identity)):
                    return self.retained_frame(state)[0]
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
            self._pose_identity, self._target = identity, target
            self._output, self._measurement, self._sample, self._alignment = output, measurement, sample, alignment
            self._output_timestamp, self._position_2d = timestamp_s, position_2d
            self._frame_state, self._pose_receipt = state, receipt
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
        if self._invalidated:
            raise ValueError('sih_projection_owner_invalidated')
        now = finite_number(self._clock(), 'sih_projection_clock')
        self._require_state(current_state, now)
        self._require_output(self._output)
        self._require_state(self._frame_state, now)
        if current_state.source != self._frame_state.source:
            self._invalidated = True
            raise ValueError('sih_projection_aircraft_source_changed')
        if not 0 <= now-self._pose_receipt <= self._image_age:
            raise ValueError('sih_projection_frame_stale')
        if self._alignment is not None:
            self.resolve(self._output, current_state)
        return self._output, self._target if self._measurement else None

    def resolve(self, output: TrackerOutput, current_state: AircraftState) -> AlignedBearing:
        """Validate current identity/age while retaining the original paired quaternion."""
        if self._invalidated:
            raise ValueError('sih_projection_owner_invalidated')
        now = finite_number(self._clock(), 'sih_projection_clock')
        self._require_state(current_state, now)
        self._require_output(output)
        if self._alignment is None or self._sample is None or not evaluate_tracker_command_freshness(output)['usable_for_following']:
            raise ValueError('sih_projection_output_unavailable_or_changed')
        if current_state.source != self._sample.aircraft_state.source:
            self._invalidated = True
            raise ValueError('sih_projection_aircraft_source_changed')
        return associate_sih_bearing(self._alignment.bearing, self._sample, binding=self._binding,
            now_monotonic_s=now, max_observation_age_s=self._image_age, max_attitude_age_s=self._attitude_age,
            previous=self._alignment, allow_simulation=True)

    __call__ = resolve
