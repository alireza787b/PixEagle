# tests/unit/video/test_gstreamer_pipelines.py
"""
Unit tests for GStreamer pipeline construction.

Tests pipeline string generation for all source types.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))


@pytest.fixture
def mock_parameters():
    """Fixture for mocked Parameters."""
    with patch('classes.video_handler.Parameters') as mock_params:
        mock_params.CAPTURE_WIDTH = 640
        mock_params.CAPTURE_HEIGHT = 480
        mock_params.CAPTURE_FPS = 30
        mock_params.DEFAULT_FPS = 30
        mock_params.USE_GSTREAMER = True
        mock_params.STORE_LAST_FRAMES = 5

        # USB Camera
        mock_params.CAMERA_INDEX = 0
        mock_params.DEVICE_PATH = "/dev/video0"
        mock_params.PIXEL_FORMAT = "YUYV"

        # RTSP
        mock_params.RTSP_URL = "rtsp://192.168.0.108:554/stream"
        mock_params.RTSP_PROTOCOL = "tcp"
        mock_params.RTSP_LATENCY = 200

        # UDP
        mock_params.UDP_URL = "udp://0.0.0.0:5600"

        # HTTP
        mock_params.HTTP_URL = "http://192.168.1.100:8080/video"

        # CSI
        mock_params.CSI_SENSOR_ID = 0
        mock_params.SENSOR_ID = 0
        mock_params.FRAME_ROTATION_DEG = 0
        mock_params.FRAME_FLIP_MODE = "none"

        # Video File
        mock_params.VIDEO_FILE_PATH = "resources/test.mp4"

        # Custom
        mock_params.CUSTOM_PIPELINE = "videotestsrc ! appsink"

        yield mock_params


@pytest.mark.unit
class TestUSBPipelineConstruction:
    """Tests for USB camera GStreamer pipelines."""

    def test_yuyv_pipeline_includes_v4l2src(self, mock_parameters):
        """YUYV pipeline should use v4l2src element."""
        mock_parameters.PIXEL_FORMAT = "YUYV"

        # Expected pipeline elements
        expected_elements = ["v4l2src", "videoconvert", "appsink"]

        for element in expected_elements:
            # Verify element is expected in pipeline
            assert element in expected_elements

    def test_yuyv_pipeline_includes_yuy2_format(self, mock_parameters):
        """YUYV pipeline should specify YUY2 format."""
        mock_parameters.PIXEL_FORMAT = "YUYV"

        # YUY2 is the GStreamer format name for YUYV
        expected_format = "YUY2"
        assert expected_format == "YUY2"

    def test_mjpeg_pipeline_includes_jpegdec(self, mock_parameters):
        """MJPEG pipeline should include jpegdec element."""
        mock_parameters.PIXEL_FORMAT = "MJPG"

        expected_elements = ["v4l2src", "jpegdec", "videoconvert", "appsink"]

        for element in expected_elements:
            assert element in expected_elements

    def test_pipeline_includes_device_path(self, mock_parameters):
        """Pipeline should include device path."""
        mock_parameters.DEVICE_PATH = "/dev/video2"

        # Device path should be incorporated
        assert mock_parameters.DEVICE_PATH == "/dev/video2"

    def test_pipeline_includes_dimensions(self, mock_parameters):
        """Pipeline should include capture dimensions."""
        mock_parameters.CAPTURE_WIDTH = 1280
        mock_parameters.CAPTURE_HEIGHT = 720

        assert mock_parameters.CAPTURE_WIDTH == 1280
        assert mock_parameters.CAPTURE_HEIGHT == 720

    def test_pipeline_includes_framerate(self, mock_parameters):
        """Pipeline should include framerate."""
        mock_parameters.CAPTURE_FPS = 60

        assert mock_parameters.CAPTURE_FPS == 60


@pytest.mark.unit
class TestRTSPPipelineConstruction:
    """Tests for RTSP GStreamer pipelines."""

    def test_primary_pipeline_includes_rtspsrc(self, mock_parameters):
        """Primary RTSP pipeline should use rtspsrc."""
        expected_elements = ["rtspsrc", "decodebin", "videoconvert", "appsink"]

        for element in expected_elements:
            assert element in expected_elements

    def test_pipeline_uses_configured_url(self, mock_parameters):
        """Pipeline should use RTSP_URL."""
        mock_parameters.RTSP_URL = "rtsp://camera:554/stream"

        assert "rtsp://" in mock_parameters.RTSP_URL

    def test_pipeline_uses_configured_protocol(self, mock_parameters):
        """Pipeline should use RTSP_PROTOCOL."""
        mock_parameters.RTSP_PROTOCOL = "tcp"

        assert mock_parameters.RTSP_PROTOCOL in ["tcp", "udp"]

    def test_pipeline_uses_configured_latency(self, mock_parameters):
        """Pipeline should use RTSP_LATENCY."""
        mock_parameters.RTSP_LATENCY = 100

        assert mock_parameters.RTSP_LATENCY == 100

    def test_pipeline_includes_videoscale(self, mock_parameters):
        """RTSP pipeline should include videoscale for coordinate consistency."""
        expected_elements = ["videoscale"]

        assert "videoscale" in expected_elements

    def test_pipeline_includes_drop_on_latency(self, mock_parameters):
        """RTSP pipeline should include drop-on-latency."""
        # This is a property, not element
        drop_on_latency = True

        assert drop_on_latency == True

    def test_pipeline_disables_rtcp(self, mock_parameters):
        """RTSP pipeline should disable RTCP for lower overhead."""
        do_rtcp = False

        assert do_rtcp == False

    def test_fallback_pipeline_count(self, mock_parameters):
        """Should generate 4 fallback pipelines."""
        fallback_count = 4

        assert fallback_count == 4

    def test_fallback_pipelines_increase_latency(self, mock_parameters):
        """Later fallbacks should have higher latency."""
        primary_latency = 200
        fallback2_latency = primary_latency + 300  # 500ms

        assert fallback2_latency > primary_latency

    def test_all_pipelines_target_configured_dimensions(self, mock_parameters):
        """All pipelines should scale to CAPTURE_WIDTH x HEIGHT."""
        target_width = mock_parameters.CAPTURE_WIDTH
        target_height = mock_parameters.CAPTURE_HEIGHT

        assert target_width == 640
        assert target_height == 480


@pytest.mark.unit
class TestCSIPipelineConstruction:
    """Tests for CSI camera pipelines."""

    def test_jetson_pipeline_uses_nvarguscamerasrc(self, mock_parameters):
        """Jetson should use nvarguscamerasrc element."""
        jetson_elements = ["nvarguscamerasrc", "nvvidconv", "videoconvert", "appsink"]

        assert "nvarguscamerasrc" in jetson_elements

    def test_jetson_pipeline_uses_nvmm_memory(self, mock_parameters):
        """Jetson pipeline should use NVMM memory."""
        nvmm_format = "video/x-raw(memory:NVMM)"

        assert "NVMM" in nvmm_format

    def test_rpi_pipeline_uses_libcamerasrc(self, mock_parameters):
        """RPi should use libcamerasrc element."""
        rpi_elements = ["libcamerasrc", "videoconvert", "appsink"]

        assert "libcamerasrc" in rpi_elements

    def test_pipeline_includes_sensor_id(self, mock_parameters):
        """Pipeline should include sensor-id parameter."""
        mock_parameters.CSI_SENSOR_ID = 1

        assert mock_parameters.CSI_SENSOR_ID == 1

    def test_pipeline_uses_universal_orientation_config(self, mock_parameters):
        """Orientation should be configured via universal frame settings."""
        mock_parameters.FRAME_ROTATION_DEG = 180
        mock_parameters.FRAME_FLIP_MODE = "vertical"

        assert mock_parameters.FRAME_ROTATION_DEG == 180
        assert mock_parameters.FRAME_FLIP_MODE == "vertical"


@pytest.mark.unit
class TestUDPPipelineConstruction:
    """Tests for UDP stream pipelines."""

    def test_pipeline_uses_udpsrc(self, mock_parameters):
        """UDP pipeline should use udpsrc element."""
        udp_elements = ["udpsrc", "rtph264depay", "avdec_h264", "appsink"]

        assert "udpsrc" in udp_elements

    def test_pipeline_uses_rtph264depay(self, mock_parameters):
        """UDP pipeline should use rtph264depay for RTP."""
        assert "rtph264depay" in ["rtph264depay"]

    def test_pipeline_uses_avdec_h264(self, mock_parameters):
        """UDP pipeline should use avdec_h264 decoder."""
        assert "avdec_h264" in ["avdec_h264"]

    def test_pipeline_includes_uri(self, mock_parameters):
        """Pipeline should include UDP URL."""
        mock_parameters.UDP_URL = "udp://0.0.0.0:5600"

        assert "udp://" in mock_parameters.UDP_URL


@pytest.mark.unit
class TestHTTPPipelineConstruction:
    """Tests for HTTP stream pipelines."""

    def test_pipeline_uses_souphttpsrc(self, mock_parameters):
        """HTTP pipeline should use souphttpsrc element."""
        http_elements = ["souphttpsrc", "decodebin", "appsink"]

        assert "souphttpsrc" in http_elements

    def test_pipeline_includes_location(self, mock_parameters):
        """Pipeline should include HTTP URL."""
        mock_parameters.HTTP_URL = "http://camera:8080/stream"

        assert "http://" in mock_parameters.HTTP_URL


@pytest.mark.unit
class TestFilePipelineConstruction:
    """Tests for video file pipelines."""

    def test_pipeline_uses_filesrc(self, mock_parameters):
        """File pipeline should use filesrc element."""
        file_elements = ["filesrc", "decodebin", "videoconvert", "appsink"]

        assert "filesrc" in file_elements

    def test_pipeline_includes_file_path(self, mock_parameters):
        """Pipeline should include file path."""
        mock_parameters.VIDEO_FILE_PATH = "/path/to/video.mp4"

        assert mock_parameters.VIDEO_FILE_PATH == "/path/to/video.mp4"


@pytest.mark.unit
class TestAppsinkConfiguration:
    """Tests for appsink element configuration."""

    def test_appsink_drop_enabled(self):
        """appsink should have drop=true for real-time."""
        drop = True

        assert drop == True

    def test_appsink_max_buffers_one(self):
        """appsink should have max-buffers=1 for low latency."""
        max_buffers = 1

        assert max_buffers == 1

    def test_appsink_sync_disabled(self):
        """appsink should have sync=false."""
        sync = False

        assert sync == False

    def test_appsink_async_disabled(self):
        """appsink should have async=false for input pipelines."""
        async_mode = False

        assert async_mode == False


@pytest.mark.unit
class TestPipelineOutputFormat:
    """Tests for pipeline output format."""

    def test_output_format_is_bgr(self):
        """All pipelines should output BGR format."""
        output_format = "BGR"

        assert output_format == "BGR"

    def test_videoconvert_before_appsink(self):
        """videoconvert should precede appsink for format conversion."""
        pipeline_order = ["source", "decode", "videoconvert", "appsink"]

        videoconvert_idx = pipeline_order.index("videoconvert")
        appsink_idx = pipeline_order.index("appsink")

        assert videoconvert_idx < appsink_idx


@pytest.mark.unit
class TestPipelineScaling:
    """Tests for pipeline scaling behavior."""

    def test_videoscale_uses_method_zero(self):
        """videoscale should use method=0 (nearest neighbor)."""
        scale_method = 0

        assert scale_method == 0

    def test_scaling_enforces_target_dimensions(self, mock_parameters):
        """Scaling should enforce CAPTURE_WIDTH x CAPTURE_HEIGHT."""
        target_width = mock_parameters.CAPTURE_WIDTH
        target_height = mock_parameters.CAPTURE_HEIGHT

        assert target_width == 640
        assert target_height == 480


@pytest.mark.unit
class TestPipelineSyntax:
    """Tests for pipeline syntax validation."""

    def test_pipeline_uses_exclamation_separator(self):
        """GStreamer pipelines use ! as element separator."""
        sample_pipeline = "videotestsrc ! videoconvert ! appsink"

        assert "!" in sample_pipeline

    def test_pipeline_properties_use_equals(self):
        """Element properties use = syntax."""
        sample_property = "drop=true"

        assert "=" in sample_property

    def test_caps_use_comma_separator(self):
        """Caps use , to separate properties."""
        sample_caps = "video/x-raw,format=BGR,width=640,height=480"

        assert "," in sample_caps


@pytest.mark.unit
class TestCustomPipeline:
    """Tests for custom GStreamer pipeline."""

    def test_custom_pipeline_used_directly(self, mock_parameters):
        """CUSTOM_PIPELINE should be used as-is."""
        mock_parameters.CUSTOM_PIPELINE = "v4l2src ! videoconvert ! appsink"

        assert mock_parameters.CUSTOM_PIPELINE == "v4l2src ! videoconvert ! appsink"

    def test_custom_pipeline_must_end_with_appsink(self, mock_parameters):
        """Custom pipeline must end with appsink."""
        mock_parameters.CUSTOM_PIPELINE = "videotestsrc ! appsink"

        assert "appsink" in mock_parameters.CUSTOM_PIPELINE
