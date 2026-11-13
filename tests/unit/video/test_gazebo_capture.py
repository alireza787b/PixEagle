"""Actual image framing and source identity, without Gazebo or a network."""

from dataclasses import asdict, replace
import json
import socket
import struct
import time

import pytest

from classes.gazebo_camera_protocol import GazeboFrameHeader, pack_header, read_header_length
from classes.gazebo_capture import GazeboCameraSettings, GazeboCapture


def header(**changes):
    base = GazeboFrameHeader(1, 'a' * 32, 'world-clock', 1, 'training', '/camera/image',
        1_000_000, time.monotonic(), 2, 1, 6, 'RGB_INT8', 6)
    return replace(base, **changes)


@pytest.fixture
def connection(tmp_path):
    path = str(tmp_path / 'camera.sock')
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen(1)
    settings = GazeboCameraSettings(path, 'world-clock', 'training', '/camera/image', .05)
    capture = GazeboCapture(settings)
    writer, _ = listener.accept()
    try:
        yield capture, writer
    finally:
        capture.release()
        writer.close()
        listener.close()


def send(writer, item, pixels=b'\x01\x02\x03\x04\x05\x06'):
    writer.sendall(pack_header(item) + pixels)


def test_pixels_and_original_sample_time_remain_one_observation(connection):
    capture, writer = connection
    item = header()
    send(writer, item)
    sample = capture.read_sample()
    assert sample.frame.tolist() == [[[3, 2, 1], [6, 5, 4]]]
    assert sample.received_at_monotonic_s == item.received_at_monotonic_s
    assert asdict(sample.source_sample) == dict(clock_id='world-clock', source_incarnation='a' * 32,
        sequence=1, timestamp_us=1_000_000, time_basis='gazebo_sim_us')


@pytest.mark.parametrize('changes', [
    dict(frame_id=0), dict(frame_id=True), dict(header_simtime_us=-1),
    dict(width=0), dict(stride=5), dict(payload_length=7), dict(pixel_format='BGR_INT8'),
    dict(provider_incarnation='not-an-incarnation'), dict(received_at_monotonic_s=float('nan')),
    dict(schema_version=True), dict(schema_version=2), dict(image_topic='camera'),
])
def test_invalid_envelope_refused_before_pixels(changes):
    with pytest.raises(ValueError):
        header(**changes)


@pytest.mark.parametrize('prefix', [b'', b'123', struct.pack('!I', 0), struct.pack('!I', 4097)])
def test_header_length_is_bounded(prefix):
    with pytest.raises(ValueError):
        read_header_length(prefix)


@pytest.mark.parametrize('changes', [dict(source_clock_id='different'), dict(world='different'),
                                    dict(image_topic='/different')])
def test_wrong_source_closes_capture(connection, changes):
    capture, writer = connection
    send(writer, header(**changes))
    with pytest.raises(ValueError, match='source_changed'):
        capture.read_sample()
    assert not capture.isOpened()


@pytest.mark.parametrize('changes', [dict(frame_id=1), dict(header_simtime_us=999_999),
                                    dict(provider_incarnation='b' * 32)])
def test_old_or_replaced_sample_cannot_refresh_capture(connection, changes):
    capture, writer = connection
    original = header()
    send(writer, original)
    capture.read_sample()
    next_item = replace(original, frame_id=2, header_simtime_us=1_033_333,
                        received_at_monotonic_s=time.monotonic())
    send(writer, replace(next_item, **changes))
    with pytest.raises(ValueError, match='source_progress_invalid'):
        capture.read_sample()
    assert not capture.isOpened()


def test_partial_payload_does_not_publish_a_frame(connection):
    capture, writer = connection
    send(writer, header(), b'12')
    writer.shutdown(socket.SHUT_WR)
    with pytest.raises(ConnectionError):
        capture.read_sample()
    assert not capture.isOpened()


def test_unknown_header_fields_do_not_extend_contract(connection):
    capture, writer = connection
    encoded = json.dumps(header().payload() | {'exposure_is_verified': True}).encode()
    writer.sendall(struct.pack('!I', len(encoded)) + encoded)
    with pytest.raises(ValueError, match='header_fields_invalid'):
        capture.read_sample()
    assert not capture.isOpened()


def test_source_stamp_survives_measurement_json_round_trip(connection):
    from classes.frame_publisher import CaptureStamp
    from classes.guidance_observation import ImageMeasurement, ObservationProvenance

    capture, writer = connection
    send(writer, header())
    sample = capture.read_sample()
    stamp = CaptureStamp('epoch', 'sample-1', sample.received_at_monotonic_s, 'fresh', sample.source_sample)
    provenance = ObservationProvenance('stream', 1, 'geometry', None, stamp)
    measurement = ImageMeasurement(provenance, (0., 0.), (2, 1), None, True)
    restored = ImageMeasurement.from_dict(json.loads(json.dumps(asdict(measurement))))
    assert restored == measurement
    assert restored.provenance.capture.source_sample is not sample.source_sample
