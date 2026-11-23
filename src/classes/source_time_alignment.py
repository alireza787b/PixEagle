"""Explicit bounded alignment of rendered image time and raw PX4 source time.

Only an independently verified simulator clock declaration can join these two
domains. DDS-adjusted timestamps and host receipt cannot replace either sample.
"""

from dataclasses import dataclass

from classes.aircraft_state import Quaternion, finite_number
from classes.capture_timing import SourceSampleStamp


@dataclass(frozen=True)
class SourceAttitudeSample:
    sample_timestamp_us: int
    publication_timestamp_us: int
    quaternion_wxyz: tuple[float, float, float, float]
    quat_reset_counter: int
    received_at_monotonic_s: float
    time_basis: str

    def __post_init__(self):
        if (any(type(value) is not int or not 0 < value < 2**64
                for value in (self.sample_timestamp_us, self.publication_timestamp_us))
                or self.sample_timestamp_us > self.publication_timestamp_us):
            raise ValueError('source_attitude_timestamps_invalid')
        if (not isinstance(self.quaternion_wxyz, tuple) or len(self.quaternion_wxyz) != 4
                or type(self.quat_reset_counter) is not int or not 0 <= self.quat_reset_counter <= 255):
            raise ValueError('source_attitude_geometry_invalid')
        Quaternion(*self.quaternion_wxyz)
        if finite_number(self.received_at_monotonic_s, 'source_attitude_receipt') < 0:
            raise ValueError('source_attitude_receipt_invalid')
        if self.time_basis != 'px4_source_us':
            raise ValueError('source_attitude_time_basis_invalid')

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict) or set(payload) != set(cls.__dataclass_fields__):
            raise ValueError('source_attitude_contract_invalid')
        values = dict(payload)
        if not isinstance(values['quaternion_wxyz'], (list, tuple)):
            raise ValueError('source_attitude_geometry_invalid')
        values['quaternion_wxyz'] = tuple(values['quaternion_wxyz'])
        return cls(**values)

    @property
    def quaternion(self):
        return Quaternion(*self.quaternion_wxyz)

    def fresh(self, now, timeout_s):
        age = finite_number(now, 'source_attitude_clock') - self.received_at_monotonic_s
        timeout = finite_number(timeout_s, 'source_attitude_timeout')
        if timeout <= 0:
            raise ValueError('source_attitude_timeout_invalid')
        processing = (self.publication_timestamp_us - self.sample_timestamp_us) * 1e-6
        return 0 <= age and age + processing <= timeout


@dataclass(frozen=True)
class SourceTimeAssociation:
    source_sample: SourceSampleStamp
    attitude: SourceAttitudeSample
    declared_clock_id: str
    maximum_skew_s: float

    def __post_init__(self):
        if not isinstance(self.source_sample, SourceSampleStamp) or not isinstance(self.attitude, SourceAttitudeSample):
            raise ValueError('source_time_association_invalid')
        if (self.source_sample.time_basis != 'gazebo_sim_us'
                or not isinstance(self.declared_clock_id, str) or not self.declared_clock_id
                or self.source_sample.clock_id != self.declared_clock_id):
            raise ValueError('source_clock_domain_unqualified')
        if finite_number(self.maximum_skew_s, 'source_time_max_skew') <= 0:
            raise ValueError('source_time_max_skew_invalid')
        if self.skew_s > self.maximum_skew_s:
            raise ValueError('source_time_skew_exceeded')

    @property
    def skew_s(self):
        return abs(self.source_sample.timestamp_us - self.attitude.sample_timestamp_us) * 1e-6
