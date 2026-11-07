"""Private local protocol to the registered PX4 external-mode runtime.

Connection recovery is read-only. Acquiring control is always an explicit
flight-owner operation; neither reconnect nor status polling replays it.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
from typing import Callable

from classes.aircraft_state import AircraftBinding, AircraftState, AirframePhase, GuidanceSessionIdentity, Vector3, finite_number
from classes.fixed_wing_vector_guidance import FixedWingCommand, UpperSpeedPolicy


PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 65536
DEFAULT_SOCKET_PATH = Path("/run/pixeagle/guidance.sock")


class NativeGuidanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeCapabilities:
    runtime_id: str
    px4_firmware: str
    external_mode_api_version: int
    fixed_wing_supported: bool
    vtol_transition_supported: bool
    unrestricted_speed_supported: bool

    @classmethod
    def from_payload(cls, payload: dict) -> NativeCapabilities:
        names = set(cls.__dataclass_fields__)
        if set(payload) != names:
            raise NativeGuidanceError("native_capabilities_contract_mismatch")
        for name in ("runtime_id", "px4_firmware"):
            if not isinstance(payload[name], str) or not payload[name]:
                raise NativeGuidanceError("native_identity_missing")
        if type(payload["external_mode_api_version"]) is not int or payload["external_mode_api_version"] != 2:
            raise NativeGuidanceError("native_external_mode_api_unsupported")
        for name in ("fixed_wing_supported", "vtol_transition_supported", "unrestricted_speed_supported"):
            if type(payload[name]) is not bool:
                raise NativeGuidanceError("native_capabilities_invalid")
        return cls(**payload)


@dataclass(frozen=True)
class NativeMulticopterCommand:
    velocity_ned_m_s: Vector3
    yaw_rate_rad_s: float

    def __post_init__(self):
        if not isinstance(self.velocity_ned_m_s, Vector3):
            raise ValueError("native_velocity_invalid")
        finite_number(self.yaw_rate_rad_s, "native_yaw_rate")

    def wire_payload(self) -> dict:
        velocity = self.velocity_ned_m_s
        return dict(velocity_north_m_s=velocity.x, velocity_east_m_s=velocity.y,
                    velocity_down_m_s=velocity.z, yaw_rate_rad_s=self.yaw_rate_rad_s)


@dataclass(frozen=True)
class NativeTransitionCommand:
    course_rad: float
    equivalent_airspeed_m_s: float

    def __post_init__(self):
        finite_number(self.course_rad, "native_transition_course")
        if finite_number(self.equivalent_airspeed_m_s, "native_transition_speed") <= 0:
            raise ValueError("native_transition_speed_not_positive")

    def wire_payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExternalModeIntent:
    identity: GuidanceSessionIdentity
    sequence: int
    created_at_monotonic_s: float
    expires_at_monotonic_s: float
    command: FixedWingCommand | NativeMulticopterCommand | NativeTransitionCommand

    def __post_init__(self):
        if not isinstance(self.identity, GuidanceSessionIdentity):
            raise ValueError("intent_identity_invalid")
        if not isinstance(self.command, (FixedWingCommand, NativeMulticopterCommand, NativeTransitionCommand)):
            raise ValueError("intent_command_invalid")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("intent_sequence_invalid")
        for name in ("created_at_monotonic_s", "expires_at_monotonic_s"):
            finite_number(getattr(self, name), name)
        if self.expires_at_monotonic_s <= self.created_at_monotonic_s:
            raise ValueError("intent_expiry_invalid")

    @property
    def phase(self) -> AirframePhase:
        if isinstance(self.command, FixedWingCommand):
            return AirframePhase.FIXED_WING
        if isinstance(self.command, NativeMulticopterCommand):
            return AirframePhase.MULTICOPTER
        return AirframePhase.VTOL_TRANSITION


class NativeGuidanceClient:
    """One local socket, one in-flight exchange and one explicitly owned session."""

    def __init__(self, socket_path: Path, *, request_timeout_s: float = .5,
                 clock: Callable[[], float] = time.monotonic):
        if finite_number(request_timeout_s, "native_request_timeout") <= 0:
            raise ValueError("native_request_timeout_invalid")
        if not socket_path.is_absolute():
            raise ValueError("native_socket_path_must_be_absolute")
        self.socket_path = socket_path
        self.request_timeout_s = request_timeout_s
        self._clock = clock
        self._lock = asyncio.Lock()
        self._reader = None
        self._writer = None
        self._generation = 0
        self._request_id = 0
        self._identity: GuidanceSessionIdentity | None = None
        self._last_sequence = -1
        self.capabilities: NativeCapabilities | None = None

    @property
    def session_identity(self) -> GuidanceSessionIdentity | None:
        return self._identity

    async def connect(self) -> NativeCapabilities:
        async with self._lock:
            await self._disconnect()
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(str(self.socket_path), limit=MAX_MESSAGE_BYTES),
                    timeout=self.request_timeout_s,
                )
                payload = await self._exchange("hello", {})
                self.capabilities = NativeCapabilities.from_payload(payload)
                return self.capabilities
            except (OSError, ValueError, NativeGuidanceError, asyncio.TimeoutError) as error:
                await self._disconnect()
                raise NativeGuidanceError("native_connection_unavailable") from error

    async def close(self) -> None:
        async with self._lock:
            await self._disconnect()

    def abort(self) -> None:
        """Revoke the owned socket immediately on its event loop, without I/O waits.

        The adapter observes EOF and performs its owner-bound handoff. A later
        reconnect is read-only; it cannot restore this session's authority.
        """
        self._retire_socket()

    async def observe(self) -> dict:
        async with self._lock:
            result = await self._exchange("observe", {})
            try:
                for name in ("owner_confirmed", "fresh", "rescue_active"):
                    if type(result.get(name)) is not bool:
                        raise ValueError("native_observation_validity_invalid")
                if self.capabilities is None or result.get("runtime_id") != self.capabilities.runtime_id:
                    raise ValueError("native_observation_runtime_changed")
                state = (AircraftState.from_payload(result["aircraft_state"])
                         if result.get("aircraft_state") is not None else None)
                if result["fresh"] and state is None:
                    raise ValueError("native_observation_missing")
                if self._identity is not None and state is not None and state.binding != self._identity.binding:
                    raise ValueError("native_observation_aircraft_changed")
            except (ValueError, TypeError, KeyError) as error:
                await self._disconnect()
                raise NativeGuidanceError("native_observation_invalid") from error
            if self._identity is not None and (result.get("owner_confirmed") is not True
                    or result.get("fresh") is not True or result.get("rescue_active") is True):
                self._identity = None
            return result

    async def bind(self, binding: AircraftBinding) -> None:
        """Bind read-only DDS observations to the current verified MAVSDK UID."""
        if not isinstance(binding, AircraftBinding):
            raise ValueError("native_aircraft_binding_invalid")
        async with self._lock:
            if self._identity is not None:
                raise NativeGuidanceError("native_session_already_owned")
            result = await self._exchange("bind", {"binding": asdict(binding)})
            if result.get("bound") is not True:
                await self._disconnect()
                raise NativeGuidanceError("native_aircraft_binding_unconfirmed")

    async def engage(self, identity: GuidanceSessionIdentity, *, circuit_breaker_active: bool) -> dict:
        async with self._lock:
            if circuit_breaker_active is not False:
                if self._identity is not None:
                    await self._disconnect()
                raise NativeGuidanceError("circuit_breaker_active")
            if self.capabilities is None or not self.capabilities.fixed_wing_supported:
                raise NativeGuidanceError("native_fixed_wing_unavailable")
            if self._identity is not None:
                raise NativeGuidanceError("native_session_already_owned")
            now = self._clock()
            result = await self._exchange("engage", {"identity": asdict(identity),
                                                     "expires_at_monotonic_s": now + self.request_timeout_s})
            if result.get("owner_confirmed") is not True:
                await self._disconnect()
                raise NativeGuidanceError("native_ownership_not_confirmed")
            self._identity = identity
            self._last_sequence = -1
            return result

    async def submit(self, intent: ExternalModeIntent, *, circuit_breaker_active: bool) -> dict:
        async with self._lock:
            if circuit_breaker_active is not False:
                if self._identity is not None:
                    await self._disconnect()
                raise NativeGuidanceError("circuit_breaker_active")
            if self._identity is None or intent.identity != self._identity:
                raise NativeGuidanceError("native_session_stale")
            now = self._clock()
            if not intent.created_at_monotonic_s <= now < intent.expires_at_monotonic_s:
                raise NativeGuidanceError("native_intent_expired")
            if intent.sequence <= self._last_sequence:
                raise NativeGuidanceError("native_intent_obsolete")
            if (isinstance(intent.command, FixedWingCommand)
                    and intent.command.upper_speed_policy is UpperSpeedPolicy.NO_UPPER_SPEED_BOUND
                    and not self.capabilities.unrestricted_speed_supported):
                raise NativeGuidanceError("unrestricted_speed_not_supported")
            if intent.phase is not AirframePhase.FIXED_WING and not self.capabilities.vtol_transition_supported:
                raise NativeGuidanceError("native_vtol_contract_unavailable")
            result = await self._exchange("intent", {
                "identity": asdict(intent.identity), "sequence": intent.sequence,
                "created_at_monotonic_s": intent.created_at_monotonic_s,
                "expires_at_monotonic_s": intent.expires_at_monotonic_s,
                "phase": intent.phase.value,
                "command": intent.command.wire_payload(),
            })
            if (type(result.get("accepted_sequence")) is not int
                    or result["accepted_sequence"] != intent.sequence or result.get("owner_confirmed") is not True):
                await self._disconnect()
                raise NativeGuidanceError("native_publication_unconfirmed")
            self._last_sequence = intent.sequence
            return result

    async def advance_generation(self, identity: GuidanceSessionIdentity) -> dict:
        """Invalidate the old contract atomically without re-acquiring aircraft control."""
        async with self._lock:
            previous = self._identity
            if (previous is None or identity.follow_session_id != previous.follow_session_id
                    or identity.binding != previous.binding
                    or identity.guidance_generation <= previous.guidance_generation):
                raise NativeGuidanceError("native_phase_context_invalid")
            result = await self._exchange("phase", {"previous_identity": asdict(previous),
                                                     "identity": asdict(identity)})
            if (type(result.get("accepted_generation")) is not int
                    or result["accepted_generation"] != identity.guidance_generation
                    or result.get("owner_confirmed") is not True):
                await self._disconnect()
                raise NativeGuidanceError("native_phase_unconfirmed")
            self._identity = identity
            self._last_sequence = -1
            return result

    async def handoff(self, identity: GuidanceSessionIdentity, *, reason: str) -> dict:
        async with self._lock:
            if identity != self._identity or self._identity is None:
                raise NativeGuidanceError("native_session_stale")
            try:
                return await self._exchange("handoff", {"identity": asdict(identity), "reason": str(reason)})
            finally:
                # A rejected or timed-out handoff must not permit old pursuit.
                self._identity = None

    def _retire_socket(self):
        self._generation += 1
        self._identity = None
        self._last_sequence = -1
        self.capabilities = None
        self._reader = None
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()
        return writer

    async def _disconnect(self) -> None:
        writer = self._retire_socket()
        if writer is not None:
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=self.request_timeout_s)
            except (OSError, asyncio.TimeoutError):
                pass

    async def _exchange(self, operation: str, payload: dict) -> dict:
        if self._reader is None or self._writer is None:
            raise NativeGuidanceError("native_disconnected")
        reader, writer = self._reader, self._writer
        self._request_id += 1
        generation, request_id = self._generation, self._request_id
        request = dict(protocol_version=PROTOCOL_VERSION, request_id=request_id,
                       generation=generation, operation=operation, payload=payload)
        encoded = json.dumps(request, allow_nan=False, separators=(",", ":")).encode() + b"\n"
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise NativeGuidanceError("native_message_too_large")
        try:
            writer.write(encoded)
            await asyncio.wait_for(writer.drain(), timeout=self.request_timeout_s)
            raw = await asyncio.wait_for(reader.readline(), timeout=self.request_timeout_s)
            if generation != self._generation:
                raise NativeGuidanceError("native_reply_context_mismatch")
            if not raw or len(raw) > MAX_MESSAGE_BYTES:
                raise NativeGuidanceError("native_reply_missing_or_oversized")
            def reject_constant(value):
                raise ValueError(f"Non-finite JSON constant: {value}")
            reply = json.loads(raw, parse_constant=reject_constant)
            if (not isinstance(reply, dict) or type(reply.get("protocol_version")) is not int
                    or reply["protocol_version"] != PROTOCOL_VERSION
                    or type(reply.get("request_id")) is not int or reply["request_id"] != request_id
                    or type(reply.get("generation")) is not int or reply["generation"] != generation):
                raise NativeGuidanceError("native_reply_context_mismatch")
            if reply.get("success") is not True:
                raise NativeGuidanceError(str(reply.get("error_code", "native_request_refused")))
            if not isinstance(reply.get("payload"), dict):
                raise NativeGuidanceError("native_reply_payload_invalid")
            return reply["payload"]
        except asyncio.CancelledError:
            await self._disconnect()
            raise
        except (OSError, ValueError, NativeGuidanceError, asyncio.TimeoutError) as error:
            await self._disconnect()
            if isinstance(error, NativeGuidanceError):
                raise
            raise NativeGuidanceError("native_transport_failed") from error
