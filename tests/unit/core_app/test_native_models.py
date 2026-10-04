"""Native installed-model contracts with the real guarded dashboard executor."""

import asyncio
import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from classes.api_security_types import APIPrincipal
from classes.api_v1_contracts import APINativeModelSelectRequest, APIActionResponse, APINativeModelInventory
from classes.api_v1_native_models import MODEL_SELECT_SCOPES, get_models, get_labels, select_model
from classes.api_v1_native_targets import target_state
from classes.api_v1_integration import integration_context
from classes.parameters import Parameters
from tests.unit.core_app.test_native_target_operations import owner as target_owner
from tests.unit.core_app.test_api_v1_integration import client

pytestmark = pytest.mark.unit


@pytest.fixture
def owner(target_owner, monkeypatch, tmp_path):
    owner = target_owner
    monkeypatch.setattr("classes.model_manager.AI_AVAILABLE", True)
    monkeypatch.setattr(Parameters, "SmartTracker", {
        "SMART_TRACKER_GPU_MODEL_PATH": str(tmp_path / "first.pt"),
        "SMART_TRACKER_CPU_MODEL_PATH": str(tmp_path / "first.pt"),
        "SMART_TRACKER_USE_GPU": True,
    })
    owner.logger = Mock()
    owner.principal_test = APIPrincipal.bearer(subject="operator-a", token_id="a", scopes=MODEL_SELECT_SCOPES)
    models = {}
    for name in ("first", "second", "unsupported"):
        artifact = tmp_path / (name + ".pt")
        artifact.write_bytes(b"mock fixture; no checkpoint execution")
        models[name] = dict(path=str(artifact), name=name, display_name=name.title(),
                            task="segment" if name == "unsupported" else "detect",
                            smarttracker_supported=name != "unsupported", artifact_sha256="a" * 64,
                            class_names=["person", "car"], size_mb=1.0)
    owner.models_test = models
    owner.model_manager = SimpleNamespace(
        available=True, discover_models=Mock(side_effect=lambda *_: copy.deepcopy(models)),
        normalize_model_id=lambda value: Path(value).stem if value else None,
        validate_model=Mock(return_value={"valid": True, "smarttracker_supported": True, "task": "detect"}),
    )

    def advance():
        owner.app_controller._tracking_session_generation += 1

    def persist(handler, path, device):
        assert handler.app_controller._follower_state_lock.locked()
        assert device == "auto"
        Parameters.SmartTracker["SMART_TRACKER_GPU_MODEL_PATH"] = str(path)
        Parameters.SmartTracker["SMART_TRACKER_CPU_MODEL_PATH"] = str(path)
        return {}

    owner.persist_test = Mock(side_effect=persist)
    monkeypatch.setattr("classes.api_legacy_model_routes.persist_standby_model_selection", owner.persist_test)
    owner.app_controller._advance_tracking_session_generation = advance
    return owner


def http_request(owner, principal=None):
    return SimpleNamespace(state=SimpleNamespace(api_principal=principal or owner.principal_test))


async def inventory(owner):
    response = await get_models(owner, http_request(owner))
    assert response.status_code == 200, response.body
    return json.loads(response.body)


async def request(owner, **updates):
    payload = dict(confirm=True, idempotency_key="selection-a", model_id="second", device="auto",
                   model_generation=(await inventory(owner))["model_generation"],
                   native_context=dict(guard=target_state(owner, owner.principal_test)["guard"], binding_mode="companion_only"))
    payload.update(updates)
    return APINativeModelSelectRequest(**payload)


async def test_inventory_redacts_paths_bounds_labels_and_does_not_load(owner):
    owner.models_test["first"]["class_names"] = [f"class-{index}" for index in range(80)]
    payload = await inventory(owner)
    APINativeModelInventory.model_validate(payload)
    assert payload["active_model_id"] is None
    assert payload["configured_model_id"] == "first"
    assert payload["models"][0]["total_labels"] == 80
    assert len(payload["models"][0]["labels"]) == 32
    assert payload["models"][0]["has_more_labels"]
    assert payload["models"][2]["available"] is False
    assert "/" not in json.dumps(payload["models"])
    owner.model_manager.validate_model.assert_not_called()
    labels = await get_labels(owner, http_request(owner), "first", offset=32, limit=20)
    page = json.loads(labels.body)
    assert page["labels"][0] == {"class_id": 32, "label": "class-32"}
    assert page["model_generation"] == payload["model_generation"]
    assert labels.headers["cache-control"] == "no-store"


