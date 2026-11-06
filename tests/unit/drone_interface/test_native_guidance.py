import asyncio
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import time

import pytest

from classes.aircraft_state import AircraftBinding, Vector3
from classes.fixed_wing_vector_guidance import FixedWingCommand, UpperSpeedPolicy
from classes.native_guidance import (
    ExternalModeIntent, GuidanceSessionIdentity, NativeCapabilities,
    NativeGuidanceClient, NativeGuidanceError,
    NativeMulticopterCommand, NativeTransitionCommand,
)
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


CAPABILITIES = dict(runtime_id="test-adapter", px4_firmware="test-firmware",
                    external_mode_api_version=2, fixed_wing_supported=True,
                    vtol_transition_supported=True, unrestricted_speed_supported=False)


@pytest.fixture
async def native_server():
    requests = []
    behavior = {"wrong_reply_id": False, "handoff_confirmed": True, "owner_confirmed": True,
                "delay_operation": None, "delay_started": asyncio.Event(), "delay_release": asyncio.Event()}
    writers = []

    async def handle(reader, writer):
        writers.append(writer)
        try:
            while raw := await reader.readline():
                request = json.loads(raw)
                requests.append(request)
                operation, payload = request["operation"], request["payload"]
                if operation == behavior["delay_operation"]:
                    behavior["delay_started"].set()
                    await behavior["delay_release"].wait()
                if operation == "hello":
                    result = CAPABILITIES
                elif operation == "engage":
                    result = {"owner_confirmed": True}
                elif operation == "bind":
                    result = {"bound": payload["binding"]["aircraft_uid"] == "aircraft-a"}
                elif operation == "intent":
                    result = {"accepted_sequence": payload["sequence"], "owner_confirmed": behavior["owner_confirmed"]}
                elif operation == "handoff":
                    result = {"hold_observed": behavior["handoff_confirmed"]}
                elif operation == "phase":
                    result = {"accepted_generation": payload["identity"]["guidance_generation"], "owner_confirmed": True}
                else:
                    result = {"fresh": True, "owner_confirmed": behavior["owner_confirmed"],
                              "rescue_active": False, "runtime_id": "test-adapter",
                              "aircraft_state": asdict(aircraft_state(binding=identity().binding))}
                response = dict(protocol_version=1, request_id=request["request_id"],
                                generation=request["generation"], success=True, payload=result)
                if behavior["wrong_reply_id"]:
                    response["request_id"] -= 1
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    with tempfile.TemporaryDirectory(prefix="pe-native-") as directory:
        path = Path(directory) / "control.sock"
        server = await asyncio.start_unix_server(handle, str(path))
        try:
            yield path, requests, behavior
        finally:
            server.close()
            behavior["delay_release"].set()
            await server.wait_closed()
            for writer in writers:
                writer.close()
            await asyncio.gather(*(writer.wait_closed() for writer in writers), return_exceptions=True)


def identity():
    return GuidanceSessionIdentity("follow-a", AircraftBinding("aircraft-a", "1", 1), 1)


