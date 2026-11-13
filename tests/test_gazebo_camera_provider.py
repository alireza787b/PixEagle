"""Actual-image envelope contracts; no Gazebo, aircraft, Docker or display."""
from pathlib import Path
from types import SimpleNamespace
import os
import socket

import pytest

from tools.gazebo_camera_provider import ImageStream, private_listener


def image(timestamp=1, **changes):
    stamp = SimpleNamespace(sec=timestamp, nsec=123000)
    header = SimpleNamespace(stamp=stamp, data=[], HasField=lambda key: key == 'stamp')
    enum = SimpleNamespace(values_by_name={'RGB_INT8': SimpleNamespace(number=3)})
    value = dict(header=header, HasField=lambda key: key == 'header',
        DESCRIPTOR=SimpleNamespace(fields_by_name={'pixel_format_type': SimpleNamespace(enum_type=enum)}),
        pixel_format_type=3, width=2, height=1, step=6, data=b'abcdef')
    return SimpleNamespace(**(value | changes))


def stream():
    return ImageStream(world='courtyard', image_topic='/world/courtyard/camera', source_clock_id='world-clock', clock=lambda: 7.25)


def test_original_callback_pixels_timestamp_and_receipt_stay_one_sample():
    source = stream()
    source.image(image())
    source.clock = lambda: 900.
    header, pixels = source.take()
    assert pixels == b'abcdef'
    assert header.header_simtime_us == 1000123
    assert header.received_at_monotonic_s == 7.25
    assert header.frame_id == 1 and header.provider_incarnation == source.incarnation
    assert header.source_clock_id == 'world-clock'


def test_latest_slot_bounds_backlog_without_reusing_frame_identity():
    source = stream()
    source.image(image(1))
    source.image(image(2, data=b'ghijkl'))
    header, pixels = source.take()
    assert (header.frame_id, header.header_simtime_us, pixels) == (2, 2000123, b'ghijkl')
    assert source.replaced == 1 and source.latest is None


def test_repeated_acquisition_does_not_renew_original_receipt_or_publish_again():
    source = stream()
    source.image(image())
    source.clock = lambda: 10.
    source.image(image())
    assert source.frame_id == 1 and source.take()[0].received_at_monotonic_s == 7.25
    source.image(image())
    assert source.latest is None and source.frame_id == 1


def test_clock_regression_retires_source_and_discards_pending_frame():
    source = stream()
    source.image(image(2))
    source.image(image(1))
    with pytest.raises(ValueError, match='source failed'):
        source.take()
    source.image(image(3))
    assert source.frame_id == 1 and source.latest is None


@pytest.mark.parametrize('change', [dict(HasField=lambda _: False), dict(pixel_format_type=8),
    dict(data=b'a'), dict(width=0), dict(step=5), dict(height=9999999)])
def test_malformed_original_images_fail_closed(change):
    source = stream()
    source.image(image(**change))
    with pytest.raises(ValueError, match='source failed'):
        source.take()
    assert source.frame_id == 0


def test_source_frame_is_taken_only_from_actual_header():
    source = stream()
    msg = image()
    msg.header.data = [SimpleNamespace(key='frame_id', value=['camera_link'])]
    source.image(msg)
    assert source.take()[0].source_frame_id == 'camera_link'


