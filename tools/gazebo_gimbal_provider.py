#!/usr/bin/env python3
"""Ideal rendered gimbal: observed Gazebo poses → stamped production SIP packets.

Only the declared instrumentation camera may receive a pose intent. No PX4,
MAVLink, aircraft action, camera motor or public HTTP endpoint is available.
"""

from dataclasses import asdict
import argparse
import json
import math
import os
from pathlib import Path
import select
import signal
import socket
import struct
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from classes.aircraft_state import Quaternion, Vector3  # noqa: E402
from classes.capture_timing import SourceSampleStamp  # noqa: E402
from classes.gazebo_gimbal_source import GazeboGimbalPacket  # noqa: E402
from classes.gimbal_control import sip_frame  # noqa: E402
from classes.gimbal_geometry import resolve_angle_geometry, resolve_mount_type  # noqa: E402
from tools.gazebo_camera_provider import private_listener  # noqa: E402
from tools.gazebo_gimbal_model import IdealGimbalSettings, IdealStabilizedGimbal, ObservedGimbalPose  # noqa: E402
from tools.gimbal_simulator import angle_hex  # noqa: E402


ENU_TO_NED = Quaternion(0., math.sqrt(.5), math.sqrt(.5), 0.)
FLU_TO_FRD = Quaternion(0., 1., 0., 0.)


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, allow_nan=False)
        stream.write('\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def observed_pose(message, *, aircraft_model, camera_model, received_at):
    stamp = message.header.stamp
    if stamp.sec < 0 or not 0 <= stamp.nsec < 1_000_000_000:
        raise ValueError('gimbal_world_stamp_invalid')
    selected = {}
    for value in message.pose:
        if value.name in (aircraft_model, camera_model):
            if value.name in selected:
                raise ValueError('gimbal_world_pose_ambiguous')
            selected[value.name] = value
    if len(selected) != 2:
        raise ValueError('gimbal_world_pose_missing')

    def convert(value):
        p, q = value.position, value.orientation
        return Vector3(p.y, p.x, -p.z), ENU_TO_NED.compose(
            Quaternion(q.w, q.x, q.y, q.z)).compose(FLU_TO_FRD)

    body_position, body_q = convert(selected[aircraft_model])
    camera_position, camera_q = convert(selected[camera_model])
    return ObservedGimbalPose(stamp.sec * 1_000_000 + stamp.nsec // 1000, received_at,
        body_position, body_q, camera_position, camera_q), selected[camera_model].id


def pose_request(intent, *, camera_model, camera_id, message_type):
    value = message_type(name=camera_model, id=camera_id)
    p = intent.position_ned
    value.position.x, value.position.y, value.position.z = p.y, p.x, -p.z
    q = ENU_TO_NED.compose(intent.camera_to_ned).compose(FLU_TO_FRD)
    value.orientation.w, value.orientation.x, value.orientation.y, value.orientation.z = q.w, q.x, q.y, q.z
    return value


class RenderedGimbalSource:
    def __init__(self, config, private, *, clock=time.monotonic):
        self.config, self.private, self.clock = config, private, clock
        mechanics = config['instrumentation_camera']
        self.camera_model = mechanics['instance']
        self.aircraft_model = config['aircraft_model']
        if self.camera_model == self.aircraft_model:
            raise ValueError('gimbal_camera_must_be_separate_instrumentation')
        self.model = IdealStabilizedGimbal(IdealGimbalSettings(Vector3(*mechanics['offset_body_frd_m']),
            mechanics['pointing_rate_deg_s'], mechanics['maximum_pose_gap_s']))
        camera = config['gimbal_config']
        mount = resolve_mount_type(camera, {}, {}, allowed=('HORIZONTAL', 'VERTICAL'))
        self.geometry = resolve_angle_geometry(camera, mount)
        self.incarnation = uuid.uuid4().hex
        self.condition = threading.Condition()
        self.pending_pose = self.pending_packets = None
        self.latest_pose = None
        self.last_pose_time = None
        self.sequence = self.control_sequence = 0
        self.last_control = None
        self.control_error = None
        self.error = None
        self.stopped = False
        self.pose_replaced = self.sent = self.client_failures = 0

    def receive(self, message):
        received = self.clock()
        try:
            pose, camera_id = observed_pose(message, aircraft_model=self.aircraft_model,
                                            camera_model=self.camera_model, received_at=received)
            with self.condition:
                if self.stopped or self.error:
                    return
                if self.last_pose_time is not None:
                    if pose.timestamp_us < self.last_pose_time:
                        raise ValueError('gimbal_world_clock_regressed')
                    if pose.timestamp_us == self.last_pose_time:
                        return
                if self.pending_pose is not None:
                    self.pose_replaced += 1
                self.last_pose_time = pose.timestamp_us
                self.pending_pose = pose, camera_id
                self.condition.notify_all()
        except Exception as error:
            with self.condition:
                self.error = error
                self.pending_pose = self.pending_packets = None
                self.condition.notify_all()

    def stop(self, *_):
        with self.condition:
            self.stopped = True
            self.condition.notify_all()

    def _control(self, pose):
        path = self.private / 'operator-command.json'
        if not path.exists():
            return
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
            raise ValueError('gimbal_operator_file_invalid')
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict) or value.get('incarnation') != self.incarnation:
            return  # A previous producer's command is never replayed after restart.
        sequence = value.get('sequence')
        if type(sequence) is not int or sequence < 1:
            raise ValueError('gimbal_operator_sequence_invalid')
        if sequence < self.control_sequence:
            raise ValueError('gimbal_operator_sequence_obsolete')
        if sequence == self.control_sequence:
            if value != self.last_control:
                raise ValueError('gimbal_operator_command_rewritten')
            return
        if sequence != self.control_sequence + 1:
            raise ValueError('gimbal_operator_sequence_gap')
        operation = value.get('operation')
        fields = {'incarnation', 'sequence', 'operation'}
        if operation == 'aim':
            if set(value) != fields | {'azimuth_deg', 'elevation_deg'}:
                raise ValueError('gimbal_operator_aim_invalid')
            self.model.aim(value['azimuth_deg'], value['elevation_deg'])
        elif operation == 'lock':
            if set(value) != fields | {'range_m'} or type(value['range_m']) not in (int, float):
                raise ValueError('gimbal_operator_range_invalid')
            distance = value['range_m']
            if not math.isfinite(distance) or not .1 <= distance <= 10_000.:
                raise ValueError('gimbal_operator_range_invalid')
            ray, point = pose.direction_ned, pose.camera_position_ned
            self.model.lock_point(Vector3(point.x + distance*ray.x, point.y + distance*ray.y, point.z + distance*ray.z))
        elif operation in ('lost', 'release'):
            if set(value) != fields:
                raise ValueError('gimbal_operator_command_invalid')
            (self.model.lose_target if operation == 'lost' else self.model.release_target)()
        else:
            raise ValueError('gimbal_operator_command_unsupported')
        self.control_sequence, self.last_control = sequence, value

    def process(self, pose):
        # Observe first so a lock is defined from current measured geometry.
        intent = self.model.observe(pose)
        if intent is None:
            return None
        try:
            self._control(pose)
            self.control_error = None
        except (ValueError, TypeError, KeyError) as error:
            # Invalid operator input preserves the live observation/old target;
            # it is not a reason to manufacture a camera source disconnect.
            self.control_error = str(error)
        raw = pose.angles(self.geometry)
        frames = (sip_frame(('#tpGPCrGAC' + ''.join(angle_hex(v) for v in raw)).encode('ascii')),
                  sip_frame(f'#TPDP2rTRC0{self.model.tracking_state.value}'.encode('ascii')))
        packets = []
        for frame in frames:
            self.sequence += 1
            sample = SourceSampleStamp(self.config['source_clock_id'], self.incarnation,
                                       self.sequence, pose.timestamp_us, 'gazebo_sim_us')
            packets.append(GazeboGimbalPacket(self.config['world'], sample,
                pose.received_at_monotonic_s, frame.decode('ascii')).encode())
        with self.condition:
            self.pending_packets = packets
            self.latest_pose = pose
            self.condition.notify_all()
        atomic_json(self.private / 'operator-state.json', dict(incarnation=self.incarnation,
            control_sequence=self.control_sequence, tracking_state=self.model.tracking_state.name,
            control_error=self.control_error,
            pose=asdict(pose), angles_deg=raw, target_ned=None if self.model.target_ned is None else asdict(self.model.target_ned),
            camera_model=self.camera_model, aircraft_model=self.aircraft_model, mechanics_qualified=False))
        return intent