async def test_native_observation_binding_is_read_only_and_not_changeable_during_pursuit(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    try:
        await client.connect()
        await client.bind(identity().binding)
        await client.engage(identity(), circuit_breaker_active=False)
        with pytest.raises(NativeGuidanceError, match="already_owned"):
            await client.bind(identity().binding)
        assert [r["operation"] for r in requests] == ["hello", "bind", "engage"]
    finally:
        await client.close()


async def test_wrong_dds_aircraft_cannot_bind_to_mavsdk_connection(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    try:
        await client.connect()
        with pytest.raises(NativeGuidanceError, match="binding_unconfirmed"):
            await client.bind(replace(identity().binding, aircraft_uid="other-aircraft"))
        assert client.capabilities is None
        assert not any(r["operation"] == "engage" for r in requests)
    finally:
        await client.close()


async def test_stop_abort_does_not_wait_for_a_blocked_status_exchange(native_server):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    await client.connect()
    await client.engage(identity(), circuit_breaker_active=False)
    behavior["delay_operation"] = "observe"
    blocked = asyncio.create_task(client.observe())
    await behavior["delay_started"].wait()
    started = time.perf_counter()
    client.abort()
    assert time.perf_counter() - started < .1
    assert client.session_identity is None
    assert client.capabilities is None
    with pytest.raises(NativeGuidanceError):
        await blocked
    with pytest.raises(NativeGuidanceError, match="session_stale"):
        await client.submit(intent(), circuit_breaker_active=False)
    assert not any(r["operation"] == "intent" for r in requests)
    await client.close()


def intent(**changes):
    values = dict(identity=identity(), sequence=1, created_at_monotonic_s=100,
                  expires_at_monotonic_s=100.5, command=FixedWingCommand(0, 20, 0, None))
    return ExternalModeIntent(**(values | changes))


async def test_real_local_protocol_connect_and_reconnect_do_not_acquire_control(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    try:
        assert (await client.connect()).runtime_id == "test-adapter"
        await client.observe()
        await client.engage(identity(), circuit_breaker_active=False)
        await client.submit(intent(), circuit_breaker_active=False)
        await client.connect()
        await client.observe()
        with pytest.raises(NativeGuidanceError, match="session_stale"):
            await client.submit(intent(sequence=2), circuit_breaker_active=False)
        assert [r["operation"] for r in requests] == ["hello", "observe", "engage", "intent", "hello", "observe"]
    finally:
        await client.close()


async def test_circuit_breaker_blocks_engagement_and_every_publication(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    try:
        await client.connect()
        with pytest.raises(NativeGuidanceError, match="circuit_breaker"):
            await client.engage(identity(), circuit_breaker_active=True)
        await client.engage(identity(), circuit_breaker_active=False)
        with pytest.raises(NativeGuidanceError, match="circuit_breaker"):
            await client.submit(intent(), circuit_breaker_active=True)
        assert client.capabilities is None
        assert [r["operation"] for r in requests] == ["hello", "engage"]
    finally:
        await client.close()


async def test_no_obsolete_expired_wrong_phase_or_unqualified_command_is_sent(native_server):
    path, requests, _ = native_server
    clock = [100.0]
    client = NativeGuidanceClient(path, clock=lambda: clock[0])
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        await client.submit(intent(), circuit_breaker_active=False)
        for invalid, reason in [
            (intent(), "obsolete"),
            (intent(sequence=2, identity=replace(identity(), guidance_generation=2)), "session_stale"),
            (intent(sequence=2, command=FixedWingCommand(0, 40, 0, None, UpperSpeedPolicy.NO_UPPER_SPEED_BOUND)),
             "not_supported"),
        ]:
            with pytest.raises(NativeGuidanceError, match=reason):
                await client.submit(invalid, circuit_breaker_active=False)
        clock[0] = 101
        with pytest.raises(NativeGuidanceError, match="expired"):
            await client.submit(intent(sequence=2), circuit_breaker_active=False)
        assert len([r for r in requests if r["operation"] == "intent"]) == 1
    finally:
        await client.close()


async def test_obsolete_callback_disconnects_without_replaying_any_action(native_server):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        behavior["wrong_reply_id"] = True
        with pytest.raises(NativeGuidanceError, match="context_mismatch"):
            await client.submit(intent(), circuit_breaker_active=False)
        assert client.capabilities is None
        with pytest.raises(NativeGuidanceError):
            await client.submit(intent(sequence=2), circuit_breaker_active=False)
        assert len([r for r in requests if r["operation"] == "intent"]) == 1
    finally:
        await client.close()


async def test_unconfirmed_handoff_does_not_retain_pursuit_authority(native_server):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        behavior["handoff_confirmed"] = False
        assert (await client.handoff(identity(), reason="operator_stop"))["hold_observed"] is False
        with pytest.raises(NativeGuidanceError, match="session_stale"):
            await client.submit(intent(), circuit_breaker_active=False)
        assert requests[-1]["operation"] == "handoff"
    finally:
        await client.close()


async def test_phase_advance_invalidates_old_commands_without_starting_a_new_session(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        await client.submit(intent(), circuit_breaker_active=False)
        new_identity = replace(identity(), guidance_generation=3)
        await client.advance_generation(new_identity)
        with pytest.raises(NativeGuidanceError, match="session_stale"):
            await client.submit(intent(sequence=2), circuit_breaker_active=False)
        await client.submit(intent(identity=new_identity), circuit_breaker_active=False)
        assert len([r for r in requests if r["operation"] == "engage"]) == 1
    finally:
        await client.close()


async def test_observed_authority_loss_prevents_any_later_publication(native_server):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        behavior["owner_confirmed"] = False
        await client.observe()
        with pytest.raises(NativeGuidanceError, match="session_stale"):
            await client.submit(intent(), circuit_breaker_active=False)
        assert not any(r["operation"] == "intent" for r in requests)
    finally:
        await client.close()


def test_aircraft_observation_round_trip_preserves_source_timestamps_and_provenance():
    from classes.aircraft_state import AircraftState
    state = aircraft_state()
    encoded = json.loads(json.dumps(asdict(state)))
    decoded = AircraftState.from_payload(encoded)
    assert decoded == state
    assert decoded.observed_at_monotonic_s == 100.
    assert decoded.airspeed.observed_at_monotonic_s == 100.
    encoded["airspeed"]["source"] = "ground_speed_proxy"
    with pytest.raises(ValueError, match="airspeed_source"):
        AircraftState.from_payload(encoded)


async def test_wire_expiry_cannot_be_renewed_by_queue_delay(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100.2)
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        await client.submit(intent(), circuit_breaker_active=False)
        assert requests[-1]["payload"]["expires_at_monotonic_s"] == 100.5
        assert "remaining_lease_s" not in requests[-1]["payload"]
    finally:
        await client.close()


@pytest.mark.parametrize("operation", ["engage", "intent", "phase", "handoff"])
async def test_cancelled_exchange_closes_the_socket_and_revokes_control(native_server, operation):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    await client.connect()
    if operation != "engage":
        await client.engage(identity(), circuit_breaker_active=False)
    behavior["delay_operation"] = operation
    calls = {
        "engage": lambda: client.engage(identity(), circuit_breaker_active=False),
        "intent": lambda: client.submit(intent(), circuit_breaker_active=False),
        "phase": lambda: client.advance_generation(replace(identity(), guidance_generation=2)),
        "handoff": lambda: client.handoff(identity(), reason="stop"),
    }
    task = asyncio.create_task(calls[operation]())
    await asyncio.wait_for(behavior["delay_started"].wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.capabilities is None
    with pytest.raises(NativeGuidanceError):
        await client.submit(intent(sequence=2), circuit_breaker_active=False)
    behavior["delay_release"].set()
    await client.close()


@pytest.mark.parametrize("bad", [{"external_mode_api_version": 3}, {"fixed_wing_supported": "true"},
                                  {"runtime_id": ""}, {"unrestricted_speed_supported": 1}])
def test_capability_version_and_types_are_explicit(bad):
    with pytest.raises(NativeGuidanceError):
        NativeCapabilities.from_payload(CAPABILITIES | bad)


@pytest.mark.parametrize("command,phase", [
    (NativeMulticopterCommand(Vector3(1, 2, -1), .1), "multicopter"),
    (NativeTransitionCommand(.1, 18), "vtol_transition"),
])
async def test_phase_specific_native_contracts_use_one_owned_socket(native_server, command, phase):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100.)
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        await client.submit(intent(command=command), circuit_breaker_active=False)
        assert requests[-1]["payload"]["phase"] == phase
        assert requests[-1]["payload"]["command"] == command.wire_payload()
        assert "upper_speed_policy" not in requests[-1]["payload"]["command"]
    finally:
        await client.close()
