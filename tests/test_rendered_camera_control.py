"""Private normalized camera adapter, exact-frame lookup and shared ownership."""

from contextlib import contextmanager
from dataclasses import replace
import json
import socket
import struct
import threading
import time
from types import SimpleNamespace

import pytest

from classes.aircraft_state import AirframePhase, Quaternion, Vector3
from classes.capture_timing import SourceSampleStamp
from classes.gazebo_camera_control import RenderedCameraControl, exchange
from classes.gazebo_camera_protocol import GazeboFrameHeader
from classes.gazebo_gimbal_source import GazeboGimbalSettings, GazeboSipGimbalProvider
from classes.gimbal_types import TrackingState
from tools.gazebo_gimbal_model import IdealGimbalSettings, IdealStabilizedGimbal, ObservedGimbalPose, forward_horizon
from tools.gazebo_rendered_control import RenderedSceneControl, serve_controls
from tools.gazebo_scene_selection import DepthObservation, SceneSelectionHistory, ObservedCameraPose


@pytest.fixture
def scene(tmp_path):
    tmp_path.chmod(0o700)
    now = [100.]
    pose = ObservedGimbalPose(1_000_000, 100., Vector3(0., 0., -20.), Quaternion(1., 0., 0., 0.),
                             Vector3(0., 0., -20.), Quaternion(1., 0., 0., 0.))
    model = IdealStabilizedGimbal(IdealGimbalSettings())
    model.observe(pose)
    source = SimpleNamespace(private=tmp_path, incarnation='b'*32, condition=threading.Condition(),
        model=model, latest_pose=pose, stopped=False, error=None, clock=lambda: now[0])
    source.home_view = lambda pose: model.aim(*forward_horizon(pose, AirframePhase.MULTICOPTER, is_tailsitter=False))
    history = SceneSelectionHistory(source_clock_id='clock', image_incarnation='a'*32,
        intrinsics=dict(image_size_px=[4, 4], focal_length_px=[2., 2.], principal_point_px=[2., 2.]),
        max_age_s=1.5, clock=lambda: now[0])
    history.image(GazeboFrameHeader(1, 'a'*32, 'clock', 1, 'world', '/image', 1_000_000,
        100., 4, 4, 12, 'RGB_INT8', 48))
    history.depth(DepthObservation(1_000_000, 100., 4, 4, 16, struct.pack('<16f', *([9.]*16))))
    history.pose(ObservedCameraPose(pose.timestamp_us, pose.received_at_monotonic_s,
        pose.camera_position_ned, pose.camera_to_ned))
    owner = RenderedSceneControl(source, history)
    ready = threading.Event()
    worker = threading.Thread(target=serve_controls, args=(owner, ready), daemon=True)
    worker.start()
    assert ready.wait(1.)
    provider = GazeboSipGimbalProvider(GazeboGimbalSettings(str(tmp_path / 'gimbal.sock'),
        'clock', 'world', .05, 'rendered_scene_v1'), control_enabled=True)
    provider.running = True
    provider._previous_packet = SimpleNamespace(source_sample=SourceSampleStamp(
        'clock', source.incarnation, 1, 1_000_000, 'gazebo_sim_us'))
    stamp = SourceSampleStamp('clock', 'a'*32, 1, 1_000_000, 'gazebo_sim_us')
    yield SimpleNamespace(source=source, owner=owner, provider=provider,
                          control=provider.manual_control, stamp=stamp, now=now)
    source.stopped = True
    worker.join(timeout=1.)
    assert not worker.is_alive()


async def prepared(scene, x=.75, y=.75):
    return await scene.control.resolve_selection(scene.control.prepare_selection_from_frame(
        x=x, y=y, source_sample=scene.stamp))


async def test_resolve_is_read_only_and_commit_requires_fresh_observed_centering(scene):
    pending = await prepared(scene)
    assert scene.source.model.target_ned is None
    result = await scene.control.execute('select', prepared_selection=pending)
    assert result['success']
    assert scene.source.model.target_ned == Vector3(9., 4.5, -15.5)
    assert scene.source.model.tracking_state is TrackingState.TARGET_SELECTION
    pose = scene.source.latest_pose
    command = scene.source.model.observe(replace(pose, timestamp_us=1_100_000, received_at_monotonic_s=100.1))
    assert scene.source.model.tracking_state is TrackingState.TARGET_SELECTION
    scene.source.model.observe(replace(pose, timestamp_us=1_200_000, received_at_monotonic_s=100.2,
                                      camera_to_ned=command.camera_to_ned))
    # The limited first step may not yet be centered; an ACK never establishes lock.
    assert scene.source.model.tracking_state in (TrackingState.TARGET_SELECTION, TrackingState.TRACKING_ACTIVE)


@pytest.mark.parametrize('change', ['stop', 'other_owner', 'expired', 'camera_restart'])
async def test_obsolete_prepared_click_preserves_existing_target(scene, change):
    pending = await prepared(scene)
    original = Vector3(30., 2., -3.)
    scene.source.model.lock_point(original)
    if change == 'stop':
        assert scene.control.stop()
    elif change == 'other_owner':
        scene.owner.changed()
    elif change == 'expired':
        scene.now[0] += 1.6
        scene.source.latest_pose = replace(scene.source.latest_pose, received_at_monotonic_s=scene.now[0])
    else:
        scene.source.incarnation = 'c'*32
    with pytest.raises((ValueError, RuntimeError)):
        await scene.control.execute('select', prepared_selection=pending)
    assert scene.source.model.target_ned is original


