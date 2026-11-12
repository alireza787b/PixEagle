"""Private local protocol to the registered PX4 external-mode runtime.

Connection recovery is read-only. Acquiring control is always an explicit
flight-owner operation; neither reconnect nor status polling replays it.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import secrets
import time
from typing import Callable

from classes.aircraft_state import AircraftBinding, AircraftState, AirframePhase, GuidanceSessionIdentity, Vector3, finite_number
from classes.fixed_wing_vector_guidance import FixedWingCommand, UpperSpeedPolicy
from classes.command_dispatch_guard import validate_before_dispatch


PROTOCOL_VERSION = 2
MAX_MESSAGE_BYTES = 65536
DEFAULT_SOCKET_PATH = Path("/run/pixeagle/guidance.sock")


class NativeGuidanceError(RuntimeError):
    pass


def validate_ownership_token(value: str) -> str:
    """The token is an acquisition identity, never a socket or mode identity."""
    if (not isinstance(value, str) or len(value) != 32 or set(value) - set("0123456789abcdef")
            or value == "0" * 32):
        raise NativeGuidanceError("native_ownership_token_invalid")
    return value


def make_ownership_token() -> str:
    return validate_ownership_token(secrets.token_hex(16))


def _unsigned(value, bits: int) -> bool:
    return type(value) is int and 0 <= value < 2 ** bits


@dataclass(frozen=True)
class NativeAcquisitionContext:
    runtime_id: str
    identity: GuidanceSessionIdentity
    token: str
    firmware_incarnation: str
    source_revision: int
    source_nav_state: int
    source_nav_state_timestamp: int
    mode_id: int
    activation_timestamp: int

    def __post_init__(self):
        if not isinstance(self.runtime_id, str) or not self.runtime_id or not isinstance(self.identity, GuidanceSessionIdentity):
            raise NativeGuidanceError("native_acquisition_identity_invalid")
        validate_ownership_token(self.token)
        validate_ownership_token(self.firmware_incarnation)
        if (not _unsigned(self.identity.guidance_generation, 64)
                or not _unsigned(self.identity.binding.telemetry_generation, 64)):
            raise NativeGuidanceError("native_acquisition_identity_invalid")
        for name in ("source_revision", "source_nav_state_timestamp", "activation_timestamp"):
            if not _unsigned(getattr(self, name), 64):
                raise NativeGuidanceError("native_acquisition_context_invalid")
        for name in ("source_nav_state", "mode_id"):
            if not _unsigned(getattr(self, name), 8):
                raise NativeGuidanceError("native_acquisition_context_invalid")
        if (self.source_nav_state_timestamp == 0 or self.source_nav_state == self.mode_id
                or self.activation_timestamp != 0 and self.activation_timestamp <= self.source_nav_state_timestamp):
            raise NativeGuidanceError("native_acquisition_context_invalid")

    @classmethod
    def from_payload(cls, payload: dict) -> NativeAcquisitionContext:
        try:
            if not isinstance(payload, dict) or set(payload) != set(cls.__dataclass_fields__):
                raise ValueError("native_acquisition_fields_invalid")
            value = dict(payload)
            identity = value["identity"]
            if (not isinstance(identity, dict) or set(identity) != set(GuidanceSessionIdentity.__dataclass_fields__)
                    or not isinstance(identity.get("binding"), dict)
                    or set(identity["binding"]) != set(AircraftBinding.__dataclass_fields__)
                    or not _unsigned(identity.get("guidance_generation"), 64)
                    or not _unsigned(identity["binding"].get("telemetry_generation"), 64)):
                raise ValueError("native_acquisition_identity_invalid")
            value["identity"] = GuidanceSessionIdentity(**(identity | {"binding": AircraftBinding(**identity["binding"])}))
            return cls(**value)
        except (ValueError, TypeError, KeyError) as error:
            raise NativeGuidanceError("native_acquisition_context_invalid") from error

    def wire_payload(self) -> dict:
        return asdict(self)

    def require_match(self, identity: GuidanceSessionIdentity, runtime_id: str, token: str,
                      known: NativeAcquisitionContext | None = None, *, mode_id: int | None = None) -> None:
        if (self.identity != identity or self.runtime_id != runtime_id or self.token != validate_ownership_token(token)
                or known is not None and self != known or mode_id is not None and self.mode_id != mode_id):
            raise NativeGuidanceError("native_acquisition_context_changed")


@dataclass(frozen=True)
class NativeReleaseReceipt:
    acquisition: NativeAcquisitionContext
    outcome: str
    observed_nav_state: int
    observed_nav_state_timestamp: int

    def __post_init__(self):
        if (not isinstance(self.acquisition, NativeAcquisitionContext)
                or not isinstance(self.outcome, str) or self.outcome not in {"hold_confirmed", "owner_already_released", "unconfirmed"}
                or not _unsigned(self.observed_nav_state, 8)
                or not _unsigned(self.observed_nav_state_timestamp, 64)):
            raise NativeGuidanceError("native_release_receipt_invalid")
        if self.outcome == "hold_confirmed" and (
                self.acquisition.activation_timestamp == 0 or self.observed_nav_state != 4
                or self.observed_nav_state_timestamp <= self.acquisition.activation_timestamp):
            raise NativeGuidanceError("native_release_receipt_invalid")

    @classmethod
    def from_payload(cls, payload: dict) -> NativeReleaseReceipt:
        if not isinstance(payload, dict) or set(payload) != set(cls.__dataclass_fields__):
            raise NativeGuidanceError("native_release_receipt_invalid")
        return cls(**(payload | {"acquisition": NativeAcquisitionContext.from_payload(payload["acquisition"])}))

    def require_match(self, identity: GuidanceSessionIdentity, runtime_id: str, token: str,
                      known: NativeAcquisitionContext | None = None, *, mode_id: int | None = None) -> NativeReleaseReceipt:
        self.acquisition.require_match(identity, runtime_id, token, known, mode_id=mode_id)
        return self

    @property
    def released(self) -> bool:
        return self.outcome != "unconfirmed"

    def wire_payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class NativeCapabilities:
    runtime_id: str
    px4_firmware: str
    external_mode_api_version: int
    fixed_wing_supported: bool
    vtol_transition_supported: bool
    unrestricted_speed_supported: bool
    owned_mode_supported: bool = False
    owned_mode_id: int | None = None

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
        for name in ("fixed_wing_supported", "vtol_transition_supported", "unrestricted_speed_supported", "owned_mode_supported"):
            if type(payload[name]) is not bool:
                raise NativeGuidanceError("native_capabilities_invalid")
        if not _unsigned(payload["owned_mode_id"], 8):
            raise NativeGuidanceError("native_owned_mode_invalid")
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
        self._acquisition: NativeAcquisitionContext | None = None
        self._acquisition_identity: GuidanceSessionIdentity | None = None
        self._ownership_token: str | None = None
        self._acquisition_runtime_id: str | None = None
        self._acquisition_mode_id: int | None = None
        self._acquisition_pending = False
        self._last_sequence = -1
        self.capabilities: NativeCapabilities | None = None

    @property
    def session_identity(self) -> GuidanceSessionIdentity | None:
        return self._identity

    @property
    def acquisition_context(self) -> NativeAcquisitionContext | None:
        return self._acquisition

    @property
    def acquisition_token(self) -> str | None:
        return self._ownership_token

    def matches_acquisition(self, identity: GuidanceSessionIdentity, runtime_id: str, token: str,
                            known: NativeAcquisitionContext | None = None) -> bool:
        return (self._acquisition_identity == identity and self._acquisition_runtime_id == runtime_id
                and self._ownership_token == token and (known is None or self._acquisition == known))

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

    async def observe_after_release(self, identity: GuidanceSessionIdentity, *, runtime_id: str,
                                    ownership_token: str, mode_id: int, acquisition: NativeAcquisitionContext | None = None
                                    ) -> NativeReleaseReceipt:
        """Reconcile only the original acquisition, using a separate read-only socket."""
        if self.session_identity is not None:
            raise NativeGuidanceError("native_session_already_owned")
        token = validate_ownership_token(ownership_token)
        if not isinstance(identity, GuidanceSessionIdentity) or not isinstance(runtime_id, str) or not runtime_id:
            raise NativeGuidanceError("native_acquisition_identity_invalid")
        if not _unsigned(mode_id, 8):
            raise NativeGuidanceError("native_owned_mode_invalid")
        if acquisition is not None:
            acquisition.require_match(identity, runtime_id, token, mode_id=mode_id)
        generation = self._generation
        original = (self._acquisition_identity, self._acquisition_runtime_id, self._ownership_token,
                    self._acquisition_mode_id, self._acquisition)

        def unchanged():
            current = (self._acquisition_identity, self._acquisition_runtime_id, self._ownership_token,
                       self._acquisition_mode_id, self._acquisition)
            if self._generation != generation or self.session_identity is not None or current != original:
                raise NativeGuidanceError("native_release_context_replaced")

        observer = NativeGuidanceClient(self.socket_path, request_timeout_s=self.request_timeout_s, clock=self._clock)

        async def reconcile():
            capabilities = await observer.connect()
            unchanged()
            if capabilities.runtime_id != runtime_id or capabilities.owned_mode_id != mode_id:
                raise NativeGuidanceError("native_release_runtime_changed")
            if not capabilities.owned_mode_supported:
                raise NativeGuidanceError("native_ownership_contract_unavailable")
            await observer.bind(identity.binding)
            while True:
                result = await observer.observe()
                unchanged()
                payload = result["release_receipt"]
                if payload is not None:
                    receipt = NativeReleaseReceipt.from_payload(payload).require_match(
                        identity, runtime_id, token, acquisition, mode_id=mode_id)
                    if receipt.released:
                        if self._ownership_token == token and self._acquisition_identity == identity:
                            self._acquisition_pending = False
                        return receipt
                await asyncio.sleep(.01)

        try:
            return await asyncio.wait_for(reconcile(), timeout=self.request_timeout_s)
        except asyncio.TimeoutError as error:
            raise NativeGuidanceError("native_release_unconfirmed") from error
        finally:
            observer.abort()

    async def observe(self) -> dict:
        async with self._lock:
            result = await self._exchange("observe", {})
            try:
                for name in ("owner_confirmed", "fresh", "rescue_active"):
                    if type(result.get(name)) is not bool:
                        raise ValueError("native_observation_validity_invalid")
                if self.capabilities is None or result.get("runtime_id") != self.capabilities.runtime_id:
                    raise ValueError("native_observation_runtime_changed")
                if "release_receipt" not in result:
                    raise ValueError("native_release_receipt_missing")
                if result["release_receipt"] is not None:
                    receipt = NativeReleaseReceipt.from_payload(result["release_receipt"])
                    if self._acquisition_pending:
                        receipt.require_match(self._acquisition_identity, self._acquisition_runtime_id,
                                              self._ownership_token, self._acquisition, mode_id=self._acquisition_mode_id)
                state = None
                timing = result.get("attitude_timing")
                if result.get("aircraft_state") is not None:
                    if not isinstance(result["aircraft_state"], dict):
                        raise ValueError("native_aircraft_state_invalid")
                    payload = dict(result["aircraft_state"])
                    if payload.get("attitude_timing") is not None:
                        raise ValueError("native_attitude_timing_must_be_top_level")
                    payload["attitude_timing"] = timing
                    state = AircraftState.from_payload(payload)
                    if (state.attitude_timing is not None
                            and state.attitude_timing.publication_received_at_monotonic_s > self._clock()):
                        raise ValueError("native_attitude_receipt_in_future")
                    result["aircraft_state"] = payload
                elif timing is not None:
                    raise ValueError("native_attitude_without_aircraft_state")
                if result["fresh"] and state is None:
                    raise ValueError("native_observation_missing")
                if self._identity is not None and state is not None and state.binding != self._identity.binding:
                    raise ValueError("native_observation_aircraft_changed")
            except (ValueError, TypeError, KeyError, NativeGuidanceError) as error:
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

    async def engage(self, identity: GuidanceSessionIdentity, *, circuit_breaker_active: bool,
                     ownership_token: str | None = None,
                     before_dispatch: Callable[[], None] | None = None,
                     on_mode_dispatch: Callable[[], None] | None = None) -> dict:
        async with self._lock:
            if not isinstance(identity, GuidanceSessionIdentity):
                raise NativeGuidanceError("native_acquisition_identity_invalid")
            if self._identity is not None or self._acquisition_pending:
                raise NativeGuidanceError("native_session_already_owned")
            if circuit_breaker_active is not False:
                raise NativeGuidanceError("circuit_breaker_active")
            if self.capabilities is None or not self.capabilities.fixed_wing_supported:
                raise NativeGuidanceError("native_fixed_wing_unavailable")
            if not self.capabilities.owned_mode_supported:
                raise NativeGuidanceError("native_ownership_contract_unavailable")
            token = make_ownership_token() if ownership_token is None else validate_ownership_token(ownership_token)
            runtime_id = self.capabilities.runtime_id
            mode_id = self.capabilities.owned_mode_id
            if not _unsigned(mode_id, 8):
                raise NativeGuidanceError("native_owned_mode_invalid")

            def dispatched():
                validate_before_dispatch(on_mode_dispatch)
                self._acquisition_identity = identity
                self._acquisition_runtime_id = runtime_id
                self._ownership_token = token
                self._acquisition_mode_id = mode_id
                self._acquisition = None
                self._acquisition_pending = True

            now = self._clock()
            result = await self._exchange("engage", {"identity": asdict(identity),
                                                     "token": token, "runtime_id": runtime_id,
                                                     "expires_at_monotonic_s": now + self.request_timeout_s},
                                          before_dispatch=before_dispatch, on_dispatch=dispatched)
            try:
                context = NativeAcquisitionContext.from_payload(result.get("acquisition"))
                context.require_match(identity, runtime_id, token, mode_id=mode_id)
                if (result.get("owner_confirmed") is not True or result.get("runtime_id") != runtime_id
                        or context.activation_timestamp == 0):
                    raise NativeGuidanceError("native_ownership_not_confirmed")
            except NativeGuidanceError:
                await self._disconnect()
                raise
            self._acquisition = context
            self._identity = identity
            self._last_sequence = -1
            return result

    async def submit(self, intent: ExternalModeIntent, *, circuit_breaker_active: bool, ownership_token: str,
                     acquisition: NativeAcquisitionContext,
                     before_dispatch: Callable[[], None] | None = None) -> dict:
        async with self._lock:
            if self._identity is None or intent.identity != self._identity:
                raise NativeGuidanceError("native_session_stale")
            token = validate_ownership_token(ownership_token)
            if (not isinstance(acquisition, NativeAcquisitionContext) or token != self._ownership_token
                    or self._acquisition != acquisition):
                raise NativeGuidanceError("native_acquisition_context_changed")
            if circuit_breaker_active is not False:
                await self._disconnect()
                raise NativeGuidanceError("circuit_breaker_active")
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
                "identity": asdict(intent.identity), "token": token, "sequence": intent.sequence,
                "created_at_monotonic_s": intent.created_at_monotonic_s,
                "expires_at_monotonic_s": intent.expires_at_monotonic_s,
                "phase": intent.phase.value,
                "command": intent.command.wire_payload(),
            }, before_dispatch=before_dispatch)
            if (type(result.get("accepted_sequence")) is not int
                    or result["accepted_sequence"] != intent.sequence or result.get("owner_confirmed") is not True):
                await self._disconnect()
                raise NativeGuidanceError("native_publication_unconfirmed")
            self._last_sequence = intent.sequence
            return result

    async def advance_generation(self, identity: GuidanceSessionIdentity, *, ownership_token: str,
                                 acquisition: NativeAcquisitionContext) -> dict:
        """Invalidate the old contract atomically without re-acquiring aircraft control."""
        async with self._lock:
            token = validate_ownership_token(ownership_token)
            if (not isinstance(acquisition, NativeAcquisitionContext) or token != self._ownership_token
                    or self._acquisition != acquisition):
                raise NativeGuidanceError("native_acquisition_context_changed")
            previous = self._identity
            if (previous is None or identity.follow_session_id != previous.follow_session_id
                    or identity.binding != previous.binding
                    or identity.guidance_generation <= previous.guidance_generation):
                raise NativeGuidanceError("native_phase_context_invalid")
            result = await self._exchange("phase", {"previous_identity": asdict(previous), "token": token,
                                                     "identity": asdict(identity)})
            if (type(result.get("accepted_generation")) is not int
                    or result["accepted_generation"] != identity.guidance_generation
                    or result.get("owner_confirmed") is not True):
                await self._disconnect()
                raise NativeGuidanceError("native_phase_unconfirmed")
            self._identity = identity
            self._last_sequence = -1
            return result

    async def handoff(self, identity: GuidanceSessionIdentity, *, reason: str, ownership_token: str,
                      acquisition: NativeAcquisitionContext,
                      before_dispatch: Callable[[], None] | None = None) -> NativeReleaseReceipt:
        async with self._lock:
            if identity != self._identity or self._identity is None:
                raise NativeGuidanceError("native_session_stale")
            dispatched = False
            token, generation = validate_ownership_token(ownership_token), self._generation
            if (not isinstance(acquisition, NativeAcquisitionContext) or token != self._ownership_token
                    or self._acquisition != acquisition):
                raise NativeGuidanceError("native_acquisition_context_changed")
            original = self._acquisition
            original_identity, runtime_id = self._acquisition_identity, self._acquisition_runtime_id

            def mark_dispatched():
                nonlocal dispatched
                dispatched = True

            try:
                payload = await self._exchange("handoff", {"identity": asdict(identity), "token": token, "reason": str(reason)},
                                               before_dispatch=before_dispatch, on_dispatch=mark_dispatched)
                receipt = NativeReleaseReceipt.from_payload(payload).require_match(
                    original_identity, runtime_id, token, original)
                if receipt.released:
                    self._acquisition_pending = False
                return receipt
            finally:
                # After dispatch, refusal or timeout must not permit old pursuit.
                if dispatched and self._generation == generation and self._ownership_token == token:
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

    async def _exchange(self, operation: str, payload: dict, *,
                        before_dispatch: Callable[[], None] | None = None,
                        on_dispatch: Callable[[], None] | None = None) -> dict:
        if self._reader is None or self._writer is None:
            raise NativeGuidanceError("native_disconnected")
        reader, writer = self._reader, self._writer
        generation, request_id = self._generation, self._request_id + 1
        request = dict(protocol_version=PROTOCOL_VERSION, request_id=request_id,
                       generation=generation, operation=operation, payload=payload)
        encoded = json.dumps(request, allow_nan=False, separators=(",", ":")).encode() + b"\n"
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise NativeGuidanceError("native_message_too_large")
        validate_before_dispatch(before_dispatch)
        validate_before_dispatch(on_dispatch)
        self._request_id = request_id
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.request_timeout_s
        try:
            writer.write(encoded)
            await asyncio.wait_for(writer.drain(), timeout=max(0., deadline - loop.time()))
            raw = await asyncio.wait_for(reader.readline(), timeout=max(0., deadline - loop.time()))
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
            if generation == self._generation and writer is self._writer:
                self._retire_socket()
            raise
        except asyncio.TimeoutError as error:
            if generation == self._generation and writer is self._writer:
                self._retire_socket()
            raise NativeGuidanceError("native_transport_failed") from error
        except (OSError, ValueError, NativeGuidanceError) as error:
            if generation == self._generation and writer is self._writer:
                self._retire_socket()
            if isinstance(error, NativeGuidanceError):
                raise
            raise NativeGuidanceError("native_transport_failed") from error
