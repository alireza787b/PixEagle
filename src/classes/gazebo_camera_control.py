"""Normalized camera adapter for a private, same-user rendered training source.

No aircraft API or vendor motor opcodes. Telemetry still comes from observed
Gazebo poses through the production SIP parser, independently of command replies.
"""

import asyncio
from contextlib import nullcontext
from dataclasses import asdict, dataclass, replace
import json
import math
import os
from pathlib import Path
import socket
import struct
import threading
import time
import uuid

from classes.capture_timing import SourceSampleStamp
from classes.gimbal_motion import SIP_MOTION_SETTINGS, resolve_motion


MAX_CONTROL_BYTES = 16_384


def exchange(path, incarnation, operation, arguments):
    request_id = uuid.uuid4().hex
    request = dict(version=1, request_id=request_id, incarnation=incarnation,
                   operation=operation, arguments=arguments)
    raw = json.dumps(request, allow_nan=False, separators=(',', ':')).encode()
    if len(raw) > MAX_CONTROL_BYTES:
        raise ValueError('rendered_camera_request_too_large')
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
            connection.settimeout(.05)
            connection.connect(str(path))
            _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise ValueError('rendered_camera_peer_uid_mismatch')
            connection.sendall(raw)
            data, _, flags, _ = connection.recvmsg(MAX_CONTROL_BYTES)
        reply = json.loads(data)
        if (flags & socket.MSG_TRUNC or not isinstance(reply, dict)
                or reply.get('request_id') != request_id or reply.get('incarnation') != incarnation):
            raise ValueError('rendered_camera_reply_context_changed')
        if reply.get('success') is not True:
            raise ValueError(reply.get('reason', 'rendered_camera_request_rejected'))
        return reply
    except (OSError, json.JSONDecodeError) as exc:
        # An uncertain mutation is never retried or replayed by this adapter.
        raise RuntimeError('Rendered camera did not acknowledge the command') from exc


@dataclass(frozen=True)
class PreparedRenderedSelection:
    control: object
    mode: str
    source_sample: SourceSampleStamp
    x: float
    y: float
    token: str | None = None


class RenderedCameraControl:
    capabilities = ('set_mode', 'select', 'cancel', 'pan', 'tilt', 'home', 'stop')
    motion_settings = SIP_MOTION_SETTINGS
    selection_mode = 'classic'

    def __init__(self, provider):
        self.provider = provider
        self.owns_tracking = False
        self._lock = threading.RLock()
        self._epoch = 0

    def _request(self, operation, **arguments):
        packet = self.provider._previous_packet
        if not self.provider.running or packet is None:
            raise ValueError('rendered_camera_source_unavailable')
        return exchange(Path(self.provider.settings.socket_path).with_name('control.sock'),
                        packet.source_sample.source_incarnation, operation, arguments)

    def prepare_selection_from_frame(self, *, x, y, source_sample, width=None, height=None):
        if (not isinstance(source_sample, SourceSampleStamp)
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) or not 0 <= v <= 1 for v in (x, y))):
            raise ValueError('rendered_camera_displayed_frame_required')
        if width is not None or height is not None:
            raise ValueError('Rendered camera supports point selection')
        return PreparedRenderedSelection(self, self.selection_mode, source_sample, x, y)

    def prepare_selection(self, **kwargs):
        raise ValueError('rendered_camera_displayed_frame_required')

    async def resolve_selection(self, prepared):
        if prepared.control is not self or prepared.mode != self.selection_mode:
            raise ValueError('rendered_camera_selection_changed')
        try:
            reply = await asyncio.to_thread(self._request, 'resolve',
                source_sample=asdict(prepared.source_sample), x=prepared.x, y=prepared.y)
        except ValueError as error:
            messages = {
                'scene_point_unavailable': 'Select a visible scene surface; sky has no simulated target.',
                'scene_frame_expired_or_unpaired': 'Displayed frame is unavailable. Select again on fresh video.',
                'scene_frame_identity_changed': 'Video source changed. Select again on fresh video.',
            }
            raise ValueError(messages.get(str(error), str(error))) from error
        return replace(prepared, token=reply['token'])

    def stop(self):
        with self._lock:
            self._epoch += 1
            try:
                self._request('stop')
                return True
            except (RuntimeError, ValueError):
                return False

    def close(self):
        self.stop()
        if self.owns_tracking:
            try:
                self._request('cancel')
            except (RuntimeError, ValueError):
                pass
        self.owns_tracking = False

    async def prepare_manual(self, command_guard):
        # Guard and final device write are serialized by CameraManualExecutor.
        with command_guard():
            self._request('cancel')
            self.owns_tracking = False

    def send_manual_intent(self, axis, value):
        if (axis not in ('pan', 'tilt') or isinstance(value, bool)
                or not isinstance(value, (int, float)) or not math.isfinite(value) or not -1 <= value <= 1):
            raise ValueError('rendered_camera_manual_intent_invalid')
        self._request('manual', axis=axis, value=value,
                      maximum_speed_deg_s=self.motion_settings['max_speed_deg_s'])

    async def execute(self, operation, *, selection_mode=None, prepared_selection=None,
                      selection_guard=None, direction=None, speed_deg_s=None, duration_ms=None, **kwargs):
        if operation not in self.capabilities:
            raise ValueError('rendered_camera_operation_unsupported')
        if operation == 'select':
            if (not isinstance(prepared_selection, PreparedRenderedSelection)
                    or prepared_selection.control is not self or not prepared_selection.token):
                raise ValueError('rendered_camera_selection_unresolved')
            with selection_guard() if selection_guard else nullcontext():
                self._request('select', token=prepared_selection.token)
                self.owns_tracking = True
            return dict(success=True, message='Camera target designated.',
                        selection_dispatched_wall_time=time.time(), selection_dispatched_monotonic=time.monotonic())
        if operation == 'set_mode':
            if selection_mode != 'classic':
                raise ValueError('rendered_camera_selection_mode_unsupported')
            self._request('cancel')
            self.owns_tracking = False
        elif operation == 'stop':
            return dict(success=self.stop(), message='Camera movement stopped.')
        elif operation in ('pan', 'tilt'):
            speed, duration = resolve_motion(self.motion_settings, speed_deg_s, duration_ms)
            if direction not in (-1, 1):
                raise ValueError('rendered_camera_direction_invalid')
            with self._lock:
                epoch = self._epoch
                self._request('manual', axis=operation,
                    value=direction * speed / self.motion_settings['max_speed_deg_s'],
                    maximum_speed_deg_s=self.motion_settings['max_speed_deg_s'])
            try:
                await asyncio.sleep(duration / 1000)
            finally:
                with self._lock:
                    if self._epoch == epoch:
                        self.stop()
        else:
            self._request(operation)
            self.owns_tracking = False
        return dict(success=True, message='Camera command accepted.')
