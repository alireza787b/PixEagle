"""Native command boundary used by the existing OffboardCommander scheduler.

This transport owns no heartbeat, tracker, recovery timer or flight controller.
It validates phase identity and converts typed intents to the native adapter.
The application's existing command owner supplies its canonical intent TTL.
"""

from dataclasses import replace
import math
import time
from typing import Awaitable, Callable

from classes.aircraft_state import AircraftState, AirframePhase, Vector3, heading_frame_to_ned
from classes.command_intent import CommandIntent
from classes.fixed_wing_vector_guidance import FixedWingCommand
from classes.native_guidance import ExternalModeIntent, NativeMulticopterCommand, NativeTransitionCommand


class NativeCommandTransport:
    publication_source = "px4_native_external_mode"

    def __init__(self, client, connection, identity, *, circuit_breaker, clock=time.monotonic,
                 on_observation: Callable[[AircraftState, dict, CommandIntent], Awaitable[CommandIntent]] | None = None):
        self.client = client
        self.connection = connection
        self.identity = identity
        self.circuit_breaker = circuit_breaker
        self.clock = clock
        self.on_observation = on_observation
        self._sequence = 0
        self._last_created = None
        self.last_feedback = None
        self.last_handoff = None
        self.last_published_intent = None
        self._pending_identity = None

    def ready(self) -> bool:
        state = self.connection.get_aircraft_state()
        return bool(self.client.session_identity == self.identity and state is not None
                    and state.binding == self.identity.binding and not state.rescue_active)

    def abort(self) -> None:
        self.client.abort()

    def _command(self, intent, state, *, identity=None):
        identity = self.identity if identity is None else identity
        if intent.guidance_identity != identity or state.binding != identity.binding:
            raise ValueError("native_command_identity_stale")
        if state.phase is AirframePhase.FIXED_WING:
            return FixedWingCommand.from_intent(intent)
        if state.phase is AirframePhase.MULTICOPTER and state.is_vtol:
            fields = intent.fields
            if (intent.control_type != "velocity_body_offboard"
                    or set(fields) != {"vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s"}):
                raise ValueError("native_mc_command_contract_invalid")
            velocity = heading_frame_to_ned(Vector3(fields["vel_body_fwd"], fields["vel_body_right"],
                                                     fields["vel_body_down"]), state.navigation_heading_rad)
            return NativeMulticopterCommand(velocity, math.radians(fields["yawspeed_deg_s"]))
        if state.phase is AirframePhase.VTOL_TRANSITION and state.is_vtol:
            if (intent.control_type != "vtol_transition_external"
                    or set(intent.fields) != {"course_rad", "equivalent_airspeed_m_s"}):
                raise ValueError("native_transition_command_contract_invalid")
            return NativeTransitionCommand(**intent.fields)
        raise ValueError("native_phase_contract_unavailable")

    def accept_intent(self, intent: CommandIntent) -> CommandIntent:
        state = self.connection.get_aircraft_state()
        if not self.ready() or state is None:
            raise ValueError("native_command_owner_unavailable")
        now, created = self.clock(), intent.created_at_monotonic_s
        if (isinstance(created, bool) or not isinstance(created, (int, float)) or not math.isfinite(created)
                or created > now or self._last_created is not None and created < self._last_created):
            raise ValueError("native_command_obsolete")
        self._command(intent, state, identity=self._pending_identity or self.identity)
        self._last_created = created
        return replace(intent, fields=dict(intent.fields))

    async def advance_generation(self, identity) -> None:
        if self._pending_identity is not None:
            raise ValueError("native_phase_binding_in_progress")
        self._pending_identity = identity
        self._last_created = None
        try:
            await self.client.advance_generation(identity)
            self.identity = identity
            self._sequence = 0
        except BaseException:
            self.abort()
            raise
        finally:
            self._pending_identity = None

    async def publish(self, intent: CommandIntent | None, *, reason: str, ttl_s: float) -> bool:
        self.last_published_intent = None
        if intent is None:
            if self.client.session_identity != self.identity:
                return False
            self.last_handoff = await self.client.handoff(self.identity, reason=reason)
            return self.last_handoff.get("hold_observed") is True
        observation = await self.client.observe()
        if (observation.get("fresh") is not True or observation.get("owner_confirmed") is not True
                or observation.get("rescue_active") is not False):
            raise ValueError("native_command_owner_unavailable")
        incoming = AircraftState.from_payload(observation["aircraft_state"])
        self.connection.commit_aircraft_state(incoming)
        state = self.connection.get_aircraft_state()
        if state is None or not self.ready():
            raise ValueError("native_aircraft_state_stale")
        if (state.source != incoming.source or state.binding != incoming.binding or state.phase != incoming.phase
                or state.is_vtol != incoming.is_vtol or state.is_tailsitter != incoming.is_tailsitter):
            raise ValueError("native_aircraft_state_rejected")
        if self.on_observation is not None:
            intent = await self.on_observation(state, observation, intent)
            if not isinstance(intent, CommandIntent):
                raise ValueError("native_phase_intent_unavailable")
        now = self.clock()
        created = intent.created_at_monotonic_s
        if (isinstance(created, bool) or not isinstance(created, (int, float))
                or not math.isfinite(created) or created > now):
            raise ValueError("native_command_obsolete")
        # Retransmission cannot turn an old intent into a newly created one.
        expires = intent.created_at_monotonic_s + ttl_s
        command = self._command(intent, state)
        external = ExternalModeIntent(self.identity, self._sequence, now, expires, command)
        await self.client.submit(external, circuit_breaker_active=self.circuit_breaker())
        self._sequence += 1
        self.last_published_intent = replace(intent, fields=dict(intent.fields))
        self.last_feedback = observation.get("native_guidance_feedback")
        return True
