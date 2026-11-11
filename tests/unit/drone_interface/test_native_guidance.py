import asyncio
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import time

import pytest

from classes.aircraft_state import AircraftBinding, Vector3
from classes.command_dispatch_guard import DispatchRefusalKind, DispatchRefused
from classes.fixed_wing_vector_guidance import FixedWingCommand, UpperSpeedPolicy
from classes.native_guidance import (
    ExternalModeIntent, GuidanceSessionIdentity, NativeCapabilities,
    NativeGuidanceClient, NativeGuidanceError,
    NativeMulticopterCommand, NativeTransitionCommand,
)
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing


CAPABILITIES = dict(runtime_id="test-adapter", px4_firmware="test-firmware",
                    external_mode_api_version=2, fixed_wing_supported=True,
                    vtol_transition_supported=True, unrestricted_speed_supported=False)


@pytest.fixture
async def native_server():
    requests = []
    behavior = {"wrong_reply_id": False, "handoff_confirmed": True, "owner_confirmed": True,
                "nav_state": 4, "nav_state_timestamp": 200,
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
                    state = asdict(aircraft_state(binding=identity().binding))
                    state.pop("attitude_timing")
                    result = {"fresh": True, "owner_confirmed": behavior["owner_confirmed"],
                              "nav_state": behavior["nav_state"], "nav_state_timestamp": behavior["nav_state_timestamp"],
                              "rescue_active": False, "runtime_id": "test-adapter",
                              "aircraft_state": state}
                    result.update(behavior.get("observation", {}))
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


@pytest.mark.parametrize("mode", [4, 5])
async def test_post_abort_observation_confirms_new_epoch_without_mode_commands(native_server, mode):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, request_timeout_s=.1, clock=lambda: 100.)
    await client.connect()
    await client.engage(identity(), circuit_breaker_active=False)
    client.abort()
    behavior.update(owner_confirmed=False, nav_state=mode)
    result = await client.observe_after_release(identity().binding, runtime_id="test-adapter", activation_timestamp=100)
    assert result["nav_state"] == mode
    assert client.session_identity is None
    assert [row["operation"] for row in requests] == ["hello", "engage", "hello", "bind", "observe"]


@pytest.mark.parametrize("change,reason", [
    ({"runtime_id": "restarted-adapter"}, "release_runtime_changed"),
    ({"activation_timestamp": 200}, "release_unconfirmed"),
    ({"activation_timestamp": None}, "activation_context_missing"),
])
async def test_release_observation_rejects_replaced_runtime_and_old_hold_epoch(native_server, change, reason):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, request_timeout_s=.05)
    behavior["owner_confirmed"] = False
    kwargs = dict(runtime_id="test-adapter", activation_timestamp=100) | change
    with pytest.raises(NativeGuidanceError, match=reason):
        await client.observe_after_release(identity().binding, **kwargs)
    assert not any(row["operation"] in {"engage", "intent", "phase", "handoff"} for row in requests)


async def test_release_observation_cannot_replace_an_active_session(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path)
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        count = len(requests)
        with pytest.raises(NativeGuidanceError, match="already_owned"):
            await client.observe_after_release(identity().binding, runtime_id="test-adapter", activation_timestamp=100)
        assert client.session_identity == identity()
        assert len(requests) == count
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


@pytest.mark.parametrize("metadata", [{}, {"attitude_timing": None},
                                      {"attitude_timing": asdict(attitude_timing())}])
async def test_optional_top_level_timing_attaches_locally_without_changing_legacy_wire(native_server, metadata):
    from classes.aircraft_state import AircraftState
    path, requests, behavior = native_server
    behavior["observation"] = metadata
    client = NativeGuidanceClient(path, clock=lambda: 100.)
    try:
        await client.connect()
        response = await client.observe()
        state = AircraftState.from_payload(response["aircraft_state"])
        expected = attitude_timing() if metadata.get("attitude_timing") is not None else None
        assert state.attitude_timing == expected
        assert state.observed_at_monotonic_s == 100.
        assert state.sequence == 1
        assert [request["operation"] for request in requests] == ["hello", "observe"]
    finally:
        await client.close()


@pytest.mark.parametrize("metadata", [
    [], {"sample_timestamp_us": 990_000},
    asdict(attitude_timing()) | {"sample_timestamp_us": 1_000_001},
    asdict(attitude_timing()) | {"publication_received_at_monotonic_s": 100.1},
    asdict(attitude_timing()) | {"quat_reset_counter": 256},
    asdict(attitude_timing()) | {"time_basis": "px4_boot_us"},
    asdict(attitude_timing()) | {"unexpected": 1},
])
async def test_invalid_top_level_timing_disconnects_without_authority_replay(native_server, metadata):
    path, requests, behavior = native_server
    behavior["observation"] = {"attitude_timing": metadata}
    client = NativeGuidanceClient(path, clock=lambda: 100.)
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        with pytest.raises(NativeGuidanceError, match="observation_invalid"):
            await client.observe()
        assert client.capabilities is None
        assert client.session_identity is None
        assert [request["operation"] for request in requests] == ["hello", "engage", "observe"]
    finally:
        await client.close()


