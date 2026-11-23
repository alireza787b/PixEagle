"""Deterministic source-clock association; these fixtures are not flight evidence."""

from dataclasses import asdict, replace
import asyncio
import math
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.aircraft_state import AircraftStateOwner, AirframePhase, GuidanceSessionIdentity, Quaternion
from classes.capture_timing import SourceSampleStamp
from classes.fixed_camera_calibration import (
    ActiveImageGeometry, FixedCameraCalibration, bind_fixed_camera_calibration, selected_source_signature,
)
from classes.frame_publisher import CaptureStamp
from classes.gazebo_capture import GazeboCameraSettings
from classes import gazebo_guidance_alignment as alignment
from classes.gazebo_guidance_alignment import (
    GazeboImageBearingResolver, SourceAttitudeHistory, bind_native_input_resolver,
    native_guidance_input_readiness,
)
from classes.guidance_observation import ImageMeasurement, ObservationProvenance
from classes.source_time_alignment import SourceAttitudeSample
from tests.fixtures.native_ownership import start_context
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing


@pytest.fixture
def case():
    now = [100.05]
    state = aircraft_state(attitude_timing=attitude_timing(),
        attitude_body_to_ned=Quaternion(math.sqrt(.5), 0., 0., math.sqrt(.5)))
    signature = selected_source_signature(source_type='GAZEBO_CAMERA', backend='gazebo_transport',
        locator='/camera/image', options={'world': 'training', 'pixel_format': 'RGB_INT8'})
    calibration = FixedCameraCalibration(signature, 'camera-v1', 'decoder_pre_orientation',
        (640, 480), (320., 320.), (320., 240.), Quaternion(.5, .5, .5, .5), 'none', 'fixed')
    geometry = ActiveImageGeometry(signature, 'stream', 'epoch', (640, 480), 0, 'none',
                                   (640, 480), 'decoder_pre_orientation')
    bound = bind_fixed_camera_calibration(calibration, geometry)
    settings = GazeboCameraSettings('/run/camera.sock', 'clock-world', 'training', '/camera/image', .05)
    source = SourceSampleStamp('clock-world', 'provider', 1, 1_020_000, 'gazebo_sim_us')
    capture = CaptureStamp('epoch', '1', 100.01, 'fresh', source)
    provenance = ObservationProvenance('stream', 3, bound.geometry_revision, bound.calibration_revision, capture)
    measurement = ImageMeasurement(provenance, (320., 240.), (640, 480), bound.image_to_calibration, True)
    history = SourceAttitudeHistory()
    raw = SourceAttitudeSample(1_000_000, 1_001_000, (1., 0., 0., 0.),
        state.attitude_timing.quat_reset_counter, 100., 'px4_source_us')
    history.commit(asdict(raw), state, runtime_id='native', source_clock_id='clock-world')
    resolver = GazeboImageBearingResolver(settings, bound, history, binding=state.binding,
        runtime_id='native', native_source_clock_id='clock-world', timeout_s=.5, clock=lambda: now[0])
    return SimpleNamespace(now=now, state=state, settings=settings, bound=bound, history=history,
        raw=raw, measurement=measurement, output=SimpleNamespace(image_measurement=measurement), resolver=resolver)


def test_world_ray_uses_retained_raw_sample_not_latest_dds_attitude(case):
    result = case.resolver(case.output, case.state)
    assert (result.direction_ned.x, result.direction_ned.y, result.direction_ned.z) == pytest.approx((1., 0., 0.))
    assert result.association_kind == 'bounded_source_time'
    assert result.worst_case_skew_s == pytest.approx(.02)
    assert result.attitude_state == case.state
    assert result.source_time.attitude == case.raw


def test_duplicate_reads_retain_original_association_and_receipt(case):
    first = case.resolver(case.output, case.state)
    case.now[0] += .1
    assert case.resolver(case.output, case.state) is first
    assert first.source_time.attitude.received_at_monotonic_s == 100.
    assert not case.history.commit(asdict(case.raw), case.state,
        runtime_id='native', source_clock_id='clock-world')


