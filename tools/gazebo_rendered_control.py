"""One simulator camera command owner for QGC, Dashboard and training GUI."""

from collections import OrderedDict
import json
import os
import socket
import struct
import uuid

from classes.capture_timing import SourceSampleStamp
from classes.gazebo_camera_control import MAX_CONTROL_BYTES
from classes.gimbal_control import validate_camera_rectangle
from tools.gazebo_camera_provider import private_listener


class RenderedSceneControl:
    def __init__(self, source, history):
        self.source, self.history = source, history
        self.revision = 0
        self._prepared = OrderedDict()

    def changed(self):
        self.revision += 1
        self._prepared.clear()

    def dispatch(self, request):
        if (not isinstance(request, dict) or set(request) != {
                'version', 'request_id', 'incarnation', 'operation', 'arguments'}
                or type(request['version']) is not int or request['version'] != 1
                or not isinstance(request['request_id'], str) or len(request['request_id']) != 32
                or request['incarnation'] != self.source.incarnation
                or not isinstance(request['arguments'], dict)):
            raise ValueError('rendered_camera_request_context_invalid')
        with self.source.condition:
            pose = self.source.latest_pose
            if (pose is None or self.source.stopped or self.source.error
                    or not 0 <= self.source.clock() - pose.received_at_monotonic_s <= self.source.model.settings.maximum_pose_gap_s):
                raise ValueError('rendered_camera_observation_stale')
            operation, args = request['operation'], request['arguments']
            if operation == 'resolve':
                if set(args) != {'source_sample', 'x', 'y', 'width', 'height'}:
                    raise ValueError('rendered_camera_selection_invalid')
                if args['width'] is not None or args['height'] is not None:
                    validate_camera_rectangle(args['x'], args['y'], args['width'], args['height'])
                sample = SourceSampleStamp(**args['source_sample'])
                point = self.history.select(sample, args['x'], args['y'])
                token = uuid.uuid4().hex
                self._prepared[token] = (point, args['x'], args['y'], self.revision)
                while len(self._prepared) > 64:
                    self._prepared.popitem(last=False)
                return dict(token=token)
            if operation == 'select':
                if set(args) != {'token'} or not isinstance(args['token'], str):
                    raise ValueError('rendered_camera_selection_invalid')
                prepared = self._prepared.pop(args['token'], None)
                if prepared is None or prepared[3] != self.revision:
                    raise ValueError('rendered_camera_selection_obsolete')
                point, x, y, _ = prepared
                # Original frame expires even if resolution/commit were delayed.
                if self.history.select(point.source_sample, x, y) != point:
                    raise ValueError('rendered_camera_selection_changed')
                self.source.model.lock_point(point.position_ned)
            elif operation == 'manual':
                if set(args) != {'axis', 'value', 'maximum_speed_deg_s'}:
                    raise ValueError('rendered_camera_manual_invalid')
                self.source.model.manual(**args)
            elif operation in ('stop', 'cancel', 'home'):
                if args:
                    raise ValueError('rendered_camera_command_invalid')
                if operation == 'stop':
                    self.source.model.stop_manual()
                elif operation == 'cancel':
                    self.source.model.release_target()
                else:
                    self.source.home_view(pose)
            else:
                raise ValueError('rendered_camera_operation_unsupported')
            self.changed()
            return dict(command_revision=self.revision)


def serve_controls(owner, ready=None):
    source = owner.source
    path = source.private / 'control.sock'
    listener = private_listener(path, socket_kind=socket.SOCK_SEQPACKET)
    inode = path.stat().st_ino
    if ready is not None:
        ready.set()
    try:
        while not source.stopped and not source.error:
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            with connection:
                connection.settimeout(.05)
                _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    continue
                request = {}
                try:
                    data, _, flags, _ = connection.recvmsg(MAX_CONTROL_BYTES)
                    if not data or flags & socket.MSG_TRUNC:
                        raise ValueError('rendered_camera_request_truncated')
                    request = json.loads(data)
                    result = owner.dispatch(request)
                    reply = dict(success=True, **result)
                except (ValueError, TypeError, KeyError, OSError) as error:
                    reply = dict(success=False, reason=str(error))
                reply.update(request_id=request.get('request_id') if isinstance(request, dict) else None,
                             incarnation=source.incarnation)
                try:
                    connection.sendall(json.dumps(reply, allow_nan=False).encode())
                except OSError:
                    pass  # No retry of an uncertain selection or movement.
    finally:
        listener.close()
        if path.exists() and path.stat().st_ino == inode:
            path.unlink()
