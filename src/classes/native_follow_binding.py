"""Join native phase guidance to the existing publisher and continuity owner.

No worker, loss deadline or flight controller lives here. The application owns
startup/teardown; its existing publisher delivers observations to this binding.
"""

from copy import deepcopy
import asyncio
from dataclasses import replace
import math
import time

from classes.command_dispatch_guard import DispatchRefusalKind, DispatchRefused, validate_before_dispatch
from classes.aircraft_state import AircraftKind, AircraftLayout, AircraftState, AirframePhase
from classes.guidance_phase_session import PhaseSessionState
from classes.native_command_transport import NativeCommandTransport
from classes.native_guidance import NativeAcquisitionContext, NativeGuidanceError, NativeReleaseReceipt, NativeStartContext, make_ownership_token
from classes.target_continuity import ContinuityMode, ContinuityPolicy, TargetEvidenceState


def requires_native_guidance(profile: dict, aircraft_kind: AircraftKind, *,
                             expected_layout: AircraftLayout = AircraftLayout.AUTO) -> bool:
    """An installation label never establishes VTOL's current flight phase."""
    phases = profile.get("native_phase_contracts", {})
    if not phases:
        return False
    if not isinstance(aircraft_kind, AircraftKind) or aircraft_kind is AircraftKind.UNKNOWN:
        raise ValueError("aircraft_kind_unavailable")
    if not isinstance(expected_layout, AircraftLayout) or not expected_layout.accepts_kind(aircraft_kind):
        raise ValueError("aircraft_layout_mismatch")
    if aircraft_kind is AircraftKind.MULTICOPTER:
        return False
    supported = {"multicopter", "fixed_wing"} & set(phases)
    if not supported or aircraft_kind is AircraftKind.FIXED_WING and "fixed_wing" not in supported:
        raise ValueError("follower_airframe_strategy_unavailable")
    return True