@pytest.mark.parametrize('changes', [dict(received_at_monotonic_s=100.1), dict(quaternion_wxyz=(0., 0., 0., 1.))])
def test_same_source_sample_cannot_be_restamped_or_rotated(case, changes):
    with pytest.raises(ValueError, match='sample_rewritten'):
        case.history.commit(asdict(replace(case.raw, **changes)), case.state,
            runtime_id='native', source_clock_id='clock-world')
    with pytest.raises(ValueError, match='alignment_unavailable'):
        case.resolver(case.output, case.state)


def test_no_alignment_inferred_from_receipt_when_source_times_disagree(case):
    source = replace(case.measurement.provenance.capture.source_sample, timestamp_us=2_000_000)
    provenance = replace(case.measurement.provenance,
        capture=replace(case.measurement.provenance.capture, source_sample=source))
    case.output.image_measurement = replace(case.measurement, provenance=provenance)
    with pytest.raises(ValueError, match='alignment_unavailable'):
        case.resolver(case.output, case.state)


def test_unqualified_clock_label_is_not_a_timing_fallback(case):
    with pytest.raises(ValueError, match='source_clock_domain_unqualified'):
        GazeboImageBearingResolver(case.settings, case.bound, case.history, binding=case.state.binding,
            runtime_id='native', native_source_clock_id='other-clock', timeout_s=.5)


def test_same_frame_measurement_rewrite_is_rejected(case):
    case.resolver(case.output, case.state)
    case.output.image_measurement = replace(case.measurement, pixel_xy=(330., 240.))
    with pytest.raises(ValueError, match='capture_rewritten'):
        case.resolver(case.output, case.state)


def test_retarget_accepts_new_generation_without_accepting_obsolete_generation(case):
    case.resolver(case.output, case.state)
    provenance = replace(case.measurement.provenance, target_generation=4)
    case.output.image_measurement = replace(case.measurement, provenance=provenance)
    assert case.resolver(case.output, case.state).binding.target_generation == 4
    case.output.image_measurement = case.measurement
    with pytest.raises(ValueError, match='target_generation_obsolete'):
        case.resolver(case.output, case.state)


def test_history_retirement_invalidates_even_a_retained_valid_frame(case):
    case.resolver(case.output, case.state)
    case.history.clear()
    with pytest.raises(ValueError, match='alignment_unavailable'):
        case.resolver(case.output, case.state)


def test_stale_raw_attitude_does_not_become_fresh_when_pose_advances(case):
    case.now[0] = 100.8
    state = replace(case.state, sequence=2, observed_at_monotonic_s=100.8,
        attitude_timing=attitude_timing(publication_received_at_monotonic_s=100.8,
                                      sample_received_at_monotonic_s=100.8))
    with pytest.raises(ValueError, match='alignment_unavailable'):
        case.resolver(case.output, state)


def advancing_sample_at_same_publication(case):
    state = replace(case.state, sequence=2, observed_at_monotonic_s=100.02,
        attitude_body_to_ned=Quaternion(math.cos(math.pi / 4 + .01), 0., 0., math.sin(math.pi / 4 + .01)),
        attitude_timing=replace(case.state.attitude_timing,
            sample_timestamp_us=case.state.attitude_timing.publication_timestamp_us,
            publication_received_at_monotonic_s=100.02, sample_received_at_monotonic_s=100.02))
    raw = replace(case.raw, sample_timestamp_us=case.raw.publication_timestamp_us,
        quaternion_wxyz=(math.cos(.01), 0., 0., math.sin(.01)), received_at_monotonic_s=100.02)
    source = replace(case.measurement.provenance.capture.source_sample, sequence=2, timestamp_us=1_021_000)
    capture = replace(case.measurement.provenance.capture, capture_id='2', captured_at=100.02, source_sample=source)
    measurement = replace(case.measurement, provenance=replace(case.measurement.provenance, capture=capture))
    return state, raw, measurement


def test_real_resolver_accepts_new_sample_at_same_publication_without_rewriting_old_ray(case):
    first = case.resolver(case.output, case.state)
    state, raw, measurement = advancing_sample_at_same_publication(case)
    assert state.attitude_timing.publication_timestamp_us == case.state.attitude_timing.publication_timestamp_us
    assert state.attitude_timing.sample_timestamp_us > case.state.attitude_timing.sample_timestamp_us
    assert case.history.commit(asdict(raw), state, runtime_id='native', source_clock_id='clock-world')
    second = case.resolver(SimpleNamespace(image_measurement=measurement), state)
    assert second.source_time.attitude == raw
    assert second.direction_ned != first.direction_ned
    assert first.source_time.attitude == case.raw and first.attitude_state is case.state
    rewritten = replace(state, sequence=3, attitude_body_to_ned=Quaternion(1., 0., 0., 0.))
    with pytest.raises(ValueError, match='guidance_aircraft_state_reordered_or_rewritten'):
        case.resolver(SimpleNamespace(image_measurement=measurement), rewritten)


