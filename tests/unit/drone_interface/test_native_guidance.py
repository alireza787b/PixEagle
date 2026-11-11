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
    NativeMulticopterCommand, NativeTransitionCommand, NativeAcquisitionContext, NativeReleaseReceipt,
)
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing
from tests.fixtures.native_ownership import acquisition, release_receipt, TOKEN


CAPABILITIES = dict(runtime_id="test-adapter", px4_firmware="test-firmware",
                    external_mode_api_version=2, fixed_wing_supported=True,
                    vtol_transition_supported=True, unrestricted_speed_supported=False, owned_mode_supported=True, owned_mode_id=23)


@pytest.fixture
async def native_server():
    requests = []
    behavior = {"wrong_reply_id": False, "handoff_confirmed": True, "owner_confirmed": True,
                "nav_state": 4, "nav_state_timestamp": 300, "acquisition": None, "release_receipt": None,
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
                    result = behavior.get("capabilities", CAPABILITIES)
                elif operation == "engage":
                    behavior["acquisition"] = acquisition(identity(), token=payload["token"])
                    result = {"owner_confirmed": True, "runtime_id": CAPABILITIES["runtime_id"],
                              "acquisition": behavior["acquisition"].wire_payload()}
                    result.update(behavior.get("engage_reply", {}))
                elif operation == "bind":
                    result = {"bound": payload["binding"]["aircraft_uid"] == "aircraft-a"}
                elif operation == "intent":
                    result = {"accepted_sequence": payload["sequence"], "owner_confirmed": behavior["owner_confirmed"]}
                elif operation == "handoff":
                    behavior["release_receipt"] = release_receipt(
                        behavior["acquisition"], outcome="hold_confirmed" if behavior["handoff_confirmed"] else "unconfirmed"
                    ).wire_payload()
                    result = behavior["release_receipt"]
                    result = behavior.get("handoff_reply", result)
                elif operation == "phase":
                    result = {"accepted_generation": payload["identity"]["guidance_generation"], "owner_confirmed": True}
                else:
                    state = asdict(aircraft_state(binding=identity().binding))
                    state.pop("attitude_timing")
                    result = {"fresh": True, "owner_confirmed": behavior["owner_confirmed"],
                              "nav_state": behavior["nav_state"], "nav_state_timestamp": behavior["nav_state_timestamp"],
                              "rescue_active": False, "runtime_id": "test-adapter",
                              "aircraft_state": state, "release_receipt": behavior["release_receipt"]}
                    result.update(behavior.get("observation", {}))
                if operation == "engage" and behavior.get("drop_engage_ack"):
                    behavior["release_receipt"] = release_receipt(behavior["acquisition"]).wire_payload()
                    behavior["owner_confirmed"] = False
                    break
                response = dict(protocol_version=behavior.get("protocol_version", 2), request_id=request["request_id"],
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


@pytest.mark.parametrize("mode,outcome", [(4, "hold_confirmed"), (5, "owner_already_released")])
async def test_post_abort_reconciles_exact_receipt_without_mode_commands(native_server, mode, outcome):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, request_timeout_s=.1, clock=lambda: 100.)
    await client.connect()
    await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
    context = client.acquisition_context
    client.abort()
    behavior.update(owner_confirmed=False, nav_state=mode)
    behavior["release_receipt"] = release_receipt(context, outcome=outcome, nav_state=mode).wire_payload()
    result = await client.observe_after_release(identity(), runtime_id="test-adapter", mode_id=23, ownership_token=TOKEN, acquisition=context)
    assert result.outcome == outcome
    assert result.acquisition == context
    assert client.session_identity is None
    assert [row["operation"] for row in requests] == ["hello", "engage", "hello", "bind", "observe"]


@pytest.mark.parametrize("change,reason", [
    ({"runtime_id": "restarted-adapter"}, "release_runtime_changed"),
    ({"ownership_token": "0" * 32}, "ownership_token_invalid"),
])
async def test_release_reconciliation_rejects_invalid_original_context(native_server, change, reason):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, request_timeout_s=.05)
    behavior["owner_confirmed"] = False
    kwargs = dict(runtime_id="test-adapter", mode_id=23, ownership_token=TOKEN) | change
    with pytest.raises(NativeGuidanceError, match=reason):
        await client.observe_after_release(identity(), **kwargs)
    assert not any(row["operation"] in {"engage", "intent", "phase", "handoff"} for row in requests)


