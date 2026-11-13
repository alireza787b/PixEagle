"""Optional sensor/source time, distinct from the backend's monotonic receipt."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSampleStamp:
    clock_id: str
    source_incarnation: str
    sequence: int
    timestamp_us: int
    time_basis: str

    def __post_init__(self):
        for name in ("clock_id", "source_incarnation", "time_basis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or value.strip() != value:
                raise ValueError("source_sample_identity_invalid")
        if (type(self.sequence) is not int or self.sequence < 1
                or type(self.timestamp_us) is not int or not 0 <= self.timestamp_us < 2**64):
            raise ValueError("source_sample_progress_invalid")

