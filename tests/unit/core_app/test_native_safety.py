"""Native command-block changes must use the state the operator reviewed."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from classes.api_legacy_safety_routes import _persist_runtime_safety_boolean
from classes.api_v1_contracts import APINativeSafetyContext
from classes.api_v1_native_safety import native_safety_context_matches, safety_snapshot
from classes.parameters import Parameters


class SafetyConfig:
    def __init__(self, enabled):
        self.enabled = enabled
        self.writes = 0

    def get_path_value(self, path, default=None):
        return self.enabled if path == ["FOLLOWER_CIRCUIT_BREAKER"] else default

    def persist_and_apply_runtime_config_path(self, path, enabled, **_kwargs):
        self.writes += 1
        self.enabled = enabled
        Parameters.FOLLOWER_CIRCUIT_BREAKER = enabled
        return {"changed": True}


def make_owner(enabled=True):
    config = SafetyConfig(enabled)
    app = SimpleNamespace(following_active=False, _follower_state_lock=asyncio.Lock())
    owner = SimpleNamespace(app_controller=app, _get_config_service=lambda: config)
    return owner, config


@pytest.mark.asyncio
async def test_native_safety_guard_rejects_stale_runtime_and_changed_state(monkeypatch):
    monkeypatch.setattr(Parameters, "FOLLOWER_CIRCUIT_BREAKER", True)
    monkeypatch.setattr(Parameters, "FOLLOWER_EXECUTION_MODE", "PX4")
    owner, config = make_owner()
    principal = SimpleNamespace(scopes={"safety:read", "safety:write"})
    current = safety_snapshot(owner, principal)
    context = APINativeSafetyContext(
        instance_id=current["instance_id"], runtime_id=current["runtime_id"],
        state_generation=current["state_generation"], expected_active=True,
    )
    assert native_safety_context_matches(owner, context)

    changed = context.model_copy(update={"runtime_id": "previous-process"})
    with pytest.raises(HTTPException) as error:
        await _persist_runtime_safety_boolean(
            owner, "FOLLOWER_CIRCUIT_BREAKER", False, source="test", expected_context=changed,
        )
    assert error.value.status_code == 409
    assert config.writes == 0

    owner.app_controller.following_active = True
    with pytest.raises(HTTPException) as error:
        await _persist_runtime_safety_boolean(
            owner, "FOLLOWER_CIRCUIT_BREAKER", False, source="test", expected_context=context,
        )
    assert error.value.status_code == 409
    assert config.writes == 0

    owner.app_controller.following_active = False
    await _persist_runtime_safety_boolean(
        owner, "FOLLOWER_CIRCUIT_BREAKER", False, source="test", expected_context=context,
    )
    assert config.writes == 1
    assert not native_safety_context_matches(owner, context)


@pytest.mark.asyncio
async def test_preview_cannot_permit_commands_even_with_fresh_guard(monkeypatch):
    monkeypatch.setattr(Parameters, "FOLLOWER_CIRCUIT_BREAKER", True)
    monkeypatch.setattr(Parameters, "FOLLOWER_EXECUTION_MODE", "COMMAND_PREVIEW")
    owner, config = make_owner()
    current = safety_snapshot(owner, SimpleNamespace(scopes={"safety:read", "safety:write"}))
    context = APINativeSafetyContext(
        instance_id=current["instance_id"], runtime_id=current["runtime_id"],
        state_generation=current["state_generation"], expected_active=True,
    )
    with pytest.raises(HTTPException) as error:
        await _persist_runtime_safety_boolean(
            owner, "FOLLOWER_CIRCUIT_BREAKER", False, source="test", expected_context=context,
        )
    assert error.value.status_code == 409
    assert config.writes == 0
