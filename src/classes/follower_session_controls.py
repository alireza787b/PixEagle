"""Typed, process-local control values owned by a single following session."""

from dataclasses import dataclass, replace
import math


@dataclass(frozen=True)
class SessionControl:
    control_id: str
    label: str
    unit: str
    minimum: float
    maximum: float | None
    step: float
    value: float
    revision: int = 0
    configured_maximum: float | None = None
    override_active: bool = False

    def updated(self, value: float, revision: int) -> "SessionControl":
        if revision != self.revision:
            raise ValueError("session_control_revision_stale")
        if value is None:
            if self.configured_maximum is None:
                raise ValueError('session_control_reset_unsupported')
            return replace(self, value=min(self.value, self.configured_maximum),
                           override_active=False, revision=self.revision + 1)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("session_control_value_invalid")
        if value < self.minimum or self.maximum is not None and value > self.maximum:
            raise ValueError("session_control_out_of_range")
        return replace(self, value=float(value), revision=self.revision + 1,
                       override_active=self.configured_maximum is not None)

    def snapshot(self) -> dict:
        return dict(control_id=self.control_id, label=self.label, unit=self.unit,
                    minimum=self.minimum, maximum=self.maximum, step=self.step,
                    value=self.value, revision=self.revision,
                    configured_maximum=self.configured_maximum, override_active=self.override_active,
                    reset_supported=self.configured_maximum is not None)
