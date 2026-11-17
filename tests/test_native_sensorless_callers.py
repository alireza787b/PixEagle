"""Harness caller regressions with synthetic native packets; no simulator or control IO."""
import asyncio
import math
from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.aircraft_state import AircraftBinding, AircraftState, AirframePhase, GuidanceSessionIdentity
from classes.native_guidance import NativeCapabilities
from classes.safety_types import AltitudeLimits
from classes.target_continuity import TargetEvidenceState
from tests.fixtures.native_ownership import acquisition, start_context
from tests.test_native_vector_sih import flight_window, transition_packet, native_follower_environment
from tests.unit.drone_interface.test_aircraft_state import attitude_timing
from tools import run_native_vector_sih as tool


def packets(*, sensorless=True, feedback=False, binding=None, phase=AirframePhase.FIXED_WING):
    states = flight_window()
    states += [replace(states[-1], sequence=7, observed_at_monotonic_s=103.1,
        airspeed=replace(states[-1].airspeed, observed_at_monotonic_s=103.1))]
    result = []
    for state in states:
        stamp = state.observed_at_monotonic_s
        state = replace(state, binding=binding or state.binding, is_vtol=True, phase=phase,
            velocity_ned_m_s=replace(state.velocity_ned_m_s, x=0., y=0.),
            attitude_timing=attitude_timing(publication_timestamp_us=int(stamp*1e6),
                sample_timestamp_us=int(stamp*1e6)-1000,
                publication_received_at_monotonic_s=stamp, sample_received_at_monotonic_s=stamp))
        if sensorless:
            state = replace(state, airspeed=replace(state.airspeed, source='unavailable', valid=False,
                                                    equivalent_m_s=None, true_m_s=None))
        context = acquisition(GuidanceSessionIdentity('caller', state.binding, 1))
        packet = transition_packet(state, context, nav_state_timestamp=300,
            attitude_timing=asdict(state.attitude_timing), phase_status_fresh=True,
            release_pending=False, neutral_drain_active=False)
        packet['start_context'] = asdict(start_context(context.identity, phase=phase.value))
        if feedback is not None:
            packet['native_guidance_feedback'] = dict(airspeed_control_enabled=feedback,
                observed_at_monotonic_s=stamp, nav_state=4, nav_state_timestamp=300)
        result.append(packet)
    return result


@pytest.mark.usefixtures('native_follower_environment')
@pytest.mark.parametrize('minimum_motion,forward', [(None, 0.), (14., 0.), (14., 18.)])
@pytest.mark.parametrize('phase,sensorless,feedback,ready', [
    (AirframePhase.FIXED_WING, True, False, True), (AirframePhase.FIXED_WING, True, None, False),
    (AirframePhase.FIXED_WING, True, True, False), (AirframePhase.FIXED_WING, False, None, True),
    (AirframePhase.MULTICOPTER, True, None, True)])
