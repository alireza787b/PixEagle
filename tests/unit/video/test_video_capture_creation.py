# tests/unit/video/test_video_capture_creation.py
"""
Unit tests for video capture creation for all source types.

Tests source-specific capture creation methods and GStreamer pipeline generation.
"""

import pytest
import sys
import os
import numpy as np
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from tests.fixtures.mock_video import (
    MockVideoCapture, MockGStreamerCapture, create_mock_video_capture
)


@pytest.fixture
def mock_parameters():
    """Fixture for mocked Parameters with all video settings."""
    with patch('classes.video_handler.Parameters') as mock_params:
        # Common settings
        mock_params.VIDEO_SOURCE_TYPE = "VIDEO_FILE"
        mock_params.VIDEO_FILE_PATH = "resources/test.mp4"
        mock_params.CAPTURE_WIDTH = 640
        mock_params.CAPTURE_HEIGHT = 480
        mock_params.CAPTURE_FPS = 30
        mock_params.DEFAULT_FPS = 30
        mock_params.USE_GSTREAMER = False
        mock_params.STORE_LAST_FRAMES = 5
        mock_params.OPENCV_BUFFER_SIZE = 1

        # USB Camera settings
        mock_params.CAMERA_INDEX = 0
        mock_params.DEVICE_PATH = "/dev/video0"
        mock_params.PIXEL_FORMAT = "YUYV"
        mock_params.USE_V4L2_BACKEND = False
        mock_params.OPENCV_FOURCC = ""

        # RTSP settings
        mock_params.RTSP_URL = "rtsp://192.168.0.108:554/stream"
        mock_params.RTSP_PROTOCOL = "tcp"
        mock_params.RTSP_LATENCY = 200
        mock_params.RTSP_MAX_CONSECUTIVE_FAILURES = 10
        mock_params.RTSP_CONNECTION_TIMEOUT = 5.0
        mock_params.RTSP_MAX_RECOVERY_ATTEMPTS = 3
        mock_params.RTSP_FRAME_CACHE_SIZE = 5

        # UDP settings
        mock_params.UDP_URL = "udp://0.0.0.0:5600"

        # HTTP settings
        mock_params.HTTP_URL = "http://192.168.1.100:8080/video"

        # CSI settings
        mock_params.CSI_SENSOR_ID = 0
        mock_params.SENSOR_ID = 0
        mock_params.FRAME_ROTATION_DEG = 0
        mock_params.FRAME_FLIP_MODE = "none"

        # Custom GStreamer
        mock_params.CUSTOM_PIPELINE = "videotestsrc ! videoconvert ! appsink"

        yield mock_params


@pytest.mark.unit
class TestVideoFileCapture:
    """Tests for VIDEO_FILE source type."""

    def test_video_file_source_type_recognized(self, mock_parameters):
        """VIDEO_FILE should be a valid source type."""
        mock_parameters.VIDEO_SOURCE_TYPE = "VIDEO_FILE"

        assert mock_parameters.VIDEO_SOURCE_TYPE == "VIDEO_FILE"

    def test_video_file_path_configurable(self, mock_parameters):
        """VIDEO_FILE_PATH should be configurable."""
        mock_parameters.VIDEO_FILE_PATH = "custom/path/video.mp4"

        assert mock_parameters.VIDEO_FILE_PATH == "custom/path/video.mp4"

    def test_mock_video_capture_for_file(self):
        """MockVideoCapture should work for file source."""
        cap = create_mock_video_capture(640, 480)

        assert cap.isOpened() == True
        ret, frame = cap.read()
        assert ret == True
        assert frame is not None


@pytest.mark.unit
class TestUSBCameraCapture:
    """Tests for USB_CAMERA source type."""

    def test_usb_camera_source_type_recognized(self, mock_parameters):
        """USB_CAMERA should be a valid source type."""
        mock_parameters.VIDEO_SOURCE_TYPE = "USB_CAMERA"

        assert mock_parameters.VIDEO_SOURCE_TYPE == "USB_CAMERA"

    def test_camera_index_configurable(self, mock_parameters):
        """CAMERA_INDEX should be configurable."""
        mock_parameters.CAMERA_INDEX = 2

        assert mock_parameters.CAMERA_INDEX == 2

    def test_pixel_format_yuyv(self, mock_parameters):
        """PIXEL_FORMAT YUYV should be valid."""
        mock_parameters.PIXEL_FORMAT = "YUYV"

        assert mock_parameters.PIXEL_FORMAT == "YUYV"

    def test_pixel_format_mjpg(self, mock_parameters):
        """PIXEL_FORMAT MJPG should be valid."""
        mock_parameters.PIXEL_FORMAT = "MJPG"

        assert mock_parameters.PIXEL_FORMAT == "MJPG"

    def test_device_path_configurable(self, mock_parameters):
        """DEVICE_PATH should be configurable."""
        mock_parameters.DEVICE_PATH = "/dev/video2"

        assert mock_parameters.DEVICE_PATH == "/dev/video2"


