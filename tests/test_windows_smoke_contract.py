"""Cross-platform unit contracts for the native Windows media smoke probe."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest
from PIL import Image


pytestmark = pytest.mark.unit
REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_PATH = REPO_ROOT / "scripts" / "windows" / "smoke.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location(
        "pixeagle_windows_smoke_contract",
        SMOKE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ice_candidate_decoder_accepts_browser_shape():
    module = _load_smoke_module()

    candidate = module._decode_ice_candidate(
        {
            "candidate": {
                "candidate": (
                    "candidate:foundation 1 udp 2130706431 "
                    "127.0.0.1 50000 typ host"
                ),
                "sdpMid": "0",
                "sdpMLineIndex": 0,
            }
        }
    )

    assert candidate is not None
    assert candidate.foundation == "foundation"
    assert candidate.ip == "127.0.0.1"
    assert candidate.sdpMid == "0"
    assert candidate.sdpMLineIndex == 0


def test_smoke_cli_refuses_non_loopback_target():
    module = _load_smoke_module()

    assert module.main(["--host", "192.0.2.10"]) == 2


def test_jpeg_probe_requires_an_actually_decodable_image():
    module = _load_smoke_module()
    payload = io.BytesIO()
    Image.new("RGB", (8, 6), color=(10, 20, 30)).save(payload, format="JPEG")

    assert module._decode_jpeg(payload.getvalue(), "test") == (8, 6)
    with pytest.raises(module.SmokeError, match="could not be decoded"):
        module._decode_jpeg(b"\xff\xd8not-a-jpeg\xff\xd9", "test")
