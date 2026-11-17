"""Bounded rendered-scene truth for frame-bound simulated target designation.

Depth is simulator-only truth, never an aircraft range estimator. Only exact
RGB/depth/observed-pose timestamps may supply a selected world point.
"""

from collections import OrderedDict
from dataclasses import dataclass, replace
import math
import struct
import sys
import threading
import time

from classes.aircraft_state import Quaternion, Vector3, finite_number
from classes.capture_timing import SourceSampleStamp
from classes.gazebo_camera_protocol import GazeboFrameHeader, MAX_FRAME_BYTES


@dataclass(frozen=True)
class ObservedCameraPose:
    timestamp_us: int
    received_at_monotonic_s: float
    camera_position_ned: Vector3
    camera_to_ned: Quaternion

    def __post_init__(self):
        if (type(self.timestamp_us) is not int or not 0 <= self.timestamp_us < 2**64
                or finite_number(self.received_at_monotonic_s, 'camera_pose_receipt') < 0
                or not isinstance(self.camera_position_ned, Vector3) or not isinstance(self.camera_to_ned, Quaternion)):
            raise ValueError('scene_camera_pose_invalid')


@dataclass(frozen=True)
class DepthObservation:
    timestamp_us: int
    received_at_monotonic_s: float
    width: int
    height: int
    stride: int
    pixels: bytes

    def __post_init__(self):
        if (type(self.timestamp_us) is not int or not 0 <= self.timestamp_us < 2**64
                or any(type(v) is not int or v < 1 for v in (self.width, self.height, self.stride))
                or self.stride < self.width * 4 or not isinstance(self.pixels, bytes)
                or len(self.pixels) != self.height * self.stride or len(self.pixels) > MAX_FRAME_BYTES):
            raise ValueError('scene_depth_geometry_invalid')
        if finite_number(self.received_at_monotonic_s, 'scene_depth_receipt') < 0:
            raise ValueError('scene_depth_receipt_invalid')

    @classmethod
    def from_message(cls, message, *, received_at_monotonic_s):
        values = message.DESCRIPTOR.fields_by_name['pixel_format_type'].enum_type.values_by_name
        stamp = message.header.stamp
        if (sys.byteorder != 'little' or message.pixel_format_type != values['R_FLOAT32'].number
                or stamp.sec < 0 or not 0 <= stamp.nsec < 1_000_000_000):
            raise ValueError('scene_depth_format_unqualified')
        return cls(stamp.sec * 1_000_000 + stamp.nsec // 1000, received_at_monotonic_s,
                   message.width, message.height, message.step, message.data)


@dataclass(frozen=True)
class ScenePoint:
    source_sample: SourceSampleStamp
    position_ned: Vector3
    depth_forward_m: float
    pixel_xy: tuple[int, int]