async def test_real_vector_initial_settle_and_refresh_forward_paired_feedback(
        tmp_path, monkeypatch, phase, sensorless, feedback, ready, minimum_motion, forward):
    ready = ready and (minimum_motion is None or phase is AirframePhase.MULTICOPTER or forward >= minimum_motion)
    output = tmp_path/'caller'
    observed = packets(sensorless=sensorless, feedback=feedback, binding=AircraftBinding('42', 'sih-caller', 1), phase=phase)
    if forward and phase is AirframePhase.FIXED_WING:
        for packet in observed:
            heading = packet['aircraft_state']['navigation_heading_rad']
            packet['aircraft_state']['velocity_ned_m_s'].update(x=forward*math.cos(heading), y=forward*math.sin(heading))
    clock, index = [100.], [0]
    async def observe():
        value = observed[min(index[0], len(observed)-1)]
        index[0] += 1
        clock[0] = max(clock[0], value['aircraft_state']['observed_at_monotonic_s'])
        return value
    async def sleep(delay): clock[0] += delay
    client = SimpleNamespace(connect=AsyncMock(return_value=NativeCapabilities('test-adapter', 'synthetic', 2,
        True, True, False, True, 23)), bind=AsyncMock(), observe=AsyncMock(side_effect=observe), close=AsyncMock())
    monkeypatch.setattr(tool, 'NativeGuidanceClient', Mock(return_value=client))
    class Recorder:
        def __init__(self, *args): self.frontend = tmp_path/'never-opened.sock'
        async def __aenter__(self): return self
        async def __aexit__(self): pass
    monkeypatch.setattr(tool, 'WireRecorder', Recorder)
    connection = tool.ObservationConnection
    monkeypatch.setattr(tool, 'ObservationConnection', lambda binding: connection(binding, clock=lambda: clock[0]))
    monkeypatch.setattr(tool, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 1000.))
    monkeypatch.setattr(tool, 'asyncio', SimpleNamespace(sleep=sleep, wait_for=asyncio.wait_for))
    refresh = tool.refresh_component_start
    async def refresh_with_clock(*args, **kwargs):
        return await refresh(*args, **kwargs, clock=lambda: clock[0])
    monkeypatch.setattr(tool, 'refresh_component_start', refresh_with_clock)
    monkeypatch.setattr(tool, 'command', lambda *args: '' if 'diff' in args else 'synthetic-revision')
    monkeypatch.setattr(tool, 'native_parameters', lambda *args: 'SYNTHETIC readonly parameter snapshot')
    follower = SimpleNamespace(altitude_limits=AltitudeLimits(5., 120., 2.),
        create_airframe_session=Mock(return_value=SimpleNamespace()))
    monkeypatch.setattr(tool.FollowerFactory, 'create_follower', Mock(return_value=follower))
    monkeypatch.setattr(tool, 'bind_component_fixture', Mock(return_value=object()))
    monkeypatch.setattr(tool, 'project_component_input', Mock(return_value=object()))
    monkeypatch.setattr(tool, 'component_target_evidence', Mock(return_value=SimpleNamespace(
        state=TargetEvidenceState.CONFIRMED, reason_code='synthetic-confirmed')))
    binding = SimpleNamespace(engage=AsyncMock(side_effect=RuntimeError('reached existing engage boundary')),
        owner_confirmed=False, acquire_dispatched=False)
    monkeypatch.setattr(tool, 'NativeFollowBinding', Mock(return_value=binding))
    monkeypatch.setattr(tool, 'attach_component_observer', Mock())
    args = SimpleNamespace(output=output, target_clock=None, scenario=None, config=tool.ROOT/'configs/config_default.yaml',
        follower='gm_velocity_vector', mount='HORIZONTAL', altitude=False, stable_timeout=4., test_altitude=30.,
        initial_phase=phase.value, socket=tmp_path/'never-opened-source.sock', duration=15.,
        expect_handoff=None, altitude_tolerance=2., mc_request=None,
        minimum_forward_ground_speed_m_s=minimum_motion)
    with pytest.raises(RuntimeError if ready else ValueError,
                       match='engage boundary' if ready else 'stable_airborne_window'):
        await tool.run(args, {'aircraft_uid': '42', 'simulator': 'gazebo'})
    assert binding.engage.await_count == (1 if ready else 0)
    assert client.close.await_count == 1
    if ready:
        assert index[0] == 8  # Seven accepted samples and the actual pre-projection refresh.
        assert AircraftState.from_payload(observed[-1]['aircraft_state']).airspeed.valid is not sensorless


