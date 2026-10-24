"""Shared state classification for gimbal vector guidance.

The classifier deliberately contains no vehicle or follower commands.  It turns
one fresh, canonical aircraft-body line-of-sight ray into a small, observable
state machine which the vector follower can apply to its existing command and
safety pipeline.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


class GuidanceState(str, Enum):
    FORWARD = "forward"
    VERTICAL = "vertical"
    REARWARD_GRACE = "rearward_grace"
    YAW_FIRST = "yaw_first"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class GimbalGuidancePolicy:
    """Tunable geometry thresholds shared by all vector gimbal sessions."""

    policy: str = "reverse_then_yaw"
    vertical_enter_horizontal_norm: float = 0.20
    vertical_exit_horizontal_norm: float = 0.30
    rearward_entry_bearing_deg: float = 100.0
    forward_reentry_bearing_deg: float = 80.0
    transition_dwell_ms: float = 300.0
    rearward_grace_ms: float = 500.0

    def __post_init__(self) -> None:
        if self.policy not in ("reverse_then_yaw", "forward_only"):
            raise ValueError("GUIDANCE.POLICY must be reverse_then_yaw or forward_only")
        values = (
            self.vertical_enter_horizontal_norm,
            self.vertical_exit_horizontal_norm,
            self.rearward_entry_bearing_deg,
            self.forward_reentry_bearing_deg,
            self.transition_dwell_ms,
            self.rearward_grace_ms,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("Gimbal guidance policy values must be finite")
        if not 0.0 <= self.vertical_enter_horizontal_norm < self.vertical_exit_horizontal_norm <= 1.0:
            raise ValueError("Vertical enter/exit thresholds must satisfy 0 <= enter < exit <= 1")
        if not 0.0 <= self.forward_reentry_bearing_deg < self.rearward_entry_bearing_deg <= 180.0:
            raise ValueError("Bearing thresholds must satisfy 0 <= reentry < entry <= 180")
        if self.transition_dwell_ms < 0.0 or self.rearward_grace_ms < 0.0:
            raise ValueError("Transition dwell and rearward grace cannot be negative")

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "GimbalGuidancePolicy":
        values = dict(raw or {})
        aliases = {
            "VERTICAL_ENTER_HORIZONTAL_NORM": "vertical_enter_horizontal_norm",
            "VERTICAL_EXIT_HORIZONTAL_NORM": "vertical_exit_horizontal_norm",
            "REARWARD_ENTRY_BEARING_DEG": "rearward_entry_bearing_deg",
            "FORWARD_REENTRY_BEARING_DEG": "forward_reentry_bearing_deg",
            "TRANSITION_DWELL_MS": "transition_dwell_ms",
            "REARWARD_GRACE_MS": "rearward_grace_ms",
            "POLICY": "policy",
        }
        kwargs = {}
        for source, target in aliases.items():
            if source in values:
                kwargs[target] = values[source]
        for key in (
            "vertical_enter_horizontal_norm",
            "vertical_exit_horizontal_norm",
            "rearward_entry_bearing_deg",
            "forward_reentry_bearing_deg",
            "transition_dwell_ms",
            "rearward_grace_ms",
        ):
            if key in values:
                kwargs[key] = values[key]
        for key in tuple(kwargs):
            if key != "policy":
                kwargs[key] = float(kwargs[key])
        return cls(**kwargs)

    @property
    def transition_dwell_s(self) -> float:
        return self.transition_dwell_ms / 1000.0

    @property
    def rearward_grace_s(self) -> float:
        return self.rearward_grace_ms / 1000.0

    def to_mapping(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "vertical_enter_horizontal_norm": self.vertical_enter_horizontal_norm,
            "vertical_exit_horizontal_norm": self.vertical_exit_horizontal_norm,
            "rearward_entry_bearing_deg": self.rearward_entry_bearing_deg,
            "forward_reentry_bearing_deg": self.forward_reentry_bearing_deg,
            "transition_dwell_ms": self.transition_dwell_ms,
            "rearward_grace_ms": self.rearward_grace_ms,
        }


def _limits(value: Any) -> Optional[Tuple[float, float]]:
    if value is None:
        return None
    try:
        result = (float(value[0]), float(value[1]))
    except (TypeError, ValueError, IndexError, OverflowError) as exc:
        raise ValueError("Gimbal angle limits must contain two numbers") from exc
    if not all(math.isfinite(number) for number in result) or result[0] > result[1]:
        raise ValueError("Gimbal angle limits must be finite and ordered")
    return result


@dataclass(frozen=True)
class GimbalGuidanceCapabilities:
    """Provider-advertised geometry and manoeuvre capabilities."""

    known: bool = False
    supports_vertical: bool = False
    supports_reverse: bool = False
    supports_yaw_fallback: bool = False
    azimuth_limits_deg: Optional[Tuple[float, float]] = None
    depression_limits_deg: Optional[Tuple[float, float]] = None

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "GimbalGuidanceCapabilities":
        if not isinstance(raw, Mapping):
            return cls()
        values = raw.get("guidance_capabilities", raw)
        if not isinstance(values, Mapping):
            return cls()
        def read(name: str, fallback: Any = None) -> Any:
            return values.get(name, values.get(name.upper(), fallback))
        return cls(
            known=bool(read("known", False)),
            supports_vertical=bool(read("supports_vertical", False)),
            supports_reverse=bool(read("supports_reverse", False)),
            supports_yaw_fallback=bool(read("supports_yaw_fallback", False)),
            azimuth_limits_deg=_limits(read("azimuth_limits_deg")),
            depression_limits_deg=_limits(read("depression_limits_deg")),
        )

    def supports(self, state: GuidanceState) -> bool:
        if state == GuidanceState.FORWARD:
            return True
        if not self.known:
            return False
        if state == GuidanceState.VERTICAL:
            return self.supports_vertical
        if state == GuidanceState.REARWARD_GRACE:
            return self.supports_reverse
        if state == GuidanceState.YAW_FIRST:
            return self.supports_yaw_fallback
        return False

    def to_mapping(self) -> dict[str, Any]:
        return {
            "known": self.known,
            "supports_vertical": self.supports_vertical,
            "supports_reverse": self.supports_reverse,
            "supports_yaw_fallback": self.supports_yaw_fallback,
            "azimuth_limits_deg": self.azimuth_limits_deg,
            "depression_limits_deg": self.depression_limits_deg,
        }


@dataclass(frozen=True)
class GuidanceDecision:
    state: GuidanceState
    horizontal_norm: float
    bearing_deg: Optional[float]
    reason: str
    transition_pending: bool = False
    state_age_s: float = 0.0


class GimbalGuidanceClassifier:
    """Hysteretic, monotonic-time classifier for fresh body-frame rays."""

    def __init__(
        self,
        policy: Optional[GimbalGuidancePolicy] = None,
        capabilities: Optional[GimbalGuidanceCapabilities] = None,
        clock=time.monotonic,
    ) -> None:
        self.policy = policy or GimbalGuidancePolicy()
        self.capabilities = capabilities or GimbalGuidanceCapabilities()
        self._clock = clock
        self.reset()

    def reset(self) -> None:
        self.state = GuidanceState.FORWARD
        self._candidate: Optional[GuidanceState] = None
        self._candidate_since: Optional[float] = None
        self._state_since: Optional[float] = None
        self._rearward_since: Optional[float] = None
        self.last_decision: Optional[GuidanceDecision] = None

    def update_capabilities(self, capabilities: Optional[GimbalGuidanceCapabilities]) -> None:
        if capabilities is not None:
            self.capabilities = capabilities

    @staticmethod
    def _normalise(ray: Any) -> Tuple[float, float, float]:
        try:
            values = (float(ray.x), float(ray.y), float(ray.z))
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Gimbal guidance requires a finite body ray") from exc
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Gimbal guidance requires a finite body ray")
        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude < 1e-9:
            raise ValueError("Gimbal guidance cannot classify a zero-length body ray")
        return tuple(value / magnitude for value in values)

    def _raw_state(self, horizontal_norm: float, bearing: Optional[float]) -> GuidanceState:
        policy = self.policy
        if horizontal_norm <= policy.vertical_enter_horizontal_norm:
            return GuidanceState.VERTICAL
        if self.state == GuidanceState.VERTICAL and horizontal_norm < policy.vertical_exit_horizontal_norm:
            return GuidanceState.VERTICAL
        if bearing is None:
            return GuidanceState.VERTICAL
        absolute = abs(bearing)
        if self.state == GuidanceState.YAW_FIRST:
            return GuidanceState.FORWARD if absolute <= policy.forward_reentry_bearing_deg else GuidanceState.YAW_FIRST
        if self.state == GuidanceState.REARWARD_GRACE:
            if absolute <= policy.forward_reentry_bearing_deg:
                return GuidanceState.FORWARD
            return GuidanceState.REARWARD_GRACE
        if absolute >= policy.rearward_entry_bearing_deg:
            if policy.policy == "reverse_then_yaw":
                return GuidanceState.REARWARD_GRACE
            return GuidanceState.YAW_FIRST
        return GuidanceState.FORWARD

    def _supported_state(self, state: GuidanceState) -> tuple[GuidanceState, str]:
        if self.capabilities.supports(state):
            return state, ""
        if state == GuidanceState.REARWARD_GRACE and self.capabilities.supports(GuidanceState.YAW_FIRST):
            return GuidanceState.YAW_FIRST, "reverse_unavailable_yaw_fallback"
        if state == GuidanceState.VERTICAL:
            return GuidanceState.UNREACHABLE, "vertical_guidance_unavailable"
        if state in (GuidanceState.REARWARD_GRACE, GuidanceState.YAW_FIRST):
            return GuidanceState.UNREACHABLE, "yaw_fallback_unavailable"
        return state, ""

    def _within_provider_limits(
        self, horizontal: float, bearing: Optional[float], z: float,
    ) -> bool:
        if not self.capabilities.known:
            return True
        if bearing is not None and self.capabilities.azimuth_limits_deg is not None:
            low, high = self.capabilities.azimuth_limits_deg
            if not low <= bearing <= high:
                return False
        # Depression is measured from the forward horizontal ray. A pure
        # vertical ray has a signed 90-degree depression and no azimuth.
        depression = math.degrees(math.atan2(z, horizontal))
        if self.capabilities.depression_limits_deg is not None:
            low, high = self.capabilities.depression_limits_deg
            if not low <= depression <= high:
                return False
        return True

    def update(self, ray: Any, now: Optional[float] = None) -> GuidanceDecision:
        timestamp = self._clock() if now is None else float(now)
        x, y, z = self._normalise(ray)
        horizontal = math.hypot(x, y)
        # Bearing is needed to decide the exit from vertical hysteresis. It is
        # omitted only for a genuinely vertical ray, not for the hysteresis
        # band between enter and exit thresholds.
        bearing = None if horizontal <= 1e-9 else math.degrees(math.atan2(y, x))
        raw_state = self._raw_state(horizontal, bearing)

        # A provider that cannot perform a newly requested special state must
        # never receive that state's raw vector during the dwell interval. Move
        # directly to its advertised safe fallback (or UNREACHABLE).
        forced_state, forced_reason = self._supported_state(raw_state)
        if forced_state != raw_state:
            self.state = forced_state
            self._state_since = timestamp
            self._candidate = None
            self._candidate_since = None
            self._rearward_since = None
            decision = GuidanceDecision(
                state=self.state,
                horizontal_norm=horizontal,
                bearing_deg=None if self.state == GuidanceState.VERTICAL else bearing,
                reason=forced_reason or "guidance_state_fallback",
                transition_pending=False,
                state_age_s=0.0,
            )
            self.last_decision = decision
            return decision

        # The grace interval starts at the first fresh rearward observation. A
        # short dwell then prevents one noisy sample from changing command mode.
        if raw_state == GuidanceState.REARWARD_GRACE and self._rearward_since is None:
            self._rearward_since = timestamp
        if raw_state in (GuidanceState.FORWARD, GuidanceState.VERTICAL):
            self._rearward_since = None

        desired = raw_state
        if (
            raw_state == GuidanceState.REARWARD_GRACE
            and self._rearward_since is not None
            and timestamp - self._rearward_since >= self.policy.rearward_grace_s
        ):
            desired = GuidanceState.YAW_FIRST

        pending = desired != self.state
        if pending:
            if desired != self._candidate:
                self._candidate = desired
                self._candidate_since = timestamp
            dwell_done = (
                self._candidate_since is not None
                and timestamp - self._candidate_since >= self.policy.transition_dwell_s
            )
            # Rearward grace already includes the required fresh-observation
            # dwell. Do not add a second hidden timer before yaw-first.
            if dwell_done or desired == GuidanceState.YAW_FIRST:
                self.state = desired
                self._state_since = timestamp
                self._candidate = None
                self._candidate_since = None
        else:
            self._candidate = None
            self._candidate_since = None

        if self.state == GuidanceState.YAW_FIRST and raw_state == GuidanceState.FORWARD:
            self._rearward_since = None
        supported_state, support_reason = self._supported_state(self.state)
        if supported_state == GuidanceState.UNREACHABLE:
            self.state = supported_state
            support_reason = support_reason or "guidance_state_unreachable"
        elif not self._within_provider_limits(horizontal, bearing, z):
            self.state = GuidanceState.UNREACHABLE
            support_reason = "provider_geometry_limit"
        state_age = 0.0 if self._state_since is None else max(0.0, timestamp - self._state_since)
        reason = support_reason or (
            "transition_pending" if pending and self._candidate is not None else self.state.value
        )
        decision = GuidanceDecision(
            state=self.state,
            horizontal_norm=horizontal,
            bearing_deg=None if self.state == GuidanceState.VERTICAL else bearing,
            reason=reason,
            transition_pending=pending and self._candidate is not None,
            state_age_s=state_age,
        )
        self.last_decision = decision
        return decision