async def test_read_needs_only_models_scope_without_target_telemetry(owner):
    principal = APIPrincipal.bearer(subject="models-reader", token_id="read", scopes={"models:read"})
    response = await get_models(owner, http_request(owner, principal))
    assert response.status_code == 200
    assert json.loads(response.body)["target_state"] is None
    mutation = await select_model(owner, await request(owner), Response(), http_request(owner, principal))
    assert mutation.status_code == 403


async def test_core_inventory_remains_readable(owner, monkeypatch):
    monkeypatch.setattr("classes.model_manager.AI_AVAILABLE", False)
    payload = await inventory(owner)
    assert not payload["available"]
    assert all(not row["available"] and row["unavailable_reason"] for row in payload["models"])
    owner.model_manager.validate_model.assert_not_called()


@pytest.mark.parametrize("task,supported,available", [
    ("detect", True, True),
    ("obb", True, True),
    ("detect", False, False),
    ("detect", None, False),
    ("segment", True, False),
    (None, True, False),
])
async def test_inventory_availability_requires_verified_supported_task(owner, task, supported, available):
    owner.models_test["second"]["task"] = task
    owner.models_test["second"]["smarttracker_supported"] = supported
    payload = await inventory(owner)
    row = next(model for model in payload["models"] if model["model_id"] == "second")
    assert row["available"] is available
    assert bool(row["unavailable_reason"]) is not available
    if not available:
        result = await select_model(owner, await request(owner), Response(), http_request(owner))
        assert result.status_code == 409 and "model_unavailable" in result.body.decode()
        owner.persist_test.assert_not_called()
    owner.model_manager.validate_model.assert_not_called()


async def test_selection_configures_without_enabling_smart_and_invalidates_target(owner):
    body = await request(owner)
    response = Response()
    result = await select_model(owner, body, response, http_request(owner))
    APIActionResponse.model_validate(result)
    assert response.status_code == 202 and result["status"] == "success"
    assert result["result"]["selection_status"] == "configured"
    assert result["result"]["model_inventory"]["configured_model_id"] == "second"
    assert result["result"]["model_inventory"]["active_model_id"] is None
    assert result["result"]["native_target_revision"] == "1"
    assert not owner.app_controller.smart_mode_active
    assert not owner.app_controller.following_active
    assert result["audit_event"]["actor"]["subject"] == "operator-a"
    owner.model_manager.validate_model.assert_called_once_with(Path(owner.models_test["second"]["path"]), allow_checkpoint_execution=True)
    replay = await select_model(owner, body, response, http_request(owner))
    assert response.status_code == 200 and replay["idempotent_replay"]
    owner.persist_test.assert_called_once()
    conflict = await select_model(owner, body.model_copy(update={"model_id": "first"}), response, http_request(owner))
    assert conflict.status_code == 409 and "idempotency_conflict" in conflict.body.decode()


async def test_idempotence_is_actor_scoped(owner):
    first = await request(owner)
    await select_model(owner, first, Response(), http_request(owner))
    other = APIPrincipal.bearer(subject="operator-b", token_id="b", scopes=MODEL_SELECT_SCOPES)
    second = await request(owner, model_id="first")
    result = await select_model(owner, second, Response(), http_request(owner, other))
    assert result["status"] == "success" and not result["idempotent_replay"]
    assert owner.persist_test.call_count == 2


@pytest.mark.parametrize("change,code", [
    ("generation", "model_generation_stale"), ("inventory", "model_generation_stale"),
    ("config", "model_generation_stale"), ("runtime", "native_context_stale"),
    ("target", "target_revision_stale"), ("following", "target_following_active"),
    ("aircraft", "native_context_stale"), ("unknown", "model_not_advertised"),
    ("unsupported", "model_unavailable"), ("selected", "model_target_active"),
])
async def test_stale_or_disallowed_selection_has_no_mutation(owner, change, code):
    body = await request(owner, model_id="unknown" if change == "unknown" else "unsupported" if change == "unsupported" else "second")
    if change == "generation":
        body.model_generation = "f" * 64
    elif change == "inventory":
        owner.models_test["second"]["artifact_sha256"] = "b" * 64
    elif change == "config":
        Parameters.SmartTracker["SMART_TRACKER_USE_GPU"] = False
    elif change == "runtime":
        body.native_context.guard.runtime_id = "other-runtime"
    elif change == "target":
        owner.app_controller._tracking_session_generation += 1
    elif change == "following":
        owner.app_controller.following_active = True
    elif change == "aircraft":
        owner.command_test["connection_generation"] = "1"
        owner.command_test["connected"] = True
    elif change == "selected":
        owner.app_controller.smart_tracker = SimpleNamespace(selected_object_id=42)
    result = await select_model(owner, body, Response(), http_request(owner))
    assert result.status_code == 409, result.body
    assert code in result.body.decode()
    owner.model_manager.validate_model.assert_not_called()
    owner.persist_test.assert_not_called()


