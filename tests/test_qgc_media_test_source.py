import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = PROJECT_ROOT / "tools" / "qgc_media_test_source.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("qgc_media_test_source", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_websocket_accept_key_matches_rfc_example():
    tool = load_tool()

    assert (
        tool.websocket_accept_key("dGhlIHNhbXBsZSBub25jZQ==")
        == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    )


def test_websocket_binary_frame_encodes_payload_lengths():
    tool = load_tool()

    short = tool.websocket_binary_frame(b"abc")
    assert short[:2] == bytes([0x82, 3])
    assert short[2:] == b"abc"

    medium_payload = b"x" * 130
    medium = tool.websocket_binary_frame(medium_payload)
    assert medium[:2] == bytes([0x82, 126])
    assert int.from_bytes(medium[2:4], "big") == len(medium_payload)
    assert medium[4:] == medium_payload


def test_embedded_frames_are_jpegs():
    tool = load_tool()

    assert len(tool.JPEG_FRAMES) >= 3
    assert len(set(tool.JPEG_FRAMES)) == len(tool.JPEG_FRAMES)
    for frame in tool.JPEG_FRAMES:
        assert frame.startswith(b"\xff\xd8")
        assert frame.endswith(b"\xff\xd9")
        assert len(frame) > 1000


def test_handler_uses_http_11_for_websocket_clients():
    tool = load_tool()

    assert tool.QGCMediaTestHandler.protocol_version == "HTTP/1.1"
