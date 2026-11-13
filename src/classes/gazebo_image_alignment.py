"""Read-only rendered-camera bearing adapter using actual raw PX4 samples."""

from collections import deque
import asyncio
import threading
import time

from classes.aircraft_state import AircraftState, AirframePhase, finite_number
from classes.fixed_camera_calibration import BoundFixedCameraCalibration
from classes.gazebo_capture import GazeboCameraSettings
from classes.guidance_observation import ImageMeasurement
from classes.image_bearing import image_to_body_bearing
from classes.observation_alignment import (
    AlignmentBinding, associate_source_timed_bearing, require_current_bearing_association,
)
from classes.source_time_alignment import SourceAttitudeSample, SourceTimeAssociation


class SourceAttitudeHistory:
    """Bounded connection-owned evidence, populated by existing native reads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._identity = None
        self._samples = deque(maxlen=256)

    def clear(self):
        with self._lock:
            self._identity = None
            self._samples.clear()

    def clear_if_current(self, binding, runtime_id):
        with self._lock:
            if self._identity is not None and self._identity[:2] == (binding, runtime_id):
                self._identity = None
                self._samples.clear()

    def commit(self, payload, state, *, runtime_id, source_clock_id):
        if not isinstance(state, AircraftState) or state.attitude_timing is None:
            self.clear()
            return False
        sample = SourceAttitudeSample.from_payload(payload)
        if (not isinstance(runtime_id, str) or not runtime_id or not isinstance(source_clock_id, str)
                or not source_clock_id or sample.quat_reset_counter != state.attitude_timing.quat_reset_counter):
            self.clear()
            return False
        identity = (state.binding, runtime_id, source_clock_id, sample.quat_reset_counter)
        with self._lock:
            if identity != self._identity:
                self._samples.clear()
                self._identity = identity
            if self._samples:
                previous, previous_state = self._samples[-1]
                if sample.sample_timestamp_us == previous.sample_timestamp_us:
                    if sample != previous:
                        self._samples.clear()
                        raise ValueError('source_attitude_sample_rewritten')
                    return False
                if (sample.sample_timestamp_us < previous.sample_timestamp_us
                        or sample.publication_timestamp_us < previous.publication_timestamp_us
                        or sample.received_at_monotonic_s <= previous.received_at_monotonic_s
                        or state.sequence < previous_state.sequence):
                    self._samples.clear()
                    raise ValueError('source_attitude_sample_reordered')
            self._samples.append((sample, state))
            return True

    def snapshot(self, *, binding, runtime_id, source_clock_id, reset_counter):
        with self._lock:
            if self._identity != (binding, runtime_id, source_clock_id, reset_counter):
                return ()
            return tuple(self._samples)


class GazeboImageBearingResolver:
    def __init__(self, settings, calibration, history, *, binding, runtime_id,
                 native_source_clock_id, timeout_s, clock=time.monotonic):
        if (not isinstance(settings, GazeboCameraSettings)
                or not isinstance(calibration, BoundFixedCameraCalibration)
                or not isinstance(history, SourceAttitudeHistory)
                or native_source_clock_id != settings.source_clock_id):
            raise ValueError('source_clock_domain_unqualified')
        self.settings = settings
        self.calibration = calibration
        self.history = history
        self.aircraft_binding = binding
        self.runtime_id = runtime_id
        self.timeout_s = timeout_s
        self.clock = clock
        self._previous = None
        self._measurement = None

    def __call__(self, output, current_state):
        measurement = getattr(output, 'image_measurement', None)
        if not isinstance(measurement, ImageMeasurement) or not measurement.measured:
            raise ValueError('image_measurement_unavailable')
        if (not isinstance(current_state, AircraftState) or current_state.binding != self.aircraft_binding
                or current_state.attitude_timing is None
                or not current_state.fresh(self.clock(), self.timeout_s)):
            raise ValueError('guidance_aircraft_binding_changed')
        provenance = measurement.provenance
        geometry = self.calibration.geometry
        if ((provenance.source_id, provenance.capture.source_epoch, provenance.geometry_revision,
             provenance.calibration_revision, measurement.image_to_calibration, measurement.image_size_px)
                != (geometry.runtime_stream_id, geometry.source_epoch, self.calibration.geometry_revision,
                    self.calibration.calibration_revision, self.calibration.image_to_calibration,
                    geometry.analysis_size_px)):
            raise ValueError('guidance_image_geometry_changed')
        sample = provenance.capture.source_sample
        if sample is None or sample.clock_id != self.settings.source_clock_id:
            raise ValueError('source_clock_domain_unqualified')
        candidates = self.history.snapshot(binding=self.aircraft_binding, runtime_id=self.runtime_id,
            source_clock_id=self.settings.source_clock_id, reset_counter=current_state.attitude_timing.quat_reset_counter)
        if not candidates:
            raise ValueError('source_attitude_alignment_unavailable')
        previous = self._previous
        if previous is not None and provenance.target_generation != previous.binding.target_generation:
            if provenance.target_generation < previous.binding.target_generation:
                raise ValueError('guidance_target_generation_obsolete')
            previous = None
        if previous is not None and provenance.capture.capture_id == previous.bearing.provenance.capture.capture_id:
            if measurement != self._measurement:
                raise ValueError('guidance_capture_rewritten')
            require_current_bearing_association(previous, provenance, current_state,
                native_runtime_id=self.runtime_id, now_monotonic_s=self.clock(),
                max_observation_age_s=self.timeout_s, max_attitude_age_s=self.timeout_s)
            return previous
        candidates = [(attitude, state) for attitude, state in candidates
            if attitude.fresh(self.clock(), self.timeout_s) and state.fresh(self.clock(), self.timeout_s)
            and abs(attitude.sample_timestamp_us - sample.timestamp_us) * 1e-6 <= self.settings.max_attitude_skew_s]
        if not candidates:
            raise ValueError('source_attitude_alignment_unavailable')
        attitude, state = min(candidates,
            key=lambda pair: (abs(pair[0].sample_timestamp_us - sample.timestamp_us), pair[0].sample_timestamp_us))
        alignment = SourceTimeAssociation(sample, attitude, self.settings.source_clock_id,
                                          self.settings.max_attitude_skew_s)
        bearing = image_to_body_bearing(measurement, self.calibration.calibration)
        binding = AlignmentBinding(provenance.source_id, provenance.capture.source_epoch,
            provenance.geometry_revision, provenance.calibration_revision, provenance.target_generation,
            self.aircraft_binding, self.runtime_id, attitude.quat_reset_counter)
        result = associate_source_timed_bearing(bearing, state, native_runtime_id=self.runtime_id,
            binding=binding, now_monotonic_s=self.clock(), max_observation_age_s=self.timeout_s,
            max_attitude_age_s=self.timeout_s, source_time=alignment,
            evidence_revision='gazebo-px4-source-clock-v1:' + self.settings.source_clock_id, previous=previous)
        require_current_bearing_association(result, provenance, current_state,
            native_runtime_id=self.runtime_id, now_monotonic_s=self.clock(),
            max_observation_age_s=self.timeout_s, max_attitude_age_s=self.timeout_s)
        self._previous, self._measurement = result, measurement
        return result


def _runtime_image_resolver(app, state, capabilities):
    video = getattr(app, 'video_handler', None)
    capture = getattr(video, 'cap', None)
    settings = getattr(capture, 'settings', None)
    calibration = getattr(app, '_image_calibration_binding', None)
    if (not isinstance(settings, GazeboCameraSettings)
            or not isinstance(calibration, BoundFixedCameraCalibration)
            or video._capture_source_signature(capture) != calibration.geometry.source_signature):
        raise ValueError('physical_capture_timing_unqualified')
    connection = app.px4_interface
    timeout = connection.get_telemetry_stale_timeout_s()
    return GazeboImageBearingResolver(settings, calibration, getattr(connection, 'source_attitude_history', None),
        binding=state.binding, runtime_id=capabilities.runtime_id,
        native_source_clock_id=getattr(capabilities, 'source_clock_id', None), timeout_s=timeout)


def native_image_guidance_readiness(app, profile, state):
    """Expose the same image/clock gate before an operator presses Start."""
    if (state is None or state.phase is not AirframePhase.FIXED_WING
            or 'POSITION_2D' not in profile.required_tracker_data
            or dict(profile.native_phase_contracts).get('fixed_wing') != 'fixed_wing_external'):
        return {'ready': True, 'reason_code': None}
    try:
        client = getattr(app.px4_interface, 'native_guidance_client', None)
        capabilities = None if client is None else client.capabilities
        if capabilities is None:
            raise ValueError('native_aircraft_state_unavailable')
        resolver = _runtime_image_resolver(app, state, capabilities)
        resolver(app.get_tracker_output(), state)
    except ValueError as error:
        return {'ready': False, 'reason_code': str(error)}
    return {'ready': True, 'reason_code': None}


async def bind_native_image_resolver(app, concrete, state, capabilities):
    """Prepare declared image-bearing input, using only bounded read-only waits."""
    bind = getattr(concrete, 'bind_guidance_input_resolver', None)
    required = concrete.setpoint_handler.profile_config.get('required_tracker_data', [])
    if (not callable(bind) or 'POSITION_2D' not in required
            or state.phase is not AirframePhase.FIXED_WING):
        return
    connection = app.px4_interface
    client = connection.native_guidance_client
    resolver = _runtime_image_resolver(app, state, capabilities)
    # Waiting for the first qualified pair is observation only. The original
    # Start context is retained independently and rechecked before acquisition.
    deadline = time.monotonic() + client.request_timeout_s
    update_rate = finite_number(concrete.update_rate, 'guidance_input_update_rate')
    if update_rate <= 0:
        raise ValueError('guidance_input_update_rate_invalid')
    period = 1. / update_rate
    while True:
        try:
            resolver(app.get_tracker_output(), connection.get_aircraft_state())
            break
        except ValueError as error:
            if str(error) != 'source_attitude_alignment_unavailable' or time.monotonic() >= deadline:
                raise
        await asyncio.sleep(min(period, max(0., deadline - time.monotonic())))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('source_attitude_alignment_unavailable')
        try:
            await asyncio.wait_for(connection.prepare_native_guidance(client.socket_path), timeout=remaining)
        except TimeoutError as error:
            raise ValueError('source_attitude_alignment_unavailable') from error
        if time.monotonic() >= deadline:
            raise ValueError('source_attitude_alignment_unavailable')
    bind(resolver)
