"""Lazy optional GStreamer loading, including the active venv's managed plugins."""

import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_gstreamer():
    import gi

    for namespace in ("Gst", "GstRtp", "GstSdp", "GstWebRTC", "GstVideo"):
        gi.require_version(namespace, "1.0")
    from gi.repository import Gst, GstRtp, GstSdp, GstWebRTC, GstVideo

    Gst.init(None)
    # Use the selected environment only; never expose all distro Python packages.
    plugin_dir = Path(sys.prefix) / "lib" / "gstreamer-1.0"
    if plugin_dir.is_dir():
        Gst.Registry.get().scan_path(str(plugin_dir))
    return Gst, GstRtp, GstSdp, GstWebRTC, GstVideo