class SceneSelectionHistory:
    def __init__(self, *, source_clock_id, image_incarnation, intrinsics, max_age_s,
                 max_depth_bytes=256 * 1024 * 1024, max_frames=90, max_poses=512, clock=time.monotonic):
        if (not isinstance(source_clock_id, str) or not source_clock_id or not isinstance(image_incarnation, str)
                or not image_incarnation or finite_number(max_age_s, 'scene_history_age') <= 0
                or any(type(v) is not int or v < 1 for v in (max_depth_bytes, max_frames, max_poses))):
            raise ValueError('scene_selection_configuration_invalid')
        width, height = intrinsics['image_size_px']
        fx, fy = intrinsics['focal_length_px']
        cx, cy = intrinsics['principal_point_px']
        if (any(type(v) is not int or v < 1 for v in (width, height))
                or any(finite_number(v, 'scene_focal_length') <= 0 for v in (fx, fy))
                or any(not 0 <= finite_number(v, 'scene_principal_point') <= limit
                       for v, limit in ((cx, width), (cy, height)))):
            raise ValueError('scene_selection_intrinsics_invalid')
        self.source_clock_id, self.image_incarnation = source_clock_id, image_incarnation
        self.width, self.height, self.fx, self.fy, self.cx, self.cy = width, height, fx, fy, cx, cy
        self.max_age_s, self.clock = max_age_s, clock
        self.max_depth_bytes, self.max_frames, self.max_poses = max_depth_bytes, max_frames, max_poses
        self._lock = threading.RLock()
        self._images, self._depth, self._poses = OrderedDict(), OrderedDict(), OrderedDict()
        self._depth_bytes = 0
        self._progress = {}
        self._last_image_time = None

    def _prune(self):
        now = self.clock()
        for records, limit in ((self._images, self.max_frames), (self._depth, self.max_frames), (self._poses, self.max_poses)):
            while records:
                value = next(iter(records.values()))
                if (len(records) <= limit and 0 <= now - value.received_at_monotonic_s <= self.max_age_s
                        and (records is not self._depth or self._depth_bytes <= self.max_depth_bytes)):
                    break
                _, removed = records.popitem(last=False)
                if records is self._depth:
                    self._depth_bytes -= len(removed.pixels)

    def _commit(self, records, key, value, *, kind):
        with self._lock:
            if value.received_at_monotonic_s > self.clock():
                raise ValueError('scene_source_future_receipt')
            last = self._progress.get(kind)
            if last is not None and key == last:
                original = records.get(key)
                if original is not None and replace(value,
                        received_at_monotonic_s=original.received_at_monotonic_s) != original:
                    raise ValueError('scene_source_sample_rewritten')
                return False
            if last is not None and key < last:
                raise ValueError('scene_source_sample_reordered')
            records[key] = value
            self._progress[kind] = key
            if records is self._depth:
                self._depth_bytes += len(value.pixels)
            self._prune()
            return True

    def image(self, header):
        if (not isinstance(header, GazeboFrameHeader) or header.source_clock_id != self.source_clock_id
                or header.provider_incarnation != self.image_incarnation
                or (header.width, header.height) != (self.width, self.height)):
            raise ValueError('scene_image_identity_changed')
        with self._lock:
            previous = self._progress.get('image')
            if previous is not None and header.frame_id > previous and header.header_simtime_us <= self._last_image_time:
                raise ValueError('scene_image_clock_reordered')
            committed = self._commit(self._images, header.frame_id, header, kind='image')
            if committed:
                self._last_image_time = header.header_simtime_us
            return committed

    def depth(self, sample):
        if (not isinstance(sample, DepthObservation)
                or (sample.width, sample.height) != (self.width, self.height)):
            raise ValueError('scene_depth_geometry_changed')
        return self._commit(self._depth, sample.timestamp_us, sample, kind='depth')

    def pose(self, sample):
        if not isinstance(sample, ObservedCameraPose):
            raise ValueError('scene_pose_invalid')
        return self._commit(self._poses, sample.timestamp_us, sample, kind='pose')

    def select(self, sample, x, y):
        if (not isinstance(sample, SourceSampleStamp) or sample.clock_id != self.source_clock_id
                or sample.source_incarnation != self.image_incarnation or sample.time_basis != 'gazebo_sim_us'):
            raise ValueError('scene_frame_identity_changed')
        x, y = finite_number(x, 'scene_selection_x'), finite_number(y, 'scene_selection_y')
        if not 0 <= x <= 1 or not 0 <= y <= 1:
            raise ValueError('scene_selection_outside_image')
        with self._lock:
            self._prune()
            image = self._images.get(sample.sequence)
            depth = self._depth.get(sample.timestamp_us)
            pose = self._poses.get(sample.timestamp_us)
            if image is None or depth is None or pose is None:
                raise ValueError('scene_frame_expired_or_unpaired')
            if image.header_simtime_us != sample.timestamp_us:
                raise ValueError('scene_frame_identity_changed')
            u, v = min(self.width - 1, int(x * self.width)), min(self.height - 1, int(y * self.height))
            distance = struct.unpack_from('<f', depth.pixels, v * depth.stride + u * 4)[0]
            if not math.isfinite(distance) or distance <= 0:
                raise ValueError('scene_point_unavailable')
            # Gazebo's qualified R_FLOAT32 depth is forward-axis distance, not
            # radial range. Native camera FRD uses right/down image directions.
            camera_ray = Vector3(distance, (u-self.cx) * distance / self.fx, (v-self.cy) * distance / self.fy)
            ray = pose.camera_to_ned.rotate(camera_ray)
            p = pose.camera_position_ned
            return ScenePoint(sample, Vector3(p.x + ray.x, p.y + ray.y, p.z + ray.z), distance, (u, v))

    def diagnostics(self):
        with self._lock:
            self._prune()
            return dict(images=len(self._images), depth_frames=len(self._depth), poses=len(self._poses),
                        depth_bytes=self._depth_bytes, maximum_depth_bytes=self.max_depth_bytes)
