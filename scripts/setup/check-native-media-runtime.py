#!/usr/bin/env python3
"""Probe optional native-media dependencies in the selected PixEagle interpreter."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from classes.gstreamer_frame_association import gstreamer_capabilities


def main():
    runtime = gstreamer_capabilities()
    missing = runtime.get("missing_elements", {})
    ready = (runtime.get("available") and runtime.get("available_codecs")
             and not missing.get("webrtc_transport") and not missing.get("congestion_control"))
    print(json.dumps({**runtime, "runtime_ready": bool(ready)}, sort_keys=True))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
