"""One-shot stock MAVLink ownership under the existing command scheduler.

There is no background resend loop. RPC success means submitted, not flown.
Standard MAVLink cannot atomically compare ownership on the aircraft; the last
application-owned boundary checks the original session and observed mode.
"""

import asyncio
from dataclasses import replace
import math
import time

from classes.aircraft_state import AirframePhase, finite_number
from classes.command_dispatch_guard import DispatchRefused, DispatchRefusalKind, validate_before_dispatch
from classes.command_intent import CommandIntent
from classes.guidance_phase_session import PhaseSessionState
from classes.mavlink_aircraft_state import MavlinkGuidanceObservation
from classes.stock_mavlink_setpoints import (
    PX4_HOLD_MODE, PX4_OFFBOARD_MODE, hold_mode_packet, offboard_mode_packet,
)


class MavlinkCommandTransport:
    publication_source = "mavlink_direct_one_shot"
    observed_publications = None  # No native controller publication receipt exists.

    def __init__(self, guidance, *, observe, send, owns_session, target_confirmed,
                 circuit_breaker, command_period_s, prime_duration_s, command_timeout_s,
                 on_observation=None, clock=time.monotonic, sleep=asyncio.sleep):
        if any(not callable(item) for item in (observe, send, owns_session, target_confirmed, circuit_breaker)):
            raise ValueError("mavlink_transport_dependencies_invalid")
        for name, value in (("command_period", command_period_s), ("prime_duration", prime_duration_s),
                            ("command_timeout", command_timeout_s)):
            if finite_number(value, name) <= 0:
                raise ValueError("mavlink_transport_timing_invalid")
        self.guidance, self.identity = guidance, guidance.identity
        self.observe, self.send = observe, send
        self.owns_session, self.target_confirmed, self.circuit_breaker = owns_session, target_confirmed, circuit_breaker
        self.command_period_s, self.prime_duration_s, self.command_timeout_s = command_period_s, prime_duration_s, command_timeout_s
        self.clock, self.sleep = clock, sleep
        self.on_observation = on_observation
        self._epoch = self._route = self._phase = None
        self._engage_attempted = self._acquire_dispatched = self._active = self._closed = False
        self._stop_attempted = False
        self._last_created = None
        self._lock = asyncio.Lock()
        self.last_published_intent = self.last_feedback = self.last_handoff = None

    def _refuse(self, reason):
        self.abort(reason)
        raise DispatchRefused(reason, DispatchRefusalKind.TERMINAL)

    def _observation(self, *, for_stop=False):
        if (self.owns_session() is not True
                or not for_stop and (self._closed or self.circuit_breaker() is not False)):
            self._refuse("mavlink_command_owner_revoked")
        observation = self.observe()
        if (not isinstance(observation, MavlinkGuidanceObservation)
                or observation.state.binding != self.identity.binding
                or observation.state.rescue_active
                or not observation.state.fresh(self.clock(), self.guidance.phase_owner.observation_timeout_s)
                or type(observation.flight_mode) is not int):
            self._refuse("mavlink_aircraft_state_unavailable")
        observed_at = observation.mode_observed_at_monotonic_s
        if (type(observed_at) not in (int, float) or not math.isfinite(observed_at)
                or not 0 <= self.clock() - observed_at <= self.guidance.phase_owner.observation_timeout_s):
            self._refuse("mavlink_flight_mode_stale")
        route = observation.system_id, observation.component_id
        if (any(type(value) is not int or not 1 <= value <= 255 for value in route)
                or not isinstance(observation.source_epoch, tuple) or len(observation.source_epoch) != 2
                or any(not isinstance(value, str) or not value for value in observation.source_epoch)
                or observation.source_epoch[0] != self.identity.binding.aircraft_uid
                or self._epoch is not None and (observation.source_epoch != self._epoch or route != self._route)):
            self._refuse("mavlink_aircraft_connection_changed")
        if not for_stop and (observation.armed is not True or self._phase is not None and observation.state.phase is not self._phase):
            self._refuse("mavlink_aircraft_phase_or_authority_changed")
        return observation

    async def _send(self, packet):
        await asyncio.wait_for(self.send(packet), timeout=self.command_timeout_s)

    def _current(self):
        if not self._active or self._closed:
            self._refuse("mavlink_command_owner_unavailable")
        observation = self._observation()
        decision = self.guidance.observe(observation.state,
            owner_confirmed=observation.flight_mode == PX4_OFFBOARD_MODE,
            target_confirmed=self.target_confirmed() is True)
        if decision.state is PhaseSessionState.ENDED:
            self._refuse(decision.reason)
        if self.on_observation is not None:
            validate_before_dispatch(lambda: self.on_observation(observation))
        return observation

    @property
    def owner_confirmed(self):
        if not self._active or self._closed:
            return False
        try:
            return self._observation().flight_mode == PX4_OFFBOARD_MODE
        except (DispatchRefused, ValueError):
            return False

    def ready(self):
        try:
            self._current()
            return True
        except (DispatchRefused, ValueError):
            return False

    def abort(self, reason="mavlink_command_owner_revoked"):
        self._closed, self._active = True, False
        self.last_published_intent = None
        self.guidance.end(reason)

    async def engage(self, *, before_dispatch, on_mode_dispatch=None):
        async with self._lock:
            if self._engage_attempted or self._closed:
                self._refuse("mavlink_command_owner_already_started")
            self._engage_attempted = True
            try:
                first = self._observation()
                if first.flight_mode == PX4_OFFBOARD_MODE:
                    self._refuse("mavlink_offboard_already_owned")
                self._epoch, self._route, self._phase = first.source_epoch, (first.system_id, first.component_id), first.state.phase
                prime_until = self.clock() + self.prime_duration_s
                requested_at = None
                while True:
                    observation = self._observation()
                    if requested_at is not None and observation.flight_mode == PX4_OFFBOARD_MODE:
                        if observation.mode_observed_at_monotonic_s >= requested_at:
                            self._active = True
                            self._current()
                            return self.guidance.baseline()
                    elif observation.flight_mode != first.flight_mode:
                        self._refuse("mavlink_mode_changed_during_acquisition")
                    if requested_at is not None and self.clock() - requested_at >= self.command_timeout_s:
                        self._refuse("mavlink_offboard_confirmation_timeout")
                    packet = self.guidance.priming_packet(observation)
                    validate_before_dispatch(before_dispatch)
                    await self._send(packet)
                    if requested_at is None and self.clock() >= prime_until:
                        # A mode or session change during the awaited RPC cannot
                        # authorize the subsequent mode request.
                        latest = self._observation()
                        if latest.flight_mode != first.flight_mode:
                            self._refuse("mavlink_mode_changed_during_acquisition")
                        packet = offboard_mode_packet(system_id=latest.system_id, component_id=latest.component_id)
                        validate_before_dispatch(before_dispatch)
                        validate_before_dispatch(on_mode_dispatch)
                        self._acquire_dispatched = True
                        requested_at = self.clock()
                        await self._send(packet)
                    await self.sleep(self.command_period_s)
            except BaseException:
                self.abort("mavlink_acquisition_failed")
                raise

    def accept_intent(self, intent):
        try:
            self._current()
        except DispatchRefused as error:
            raise ValueError(error.reason_code) from error
        if not isinstance(intent, CommandIntent):
            raise ValueError("mavlink_command_contract_invalid")
        created = intent.created_at_monotonic_s
        if (type(created) not in (int, float) or not math.isfinite(created)
                or created > self.clock() or self._last_created is not None and created < self._last_created
                or intent.guidance_identity != self.identity):
            raise ValueError("mavlink_command_obsolete")
        self._last_created = created
        return replace(intent, fields=dict(intent.fields))

    async def publish(self, intent, *, reason, ttl_s, before_dispatch=None):
        async with self._lock:
            self.last_published_intent = None
            observation = self._current()
            if (not isinstance(intent, CommandIntent) or intent.guidance_identity != self.identity
                    or not 0 <= self.clock() - intent.created_at_monotonic_s <= finite_number(ttl_s, "intent_ttl")):
                self._refuse("mavlink_command_expired")
            if self.guidance.phase_owner.state is not PhaseSessionState.PURSUIT:
                intent = self.guidance.baseline()
            if self._phase is AirframePhase.FIXED_WING:
                intent = replace(intent, fields=self.guidance.guard_native_fields(intent.fields))
            packet = self.guidance.packet(intent, observation.state, system_id=observation.system_id,
                component_id=observation.component_id, local_position_ned=observation.local_position_ned)
            validate_before_dispatch(before_dispatch)
            await self._send(packet)
            self._current()  # A completed RPC does not renew a revoked session.
            self.last_published_intent = replace(intent, fields=dict(intent.fields))
            return True

    def published_intent(self, *, ttl_s):
        intent = self.last_published_intent
        if not self.ready() or intent is None or not 0 <= self.clock() - intent.created_at_monotonic_s <= ttl_s:
            return None
        return replace(intent, fields=dict(intent.fields))

    async def stop(self, reason):
        # Revoke before waiting for a queued publication to finish. Joining the
        # same lock serializes the sole Hold against the final submitted packet.
        self.abort(reason)
        async with self._lock:
            if self.last_handoff is not None:
                return dict(self.last_handoff)
            if self._stop_attempted:
                raise ValueError("mavlink_handoff_already_attempted")
            self._stop_attempted = True
            outcome = dict(executed=False, local_sender_quiesced=True, errors=[], reason=reason,
                           authority_released=False, handoff_contract="observed_mavlink_mode")
            if not self._acquire_dispatched:
                self.last_handoff = outcome | {"reason": "mavlink_acquire_not_dispatched", "authority_released": True}
                return dict(self.last_handoff)
            observation = self._observation(for_stop=True)
            if observation.flight_mode != PX4_OFFBOARD_MODE or observation.armed is False:
                self.last_handoff = outcome | {"reason": "observed_authority_already_released", "authority_released": True}
                return dict(self.last_handoff)
            if (observation.state.phase in {AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING, AirframePhase.VTOL_TRANSITION}
                    and observation.state.phase is not self._phase):
                self.last_handoff = outcome | {"reason": "phase_changed_sender_quiesced"}
                return dict(self.last_handoff)
            if observation.armed is not True or observation.state.phase is AirframePhase.UNKNOWN:
                raise ValueError("mavlink_handoff_authority_unavailable")
            requested_at = self.clock()
            await self._send(hold_mode_packet(system_id=observation.system_id, component_id=observation.component_id))
            while True:
                observation = self._observation(for_stop=True)
                if observation.mode_observed_at_monotonic_s >= requested_at:
                    if observation.flight_mode == PX4_HOLD_MODE:
                        self.last_handoff = outcome | {"executed": True, "reason": "hold_confirmed", "authority_released": True}
                        return dict(self.last_handoff)
                    if observation.flight_mode != PX4_OFFBOARD_MODE or observation.armed is False:
                        self.last_handoff = outcome | {"reason": "observed_authority_already_released", "authority_released": True}
                        return dict(self.last_handoff)
                if self.clock() - requested_at >= self.command_timeout_s:
                    raise ValueError("mavlink_hold_confirmation_timeout")
                await self.sleep(self.command_period_s)
