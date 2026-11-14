"""MAVSDK loss retires native pursuit without dropping original release proof."""

from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from classes.aircraft_state import AircraftStateOwner, AirframePhase
from classes.airframe_session_controls import AirframeSessionControls
from classes.command_intent import AltitudeHoldReference
from classes.gimbal_guidance import GimbalGuidancePolicy
from classes.native_follow_binding import NativeFollowBinding
from classes.native_guidance import NativeGuidanceClient
from classes.safety_types import AltitudeLimits
from classes.vector_guidance_session import VectorGuidanceSession
from tests.fixtures.native_ownership import release_receipt, start_context
from tests.unit.core_app.test_fixed_wing_continuity import evidence
from tests.unit.core_app.test_native_follow_application import app as app
from tests.unit.core_app.test_native_follow_binding import CONFIG
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.unit.drone_interface.test_native_guidance import identity
from tests.unit.drone_interface.test_native_guidance import native_server as native_server


@pytest.fixture
async def native_application(app, native_server):
    path, requests, behavior = native_server
    original = identity()
    state = aircraft_state(binding=original.binding)
    behavior["observation"] = {"aircraft_state": asdict(state)}
    client = NativeGuidanceClient(path, request_timeout_s=.1, clock=lambda: 100.)
    capabilities = await client.connect()
    await client.bind(original.binding)
    states = AircraftStateOwner(clock=lambda: 100.)
    states.bind(original.binding)
    assert states.commit(state)
    connection = SimpleNamespace(get_aircraft_state=lambda: states.snapshot(timeout_s=.75),
                                 commit_aircraft_state=states.commit)
    guidance = VectorGuidanceSession(
        original, capabilities, profile_name="gm_velocity_vector",
        controls=AirframeSessionControls.for_fixed_wing(original, step_m_s=.5),
        supported_phases=frozenset({AirframePhase.FIXED_WING}),
        geometry_policy=GimbalGuidancePolicy().geometry, altitude_control=False,
        altitude_limits=AltitudeLimits(5., 120., 2.), confirmation_s=.5,
        observation_timeout_s=.75, initial_phase=AirframePhase.FIXED_WING, clock=lambda: 100.,
    )
    ctrl = app.ctrl
    ctrl.px4_interface.native_start_context = start_context(original)
    ctrl.px4_interface.native_guidance_client = client
    ctrl.px4_interface.get_aircraft_state.return_value = state
    ctrl.px4_interface.get_aircraft_identity.return_value = {
        "autopilot_uid": original.binding.aircraft_uid,
        "connection_generation": original.binding.connection_generation,
    }
    bindings = []

    async def prepare(start_context):
        assert start_context is ctrl.px4_interface.native_start_context
        binding = NativeFollowBinding(
            guidance, connection, client, ctrl.target_continuity,
            profile_name="gm_velocity_vector", continuity_config=CONFIG,
            target_evidence=evidence, context=ctrl._build_target_continuity_context,
            circuit_breaker=lambda: False, clock=lambda: 100.,
        )
        ctrl._following_session_id = original.follow_session_id
        ctrl._native_follow_binding = binding
        bindings.append(binding)
        return binding

    ctrl._prepare_native_follow_binding = AsyncMock(side_effect=prepare)
    try:
        yield SimpleNamespace(ctrl=ctrl, client=client, requests=requests, behavior=behavior,
                              bindings=bindings, original=original)
    finally:
        await client.close()


async def start(native):
    result = await native.ctrl._connect_px4_on_flight_loop()
    assert result["errors"] == []
    assert native.ctrl.following_active
    binding = native.bindings[0]
    assert binding.acquire_dispatched
    assert binding._acquisition == native.client.acquisition_context
    return binding


async def lose_mavsdk(native):
    await native.ctrl._handle_px4_connection_loss_on_flight_loop({"last_error": "test_mavsdk_link_lost"})
    assert not native.ctrl.following_active
    native.ctrl.px4_interface.stop_offboard_mode.assert_not_called()


def post_loss_operations(native, before):
    operations = [row["operation"] for row in native.requests[before:]]
    assert not set(operations) & {"engage", "intent", "phase", "handoff"}
    return operations


@pytest.mark.parametrize("outcome", ["hold_confirmed", "owner_already_released"])
async def test_connection_loss_confirms_only_original_release_via_read_only_protocol(native_application, outcome):
    native = native_application
    binding = await start(native)
    acquisition = native.client.acquisition_context
    native.behavior["owner_confirmed"] = False
    native.behavior["release_receipt"] = release_receipt(acquisition, outcome=outcome).wire_payload()
    before = len(native.requests)
    await lose_mavsdk(native)
    assert post_loss_operations(native, before) == ["hello", "bind", "observe"]
    assert native.requests[before + 1]["payload"]["binding"] == asdict(acquisition.identity.binding)
    assert binding.release_receipt.acquisition == acquisition
    assert native.ctrl._native_follow_binding is None
    assert not native.ctrl._following_offboard_cleanup_required
    assert native.client.session_identity is None