def test_state_owner_accepts_same_publication_only_with_real_sample_progress(case):
    owner = AircraftStateOwner(clock=lambda: case.now[0])
    owner.bind(case.state.binding)
    assert owner.commit(case.state)
    state, _, _ = advancing_sample_at_same_publication(case)
    assert owner.accepts(state) and owner.commit(state)
    assert owner.snapshot(timeout_s=.5) == state
    assert not owner.commit(replace(state, sequence=3, attitude_body_to_ned=Quaternion(1., 0., 0., 0.)))


@pytest.fixture
def runtime_case(case, monkeypatch):
    receipt = time.monotonic()
    state = replace(case.state, observed_at_monotonic_s=receipt,
        attitude_timing=attitude_timing(publication_received_at_monotonic_s=receipt,
                                      sample_received_at_monotonic_s=receipt))
    capture = replace(case.measurement.provenance.capture, captured_at=receipt)
    measurement = replace(case.measurement,
        provenance=replace(case.measurement.provenance, capture=capture))
    raw = replace(case.raw, received_at_monotonic_s=receipt)
    case.history.clear()
    case.history.commit(asdict(raw), state, runtime_id='native', source_clock_id='clock-world')
    capabilities = SimpleNamespace(runtime_id='native', source_clock_id='clock-world')
    client = SimpleNamespace(capabilities=capabilities, socket_path=Path('/run/native.sock'),
        request_timeout_s=.1, engage=AsyncMock(), acquire=AsyncMock(), publish=AsyncMock())
    context = start_context(GuidanceSessionIdentity('preparing', state.binding, 0), runtime_id='native')
    connection = SimpleNamespace(native_guidance_client=client, source_attitude_history=case.history,
        get_telemetry_stale_timeout_s=lambda: .5, get_aircraft_state=Mock(return_value=state),
        prepare_native_guidance=AsyncMock(), guidance_start_context=context)
    app = SimpleNamespace(px4_interface=connection, _image_calibration_binding=case.bound,
        video_handler=SimpleNamespace(cap=SimpleNamespace(settings=case.settings),
            _capture_source_signature=Mock(return_value=case.bound.geometry.source_signature)),
        get_tracker_output=Mock(return_value=SimpleNamespace(image_measurement=measurement)))
    concrete = SimpleNamespace(setpoint_handler=SimpleNamespace(profile_config={
        'required_tracker_data': ['POSITION_2D']}), update_rate=50., bind_guidance_input_resolver=Mock())
    profile = SimpleNamespace(required_tracker_data=('POSITION_2D',),
        native_phase_contracts=(('fixed_wing', 'fixed_wing_external'),))
    clock, delays = [receipt], []

    async def advance(delay):
        delays.append(delay)
        clock[0] += delay
        await asyncio.sleep(0)

    # Keep actual resolver receipt checks on the real monotonic clock. Only the
    # admission wait's budget is advanced deterministically by its awaited poll.
    monkeypatch.setattr(alignment, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(alignment, 'asyncio', SimpleNamespace(sleep=advance, wait_for=asyncio.wait_for))
    return SimpleNamespace(app=app, connection=connection, client=client, concrete=concrete,
        profile=profile, capabilities=capabilities, state=state, context=context, raw=raw,
        measurement=measurement, history=case.history, clock=clock, delays=delays)


async def test_first_pair_wait_refreshes_observations_without_acquiring_or_replacing_context(runtime_case):
    run = runtime_case
    run.history.clear()
    original = run.context.wire_payload()
    reads = []

    async def refresh(path):
        reads.append(path)
        run.history.commit(asdict(run.raw), run.state,
            runtime_id='native', source_clock_id='clock-world')

    run.connection.prepare_native_guidance.side_effect = refresh
    assert native_guidance_input_readiness(run.app, run.profile, run.state) == {
        'ready': False, 'reason_code': 'source_attitude_alignment_unavailable'}
    run.connection.prepare_native_guidance.assert_not_awaited()
    await bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities)
    run.concrete.bind_guidance_input_resolver.assert_called_once()
    resolver = run.concrete.bind_guidance_input_resolver.call_args.args[0]
    paired = resolver(run.app.get_tracker_output(), run.state)
    assert paired.source_time.attitude == run.raw
    assert paired.bearing.provenance.capture == run.measurement.provenance.capture
    assert reads == [run.client.socket_path] and run.delays == [.02]
    assert run.connection.guidance_start_context is run.context
    assert run.context.wire_payload() == original
    for action in (run.client.engage, run.client.acquire, run.client.publish):
        action.assert_not_called()
    assert native_guidance_input_readiness(run.app, run.profile, run.state) == {
        'ready': True, 'reason_code': None}


