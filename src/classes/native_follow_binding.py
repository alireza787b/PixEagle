"""Join native phase guidance to the existing publisher and continuity owner.

No worker, loss deadline or flight controller lives here. The application owns
startup/teardown; its existing publisher delivers observations to this binding.
"""

from copy import deepcopy
from dataclasses import replace
import math
import time

from classes.aircraft_state import AircraftKind, AircraftLayout, AircraftState, AirframePhase
from classes.guidance_phase_session import PhaseSessionState
from classes.native_command_transport import NativeCommandTransport
from classes.native_guidance import NativeGuidanceError
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
    required = ({"multicopter", "fixed_wing", "vtol_transition"} if aircraft_kind is AircraftKind.VTOL
                else {"fixed_wing"})
    if not required.issubset(phases):
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
        fw_policy = ContinuityPolicy.resolve(self._continuity_config, profile_name, AirframePhase.FIXED_WING)
        if fw_policy.mode is not ContinuityMode.BOUNDED_FLIGHT:
            raise ValueError("native_fixed_wing_continuity_not_configured")
        self._target_evidence = target_evidence
        self._context = context
        self._circuit_breaker = circuit_breaker
        self.clock = clock
        self.transport = NativeCommandTransport(
            client, connection, guidance.identity, circuit_breaker=circuit_breaker,
            clock=clock, on_observation=self.on_observation,
        )
        self._engage_attempted = False
        self._stopping = False
        self._activation_timestamp = None

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

    async def engage(self):
        if self._engage_attempted or self._stopping:
            raise NativeGuidanceError("native_follow_binding_already_started")
        self._engage_attempted = True
        try:
            await self.client.engage(self.guidance.identity, circuit_breaker_active=self._circuit_breaker())
            observation = await self.client.observe()
            if observation.get("fresh") is not True or observation.get("rescue_active") is not False:
                raise NativeGuidanceError("native_aircraft_state_unavailable")
            epoch = observation.get("nav_state_timestamp")
            if type(epoch) is not int or epoch <= 0:
                raise NativeGuidanceError("native_activation_context_missing")
            self._activation_timestamp = epoch
            state = AircraftState.from_payload(observation["aircraft_state"])
            self.connection.commit_aircraft_state(state)
            accepted = self.connection.get_aircraft_state()
            if accepted is None or accepted != state:
                raise NativeGuidanceError("native_aircraft_state_rejected")
            return await self.on_observation(state, observation, None)
        except BaseException:
            self.abort("native_follow_start_failed")
            raise

    async def on_observation(self, state, observation, intent):
        if self._stopping:
            raise NativeGuidanceError("native_follow_stopping")
        evidence = self._target_evidence()
        decision = self.guidance.observe(
            state, owner_confirmed=observation.get("owner_confirmed") is True,
            target_confirmed=evidence.state is TargetEvidenceState.CONFIRMED,
        )
        if decision.state is PhaseSessionState.ENDED:
            self.abort(decision.reason)
            raise NativeGuidanceError(decision.reason)
        generation_changed = self.transport.identity != self.guidance.identity
        if generation_changed:
            baseline = self.guidance.baseline()
            phase = self.guidance.phase
            policy = ContinuityPolicy.resolve(
                self._continuity_config, self.profile_name,
                phase if phase is not AirframePhase.VTOL_TRANSITION else None,
            )
            result = self.continuity.rebind_strategy(
                policy, baseline, self.context(self._context()), now_monotonic_s=self.clock(),
            )
            if result.handoff_request is not None:
                self.abort(result.reason_code)
                raise NativeGuidanceError(result.reason_code)
            await self.transport.advance_generation(self.guidance.identity)
        if (intent is None or generation_changed or not decision.pursuit_allowed
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
        self.transport.abort()

    async def stop(self, reason: str):
        """Called after the existing publisher has joined; never reacquire control."""
        self._stopping = True
        self.guidance.end(reason)
        identity = self.transport.identity
        try:
            if self.client.session_identity != identity:
                if self.client.session_identity is not None:
                    raise NativeGuidanceError("native_session_replaced")
                observation = await self.client.observe_after_release(
                    identity.binding, runtime_id=self.guidance.phase_owner.capabilities.runtime_id,
                    activation_timestamp=self._activation_timestamp,
                )
                hold = observation["nav_state"] == 4 and not observation["rescue_active"]
                return {"executed": hold, "local_sender_quiesced": True,
                        "reason": reason if hold else "native_owner_already_released",
                        "observed_nav_state": observation["nav_state"], "errors": []}
            result = await self.client.handoff(identity, reason=reason)
            if result.get("hold_observed") is not True:
                raise NativeGuidanceError("native_hold_not_confirmed")
            return {"executed": True, "local_sender_quiesced": True,
                    "reason": reason, "errors": []}
        finally:
            if self.client.session_identity in (None, identity):
                self.client.abort()