def test_existing_endpoint_is_never_removed(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / 'camera.sock'
    path.write_text('another owner')
    with pytest.raises(ValueError, match='already exists'):
        private_listener(path)
    assert path.read_text() == 'another owner'


def test_listener_is_private_and_does_not_accept_shared_parent(tmp_path):
    tmp_path.chmod(0o755)
    path = tmp_path / 'camera.sock'
    with pytest.raises(ValueError, match='0700'):
        private_listener(path)
    tmp_path.chmod(0o700)
    listener = private_listener(path)
    try:
        assert path.stat().st_mode & 0o777 == 0o600
        assert listener.family == socket.AF_UNIX
        assert path.stat().st_uid == os.getuid()
    finally:
        listener.close()
        path.unlink()


def test_socket_stream_preserves_header_and_pixels_for_one_active_peer(tmp_path):
    import json
    import struct
    import threading
    from tools.gazebo_camera_provider import serve
    tmp_path.chmod(0o700)
    path = tmp_path / 'camera.sock'
    source = stream()
    failures = []
    def server():
        try:
            serve(source, path)
        except Exception as error:
            failures.append(error)
    thread = threading.Thread(target=server)
    thread.start()
    try:
        import time
        deadline = time.monotonic() + 2
        while not path.is_socket() and time.monotonic() < deadline:
            threading.Event().wait(.005)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as receiver:
            receiver.settimeout(2)
            receiver.connect(str(path))
            with source.condition:
                assert source.condition.wait_for(lambda: source.connections == 1, timeout=1)
            # A callback that began before accept may commit after the pending slot was cleared.
            source.clock = lambda: 7.0
            source.image(image(0))
            receiver.settimeout(.05)
            with pytest.raises(socket.timeout):
                receiver.recv(1)
            receiver.settimeout(2)
            source.clock = lambda: 7.5
            source.image(image())
            def read(count):
                data = b''
                while len(data) < count:
                    data += receiver.recv(count - len(data))
                return data
            header = json.loads(read(struct.unpack('!I', read(4))[0]))
            assert header['header_simtime_us'] == 1000123
            assert header['received_at_monotonic_s'] == 7.5
            assert read(header['payload_length']) == b'abcdef'
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as other:
                other.settimeout(.05)
                other.connect(str(path))
                with pytest.raises(socket.timeout):
                    other.recv(1)  # A queued peer cannot consume the active client's stream.
    finally:
        source.stop()
        thread.join(2)
    assert not thread.is_alive() and not failures and not path.exists()


def info_message():
    return SimpleNamespace(width=1280, height=960,
        intrinsics=SimpleNamespace(k=[500., 0., 640., 0., 500., 480., 0., 0., 1.]),
        distortion=SimpleNamespace(k=[0.] * 5), SerializeToString=lambda: b'original-protobuf')


@pytest.mark.parametrize('change', ['none', 'width', 'focal', 'center', 'nan', 'distortion', 'short'])
def test_actual_camera_info_must_match_source_derived_calibration(change):
    from tools.gazebo_camera_provider import validate_camera_info
    expected = dict(image_size_px=[1280, 960], focal_length_px=[500., 500.], principal_point_px=[640., 480.])
    msg = info_message()
    if change == 'width': msg.width = 640
    elif change == 'focal': msg.intrinsics.k[0] = 501.
    elif change == 'center': msg.intrinsics.k[2] = 639.5
    elif change == 'nan': msg.intrinsics.k[0] = float('nan')
    elif change == 'distortion': msg.distortion.k[0] = .01
    elif change == 'short': msg.intrinsics.k.pop()
    if change == 'none':
        receipt = validate_camera_info(msg, expected)
        assert receipt['raw_protobuf_hex'] == b'original-protobuf'.hex()
        assert receipt['maximum_intrinsics_error_px'] == 0
    else:
        with pytest.raises(ValueError, match='differs'):
            validate_camera_info(msg, expected)


def test_camera_info_confirmation_is_original_and_later_change_retires_source(tmp_path):
    import json
    import threading
    from tools.gazebo_camera_provider import camera_info_callback
    source = stream()
    expected = dict(image_size_px=[1280, 960], focal_length_px=[500., 500.], principal_point_px=[640., 480.])
    path, ready = tmp_path / 'camera-info.json', threading.Event()
    callback = camera_info_callback(source, expected, path, ready)
    callback(info_message())
    assert ready.is_set()
    original = path.read_bytes()
    assert json.loads(original)['received_at_monotonic_s'] == 7.25
    source.clock = lambda: 99.
    callback(info_message())
    assert path.read_bytes() == original
    changed = info_message()
    changed.width = 42
    callback(changed)
    assert source.error is not None and path.read_bytes() == original


@pytest.mark.parametrize('stalled', [False, True])
def test_receiver_reconnect_requires_new_image_without_restarting_source(tmp_path, stalled):
    import json
    import struct
    import threading
    import time
    from tools.gazebo_camera_provider import serve
    tmp_path.chmod(0o700)
    path = tmp_path / 'camera.sock'
    source = stream()
    source.clock = time.monotonic
    source.image(image(1))  # Pending image from before the first connection must never replay.
    failures = []
    def server():
        try:
            serve(source, path)
        except Exception as error:
            failures.append(error)
    thread = threading.Thread(target=server)
    thread.start()
    first = second = None
    try:
        deadline = time.monotonic() + 2
        while not path.is_socket() and time.monotonic() < deadline:
            threading.Event().wait(.005)
        first = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        first.settimeout(.05)
        first.connect(str(path))
        with source.condition:
            assert source.condition.wait_for(lambda: source.connections == 1, timeout=1)
        with pytest.raises(socket.timeout):
            first.recv(1)
        if stalled:
            # Larger than the socket send buffer; the receiver intentionally consumes nothing.
            source.image(image(2, width=1024, height=1024, step=3072, data=b'x' * (3072 * 1024)))
            deadline = time.monotonic() + 2
            while source.client_failures == 0 and time.monotonic() < deadline:
                threading.Event().wait(.01)
            assert source.client_failures == 1
        first.close()
        source.image(image(3))  # Pending between connections must also be discarded.
        second = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        second.settimeout(.05)
        second.connect(str(path))
        with source.condition:
            assert source.condition.wait_for(lambda: source.connections == 2, timeout=1)
        with pytest.raises(socket.timeout):
            second.recv(1)
        source.image(image(4, data=b'newest'))
        second.settimeout(1)
        def read(count):
            value = b''
            while len(value) < count:
                part = second.recv(count - len(value))
                assert part
                value += part
            return value
        header = json.loads(read(struct.unpack('!I', read(4))[0]))
        assert header['header_simtime_us'] == 4000123
        assert header['provider_incarnation'] == source.incarnation
        assert header['source_clock_id'] == 'world-clock'
        assert read(header['payload_length']) == b'newest'
        assert thread.is_alive() and source.error is None
        source.image(image(1))  # Source reset remains fatal even after a successful reconnect.
        thread.join(2)
        assert failures and not thread.is_alive()
    finally:
        source.stop()
        if first: first.close()
        if second: second.close()
        thread.join(2)
    assert not path.exists()
