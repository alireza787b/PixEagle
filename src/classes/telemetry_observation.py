"""Transport-independent observations shared by control and command preview."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AltitudeSourceSample:
    """Paired height/vertical speed; receipt time is not sensor capture time."""

    height_relative_m: float
    vertical_speed_up_m_s: float
    source_marker: int
    sample_time_s: float
    received_at_monotonic_s: float
    sample_time_basis: str
    source: str
    altitude_reference_generation: int

    def __post_init__(self):
        for value in (self.height_relative_m, self.vertical_speed_up_m_s,
                      self.sample_time_s, self.received_at_monotonic_s):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Altitude sample requires finite numbers")
        if (type(self.source_marker) is not int or not 0 <= self.source_marker < 2**32
                or self.sample_time_s < 0. or self.received_at_monotonic_s < 0.
                or type(self.altitude_reference_generation) is not int or self.altitude_reference_generation < 1
                or not isinstance(self.source, str) or not self.source
                or not isinstance(self.sample_time_basis, str) or not self.sample_time_basis):
            raise ValueError("Altitude sample source metadata is invalid")


@dataclass(frozen=True)
class AltitudeObservation(AltitudeSourceSample):
    """A complete height sample owned by one command telemetry lifecycle."""

    connection_generation: int
    telemetry_generation: int

    def __post_init__(self):
        super().__post_init__()
        if any(type(value) is not int or value < 0
               for value in (self.connection_generation, self.telemetry_generation)):
            raise ValueError("Altitude observation owner generations are invalid")
