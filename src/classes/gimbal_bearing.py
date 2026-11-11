"""Observed boresight to physical-body bearing; no image or exposure fiction."""

from classes.aircraft_state import Vector3
from classes.gimbal_geometry import AngleGeometry, body_line_of_sight
from classes.gimbal_types import GimbalAngleObservation
from classes.guidance_observation import CalibratedBearing


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