@pytest.mark.parametrize("failure", ["unavailable", "missing_receipt", "token", "runtime", "aircraft_uid"])
async def test_connection_loss_keeps_original_binding_and_barrier_without_matching_receipt(native_application, failure):
    native = native_application
    binding = await start(native)
    acquisition = native.client.acquisition_context
    native.behavior["owner_confirmed"] = False
    if failure == "unavailable":
        native.client.socket_path.unlink()
    elif failure == "token":
        native.behavior["release_receipt"] = release_receipt(replace(acquisition, token="e" * 32)).wire_payload()
    elif failure == "runtime":
        native.behavior["capabilities"] = {**native.client.capabilities.__dict__, "runtime_id": "replacement-runtime"}
    elif failure == "aircraft_uid":
        changed_identity = replace(acquisition.identity,
            binding=replace(acquisition.identity.binding, aircraft_uid="replacement-aircraft"))
        native.behavior["release_receipt"] = release_receipt(
            replace(acquisition, identity=changed_identity,
                    start_context=replace(acquisition.start_context, binding=changed_identity.binding))).wire_payload()
    before = len(native.requests)
    await lose_mavsdk(native)
    operations = post_loss_operations(native, before)
    if failure == "unavailable":
        assert operations == []
    else:
        assert operations[0] == "hello"
    assert native.ctrl._native_follow_binding is binding
    assert native.ctrl._following_offboard_cleanup_required
    assert binding.release_receipt is None
    assert native.client.acquisition_context == acquisition
    assert native.client.session_identity is None
    assert native.ctrl._last_following_handoff["result"] == "failed"
    assert native.ctrl._following_teardown_context["follow_session_id"] == native.original.follow_session_id
    request_count = len(native.requests)
    refused = await native.ctrl._connect_px4_on_flight_loop()
    assert refused["precondition"]["code"] == "following_stop_pending"
    assert len(native.requests) == request_count


async def test_connection_loss_does_not_abort_or_release_a_current_replacement_acquisition(native_application):
    native = native_application
    binding = await start(native)
    original = native.client.acquisition_context
    native.client.abort()
    native.behavior["owner_confirmed"] = False
    native.behavior["release_receipt"] = release_receipt(original).wire_payload()
    await native.client.observe_after_release(native.original, runtime_id=original.runtime_id,
        ownership_token=original.token, mode_id=original.mode_id, acquisition=original)
    await native.client.connect()
    await native.client.bind(native.original.binding)
    state = binding.connection.get_aircraft_state()
    reference = AltitudeHoldReference(state.altitude_amsl_m, state.altitude_reference_generation)
    await native.client.engage(native.original, circuit_breaker_active=False, ownership_token="e" * 32,
                               altitude_reference=reference, start_context=start_context(native.original))
    replacement = native.client.acquisition_context
    assert replacement != original
    before = len(native.requests)
    await lose_mavsdk(native)
    assert post_loss_operations(native, before) == []
    assert native.client.session_identity == native.original
    assert native.client.acquisition_context == replacement
    assert native.ctrl._native_follow_binding is binding
    assert native.ctrl._following_offboard_cleanup_required
    assert binding._acquisition == original
    assert native.ctrl._last_following_handoff["result"] == "failed"
    refused = await native.ctrl._connect_px4_on_flight_loop()
    assert refused["precondition"]["code"] == "following_stop_pending"
    assert native.client.session_identity == native.original
    assert post_loss_operations(native, before) == []


async def test_preacquire_no_dispatch_remains_a_legitimate_local_only_cleanup(native_application):
    native = native_application
    ctrl = native.ctrl
    ctrl._refresh_target_continuity_policy()
    ctrl._reset_target_continuity("partial_start")
    binding = await ctrl._prepare_native_follow_binding(ctrl.px4_interface.native_start_context)
    assert not binding.acquire_dispatched
    result = {"steps": [], "errors": []}
    before = len(native.requests)
    await ctrl._stop_native_follow_binding(result, reason="start_refused", allow_handoff=False)
    assert result["errors"] == []
    assert result["offboard_stop_action"]["reason"] == "native_acquire_not_dispatched"
    assert result["offboard_stop_action"]["local_sender_quiesced"] is True
    assert post_loss_operations(native, before) == []
    assert ctrl._native_follow_binding is None
    assert not ctrl._following_offboard_cleanup_required
