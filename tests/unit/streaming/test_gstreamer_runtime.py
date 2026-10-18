"""Managed native plugins are scoped to the selected Python environment."""

import sys
from types import SimpleNamespace

import pytest

from classes.gstreamer_runtime import load_gstreamer

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


@pytest.mark.parametrize("plugin_installed", [True, False])
def test_optional_loader_discovers_only_active_venv_plugins(monkeypatch, tmp_path, plugin_installed):
    calls = []
    plugin_dir = tmp_path / "lib/gstreamer-1.0"
    if plugin_installed:
        plugin_dir.mkdir(parents=True)
    gst = SimpleNamespace(init=lambda value: calls.append(("init", value)),
                          Registry=SimpleNamespace(get=lambda: SimpleNamespace(scan_path=lambda path: calls.append(("scan", path)))))
    repository = SimpleNamespace(Gst=gst, GstRtp=object(), GstSdp=object(), GstWebRTC=object(), GstVideo=object())
    gi = SimpleNamespace(require_version=lambda name, version: calls.append((name, version)))
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    before_path = tuple(sys.path)
    runtime = load_gstreamer.__wrapped__()
    assert runtime[0] is gst
    assert ("GstWebRTC", "1.0") in calls
    assert (("scan", str(plugin_dir)) in calls) is plugin_installed
    assert tuple(sys.path) == before_path