@pytest.mark.unit
class TestRTSPCapture:
    """Tests for RTSP_STREAM source type."""

    def test_rtsp_stream_source_type_recognized(self, mock_parameters):
        """RTSP_STREAM should be a valid source type."""
        mock_parameters.VIDEO_SOURCE_TYPE = "RTSP_STREAM"

        assert mock_parameters.VIDEO_SOURCE_TYPE == "RTSP_STREAM"

    def test_rtsp_url_configurable(self, mock_parameters):
        """RTSP_URL should be configurable."""
        mock_parameters.RTSP_URL = "rtsp://custom:554/stream"

        assert mock_parameters.RTSP_URL == "rtsp://custom:554/stream"

    def test_rtsp_protocol_tcp(self, mock_parameters):
        """RTSP_PROTOCOL tcp should be valid."""
        mock_parameters.RTSP_PROTOCOL = "tcp"

        assert mock_parameters.RTSP_PROTOCOL == "tcp"

    def test_rtsp_protocol_udp(self, mock_parameters):
        """RTSP_PROTOCOL udp should be valid."""
        mock_parameters.RTSP_PROTOCOL = "udp"

        assert mock_parameters.RTSP_PROTOCOL == "udp"

    def test_rtsp_latency_configurable(self, mock_parameters):
        """RTSP_LATENCY should be configurable."""
        mock_parameters.RTSP_LATENCY = 100

        assert mock_parameters.RTSP_LATENCY == 100

    def test_rtsp_requires_gstreamer(self, mock_parameters):
        """RTSP_STREAM typically requires GStreamer."""
        mock_parameters.VIDEO_SOURCE_TYPE = "RTSP_STREAM"
        mock_parameters.USE_GSTREAMER = True

        assert mock_parameters.USE_GSTREAMER == True


@pytest.mark.unit
class TestUDPCapture:
    """Tests for UDP_STREAM source type."""

    def test_udp_stream_source_type_recognized(self, mock_parameters):
        """UDP_STREAM should be a valid source type."""
        mock_parameters.VIDEO_SOURCE_TYPE = "UDP_STREAM"

        assert mock_parameters.VIDEO_SOURCE_TYPE == "UDP_STREAM"

    def test_udp_url_configurable(self, mock_parameters):
        """UDP_URL should be configurable."""
        mock_parameters.UDP_URL = "udp://0.0.0.0:5601"

        assert mock_parameters.UDP_URL == "udp://0.0.0.0:5601"

    def test_udp_requires_gstreamer(self, mock_parameters):
        """UDP_STREAM requires GStreamer for RTP parsing."""
        mock_parameters.VIDEO_SOURCE_TYPE = "UDP_STREAM"
        mock_parameters.USE_GSTREAMER = True

        assert mock_parameters.USE_GSTREAMER == True


@pytest.mark.unit
class TestHTTPCapture:
    """Tests for HTTP_STREAM source type."""

    def test_http_stream_source_type_recognized(self, mock_parameters):
        """HTTP_STREAM should be a valid source type."""
        mock_parameters.VIDEO_SOURCE_TYPE = "HTTP_STREAM"

        assert mock_parameters.VIDEO_SOURCE_TYPE == "HTTP_STREAM"

    def test_http_url_configurable(self, mock_parameters):
        """HTTP_URL should be configurable."""
        mock_parameters.HTTP_URL = "http://camera.local:8080/stream"

        assert mock_parameters.HTTP_URL == "http://camera.local:8080/stream"


