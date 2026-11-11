"""Input-independent direction thresholds for bearing-based guidance.

Values come from the owning profile's resolved configuration. This value owns
neither camera mechanics nor MC reverse/yaw timing, speed or aircraft authority.
"""

from dataclasses import dataclass

from classes.aircraft_state import finite_number


@dataclass(frozen=True)
class BearingGeometryPolicy:
    vertical_enter_horizontal_norm: float
    vertical_exit_horizontal_norm: float
    rearward_entry_bearing_deg: float
    forward_reentry_bearing_deg: float

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            finite_number(getattr(self, name), name)
        if not 0. <= self.vertical_enter_horizontal_norm < self.vertical_exit_horizontal_norm <= 1.:
            raise ValueError("Vertical enter/exit thresholds must satisfy 0 <= enter < exit <= 1")
        if not 0. <= self.forward_reentry_bearing_deg < self.rearward_entry_bearing_deg <= 180.:
            raise ValueError("Bearing thresholds must satisfy 0 <= reentry < entry <= 180")
