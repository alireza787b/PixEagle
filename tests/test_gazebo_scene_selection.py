"""Synthetic exact-stamp RGB-D fixtures; actual renderer proof is retained separately."""

from dataclasses import replace
import math
import struct
from types import SimpleNamespace

import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.capture_timing import SourceSampleStamp
from classes.gazebo_camera_protocol import GazeboFrameHeader
from tools.gazebo_scene_selection import DepthObservation, SceneSelectionHistory, ObservedCameraPose


@pytest.fixture
def case():
    now = [100.]
    history = SceneSelectionHistory(source_clock_id='clock', image_incarnation='a'*32,
        intrinsics=dict(image_size_px=[4, 4], focal_length_px=[2., 2.], principal_point_px=[2., 2.]),
        max_age_s=1.5, max_depth_bytes=128, clock=lambda: now[0])
    image = GazeboFrameHeader(1, 'a'*32, 'clock', 1, 'world', '/camera/image', 1_000_000,
                              100., 4, 4, 12, 'RGB_INT8', 48)
    depth = DepthObservation(1_000_000, 100., 4, 4, 16, struct.pack('<16f', *([9.]*16)))
    pose = ObservedCameraPose(1_000_000, 100., Vector3(1., 2., -3.), Quaternion(1., 0., 0., 0.))
    stamp = SourceSampleStamp('clock', 'a'*32, 1, 1_000_000, 'gazebo_sim_us')
    history.image(image); history.depth(depth); history.pose(pose)
    return SimpleNamespace(now=now, history=history, image=image, depth=depth, pose=pose, stamp=stamp)


def test_center_and_offaxis_points_use_forward_depth_not_radial_range(case):
    assert case.history.select(case.stamp, .5, .5).position_ned == Vector3(10., 2., -3.)
    selected = case.history.select(case.stamp, .75, .75)
    assert selected.position_ned == Vector3(10., 6.5, 1.5)
    assert selected.depth_forward_m == 9. and selected.pixel_xy == (3, 3)
    assert case.history.select(case.stamp, 1., 1.) == selected


def test_world_point_uses_the_original_camera_quaternion_once(case):
    history = SceneSelectionHistory(source_clock_id='clock', image_incarnation='a'*32,
        intrinsics=dict(image_size_px=[4, 4], focal_length_px=[2., 2.], principal_point_px=[2., 2.]),
        max_age_s=1.5, clock=lambda: case.now[0])
    history.image(case.image); history.depth(case.depth)
    history.pose(replace(case.pose, camera_to_ned=Quaternion.from_euler(0., 0., math.pi/2)))
    result = history.select(case.stamp, .5, .5)
    assert (result.position_ned.x, result.position_ned.y, result.position_ned.z) == pytest.approx((1., 11., -3.))


@pytest.mark.parametrize('missing', ['image', 'depth', 'pose'])
def test_nearby_frame_is_not_a_substitute_for_exact_camera_image_pose_pair(case, missing):
    getattr(case.history, '_' + ('images' if missing == 'image' else 'poses' if missing == 'pose' else 'depth')).clear()
    with pytest.raises(ValueError, match='expired_or_unpaired'):
        case.history.select(case.stamp, .5, .5)


@pytest.mark.parametrize('changes', [dict(clock_id='other'), dict(source_incarnation='b'*32),
    dict(sequence=2), dict(timestamp_us=1_000_001), dict(time_basis='receipt_time')])
def test_obsolete_or_wrong_frame_identity_cannot_select(case, changes):
    with pytest.raises(ValueError):
        case.history.select(replace(case.stamp, **changes), .5, .5)


@pytest.mark.parametrize('value', [float('inf'), float('nan'), 0., -1.])
def test_sky_or_missing_depth_is_not_invented_as_a_finite_target(case, value):
    case.history._depth.clear()
    case.history._progress.pop('depth')
    case.history.depth(replace(case.depth, pixels=struct.pack('<16f', *([value]*16))))
    with pytest.raises(ValueError, match='point_unavailable'):
        case.history.select(case.stamp, .5, .5)


def test_paused_repeated_samples_do_not_refresh_receipt_or_expiry(case):
    case.now[0] += 1.
    assert not case.history.depth(replace(case.depth, received_at_monotonic_s=101.))
    assert not case.history.pose(replace(case.pose, received_at_monotonic_s=101.))
    assert not case.history.image(replace(case.image, received_at_monotonic_s=101.))
    case.now[0] = 101.51
    with pytest.raises(ValueError, match='expired_or_unpaired'):
        case.history.select(case.stamp, .5, .5)


def test_depth_memory_stays_bounded_and_progress_survives_eviction(case):
    for sequence in range(2, 6):
        case.now[0] += .1
        case.history.depth(replace(case.depth, timestamp_us=sequence*1_000_000,
                                   received_at_monotonic_s=case.now[0]))
    assert case.history.diagnostics()['depth_bytes'] <= 128
    assert case.history.diagnostics()['depth_frames'] == 2
    with pytest.raises(ValueError, match='reordered'):
        case.history.depth(case.depth)


def test_rewritten_depth_geometry_or_source_image_time_is_rejected(case):
    with pytest.raises(ValueError, match='rewritten'):
        case.history.depth(replace(case.depth, pixels=struct.pack('<16f', *([8.]*16))))
    with pytest.raises(ValueError, match='clock_reordered'):
        case.history.image(replace(case.image, frame_id=2, header_simtime_us=999_999))


def test_future_receipts_cannot_become_live_scene_evidence(case):
    with pytest.raises(ValueError, match='future_receipt'):
        case.history.pose(replace(case.pose, timestamp_us=2_000_000, received_at_monotonic_s=101.))