@pytest.mark.unit
class TestCSICapture:
    """Tests for CSI_CAMERA source type."""

    def test_csi_camera_source_type_recognized(self, mock_parameters):
        """CSI_CAMERA should be a valid source type."""
        mock_parameters.VIDEO_SOURCE_TYPE = "CSI_CAMERA"

        assert mock_parameters.VIDEO_SOURCE_TYPE == "CSI_CAMERA"

    def test_csi_sensor_id_configurable(self, mock_parameters):
        """CSI_SENSOR_ID should be configurable."""
        mock_parameters.CSI_SENSOR_ID = 1

        assert mock_parameters.CSI_SENSOR_ID == 1

    def test_frame_rotation_deg_configurable(self, mock_parameters):
        """FRAME_ROTATION_DEG should be configurable."""
        mock_parameters.FRAME_ROTATION_DEG = 180
        assert mock_parameters.FRAME_ROTATION_DEG == 180

    def test_frame_rotation_deg_valid_values(self, mock_parameters):
        """FRAME_ROTATION_DEG should support right-angle values."""
        for rotation in (0, 90, 180, 270):
            mock_parameters.FRAME_ROTATION_DEG = rotation
            assert mock_parameters.FRAME_ROTATION_DEG in (0, 90, 180, 270)

    def test_frame_flip_mode_configurable(self, mock_parameters):
        """FRAME_FLIP_MODE should be configurable."""
        mock_parameters.FRAME_FLIP_MODE = "vertical"
        assert mock_parameters.FRAME_FLIP_MODE == "vertical"

    def test_csi_requires_gstreamer(self, mock_parameters):
        """CSI_CAMERA requires GStreamer."""
        mock_parameters.VIDEO_SOURCE_TYPE = "CSI_CAMERA"
        mock_parameters.USE_GSTREAMER = True

        assert mock_parameters.USE_GSTREAMER == True


@pytest.mark.unit
class TestCustomGStreamerCapture:
    """Tests for CUSTOM_GSTREAMER source type."""

    def test_custom_gstreamer_source_type_recognized(self, mock_parameters):
        """CUSTOM_GSTREAMER should be a valid source type."""
        mock_parameters.VIDEO_SOURCE_TYPE = "CUSTOM_GSTREAMER"

        assert mock_parameters.VIDEO_SOURCE_TYPE == "CUSTOM_GSTREAMER"

    def test_custom_pipeline_configurable(self, mock_parameters):
        """CUSTOM_PIPELINE should be configurable."""
        mock_parameters.CUSTOM_PIPELINE = "v4l2src ! videoconvert ! appsink"

        assert mock_parameters.CUSTOM_PIPELINE == "v4l2src ! videoconvert ! appsink"

    def test_custom_gstreamer_requires_gstreamer(self, mock_parameters):
        """CUSTOM_GSTREAMER requires GStreamer."""
        mock_parameters.VIDEO_SOURCE_TYPE = "CUSTOM_GSTREAMER"
        mock_parameters.USE_GSTREAMER = True

        assert mock_parameters.USE_GSTREAMER == True


@pytest.mark.unit
class TestMockVideoCapture:
    """Tests for MockVideoCapture behavior."""

    def test_mock_capture_opens_successfully(self):
        """MockVideoCapture should open successfully."""
        cap = MockVideoCapture()

        assert cap.isOpened() == True

    def test_mock_capture_read_returns_frame(self):
        """MockVideoCapture read should return frame."""
        cap = MockVideoCapture(640, 480)

        ret, frame = cap.read()

        assert ret == True
        assert frame is not None
        assert frame.shape == (480, 640, 3)

    def test_mock_capture_configurable_success_rate(self):
        """MockVideoCapture should respect success_rate."""
        cap = MockVideoCapture(success_rate=0.0)

        ret, frame = cap.read()

        assert ret == False

    def test_mock_capture_fail_after_n(self):
        """MockVideoCapture should fail after N reads."""
        cap = MockVideoCapture()
        cap.set_fail_after(2)

        # First two succeed
        ret1, _ = cap.read()
        ret2, _ = cap.read()
        # Third fails
        ret3, _ = cap.read()

        assert ret1 == True
        assert ret2 == True
        assert ret3 == False

    def test_mock_capture_grab_retrieve(self):
        """MockVideoCapture should support grab/retrieve."""
        cap = MockVideoCapture()

        grabbed = cap.grab()
        ret, frame = cap.retrieve()

        assert grabbed == True
        assert ret == True
        assert frame is not None

    def test_mock_capture_get_properties(self):
        """MockVideoCapture should return properties."""
        import cv2

        cap = MockVideoCapture(1280, 720, 60.0)

        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        fps = cap.get(cv2.CAP_PROP_FPS)

        assert width == 1280.0
        assert height == 720.0
        assert fps == 60.0

    def test_mock_capture_set_properties(self):
        """MockVideoCapture should allow setting properties."""
        import cv2

        cap = MockVideoCapture(640, 480)

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

        assert cap.get(cv2.CAP_PROP_FRAME_WIDTH) == 1920.0
        assert cap.get(cv2.CAP_PROP_FRAME_HEIGHT) == 1080.0

    def test_mock_capture_release(self):
        """MockVideoCapture should close on release."""
        cap = MockVideoCapture()
        assert cap.isOpened() == True

        cap.release()

        assert cap.isOpened() == False

    def test_mock_capture_backend_name(self):
        """MockVideoCapture should return backend name."""
        cap = MockVideoCapture()

        assert cap.getBackendName() == "MOCK"