@pytest.mark.parametrize("observation", [
    {"fresh": False, "aircraft_state": None, "attitude_timing": asdict(attitude_timing())},
    {"aircraft_state": asdict(aircraft_state(attitude_timing=attitude_timing()))},
    {"aircraft_state": list(asdict(aircraft_state()).items())},
])
async def test_timing_requires_the_top_level_contract_and_a_corresponding_aircraft_state(native_server, observation):
    path, _, behavior = native_server
    behavior["observation"] = observation
    client = NativeGuidanceClient(path, clock=lambda: 100.)
    try:
        await client.connect()
        with pytest.raises(NativeGuidanceError, match="observation_invalid"):
            await client.observe()
        assert client.capabilities is None
    finally:
        await client.close()


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


@pytest.mark.parametrize("operation", ["engage", "intent"])
async def test_final_guard_rejects_after_rpc_lock_without_wire_effects(native_server, operation):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    await client.connect()
    if operation == "intent":
        await client.engage(identity(), circuit_breaker_active=False)
    refusal = DispatchRefused("target_replaced", DispatchRefusalKind.SUPERSEDED)
    valid = True
    receipts = []

    def guard():
        if not valid:
            raise refusal

    await client._lock.acquire()
    try:
        call = (client.engage(identity(), circuit_breaker_active=False, before_dispatch=guard,
                              on_mode_dispatch=lambda: receipts.append("acquire"))
                if operation == "engage" else
                client.submit(intent(), circuit_breaker_active=False, before_dispatch=guard))
        task = asyncio.create_task(call)
        await asyncio.sleep(0)
        valid = False
        request_id, last_sequence = client._request_id, client._last_sequence
        previous = list(requests)
    finally:
        client._lock.release()
    try:
        with pytest.raises(DispatchRefused) as error:
            await task
        assert error.value is refusal
        assert requests == previous
        assert client._request_id == request_id
        assert client._last_sequence == last_sequence
        assert client.capabilities is not None
        assert receipts == []
        valid = True
        if operation == "engage":
            await client.engage(identity(), circuit_breaker_active=False, before_dispatch=guard,
                                on_mode_dispatch=lambda: receipts.append("acquire"))
            assert receipts == ["acquire"]
        else:
            await client.submit(intent(), circuit_breaker_active=False, before_dispatch=guard)
        assert requests[-1]["operation"] == operation
    finally:
        await client.close()


@pytest.mark.parametrize("operation", ["engage", "intent"])
async def test_async_final_native_guard_is_not_a_transport_failure(native_server, operation):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    await client.connect()
    if operation == "intent":
        await client.engage(identity(), circuit_breaker_active=False)

    async def invalid():
        raise AssertionError("async guard body must not run")

    previous = list(requests)
    try:
        with pytest.raises(DispatchRefused, match="dispatch_guard_contract_invalid"):
            if operation == "engage":
                await client.engage(identity(), circuit_breaker_active=False, before_dispatch=invalid)
            else:
                await client.submit(intent(), circuit_breaker_active=False, before_dispatch=invalid)
        assert requests == previous
        assert client.capabilities is not None
    finally:
        await client.close()


async def test_native_acquisition_receipt_precedes_missing_ack(native_server):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    await client.connect()
    behavior["delay_operation"] = "engage"
    receipts = []
    task = asyncio.create_task(client.engage(
        identity(), circuit_breaker_active=False, before_dispatch=lambda: None,
        on_mode_dispatch=lambda: receipts.append("possibly_sent"),
    ))
    await asyncio.wait_for(behavior["delay_started"].wait(), 1)
    assert receipts == ["possibly_sent"]
    assert requests[-1]["operation"] == "engage"
    assert client.session_identity is None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await client.close()


async def test_guarded_queued_ttl_handoff_does_not_hold_a_superseding_target(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    await client.connect()
    await client.engage(identity(), circuit_breaker_active=False)
    current = True
    refusal = DispatchRefused("target_replaced", DispatchRefusalKind.SUPERSEDED)

    def guard():
        if not current:
            raise refusal

    await client._lock.acquire()
    try:
        task = asyncio.create_task(client.handoff(identity(), reason="intent_expired", before_dispatch=guard))
        await asyncio.sleep(0)
        current = False
        request_id = client._request_id
        previous = list(requests)
    finally:
        client._lock.release()
    try:
        with pytest.raises(DispatchRefused) as error:
            await task
        assert error.value is refusal
        assert requests == previous
        assert client._request_id == request_id
        assert client.session_identity == identity()
        assert client.capabilities is not None
        # Explicit safety teardown remains exempt from an obsolete target guard.
        await client.handoff(identity(), reason="operator_stop")
        assert requests[-1]["operation"] == "handoff"
        assert client.session_identity is None
    finally:
        await client.close()


async def test_invalid_acquisition_observer_cannot_advance_wire_or_session(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    await client.connect()
    previous, request_id = list(requests), client._request_id

    async def invalid():
        raise AssertionError("async acquisition observer must not run")

    try:
        with pytest.raises(DispatchRefused, match="dispatch_guard_contract_invalid"):
            await client.engage(identity(), circuit_breaker_active=False, on_mode_dispatch=invalid)
        assert requests == previous
        assert client._request_id == request_id
        assert client.session_identity is None
        assert client.capabilities is not None
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
