"""Explicit image/attitude associations without capture, clocks, or authority.

Receipt times remain receipts. Bounded receive-time qualification requires
independently established total-delay bounds; exact SIH pairing describes only
an image projected from a retained observed state, never hardware synchronization.
"""

from dataclasses import dataclass
import math

from classes.aircraft_state import AircraftBinding, AircraftState, Vector3, finite_number
from classes.guidance_observation import CalibratedBearing, ObservationProvenance


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
    source_epoch: str
    geometry_revision: str
    calibration_revision: str
    target_generation: int
    aircraft_binding: AircraftBinding
    native_runtime_id: str
    quat_reset_counter: int

    def __post_init__(self):
        for name in ("source_id", "source_epoch", "geometry_revision", "calibration_revision", "native_runtime_id"):
            _identity(getattr(self, name))
        if type(self.target_generation) is not int or self.target_generation < 0:
            raise ValueError("alignment_target_generation_invalid")
        if not isinstance(self.aircraft_binding, AircraftBinding):
            raise ValueError("alignment_aircraft_binding_invalid")
        if type(self.quat_reset_counter) is not int or not 0 <= self.quat_reset_counter <= 255:
            raise ValueError("alignment_reset_counter_invalid")


@dataclass(frozen=True)
class ReceiveTimeBounds:
    """Measured total delays and relative-clock error for this exact binding.

    camera_delay_s bounds acquisition to backend receipt. The attitude interval
    bounds sample acquisition to this packet's publication receipt, including
    source processing, republishing and transport. Evidence is supplied by the
    caller; this module cannot establish those bounds from timestamps alone.
    """

    binding: AlignmentBinding
    camera_delay_s: tuple[float, float]
    attitude_sample_to_publication_receipt_s: tuple[float, float]
    relative_clock_uncertainty_s: float
    max_skew_s: float
    evidence_revision: str

    def __post_init__(self):
        if not isinstance(self.binding, AlignmentBinding):
            raise ValueError("alignment_binding_invalid")
        _delay_interval(self.camera_delay_s)
        _delay_interval(self.attitude_sample_to_publication_receipt_s)
        if finite_number(self.relative_clock_uncertainty_s, "alignment_clock_uncertainty") < 0:
            raise ValueError("alignment_clock_uncertainty_negative")
        _positive(self.max_skew_s, "alignment_max_skew")
        _identity(self.evidence_revision)


@dataclass(frozen=True)
class ExactSihSample:
    """Retained projection inputs, constructed by an isolated SIH fixture only."""

    image_provenance: ObservationProvenance
    aircraft_state: AircraftState
    native_runtime_id: str
    fixture_revision: str

    def __post_init__(self):
        if not isinstance(self.image_provenance, ObservationProvenance) or not isinstance(self.aircraft_state, AircraftState):
            raise ValueError("sih_projection_pair_invalid")
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

    def __post_init__(self):
        if (not isinstance(self.binding, AlignmentBinding) or not isinstance(self.bearing, CalibratedBearing)
                or not isinstance(self.attitude_state, AircraftState) or not isinstance(self.direction_ned, Vector3)):
            raise ValueError("aligned_bearing_contract_invalid")
        image, binding, state = self.bearing.provenance, self.binding, self.attitude_state
        if ((image.source_id, image.capture.source_epoch, image.geometry_revision,
             image.calibration_revision, image.target_generation)
                != (binding.source_id, binding.source_epoch, binding.geometry_revision,
                    binding.calibration_revision, binding.target_generation)
                or image.capture.state != "fresh" or state.binding != binding.aircraft_binding
                or state.attitude_timing is None
                or state.attitude_timing.quat_reset_counter != binding.quat_reset_counter):
            raise ValueError("aligned_bearing_binding_invalid")
        if not math.isclose(self.direction_ned.magnitude, 1., rel_tol=0., abs_tol=1e-9):
            raise ValueError("aligned_bearing_direction_not_unit")
        expected = state.attitude_body_to_ned.rotate(self.bearing.direction_body_frd).normalized()
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
        else:
            raise ValueError("aligned_bearing_kind_invalid")


def _validate_pair(
    bearing, state, native_runtime_id, binding, now, image_age, attitude_age,
) -> None:
    if (not isinstance(bearing, CalibratedBearing) or not isinstance(state, AircraftState)
            or not isinstance(binding, AlignmentBinding)):
        raise ValueError("alignment_contract_invalid")
    now = finite_number(now, "alignment_clock")
    _positive(image_age, "alignment_image_age_limit")
    _positive(attitude_age, "alignment_attitude_age_limit")
    bearing.provenance.require_current(
        source_id=binding.source_id, source_epoch=binding.source_epoch,
        geometry_revision=binding.geometry_revision, calibration_revision=binding.calibration_revision,
        target_generation=binding.target_generation, now_monotonic_s=now, max_receipt_age_s=image_age,
    )
    if state.binding != binding.aircraft_binding or native_runtime_id != binding.native_runtime_id:
        raise ValueError("alignment_aircraft_or_runtime_changed")
    timing = state.attitude_timing
    if timing is None:
        raise ValueError("alignment_attitude_timing_unavailable")
    if timing.quat_reset_counter != binding.quat_reset_counter:
        raise ValueError("alignment_attitude_reset_changed")
    if not state.fresh(now, attitude_age) or not timing.fresh(now, attitude_age):
        raise ValueError("alignment_attitude_stale")


