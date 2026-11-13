"""Bounded actual-image envelope shared by the isolated Gazebo provider and reader.

Simulator sample time and host receipt are deliberately separate. This protocol
does not establish an aircraft clock mapping or grant command authority.
"""

from dataclasses import asdict, dataclass
import json
import math
import re
import struct


MAX_HEADER_BYTES = 4096
MAX_FRAME_BYTES = 32 * 1024 * 1024


def _text(value, name, *, maximum=256):
    if (not isinstance(value, str) or not value or value.strip() != value
            or len(value) > maximum or any(ord(char) < 32 for char in value)):
        raise ValueError(f"gazebo_camera_{name}_invalid")


@dataclass(frozen=True)
class GazeboFrameHeader:
    schema_version: int
    provider_incarnation: str
    source_clock_id: str
    frame_id: int
    world: str
    image_topic: str
    header_simtime_us: int
    received_at_monotonic_s: float
    width: int
    height: int
    stride: int
    pixel_format: str
    payload_length: int
    source_frame_id: str | None = None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("gazebo_camera_schema_unsupported")
        if (not isinstance(self.provider_incarnation, str)
                or re.fullmatch(r"[0-9a-f]{32}", self.provider_incarnation) is None):
            raise ValueError("gazebo_camera_incarnation_invalid")
        for field in ("source_clock_id", "world", "image_topic"):
            _text(getattr(self, field), field)
        if not self.image_topic.startswith("/"):
            raise ValueError("gazebo_camera_topic_invalid")
        if self.source_frame_id is not None:
            _text(self.source_frame_id, "source_frame_id")
        for name in ("frame_id", "header_simtime_us", "width", "height", "stride", "payload_length"):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name == "header_simtime_us" else 1):
                raise ValueError(f"gazebo_camera_{name}_invalid")
        if (self.pixel_format != "RGB_INT8" or self.stride < self.width * 3
                or self.payload_length != self.stride * self.height
                or self.payload_length > MAX_FRAME_BYTES):
            raise ValueError("gazebo_camera_payload_geometry_invalid")
        receipt = self.received_at_monotonic_s
        if (type(receipt) not in (int, float) or not math.isfinite(receipt) or receipt < 0):
            raise ValueError("gazebo_camera_receipt_invalid")

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("gazebo_camera_header_invalid")
        try:
            return cls(**payload)
        except TypeError as error:
            raise ValueError("gazebo_camera_header_fields_invalid") from error

    def payload(self):
        values = asdict(self)
        if self.source_frame_id is None:
            values.pop("source_frame_id")
        return values


def pack_header(header: GazeboFrameHeader) -> bytes:
    if not isinstance(header, GazeboFrameHeader):
        raise ValueError("gazebo_camera_header_invalid")
    encoded = json.dumps(header.payload(), separators=(",", ":"), allow_nan=False).encode("utf-8")
    if not 1 <= len(encoded) <= MAX_HEADER_BYTES:
        raise ValueError("gazebo_camera_header_size_invalid")
    return struct.pack("!I", len(encoded)) + encoded


def read_header_length(prefix: bytes) -> int:
    if not isinstance(prefix, bytes) or len(prefix) != 4:
        raise ValueError("gazebo_camera_header_prefix_invalid")
    length = struct.unpack("!I", prefix)[0]
    if not 1 <= length <= MAX_HEADER_BYTES:
        raise ValueError("gazebo_camera_header_size_invalid")
    return length
