"""Tests for legacy model/yolo route helper extraction."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from classes import api_legacy_model_routes as model_routes


pytestmark = [pytest.mark.unit]


class FakeLogger:
    def debug(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass

    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass


class FakeModelManager:
    def __init__(self, models):
        self.models = models
        self.folder = "."
        self.last_force_rescan = None

    def normalize_model_id(self, model_identifier):
        if model_identifier is None:
            return None
        return Path(str(model_identifier)).name

    def discover_models(self, force_rescan=False):
        self.last_force_rescan = force_rescan
        return self.models

    def get_model_labels(self, model_identifier, force_rescan=False):
        self.last_force_rescan = force_rescan
        model_info = self.models.get(model_identifier)
        if model_info is None:
            return None, []
        return model_info, list(model_info.get("class_names", []))


def _json_body(response):
    return json.loads(response.body.decode("utf-8"))


def test_build_active_model_summary_limits_label_preview():
    summary = model_routes.build_active_model_summary(
        model_id="demo.pt",
        model_info={
            "name": "Demo",
            "path": "models/demo.pt",
            "class_names": ["boat", "person", "car"],
            "is_custom": True,
            "has_ncnn": True,
        },
        runtime={
            "model_task": "detect",
            "geometry_mode": "obb",
            "backend": "ultralytics",
            "effective_device": "cpu",
        },
        source="runtime",
        label_preview_limit=2,
    )

    assert summary["model_id"] == "demo.pt"
    assert summary["task"] == "detect"
    assert summary["geometry_mode"] == "obb"
    assert summary["label_preview"] == ["boat", "person"]
    assert summary["has_more_labels"] is True
    assert summary["is_custom"] is True


@pytest.mark.asyncio
async def test_get_models_uses_runtime_model_and_force_rescan(tmp_path):
    model_path = tmp_path / "demo.pt"
    model_path.write_text("placeholder", encoding="utf-8")
    ncnn_dir = tmp_path / "demo_ncnn_model"
    ncnn_dir.mkdir()

    manager = FakeModelManager(
        {
            "demo.pt": {
                "name": "Demo",
                "path": str(model_path),
                "class_names": ["boat"],
                "task": "detect",
            }
        }
    )
    smart_tracker = SimpleNamespace(
        get_runtime_info=lambda: {
            "model_path": str(ncnn_dir),
            "model_task": "detect",
            "geometry_mode": "aabb",
            "backend": "test-backend",
            "effective_device": "cpu",
        }
    )
    handler = SimpleNamespace(
        app_controller=SimpleNamespace(smart_tracker=smart_tracker),
        model_manager=manager,
        logger=FakeLogger(),
    )
    request = SimpleNamespace(query_params={"force_rescan": "true"})

    response = await model_routes.get_models(handler, request)
    body = _json_body(response)

    assert manager.last_force_rescan is True
    assert body["current_model"] == "demo.pt"
    assert body["active_model_id"] == "demo.pt"
    assert body["active_model_source"] == "runtime"
    assert body["active_model_summary"]["backend"] == "test-backend"


@pytest.mark.asyncio
async def test_get_model_labels_searches_and_bounds_page():
    manager = FakeModelManager(
        {
            "demo.pt": {
                "name": "Demo",
                "class_names": ["boat", "person", "bottle"],
            }
        }
    )
    handler = SimpleNamespace(model_manager=manager, logger=FakeLogger())
    request = SimpleNamespace(
        query_params={
            "search": "bo",
            "offset": "0",
            "limit": "1",
            "force_rescan": "true",
        }
    )

    response = await model_routes.get_model_labels(handler, "demo.pt", request)
    body = _json_body(response)

    assert manager.last_force_rescan is True
    assert body["filtered_count"] == 2
    assert body["returned_count"] == 1
    assert body["has_more"] is True
    assert body["labels"] == [{"class_id": 0, "label": "boat"}]


def test_resolve_standby_cpu_model_path_prefers_sibling_ncnn_export(tmp_path):
    model_path = tmp_path / "demo.pt"
    model_path.write_text("placeholder", encoding="utf-8")
    ncnn_dir = tmp_path / "demo_ncnn_model"
    ncnn_dir.mkdir()
    (ncnn_dir / "demo.bin").write_text("bin", encoding="utf-8")
    (ncnn_dir / "demo.param").write_text("param", encoding="utf-8")

    assert model_routes.resolve_standby_cpu_model_path(model_path) == str(
        ncnn_dir.as_posix()
    )