@pytest.mark.parametrize('feedback,ready', [(False, True), (None, False), (True, False)])
async def test_post_transition_sensorless_settle_uses_current_packet_feedback(monkeypatch, feedback, ready):
    observed = packets(feedback=feedback)[:7]
    clock, index = [100.], [0]
    async def observe():
        value = observed[min(index[0], 6)];index[0] += 1
        return value
    async def sleep(_delay): clock[0] += .5
    monkeypatch.setattr(tool, 'asyncio', SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(tool, 'observed_pose_record', Mock(return_value=None))
    state = AircraftState.from_payload(observed[0]['aircraft_state'])
    context = acquisition(GuidanceSessionIdentity('caller', state.binding, 1))
    capture = tool.capture_post_transition(SimpleNamespace(observe=AsyncMock(side_effect=observe)),
        tool.PilotTransitionEvent(1., AirframePhase.FIXED_WING), context, log=Mock(), started=90., follow_start=95.,
        timeout_s=4., scenario=SimpleNamespace(target_at=lambda _: (80., 0., -30.)), response=[], clock=lambda: clock[0])
    if ready:
        assert (await capture)['settled']
    else:
        with pytest.raises(TimeoutError, match='settle_timeout'): await capture


async def test_post_transition_waits_for_a_complete_forward_motion_window(monkeypatch):
    # Synthetic telemetry follows the observed accelerating pattern; it is never reported as actual PX4 evidence.
    speeds = [6., 11., 13., 14.3, 15., 15.5, 16., 18., 18., 18.]
    template = packets()[0]
    observed = []
    for index, speed in enumerate(speeds):
        packet = deepcopy(template)
        stamp = 100.+index*.5
        state = AircraftState.from_payload(packet['aircraft_state'])
        state = replace(state, sequence=index+1, observed_at_monotonic_s=stamp, navigation_heading_rad=0.,
            velocity_ned_m_s=replace(state.velocity_ned_m_s, x=speed, y=0.),
            airspeed=replace(state.airspeed, observed_at_monotonic_s=stamp),
            attitude_timing=replace(state.attitude_timing, publication_timestamp_us=int(stamp*1e6),
                sample_timestamp_us=int(stamp*1e6), publication_received_at_monotonic_s=stamp,
                sample_received_at_monotonic_s=stamp))
        packet.update(aircraft_state=asdict(state), attitude_timing=asdict(state.attitude_timing))
        packet['vehicle_pose'].update(observed_at_monotonic_s=stamp, px4_timestamp_us=int(stamp*1e6))
        packet['native_guidance_feedback']['observed_at_monotonic_s'] = stamp
        observed.append(packet)
    clock, count = [100.], [0]
    async def observe():
        value = observed[count[0]]
        count[0] += 1
        clock[0] = value['aircraft_state']['observed_at_monotonic_s']
        return value
    async def sleep(_delay): pass
    monkeypatch.setattr(tool, 'asyncio', SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(tool, 'observed_pose_record', Mock(return_value=None))
    state = AircraftState.from_payload(observed[0]['aircraft_state'])
    context = acquisition(GuidanceSessionIdentity('caller', state.binding, 1))
    result = await tool.capture_post_transition(SimpleNamespace(observe=AsyncMock(side_effect=observe)),
        tool.PilotTransitionEvent(1., AirframePhase.FIXED_WING), context, log=Mock(), started=90., follow_start=95.,
        timeout_s=6., scenario=SimpleNamespace(target_at=lambda _: (80., 0., -30.)), response=[],
        minimum_forward_ground_speed_m_s=14., clock=lambda: clock[0])
    assert result['settled'] and count[0] == 10
    assert all(tool.forward_ground_speed(AircraftState.from_payload(s)) >= 14. for s in result['states'])


@pytest.mark.parametrize('change', [None, 'missing', 'enabled', 'nonbool', 'stale', 'future', 'oldest', 'mode', 'binding', 'reset', 'sample'])
def test_feedback_flag_requires_same_native_state_and_source_receipt(change):
    packet = packets()[-1]
    state = AircraftState.from_payload(packet['aircraft_state'])
    if change == 'missing': packet.pop('native_guidance_feedback')
    elif change == 'enabled': packet['native_guidance_feedback']['airspeed_control_enabled'] = True
    elif change == 'nonbool': packet['native_guidance_feedback']['airspeed_control_enabled'] = 0
    elif change == 'stale': packet['native_guidance_feedback']['observed_at_monotonic_s'] -= 1.
    elif change == 'future': packet['native_guidance_feedback']['observed_at_monotonic_s'] += 1.
    elif change == 'oldest': packet['native_guidance_feedback']['observed_at_monotonic_s'] -= .01
    elif change == 'mode': packet['native_guidance_feedback']['nav_state_timestamp'] += 1
    elif change == 'binding': packet['aircraft_state']['binding']['connection_generation'] += '-wrong'
    elif change == 'reset': packet['aircraft_state']['attitude_timing']['quat_reset_counter'] = 1
    elif change == 'sample': packet['aircraft_state']['attitude_timing']['sample_timestamp_us'] -= 1
    _, flag = tool.stability_sample(state, packet, captured_at=103.1)
    assert flag is (False if change is None else True if change == 'enabled' else None)


@pytest.mark.parametrize('replace_flag', [False, True, None])
async def test_sensorless_duplicate_time_refresh_aligns_feedback_to_replaced_sample(replace_flag):
    observed = packets()
    qualified = [(AircraftState.from_payload(packet['aircraft_state']), False) for packet in observed[:7]]
    states = [sample[0] for sample in qualified]
    clock = [103.]
    connection = tool.ObservationConnection(states[-1].binding, clock=lambda: clock[0])
    assert connection.commit_aircraft_state(states[-1]) and connection.retain_packet(states[-1], observed[6])
    duplicate = deepcopy(observed[6]);duplicate['aircraft_state']['sequence'] += 1
    if replace_flag is None: duplicate.pop('native_guidance_feedback')
    else: duplicate['native_guidance_feedback']['airspeed_control_enabled'] = replace_flag
    complete = deepcopy(observed[7]);complete['aircraft_state']['sequence'] += 1
    replies = [duplicate, complete]
    async def observe():
        packet = replies.pop(0);clock[0] = 103. if replies else 103.1
        return packet
    client = SimpleNamespace(observe=AsyncMock(side_effect=observe))
    refresh = tool.refresh_component_start(client, connection, qualified, runtime_id='test-adapter', expected_altitude_m=30.,
        deadline=104., log=Mock(), started=100., clock=lambda: clock[0])
    if replace_flag is False:
        state = await refresh
        assert state.sequence == complete['aircraft_state']['sequence'] and client.observe.await_count == 2
    else:
        with pytest.raises(ValueError, match='not_stable'): await refresh
        assert client.observe.await_count == 1


def test_feedback_can_be_newer_than_aggregate_state_without_becoming_airspeed():
    packet = packets()[-1]
    state = AircraftState.from_payload(packet['aircraft_state'])
    packet['native_guidance_feedback']['observed_at_monotonic_s'] += .05
    retained, flag = tool.stability_sample(state, packet, captured_at=103.15)
    assert retained is state and flag is False
    assert not state.airspeed.valid and state.airspeed.equivalent_m_s is None


async def test_refresh_cannot_accept_sensorless_history_with_unpaired_feedback():
    observed = packets()
    states = [AircraftState.from_payload(packet['aircraft_state']) for packet in observed[:7]]
    connection = tool.ObservationConnection(states[-1].binding, clock=lambda: 103.1)
    assert connection.commit_aircraft_state(states[-1]) and connection.retain_packet(states[-1], observed[6])
    client = SimpleNamespace(observe=AsyncMock(return_value=observed[7]))
    with pytest.raises(ValueError, match='not_stable'):
        await tool.refresh_component_start(client, connection, [(state, None) for state in states], runtime_id='test-adapter',
            expected_altitude_m=30., deadline=104., log=Mock(), started=100., clock=lambda: 103.1)


@pytest.mark.parametrize('heading', [0., math.pi/2, -math.pi+.01])
@pytest.mark.parametrize('along,across,ready', [(18., 0., True), (14., 30., True),
    (13., 0., False), (0., 30., False), (-18., 0., False)])
def test_declared_forward_motion_uses_observed_navigation_frame(heading, along, across, ready):
    state = AircraftState.from_payload(packets()[-1]['aircraft_state'])
    state = replace(state, navigation_heading_rad=heading, velocity_ned_m_s=replace(state.velocity_ned_m_s,
        x=along*math.cos(heading)-across*math.sin(heading),
        y=along*math.sin(heading)+across*math.cos(heading)))
    assert tool.forward_ground_speed(state) == pytest.approx(along)
    assert tool.forward_motion_ready([state], 14.) is ready
    assert not state.airspeed.valid and state.airspeed.equivalent_m_s is None


@pytest.mark.parametrize('minimum', [True, 0., -1., float('nan'), float('inf')])
def test_motion_threshold_is_a_finite_positive_fixture_condition(minimum):
    with pytest.raises(ValueError, match='motion_threshold_invalid'):
        tool.forward_motion_ready([], minimum)


def test_basic_sensorless_predicate_does_not_satisfy_an_explicit_motion_condition():
    observed = packets()[:7]
    samples = [tool.stability_sample(AircraftState.from_payload(p['aircraft_state']), p,
        captured_at=p['aircraft_state']['observed_at_monotonic_s']) for p in observed]
    assert tool.stable_samples(samples, expected_altitude_m=30.)
    assert not tool.stable_samples(samples, expected_altitude_m=30., minimum_forward_ground_speed_m_s=14.)
    assert not tool.forward_motion_ready([replace(samples[-1][0], phase=AirframePhase.MULTICOPTER)], 14.)


async def test_fresh_start_rechecks_motion_instead_of_reusing_the_old_window():
    observed = packets()
    qualified = []
    for packet in observed[:7]:
        state = AircraftState.from_payload(packet['aircraft_state'])
        state = replace(state, navigation_heading_rad=0., velocity_ned_m_s=replace(state.velocity_ned_m_s, x=18.))
        qualified.append((state, False))
    assert tool.stable_samples(qualified, expected_altitude_m=30., minimum_forward_ground_speed_m_s=14.)
    old_packet = deepcopy(observed[6]);old_packet['aircraft_state'] = asdict(qualified[-1][0])
    connection = tool.ObservationConnection(qualified[-1][0].binding, clock=lambda: 103.1)
    assert connection.commit_aircraft_state(qualified[-1][0]) and connection.retain_packet(qualified[-1][0], old_packet)
    # New actual snapshot is stable but has no forward motion. A previous ready window cannot authorize it.
    client = SimpleNamespace(observe=AsyncMock(return_value=observed[7]), engage=AsyncMock())
    with pytest.raises(ValueError, match='not_stable'):
        await tool.refresh_component_start(client, connection, qualified, runtime_id='test-adapter',
            expected_altitude_m=30., minimum_forward_ground_speed_m_s=14., deadline=104.,
            log=Mock(), started=100., clock=lambda: 103.1)
    client.engage.assert_not_awaited()