@pytest.mark.parametrize("replacement", ["token", "firmware_incarnation", "source_revision", "activation_timestamp", "identity"])
async def test_replaced_acquisition_cannot_confirm_hold_even_at_same_mode_and_epoch(native_server, replacement):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, request_timeout_s=.05)
    context = acquisition(identity())
    changed = context.wire_payload()
    changed[replacement] = {
        "token": "1" * 32, "firmware_incarnation": "2" * 32,
        "source_revision": 8, "activation_timestamp": 201,
        "identity": asdict(replace(identity(), guidance_generation=2)),
    }[replacement]
    behavior["release_receipt"] = release_receipt(NativeAcquisitionContext.from_payload(changed)).wire_payload()
    with pytest.raises(NativeGuidanceError, match="context_changed"):
        await client.observe_after_release(identity(), runtime_id="test-adapter", mode_id=23, ownership_token=TOKEN, acquisition=context)
    assert not any(row["operation"] in {"engage", "intent", "phase", "handoff"} for row in requests)


async def test_current_hold_without_correlated_receipt_does_not_confirm_release(native_server):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, request_timeout_s=.04)
    behavior.update(owner_confirmed=False, nav_state=4, nav_state_timestamp=999)
    with pytest.raises(NativeGuidanceError, match="release_unconfirmed"):
        await client.observe_after_release(identity(), runtime_id="test-adapter", mode_id=23, ownership_token=TOKEN)
    assert not any(row["operation"] in {"engage", "intent", "phase", "handoff"} for row in requests)


