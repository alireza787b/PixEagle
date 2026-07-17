"""Regression coverage for browser/GCS OSD resolution isolation."""

from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np
import pytest

from classes.osd_pipeline import OSDPipeline
from classes.osd_renderer import OSDRenderer
from classes.osd_text_renderer import OSDTextRenderer
from classes.parameters import Parameters


pytestmark = [pytest.mark.unit]


class _SharedRenderer:
    def __init__(self):
        self.current_size = (1280, 720)
        self.direct_sizes = []

    def sync_frame_size(self, frame_shape):
        frame_height, frame_width = frame_shape[:2]
        self.current_size = (frame_width, frame_height)

    def _get_color_mode_tag(self):
        return "test"

    def get_performance_mode(self):
        return "quality"

    def draw_direct_elements(self, frame, layer_filter=None):
        self.direct_sizes.append(self.current_size)
        return frame


class _OSDHandler:
    def __init__(self, renderer):
        self.renderer = renderer

    def is_enabled(self):
        return True

    def set_enabled(self, enabled):
        assert enabled is True


def _prime_cached_pipeline(pipeline, renderer, width, height):
    pipeline._sprite_cache = {"cached": SimpleNamespace(content_hash="cached")}
    pipeline._sprite_list = []
    pipeline._sprite_list_dirty = False
    pipeline._last_shape = (width, height)
    pipeline._last_renderer_id = id(renderer)
    pipeline._last_enabled = True
    pipeline._last_preset = str(getattr(Parameters, "OSD_PRESET", "professional"))
    pipeline._last_color_mode = "test"
    now = time.perf_counter()
    pipeline._last_slow_update_ts = now
    pipeline._last_dynamic_update_ts = now


def test_alternating_cached_pipelines_sync_direct_geometry_to_each_frame(monkeypatch):
    monkeypatch.setattr(Parameters, "OSD_ENABLED", True, raising=False)
    monkeypatch.setattr(OSDTextRenderer, "blit_sprites", lambda frame, sprites: None)
    renderer = _SharedRenderer()
    handler = _OSDHandler(renderer)
    browser_pipeline = OSDPipeline(handler)
    gcs_pipeline = OSDPipeline(handler)
    _prime_cached_pipeline(browser_pipeline, renderer, 640, 480)
    _prime_cached_pipeline(gcs_pipeline, renderer, 1280, 720)

    browser_pipeline.compose(np.zeros((480, 640, 3), dtype=np.uint8))
    gcs_pipeline.compose(np.zeros((720, 1280, 3), dtype=np.uint8))

    assert renderer.direct_sizes == [(640, 480), (1280, 720)]


def test_renderer_frame_size_sync_updates_all_dimension_consumers():
    renderer = OSDRenderer.__new__(OSDRenderer)
    renderer.frame_width = 640
    renderer.frame_height = 480
    text_updates = []
    layout_updates = []
    renderer.text_renderer = SimpleNamespace(
        update_frame_size=lambda width, height: text_updates.append((width, height))
    )
    renderer.layout_manager = SimpleNamespace(
        update_frame_size=lambda width, height: layout_updates.append((width, height))
    )

    renderer.sync_frame_size((720, 1280, 3))
    renderer.sync_frame_size((720, 1280, 3))

    assert (renderer.frame_width, renderer.frame_height) == (1280, 720)
    assert text_updates == [(1280, 720)]
    assert layout_updates == [(1280, 720)]
