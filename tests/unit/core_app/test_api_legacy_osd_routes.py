"""Tests for legacy OSD route helper extraction."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from classes import api_legacy_osd_routes as routes
from classes.parameters import Parameters


pytestmark = [pytest.mark.unit]


class FakeOSDHandler:
    def __init__(self, enabled=True) -> None:
        self.enabled = enabled
        self.set_calls = []

    def is_enabled(self):
        return self.enabled

    def set_enabled(self, value):
        self.enabled = value
        self.set_calls.append(value)

    def get_performance_stats(self):
        return {"fps": 12.5, "frames_rendered": 42}


class FakeOSDPipeline:
    def __init__(self) -> None:
        self.invalidations = []

    def get_stats(self):
        return {"cache_hits": 4}

    def invalidate_cache(self, reason):
        self.invalidations.append(reason)


class FakeModeManager:
    def __init__(self, color_mode="day", switch_success=True) -> None:
        self.color_mode = color_mode
        self.switch_success = switch_success
        self.switch_calls = []

    def switch_color_mode(self, mode):
        self.switch_calls.append(mode)
        if self.switch_success:
            self.color_mode = mode
        return self.switch_success

    def get_status(self):
        return {
            "color_mode": self.color_mode,
            "available_presets": ["professional", "minimal"],
        }


def make_handler(*, osd=True, pipeline=True, mode_manager=True):
    app_controller = SimpleNamespace()
    if osd:
        app_controller.osd_handler = FakeOSDHandler()
    if pipeline:
        app_controller.osd_pipeline = FakeOSDPipeline()
    if mode_manager:
        app_controller.osd_mode_manager = FakeModeManager()
    return SimpleNamespace(
        app_controller=app_controller,
        logger=logging.getLogger("test.api_legacy_osd_routes"),
    )


def response_body(response):
    return json.loads(response.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_status_and_toggle_preserve_legacy_payload_shape(monkeypatch):
    monkeypatch.setattr(Parameters, "OSD_ENABLED", True, raising=False)
    monkeypatch.setattr(Parameters, "OSD_PRESET", "professional", raising=False)
    handler = make_handler()

    status = response_body(await routes.get_osd_status(handler))
    toggled = response_body(await routes.toggle_osd(handler))

    assert status["available"] is True
    assert status["enabled"] is True
    assert status["configuration"]["current_preset"] == "professional"
    assert status["configuration"]["color_mode"] == "day"
    assert status["performance"] == {"fps": 12.5, "frames_rendered": 42}
    assert status["pipeline"] == {"cache_hits": 4}
    assert toggled["status"] == "success"
    assert toggled["enabled"] is False
    assert toggled["old_state"] is True
    assert toggled["new_state"] is False
    assert handler.app_controller.osd_handler.set_calls == [False]
    assert handler.app_controller.osd_pipeline.invalidations == ["toggle_osd"]
    assert Parameters.OSD_ENABLED is False


@pytest.mark.asyncio
async def test_unavailable_osd_status_and_toggle_keep_legacy_semantics():
    handler = make_handler(osd=False)

    status = response_body(await routes.get_osd_status(handler))

    assert status == {
        "available": False,
        "error": "OSD system not available",
    }

    with pytest.raises(HTTPException) as exc:
        await routes.toggle_osd(handler)
    assert exc.value.status_code == 500
    assert "OSD system not available" in exc.value.detail


@pytest.mark.asyncio
async def test_presets_list_load_and_validate_relative_config_dir(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Parameters, "OSD_PRESET", "professional", raising=False)
    presets_dir = tmp_path / "configs" / "osd_presets"
    presets_dir.mkdir(parents=True)
    (presets_dir / "minimal.yaml").write_text("ELEMENTS:\n  altitude: {}\n")
    (presets_dir / "professional.yaml").write_text(
        "ELEMENTS:\n  altitude: {}\n  speed: {}\n"
    )

    handler = make_handler(osd=False)

    listed = response_body(await routes.get_osd_presets(handler))
    loaded = response_body(await routes.load_osd_preset(handler, "professional"))

    assert listed["available"] is True
    assert listed["presets"] == ["professional", "minimal"]
    assert listed["current"] == "professional"
    assert listed["presets_directory"] == "configs/osd_presets"
    assert loaded["status"] == "success"
    assert loaded["old_preset"] == "professional"
    assert loaded["new_preset"] == "professional"
    assert loaded["element_count"] == 2
    assert loaded["requires_restart"] is False

    with pytest.raises(HTTPException) as invalid_exc:
        await routes.load_osd_preset(handler, "../bad")
    with pytest.raises(HTTPException) as missing_exc:
        await routes.load_osd_preset(handler, "missing")

    assert invalid_exc.value.status_code == 400
    assert invalid_exc.value.detail == "Invalid preset name"
    assert missing_exc.value.status_code == 404
    assert missing_exc.value.detail == "Preset 'missing' not found"


@pytest.mark.asyncio
async def test_presets_missing_directory_shape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    handler = make_handler(osd=False)

    presets = response_body(await routes.get_osd_presets(handler))

    assert presets == {
        "available": False,
        "error": "OSD presets directory not found",
        "presets": [],
    }


@pytest.mark.asyncio
async def test_color_mode_and_modes_routes_delegate_to_mode_manager():
    handler = make_handler()
    manager = handler.app_controller.osd_mode_manager

    color_modes = response_body(await routes.get_osd_color_modes(handler))
    switched = response_body(await routes.set_osd_color_mode(handler, "night"))
    modes = response_body(await routes.get_osd_modes(handler))

    assert color_modes["available_modes"] == ["day", "night", "amber"]
    assert color_modes["current"] == "day"
    assert switched["status"] == "success"
    assert switched["old_mode"] == "day"
    assert switched["new_mode"] == "night"
    assert manager.switch_calls == ["night"]
    assert modes["status"] == "success"
    assert modes["color_mode"] == "night"
    assert modes["available_presets"] == ["professional", "minimal"]


@pytest.mark.asyncio
async def test_color_mode_validation_errors():
    missing_handler = make_handler(mode_manager=False)
    failed_handler = make_handler()
    failed_handler.app_controller.osd_mode_manager = FakeModeManager(
        switch_success=False
    )

    with pytest.raises(HTTPException) as missing_exc:
        await routes.get_osd_color_modes(missing_handler)
    with pytest.raises(HTTPException) as invalid_exc:
        await routes.set_osd_color_mode(failed_handler, "infrared")
    with pytest.raises(HTTPException) as failed_exc:
        await routes.set_osd_color_mode(failed_handler, "amber")

    assert missing_exc.value.status_code == 503
    assert missing_exc.value.detail == "OSD mode manager not available"
    assert invalid_exc.value.status_code == 400
    assert "Invalid color mode 'infrared'" in invalid_exc.value.detail
    assert failed_exc.value.status_code == 500
    assert failed_exc.value.detail == "Failed to switch color mode"