async def test_already_qualified_pair_binds_without_sleep_or_native_refresh(runtime_case):
    run = runtime_case
    await bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities)
    run.concrete.bind_guidance_input_resolver.assert_called_once()
    run.connection.prepare_native_guidance.assert_not_awaited()
    assert run.delays == []


async def test_guarded_missing_frame_recovers_only_from_a_new_current_measurement(runtime_case):
    run = runtime_case
    original_output = run.app.get_tracker_output.return_value
    run.app.get_tracker_output.return_value = SimpleNamespace(image_measurement=None)
    guard = Mock()

    async def refresh(_):
        run.app.get_tracker_output.return_value = original_output

    run.connection.prepare_native_guidance.side_effect = refresh
    await bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities, validate_input=guard)
    resolver = run.concrete.bind_guidance_input_resolver.call_args.args[0]
    association = resolver(original_output, run.state)
    assert association.bearing.provenance.capture == run.measurement.provenance.capture
    assert guard.call_count >= 3
    assert run.delays == [.02]
    for action in (run.client.engage, run.client.acquire, run.client.publish):
        action.assert_not_called()


async def test_guarded_target_loss_expires_inside_original_budget_with_specific_reason(runtime_case):
    run = runtime_case
    run.app.get_tracker_output.return_value = SimpleNamespace(image_measurement=None)
    with pytest.raises(ValueError, match='^image_measurement_unavailable$'):
        await bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities, validate_input=Mock())
    assert sum(run.delays) == pytest.approx(run.client.request_timeout_s)
    run.concrete.bind_guidance_input_resolver.assert_not_called()
    for action in (run.client.engage, run.client.acquire, run.client.publish):
        action.assert_not_called()


@pytest.mark.parametrize('reason', ['following_input_context_changed', 'native_start_context_changed'])
async def test_context_change_during_first_pair_wait_cannot_bind_or_renew_deadline(runtime_case, reason):
    run = runtime_case
    run.history.clear()
    guard = Mock(side_effect=[None, ValueError(reason)])
    with pytest.raises(ValueError, match='^' + reason + '$'):
        await bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities, validate_input=guard)
    assert run.delays == [.02]
    run.connection.prepare_native_guidance.assert_not_awaited()
    run.concrete.bind_guidance_input_resolver.assert_not_called()


async def test_context_is_rechecked_before_binding_an_already_qualified_pair(runtime_case):
    run = runtime_case
    guard = Mock(side_effect=[None, ValueError('following_input_context_changed')])
    with pytest.raises(ValueError, match='^following_input_context_changed$'):
        await bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities, validate_input=guard)
    run.concrete.bind_guidance_input_resolver.assert_not_called()
    assert run.delays == []


async def test_cancelled_first_pair_wait_cannot_refresh_bind_or_acquire(runtime_case, monkeypatch):
    run = runtime_case
    run.history.clear()

    async def cancelled(_):
        raise asyncio.CancelledError

    monkeypatch.setattr(alignment.asyncio, 'sleep', cancelled)
    with pytest.raises(asyncio.CancelledError):
        await bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities, validate_input=Mock())
    run.connection.prepare_native_guidance.assert_not_awaited()
    run.concrete.bind_guidance_input_resolver.assert_not_called()
    for action in (run.client.engage, run.client.acquire, run.client.publish):
        action.assert_not_called()


