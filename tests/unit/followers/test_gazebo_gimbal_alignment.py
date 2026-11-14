"""Source-time association is simulation evidence, not hardware qualification."""

from dataclasses import asdict, replace
import math
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from classes.aircraft_state import Quaternion
from classes.capture_timing import SourceSampleStamp
from classes.gazebo_gimbal_source import GazeboGimbalSettings, GazeboSipGimbalProvider
from classes.gazebo_guidance_alignment import (
    GazeboGimbalBearingResolver, SourceAttitudeHistory, bind_native_input_resolver,
    native_guidance_input_readiness,
)
from classes.gimbal_geometry import angle_geometry_revision, resolve_angle_geometry
from classes.gimbal_types import CameraObservationSource, GimbalAngleObservation
from classes.source_time_alignment import SourceAttitudeSample
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing


@pytest.fixture(params=['HORIZONTAL', 'VERTICAL'])
def case(request):
    mount = request.param
    state = aircraft_state(attitude_timing=attitude_timing(),
        attitude_body_to_ned=Quaternion.from_euler(0., 0., math.pi/2))
    raw = SourceAttitudeSample(1_000_000, 1_001_000, (1., 0., 0., 0.),
        state.attitude_timing.quat_reset_counter, 100., 'px4_source_us')
    settings = GazeboGimbalSettings('/tmp/gimbal.sock', 'clock', 'training', .05)
    geometry = resolve_angle_geometry({}, mount)
    source = CameraObservationSource('camera-owner', 1)
    observation = GimbalAngleObservation(source, 3, 'topotek_sip_udp',
        angle_geometry_revision('topotek_sip_udp', mount, geometry),
        (0., 90., 0.) if mount == 'VERTICAL' else (0., 0., 0.),
        'gimbal_body', 1, 100., 'TRACKING_ACTIVE', 100.,
        SourceSampleStamp('clock', 'pose-producer', 1, 1_020_000, 'gazebo_sim_us'))
    history = SourceAttitudeHistory()
    history.commit(asdict(raw), state, runtime_id='native', source_clock_id='clock')
    now = [100.05]
    resolver = GazeboGimbalBearingResolver(settings, history, source=source, provider_id='topotek_sip_udp',
        mount=mount, geometry=geometry, binding=state.binding, runtime_id='native',
        native_source_clock_id='clock', timeout_s=.5, clock=lambda: now[0])
    return SimpleNamespace(mount=mount, state=state, raw=raw, settings=settings, geometry=geometry,
        observation=observation, history=history, now=now, resolver=resolver,
        output=SimpleNamespace(gimbal_observation=observation))


def test_both_mounts_use_raw_source_attitude_not_latest_navigation_attitude(case):
    result = case.resolver(case.output, case.state)
    assert result.direction_ned.x == pytest.approx(1.)
    assert result.direction_ned.y == pytest.approx(0.)
    assert result.direction_ned.z == pytest.approx(0.)
    assert result.source_time.attitude == case.raw
    assert result.worst_case_skew_s == pytest.approx(.02)
    assert result.bearing.provenance.time_basis == 'backend_receipt'


def test_status_only_progress_keeps_original_source_sample_and_attitude(case):
    first = case.resolver(case.output, case.state)
    case.output.gimbal_observation = replace(case.observation, tracking_received_at_monotonic_s=100.01)
    second = case.resolver(case.output, case.state)
    assert second.source_time is first.source_time
    assert second.attitude_state is first.attitude_state
    assert second.direction_ned == first.direction_ned
    assert second.bearing.provenance.angle_received_at_monotonic_s == 100.


@pytest.mark.parametrize('mutation', [
    lambda o: replace(o, source_sample=None),
    lambda o: replace(o, source_sample=replace(o.source_sample, clock_id='other')),
    lambda o: replace(o, source_sample=replace(o.source_sample, timestamp_us=2_000_000)),
    lambda o: replace(o, geometry_revision='other'),
    lambda o: replace(o, source=CameraObservationSource('new-owner', 1)),
    lambda o: replace(o, tracking_state='TARGET_LOST'),
])
def test_unqualified_observation_cannot_use_latest_pose_as_fallback(case, mutation):
    case.output.gimbal_observation = mutation(case.observation)
    with pytest.raises(ValueError):
        case.resolver(case.output, case.state)


def test_retired_history_invalidates_previously_valid_observation(case):
    case.resolver(case.output, case.state)
    case.history.clear()
    with pytest.raises(ValueError, match='alignment_unavailable'):
        case.resolver(case.output, case.state)


def test_same_receipt_cannot_rewrite_angle_or_original_stamp(case):
    case.resolver(case.output, case.state)
    case.output.gimbal_observation = replace(case.observation, angles_deg=(1., 2., 3.))
    with pytest.raises(ValueError, match='capture_rewritten'):
        case.resolver(case.output, case.state)
    case.output.gimbal_observation = replace(case.observation,
        source_sample=replace(case.observation.source_sample, timestamp_us=1_030_000))
    with pytest.raises(ValueError, match='capture_rewritten'):
        case.resolver(case.output, case.state)


def test_retarget_does_not_allow_older_generation_to_return(case):
    case.resolver(case.output, case.state)
    case.output.gimbal_observation = replace(case.observation, target_generation=4)
    assert case.resolver(case.output, case.state).binding.target_generation == 4
    case.output.gimbal_observation = case.observation
    with pytest.raises(ValueError, match='target_generation_obsolete'):
        case.resolver(case.output, case.state)


async def test_runtime_binds_gimbal_input_without_rendered_image_or_frame_tokens(case, monkeypatch):
    # Bound receipt clocks replace deterministic fixture time only for the public
    # readiness helper's newly constructed resolver.
    monkeypatch.setattr('classes.gazebo_guidance_alignment.GazeboGimbalBearingResolver',
        lambda *args, **kwargs: case.resolver)
    provider = GazeboSipGimbalProvider(case.settings)
    runtime = SimpleNamespace(provider=provider, settings=dict(MOUNT_TYPE=case.mount),
        angle_observation_context=lambda: case.observation.source)
    capabilities = SimpleNamespace(runtime_id='native', source_clock_id='clock')
    connection = SimpleNamespace(source_attitude_history=case.history,
        get_telemetry_stale_timeout_s=lambda: .5,
        get_aircraft_state=lambda: case.state,
        native_guidance_client=SimpleNamespace(capabilities=capabilities, request_timeout_s=1.))
    app = SimpleNamespace(camera_runtime=runtime, px4_interface=connection,
        get_tracker_output=lambda: case.output, video_handler=None)
    profile = SimpleNamespace(required_tracker_data=('GIMBAL_ANGLES',),
        native_phase_contracts=(('fixed_wing', 'fixed_wing_external'),))
    concrete = SimpleNamespace(setpoint_handler=SimpleNamespace(profile_config={
        'required_tracker_data': ['GIMBAL_ANGLES']}), update_rate=50., bind_guidance_input_resolver=Mock())
    assert native_guidance_input_readiness(app, profile, case.state)['ready']
    await bind_native_input_resolver(app, concrete, case.state, capabilities)
    concrete.bind_guidance_input_resolver.assert_called_once_with(case.resolver)
