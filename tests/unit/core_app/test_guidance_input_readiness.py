"""Read-only guidance qualification gates startup and the shared target evidence."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import time

import pytest

from classes.app_controller import AppController
from tests.fixtures.following_observation import bind_image_source, bind_controller_source
from classes.followers.base_follower import BaseFollower
from classes.following_readiness import (
    evaluate_follower_guidance_input,
    evaluate_following_start_readiness,
    following_readiness_failure_code,
)
from classes.frame_publisher import CaptureStamp
from classes.guidance_observation import ImageFrameContext, ObservationProvenance
from classes.target_continuity import (
    AirframePhase, ContinuityAuthorityState, ContinuityPolicy, IdentityVerdict,
    TargetContinuitySupervisor, TargetEvidenceState,
)
from tests.unit.core_app.test_app_controller_offboard_safety import _active_position_output
from tests.unit.core_app.test_native_follow_application import app  # noqa: F401
from tests.unit.core_app.test_native_follow_binding import CONFIG


pytestmark = pytest.mark.unit


def input_controller(hook):
    sample = _active_position_output()
    state = object()
    ctrl = object.__new__(AppController)
    ctrl._tracking_session_generation = 0
    bind_image_source(ctrl, sample)
    ctrl.get_tracker_output = Mock(return_value=sample)
    ctrl.px4_interface = SimpleNamespace(get_aircraft_state=Mock(return_value=state))
    ctrl.follower = SimpleNamespace(follower=SimpleNamespace(require_guidance_input=hook))
    ctrl._tracker_requires_video_for_following = lambda: True
    ctrl.video_handler = SimpleNamespace(get_frame_status=lambda: {"usable_for_following": True})
    ctrl.target_continuity = SimpleNamespace(get_status=lambda: {"target_transition_pending": False})
    return ctrl, sample, state


def readiness(ctrl):
    return evaluate_following_start_readiness(
        ctrl, runtime_status={"usable_for_following": True, "active_tracking": True},
    )


def context(*, capture_id="1", epoch="source-a", geometry="geometry-a"):
    capture = CaptureStamp(epoch, capture_id, time.monotonic(), "fresh")
    return ImageFrameContext(ObservationProvenance("stream-a", 0, geometry, None, capture), (640, 480))


def test_base_input_hook_is_read_only_and_preserves_existing_profiles():
    sample = _active_position_output()
    before = sample.to_dict()
    assert BaseFollower.require_guidance_input(object(), sample, None) is None
    assert sample.to_dict() == before
    assert evaluate_follower_guidance_input(SimpleNamespace()) == {"ready": True, "reason_code": None}


def test_canonical_readiness_calls_hook_with_exact_current_values():
    hook = Mock(return_value=None)
    ctrl, sample, state = input_controller(hook)
    result = readiness(ctrl)
    assert result["usable_for_following"] is True
    assert result["guidance_input_readiness"] == {"ready": True, "reason_code": None}
    hook.assert_called_once_with(sample, state)


async def test_active_phase_readiness_cannot_advance_camera_association_ahead_of_command_owner():
    from tests.unit.drone_interface.test_mavlink_command_transport import Bench

    bench = Bench()
    await bench.engage()
    hook = Mock(return_value=None)
    ctrl, sample, _ = input_controller(hook)
    ctrl.follower.follower._airframe_session = bench.guidance
    ctrl.follower.follower._airframe_session_bound = True
    state = bench.guidance.require_state()
    assert evaluate_follower_guidance_input(ctrl, sample)["ready"]
    hook.assert_called_once_with(sample, state)
    ctrl.px4_interface.get_aircraft_state.assert_not_called()
    await bench.sleep(.6)
    assert evaluate_follower_guidance_input(ctrl, sample) == {"ready": False, "reason_code": "aircraft_state_stale"}
    assert hook.call_count == 1


@pytest.mark.parametrize("error,code", [
    (ValueError("image_attitude_alignment_stale"), "image_attitude_alignment_stale"),
    (ValueError("bad value with private source details"), "guidance_input_invalid"),
    (RuntimeError("unexpected implementation failure"), "guidance_input_readiness_failed"),
])
def test_input_failures_are_structured_and_fail_closed(error, code):
    ctrl, sample, _ = input_controller(Mock(side_effect=error))
    result = readiness(ctrl)
    assert not result["usable_for_following"]
    assert following_readiness_failure_code(result) == code
    assert result["reason"].endswith(code)
    evidence = ctrl._target_evidence_snapshot(sample)
    assert evidence.state is TargetEvidenceState.UNCERTAIN
    assert evidence.identity_verdict is IdentityVerdict.UNCONFIRMED
    assert evidence.reason_code == code
    assert not hasattr(ctrl.follower.follower, "_geometry_invalid")
    assert not hasattr(ctrl.follower.follower, "_safety_rejection")


def test_noncallable_input_hook_cannot_authorize_following():
    ctrl, _, _ = input_controller(False)
    assert following_readiness_failure_code(readiness(ctrl)) == "guidance_input_contract_invalid"


@pytest.mark.parametrize("value", [False, True, object()])
def test_hook_must_validate_synchronously_and_return_none(value):
    ctrl, _, _ = input_controller(Mock(return_value=value))
    assert following_readiness_failure_code(readiness(ctrl)) == "guidance_input_contract_invalid"


def test_async_hook_is_rejected_without_leaving_an_unawaited_coroutine():
    async def hook(_output, _state):
        pytest.fail("An asynchronous validation hook must never run")

    ctrl, _, _ = input_controller(hook)
    assert following_readiness_failure_code(readiness(ctrl)) == "guidance_input_contract_invalid"


def test_source_and_evidence_readers_do_not_refresh_an_old_measurement():
    clock = [100.]
    provenance = ObservationProvenance("stream-a", 0, "geometry-a", None, CaptureStamp("source-a", "1", 100., "fresh"))
    measurement = ImageFrameContext(provenance, (640, 480)).at_pixel((319.5, 239.5))

    def require_input(output, _state):
        assert output.image_measurement is measurement
        measurement.provenance.require_current(
            source_id="stream-a", source_epoch="source-a", target_generation=0,
            geometry_revision="geometry-a", calibration_revision=None,
            now_monotonic_s=clock[0], max_receipt_age_s=.5,
        )

    ctrl, sample, _ = input_controller(require_input)
    sample.image_measurement = measurement
    ctrl.tracking_input_context = ImageFrameContext(provenance, (640, 480))
    ctrl.frame_publisher = SimpleNamespace(stream_id='stream-a', control_source_epoch='source-a')
    original = sample.to_dict()
    for _ in range(3):
        assert readiness(ctrl)["usable_for_following"]
        assert ctrl._target_evidence_snapshot(sample).state is TargetEvidenceState.CONFIRMED
    clock[0] = 100.6
    for _ in range(3):
        assert not readiness(ctrl)["usable_for_following"]
        assert ctrl._target_evidence_snapshot(sample).reason_code == "image_receipt_stale"
    assert sample.image_measurement is measurement
    assert sample.to_dict() == original


async def test_native_discovery_cannot_engage_after_target_becomes_unusable(app):
    original = app.ctrl._prepare_airframe_follow_binding.side_effect

    async def prepare(start_context):
        binding = await original(start_context)
        await asyncio.sleep(0)
        app.ctrl._get_follow_start_readiness.return_value = {"usable_for_following": False, "reason": "target_lost"}
        return binding

    app.ctrl._prepare_airframe_follow_binding.side_effect = prepare
    result = await app.ctrl._connect_px4_on_flight_loop()
    assert result["precondition"]["stage"] == "after_native_discovery"
    app.f.client.engage.assert_not_called()
    app.f.client.handoff.assert_not_called()
    app.f.client.observe_after_release.assert_not_called()
    app.commander_factory.assert_not_called()
    app.ctrl.px4_interface.stop_offboard_mode.assert_not_called()
    assert not app.ctrl.following_active


@pytest.mark.parametrize("change", ["target", "source", "geometry", "calibration"])
async def test_new_target_or_source_during_native_discovery_requires_fresh_start(app, change):
    ctrl = app.ctrl
    ctrl._tracking_session_generation = 0
    ctrl.tracking_input_context = context()
    ctrl.frame_publisher = SimpleNamespace(stream_id="stream-a", control_source_epoch="source-a")
    ctrl.get_tracker_output().image_measurement = ctrl.tracking_input_context.at_pixel((319.5, 239.5))
    original = ctrl._prepare_airframe_follow_binding.side_effect

    async def prepare(start_context):
        binding = await original(start_context)
        await asyncio.sleep(0)
        if change == "target":
            ctrl._tracking_session_generation += 1
        elif change == "source":
            ctrl.frame_publisher.control_source_epoch = "source-b"
        else:
            provenance = replace(ctrl.tracking_input_context.provenance, **{
                "geometry_revision" if change == "geometry" else "calibration_revision": "changed",
            })
            ctrl.tracking_input_context = ImageFrameContext(provenance, (640, 480))
        return binding

    ctrl._prepare_airframe_follow_binding.side_effect = prepare
    result = await ctrl._connect_px4_on_flight_loop()
    assert result["precondition"]["code"] == "following_input_context_changed"
    assert result["precondition"]["stage"] == "after_native_discovery"
    app.f.client.engage.assert_not_called()
    app.f.client.handoff.assert_not_called()
    app.f.client.observe_after_release.assert_not_called()
    app.commander_factory.assert_not_called()
    assert ctrl._airframe_follow_binding is None
    assert ctrl._following_offboard_cleanup_required is False
    assert not ctrl.following_active


async def test_new_frame_in_same_geometry_during_discovery_does_not_change_start_identity(app):
    ctrl = app.ctrl
    ctrl.tracking_input_context = context()
    ctrl.frame_publisher = SimpleNamespace(stream_id="stream-a", control_source_epoch="source-a")
    ctrl.get_tracker_output().image_measurement = ctrl.tracking_input_context.at_pixel((319.5, 239.5))
    original = ctrl._prepare_airframe_follow_binding.side_effect

    async def prepare(start_context):
        binding = await original(start_context)
        ctrl.tracking_input_context = context(capture_id="2")
        return binding

    ctrl._prepare_airframe_follow_binding.side_effect = prepare
    result = await ctrl._connect_px4_on_flight_loop()
    assert not result["errors"]
    assert ctrl.following_active
    app.f.client.engage.assert_awaited_once()


async def test_video_only_epoch_changes_do_not_invalidate_non_video_target_identity(app):
    ctrl = app.ctrl
    ctrl._tracker_requires_video_for_following = lambda: False
    from tests.unit.core_app.test_app_controller_offboard_safety import _active_gimbal_output
    external = bind_controller_source(ctrl, _active_gimbal_output())
    ctrl.get_tracker_output = Mock(return_value=external)
    ctrl.frame_publisher = SimpleNamespace(stream_id="stream-a", control_source_epoch="source-a")
    ctrl.get_tracker_output().image_measurement = ctrl.tracking_input_context.at_pixel((319.5, 239.5))
    original = ctrl._prepare_airframe_follow_binding.side_effect

    async def prepare(start_context):
        binding = await original(start_context)
        ctrl.frame_publisher.control_source_epoch = "source-b"
        return binding

    ctrl._prepare_airframe_follow_binding.side_effect = prepare
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    app.f.client.engage.assert_awaited_once()


@pytest.mark.parametrize("stage", ["engage", "publisher"])
@pytest.mark.parametrize("change", ["target", "source"])
async def test_identity_change_during_acquisition_or_publisher_start_never_activates_following(app, stage, change):
    ctrl = app.ctrl
    ctrl._tracking_session_generation = 0
    ctrl.tracking_input_context = context()
    ctrl.frame_publisher = SimpleNamespace(stream_id="stream-a", control_source_epoch="source-a")
    ctrl.get_tracker_output().image_measurement = ctrl.tracking_input_context.at_pixel((319.5, 239.5))
    target = app.f.client.engage if stage == "engage" else app.commander.start
    original = target.side_effect

    async def changed(*args, **kwargs):
        value = await original(*args, **kwargs) if original is not None else target.return_value
        await asyncio.sleep(0)
        if change == "target":
            ctrl._tracking_session_generation += 1
        else:
            ctrl.frame_publisher.control_source_epoch = "source-b"
        return value

    target.side_effect = changed
    result = await ctrl._connect_px4_on_flight_loop()
    assert result["precondition"]["code"] == "following_input_context_changed"
    assert result["precondition"]["stage"] == ("after_offboard" if stage == "engage" else "before_activation")
    assert not ctrl.following_active
    app.f.client.handoff.assert_awaited_once()
    if stage == "engage":
        app.commander_factory.assert_not_called()
    else:
        app.commander.stop.assert_awaited_once()


async def test_read_only_discovery_preserves_captured_context_before_specialized_input_validation(app):
    ctrl = app.ctrl
    current_state = [app.f.state]
    original = ctrl._prepare_airframe_follow_binding.side_effect
    sample = _active_position_output()
    bind_image_source(ctrl, sample)

    def hook(output, state):
        assert output is sample
        assert state is app.f.state

    app.manager.follower.require_guidance_input = hook
    ctrl.get_tracker_output = Mock(return_value=sample)
    ctrl.px4_interface.get_aircraft_state = lambda: current_state[0]
    ctrl.video_handler = SimpleNamespace(get_frame_status=lambda: {"usable_for_following": True})
    ctrl._get_follow_start_readiness = lambda: readiness(ctrl)

    async def discover(_socket_path):
        assert current_state[0] is app.f.state
        return app.f.guidance.phase_owner.capabilities

    async def prepare(start_context):
        assert current_state[0] is app.f.state
        return await original(start_context)

    ctrl.px4_interface.prepare_native_guidance.side_effect = discover
    ctrl._prepare_airframe_follow_binding.side_effect = prepare
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    assert ctrl.following_active
    ctrl.px4_interface.prepare_native_guidance.assert_awaited_once()
    ctrl._prepare_airframe_follow_binding.assert_awaited_once()


@pytest.mark.parametrize("failure_stage", ["discovery", "engage", "publisher"])
async def test_additional_input_readiness_is_checked_across_awaited_startup(app, failure_stage):
    ctrl = app.ctrl
    valid = [True]
    sample = _active_position_output()
    bind_image_source(ctrl, sample)

    def hook(output, state):
        assert output is sample and state is app.f.state
        if not valid[0]:
            raise ValueError("image_attitude_alignment_stale")

    app.manager.follower.require_guidance_input = hook
    ctrl.get_tracker_output = Mock(return_value=sample)
    ctrl.px4_interface.get_aircraft_state = Mock(return_value=app.f.state)
    ctrl.video_handler = SimpleNamespace(get_frame_status=lambda: {"usable_for_following": True})
    ctrl._get_follow_start_readiness = lambda: readiness(ctrl)
    target = {"discovery": ctrl._prepare_airframe_follow_binding,
              "engage": app.f.client.engage, "publisher": app.commander.start}[failure_stage]
    original = target.side_effect

    async def fail_input(*args, **kwargs):
        result = await original(*args, **kwargs) if original is not None else target.return_value
        await asyncio.sleep(0)
        valid[0] = False
        return result

    target.side_effect = fail_input
    result = await ctrl._connect_px4_on_flight_loop()
    assert result["precondition"]["code"] == "image_attitude_alignment_stale"
    assert not ctrl.following_active
    if failure_stage == "discovery":
        app.f.client.engage.assert_not_called()
        app.f.client.handoff.assert_not_called()
        app.f.client.observe_after_release.assert_not_called()
        app.commander_factory.assert_not_called()
    elif failure_stage == "engage":
        app.commander_factory.assert_not_called()
        app.f.client.handoff.assert_awaited_once()
    else:
        app.commander.stop.assert_awaited_once()
        app.f.client.handoff.assert_awaited_once()


async def test_unqualified_input_uses_shared_fw_recovery_without_resetting_its_budget(app):
    ctrl = app.ctrl
    valid = [True]
    sample = _active_position_output()
    bind_image_source(ctrl, sample)

    def hook(_output, _state):
        if not valid[0]:
            raise ValueError("image_attitude_alignment_stale")

    app.manager.follower.require_guidance_input = hook
    assert not (await ctrl._connect_px4_on_flight_loop())["errors"]
    ctrl.get_tracker_output = lambda: sample
    ctrl.px4_interface.get_aircraft_state = app.f.connection.get_aircraft_state
    app.f.binding._target_evidence = lambda: ctrl._target_evidence_snapshot(sample)
    supervisor = TargetContinuitySupervisor(
        ContinuityPolicy.resolve(CONFIG, "gm_velocity_vector", AirframePhase.FIXED_WING),
        clock=lambda: app.f.clock[0],
    )
    supervisor.reset_session(session_epoch=0, reason="contract_test")
    ctrl.target_continuity = supervisor
    for _ in range(4):
        await app.f.observation()
    nominal = app.f.guidance.baseline()
    decision = supervisor.evaluate(ctrl._target_evidence_snapshot(sample), app.f.binding.context(app.f.base), nominal)
    assert decision.authorized_intent is not None
    supervisor.record_authorized_intent(decision.authorized_intent)
    valid[0] = False
    for index in range(82):
        await app.f.observation()
        evidence = ctrl._target_evidence_snapshot(sample)
        assert evidence.state is TargetEvidenceState.UNCERTAIN
        decision = supervisor.evaluate(evidence, app.f.binding.context(app.f.base), None)
        if index == 0:
            assert supervisor.get_status()["authority_state"] == ContinuityAuthorityState.COASTING.value
            assert decision.handoff_request is None
            assert decision.authorized_intent.control_type == "fixed_wing_external"
            assert decision.authorized_intent.fields["height_rate_m_s"] == 0.
    assert decision.handoff_request is not None
    assert decision.reason_code == "maximum_coast_time_reached"
    assert app.manager.follower.require_guidance_input is hook
