#!/usr/bin/env python3
"""Receive actual stamped Gazebo images and expose one private, bounded pixel stream.

No aircraft client, pose synthesis, command publisher, encoder or timing estimate.
The simulator and receiver run on the same host CLOCK_MONOTONIC domain.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import signal
import select
import socket
import stat
import struct
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from classes.gazebo_camera_protocol import GazeboFrameHeader, MAX_FRAME_BYTES, pack_header  # noqa: E402


class ImageStream:
    """Only a callback's original image/receipt pair can enter the latest slot."""
    def __init__(self, *, world, image_topic, source_clock_id, clock=time.monotonic):
        self.world, self.image_topic, self.source_clock_id = world, image_topic, source_clock_id
        self.incarnation = uuid.uuid4().hex
        self.clock = clock
        self.condition = threading.Condition()
        self.latest = None
        self.error = None
        self.stopped = False
        self.frame_id = self.sent = self.replaced = 0
        self.connections = self.client_failures = 0
        self.last_simtime_us = None

    def image(self, message):
        received = self.clock()
        try:
            if not message.HasField('header') or not message.header.HasField('stamp'):
                raise ValueError('Gazebo Image acquisition stamp is absent')
            stamp = message.header.stamp
            if stamp.sec < 0 or not 0 <= stamp.nsec < 1000000000:
                raise ValueError('Gazebo Image acquisition stamp is invalid')
            timestamp = stamp.sec * 1000000 + stamp.nsec // 1000
            enum = message.DESCRIPTOR.fields_by_name['pixel_format_type'].enum_type
            if message.pixel_format_type != enum.values_by_name['RGB_INT8'].number:
                raise ValueError('Gazebo Image must contain original RGB_INT8 pixels')
            payload = message.data
            if not isinstance(payload, bytes) or len(payload) > MAX_FRAME_BYTES:
                raise ValueError('Gazebo Image payload is invalid')
            source_frames = [value for item in message.header.data if item.key == 'frame_id' for value in item.value]
            if len(source_frames) > 1:
                raise ValueError('Gazebo Image frame metadata is ambiguous')
            with self.condition:
                if self.stopped or self.error:
                    return
                if self.last_simtime_us is not None:
                    if timestamp < self.last_simtime_us:
                        raise ValueError('Gazebo camera clock regressed; retire source')
                    if timestamp == self.last_simtime_us:
                        return  # A paused/repeated acquisition never renews its receipt.
                header = GazeboFrameHeader(schema_version=1, provider_incarnation=self.incarnation,
                    source_clock_id=self.source_clock_id, frame_id=self.frame_id + 1,
                    world=self.world, image_topic=self.image_topic, header_simtime_us=timestamp,
                    received_at_monotonic_s=received, width=message.width, height=message.height,
                    stride=message.step, pixel_format='RGB_INT8', payload_length=len(payload),
                    source_frame_id=source_frames[0] if source_frames else None)
                if self.latest is not None:
                    self.replaced += 1
                self.frame_id += 1
                self.last_simtime_us = timestamp
                self.latest = (header, payload)
                self.condition.notify_all()
        except Exception as error:
            with self.condition:
                self.error = error
                self.latest = None
                self.condition.notify_all()

    def stop(self, *_):
        with self.condition:
            self.stopped = True
            self.condition.notify_all()

    def take(self):
        with self.condition:
            if self.latest is None and not self.error and not self.stopped:
                self.condition.wait(.25)
            if self.error:
                raise ValueError('Gazebo source failed') from self.error
            result, self.latest = self.latest, None
            return result


def private_listener(path):
    """Never unlink a pre-existing endpoint or replace another provider."""
    parent = path.parent.stat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError('Camera socket requires its same-user private 0700 directory')
    if path.exists() or path.is_symlink():
        raise ValueError('Camera socket endpoint already exists')
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(str(path))
        path.chmod(0o600)
        listener.listen(1)
        listener.settimeout(.25)
        return listener
    except BaseException:
        listener.close()
        raise