async def test_first_pair_timeout_does_not_issue_a_refresh_after_deadline(runtime_case):
    run = runtime_case
    run.history.clear()
    run.client.request_timeout_s = .01
    with pytest.raises(ValueError, match='^source_attitude_alignment_unavailable$'):
        await bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities)
    run.connection.prepare_native_guidance.assert_not_awaited()
    run.concrete.bind_guidance_input_resolver.assert_not_called()
    assert len(run.delays) == 1 and run.delays[0] == pytest.approx(.01)


async def test_pair_returned_after_original_deadline_cannot_bind(runtime_case):
    run = runtime_case
    run.history.clear()

    async def late_refresh(_):
        run.history.commit(asdict(run.raw), run.state,
            runtime_id='native', source_clock_id='clock-world')
        run.clock[0] += run.client.request_timeout_s

    run.connection.prepare_native_guidance.side_effect = late_refresh
    with pytest.raises(ValueError, match='^source_attitude_alignment_unavailable$'):
        await bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities)
    run.connection.prepare_native_guidance.assert_awaited_once_with(run.client.socket_path)
    run.concrete.bind_guidance_input_resolver.assert_not_called()


async def test_refresh_timeout_is_a_not_ready_result_without_binding(runtime_case):
    run = runtime_case
    run.history.clear()
    run.client.request_timeout_s = .03
    cancelled = []

    async def stalled_refresh(_):
        try:
            await asyncio.Future()
        finally:
            cancelled.append(True)

    run.connection.prepare_native_guidance.side_effect = stalled_refresh
    with pytest.raises(ValueError, match='^source_attitude_alignment_unavailable$'):
        await asyncio.wait_for(
            bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities), timeout=.25)
    assert cancelled == [True]
    run.connection.prepare_native_guidance.assert_awaited_once_with(run.client.socket_path)
    run.concrete.bind_guidance_input_resolver.assert_not_called()


@pytest.mark.parametrize('defect, reason', [
    ('clock', 'source_clock_domain_unqualified'),
    ('geometry', 'physical_capture_timing_unqualified'),
    ('measurement', 'image_measurement_unavailable'),
])
async def test_readiness_and_start_refuse_the_same_invalid_input_without_waiting(runtime_case, defect, reason):
    run = runtime_case
    if defect == 'clock':
        run.capabilities.source_clock_id = 'different-world'
    elif defect == 'geometry':
        run.app.video_handler._capture_source_signature.return_value = 'different-source'
    else:
        run.app.get_tracker_output.return_value = SimpleNamespace(image_measurement=None)
    assert native_guidance_input_readiness(run.app, run.profile, run.state) == {
        'ready': False, 'reason_code': reason}
    with pytest.raises(ValueError, match='^' + reason + '$'):
        await bind_native_input_resolver(run.app, run.concrete, run.state, run.capabilities)
    run.connection.prepare_native_guidance.assert_not_awaited()
    run.concrete.bind_guidance_input_resolver.assert_not_called()
    assert run.delays == []


def test_readiness_reports_missing_native_client_without_observing_or_acquiring(runtime_case):
    run = runtime_case
    run.connection.native_guidance_client = None
    assert native_guidance_input_readiness(run.app, run.profile, run.state) == {
        'ready': False, 'reason_code': 'native_aircraft_state_unavailable'}
    run.app.get_tracker_output.assert_not_called()
    run.connection.prepare_native_guidance.assert_not_awaited()


@pytest.mark.parametrize('unsupported', ['mc', 'angles', 'no_resolver'])
async def test_irrelevant_phase_or_input_does_not_prepare_image_resolution(runtime_case, unsupported):
    run = runtime_case
    state = run.state
    if unsupported == 'mc':
        state = replace(state, phase=AirframePhase.MULTICOPTER)
    elif unsupported == 'angles':
        run.concrete.setpoint_handler.profile_config['required_tracker_data'] = ['CAMERA_ANGLES']
        run.profile.required_tracker_data = ('CAMERA_ANGLES',)
    else:
        run.concrete.bind_guidance_input_resolver = None
        run.profile.native_phase_contracts = ()
    run.app.video_handler = None
    await bind_native_input_resolver(run.app, run.concrete, state, run.capabilities)
    assert native_guidance_input_readiness(run.app, run.profile, state) == {
        'ready': True, 'reason_code': None}
    run.app.get_tracker_output.assert_not_called()
    run.connection.prepare_native_guidance.assert_not_awaited()
    assert run.delays == []