class NativeFollowBinding:
    def __init__(self, guidance, connection, client, continuity, *, profile_name: str,
                 continuity_config, target_evidence, context, circuit_breaker, clock=time.monotonic):
        self.guidance = guidance
        self.connection = connection
        self.client = client
        self.continuity = continuity
        self.profile_name = profile_name
        self._continuity_config = deepcopy(continuity_config)
        if AirframePhase.FIXED_WING in guidance.supported_phases:
            fw_policy = ContinuityPolicy.resolve(self._continuity_config, profile_name, AirframePhase.FIXED_WING)
            if fw_policy.mode is not ContinuityMode.BOUNDED_FLIGHT:
                raise ValueError("native_fixed_wing_continuity_not_configured")
        self._target_evidence = target_evidence
        self._context = context
        self._circuit_breaker = circuit_breaker
        self.clock = clock
        self.transport = NativeCommandTransport(
            client, connection, guidance.identity, circuit_breaker=circuit_breaker,
            clock=clock, on_observation=self.on_observation, altitude_limits=guidance.altitude_limits,
        )
        self._engage_attempted = False
        self._engage_in_progress = False
        self.acquire_dispatched = False
        self._stopping = False
        self._acquisition_identity = guidance.identity
        self._runtime_id = guidance.phase_owner.capabilities.runtime_id
        self._mode_id = guidance.phase_owner.capabilities.owned_mode_id
        self._ownership_token = None
        self._acquisition = None
        self._release_receipt = None
        self._strategy_bound = False
        self._stop_lock = asyncio.Lock()

    @property
    def owner_confirmed(self) -> bool:
        return (not self._stopping and self.transport.ready()
                and self.guidance.phase_owner.state is not PhaseSessionState.ENDED)

    @property
    def pursuit_paused(self) -> bool:
        return self.guidance.phase_owner.state is not PhaseSessionState.PURSUIT

    @property
    def terminal_reason(self) -> str | None:
        owner = self.guidance.phase_owner
        return owner.reason if owner.state is PhaseSessionState.ENDED else None

    @property
    def release_receipt(self) -> NativeReleaseReceipt | None:
        receipt = self._release_receipt
        if receipt is None:
            return None
        if not isinstance(receipt, NativeReleaseReceipt):
            raise NativeGuidanceError("native_release_receipt_invalid")
        receipt.require_match(self._acquisition_identity, self._runtime_id, self._ownership_token, self._acquisition)
        if not receipt.released:
            raise NativeGuidanceError("native_release_unconfirmed")
        return receipt

    def context(self, base):
        state = self.connection.get_aircraft_state()
        return replace(
            base, execution_mode="PX4_NATIVE", airframe_phase=self.guidance.phase,
            control_type=self.guidance.control_type,
            vehicle_state_fresh=state is not None,
            offboard_active=self.owner_confirmed, guidance_identity=self.guidance.identity,
            pursuit_paused=self.pursuit_paused,
            vehicle_yaw_deg=None if state is None else math.degrees(state.navigation_heading_rad),
        )

    async def engage(self, *, start_context=None, before_dispatch=None, on_mode_dispatch=None):
        if self._engage_attempted or self._stopping:
            raise NativeGuidanceError("native_follow_binding_already_started")
        self._engage_attempted = True
        self._engage_in_progress = True
        self._ownership_token = make_ownership_token()
        try:
            def may_engage():
                if self._stopping:
                    raise DispatchRefused("native_follow_stopping", DispatchRefusalKind.TERMINAL)
                validate_before_dispatch(before_dispatch)

            def dispatched():
                validate_before_dispatch(on_mode_dispatch)
                self.acquire_dispatched = True
            state = self.connection.get_aircraft_state()
            if state is None:
                raise NativeGuidanceError("native_aircraft_state_unavailable")
            if not isinstance(start_context, NativeStartContext):
                raise NativeGuidanceError("native_start_context_required")
            phase = self.guidance.phase_owner.initial_phase or state.phase
            start_context.require_match(state.binding, self._runtime_id, phase=phase)
            if state.phase is not phase:
                raise NativeGuidanceError("native_start_context_changed")
            altitude_reference = self.guidance.prepare_engagement_reference(state)
            result = await self.client.engage(
                self._acquisition_identity, ownership_token=self._ownership_token,
                altitude_reference=altitude_reference,
                start_context=start_context,
                circuit_breaker_active=self._circuit_breaker(),
                before_dispatch=may_engage, on_mode_dispatch=dispatched)
            self._acquisition = NativeAcquisitionContext.from_payload(result.get("acquisition"))
            self._acquisition.require_match(self._acquisition_identity, self._runtime_id,
                                            self._ownership_token, mode_id=self._mode_id)
            if (result.get("owner_confirmed") is not True or result.get("runtime_id") != self._runtime_id
                    or self._acquisition.activation_timestamp == 0):
                raise NativeGuidanceError("native_ownership_not_confirmed")
            if self._stopping:
                raise NativeGuidanceError("native_follow_stopping")
            self.transport.bind_acquisition(self._acquisition)
            observation = await self.client.observe()
            if observation.get("fresh") is not True or observation.get("rescue_active") is not False:
                raise NativeGuidanceError("native_aircraft_state_unavailable")
            state = AircraftState.from_payload(observation["aircraft_state"])
            commit = getattr(self.connection, "commit_native_observation", None)
            if callable(commit):
                if commit(observation) is not True:
                    raise NativeGuidanceError("native_aircraft_state_rejected")
            else:
                self.connection.commit_aircraft_state(state)
            accepted = self.connection.get_aircraft_state()
            if accepted is None or accepted != state:
                raise NativeGuidanceError("native_aircraft_state_rejected")
            return await self.on_observation(state, observation, None)
        except BaseException:
            self.abort("native_follow_start_failed")
            raise
        finally:
            self._engage_in_progress = False

    async def on_observation(self, state: AircraftState | None, observation, intent):
        if not self._owns_client_acquisition():
            self.abort("native_session_replaced")
            raise DispatchRefused("native_session_replaced", DispatchRefusalKind.TERMINAL)
        if self._stopping:
            raise DispatchRefused("native_follow_stopping", DispatchRefusalKind.TERMINAL)
        if self.terminal_reason is not None:
            self.abort(self.terminal_reason)
            raise DispatchRefused(self.terminal_reason, DispatchRefusalKind.TERMINAL)
        if state is None or observation.get("fresh") is not True:
            self.abort("native_aircraft_state_unavailable")
            raise DispatchRefused("native_aircraft_state_unavailable", DispatchRefusalKind.TERMINAL)
        owner = self.guidance.phase_owner
        if not state.fresh(self.clock(), owner.observation_timeout_s):
            self.abort("aircraft_state_stale")
            raise DispatchRefused("aircraft_state_stale", DispatchRefusalKind.TERMINAL)
        if observation.get("rescue_active") is not False or state.rescue_active:
            self.abort("aircraft_rescue_active")
            raise DispatchRefused("aircraft_rescue_active", DispatchRefusalKind.TERMINAL)
        expected_phase = owner.initial_phase or owner.phase
        # A known interruption must revoke controls before tracker/target work.
        interrupted = (observation.get("owner_confirmed") is not True
                       or state.phase not in self.guidance.supported_phases
                       or expected_phase is not AirframePhase.UNKNOWN and state.phase is not expected_phase
                       or state.binding != self.guidance.identity.binding
                       or not owner.expected_layout.matches(state))
        target_confirmed = (owner.state is not PhaseSessionState.PURSUIT and not interrupted
                            and self._target_evidence().state is TargetEvidenceState.CONFIRMED)
        decision = self.guidance.observe(
            state, owner_confirmed=observation.get("owner_confirmed") is True,
            target_confirmed=target_confirmed,
        )
        if decision.state is PhaseSessionState.ENDED:
            self.abort(decision.reason)
            raise DispatchRefused(decision.reason, DispatchRefusalKind.TERMINAL)
        if not self._strategy_bound:
            baseline = self.guidance.baseline()
            phase = self.guidance.phase
            policy = ContinuityPolicy.resolve(
                self._continuity_config, self.profile_name,
                phase,
            )
            result = self.continuity.bind_initial_strategy(
                policy, baseline, self.context(self._context()), now_monotonic_s=self.clock(),
            )
            if result.handoff_request is not None:
                self.abort(result.reason_code)
                raise DispatchRefused(result.reason_code, DispatchRefusalKind.TERMINAL)
            self._strategy_bound = True
        if (intent is None or not decision.pursuit_allowed
                or intent.guidance_identity != self.guidance.identity):
            return self.guidance.baseline()
        return intent

    def paused_baseline(self):
        if not self.owner_confirmed:
            return None
        if self.guidance.phase_owner.state is PhaseSessionState.PURSUIT:
            return None
        return self.guidance.baseline()

    def abort(self, reason: str):
        self._stopping = True
        self.guidance.end(reason)
        if (self._owns_client_acquisition()
                or not self.acquire_dispatched and self.client.session_identity is None
                and self.client.acquisition_token is None):
            self.client.abort()

    def _owns_client_acquisition(self):
        return self._ownership_token is not None and self.client.matches_acquisition(
            self._acquisition_identity, self._runtime_id, self._ownership_token, self._acquisition)

    def _release_result(self, reason):
        receipt = self.release_receipt
        hold = receipt.outcome == "hold_confirmed"
        return {"executed": hold, "local_sender_quiesced": True,
                "reason": reason if hold else "native_owner_already_released",
                "observed_nav_state": receipt.observed_nav_state,
                "release_receipt": receipt.wire_payload(), "errors": []}

    async def stop(self, reason: str):
        """Called after the existing publisher has joined; never reacquire control."""
        self._stopping = True
        self.guidance.end(reason)
        if self._engage_in_progress:
            self.abort(reason)
        async with self._stop_lock:
            return await self._stop(reason)

    async def _stop(self, reason: str):
        if self._release_receipt is not None:
            return self._release_result(reason)
        identity = self.transport.identity
        if not self.acquire_dispatched:
            if self.client.session_identity is None and self.client.acquisition_token in (None, self._ownership_token):
                self.transport.abort()
            return {"executed": False, "local_sender_quiesced": True,
                    "reason": "native_acquire_not_dispatched", "errors": []}
        if not self._owns_client_acquisition():
            raise NativeGuidanceError("native_session_replaced")
        try:
            if self.client.session_identity != identity:
                if self.client.session_identity is not None:
                    raise NativeGuidanceError("native_session_replaced")
                receipt = await self.client.observe_after_release(
                    self._acquisition_identity, runtime_id=self._runtime_id,
                    ownership_token=self._ownership_token, mode_id=self._mode_id, acquisition=self._acquisition,
                )
            else:
                receipt = await self.client.handoff(identity, reason=reason, ownership_token=self._ownership_token,
                                                    acquisition=self._acquisition)
            if not isinstance(receipt, NativeReleaseReceipt):
                raise NativeGuidanceError("native_release_receipt_invalid")
            receipt.require_match(self._acquisition_identity, self._runtime_id, self._ownership_token, self._acquisition)
            if not receipt.released:
                raise NativeGuidanceError("native_release_unconfirmed")
            self._release_receipt = receipt
            return self._release_result(reason)
        finally:
            if self.client.session_identity in (None, identity) and self._owns_client_acquisition():
                self.client.abort()
