"""Private, source-stamped SIP input for isolated Gazebo training only.

The SIP parser remains authoritative. This envelope adds simulator provenance;
it does not infer hardware timing, target identity or motor mechanics.
"""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import socket
import struct
import time

from classes.capture_timing import SourceSampleStamp
from classes.gimbal_interface import GimbalSourceError, ReceivedGimbalPacket
from classes.gimbal_provider import SipUdpGimbalProvider


@dataclass(frozen=True)
class GazeboGimbalSettings:
    socket_path: str
    source_clock_id: str
    world: str
    max_attitude_skew_s: float

    def __post_init__(self):
        if (not isinstance(self.socket_path, str) or not Path(self.socket_path).is_absolute()
                or '\x00' in self.socket_path or len(os.fsencode(self.socket_path)) > 107):
            raise ValueError('gazebo_gimbal_socket_invalid')
        for value in (self.source_clock_id, self.world):
            if not isinstance(value, str) or not value or value.strip() != value or len(value) > 256:
                raise ValueError('gazebo_gimbal_source_identity_invalid')
        if (type(self.max_attitude_skew_s) not in (float, int)
                or not math.isfinite(self.max_attitude_skew_s) or self.max_attitude_skew_s <= 0):
            raise ValueError('gazebo_gimbal_skew_invalid')

    @classmethod
    def from_mapping(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError('gazebo_gimbal_configuration_invalid')
        return cls(**value)


@dataclass(frozen=True)
class GazeboGimbalPacket:
    world: str
    source_sample: SourceSampleStamp
    received_at_monotonic_s: float
    sip_frame: str

    def __post_init__(self):
        if not isinstance(self.world, str) or not self.world or self.world.strip() != self.world:
            raise ValueError('gazebo_gimbal_world_invalid')
        if not isinstance(self.source_sample, SourceSampleStamp) or self.source_sample.time_basis != 'gazebo_sim_us':
            raise ValueError('gazebo_gimbal_clock_invalid')
        if (type(self.received_at_monotonic_s) not in (int, float)
                or not math.isfinite(self.received_at_monotonic_s) or self.received_at_monotonic_s < 0):
            raise ValueError('gazebo_gimbal_receipt_invalid')
        if (not isinstance(self.sip_frame, str) or len(self.sip_frame) not in (14, 24)
                or not self.sip_frame.isascii() or self.sip_frame[7:10] not in ('GAC', 'TRC')):
            raise ValueError('gazebo_gimbal_packet_invalid')

    def encode(self):
        return json.dumps(asdict(self), separators=(',', ':'), allow_nan=False).encode('ascii')

    @classmethod
    def decode(cls, data):
        if not isinstance(data, bytes) or not 1 <= len(data) <= 4096:
            raise ValueError('gazebo_gimbal_envelope_invalid')
        value = json.loads(data)
        if (not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__)
                or not isinstance(value.get('source_sample'), dict)
                or set(value['source_sample']) != set(SourceSampleStamp.__dataclass_fields__)):
            raise ValueError('gazebo_gimbal_envelope_invalid')
        value['source_sample'] = SourceSampleStamp(**value['source_sample'])
        return cls(**value)


def validate_gazebo_gimbal_config(config):
    """One semantic validation used by startup, preview/apply and construction."""
    value = config.get('GAZEBO_INPUT')
    if value is None:
        return None
    if config.get('CONTROL_ENABLED', False) is not False:
        raise ValueError('gazebo_gimbal_controls_unsupported')
    from classes.gimbal_provider import canonicalize_gimbal_provider, TOPOTEK_SIP_UDP_PROVIDER
    if canonicalize_gimbal_provider(config.get('PROVIDER')) != TOPOTEK_SIP_UDP_PROVIDER:
        raise ValueError('gazebo_gimbal_protocol_unsupported')
    return GazeboGimbalSettings.from_mapping(value)


class GazeboSipGimbalProvider(SipUdpGimbalProvider):
    """Reuse SIP parsing, caches and runtime ownership over a private local pipe."""

    requires_queries = False

    def __init__(self, settings, **kwargs):
        if not isinstance(settings, GazeboGimbalSettings):
            raise ValueError('gazebo_gimbal_configuration_invalid')
        super().__init__(gimbal_ip='127.0.0.1', control_enabled=False, **kwargs)
        self.settings = settings
        self._previous_packet = None
        self._family_samples = {}

    def _init_listening_socket(self):
        self._previous_packet = None
        self._family_samples.clear()
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            stream.settimeout(self.SOCKET_TIMEOUT)
            stream.connect(self.settings.socket_path)
            _, uid, _ = struct.unpack('3i', stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise ValueError('gazebo_gimbal_peer_uid_mismatch')
            self.listen_socket = stream
            return True
        except BaseException:
            stream.close()
            raise

    def _send_command(self, command):
        return False  # This source has no camera command or aircraft-control route.

    def _receive_packet(self):
        try:
            data, _, flags, _ = self.listen_socket.recvmsg(4096)
            if not data or flags & socket.MSG_TRUNC:
                raise ValueError('gazebo_gimbal_source_disconnected_or_truncated')
            packet = GazeboGimbalPacket.decode(data)
            sample = packet.source_sample
            if (packet.world != self.settings.world or sample.clock_id != self.settings.source_clock_id
                    or packet.received_at_monotonic_s > time.monotonic()):
                raise ValueError('gazebo_gimbal_source_changed_or_future')
            previous = self._previous_packet
            if previous is not None:
                old = previous.source_sample
                if (sample.source_incarnation != old.source_incarnation or sample.sequence <= old.sequence
                        or sample.timestamp_us < old.timestamp_us
                        or packet.received_at_monotonic_s < previous.received_at_monotonic_s):
                    raise ValueError('gazebo_gimbal_source_progress_invalid')
            family = packet.sip_frame[7:10]
            if family in self._family_samples and sample.timestamp_us <= self._family_samples[family]:
                raise ValueError('gazebo_gimbal_sample_repeated')
            raw = packet.sip_frame.encode('ascii')
            if self._parse_gimbal_packet(raw, source_ip=self.gimbal_ip) is None:
                raise ValueError('gazebo_gimbal_sip_invalid')
            self._previous_packet = packet
            self._family_samples[family] = sample.timestamp_us
            return ReceivedGimbalPacket(raw, self.gimbal_ip, packet.received_at_monotonic_s,
                                       sample if family == 'GAC' else None)
        except socket.timeout:
            raise
        except (OSError, ValueError, TypeError) as error:
            raise GimbalSourceError(str(error)) from error

    def matches_video_source(self, source):
        return (source.get('type') == 'GAZEBO_CAMERA'
                and source.get('source_clock_id') == self.settings.source_clock_id
                and source.get('world') == self.settings.world)

    def selection_modes(self):
        return []  # Lock is an explicit training stimulus, not image-based acquisition.

    def get_provider_metadata(self):
        result = super().get_provider_metadata()
        for key in ('gimbal_ip', 'listen_port', 'control_port'):
            result.pop(key)
        result.update(transport='unix_seqpacket', simulated=True,
            source_clock_id=self.settings.source_clock_id, world=self.settings.world,
            source_time_basis='gazebo_sim_us', mechanics_qualified=False)
        return result