async def test_context_is_rechecked_after_checkpoint_validation(owner):
    def validate(*args, **kwargs):
        owner.command_test["connection_generation"] = "changed"
        return {"valid": True, "smarttracker_supported": True}

    owner.model_manager.validate_model.side_effect = validate
    result = await select_model(owner, await request(owner), Response(), http_request(owner))
    assert result.status_code == 409 and "native_context_stale" in result.body.decode()
    owner.persist_test.assert_not_called()


async def test_inventory_is_rechecked_after_checkpoint_validation(owner):
    def validate(*args, **kwargs):
        owner.models_test["second"]["artifact_sha256"] = "c" * 64
        return {"valid": True, "smarttracker_supported": True}

    owner.model_manager.validate_model.side_effect = validate
    result = await select_model(owner, await request(owner), Response(), http_request(owner))
    assert result.status_code == 409 and "model_generation_stale" in result.body.decode()
    owner.persist_test.assert_not_called()


async def test_slow_model_validation_does_not_block_context_or_source(owner):
    entered = threading.Event()
    release = threading.Event()

    def validate(*args, **kwargs):
        entered.set()
        assert release.wait(5), "test did not release checkpoint validation"
        return {"valid": True, "smarttracker_supported": True}

    owner.model_manager.validate_model.side_effect = validate
    mutation = asyncio.create_task(select_model(owner, await request(owner), Response(), http_request(owner)))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        # Exercise the actual context route, whose publisher read must remain
        # available while a checkpoint is loading on another thread.
        response = await asyncio.wait_for(integration_context(owner, http_request(owner)), 1)
        assert response.status_code == 200
        assert owner.frame_publisher.selection_transaction().acquire(blocking=False)
        owner.frame_publisher.selection_transaction().release()
        assert not mutation.done()
    finally:
        release.set()
        result = await asyncio.wait_for(mutation, 2)
    assert result["status"] == "success"


async def test_waiting_target_read_does_not_block_context(owner, monkeypatch):
    from classes.api_v1_native_targets import get_target_state

    monkeypatch.setattr("classes.model_manager.AI_AVAILABLE", False)
    entered = threading.Event()
    reading = threading.Event()
    release = threading.Event()

    def read_target(*args):
        reading.set()
        return target_state(*args)

    monkeypatch.setattr("classes.api_v1_native_targets.target_state", read_target)

    def hold_model_lock():
        with owner.app_controller._tracker_model_state_lock:
            entered.set()
            assert release.wait(5), "test did not release tracker/model lock"

    holding = asyncio.create_task(asyncio.to_thread(hold_model_lock))
    assert await asyncio.to_thread(entered.wait, 2)
    read = asyncio.create_task(get_target_state(owner, http_request(owner)))
    try:
        assert await asyncio.to_thread(reading.wait, 2)
        response = await asyncio.wait_for(integration_context(owner, http_request(owner)), 1)
        assert response.status_code == 200
        assert not read.done()
    finally:
        release.set()
        await holding
    assert (await asyncio.wait_for(read, 2)).status_code == 200


async def test_dashboard_selection_invalidates_native_generation_and_target_guard(owner):
    from classes.api_legacy_model_routes import switch_model
    from unittest.mock import AsyncMock

    previous = await request(owner)
    body = SimpleNamespace(json=AsyncMock(return_value={"model_path": owner.models_test["second"]["path"]}))
    result = await switch_model(owner, body)
    assert result.status_code == 200
    assert owner.app_controller._tracking_session_generation == 1
    stale = await select_model(owner, previous, Response(), http_request(owner))
    assert stale.status_code == 409 and "target_revision_stale" in stale.body.decode()
    owner.persist_test.assert_called_once()


@pytest.mark.parametrize("success", [True, False])
async def test_active_smart_switch_uses_shared_executor_without_starting_following(owner, success):
    current = {"model_path": owner.models_test["first"]["path"], "effective_device": "cpu", "backend": "ultralytics",
               "fallback_occurred": True, "fallback_reason": "Failed /private/checkpoint.pt CUDA init"}

    def switch(path, *, device):
        if success:
            current["model_path"] = path
        return {"success": success, "message": "model switch fixture", "model_info": {"runtime": dict(current)}}

    owner.app_controller.smart_mode_active = True
    owner.app_controller.smart_tracker = SimpleNamespace(
        selected_object_id=None, selected_bbox=None, get_runtime_info=lambda: dict(current),
        switch_model=Mock(side_effect=switch),
    )
    result = await select_model(owner, await request(owner), Response(), http_request(owner))
    assert result["status"] == ("success" if success else "failure")
    after = result["result"]["model_inventory"]
    assert after["active_model_id"] == ("second" if success else "first")
    assert after["runtime"]["device"] == "cpu"
    assert after["runtime"]["fallback_occurred"] is True
    assert "/private/" not in json.dumps(after)
    assert not owner.app_controller.following_active
    owner.app_controller.smart_tracker.switch_model.assert_called_once()
    assert owner.persist_test.call_count == int(success)


