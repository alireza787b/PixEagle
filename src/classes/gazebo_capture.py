"""Optional, read-only capture of actual stamped Gazebo images over a private UDS.

The normal capture worker owns reads. No simulator bindings, aircraft commands,
pose invention or second image-processing pipeline live in this module.
"""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import socket
import struct
import time

import cv2
import numpy as np

from classes.capture_timing import SourceSampleStamp
from classes.gazebo_camera_protocol import GazeboFrameHeader, read_header_length


@dataclass(frozen=True)
class GazeboCameraSettings:
    socket_path: str
    source_clock_id: str
    world: str
    image_topic: str
    max_attitude_skew_s: float

    def __post_init__(self):
        if (not isinstance(self.socket_path, str) or not Path(self.socket_path).is_absolute()
                or "\x00" in self.socket_path or len(os.fsencode(self.socket_path)) > 107):
            raise ValueError("gazebo_camera_socket_invalid")
        for name in ("source_clock_id", "world", "image_topic"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value.strip() != value or len(value) > 256:
                raise ValueError("gazebo_camera_source_identity_invalid")
        if not self.image_topic.startswith("/"):
            raise ValueError("gazebo_camera_topic_invalid")
        if (isinstance(self.max_attitude_skew_s, bool) or not isinstance(self.max_attitude_skew_s, (int, float))
                or not math.isfinite(self.max_attitude_skew_s) or self.max_attitude_skew_s <= 0):
            raise ValueError("gazebo_camera_skew_invalid")

    @classmethod
    def from_mapping(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("gazebo_camera_configuration_invalid")
        return cls(**value)


@dataclass(frozen=True)
class GazeboCapturedImage:
    frame: np.ndarray
    received_at_monotonic_s: float
    source_sample: SourceSampleStamp


class GazeboCapture:
    def __init__(self, settings: GazeboCameraSettings, *, clock=time.monotonic):
        self.settings = settings
        self.clock = clock
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.settimeout(.25)
        self._opened = False
        self._header = None
        try:
            self._socket.connect(settings.socket_path)
            _, uid, _ = struct.unpack("3i", self._socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise ValueError("gazebo_camera_peer_uid_mismatch")
            self._opened = True
        except BaseException:
            self.release()
            raise

    def isOpened(self):
        return self._opened

    def release(self):
        self._opened = False
        self._socket.close()

    def get(self, property_id):
        if self._header is None:
            return 0.
        return float({cv2.CAP_PROP_FRAME_WIDTH: self._header.width,
                      cv2.CAP_PROP_FRAME_HEIGHT: self._header.height}.get(property_id, 0.))

    def set(self, *_):
        return False

    def _exact(self, count, *, idle_allowed=False):
        data = bytearray()
        deadline = self.clock() + 1.
        while len(data) < count:
            if self.clock() > deadline:
                raise TimeoutError("gazebo_camera_partial_frame_stalled")
            try:
                part = self._socket.recv(min(count - len(data), 1024 * 1024))
            except socket.timeout:
                if not data and idle_allowed:
                    return None
                raise
            if not part:
                raise ConnectionError("gazebo_camera_provider_disconnected")
            data.extend(part)
        return bytes(data)

    def read_sample(self):
        if not self._opened:
            return None
        try:
            prefix = self._exact(4, idle_allowed=True)
            if prefix is None:
                return None
            encoded = self._exact(read_header_length(prefix))
            header = GazeboFrameHeader.from_payload(json.loads(encoded))
            if ((header.source_clock_id, header.world, header.image_topic)
                    != (self.settings.source_clock_id, self.settings.world, self.settings.image_topic)):
                raise ValueError("gazebo_camera_source_changed")
            if header.received_at_monotonic_s > self.clock():
                raise ValueError("gazebo_camera_future_receipt")
            old = self._header
            if old is not None and (header.provider_incarnation != old.provider_incarnation
                    or header.frame_id <= old.frame_id or header.header_simtime_us <= old.header_simtime_us
                    or header.received_at_monotonic_s <= old.received_at_monotonic_s
                    or (header.width, header.height, header.stride) != (old.width, old.height, old.stride)):
                raise ValueError("gazebo_camera_source_progress_invalid")
            pixels = self._exact(header.payload_length)
            rgb = np.frombuffer(pixels, dtype=np.uint8).reshape(header.height, header.stride)
            rgb = rgb[:, :header.width * 3].reshape(header.height, header.width, 3)
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            self._header = header
            source = SourceSampleStamp(header.source_clock_id, header.provider_incarnation,
                header.frame_id, header.header_simtime_us, "gazebo_sim_us")
            return GazeboCapturedImage(frame, header.received_at_monotonic_s, source)
        except (OSError, ValueError, ConnectionError, TimeoutError):
            self.release()
            raise
