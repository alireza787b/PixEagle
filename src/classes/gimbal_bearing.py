"""Observed boresight to physical-body bearing; no image or exposure fiction."""

import time

from classes.aircraft_state import AircraftState, Vector3
from classes.gimbal_geometry import AngleGeometry, angle_geometry_revision, body_line_of_sight
from classes.gimbal_types import GimbalAngleObservation
from classes.guidance_observation import CalibratedBearing
from classes.observation_alignment import associate_latest_received_bearing


def gimbal_to_body_bearing(
    observation: GimbalAngleObservation, *, mount_type: str,
    geometry: AngleGeometry, geometry_revision: str,
) -> CalibratedBearing:
    """Use the same owned mapping as the tracker, never reinterpret raw axes.

    The caller retains the expected mapping revision. Agreement establishes
    convention/identity only; acquisition timing still needs separate evidence.
    """
    if not isinstance(observation, GimbalAngleObservation) or not isinstance(geometry, AngleGeometry):
        raise ValueError("gimbal_bearing_contract_invalid")
    if observation.geometry_revision != geometry_revision:
        raise ValueError("gimbal_bearing_geometry_changed")
    ray = Vector3(*body_line_of_sight(observation.angles_deg, mount_type, geometry))
    return CalibratedBearing(observation, ray.normalized())


class ReceivedGimbalBearingResolver:
    """Stock receipt-based boresight adapter; no range or exposure-time claim."""

    def __init__(self, *, source, provider_id, mount, geometry, binding, runtime_id, timeout_s, clock=time.monotonic):
        self.source, self.provider_id, self.mount, self.geometry = source, provider_id, mount, geometry
        self.aircraft_binding, self.runtime_id = binding, runtime_id
        self.geometry_revision = angle_geometry_revision(provider_id, mount, geometry)
        self.timeout_s, self.clock = timeout_s, clock
        self._previous = None

    def __call__(self, output, current_state):
        observation = getattr(output, 'gimbal_observation', None)
        if not isinstance(observation, GimbalAngleObservation):
            raise ValueError('gimbal_observation_unavailable')
        if (self.source is None or observation.source != self.source or observation.provider_id != self.provider_id
                or observation.geometry_revision != self.geometry_revision or observation.target_generation is None):
            raise ValueError('guidance_gimbal_binding_changed')
        if (not isinstance(current_state, AircraftState) or current_state.binding != self.aircraft_binding
                or current_state.attitude_timing is not None):
            raise ValueError('guidance_aircraft_binding_changed')
        previous = self._previous
        if previous is not None and observation.target_generation != previous.binding.target_generation:
            if observation.target_generation < previous.binding.target_generation:
                raise ValueError('guidance_target_generation_obsolete')
            previous = None
        bearing = gimbal_to_body_bearing(observation, mount_type=self.mount,
            geometry=self.geometry, geometry_revision=self.geometry_revision)
        result = associate_latest_received_bearing(bearing, current_state,
            native_runtime_id=self.runtime_id, now_monotonic_s=self.clock(),
            max_observation_age_s=self.timeout_s, max_attitude_age_s=self.timeout_s, previous=previous)
        self._previous = result
        return result