def _result(bearing, state, binding, kind, evidence, skew, bounds, previous) -> AlignedBearing:
    if previous is not None:
        if not isinstance(previous, AlignedBearing) or previous.binding != binding:
            raise ValueError("alignment_binding_changed")
        if (kind != previous.association_kind or evidence != previous.evidence_revision
                or bounds != previous.receive_bounds):
            raise ValueError("alignment_qualification_changed")
        before = previous.bearing.provenance.capture
        current = bearing.provenance.capture
        if current.capture_id == before.capture_id:
            if bearing != previous.bearing or state != previous.attitude_state:
                raise ValueError("alignment_capture_rewritten")
            return previous
        if current.captured_at <= before.captured_at:
            raise ValueError("alignment_capture_reordered")
        if (current.capture_id.isdecimal() and before.capture_id.isdecimal()
                and int(current.capture_id) < int(before.capture_id)):
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
                    and (new != old or state.attitude_body_to_ned != old_state.attitude_body_to_ned))
                or (new.sample_timestamp_us == old.sample_timestamp_us
                    and new.sample_received_at_monotonic_s != old.sample_received_at_monotonic_s)):
            raise ValueError("alignment_attitude_reordered_or_rewritten")
    direction = state.attitude_body_to_ned.rotate(bearing.direction_body_frd).normalized()
    return AlignedBearing(binding, bearing, state, direction, kind, evidence, skew, bounds)


def _receive_intervals(bearing, attitude_state, bounds) -> tuple[tuple, tuple, float]:
    timing = attitude_state.attitude_timing
    processing = (timing.publication_timestamp_us - timing.sample_timestamp_us) * 1e-6
    lower, upper = bounds.attitude_sample_to_publication_receipt_s
    lower = max(lower, processing)
    if lower > upper:
        raise ValueError("alignment_attitude_delay_contradicts_processing")
    camera_receipt = bearing.provenance.capture.captured_at
    camera = (camera_receipt - bounds.camera_delay_s[1], camera_receipt - bounds.camera_delay_s[0])
    attitude = (timing.publication_received_at_monotonic_s - upper,
                min(timing.publication_received_at_monotonic_s - lower, timing.sample_received_at_monotonic_s))
    if attitude[0] > attitude[1]:
        raise ValueError("alignment_attitude_delay_contradicts_first_receipt")
    uncertainty = bounds.relative_clock_uncertainty_s
    skew = max(abs(camera[0] - attitude[1]), abs(camera[1] - attitude[0])) + uncertainty
    return camera, attitude, skew


def associate_received_bearing(
    bearing: CalibratedBearing, attitude_state: AircraftState, *, native_runtime_id: str,
    binding: AlignmentBinding, now_monotonic_s: float, max_image_age_s: float,
    max_attitude_age_s: float, previous: AlignedBearing | None,
    bounds: ReceiveTimeBounds | None = None,
) -> AlignedBearing:
    """Use explicit delay bounds; no bounds means physical timing is unqualified."""
    if not isinstance(bounds, ReceiveTimeBounds):
        raise ValueError("physical_capture_timing_unqualified")
    _validate_pair(bearing, attitude_state, native_runtime_id, binding, now_monotonic_s,
                   max_image_age_s, max_attitude_age_s)
    if bounds.binding != binding:
        raise ValueError("alignment_bounds_binding_changed")
    camera, attitude, skew = _receive_intervals(bearing, attitude_state, bounds)
    uncertainty = bounds.relative_clock_uncertainty_s
    if now_monotonic_s - camera[0] + uncertainty > max_image_age_s:
        raise ValueError("alignment_camera_acquisition_stale")
    if now_monotonic_s - attitude[0] + uncertainty > max_attitude_age_s:
        raise ValueError("alignment_attitude_acquisition_stale")
    if skew > bounds.max_skew_s:
        raise ValueError("alignment_skew_exceeded")
    return _result(bearing, attitude_state, binding, "bounded_receive_time", bounds.evidence_revision,
                   skew, bounds, previous)


def associate_sih_bearing(
    bearing: CalibratedBearing, sample: ExactSihSample, *, binding: AlignmentBinding,
    now_monotonic_s: float, max_image_age_s: float, max_attitude_age_s: float,
    previous: AlignedBearing | None, allow_simulation: bool = False,
) -> AlignedBearing:
    """Pair a synthetic projection with its retained observed state, by opt-in.

    Only a trusted isolated-SIH fixture may enable this path. It is never an
    ordinary live qualification option or a claim about sensor exposure timing.
    """
    if type(allow_simulation) is not bool or not allow_simulation:
        raise ValueError("sih_projection_pair_not_enabled")
    if not isinstance(sample, ExactSihSample):
        raise ValueError("sih_projection_pair_invalid")
    _validate_pair(bearing, sample.aircraft_state, sample.native_runtime_id, binding,
                   now_monotonic_s, max_image_age_s, max_attitude_age_s)
    if sample.image_provenance != bearing.provenance:
        raise ValueError("sih_projection_image_changed")
    return _result(bearing, sample.aircraft_state, binding, "sih_projection_pair", sample.fixture_revision,
                   None, None, previous)
