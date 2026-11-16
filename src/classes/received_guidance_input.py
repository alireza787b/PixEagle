"""Read-only stock camera input adapters over canonical geometry and receipts."""

import time

from classes.aircraft_state import AircraftState, AirframePhase
from classes.fixed_camera_calibration import BoundFixedCameraCalibration
from classes.gimbal_bearing import ReceivedGimbalBearingResolver
from classes.gimbal_geometry import resolve_angle_geometry, resolve_mount_type
from classes.guidance_observation import ImageMeasurement
from classes.image_bearing import image_to_body_bearing
from classes.mavlink_vector_guidance_session import MavlinkGuidanceCapabilities
from classes.observation_alignment import associate_latest_received_bearing


class ReceivedImageBearingResolver:
    def __init__(self, calibration, *, binding, runtime_id, timeout_s, clock=time.monotonic):
        if not isinstance(calibration, BoundFixedCameraCalibration):
            raise ValueError("camera_calibration_required")
        self.calibration = calibration
        self.binding, self.runtime_id, self.timeout_s, self.clock = binding, runtime_id, timeout_s, clock
        self._previous = None

    def __call__(self, output, state):
        measurement = getattr(output, "image_measurement", None)
        if not isinstance(measurement, ImageMeasurement):
            raise ValueError("image_measurement_unavailable")
        if not isinstance(state, AircraftState) or state.binding != self.binding or state.attitude_timing is not None:
            raise ValueError("guidance_aircraft_binding_changed")
        provenance, geometry = measurement.provenance, self.calibration.geometry
        if ((provenance.source_id, provenance.capture.source_epoch, provenance.geometry_revision,
             provenance.calibration_revision, measurement.image_to_calibration, measurement.image_size_px)
                != (geometry.runtime_stream_id, geometry.source_epoch, self.calibration.geometry_revision,
                    self.calibration.calibration_revision, self.calibration.image_to_calibration, geometry.analysis_size_px)):
            raise ValueError("guidance_image_geometry_changed")
        previous = self._previous
        if previous is not None and provenance.target_generation != previous.binding.target_generation:
            if provenance.target_generation < previous.binding.target_generation:
                raise ValueError("guidance_target_generation_obsolete")
            previous = None
        bearing = image_to_body_bearing(measurement, self.calibration.calibration)
        result = associate_latest_received_bearing(bearing, state, native_runtime_id=self.runtime_id,
            now_monotonic_s=self.clock(), max_observation_age_s=self.timeout_s,
            max_attitude_age_s=self.timeout_s, previous=previous)
        self._previous = result
        return result


def _runtime_resolver(app, state, capabilities, required):
    connection = app.px4_interface
    timeout = connection.get_telemetry_stale_timeout_s()
    if "GIMBAL_ANGLES" in required:
        runtime = getattr(app, "camera_runtime", None)
        provider = getattr(runtime, "provider", None)
        if provider is None:
            raise ValueError("gimbal_observation_unavailable")
        config = runtime.settings
        mount = resolve_mount_type(config, {}, {}, allowed=("HORIZONTAL", "VERTICAL"))
        return ReceivedGimbalBearingResolver(source=runtime.angle_observation_context(), provider_id=provider.provider_id,
            mount=mount, geometry=resolve_angle_geometry(config, mount), binding=state.binding,
            runtime_id=capabilities.runtime_id, timeout_s=timeout)
    if "POSITION_2D" in required:
        calibration = getattr(app, "_image_calibration_binding", None)
        video = getattr(app, "video_handler", None)
        capture = getattr(video, "cap", None)
        if (not isinstance(calibration, BoundFixedCameraCalibration) or capture is None
                or video._capture_source_signature(capture) != calibration.geometry.source_signature):
            raise ValueError("camera_calibration_required")
        return ReceivedImageBearingResolver(calibration, binding=state.binding, runtime_id=capabilities.runtime_id, timeout_s=timeout)
    raise ValueError("guidance_bearing_adapter_unavailable")


def airframe_input_readiness(app, profile, state):
    if state is None or state.phase is not AirframePhase.FIXED_WING:
        return {"ready": True, "reason_code": None}
    capabilities = app.px4_interface.guidance_capabilities
    if not isinstance(capabilities, MavlinkGuidanceCapabilities):
        from classes.gazebo_guidance_alignment import native_guidance_input_readiness
        return native_guidance_input_readiness(app, profile, state)
    try:
        _runtime_resolver(app, state, capabilities, profile.required_tracker_data)(app.get_tracker_output(), state)
    except ValueError as error:
        return {"ready": False, "reason_code": str(error)}
    return {"ready": True, "reason_code": None}


async def bind_airframe_input_resolver(app, concrete, state, capabilities, *, validate_input):
    if not isinstance(capabilities, MavlinkGuidanceCapabilities):
        from classes.gazebo_guidance_alignment import bind_native_input_resolver
        await bind_native_input_resolver(app, concrete, state, capabilities, validate_input=validate_input)
        return
    if state.phase is not AirframePhase.FIXED_WING:
        return
    validate_input()
    resolver = _runtime_resolver(app, state, capabilities, concrete.setpoint_handler.profile_config["required_tracker_data"])
    resolver(app.get_tracker_output(), state)
    validate_input()
    concrete.bind_guidance_input_resolver(resolver)