async def test_failed_validation_retains_classic_and_redacts_private_details(owner):
    owner.model_manager.validate_model.return_value = {"valid": False, "error": "/private/model/path.pt failed"}
    result = await select_model(owner, await request(owner), Response(), http_request(owner))
    assert result.status_code == 503 and "private/model" not in result.body.decode()
    assert not owner.app_controller.smart_mode_active
    assert Parameters.SmartTracker["SMART_TRACKER_GPU_MODEL_PATH"].endswith("first.pt")
    owner.persist_test.assert_not_called()


async def test_dry_run_does_not_load_or_persist(owner):
    body = await request(owner, dry_run=True, confirm=False, idempotency_key=None)
    result = await select_model(owner, body, Response(), http_request(owner))
    assert result["status"] == "validated" and not result["executed"]
    owner.model_manager.validate_model.assert_not_called()
    owner.persist_test.assert_not_called()


async def test_unavailable_audit_refuses_model_loading(owner):
    owner._record_security_audit_event.return_value = False
    result = await select_model(owner, await request(owner), Response(), http_request(owner))
    assert result.status_code == 503 and "audit_unavailable" in result.body.decode()
    owner.model_manager.validate_model.assert_not_called()


@pytest.mark.parametrize("identifier", ["../first", "/tmp/model.pt", "first/path", "", "a"*129])
def test_contract_rejects_model_paths(owner, identifier):
    with pytest.raises(ValidationError):
        APINativeModelSelectRequest(model_id=identifier, model_generation="a"*64,
                                   native_context=dict(guard=target_state(owner, owner.principal_test)["guard"], binding_mode="companion_only"))


async def test_label_unknown_and_invalid_paging(owner):
    assert (await get_labels(owner, http_request(owner), "missing")).status_code == 404
    for offset, limit in ((-1, 20), (0, 0), (0, 201)):
        assert (await get_labels(owner, http_request(owner), "first", offset=offset, limit=limit)).status_code == 422


def model_client(owner, **kwargs):
    http = client(owner, **kwargs)
    owner.app.add_api_route("/api/v1/integration/models", owner.get_native_models, methods=["GET"])
    owner.app.add_api_route("/api/v1/actions/model-select", owner.native_model_select_action, methods=["POST"])
    return http


def test_actual_middleware_read_scope_and_local_compat_denial(owner):
    http = model_client(owner, scopes=("models:read",))
    assert http.get("/api/v1/integration/models").status_code == 401
    headers = {"Authorization": "Bearer native-test-fixture"}
    assert http.get("/api/v1/integration/models", headers=headers).status_code == 200
    assert http.post("/api/v1/actions/model-select", headers=headers, json={}).status_code == 403
    http = model_client(owner, mode="local_compat")
    assert http.get("/api/v1/integration/models").status_code == 401


def test_actual_session_csrf_required_before_selection(owner):
    from classes.api_auth_runtime import APIAuthRuntime, APIUserRecord, hash_password_pbkdf2_sha256

    http = model_client(owner, mode="browser_session")
    user = APIUserRecord(username="model-operator", role="operator", password_pbkdf2_sha256=hash_password_pbkdf2_sha256("test-only"))
    # APIAuthRuntime freezes its user mapping after construction. Build the
    # operator fixture before creating the runtime instead of mutating it.
    runtime = APIAuthRuntime(mode="browser_session", users_by_username={user.username: user}, bearer_tokens_by_hash={})
    owner.api_auth_runtime = runtime
    session = runtime.create_session_for_user(user)
    http.cookies.set(runtime.session_cookie_name, session.session_id)
    payload = http.get("/api/v1/integration/models").json()
    body = dict(model_id="second", model_generation=payload["model_generation"], confirm=True,
                idempotency_key="session", native_context=dict(guard=payload["target_state"]["guard"], binding_mode="companion_only"))
    assert http.post("/api/v1/actions/model-select", json=body).status_code == 403
    assert http.post("/api/v1/actions/model-select", json=body,
                     headers={runtime.csrf_header_name: session.csrf_token}).status_code == 202
    runtime.revoke_session_id(session.session_id)
    assert http.get("/api/v1/integration/models").status_code == 401
