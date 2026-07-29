"""Native-Windows Core model-management capability boundary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import classes.model_manager as model_manager_module
from classes.api_legacy_model_routes import get_models, upload_model


pytestmark = pytest.mark.unit


class _Logger:
    def error(self, *_args, **_kwargs):
        return None


def test_factory_returns_explicit_unavailable_capability(monkeypatch):
    monkeypatch.setattr(
        model_manager_module,
        "model_artifact_policy_unavailable_reason",
        lambda: "Windows trust policy unavailable",
    )
    parameters = SimpleNamespace(SmartTracker={})

    manager = model_manager_module.create_model_manager_from_parameters(parameters)

    assert manager.available is False
    assert manager.unavailable_reason == "Windows trust policy unavailable"
    assert manager.models_folder.name == "models"


@pytest.mark.asyncio
async def test_model_inventory_reports_unavailable_without_failing_core_runtime():
    manager = model_manager_module.UnavailableModelManager("POSIX policy required")
    handler = SimpleNamespace(model_manager=manager, logger=_Logger())

    response = await get_models(handler)

    assert response.status_code == 200
    assert b'"total_count":0' in response.body
    assert b'"available":false' in response.body
    assert b"POSIX policy required" in response.body


@pytest.mark.asyncio
async def test_model_mutation_is_structured_service_unavailable():
    manager = model_manager_module.UnavailableModelManager("POSIX policy required")
    handler = SimpleNamespace(model_manager=manager, logger=_Logger())

    with pytest.raises(HTTPException) as raised:
        await upload_model(handler, SimpleNamespace())

    assert raised.value.status_code == 503
    assert raised.value.detail["error_code"] == "MODEL_MANAGEMENT_UNAVAILABLE"