def serve(stream, path):
    listener = private_listener(path)
    inode = path.stat().st_ino
    try:
        while not stream.stopped:
            if stream.error:
                raise ValueError('Gazebo source failed') from stream.error
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            connected_at = stream.clock()
            with connection:
                _pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    continue
                with stream.condition:
                    stream.latest = None
                    stream.connections += 1
                    stream.condition.notify_all()
                print(json.dumps(dict(kind='camera_receiver_connected', connection=stream.connections,
                    accepted_at_monotonic_s=connected_at, provider_incarnation=stream.incarnation)), flush=True)
                connection.settimeout(1.)  # Transport resource bound, not an image-age qualification.
                try:
                    while not stream.stopped:
                        # This is a one-way stream: EOF or incoming bytes retire only this client.
                        if select.select([connection], [], [], 0)[0]:
                            break
                        frame = stream.take()
                        if frame is not None:
                            header, payload = frame
                            if header.received_at_monotonic_s <= connected_at:
                                continue
                            connection.sendall(pack_header(header))
                            connection.sendall(payload)
                            stream.sent += 1
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    stream.client_failures += 1

    finally:
        listener.close()
        stream.stop()
        if path.exists() and path.is_socket() and path.stat().st_ino == inode:
            path.unlink()


def validate_camera_info(message, calibration):
    """Compare renderer-reported intrinsics with the pinned SDF-derived values."""
    width, height = calibration['image_size_px']
    fx, fy = calibration['focal_length_px']
    cx, cy = calibration['principal_point_px']
    expected = [fx, 0., cx, 0., fy, cy, 0., 0., 1.]
    actual = list(message.intrinsics.k)
    distortion = list(message.distortion.k)
    if (message.width != width or message.height != height or len(actual) != 9
            or any(not math.isfinite(value) or abs(value - reference) > .001 for value, reference in zip(actual, expected))
            or len(distortion) != 5 or any(value != 0. for value in distortion)):
        raise ValueError('Actual Gazebo camera_info differs from pinned pinhole calibration')
    return dict(width=message.width, height=message.height, intrinsics_k=actual,
        distortion_k=distortion, maximum_intrinsics_error_px=max(abs(a-b) for a, b in zip(actual, expected)),
        tolerance_px=.001, raw_protobuf_hex=message.SerializeToString().hex())


def camera_info_callback(stream, calibration, receipt_path, ready):
    def receive(message):
        received = stream.clock()
        try:
            value = validate_camera_info(message, calibration)
            with stream.condition:
                if ready.is_set():
                    return
                value.update(source_clock_id=stream.source_clock_id, image_topic=stream.image_topic,
                    provider_incarnation=stream.incarnation, received_at_monotonic_s=received,
                    actual_camera_info_confirmation=True)
                temporary = receipt_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(value, indent=2) + '\n')
                temporary.replace(receipt_path)
                ready.set()
        except Exception as error:
            with stream.condition:
                stream.error = error
                stream.latest = None
                stream.condition.notify_all()
    return receive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True, type=Path)
    parser.add_argument('--world', required=True)
    parser.add_argument('--image-topic', required=True)
    parser.add_argument('--source-clock-id', required=True)
    parser.add_argument('--calibration-file', required=True, type=Path)
    args = parser.parse_args()
    # Bindings are supplied by the verified Harmonic image, never installed at startup.
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image
    from gz.msgs10.camera_info_pb2 import CameraInfo
    stream = ImageStream(world=args.world, image_topic=args.image_topic, source_clock_id=args.source_clock_id)
    calibration = json.loads(args.calibration_file.read_text())['calibration']
    node = Node()
    signal.signal(signal.SIGTERM, stream.stop)
    signal.signal(signal.SIGINT, stream.stop)
    if not node.subscribe(Image, args.image_topic, stream.image):
        raise RuntimeError('Gazebo camera subscription refused')
    print(json.dumps(dict(kind='actual-gazebo-image-provider-v1', provider_incarnation=stream.incarnation,
        source_clock_id=args.source_clock_id, image_topic=args.image_topic, world=args.world)), flush=True)
    info_topic = args.image_topic.rsplit('/', 1)[0] + '/camera_info'
    ready = threading.Event()
    callback = camera_info_callback(stream, calibration, args.socket.parent / 'camera-info.json', ready)
    try:
        if not node.subscribe(CameraInfo, info_topic, callback):
            raise RuntimeError('Gazebo camera_info subscription refused')
        deadline = time.monotonic() + 10.
        while not ready.is_set() and not stream.stopped and not stream.error and time.monotonic() < deadline:
            ready.wait(.05)
        if stream.error or not ready.is_set():
            raise ValueError('Actual Gazebo camera_info startup confirmation unavailable') from stream.error
        serve(stream, args.socket)
    finally:
        node.unsubscribe(info_topic)
        node.unsubscribe(args.image_topic)
        print(json.dumps(dict(frames_received=stream.frame_id, frames_sent=stream.sent,
                              pending_frames_replaced=stream.replaced, connections=stream.connections,
                              client_failures=stream.client_failures)), flush=True)


if __name__ == '__main__':
    main()