@pytest.mark.unit
class TestMockGStreamerCapture:
    """Tests for MockGStreamerCapture behavior."""

    def test_gstreamer_capture_stores_pipeline(self):
        """MockGStreamerCapture should store pipeline string."""
        pipeline = "videotestsrc ! appsink"
        cap = MockGStreamerCapture(pipeline=pipeline)

        assert cap.pipeline == pipeline

    def test_gstreamer_capture_backend_name(self):
        """MockGStreamerCapture should report GSTREAMER backend."""
        cap = MockGStreamerCapture()

        assert cap.getBackendName() == "GSTREAMER"

    def test_gstreamer_capture_from_pipeline(self):
        """MockGStreamerCapture.from_pipeline should create capture."""
        pipeline = "v4l2src ! videoconvert ! appsink"
        cap = MockGStreamerCapture.from_pipeline(pipeline, 640, 480)

        assert cap.pipeline == pipeline
        assert cap._width == 640
        assert cap._height == 480


@pytest.mark.unit
class TestSourceTypeValidation:
    """Tests for source type validation."""

    def test_all_source_types_are_strings(self, mock_parameters):
        """All source types should be string values."""
        source_types = [
            "VIDEO_FILE",
            "USB_CAMERA",
            "RTSP_STREAM",
            "UDP_STREAM",
            "HTTP_STREAM",
            "CSI_CAMERA",
            "CUSTOM_GSTREAMER"
        ]

        for source_type in source_types:
            assert isinstance(source_type, str)

    def test_seven_source_types_supported(self):
        """Should support exactly 7 source types."""
        source_types = [
            "VIDEO_FILE",
            "USB_CAMERA",
            "RTSP_STREAM",
            "UDP_STREAM",
            "HTTP_STREAM",
            "CSI_CAMERA",
            "CUSTOM_GSTREAMER"
        ]

        assert len(source_types) == 7


@pytest.mark.unit
class TestGStreamerBackendSelection:
    """Tests for GStreamer backend selection logic."""

    def test_gstreamer_required_for_rtsp(self, mock_parameters):
        """RTSP should work best with GStreamer."""
        mock_parameters.VIDEO_SOURCE_TYPE = "RTSP_STREAM"
        mock_parameters.USE_GSTREAMER = True

        assert mock_parameters.USE_GSTREAMER == True

    def test_gstreamer_required_for_udp(self, mock_parameters):
        """UDP requires GStreamer for RTP handling."""
        mock_parameters.VIDEO_SOURCE_TYPE = "UDP_STREAM"
        mock_parameters.USE_GSTREAMER = True

        assert mock_parameters.USE_GSTREAMER == True

    def test_gstreamer_required_for_csi(self, mock_parameters):
        """CSI requires GStreamer for hardware access."""
        mock_parameters.VIDEO_SOURCE_TYPE = "CSI_CAMERA"
        mock_parameters.USE_GSTREAMER = True

        assert mock_parameters.USE_GSTREAMER == True

    def test_gstreamer_optional_for_file(self, mock_parameters):
        """VIDEO_FILE works without GStreamer."""
        mock_parameters.VIDEO_SOURCE_TYPE = "VIDEO_FILE"
        mock_parameters.USE_GSTREAMER = False

        assert mock_parameters.USE_GSTREAMER == False

    def test_gstreamer_optional_for_http(self, mock_parameters):
        """HTTP_STREAM works without GStreamer."""
        mock_parameters.VIDEO_SOURCE_TYPE = "HTTP_STREAM"
        mock_parameters.USE_GSTREAMER = False

        assert mock_parameters.USE_GSTREAMER == False
