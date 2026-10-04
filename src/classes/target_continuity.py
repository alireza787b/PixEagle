"""Shared target-evidence and follower command-authority policy.

Trackers report evidence, followers calculate nominal commands, and this module
alone decides whether those commands retain authority after target evidence is
lost.  It never sends a vehicle command or changes PX4 mode itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
import math
import time
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from classes.command_intent import CommandIntent
from classes.follower_types import FollowerType
from classes.tracker_runtime_status import (
    evaluate_tracker_command_freshness,
    parse_bool_like,
)


class TargetEvidenceState(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNCERTAIN = "UNCERTAIN"
    PREDICTED = "PREDICTED"
    AMBIGUOUS = "AMBIGUOUS"
    ABSENT = "ABSENT"


class IdentityVerdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"
    AMBIGUOUS = "AMBIGUOUS"


class ContinuityAuthorityState(str, Enum):
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    COASTING = "COASTING"
    REACQUIRING = "REACQUIRING"
    HANDOFF_PENDING = "HANDOFF_PENDING"


class ContinuityMode(str, Enum):
    IMMEDIATE_HANDOFF = "immediate_handoff"
    BOUNDED_DECAY = "bounded_decay"


class AirframePhase(str, Enum):
    MULTICOPTER = "multicopter"
    FIXED_WING = "fixed_wing"
    VTOL_TRANSITION = "vtol_transition"
    UNKNOWN = "unknown"


class TerminalAction(str, Enum):
    HOLD = "hold"


@dataclass(frozen=True)
class TargetEvidenceSnapshot:
    state: TargetEvidenceState
    observed_at_monotonic_s: float
    session_epoch: int
    target_id: Optional[str]
    identity_verdict: IdentityVerdict
    reason_code: str

    @classmethod
    def from_tracker_output(
        cls,
        tracker_output: Any,
        *,
        session_epoch: int,
        now_monotonic_s: Optional[float] = None,
    ) -> "TargetEvidenceSnapshot":
        """Normalize tracker evidence without adding flight-control policy."""
        now = time.monotonic() if now_monotonic_s is None else float(now_monotonic_s)
        if tracker_output is None:
            return cls(
                state=TargetEvidenceState.ABSENT,
                observed_at_monotonic_s=now,
                session_epoch=int(session_epoch),
                target_id=None,
                identity_verdict=IdentityVerdict.UNCONFIRMED,
                reason_code="tracker_output_missing",
            )

        freshness = evaluate_tracker_command_freshness(tracker_output)
        raw_data = getattr(tracker_output, "raw_data", None) or {}
        metadata = getattr(tracker_output, "metadata", None) or {}
        reason_code = str(
            freshness.get("reason_code")
            or metadata.get("freshness_reason")
            or raw_data.get("freshness_reason")
            or "tracker_evidence_unavailable"
        )
        prediction_only = parse_bool_like(
            metadata.get("prediction_only", raw_data.get("prediction_only")),
            default=False,
        )
        identity_ambiguous = parse_bool_like(
            metadata.get(
                "identity_ambiguous",
                raw_data.get("identity_ambiguous"),
            ),
            default=False,
        ) or reason_code in {
            "identity_ambiguous",
            "identity_mismatch",
            "multiple_identity_candidates",
        }
        identity_confirmed = parse_bool_like(
            metadata.get(
                "identity_confirmed",
                raw_data.get("identity_confirmed", True),
            ),
            default=True,
        )

        if identity_ambiguous:
            state = TargetEvidenceState.AMBIGUOUS
            verdict = IdentityVerdict.AMBIGUOUS
        elif prediction_only:
            state = TargetEvidenceState.PREDICTED
            verdict = IdentityVerdict.UNCONFIRMED
        elif freshness.get("usable_for_following") and identity_confirmed:
            state = TargetEvidenceState.CONFIRMED
            verdict = IdentityVerdict.CONFIRMED
            reason_code = "fresh_identity_confirmed_measurement"
        elif freshness.get("active_tracking"):
            state = TargetEvidenceState.UNCERTAIN
            verdict = IdentityVerdict.UNCONFIRMED
        else:
            state = TargetEvidenceState.ABSENT
            verdict = IdentityVerdict.UNCONFIRMED

        target_id = getattr(tracker_output, "target_id", None)
        if target_id is None:
            target_id = metadata.get("target_identity", raw_data.get("target_identity"))

        return cls(
            state=state,
            observed_at_monotonic_s=now,
            session_epoch=int(session_epoch),
            target_id=None if target_id is None else str(target_id),
            identity_verdict=verdict,
            reason_code=reason_code,
        )


@dataclass(frozen=True)
class ContinuityContext:
    execution_mode: str
    airframe_phase: AirframePhase
    control_type: str
    vehicle_state_fresh: bool
    offboard_active: bool
    publisher_healthy: bool
    vehicle_yaw_deg: Optional[float] = None
    operator_abort: bool = False


@dataclass(frozen=True)
class HandoffRequest:
    action: TerminalAction
    request_id: str
    reason_code: str


@dataclass(frozen=True)
class ContinuityDecision:
    authority_state: ContinuityAuthorityState
    authorized_intent: Optional[CommandIntent]
    authority_fraction: float
    reason_code: str
    episode_id: int
    loss_elapsed_s: float
    coast_distance_m: float
    handoff_request: Optional[HandoffRequest] = None


@dataclass(frozen=True)
class ContinuityPolicy:
    mode: ContinuityMode
    max_coast_time_s: float
    max_coast_distance_m: float
    max_retarget_time_s: float
    reacquire_confirmation_s: float
    authority_restore_time_s: float
    terminal_action: TerminalAction
    retarget_angle_blend_fraction: float = 0.7
    retarget_provisional_authority_fraction: float = 0.5
    retarget_restore_time_s: float = 0.5

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "ContinuityPolicy":
        return cls.resolve(raw, None)

    @classmethod
    def resolve(
        cls, raw: Optional[Mapping[str, Any]], profile_name: Optional[str],
    ) -> "ContinuityPolicy":
        if raw is not None and not isinstance(raw, Mapping):
            raise ValueError("TargetContinuity must be an object")
        values = dict(raw or {})
        overrides = values.pop("FollowerOverrides", {})
        if not isinstance(overrides, Mapping):
            raise ValueError("TargetContinuity.FollowerOverrides must be an object")
        known = {follower.value.upper() for follower in FollowerType}
        resolved = {}
        global_policy = cls._from_flat_mapping(values)
        for name, override in overrides.items():
            if name not in known:
                raise ValueError(f"Unknown TargetContinuity follower: {name!r}")
            if not isinstance(override, Mapping):
                raise ValueError(f"TargetContinuity.FollowerOverrides.{name} must be an object")
            resolved[name] = cls._from_flat_mapping({**values, **override})
        if profile_name is None:
            return global_policy
        name = str(profile_name).upper()
        if name not in known:
            raise ValueError(f"Unknown TargetContinuity follower: {profile_name!r}")
        return resolved.get(name, global_policy)

    @classmethod
    def _from_flat_mapping(cls, raw: Mapping[str, Any]) -> "ContinuityPolicy":
        values = dict(raw or {})
        allowed = {
            "MODE",
            "MAX_COAST_TIME_S",
            "MAX_COAST_DISTANCE_M",
            "MAX_RETARGET_TIME_S",
            "REACQUIRE_CONFIRMATION_S",
            "AUTHORITY_RESTORE_TIME_S",
            "TERMINAL_ACTION",
            "RETARGET_ANGLE_BLEND_FRACTION",
            "RETARGET_PROVISIONAL_AUTHORITY_FRACTION",
            "RETARGET_RESTORE_TIME_S",
        }
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"Unknown TargetContinuity settings: {unknown}")

        try:
            mode = ContinuityMode(values.get("MODE", "immediate_handoff"))
            terminal_action = TerminalAction(values.get("TERMINAL_ACTION", "hold"))
        except ValueError as exc:
            raise ValueError(f"Invalid TargetContinuity enum value: {exc}") from exc

        numeric_defaults = {
            "MAX_COAST_TIME_S": 1.0,
            "MAX_COAST_DISTANCE_M": 2.0,
            "MAX_RETARGET_TIME_S": 3.0,
            "REACQUIRE_CONFIRMATION_S": 0.5,
            "AUTHORITY_RESTORE_TIME_S": 1.0,
            "RETARGET_ANGLE_BLEND_FRACTION": 0.7,
            "RETARGET_PROVISIONAL_AUTHORITY_FRACTION": 0.5,
            "RETARGET_RESTORE_TIME_S": 0.5,
        }
        parsed: Dict[str, float] = {}
        for name, default in numeric_defaults.items():
            value = values.get(name, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"TargetContinuity.{name} must be a finite number")
            parsed[name] = float(value)
            if not math.isfinite(parsed[name]) or parsed[name] < 0.0:
                raise ValueError(f"TargetContinuity.{name} must be finite and non-negative")

        if mode is ContinuityMode.BOUNDED_DECAY and (
            parsed["MAX_COAST_TIME_S"] <= 0.0
            or parsed["MAX_COAST_DISTANCE_M"] <= 0.0
        ):
            raise ValueError(
                "bounded_decay requires positive MAX_COAST_TIME_S and "
                "MAX_COAST_DISTANCE_M"
            )
        if parsed["MAX_RETARGET_TIME_S"] <= 0.0:
            raise ValueError("TargetContinuity.MAX_RETARGET_TIME_S must be positive")
        for name in ("RETARGET_ANGLE_BLEND_FRACTION", "RETARGET_PROVISIONAL_AUTHORITY_FRACTION"):
            if parsed[name] > 1.0:
                raise ValueError(f"TargetContinuity.{name} must be at most 1")

        return cls(
            mode=mode,
            max_coast_time_s=parsed["MAX_COAST_TIME_S"],
            max_coast_distance_m=parsed["MAX_COAST_DISTANCE_M"],
            max_retarget_time_s=parsed["MAX_RETARGET_TIME_S"],
            reacquire_confirmation_s=parsed["REACQUIRE_CONFIRMATION_S"],
            authority_restore_time_s=parsed["AUTHORITY_RESTORE_TIME_S"],
            terminal_action=terminal_action,
            retarget_angle_blend_fraction=parsed["RETARGET_ANGLE_BLEND_FRACTION"],
            retarget_provisional_authority_fraction=parsed["RETARGET_PROVISIONAL_AUTHORITY_FRACTION"],
            retarget_restore_time_s=parsed["RETARGET_RESTORE_TIME_S"],
        )


@dataclass(frozen=True)
class ContinuityStrategyCapability:
    name: str
    airframe_phase: AirframePhase
    control_type: str
    preview_coasting_supported: bool
    live_coasting_supported: bool


class ContinuityStrategyRegistry:
    """Resolve capabilities by physical phase and command type, never follower name."""

    _MC_HORIZONTAL = ContinuityStrategyCapability(
        name="multicopter_horizontal_decay",
        airframe_phase=AirframePhase.MULTICOPTER,
        control_type="velocity_body_offboard",
        preview_coasting_supported=True,
        live_coasting_supported=True,
    )

    @classmethod
    def resolve(
        cls,
        airframe_phase: AirframePhase,
        control_type: str,
    ) -> ContinuityStrategyCapability:
        if (
            airframe_phase is cls._MC_HORIZONTAL.airframe_phase
            and control_type == cls._MC_HORIZONTAL.control_type
        ):
            return cls._MC_HORIZONTAL
        return ContinuityStrategyCapability(
            name="immediate_handoff",
            airframe_phase=airframe_phase,
            control_type=str(control_type),
            preview_coasting_supported=False,
            live_coasting_supported=False,
        )


class TargetContinuitySupervisor:
    """Single command-authority owner for one target-evidence session."""

    def __init__(
        self,
        policy: ContinuityPolicy,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy
        self._clock = clock
        self._state = ContinuityAuthorityState.INACTIVE
        self._session_epoch = 0
        self._episode_id = 0
        self._loss_started_at: Optional[float] = None
        self._last_evaluated_at: Optional[float] = None
        self._last_coast_update_at: Optional[float] = None
        self._coast_distance_m = 0.0
        self._last_coast_speed_m_s = 0.0
        self._loss_entry_intent: Optional[CommandIntent] = None
        self._loss_entry_inertial_velocity: Optional[Tuple[float, float]] = None
        self._reacquire_started_at: Optional[float] = None
        self._restore_started_at: Optional[float] = None
        self._restore_entry_intent: Optional[CommandIntent] = None
        self._last_authority_fraction = 0.0
        self._last_active_yaw_deg: Optional[float] = None
        self._last_reason = "not_started"
        self._pending_handoff: Optional[HandoffRequest] = None
        self._last_handoff_result: Optional[Dict[str, Any]] = None
        self._last_decision: Optional[ContinuityDecision] = None
        self._target_transition_pending = False

    def reset_session(self, *, session_epoch: int, reason: str) -> None:
        self._state = ContinuityAuthorityState.INACTIVE
        self._session_epoch = int(session_epoch)
        self._episode_id = 0
        self._loss_started_at = None
        self._last_evaluated_at = None
        self._last_coast_update_at = None
        self._coast_distance_m = 0.0
        self._last_coast_speed_m_s = 0.0
        self._loss_entry_intent = None
        self._loss_entry_inertial_velocity = None
        self._reacquire_started_at = None
        self._restore_started_at = None
        self._restore_entry_intent = None
        self._last_authority_fraction = 0.0
        self._last_active_yaw_deg = None
        self._last_reason = str(reason)
        self._pending_handoff = None
        self._last_handoff_result = None
        self._last_decision = None
        self._target_transition_pending = False

    def last_authorized_intent(self) -> Optional[CommandIntent]:
        decision = self._last_decision
        return decision.authorized_intent if decision is not None else None

    def begin_target_transition(
        self, *, session_epoch: int, previous_intent: CommandIntent,
    ) -> bool:
        """Continue bounded prior motion while a replacement target is confirmed."""
        fields = previous_intent.fields
        required = {"vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s"}
        if (previous_intent.control_type != "velocity_body_offboard"
                or not required.issubset(fields)
                or any(not math.isfinite(float(value)) for value in fields.values())):
            return False
        now = self._clock()
        if self._loss_started_at is None:
            if self._last_active_yaw_deg is None:
                return False
            self._begin_loss_episode(previous_intent, None, now)
        self._session_epoch = int(session_epoch)
        self._target_transition_pending = True
        self._state = ContinuityAuthorityState.COASTING
        self._reacquire_started_at = None
        self._restore_started_at = None
        self._restore_entry_intent = None
        self._last_reason = "operator_target_transition"
        return True

    def evaluate(
        self,
        evidence: TargetEvidenceSnapshot,
        context: ContinuityContext,
        nominal_intent: Optional[CommandIntent] = None,
        provisional_intent: Optional[CommandIntent] = None,
        *,
        now_monotonic_s: Optional[float] = None,
    ) -> ContinuityDecision:
        now = self._clock() if now_monotonic_s is None else float(now_monotonic_s)
        if not math.isfinite(now):
            raise ValueError("Continuity clock must be finite")
        if self._last_evaluated_at is not None and now < self._last_evaluated_at:
            raise ValueError("Continuity monotonic clock moved backwards")
        self._last_evaluated_at = now

        if evidence.session_epoch != self._session_epoch:
            return self._request_handoff("target_session_epoch_mismatch", now)
        if context.operator_abort:
            return self._request_handoff("operator_abort", now)
        if not context.vehicle_state_fresh:
            return self._request_handoff("vehicle_state_stale", now)
        if not context.publisher_healthy:
            return self._request_handoff("command_publisher_unhealthy", now)
        if context.execution_mode == "PX4" and not context.offboard_active:
            return self._request_handoff("offboard_not_confirmed", now)
        if evidence.state is TargetEvidenceState.AMBIGUOUS:
            return self._request_handoff("target_identity_ambiguous", now)

        if evidence.state is TargetEvidenceState.CONFIRMED:
            return self._handle_confirmed(evidence, context, nominal_intent, now)
        return self._handle_unusable(evidence, context, now, provisional_intent)

    def record_handoff_result(self, *, success: bool, detail: str) -> None:
        self._last_handoff_result = {
            "success": bool(success),
            "detail": str(detail),
            "recorded_at_monotonic_s": self._clock(),
            "request_id": (
                self._pending_handoff.request_id if self._pending_handoff else None
            ),
        }
        if success:
            self._state = ContinuityAuthorityState.INACTIVE
            self._last_authority_fraction = 0.0
            self._pending_handoff = None
            self._target_transition_pending = False
            self._last_reason = "handoff_confirmed"
        else:
            self._state = ContinuityAuthorityState.HANDOFF_PENDING
            self._last_reason = "handoff_unconfirmed"

    def record_authorized_intent(self, intent: CommandIntent) -> None:
        decision = self._last_decision
        if decision is None or decision.authorized_intent is None:
            raise ValueError("No current command authority to record")
        prior = decision.authorized_intent
        if (intent.profile_name != prior.profile_name
                or intent.control_type != prior.control_type
                or set(intent.fields) != set(prior.fields)
                or any(not math.isfinite(float(value)) for value in intent.fields.values())):
            raise ValueError("Submitted command does not match current authority")
        self._last_decision = replace(decision, authorized_intent=intent)
        if self._loss_started_at is not None:
            self._last_coast_speed_m_s = math.hypot(
                float(intent.fields.get("vel_body_fwd", 0.0)),
                float(intent.fields.get("vel_body_right", 0.0)),
            )

    def get_status(self) -> Dict[str, Any]:
        decision = self._last_decision
        return {
            "schema_version": 1,
            "source": "target_continuity_supervisor",
            "authority_state": self._state.value,
            "policy_mode": self.policy.mode.value,
            "terminal_action": self.policy.terminal_action.value,
            "session_epoch": self._session_epoch,
            "episode_id": self._episode_id,
            "authority_fraction": self._last_authority_fraction,
            "loss_elapsed_s": decision.loss_elapsed_s if decision else 0.0,
            "coast_distance_m": self._coast_distance_m,
            "reason_code": self._last_reason,
            "handoff_pending": self._pending_handoff is not None,
            "target_transition_pending": self._target_transition_pending,
            "transition_phase": (
                "retarget" if self._target_transition_pending else
                "loss" if self._state in {ContinuityAuthorityState.COASTING, ContinuityAuthorityState.REACQUIRING}
                else "none"
            ),
            "effective_command_fields": (
                dict(decision.authorized_intent.fields)
                if decision and decision.authorized_intent else None
            ),
            "handoff_request": (
                asdict(self._pending_handoff) if self._pending_handoff else None
            ),
            "last_handoff_result": (
                dict(self._last_handoff_result)
                if self._last_handoff_result is not None
                else None
            ),
            "claim_boundary": (
                "Process-local command-authority decision only; PX4 mode and "
                "vehicle response require separate observed confirmation."
            ),
        }

    def _handle_confirmed(
        self,
        evidence: TargetEvidenceSnapshot,
        context: ContinuityContext,
        nominal_intent: Optional[CommandIntent],
        now: float,
    ) -> ContinuityDecision:
        if nominal_intent is None:
            return self._request_handoff("nominal_intent_missing", now)
        if self._state is ContinuityAuthorityState.HANDOFF_PENDING:
            return self._request_handoff("handoff_already_pending", now)

        if self._state in {
            ContinuityAuthorityState.INACTIVE,
            ContinuityAuthorityState.ACTIVE,
        }:
            self._clear_loss_episode()
            self._state = ContinuityAuthorityState.ACTIVE
            yaw = context.vehicle_yaw_deg
            self._last_active_yaw_deg = (
                float(yaw) if yaw is not None and math.isfinite(yaw) else None
            )
            return self._decision(
                intent=nominal_intent,
                authority_fraction=1.0,
                reason="confirmed_target_authority",
                now=now,
            )

        self._integrate_coast_distance(now)
        budget_reason = self._coast_budget_exhaustion_reason(now)
        if budget_reason is not None:
            return self._request_handoff(budget_reason, now)

        if self._reacquire_started_at is None:
            self._reacquire_started_at = now
            self._restore_started_at = None
            self._restore_entry_intent = None
        self._state = ContinuityAuthorityState.REACQUIRING

        confirmation_elapsed = now - self._reacquire_started_at
        if confirmation_elapsed < self.policy.reacquire_confirmation_s:
            intent, fraction = self._build_decay_intent(context, now)
            if intent is None:
                return self._request_handoff("reacquire_guard_has_no_safe_intent", now)
            if self._target_transition_pending:
                try:
                    intent = self._blend_provisional_intent(intent, nominal_intent)
                except (TypeError, ValueError):
                    return self._request_handoff("provisional_intent_invalid", now)
            return self._decision(
                intent=intent,
                authority_fraction=fraction,
                reason="reacquire_confirmation_pending",
                now=now,
            )

        if self._restore_started_at is None:
            self._restore_started_at = now
            self._restore_entry_intent = (
                self._last_decision.authorized_intent
                if self._target_transition_pending and self._last_decision is not None
                else None
            )
        restore_duration = (self.policy.retarget_restore_time_s if self._target_transition_pending
                            else self.policy.authority_restore_time_s)
        restore_fraction = (
            1.0
            if restore_duration <= 0.0
            else min(1.0, max(0.0, (now - self._restore_started_at) / restore_duration))
        )
        baseline, _ = self._build_decay_intent(context, now)
        if baseline is None:
            return self._request_handoff("authority_restore_has_no_safe_baseline", now)
        if self._restore_entry_intent is not None:
            baseline = self._restore_entry_intent
        restored = self._blend_intents(baseline, nominal_intent, restore_fraction)
        if restore_fraction >= 1.0:
            self._clear_loss_episode()
            self._state = ContinuityAuthorityState.ACTIVE
            return self._decision(
                intent=nominal_intent,
                authority_fraction=1.0,
                reason="target_authority_restored",
                now=now,
            )
        return self._decision(
            intent=restored,
            authority_fraction=restore_fraction,
            reason="target_authority_restoring",
            now=now,
        )

    def _handle_unusable(
        self,
        evidence: TargetEvidenceSnapshot,
        context: ContinuityContext,
        now: float,
        provisional_intent: Optional[CommandIntent],
    ) -> ContinuityDecision:
        if self._state is ContinuityAuthorityState.HANDOFF_PENDING:
            return self._request_handoff("handoff_already_pending", now)
        if (self.policy.mode is ContinuityMode.IMMEDIATE_HANDOFF
                and not self._target_transition_pending):
            return self._request_handoff(evidence.reason_code, now)

        capability = ContinuityStrategyRegistry.resolve(
            context.airframe_phase,
            context.control_type,
        )
        if context.execution_mode == "COMMAND_PREVIEW":
            coast_supported = capability.preview_coasting_supported
        else:
            coast_supported = capability.live_coasting_supported
        if not coast_supported:
            return self._request_handoff(
                f"{capability.name}_coasting_unsupported_for_{context.execution_mode.lower()}",
                now,
            )

        if self._loss_started_at is None:
            if self._state is not ContinuityAuthorityState.ACTIVE:
                return self._request_handoff("loss_without_active_authority", now)
            if self._last_decision is None or self._last_decision.authorized_intent is None:
                return self._request_handoff("loss_entry_intent_missing", now)
            if self._last_active_yaw_deg is None:
                return self._request_handoff("loss_entry_heading_unavailable", now)
            self._begin_loss_episode(
                self._last_decision.authorized_intent,
                context,
                now,
            )
        else:
            self._integrate_coast_distance(now)

        self._reacquire_started_at = None
        self._restore_started_at = None
        self._restore_entry_intent = None
        self._state = ContinuityAuthorityState.COASTING
        budget_reason = self._coast_budget_exhaustion_reason(now)
        if budget_reason is not None:
            return self._request_handoff(budget_reason, now)

        intent, fraction = self._build_decay_intent(context, now)
        if intent is None:
            return self._request_handoff("bounded_decay_intent_unavailable", now)
        if self._target_transition_pending and provisional_intent is not None:
            try:
                intent = self._blend_provisional_intent(intent, provisional_intent)
            except (TypeError, ValueError):
                return self._request_handoff("provisional_intent_invalid", now)
        return self._decision(
            intent=intent,
            authority_fraction=fraction,
            reason=evidence.reason_code,
            now=now,
        )

    def _blend_provisional_intent(
        self, baseline: CommandIntent, provisional: CommandIntent,
    ) -> CommandIntent:
        if (provisional.profile_name != baseline.profile_name
                or provisional.control_type != baseline.control_type
                or set(provisional.fields) != set(baseline.fields)):
            raise ValueError("Provisional intent does not match the active follower")
        if any(not math.isfinite(float(value)) for value in provisional.fields.values()):
            raise ValueError("Provisional intent contains non-finite fields")
        limited = CommandIntent(
            profile_name=provisional.profile_name,
            control_type=provisional.control_type,
            fields={
                name: float(value) * self.policy.retarget_provisional_authority_fraction
                for name, value in provisional.fields.items()
            },
            source="target_continuity", reason="provisional_camera_angles",
        )
        blended = self._blend_intents(
            baseline, limited, self.policy.retarget_angle_blend_fraction,
        )
        # The cap applies to new guidance; the submitted-command slew limiter
        # preserves continuity while already authorized motion decays toward it.
        return blended

    def _begin_loss_episode(
        self,
        intent: CommandIntent,
        context: ContinuityContext,
        now: float,
    ) -> None:
        self._episode_id += 1
        self._loss_started_at = now
        self._last_evaluated_at = now
        self._coast_distance_m = 0.0
        self._loss_entry_intent = intent
        self._last_coast_update_at = now
        self._last_authority_fraction = 1.0
        yaw_rad = math.radians(self._last_active_yaw_deg)
        forward = float(intent.fields.get("vel_body_fwd", 0.0))
        right = float(intent.fields.get("vel_body_right", 0.0))
        north = math.cos(yaw_rad) * forward - math.sin(yaw_rad) * right
        east = math.sin(yaw_rad) * forward + math.cos(yaw_rad) * right
        self._loss_entry_inertial_velocity = (north, east)
        self._last_coast_speed_m_s = math.hypot(north, east)

    def _integrate_coast_distance(self, now: float) -> None:
        if self._last_coast_update_at is None:
            self._last_coast_update_at = now
            return
        dt = max(0.0, now - self._last_coast_update_at)
        self._coast_distance_m += self._last_coast_speed_m_s * dt
        self._last_coast_update_at = now

    def _coast_budget_exhaustion_reason(self, now: float) -> Optional[str]:
        if self._loss_started_at is None:
            return None
        time_budget = (self.policy.max_retarget_time_s if self._target_transition_pending
                       else self.policy.max_coast_time_s)
        if now - self._loss_started_at >= time_budget:
            return ("maximum_retarget_time_reached" if self._target_transition_pending
                    else "maximum_coast_time_reached")
        if self._coast_distance_m >= self.policy.max_coast_distance_m:
            return "maximum_coast_distance_reached"
        return None

    def _build_decay_intent(
        self,
        context: ContinuityContext,
        now: float,
    ) -> Tuple[Optional[CommandIntent], float]:
        if (
            self._loss_started_at is None
            or self._loss_entry_intent is None
            or self._loss_entry_inertial_velocity is None
        ):
            return None, 0.0

        elapsed = max(0.0, now - self._loss_started_at)
        time_budget = (self.policy.max_retarget_time_s if self._target_transition_pending
                       else self.policy.max_coast_time_s)
        time_fraction = max(0.0, 1.0 - elapsed / time_budget)
        distance_fraction = max(
            0.0,
            1.0 - self._coast_distance_m / self.policy.max_coast_distance_m,
        )
        authority = min(
            self._last_authority_fraction,
            time_fraction,
            distance_fraction,
        )
        self._last_authority_fraction = authority

        north, east = self._loss_entry_inertial_velocity
        yaw = context.vehicle_yaw_deg
        if yaw is None or not math.isfinite(yaw):
            if north != 0.0 or east != 0.0:
                return None, 0.0
            yaw = 0.0
        yaw_rad = math.radians(yaw)
        forward = (math.cos(yaw_rad) * north + math.sin(yaw_rad) * east) * authority
        right = (-math.sin(yaw_rad) * north + math.cos(yaw_rad) * east) * authority
        fields = dict(self._loss_entry_intent.fields)
        required = {"vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s"}
        if self._loss_entry_intent.control_type != "velocity_body_offboard" or not required.issubset(fields):
            return None, 0.0
        fields.update(
            {
                "vel_body_fwd": forward,
                "vel_body_right": right,
                "vel_body_down": 0.0,
                "yawspeed_deg_s": 0.0,
            }
        )
        self._last_coast_speed_m_s = math.hypot(forward, right)
        return (
            CommandIntent(
                profile_name=self._loss_entry_intent.profile_name,
                control_type=self._loss_entry_intent.control_type,
                fields=fields,
                source="target_continuity",
                reason="bounded_horizontal_decay",
                created_at_monotonic_s=now,
            ),
            authority,
        )

    @staticmethod
    def _blend_intents(
        baseline: CommandIntent,
        nominal: CommandIntent,
        fraction: float,
    ) -> CommandIntent:
        if (
            baseline.profile_name != nominal.profile_name
            or baseline.control_type != nominal.control_type
            or set(baseline.fields) != set(nominal.fields)
        ):
            raise ValueError("Cannot restore authority across incompatible command intents")
        alpha = min(1.0, max(0.0, float(fraction)))
        fields = {
            name: float(baseline.fields[name])
            + alpha * (float(nominal.fields[name]) - float(baseline.fields[name]))
            for name in baseline.fields
        }
        return CommandIntent(
            profile_name=nominal.profile_name,
            control_type=nominal.control_type,
            fields=fields,
            source="target_continuity",
            reason="authority_restore_ramp",
        )

    def _request_handoff(self, reason: str, now: float) -> ContinuityDecision:
        self._state = ContinuityAuthorityState.HANDOFF_PENDING
        self._last_authority_fraction = 0.0
        if self._pending_handoff is None:
            self._pending_handoff = HandoffRequest(
                action=self.policy.terminal_action,
                request_id=(
                    f"target-continuity-{self._session_epoch}-{self._episode_id}"
                ),
                reason_code=str(reason),
            )
        return self._decision(
            intent=None,
            authority_fraction=0.0,
            reason=str(reason),
            now=now,
            handoff=self._pending_handoff,
        )

    def _decision(
        self,
        *,
        intent: Optional[CommandIntent],
        authority_fraction: float,
        reason: str,
        now: float,
        handoff: Optional[HandoffRequest] = None,
    ) -> ContinuityDecision:
        if (intent is not None and self._loss_started_at is not None
                and self._state in {ContinuityAuthorityState.COASTING,
                                    ContinuityAuthorityState.REACQUIRING}):
            self._last_coast_speed_m_s = math.hypot(
                float(intent.fields.get("vel_body_fwd", 0.0)),
                float(intent.fields.get("vel_body_right", 0.0)),
            )
        elapsed = (
            max(0.0, now - self._loss_started_at)
            if self._loss_started_at is not None
            else 0.0
        )
        decision = ContinuityDecision(
            authority_state=self._state,
            authorized_intent=intent,
            authority_fraction=float(authority_fraction),
            reason_code=str(reason),
            episode_id=self._episode_id,
            loss_elapsed_s=elapsed,
            coast_distance_m=self._coast_distance_m,
            handoff_request=handoff,
        )
        self._last_reason = str(reason)
        self._last_decision = decision
        return decision

    def _clear_loss_episode(self) -> None:
        self._loss_started_at = None
        self._coast_distance_m = 0.0
        self._last_coast_speed_m_s = 0.0
        self._last_coast_update_at = None
        self._loss_entry_intent = None
        self._loss_entry_inertial_velocity = None
        self._reacquire_started_at = None
        self._restore_started_at = None
        self._restore_entry_intent = None
        self._last_authority_fraction = 1.0
        self._pending_handoff = None
        self._target_transition_pending = False


__all__ = [
    "AirframePhase",
    "ContinuityAuthorityState",
    "ContinuityContext",
    "ContinuityDecision",
    "ContinuityMode",
    "ContinuityPolicy",
    "ContinuityStrategyRegistry",
    "HandoffRequest",
    "IdentityVerdict",
    "TargetContinuitySupervisor",
    "TargetEvidenceSnapshot",
    "TargetEvidenceState",
    "TerminalAction",
]