def serve_packets(source):
    path = source.private / 'gimbal.sock'
    listener = private_listener(path, socket_kind=socket.SOCK_SEQPACKET)
    inode = path.stat().st_ino
    try:
        while not source.stopped and not source.error:
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            with connection:
                _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    continue
                connection.settimeout(.1)
                with source.condition:
                    source.pending_packets = None  # No retained angle is replayed to a new backend.
                try:
                    while not source.stopped and not source.error:
                        if select.select([connection], [], [], 0)[0]:
                            break
                        with source.condition:
                            source.condition.wait_for(lambda: source.pending_packets is not None or source.stopped or source.error, timeout=.1)
                            packets, source.pending_packets = source.pending_packets, None
                        for packet in packets or ():
                            connection.sendall(packet)
                            source.sent += 1
                except OSError:
                    source.client_failures += 1
    finally:
        listener.close()
        if path.exists() and path.stat().st_ino == inode:
            path.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--private', type=Path, required=True)
    args = parser.parse_args()
    from gz.transport13 import Node
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.msgs10.pose_pb2 import Pose
    from gz.msgs10.boolean_pb2 import Boolean

    config = json.loads(args.source.read_text())
    source = RenderedGimbalSource(config, args.private)
    signal.signal(signal.SIGTERM, source.stop)
    signal.signal(signal.SIGINT, source.stop)
    node = Node()
    topic = f'/world/{config["world"]}/pose/info'
    if not node.subscribe(Pose_V, topic, source.receive):
        raise ValueError('gimbal_pose_subscription_refused')
    def packet_worker():
        try:
            serve_packets(source)
        except Exception as error:
            with source.condition:
                source.error = error
                source.condition.notify_all()

    worker = threading.Thread(target=packet_worker, name='simulated-sip-source', daemon=True)
    worker.start()
    request_count = unacknowledged = 0
    try:
        while not source.stopped:
            with source.condition:
                source.condition.wait_for(lambda: source.pending_pose is not None or source.error or source.stopped, timeout=.1)
                if source.error:
                    raise ValueError('gimbal_observed_source_failed') from source.error
                selected, source.pending_pose = source.pending_pose, None
            if selected is None:
                continue
            pose, camera_id = selected
            intent = source.process(pose)
            if intent is not None:
                request = pose_request(intent, camera_model=source.camera_model, camera_id=camera_id, message_type=Pose)
                ok, reply = node.request(f'/world/{config["world"]}/set_pose', request, Pose, Boolean, 20)
                request_count += 1
                unacknowledged += not (ok and reply.data)
                # Reply uncertainty is diagnostic. Only a later world-pose
                # callback can supply observed angles, never this intent/ACK.
    finally:
        source.stop()
        worker.join(timeout=1.)
        node.unsubscribe(topic)
        del node
        print(json.dumps(dict(pose_requests=request_count, unacknowledged_pose_requests=unacknowledged,
            packets_sent=source.sent, replaced_pending_poses=source.pose_replaced, client_failures=source.client_failures,
            mechanics='ideal_stabilized', aircraft_commands_sent=False)), flush=True)


if __name__ == '__main__':
    main()