async def test_selection_guard_is_rechecked_after_read_only_resolution(scene):
    pending = await prepared(scene)
    @contextmanager
    def revoked():
        raise ValueError('source context changed')
        yield
    with pytest.raises(ValueError, match='context changed'):
        await scene.control.execute('select', prepared_selection=pending, selection_guard=revoked)
    assert scene.source.model.target_ned is None


async def test_consumed_selection_is_never_replayed(scene):
    pending = await prepared(scene)
    await scene.control.execute('select', prepared_selection=pending)
    with pytest.raises(ValueError, match='obsolete'):
        await scene.control.execute('select', prepared_selection=pending)


@pytest.mark.parametrize('sample', [None, SourceSampleStamp('other', 'a'*32, 1, 1_000_000, 'gazebo_sim_us')])
async def test_wrong_or_missing_displayed_frame_is_not_latest_pose_selection(scene, sample):
    with pytest.raises(ValueError):
        pending = scene.control.prepare_selection_from_frame(x=.5, y=.5, source_sample=sample)
        await scene.control.resolve_selection(pending)
    assert scene.source.model.target_ned is None


async def test_manual_controls_share_cancel_stop_and_supported_capabilities(scene):
    assert isinstance(scene.control, RenderedCameraControl)
    assert not {'roll', 'zoom'} & set(scene.control.capabilities)
    assert scene.provider.selection_modes() == [dict(id='classic', label='Camera Classic', point=True, rectangle=True)]
    scene.source.model.lock_point(Vector3(30., 1., -2.))
    @contextmanager
    def admitted():
        yield
    await scene.control.prepare_manual(admitted)
    assert scene.source.model.target_ned is None
    scene.control.send_manual_intent('pan', .5)
    assert scene.source.model._manual == ('pan', 15.)
    assert scene.control.stop()
    assert scene.source.model._manual is None


def test_source_does_not_expose_aircraft_actions_or_unbounded_requests(scene):
    for operation in ('follow_start', 'aircraft_arm', 'set_pose', 'roll'):
        with pytest.raises(ValueError, match='unsupported'):
            exchange(scene.source.private / 'control.sock', scene.source.incarnation, operation, {})
    with pytest.raises(ValueError, match='too_large'):
        exchange(scene.source.private / 'control.sock', scene.source.incarnation, 'select', dict(token='x'*20_000))


def test_bad_packet_cannot_replace_a_target_or_kill_camera_owner(scene):
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
        connection.connect(str(scene.source.private / 'control.sock'))
        connection.sendall(b'[1]')
        assert json.loads(connection.recv(4096))['success'] is False
    assert scene.source.model.target_ned is None
    assert scene.control.stop()


async def test_rectangle_and_point_designate_same_scene_center(scene):
    rectangle = scene.control.prepare_selection_from_frame(x=.5, y=.5, width=.2, height=.2,
        source_sample=scene.stamp)
    resolved = await scene.control.resolve_selection(rectangle)
    await scene.control.execute('select', prepared_selection=resolved)
    assert scene.source.model.target_ned == Vector3(9., 0., -20.)


@pytest.mark.parametrize('extent', [(.8, .2), (None, .2), (.2, float('nan')), (0., .2), (True, .2)])
def test_invalid_region_cannot_change_existing_target(scene, extent):
    original = Vector3(30., 1., -2.)
    scene.source.model.lock_point(original)
    with pytest.raises(ValueError):
        scene.control.prepare_selection_from_frame(x=.25, y=.5, width=extent[0], height=extent[1],
            source_sample=scene.stamp)
    assert scene.source.model.target_ned is original


async def test_home_levels_body_forward_heading_instead_of_previous_camera_pan(scene):
    body = Quaternion.from_euler(.1, -.3, 1.)
    pose = replace(scene.source.latest_pose, body_to_ned=body)
    scene.source.latest_pose = pose
    await scene.control.execute('home')
    ray = body.rotate(Vector3(1., 0., 0.))
    ray = Vector3(ray.x, ray.y, 0.).normalized()
    aim = scene.source.model._aim
    assert (aim.x, aim.y, aim.z) == pytest.approx((ray.x, ray.y, ray.z))
    assert scene.source.model.target_ned is None


async def test_finite_step_releases_camera_lock_and_stops_after_pulse(scene):
    scene.source.model.lock_point(Vector3(30., 2., -10.))
    result = await scene.control.execute('tilt', direction=-1, speed_deg_s=10, duration_ms=100)
    assert result['success']
    assert scene.source.model.target_ned is None and scene.source.model._manual is None


@pytest.mark.parametrize('operation', ['home', 'pan'])
async def test_obsolete_manual_guard_prevents_last_device_write(scene, operation):
    original = Vector3(30., 2., -10.)
    scene.source.model.lock_point(original)
    @contextmanager
    def revoked():
        raise ValueError('gesture retired')
        yield
    with pytest.raises(ValueError, match='gesture retired'):
        await scene.control.execute(operation, direction=1 if operation=='pan' else None,
                                    selection_guard=revoked)
    assert scene.source.model.target_ned is original
    assert scene.source.model._manual is None