async def test_release_observation_cannot_replace_an_active_session(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path)
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        count = len(requests)
        with pytest.raises(NativeGuidanceError, match="already_owned"):
            await client.observe_after_release(identity(), runtime_id="test-adapter", mode_id=23, ownership_token=TOKEN)
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
        await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
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
        await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
        await client.connect()
        await client.observe()
        with pytest.raises(NativeGuidanceError, match="session_stale"):
            await client.submit(intent(sequence=2), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
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
            await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=True)
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
        await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
        for invalid, reason in [
            (intent(), "obsolete"),
            (intent(sequence=2, identity=replace(identity(), guidance_generation=2)), "session_stale"),
            (intent(sequence=2, command=FixedWingCommand(0, 40, 0, None, UpperSpeedPolicy.NO_UPPER_SPEED_BOUND)),
             "not_supported"),
        ]:
            with pytest.raises(NativeGuidanceError, match=reason):
                await client.submit(invalid, ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
        clock[0] = 101
        with pytest.raises(NativeGuidanceError, match="expired"):
            await client.submit(intent(sequence=2), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
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
            await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
        assert client.capabilities is None
        with pytest.raises(NativeGuidanceError):
            await client.submit(intent(sequence=2), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
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
        assert (await client.handoff(identity(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, reason="operator_stop")).outcome == "unconfirmed"
        with pytest.raises(NativeGuidanceError, match="session_stale"):
            await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
        assert requests[-1]["operation"] == "handoff"
    finally:
        await client.close()


async def test_phase_advance_invalidates_old_commands_without_starting_a_new_session(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path, clock=lambda: 100)
    try:
        await client.connect()
        await client.engage(identity(), circuit_breaker_active=False)
        await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
        new_identity = replace(identity(), guidance_generation=3)
        await client.advance_generation(new_identity, ownership_token=client.acquisition_token, acquisition=client.acquisition_context)
        with pytest.raises(NativeGuidanceError, match="session_stale"):
            await client.submit(intent(sequence=2), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
        await client.submit(intent(identity=new_identity), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
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
            await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
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
        await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
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
                client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False, before_dispatch=guard))
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
            await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False, before_dispatch=guard)
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
                await client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False, before_dispatch=invalid)
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
        task = asyncio.create_task(client.handoff(identity(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, reason="intent_expired", before_dispatch=guard))
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
        await client.handoff(identity(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, reason="operator_stop")
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
        "intent": lambda: client.submit(intent(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False),
        "phase": lambda: client.advance_generation(replace(identity(), guidance_generation=2), ownership_token=client.acquisition_token, acquisition=client.acquisition_context),
        "handoff": lambda: client.handoff(identity(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, reason="stop"),
    }
    task = asyncio.create_task(calls[operation]())
    await asyncio.wait_for(behavior["delay_started"].wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.capabilities is None
    with pytest.raises(NativeGuidanceError):
        await client.submit(intent(sequence=2), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
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
        await client.submit(intent(command=command), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, circuit_breaker_active=False)
        assert requests[-1]["payload"]["phase"] == phase
        assert requests[-1]["payload"]["command"] == command.wire_payload()
        assert "upper_speed_policy" not in requests[-1]["payload"]["command"]
    finally:
        await client.close()


def test_python_ownership_contract_matches_shared_cpp_golden_json():
    golden = json.loads((Path(__file__).parents[3] / 'native/px4_guidance/test/fixtures/ownership-protocol.json').read_text())
    assert NativeCapabilities.from_payload(golden['capabilities']).owned_mode_supported
    context = NativeAcquisitionContext.from_payload(golden['acquisition'])
    receipt = NativeReleaseReceipt.from_payload(golden['release_receipt'])
    assert context.wire_payload() == golden['acquisition']
    assert receipt.wire_payload() == golden['release_receipt']
    assert receipt.require_match(context.identity, context.runtime_id, context.token, context) is receipt


@pytest.mark.parametrize('token', ['', '0' * 32, 'a' * 31, 'b' * 33, 'A' * 32, 'x' * 32, 1, True])
async def test_malformed_acquisition_token_never_reaches_adapter(native_server, token):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path)
    await client.connect()
    try:
        with pytest.raises(NativeGuidanceError, match='ownership_token_invalid'):
            await client.engage(identity(), circuit_breaker_active=False, ownership_token=token)
        assert [row['operation'] for row in requests] == ['hello']
    finally:
        await client.close()


@pytest.mark.parametrize('field,value', [
    ('source_revision', True), ('source_revision', -1), ('source_revision', 2 ** 64),
    ('source_nav_state', 256), ('mode_id', -1), ('activation_timestamp', 1.),
    ('source_nav_state_timestamp', -1), ('firmware_incarnation', '0' * 32),
    ('identity', None), ('runtime_id', ''),
])
def test_malformed_acquisition_context_fails_closed(field, value):
    payload = acquisition(identity()).wire_payload() | {field: value}
    with pytest.raises(NativeGuidanceError):
        NativeAcquisitionContext.from_payload(payload)


@pytest.mark.parametrize('change', [
    {'outcome': 'success'}, {'outcome': []}, {'observed_nav_state': True},
    {'observed_nav_state': 256}, {'observed_nav_state_timestamp': -1},
    {'observed_nav_state_timestamp': 200}, {'observed_nav_state': 5},
    {'acquisition': None}, {'hold_observed': True},
])
def test_malformed_release_receipts_cannot_authorize_hold(change):
    with pytest.raises(NativeGuidanceError):
        NativeReleaseReceipt.from_payload(release_receipt(acquisition(identity())).wire_payload() | change)


async def test_lost_engage_ack_keeps_original_token_and_reconciles_read_only(native_server):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path, request_timeout_s=.1)
    await client.connect()
    behavior['drop_engage_ack'] = True
    with pytest.raises(NativeGuidanceError, match='reply_missing'):
        await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
    assert client.acquisition_token == TOKEN
    assert client.acquisition_context is None
    assert client.session_identity is None
    receipt = await client.observe_after_release(identity(), runtime_id='test-adapter', mode_id=23, ownership_token=TOKEN)
    assert receipt.acquisition.token == TOKEN
    assert receipt.outcome == 'hold_confirmed'
    assert [row['operation'] for row in requests] == ['hello', 'engage', 'hello', 'bind', 'observe']
    assert client.acquisition_context is None  # A release receipt is not an engagement ACK.


async def test_pending_lost_ack_cannot_be_reacquired_on_reconnect(native_server):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path)
    await client.connect()
    behavior['drop_engage_ack'] = True
    with pytest.raises(NativeGuidanceError):
        await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
    await client.connect()
    try:
        with pytest.raises(NativeGuidanceError, match='already_owned'):
            await client.engage(identity(), circuit_breaker_active=False)
        assert [row['operation'] for row in requests].count('engage') == 1
    finally:
        await client.close()


async def test_acquisition_ack_is_not_replaced_by_later_navigation_observation(native_server):
    path, _, behavior = native_server
    client = NativeGuidanceClient(path)
    await client.connect()
    try:
        await client.engage(identity(), circuit_breaker_active=False)
        original = client.acquisition_context
        assert original.activation_timestamp == 200
        behavior['nav_state_timestamp'] = 300
        assert (await client.observe())['nav_state_timestamp'] == 300
        assert client.acquisition_context is original
    finally:
        await client.close()


async def test_phase_advance_keeps_original_acquisition_identity_and_handoff_token(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path)
    await client.connect()
    try:
        await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
        original = client.acquisition_context
        current = replace(identity(), guidance_generation=2)
        await client.advance_generation(current, ownership_token=client.acquisition_token, acquisition=client.acquisition_context)
        receipt = await client.handoff(current, ownership_token=client.acquisition_token, acquisition=client.acquisition_context, reason='operator_stop')
        assert receipt.acquisition == original
        assert receipt.acquisition.identity == identity()
        assert requests[-1]['payload'] == {'identity': asdict(current), 'token': TOKEN, 'reason': 'operator_stop'}
    finally:
        await client.close()


async def test_read_only_reconciliation_cannot_clear_replacement_client_context(native_server):
    path, _, behavior = native_server
    client = NativeGuidanceClient(path, request_timeout_s=.2)
    behavior['delay_operation'] = 'observe'
    task = asyncio.create_task(client.observe_after_release(identity(), runtime_id='test-adapter', mode_id=23, ownership_token=TOKEN))
    await behavior['delay_started'].wait()
    replacement = replace(identity(), follow_session_id='replacement')
    client._identity = replacement
    client._ownership_token = 'f' * 32
    behavior['release_receipt'] = release_receipt(acquisition(identity())).wire_payload()
    behavior['delay_release'].set()
    with pytest.raises(NativeGuidanceError, match='context_replaced'):
        await task
    assert client.session_identity == replacement
    assert client.acquisition_token == 'f' * 32


async def test_incompatible_handoff_receipt_revokes_only_original_pursuit(native_server):
    path, _, behavior = native_server
    client = NativeGuidanceClient(path)
    await client.connect()
    await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
    behavior['handoff_reply'] = release_receipt(acquisition(identity(), token='d' * 32)).wire_payload()
    try:
        with pytest.raises(NativeGuidanceError, match='context_changed'):
            await client.handoff(identity(), ownership_token=client.acquisition_token, acquisition=client.acquisition_context, reason='operator_stop')
        assert client.session_identity is None
        assert client.acquisition_token == TOKEN
        assert client.acquisition_context.token == TOKEN
    finally:
        await client.close()


async def test_missing_owned_mode_support_refuses_before_engage(native_server):
    path, requests, behavior = native_server
    behavior['capabilities'] = CAPABILITIES | {'owned_mode_supported': False}
    client = NativeGuidanceClient(path)
    await client.connect()
    try:
        with pytest.raises(NativeGuidanceError, match='ownership_contract_unavailable'):
            await client.engage(identity(), circuit_breaker_active=False)
        assert [row['operation'] for row in requests] == ['hello']
    finally:
        await client.close()


async def test_protocol_one_is_not_accepted_as_owned_mode_support(native_server):
    path, requests, behavior = native_server
    behavior['protocol_version'] = 1
    client = NativeGuidanceClient(path)
    with pytest.raises(NativeGuidanceError, match='connection_unavailable'):
        await client.connect()
    assert [row['operation'] for row in requests] == ['hello']
    assert client.capabilities is None


async def test_runtime_replacement_cannot_reconcile_an_old_acquisition(native_server):
    path, requests, behavior = native_server
    client = NativeGuidanceClient(path)
    await client.connect()
    await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
    original = client.acquisition_context
    client.abort()
    behavior['capabilities'] = CAPABILITIES | {'runtime_id': 'replacement-adapter'}
    behavior['release_receipt'] = release_receipt(original).wire_payload()
    with pytest.raises(NativeGuidanceError, match='release_runtime_changed'):
        await client.observe_after_release(identity(), runtime_id=original.runtime_id, mode_id=23,
                                           ownership_token=TOKEN, acquisition=original)
    assert client.acquisition_context is original
    assert [row['operation'] for row in requests] == ['hello', 'engage', 'hello']


@pytest.mark.parametrize('reply', [
    {'owner_confirmed': False}, {'runtime_id': 'replacement-adapter'},
    {'acquisition': None},
    {'acquisition': acquisition(identity(), token='c' * 32).wire_payload()},
    {'acquisition': acquisition(identity(), activation_timestamp=0).wire_payload()},
])
async def test_invalid_engage_ack_cannot_create_authority(native_server, reply):
    path, requests, behavior = native_server
    behavior['engage_reply'] = reply
    client = NativeGuidanceClient(path)
    await client.connect()
    with pytest.raises(NativeGuidanceError):
        await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
    assert client.session_identity is None
    assert client.acquisition_context is None
    assert client.acquisition_token == TOKEN
    assert [row['operation'] for row in requests] == ['hello', 'engage']


@pytest.mark.parametrize('operation', ['handoff', 'intent', 'phase'])
async def test_queued_equal_identity_replacement_cannot_adopt_new_acquisition(native_server, operation):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path)
    await client.connect()
    await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
    original = client.acquisition_context
    await client._lock.acquire()
    try:
        calls = {
            'handoff': lambda: client.handoff(identity(), ownership_token=TOKEN, acquisition=original, reason='late_cleanup'),
            'intent': lambda: client.submit(
                intent(created_at_monotonic_s=client._clock(), expires_at_monotonic_s=client._clock() + .5),
                ownership_token=TOKEN, circuit_breaker_active=False, acquisition=original),
            'phase': lambda: client.advance_generation(replace(identity(), guidance_generation=2),
                ownership_token=TOKEN, acquisition=original),
        }
        call = calls[operation]()
        task = asyncio.create_task(call)
        await asyncio.sleep(0)
        replacement = replace(original, token='e' * 32, source_revision=8)
        client._acquisition = replacement
        client._ownership_token = replacement.token
        previous = list(requests)
    finally:
        client._lock.release()
    try:
        with pytest.raises(NativeGuidanceError, match='acquisition_context_changed'):
            await task
        assert requests == previous
        assert client.session_identity == identity()
        assert client.acquisition_context is replacement
        assert client.acquisition_token == replacement.token
    finally:
        await client.close()


async def test_stale_exchange_cannot_disconnect_a_replacement_socket_context(native_server):
    path, _, behavior = native_server
    client = NativeGuidanceClient(path)
    await client.connect()
    behavior['delay_operation'] = 'observe'
    task = asyncio.create_task(client.observe())
    await behavior['delay_started'].wait()
    client.abort()
    replacement = replace(identity(), follow_session_id='replacement')
    client._identity = replacement
    client._ownership_token = 'f' * 32
    with pytest.raises(NativeGuidanceError):
        await task
    assert client.session_identity == replacement
    assert client.acquisition_token == 'f' * 32


@pytest.mark.parametrize('change', [
    {'source_nav_state_timestamp': 0}, {'source_nav_state': 23},
    {'activation_timestamp': 100}, {'activation_timestamp': 99},
])
def test_invalid_acquisition_epochs_and_source_modes_are_not_proofs(change):
    with pytest.raises(NativeGuidanceError, match='context_invalid'):
        NativeAcquisitionContext.from_payload(acquisition(identity()).wire_payload() | change)


async def test_ack_mode_must_match_captured_registered_mode(native_server):
    path, _, behavior = native_server
    behavior['engage_reply'] = {'acquisition': replace(acquisition(identity()), mode_id=24).wire_payload()}
    client = NativeGuidanceClient(path)
    await client.connect()
    with pytest.raises(NativeGuidanceError, match='context_changed'):
        await client.engage(identity(), circuit_breaker_active=False, ownership_token=TOKEN)
    assert client.session_identity is None
    assert client.acquisition_context is None


async def test_pending_release_receipt_must_match_original_registered_mode(native_server):
    path, requests, behavior = native_server
    context = replace(acquisition(identity()), mode_id=24, activation_timestamp=0)
    behavior['release_receipt'] = release_receipt(context, outcome='owner_already_released').wire_payload()
    client = NativeGuidanceClient(path)
    with pytest.raises(NativeGuidanceError, match='context_changed'):
        await client.observe_after_release(identity(), runtime_id='test-adapter', mode_id=23, ownership_token=TOKEN)
    assert not any(row['operation'] in {'engage', 'intent', 'handoff', 'phase'} for row in requests)


@pytest.mark.parametrize('operation', ['handoff', 'intent', 'phase'])
async def test_contextless_write_cannot_adopt_client_ack(native_server, operation):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path)
    await client.connect()
    await client.engage(identity(), ownership_token=TOKEN, circuit_breaker_active=False)
    previous = list(requests)
    calls = {
        'handoff': lambda: client.handoff(identity(), ownership_token=TOKEN, acquisition=None, reason='stop'),
        'intent': lambda: client.submit(intent(), ownership_token=TOKEN, acquisition=None, circuit_breaker_active=False),
        'phase': lambda: client.advance_generation(replace(identity(), guidance_generation=2), ownership_token=TOKEN, acquisition=None),
    }
    try:
        with pytest.raises(NativeGuidanceError, match='context_changed'):
            await calls[operation]()
        assert requests == previous
        assert client.session_identity == identity()
    finally:
        await client.close()


async def test_stale_circuit_breaker_request_cannot_disconnect_replacement_owner(native_server):
    path, requests, _ = native_server
    client = NativeGuidanceClient(path)
    await client.connect()
    await client.engage(identity(), ownership_token=TOKEN, circuit_breaker_active=False)
    original = client.acquisition_context
    replacement = replace(original, token='c' * 32, source_revision=8)
    client._acquisition = replacement
    client._ownership_token = replacement.token
    previous = list(requests)
    try:
        with pytest.raises(NativeGuidanceError, match='context_changed'):
            await client.submit(intent(), ownership_token=TOKEN, acquisition=original, circuit_breaker_active=True)
        assert client.session_identity == identity()
        assert client.acquisition_context is replacement
        assert client.capabilities is not None
        assert requests == previous
        with pytest.raises(NativeGuidanceError, match='already_owned'):
            await client.engage(identity(), circuit_breaker_active=True)
        assert client.session_identity == identity()
        assert client.capabilities is not None
    finally:
        await client.close()


async def test_drain_and_reply_share_one_rpc_budget_and_retire_socket_immediately(tmp_path):
    class SlowWriter:
        closed = False

        def write(self, data):
            self.request = json.loads(data)

        async def drain(self):
            await asyncio.sleep(.07)

        def close(self):
            self.closed = True

        async def wait_closed(self):
            raise AssertionError('RPC expiry must not add a second close-wait budget')

    class SlowReader:
        completed = False

        async def readline(self):
            await asyncio.sleep(.07)
            self.completed = True
            return json.dumps({'protocol_version': 2, 'request_id': 1, 'generation': 0,
                               'success': True, 'payload': CAPABILITIES}).encode() + b'\n'

    client = NativeGuidanceClient(tmp_path / 'control.sock', request_timeout_s=.1)
    writer, reader = SlowWriter(), SlowReader()
    client._writer, client._reader = writer, reader
    context = acquisition(identity())
    client._acquisition, client._identity = context, identity()
    started = time.monotonic()
    with pytest.raises(NativeGuidanceError, match='transport_failed'):
        await client._exchange('hello', {})
    assert time.monotonic() - started < .2
    assert writer.closed
    assert not reader.completed
    assert client.session_identity is None
    assert client.acquisition_context is context
    assert client._generation == 1
