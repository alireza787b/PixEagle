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
from classes.command_intent import AltitudeHoldReference, CommandIntent
from classes.command_dispatch_guard import DispatchRefused, DispatchRefusalKind
from classes.fixed_wing_vector_guidance import FixedWingCommand
from classes.safety_types import AltitudeLimits
from classes.native_guidance import (
    ExternalModeIntent, NativeAcquisitionContext, NativeBackendRefusal, NativeMulticopterCommand, NativeReleaseReceipt,
)


class NativeCommandTransport:
    publication_source = "px4_native_external_mode"

    def __init__(self, client, connection, identity, *, circuit_breaker, clock=time.monotonic,
                 on_observation: Callable[[AircraftState | None, dict, CommandIntent], Awaitable[CommandIntent]] | None = None,
                 altitude_limits: AltitudeLimits | None = None):
        self.client = client
        self.connection = connection
        self.identity = identity
        self.circuit_breaker = circuit_breaker
        self.clock = clock
        self.on_observation = on_observation
        self.altitude_limits = altitude_limits
        self._sequence = 0
        self._last_created = None
        self.last_feedback = None
        self.last_handoff = None
        self.last_published_intent = None
        self.last_backend_refusal = None
        self._publication_origin = None
        self._last_publications = None
        self._publication_counter_invalid = False
        self._acquisition = None

    def bind_acquisition(self, acquisition: NativeAcquisitionContext) -> None:
        """Pin the validated engage ACK before any command can enter publication."""
        if (not isinstance(acquisition, NativeAcquisitionContext) or acquisition.identity != self.identity
                or acquisition.activation_timestamp == 0):
            raise ValueError("native_acquisition_context_invalid")
        if self._acquisition is not None and self._acquisition != acquisition:
            raise ValueError("native_acquisition_context_changed")
        self._acquisition = acquisition

    def ready(self) -> bool:
        state = self.connection.get_aircraft_state()
        acquisition = self._acquisition
        return bool(acquisition is not None and self.client.matches_acquisition(
                    acquisition.identity, acquisition.runtime_id, acquisition.token, acquisition)
                    and self.client.session_identity == self.identity and state is not None
                    and state.binding == self.identity.binding and not state.rescue_active)

    def abort(self) -> None:
        acquisition = self._acquisition
        if (acquisition is not None and self.client.matches_acquisition(
                acquisition.identity, acquisition.runtime_id, acquisition.token, acquisition)
                or acquisition is None and self.client.session_identity is None and self.client.acquisition_token is None):
            self.client.abort()

    def published_intent(self, *, ttl_s: float) -> CommandIntent | None:
        """Current adapter-accepted command, never a predicted PX4 response."""
        intent = self.last_published_intent
        state = self.connection.get_aircraft_state()
        if (not self.ready() or state is None or intent is None or intent.guidance_identity != self.identity
                or not 0. <= self.clock() - intent.created_at_monotonic_s <= ttl_s):
            return None
        try:
            self._command(intent, state)
        except ValueError:
            return None
        return replace(intent, fields=dict(intent.fields))

    @property
    def observed_publications(self) -> int | None:
        if not self.ready() or self._publication_counter_invalid or self._publication_origin is None:
            return None
        return self._last_publications - self._publication_origin

    def _record_publication_count(self, value):
        if type(value) is not int or value < 0:
            return
        if self._last_publications is not None and value < self._last_publications:
            self._publication_counter_invalid = True
        if self._publication_origin is None:
            self._publication_origin = value
        self._last_publications = value

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
            hold = intent.altitude_hold
            if hold is not None:
                if (not isinstance(hold, AltitudeHoldReference)
                        or not self.client.capabilities.multicopter_altitude_hold_supported
                        or not isinstance(self.altitude_limits, AltitudeLimits)):
                    raise ValueError("native_mc_altitude_hold_unavailable")
                if hold.reference_generation != state.altitude_reference_generation:
                    raise ValueError("altitude_reference_changed")
                self.altitude_limits.require_hold_target(
                    hold.altitude_amsl_m, current_amsl_m=state.altitude_amsl_m,
                    current_relative_m=state.relative_altitude_m)
            return NativeMulticopterCommand(velocity, math.radians(fields["yawspeed_deg_s"]), hold)
        raise ValueError("native_phase_contract_unavailable")

    def accept_intent(self, intent: CommandIntent) -> CommandIntent:
        state = self.connection.get_aircraft_state()
        if not self.ready() or state is None:
            raise ValueError("native_command_owner_unavailable")
        now, created = self.clock(), intent.created_at_monotonic_s
        if (isinstance(created, bool) or not isinstance(created, (int, float)) or not math.isfinite(created)
                or created > now or self._last_created is not None and created < self._last_created):
            raise ValueError("native_command_obsolete")
        self._command(intent, state)
        self._last_created = created
        return replace(intent, fields=dict(intent.fields))

    async def publish(self, intent: CommandIntent | None, *, reason: str, ttl_s: float, before_dispatch=None) -> bool:
        self.last_published_intent = None
        acquisition = self._acquisition
        if acquisition is None:
            raise ValueError("native_acquisition_context_missing")
        if intent is None:
            if self.client.session_identity != self.identity:
                return False
            self.last_handoff = await self.client.handoff(
                self.identity, ownership_token=acquisition.token, acquisition=acquisition,
                reason=reason, before_dispatch=before_dispatch)
            if not isinstance(self.last_handoff, NativeReleaseReceipt):
                raise ValueError("native_release_receipt_invalid")
            self.last_handoff.require_match(self.identity, acquisition.runtime_id, acquisition.token, acquisition)
            return self.last_handoff.released
        observation = await self.client.observe()
        payload = observation.get("aircraft_state")
        incoming = None if payload is None else AircraftState.from_payload(payload)
        state = None
        state_rejected = False
        if (incoming is not None and self.client.matches_acquisition(
                acquisition.identity, acquisition.runtime_id, acquisition.token, acquisition)):
            self.connection.commit_aircraft_state(incoming)
            state = self.connection.get_aircraft_state()
            if state is not None and state != incoming:
                state, state_rejected = None, True
        if self.on_observation is not None:
            intent = await self.on_observation(state, observation, intent)
            if not isinstance(intent, CommandIntent):
                raise ValueError("native_phase_intent_unavailable")
        if (observation.get("fresh") is not True or observation.get("owner_confirmed") is not True
                or observation.get("rescue_active") is not False):
            raise ValueError("native_command_owner_unavailable")
        if state_rejected:
            raise ValueError("native_aircraft_state_rejected")
        if state is None or not self.ready():
            raise ValueError("native_aircraft_state_stale")
        self._record_publication_count(observation.get("publications"))
        now = self.clock()
        created = intent.created_at_monotonic_s
        if (isinstance(created, bool) or not isinstance(created, (int, float))
                or not math.isfinite(created) or created > now):
            raise ValueError("native_command_obsolete")
        # Retransmission cannot turn an old intent into a newly created one.
        expires = intent.created_at_monotonic_s + ttl_s
        command = self._command(intent, state)
        external = ExternalModeIntent(self.identity, self._sequence, now, expires, command)
        try:
            await self.client.submit(external, circuit_breaker_active=self.circuit_breaker(),
                                     ownership_token=acquisition.token, acquisition=acquisition,
                                     before_dispatch=before_dispatch)
        except NativeBackendRefusal as refusal:
            self.last_backend_refusal = refusal
            if (refusal.operation != "intent" or refusal.code != "native_pursuit_ended"
                    or self.on_observation is None
                    or not self.client.matches_acquisition(
                        acquisition.identity, acquisition.runtime_id, acquisition.token, acquisition)):
                raise
            evidence = await self.client.observe_release_evidence(
                acquisition.identity, runtime_id=acquisition.runtime_id, ownership_token=acquisition.token,
                mode_id=acquisition.mode_id, acquisition=acquisition,
                deadline=refusal.deadline, expected_generation=refusal.generation + 1)
            observation = evidence.observation()
            payload = observation.get("aircraft_state")
            incoming = None if payload is None else AircraftState.from_payload(payload)
            if (observation.get("runtime_id") != acquisition.runtime_id or observation.get("fresh") is not True
                    or observation.get("owner_confirmed") is not False
                    or observation.get("rescue_active") is not False or observation.get("phase_status_fresh") is not True
                    or incoming is None or incoming.binding != acquisition.identity.binding
                    or not self.client.matches_acquisition(
                        acquisition.identity, acquisition.runtime_id, acquisition.token, acquisition)):
                raise refusal
            self.connection.commit_aircraft_state(incoming)
            state = self.connection.get_aircraft_state()
            if state is None or state != incoming:
                raise refusal
            # Reconciliation has finished its generation proof before the
            # existing callback may abort the original client/phase owner.
            try:
                await self.on_observation(state, observation, intent)
            except DispatchRefused as terminal:
                if terminal.kind is DispatchRefusalKind.TERMINAL:
                    raise DispatchRefused(terminal.reason_code, terminal.kind,
                                          details=refusal.admission_details()) from refusal
                raise refusal from terminal
            raise refusal
        self._sequence += 1
        self.last_published_intent = replace(intent, fields=dict(intent.fields))
        self.last_feedback = observation.get("native_guidance_feedback")
        return True
