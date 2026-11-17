"""Shared FW navigation policy; no aircraft controller or parameter writer.

Input adapters may produce objectives from gimbal rays or image tracking. They
share this policy only after adopting a qualified phase-bound command owner.
The older attitude-rate controller cannot silently claim these capabilities.
"""

from dataclasses import dataclass
from enum import Enum
from collections.abc import Mapping

from classes.aircraft_state import finite_number


class UpperSpeedPolicy(str, Enum):
    PX4_CONFIGURED_MAX = "px4_configured_max"
    NO_UPPER_SPEED_BOUND = "no_upper_speed_bound"


@dataclass(frozen=True)
class FixedWingGuidancePolicy:
    upper_speed_policy: UpperSpeedPolicy = UpperSpeedPolicy.PX4_CONFIGURED_MAX
    min_dive_throttle: float | None = None

    def __post_init__(self):
        if not isinstance(self.upper_speed_policy, UpperSpeedPolicy):
            raise ValueError("upper_speed_policy_invalid")
        if self.min_dive_throttle is not None and not 0. <= finite_number(self.min_dive_throttle, "min_dive_throttle") <= 1.:
            raise ValueError("min_dive_throttle_out_of_range")

    @classmethod
    def from_mapping(cls, raw: Mapping | None):
        if raw is None:
            return cls()
        if not isinstance(raw, Mapping) or set(raw) - {"UPPER_SPEED_POLICY", "MIN_DIVE_THROTTLE"}:
            raise ValueError("fixed_wing_guidance_policy_invalid")
        try:
            mode = UpperSpeedPolicy(raw.get("UPPER_SPEED_POLICY", UpperSpeedPolicy.PX4_CONFIGURED_MAX.value))
        except (TypeError, ValueError) as error:
            raise ValueError("upper_speed_policy_invalid") from error
        return cls(mode, raw.get("MIN_DIVE_THROTTLE"))

    def resolve_native(self, unrestricted_verified: bool) -> "FixedWingGuidancePolicy":
        """Select supported behavior without claiming an unavailable experiment."""
        if type(unrestricted_verified) is not bool:
            raise ValueError("unrestricted_capability_invalid")
        if self.upper_speed_policy is UpperSpeedPolicy.NO_UPPER_SPEED_BOUND and not unrestricted_verified:
            return FixedWingGuidancePolicy()
        return self
