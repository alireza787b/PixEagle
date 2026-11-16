"""Stock command ownership joined to the existing phase and continuity session."""

from dataclasses import replace
from copy import deepcopy
import asyncio
import math
import time

from classes.aircraft_state import AirframePhase
from classes.command_dispatch_guard import DispatchRefused, DispatchRefusalKind
from classes.guidance_phase_session import PhaseSessionState
from classes.mavlink_command_transport import MavlinkCommandTransport
from classes.mavlink_guidance_source import MavlinkStartContext
from classes.target_continuity import ContinuityMode, ContinuityPolicy, TargetEvidenceState


class MavlinkFollowBinding:
    def __init__(self, guidance, connection, source, continuity, *, continuity_config,
                 target_evidence, context, owns_session, circuit_breaker,
                 command_period_s, prime_duration_s, clock=time.monotonic):
        self.guidance, self.connection, self.source, self.continuity = guidance, connection, source, continuity
        self.profile_name = guidance.profile_name
        self._context, self._continuity_config = context, deepcopy(continuity_config)
        self._strategy_bound = False
        self._stopping = False
        self.clock = clock
        self._connection_generation = connection.connection_generation
        if (AirframePhase.FIXED_WING in guidance.supported_phases
                and ContinuityPolicy.resolve(continuity_config, guidance.profile_name, AirframePhase.FIXED_WING).mode
                is not ContinuityMode.BOUNDED_FLIGHT):
            raise ValueError("fixed_wing_continuity_not_configured")
        async def send(packet):
            if not connection.is_command_connection_ready(expected_generation=self._connection_generation):
                raise DispatchRefused("mavlink_command_connection_changed", DispatchRefusalKind.TERMINAL)
            await connection.drone.mavlink_direct.send_message(packet.sdk_message())
        self.transport = MavlinkCommandTransport(guidance, observe=connection.get_mavlink_guidance_observation,
            send=send, owns_session=owns_session,
            target_confirmed=lambda: target_evidence().state is TargetEvidenceState.CONFIRMED,
            circuit_breaker=circuit_breaker, command_period_s=command_period_s, prime_duration_s=prime_duration_s,
            command_timeout_s=connection.get_mavsdk_command_timeout_s(), on_observation=self._bind_strategy, clock=clock)

    @property
    def owner_confirmed(self):
        return not self._stopping and self.transport.owner_confirmed

    @property
    def pursuit_paused(self):
        return self.guidance.phase_owner.state is not PhaseSessionState.PURSUIT

    @property
    def terminal_reason(self):
        owner = self.guidance.phase_owner
        return owner.reason if owner.state is PhaseSessionState.ENDED else None

    @property
    def release_confirmed(self):
        return (self.transport.last_handoff or {}).get("authority_released") is True

    def context(self, base):
        state = self.connection.get_aircraft_state()
        return replace(base, execution_mode="PX4", airframe_phase=self.guidance.phase,
            control_type=self.guidance.control_type, vehicle_state_fresh=state is not None,
            offboard_active=self.owner_confirmed, guidance_identity=self.guidance.identity,
            pursuit_paused=self.pursuit_paused,
            vehicle_yaw_deg=None if state is None else math.degrees(state.navigation_heading_rad))

    def _bind_strategy(self, observation):
        if self._strategy_bound:
            return
        policy = ContinuityPolicy.resolve(self._continuity_config, self.guidance.profile_name, self.guidance.phase)
        result = self.continuity.bind_initial_strategy(policy, self.guidance.baseline(),
            self.context(self._context()), now_monotonic_s=self.clock())
        if result.handoff_request is not None:
            self.abort(result.reason_code)
            raise DispatchRefused(result.reason_code, DispatchRefusalKind.TERMINAL)
        self._strategy_bound = True

    async def engage(self, *, start_context, before_dispatch, on_mode_dispatch=None):
        # The stock owner must never overlap the SDK plugin's autonomous
        # resend loop, including one retained by a surviving SDK server.
        if await asyncio.wait_for(self.connection.drone.offboard.is_active(),
                                  timeout=self.connection.get_mavsdk_command_timeout_s()):
            raise ValueError("mavsdk_autoresend_owner_active")
        if not isinstance(start_context, MavlinkStartContext) or start_context != self.source.start_context:
            raise ValueError("mavlink_start_context_changed")
        start_context.require_match(self.guidance.identity.binding, self.source.runtime_id,
            phase=self.guidance.phase_owner.initial_phase)
        return await self.transport.engage(before_dispatch=before_dispatch, on_mode_dispatch=on_mode_dispatch)

    def paused_baseline(self):
        if self.owner_confirmed and self.pursuit_paused:
            return self.guidance.baseline()
        return None

    def abort(self, reason):
        self._stopping = True
        self.transport.abort(reason)

    async def stop(self, reason):
        self._stopping = True
        return await self.transport.stop(reason)
