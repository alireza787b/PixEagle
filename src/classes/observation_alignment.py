"""Explicit bearing/attitude associations without acquisition clocks or authority.

Receipt times remain receipts. Bounded receive-time qualification requires
independently established total-delay bounds; exact SIH pairing describes only
a bearing projected from a retained observed state, never hardware synchronization.
"""

from dataclasses import dataclass, replace
import math

from classes.aircraft_state import AircraftBinding, AircraftState, Vector3, finite_number, preserves_attitude_sample
from classes.gimbal_types import GimbalAngleObservation
from classes.guidance_observation import CalibratedBearing, ObservationProvenance, bearing_receipt
from classes.source_time_alignment import SourceTimeAssociation


def _identity(value: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError("alignment_identity_invalid")


def _positive(value: float, name: str) -> float:
    value = finite_number(value, name)
    if value <= 0:
        raise ValueError(f"{name}_not_positive")
    return value


def _delay_interval(value: tuple[float, float]) -> None:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError("alignment_delay_interval_invalid")
    lower, upper = (finite_number(item, "alignment_delay") for item in value)
    if not 0 <= lower <= upper:
        raise ValueError("alignment_delay_interval_invalid")


@dataclass(frozen=True)
class AlignmentBinding:
    source_id: str
    source_epoch: str | int
    geometry_revision: str
    calibration_revision: str | None
    target_generation: int
    aircraft_binding: AircraftBinding
    native_runtime_id: str
    quat_reset_counter: int
    provider_id: str | None = None

    def __post_init__(self):
        for name in ("source_id", "geometry_revision", "native_runtime_id"):
            _identity(getattr(self, name))
        if type(self.source_epoch) is int:
            if self.source_epoch < 0 or self.calibration_revision is not None:
                raise ValueError("alignment_gimbal_source_invalid")
            _identity(self.provider_id)
        else:
            _identity(self.source_epoch)
            _identity(self.calibration_revision)
            if self.provider_id is not None:
                raise ValueError("alignment_image_provider_invalid")
        if type(self.target_generation) is not int or self.target_generation < 0:
            raise ValueError("alignment_target_generation_invalid")
        if not isinstance(self.aircraft_binding, AircraftBinding):
            raise ValueError("alignment_aircraft_binding_invalid")
        if type(self.quat_reset_counter) is not int or not 0 <= self.quat_reset_counter <= 255:
            raise ValueError("alignment_reset_counter_invalid")


@dataclass(frozen=True)
class ReceiveTimeBounds:
    """Measured total delays and relative-clock error for this exact binding.

    observation_delay_s bounds acquisition to backend receipt. The attitude interval
    bounds sample acquisition to this packet's publication receipt, including
    source processing, republishing and transport. Evidence is supplied by the
    caller; this module cannot establish those bounds from timestamps alone.
    """

    binding: AlignmentBinding
    observation_delay_s: tuple[float, float]
    attitude_sample_to_publication_receipt_s: tuple[float, float]
    relative_clock_uncertainty_s: float
    max_skew_s: float
    evidence_revision: str

    def __post_init__(self):
        if not isinstance(self.binding, AlignmentBinding):
            raise ValueError("alignment_binding_invalid")
        _delay_interval(self.observation_delay_s)
        _delay_interval(self.attitude_sample_to_publication_receipt_s)
        if finite_number(self.relative_clock_uncertainty_s, "alignment_clock_uncertainty") < 0:
            raise ValueError("alignment_clock_uncertainty_negative")
        _positive(self.max_skew_s, "alignment_max_skew")
        _identity(self.evidence_revision)


@dataclass(frozen=True)
class ExactSihSample:
    """Retained projection inputs, constructed by an isolated SIH fixture only."""

    observation_provenance: ObservationProvenance | GimbalAngleObservation
    aircraft_state: AircraftState
    native_runtime_id: str
    fixture_revision: str

    def __post_init__(self):
        if (not isinstance(self.observation_provenance, (ObservationProvenance, GimbalAngleObservation))
                or not isinstance(self.aircraft_state, AircraftState)):
            raise ValueError("sih_projection_pair_invalid")
        bearing_receipt(self.observation_provenance)
        _identity(self.native_runtime_id)
        _identity(self.fixture_revision)


@dataclass(frozen=True)
class AlignedBearing:
    binding: AlignmentBinding
    bearing: CalibratedBearing
    attitude_state: AircraftState
    direction_ned: Vector3
    association_kind: str
    evidence_revision: str
    worst_case_skew_s: float | None
    receive_bounds: ReceiveTimeBounds | None
    source_time: SourceTimeAssociation | None = None

    def __post_init__(self):
        if (not isinstance(self.binding, AlignmentBinding) or not isinstance(self.bearing, CalibratedBearing)
                or not isinstance(self.attitude_state, AircraftState) or not isinstance(self.direction_ned, Vector3)):
            raise ValueError("aligned_bearing_contract_invalid")
        observation, binding, state = bearing_receipt(self.bearing.provenance), self.binding, self.attitude_state
        if ((observation.source_id, observation.source_epoch, observation.geometry_revision,
             observation.calibration_revision, observation.target_generation, observation.provider_id)
                != (binding.source_id, binding.source_epoch, binding.geometry_revision,
                    binding.calibration_revision, binding.target_generation, binding.provider_id)
                or observation.state != "fresh" or state.binding != binding.aircraft_binding
                or state.attitude_timing is None
                or state.attitude_timing.quat_reset_counter != binding.quat_reset_counter):
            raise ValueError("aligned_bearing_binding_invalid")
        if (isinstance(self.bearing.provenance, GimbalAngleObservation)
                and self.bearing.provenance.tracking_state != "TRACKING_ACTIVE"):
            raise ValueError("aligned_bearing_tracking_invalid")
        if not math.isclose(self.direction_ned.magnitude, 1., rel_tol=0., abs_tol=1e-9):
            raise ValueError("aligned_bearing_direction_not_unit")
        source_time = self.source_time
        if self.association_kind == 'bounded_source_time':
            if (not isinstance(source_time, SourceTimeAssociation)
                    or not isinstance(self.bearing.provenance, ObservationProvenance)
                    or self.bearing.provenance.capture.source_sample != source_time.source_sample
                    or source_time.attitude.quat_reset_counter != binding.quat_reset_counter):
                raise ValueError('aligned_bearing_source_time_invalid')
            quaternion = source_time.attitude.quaternion
        else:
            if source_time is not None:
                raise ValueError('aligned_bearing_unexpected_source_time')
            quaternion = state.attitude_body_to_ned
        expected = quaternion.rotate(self.bearing.direction_body_frd).normalized()
        if any(not math.isclose(getattr(self.direction_ned, name), getattr(expected, name),
                                rel_tol=0., abs_tol=1e-9) for name in ("x", "y", "z")):
            raise ValueError("aligned_bearing_direction_mismatch")
        _identity(self.evidence_revision)
        if self.association_kind == "bounded_receive_time":
            bounds = self.receive_bounds
            if (not isinstance(bounds, ReceiveTimeBounds) or bounds.binding != binding
                    or bounds.evidence_revision != self.evidence_revision):
                raise ValueError("aligned_bearing_receive_bounds_invalid")
            skew = finite_number(self.worst_case_skew_s, "aligned_bearing_skew")
            expected_skew = _receive_intervals(self.bearing, state, bounds)[2]
            if (not 0 <= skew <= bounds.max_skew_s
                    or not math.isclose(skew, expected_skew, rel_tol=0., abs_tol=1e-12)):
                raise ValueError("aligned_bearing_skew_invalid")
        elif self.association_kind == "sih_projection_pair":
            if self.receive_bounds is not None or self.worst_case_skew_s is not None:
                raise ValueError("aligned_bearing_sih_qualification_invalid")
        elif self.association_kind == 'bounded_source_time':
            if (self.receive_bounds is not None or self.worst_case_skew_s != source_time.skew_s):
                raise ValueError('aligned_bearing_source_time_invalid')
        else:
            raise ValueError("aligned_bearing_kind_invalid")


def _validate_pair(
    bearing, state, native_runtime_id, binding, now, observation_age, attitude_age,
) -> None:
    if (not isinstance(bearing, CalibratedBearing) or not isinstance(state, AircraftState)
            or not isinstance(binding, AlignmentBinding)):
        raise ValueError("alignment_contract_invalid")
    now = finite_number(now, "alignment_clock")
    _positive(observation_age, "alignment_observation_age_limit")
    _positive(attitude_age, "alignment_attitude_age_limit")
    receipt = bearing_receipt(bearing.provenance)
    if ((receipt.source_id, receipt.source_epoch, receipt.geometry_revision,
         receipt.calibration_revision, receipt.target_generation, receipt.provider_id)
            != (binding.source_id, binding.source_epoch, binding.geometry_revision,
                binding.calibration_revision, binding.target_generation, binding.provider_id)):
        raise ValueError("alignment_observation_binding_changed")
    if receipt.state != "fresh":
        raise ValueError("alignment_observation_not_fresh")
    if not 0 <= now - receipt.received_at_monotonic_s <= observation_age:
        raise ValueError("alignment_observation_receipt_stale_or_future")
    if isinstance(bearing.provenance, GimbalAngleObservation):
        observation = bearing.provenance
        if (observation.tracking_state != "TRACKING_ACTIVE"
                or observation.tracking_received_at_monotonic_s is None
                or not 0 <= now - observation.tracking_received_at_monotonic_s <= observation_age):
            raise ValueError("alignment_gimbal_tracking_unqualified")
    if state.binding != binding.aircraft_binding or native_runtime_id != binding.native_runtime_id:
        raise ValueError("alignment_aircraft_or_runtime_changed")
    timing = state.attitude_timing
    if timing is None:
        raise ValueError("alignment_attitude_timing_unavailable")
    if timing.quat_reset_counter != binding.quat_reset_counter:
        raise ValueError("alignment_attitude_reset_changed")
    if not state.fresh(now, attitude_age) or not timing.fresh(now, attitude_age):
        raise ValueError("alignment_attitude_stale")


def _result(bearing, state, binding, kind, evidence, skew, bounds, previous, source_time=None) -> AlignedBearing:
    if previous is not None:
        if not isinstance(previous, AlignedBearing) or previous.binding != binding:
            raise ValueError("alignment_binding_changed")
        if (kind != previous.association_kind or evidence != previous.evidence_revision
                or bounds != previous.receive_bounds):
            raise ValueError("alignment_qualification_changed")
        if source_time is not None:
            old_time = previous.source_time
            if (old_time is None or source_time.declared_clock_id != old_time.declared_clock_id
                    or source_time.maximum_skew_s != old_time.maximum_skew_s
                    or source_time.source_sample.source_incarnation != old_time.source_sample.source_incarnation
                    or source_time.attitude.sample_timestamp_us < old_time.attitude.sample_timestamp_us
                    or source_time.attitude.received_at_monotonic_s < old_time.attitude.received_at_monotonic_s
                    or (source_time.attitude.sample_timestamp_us == old_time.attitude.sample_timestamp_us
                        and source_time.attitude != old_time.attitude)):
                raise ValueError('alignment_source_time_changed_or_reordered')
        before = bearing_receipt(previous.bearing.provenance)
        current = bearing_receipt(bearing.provenance)
        if isinstance(bearing.provenance, GimbalAngleObservation):
            old = previous.bearing.provenance
            if (not isinstance(old, GimbalAngleObservation)
                    or bearing.provenance.tracking_received_at_monotonic_s < old.tracking_received_at_monotonic_s):
                raise ValueError("alignment_tracking_receipt_reordered")
        if current.sample_id == before.sample_id:
            comparable = bearing
            if isinstance(bearing.provenance, GimbalAngleObservation):
                # TRC progresses independently; it cannot refresh/rotate GAC.
                comparable = replace(bearing, provenance=replace(bearing.provenance,
                    tracking_state=old.tracking_state,
                    tracking_received_at_monotonic_s=old.tracking_received_at_monotonic_s))
            if (comparable != previous.bearing or state != previous.attitude_state
                    or source_time != previous.source_time):
                raise ValueError("alignment_capture_rewritten")
            return previous if bearing == previous.bearing else replace(previous, bearing=bearing)
        if current.received_at_monotonic_s <= before.received_at_monotonic_s:
            raise ValueError("alignment_capture_reordered")
        if (str(current.sample_id).isdecimal() and str(before.sample_id).isdecimal()
                and int(current.sample_id) < int(before.sample_id)):
            raise ValueError("alignment_capture_reordered")
        old_state = previous.attitude_state
        old, new = old_state.attitude_timing, state.attitude_timing
        if (state.source != old_state.source or state.sequence < old_state.sequence
                or state.observed_at_monotonic_s < old_state.observed_at_monotonic_s
                or (state.sequence == old_state.sequence and state != old_state)
                or new.publication_timestamp_us < old.publication_timestamp_us
                or new.sample_timestamp_us < old.sample_timestamp_us
                or new.publication_received_at_monotonic_s < old.publication_received_at_monotonic_s
                or new.sample_received_at_monotonic_s < old.sample_received_at_monotonic_s
                or (new.publication_timestamp_us == old.publication_timestamp_us
                    and new.sample_timestamp_us == old.sample_timestamp_us
                    and (new != old or state.attitude_body_to_ned != old_state.attitude_body_to_ned))
                or not preserves_attitude_sample(old, old_state.attitude_body_to_ned,
                                                 new, state.attitude_body_to_ned)):
            raise ValueError("alignment_attitude_reordered_or_rewritten")
    quaternion = state.attitude_body_to_ned if source_time is None else source_time.attitude.quaternion
    direction = quaternion.rotate(bearing.direction_body_frd).normalized()
    return AlignedBearing(binding, bearing, state, direction, kind, evidence, skew, bounds, source_time)


def _receive_intervals(bearing, attitude_state, bounds) -> tuple[tuple, tuple, float]:
    timing = attitude_state.attitude_timing
    processing = (timing.publication_timestamp_us - timing.sample_timestamp_us) * 1e-6
    lower, upper = bounds.attitude_sample_to_publication_receipt_s
    lower = max(lower, processing)
    if lower > upper:
        raise ValueError("alignment_attitude_delay_contradicts_processing")
    camera_receipt = bearing_receipt(bearing.provenance).received_at_monotonic_s
    camera = (camera_receipt - bounds.observation_delay_s[1], camera_receipt - bounds.observation_delay_s[0])
    attitude = (timing.publication_received_at_monotonic_s - upper,
                min(timing.publication_received_at_monotonic_s - lower, timing.sample_received_at_monotonic_s))
    if attitude[0] > attitude[1]:
        raise ValueError("alignment_attitude_delay_contradicts_first_receipt")
    uncertainty = bounds.relative_clock_uncertainty_s
    skew = max(abs(camera[0] - attitude[1]), abs(camera[1] - attitude[0])) + uncertainty
    return camera, attitude, skew


def _validate_receive_bounds(bearing, state, binding, bounds, now, observation_age, attitude_age):
    if not isinstance(bounds, ReceiveTimeBounds) or bounds.binding != binding:
        raise ValueError("alignment_bounds_binding_changed")
    observation, attitude, skew = _receive_intervals(bearing, state, bounds)
    uncertainty = bounds.relative_clock_uncertainty_s
    if now - observation[0] + uncertainty > observation_age:
        raise ValueError("alignment_camera_acquisition_stale")
    if now - attitude[0] + uncertainty > attitude_age:
        raise ValueError("alignment_attitude_acquisition_stale")
    if skew > bounds.max_skew_s:
        raise ValueError("alignment_skew_exceeded")
    return skew


def associate_received_bearing(
    bearing: CalibratedBearing, attitude_state: AircraftState, *, native_runtime_id: str,
    binding: AlignmentBinding, now_monotonic_s: float, max_observation_age_s: float,
    max_attitude_age_s: float, previous: AlignedBearing | None,
    bounds: ReceiveTimeBounds | None = None,
) -> AlignedBearing:
    """Use explicit delay bounds; no bounds means physical timing is unqualified."""
    if not isinstance(bounds, ReceiveTimeBounds):
        raise ValueError("physical_capture_timing_unqualified")
    _validate_pair(bearing, attitude_state, native_runtime_id, binding, now_monotonic_s,
                   max_observation_age_s, max_attitude_age_s)
    skew = _validate_receive_bounds(bearing, attitude_state, binding, bounds, now_monotonic_s,
                                   max_observation_age_s, max_attitude_age_s)
    return _result(bearing, attitude_state, binding, "bounded_receive_time", bounds.evidence_revision,
                   skew, bounds, previous)


def associate_source_timed_bearing(
    bearing: CalibratedBearing, attitude_state: AircraftState, *, native_runtime_id: str,
    binding: AlignmentBinding, now_monotonic_s: float, max_observation_age_s: float,
    max_attitude_age_s: float, source_time: SourceTimeAssociation, evidence_revision: str,
    previous: AlignedBearing | None,
) -> AlignedBearing:
    """Associate actual pixels to a raw source-clock sample within explicit skew.

    The caller establishes the common simulator clock from verified deployment
    evidence. This never aliases DDS-adjusted time to source time or substitutes
    receipt time for exposure. The reported mismatch remains visible.
    """
    if not isinstance(source_time, SourceTimeAssociation):
        raise ValueError('source_time_association_invalid')
    _validate_pair(bearing, attitude_state, native_runtime_id, binding, now_monotonic_s,
                   max_observation_age_s, max_attitude_age_s)
    if not source_time.attitude.fresh(now_monotonic_s, max_attitude_age_s):
        raise ValueError('alignment_source_attitude_stale')
    return _result(bearing, attitude_state, binding, 'bounded_source_time', evidence_revision,
                   source_time.skew_s, None, previous, source_time)


def associate_sih_bearing(
    bearing: CalibratedBearing, sample: ExactSihSample, *, binding: AlignmentBinding,
    now_monotonic_s: float, max_observation_age_s: float, max_attitude_age_s: float,
    previous: AlignedBearing | None, allow_simulation: bool = False,
) -> AlignedBearing:
    """Pair a synthetic image or boresight with its retained state, by opt-in.

    Only a trusted isolated-SIH fixture may enable this path. It is never an
    ordinary live qualification option or a claim about sensor exposure timing.
    """
    if type(allow_simulation) is not bool or not allow_simulation:
        raise ValueError("sih_projection_pair_not_enabled")
    if not isinstance(sample, ExactSihSample):
        raise ValueError("sih_projection_pair_invalid")
    _validate_pair(bearing, sample.aircraft_state, sample.native_runtime_id, binding,
                   now_monotonic_s, max_observation_age_s, max_attitude_age_s)
    if sample.observation_provenance != bearing.provenance:
        raise ValueError("sih_projection_observation_changed")
    return _result(bearing, sample.aircraft_state, binding, "sih_projection_pair", sample.fixture_revision,
                   None, None, previous)


def require_current_bearing_association(
    aligned: AlignedBearing, provenance: ObservationProvenance | GimbalAngleObservation,
    current_state: AircraftState, *, native_runtime_id: str, now_monotonic_s: float,
    max_observation_age_s: float, max_attitude_age_s: float,
) -> None:
    """Revalidate a resolver result against current native identity, without rebinding.

    Retaining a world ray does not authorize using it after an estimator reset.
    A newer attitude packet may update navigation constraints, but never rotates
    that older measurement again or changes its original acquisition association.
    """
    if not isinstance(aligned, AlignedBearing) or not isinstance(current_state, AircraftState):
        raise ValueError("guidance_input_resolver_contract_invalid")
    if aligned.bearing.provenance != provenance:
        raise ValueError("guidance_observation_binding_changed")
    try:
        _validate_pair(aligned.bearing, aligned.attitude_state, native_runtime_id, aligned.binding,
                       now_monotonic_s, max_observation_age_s, max_attitude_age_s)
        if aligned.association_kind == "bounded_receive_time":
            _validate_receive_bounds(aligned.bearing, aligned.attitude_state, aligned.binding,
                aligned.receive_bounds, now_monotonic_s, max_observation_age_s, max_attitude_age_s)
        if (aligned.source_time is not None
                and not aligned.source_time.attitude.fresh(now_monotonic_s, max_attitude_age_s)):
            raise ValueError('alignment_source_attitude_stale')
    except ValueError as error:
        if str(error) in {"alignment_observation_receipt_stale_or_future", "alignment_attitude_stale",
                          "alignment_camera_acquisition_stale", "alignment_attitude_acquisition_stale",
                          "alignment_source_attitude_stale"}:
            raise ValueError("guidance_input_stale") from error
        raise
    if (current_state.binding != aligned.binding.aircraft_binding
            or current_state.source != aligned.attitude_state.source
            or current_state.attitude_timing is None
            or current_state.attitude_timing.quat_reset_counter != aligned.binding.quat_reset_counter):
        raise ValueError("guidance_aircraft_or_reset_changed")
    associated = aligned.attitude_state
    if (current_state.sequence < associated.sequence
            or current_state.observed_at_monotonic_s < associated.observed_at_monotonic_s
            or current_state.attitude_timing.sample_timestamp_us < associated.attitude_timing.sample_timestamp_us
            or current_state.attitude_timing.publication_timestamp_us < associated.attitude_timing.publication_timestamp_us
            or not preserves_attitude_sample(associated.attitude_timing, associated.attitude_body_to_ned,
                                             current_state.attitude_timing, current_state.attitude_body_to_ned)
            or current_state.sequence == associated.sequence and current_state != associated):
        raise ValueError("guidance_aircraft_state_reordered_or_rewritten")
    if (not current_state.fresh(now_monotonic_s, max_attitude_age_s)
            or not current_state.attitude_timing.fresh(now_monotonic_s, max_attitude_age_s)):
        raise ValueError("guidance_input_stale")


def bearing_intent_requires_update(
    aligned: AlignedBearing, previous: AlignedBearing | None,
    state: AircraftState, previous_state: AircraftState | None,
    control_revision: int, previous_control_revision: int | None,
) -> bool:
    """Share progression checks without owning a publisher or refreshing a sample.

    Current navigation constraints and an acknowledged control change can require
    recalculation against the original world ray. An unchanged poll cannot renew
    a command. The caller validates current ages before using this predicate.
    """
    if previous is not None:
        expected = _result(aligned.bearing, aligned.attitude_state, aligned.binding,
            aligned.association_kind, aligned.evidence_revision, aligned.worst_case_skew_s,
            aligned.receive_bounds, previous, aligned.source_time)
        if expected != aligned:
            raise ValueError("guidance_association_rewritten")
    if previous_state is not None and (
            state.source != previous_state.source or state.sequence < previous_state.sequence
            or state.observed_at_monotonic_s < previous_state.observed_at_monotonic_s
            or state.sequence == previous_state.sequence and state != previous_state):
        raise ValueError("guidance_aircraft_state_reordered_or_rewritten")
    duplicate = (previous is not None
                 and bearing_receipt(aligned.bearing.provenance).sample_id
                 == bearing_receipt(previous.bearing.provenance).sample_id)
    return (not duplicate or previous_state is None or state.sequence > previous_state.sequence
            or control_revision != previous_control_revision)
