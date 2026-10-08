"""Optional actual packet test; default installations need no GI package."""

import importlib.util

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


@pytest.mark.parametrize("codec", ["h264", "vp8"])
def test_actual_payloader_mapping_when_gstreamer_is_available(codec):
    if importlib.util.find_spec("gi") is None:
        pytest.skip("Optional GStreamer introspection is not installed")
    from classes.gstreamer_frame_association import gstreamer_capabilities
    from tools.qualify_gstreamer_association import qualify_codec

    capabilities = gstreamer_capabilities()
    if not capabilities["available"]:
        pytest.skip(capabilities["reason"])
    missing = capabilities["missing_elements"][f"{codec}_association"]
    if missing:
        pytest.skip(f"Optional {codec} elements not installed: {missing}")
    from gi.repository import Gst
    receiver_elements = ["rtpjitterbuffer", "rtph264depay", "avdec_h264"] if codec == "h264" else ["rtpjitterbuffer", "rtpvp8depay", "vp8dec"]
    if any(Gst.ElementFactory.find(name) is None for name in receiver_elements):
        pytest.skip("Optional receiver decoder plugins are not installed")
    result = qualify_codec(codec, decode_receiver=True)
    assert result["passed"]
    assert len(result["epochs"]) == 2
    assert all(epoch["receiver"]["passed"] for epoch in result["epochs"])
