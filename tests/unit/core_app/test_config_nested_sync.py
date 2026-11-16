"""Exact nested configuration migration against the real persistence service."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from classes import api_legacy_config_routes as routes
from classes.config_service import ConfigService
from classes.config_sync import (
    ConfigSyncApplyRequest,
    ConfigSyncOperation,
    build_defaults_sync_plan,
    build_defaults_sync_report,
)
from tests.unit.core_app.test_api_legacy_config_routes import FakeHandler, response_body


pytestmark = [pytest.mark.unit]
ROOT = Path(__file__).resolve().parents[3]
GENERAL_ALPHA = ["Follower", "General", "YAW_SMOOTHING", "SMOOTHING_ALPHA"]
OVERRIDE_ALPHA = ["Follower", "FollowerOverrides", "MC_VELOCITY_CHASE", "YAW_SMOOTHING", "SMOOTHING_ALPHA"]
RETIRED = ["Follower", "General", "TARGET_LOSS_TIMEOUT"]


@pytest.fixture
def nested_service(tmp_path, monkeypatch):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    for name in ("config_default.yaml", "config_schema.yaml", "config_retirements.yaml"):
        (config_dir / name).write_bytes((ROOT / "configs" / name).read_bytes())
    current = yaml.safe_load((config_dir / "config_default.yaml").read_text())
    current["Follower"]["General"]["SMOOTHING_FACTOR"] = 0.42
    current["Follower"]["FollowerOverrides"] = {}
    current["Follower"]["General"]["TARGET_LOSS_TIMEOUT"] = 9.0
    for name, value in (("REQUIRED_TRACKER_FIELDS", ["angular"]),
                        ("SAFETY_RETURN_SPEED", 9.0), ("DEFAULT_THRUST", 0.8)):
        current["GM_VELOCITY_CHASE"][name] = value
    (config_dir / "config.yaml").write_text(yaml.safe_dump(current, sort_keys=False))
    service = ConfigService(project_root=tmp_path)
    runtime = service.get_config()
    monkeypatch.setattr(service, "get_applied_runtime_config", lambda: copy.deepcopy(runtime))
    monkeypatch.setattr(service, "apply_runtime_config_tiers", lambda *args, **kwargs: {
        "applied": False, "applied_paths": [], "pending_paths": ["Follower.General"]
    })
    monkeypatch.setattr(service, "publish_runtime_config_snapshot", lambda *args, **kwargs: None)
    return service


def _request(service, operations):
    plan = build_defaults_sync_plan(service, operations)
    assert plan["valid"], plan["errors"]
    return ConfigSyncApplyRequest(
        contract_version=2, operations=operations, confirm=True,
        plan_digest=routes._config_sync_plan_token(plan),
    )


def test_nested_writes_preserve_custom_siblings_and_sparse_absence(nested_service):
    service = nested_service
    before = service.get_config()
    assert service.set_path(GENERAL_ALPHA, 0.35).valid
    assert service.set_path(OVERRIDE_ALPHA, 0.25).valid
    current = service.get_config()
    assert current["Follower"]["General"]["SMOOTHING_FACTOR"] == 0.42
    assert current["Follower"]["General"]["YAW_SMOOTHING"]["DEADZONE_DEG_S"] == before["Follower"]["General"]["YAW_SMOOTHING"]["DEADZONE_DEG_S"]
    assert current["Follower"]["FollowerOverrides"] == {
        "MC_VELOCITY_CHASE": {"YAW_SMOOTHING": {"SMOOTHING_ALPHA": 0.25}}
    }


def test_saved_private_floor_is_preserved_until_explicit_factory_adoption(nested_service, monkeypatch):
    service = nested_service
    path = ["Safety", "GlobalLimits", "MIN_ALTITUDE"]
    assert service.set_path(path, 3.0).valid
    assert service.get_effective_defaults()["Safety"]["GlobalLimits"]["MIN_ALTITUDE"] == 5.0
    previous = service.get_effective_defaults()
    previous["Safety"]["GlobalLimits"]["MIN_ALTITUDE"] = 3.0
    monkeypatch.setattr(service, "get_sync_meta", lambda: {"defaults_snapshot": previous})
    report = build_defaults_sync_report(service)
    assert path in [row["path"] for row in report["changed_defaults"]]
    assert service.get_config()["Safety"]["GlobalLimits"]["MIN_ALTITUDE"] == 3.0
    plan = build_defaults_sync_plan(service, [ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=path)])
    assert plan["valid"], plan["errors"]
    assert plan["operations"][0]["target_value"] == 5.0
    assert service.get_config()["Safety"]["GlobalLimits"]["MIN_ALTITUDE"] == 3.0


def test_missing_legacy_speed_permission_requires_preview_and_explicit_adoption(nested_service, tmp_path):
    path = ["Safety", "ALLOW_SESSION_VELOCITY_OVERRIDE"]
    saved = tmp_path / "configs/config.yaml"
    config = yaml.safe_load(saved.read_text())
    del config["Safety"]["ALLOW_SESSION_VELOCITY_OVERRIDE"]
    saved.write_text(yaml.safe_dump(config, sort_keys=False))
    nested_service.reload()
    before = saved.read_bytes()
    report = build_defaults_sync_report(nested_service)
    assert path in [row["path"] for row in report["new_parameters"]]
    plan = build_defaults_sync_plan(nested_service, [ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=path)])
    assert plan["valid"], plan["errors"]
    assert plan["operations"][0]["target_value"] is False
    assert "ALLOW_SESSION_VELOCITY_OVERRIDE" not in nested_service.get_sync_config()["Safety"]
    assert saved.read_bytes() == before


@pytest.mark.parametrize("path,value", [
    (GENERAL_ALPHA, 2.0), (GENERAL_ALPHA, True), (GENERAL_ALPHA, None),
    (["Follower", "General", "NOT_DECLARED"], 1),
    (["Follower", "FollowerOverrides", "UNKNOWN", "CONTROL_UPDATE_RATE"], 10),
    (["Follower", "General", "CONTROL_UPDATE_RATE", "child"], 1),
    (["GimbalTracker", "GUIDANCE", "CAPABILITIES", "AZIMUTH_LIMITS_DEG", "0"], 0),
])
def test_nested_invalid_write_is_atomic(nested_service, path, value):
    before = nested_service.get_config()
    assert not nested_service.set_path(path, value).valid
    assert nested_service.get_config() == before


@pytest.mark.parametrize("ancestor", [None, 3, []])
def test_nested_shape_conflict_is_previewed_without_replacing_ancestor(nested_service, ancestor):
    current = nested_service.get_sync_config()
    current["Follower"]["FollowerOverrides"] = ancestor
    nested_service.get_sync_config = lambda: current
    plan = build_defaults_sync_plan(nested_service, [
        ConfigSyncOperation(op_type="ADD_NEW", path=OVERRIDE_ALPHA, value=0.25)
    ])
    assert not plan["valid"]
    assert any("shape conflict" in row["error"] for row in plan["errors"])
    assert current["Follower"]["FollowerOverrides"] == ancestor


def test_report_uses_leaf_defaults_and_exact_deep_retirements(nested_service, monkeypatch):
    service = nested_service
    baseline = service.get_effective_defaults()
    baseline["Follower"]["General"]["YAW_SMOOTHING"]["SMOOTHING_ALPHA"] = 0.6
    monkeypatch.setattr(service, "get_sync_meta", lambda: {"defaults_snapshot": baseline})
    report = build_defaults_sync_report(service)
    assert [row["path"] for row in report["changed_defaults"]] == [GENERAL_ALPHA]
    assert RETIRED in [row["path"] for row in report["registered_retirements"]]
    assert not report["unknown_extensions"]
    assert OVERRIDE_ALPHA not in [row["path"] for row in report["new_parameters"]]
    assert ["Follower", "FollowerOverrides"] not in [row["path"] for row in report["new_parameters"]]


def test_schema_only_override_needs_explicit_value_not_inherited_default(nested_service):
    missing = build_defaults_sync_plan(nested_service, [
        ConfigSyncOperation(op_type="ADD_NEW", path=OVERRIDE_ALPHA)
    ])
    adopt = build_defaults_sync_plan(nested_service, [
        ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=OVERRIDE_ALPHA)
    ])
    explicit = build_defaults_sync_plan(nested_service, [
        ConfigSyncOperation(op_type="ADD_NEW", path=OVERRIDE_ALPHA, value=0.25)
    ])
    assert not missing["valid"]
    assert not adopt["valid"]
    assert explicit["valid"]
    assert explicit["operations"][0]["target_value"] == 0.25


def test_explicit_null_is_distinct_from_omitted_add_value(nested_service, monkeypatch):
    path = ["GM_VELOCITY_VECTOR", "REQUESTED_SPEED"]
    current = nested_service.get_sync_config()
    del current["GM_VELOCITY_VECTOR"]["REQUESTED_SPEED"]
    defaults = nested_service.get_effective_defaults()
    defaults["GM_VELOCITY_VECTOR"]["REQUESTED_SPEED"] = 0.5
    monkeypatch.setattr(nested_service, "get_sync_config", lambda: current)
    monkeypatch.setattr(nested_service, "get_effective_defaults", lambda: defaults)
    omitted = build_defaults_sync_plan(nested_service, [ConfigSyncOperation(op_type="ADD_NEW", path=path)])
    explicit = build_defaults_sync_plan(nested_service, [ConfigSyncOperation(op_type="ADD_NEW", path=path, value=None)])
    assert omitted["valid"] and explicit["valid"]
    assert omitted["operations"][0]["target_value"] == 0.5
    assert explicit["operations"][0]["target_value"] is None
    assert omitted["plan_digest"] != explicit["plan_digest"]


@pytest.mark.parametrize("reverse", [False, True])
def test_overlapping_parent_child_operations_are_refused(nested_service, reverse):
    paths = [GENERAL_ALPHA[:2], GENERAL_ALPHA]
    if reverse:
        paths.reverse()
    plan = build_defaults_sync_plan(nested_service, [
        ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=path) for path in paths
    ])
    assert not plan["valid"]
    assert any("Overlapping" in row["error"] for row in plan["errors"])


@pytest.mark.asyncio
async def test_nested_apply_persists_only_selected_leaves_and_retires_exact_keys(nested_service):
    service = nested_service
    baseline = service.get_effective_defaults()
    baseline["Follower"]["General"]["SMOOTHING_FACTOR"] = 0.1
    baseline["Follower"]["General"]["YAW_SMOOTHING"]["SMOOTHING_ALPHA"] = 0.2
    baseline["Follower"]["General"]["TARGET_LOSS_TIMEOUT"] = 9.0
    service.save_sync_meta({"defaults_snapshot": baseline})
    operations = [
        ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=GENERAL_ALPHA),
        ConfigSyncOperation(op_type="ADD_NEW", path=OVERRIDE_ALPHA, value=0.25),
        ConfigSyncOperation(op_type="REMOVE_RETIRED", path=RETIRED),
        ConfigSyncOperation(op_type="REMOVE_RETIRED", path=["GM_VELOCITY_CHASE", "DEFAULT_THRUST"]),
    ]
    body = response_body(await routes.apply_defaults_sync(FakeHandler(service), _request(service, operations)))
    assert body["success"]
    assert body["applied_count"] == 4
    assert body["applied_operations"][0]["reload_tier"] == "follower_restart"
    assert len(service.get_backup_history()) == 1
    saved = yaml.safe_load((service._project_root / "configs/config.yaml").read_text())
    assert saved["Follower"]["General"]["SMOOTHING_FACTOR"] == 0.42
    assert "TARGET_LOSS_TIMEOUT" not in saved["Follower"]["General"]
    assert saved["Follower"]["FollowerOverrides"] == {
        "MC_VELOCITY_CHASE": {"YAW_SMOOTHING": {"SMOOTHING_ALPHA": 0.25}}
    }
    assert "DEFAULT_THRUST" not in saved["GM_VELOCITY_CHASE"]
    assert saved["GM_VELOCITY_CHASE"]["SAFETY_RETURN_SPEED"] == 9.0
    snapshot = service.get_sync_meta()["defaults_snapshot"]
    assert snapshot["Follower"]["General"]["SMOOTHING_FACTOR"] == 0.1
    assert snapshot["Follower"]["General"]["YAW_SMOOTHING"]["SMOOTHING_ALPHA"] == 0.7
    assert "TARGET_LOSS_TIMEOUT" not in snapshot["Follower"]["General"]
    assert "MC_VELOCITY_CHASE" not in snapshot["Follower"]["FollowerOverrides"]
    audits = service.get_audit_log()["entries"]
    assert any(row["parameter"] == "General.YAW_SMOOTHING.SMOOTHING_ALPHA" for row in audits)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["audit", "publication"])
async def test_nested_apply_failure_restores_files_and_backups(nested_service, monkeypatch, failure):
    service = nested_service
    request = _request(service, [ConfigSyncOperation(op_type="ADD_NEW", path=OVERRIDE_ALPHA, value=0.25)])
    original = service.capture_persistence_snapshot()
    original_digests = service.get_persistence_state_digests()

    def fail(*args, **kwargs):
        raise RuntimeError("injected nested apply failure")

    monkeypatch.setattr(service, "log_audit_entry" if failure == "audit" else "apply_runtime_config_tiers", fail)
    with pytest.raises(HTTPException, match="rolled back"):
        await routes.apply_defaults_sync(FakeHandler(service), request)
    assert service.get_persistence_state_digests() == original_digests
    assert service.capture_persistence_snapshot() == original
    assert service.get_path_value(["Follower", "FollowerOverrides"]) == {}


def test_required_general_upgrade_fails_before_preview_without_default_merge(nested_service):
    path = nested_service._project_root / "configs/config.yaml"
    current = yaml.safe_load(path.read_text())
    del current["Follower"]["General"]["YAW_SMOOTHING"]["SMOOTHING_ALPHA"]
    path.write_text(yaml.safe_dump(current, sort_keys=False))
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="Missing required properties: SMOOTHING_ALPHA"):
        ConfigService(project_root=nested_service._project_root)
    assert path.read_bytes() == before


def test_retired_gm_chase_settings_are_inert_until_explicit_cleanup(nested_service):
    defaults = nested_service.get_effective_defaults()["GM_VELOCITY_CHASE"]
    schema = nested_service.get_schema("GM_VELOCITY_CHASE")["parameters"]
    for name in ("REQUIRED_TRACKER_FIELDS", "SAFETY_RETURN_SPEED", "DEFAULT_THRUST"):
        assert name not in defaults and name not in schema
        assert name not in nested_service.get_config("GM_VELOCITY_CHASE")
        assert name in nested_service.get_sync_config()["GM_VELOCITY_CHASE"]
        assert nested_service.get_registered_retirement(["GM_VELOCITY_CHASE", name])


def test_nested_safety_write_validates_the_resolved_envelope(nested_service):
    before = nested_service.get_config()
    result = nested_service.set_path(["Safety", "GlobalLimits", "MAX_ALTITUDE"], 2.0)
    assert not result.valid
    assert any("Safety semantic validation" in error for error in result.errors)
    assert nested_service.get_config() == before


def test_optional_mission_ceiling_survives_edit_import_export_and_sync(nested_service):
    service = nested_service
    path = ["Safety", "GlobalLimits", "MAX_ALTITUDE"]
    assert service.set_path(path, None).valid
    assert service.get_path_value(path) is None
    exported = service.export_config(changes_only=True)
    assert exported["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] is None
    report = build_defaults_sync_report(service)
    assert path not in [row["path"] for row in report["new_parameters"]]
    assert service.set_path(path, 90.0).valid
    wire_config = json.loads(json.dumps(exported))
    ok, _ = service.import_config(yaml.safe_load(yaml.safe_dump(wire_config)))
    assert ok
    assert service.get_sync_config()["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] is None
    assert service.set_path(["Safety", "FollowerOverrides", "MC_VELOCITY_CHASE", "MAX_ALTITUDE"], 75.0).valid
    assert not service.set_path(["Safety", "FollowerOverrides", "MC_VELOCITY_CHASE", "MAX_ALTITUDE"], None).valid


def test_missing_mission_ceiling_in_replace_import_uses_checked_in_default(nested_service):
    ok, _ = nested_service.import_config({"Safety": {"GlobalLimits": {"MIN_ALTITUDE": 3.0}}}, "replace")
    assert ok
    assert nested_service.get_path_value(["Safety", "GlobalLimits", "MAX_ALTITUDE"]) == 100.0


def test_nested_resolver_supports_explicit_typed_extension_children(nested_service):
    nested_service._schema["meta"]["extension_sections"]["Site"] = {
        "type": "object", "additional_properties": False,
        "properties": {"Limits": {
            "type": "object", "properties": {},
            "additional_properties": {"type": "float", "min": 0.0},
        }},
    }
    path = ["Site", "Limits", "north"]
    assert nested_service.set_path(path, 2.0).valid
    assert not nested_service.validate_path(path, -1.0).valid
    assert not nested_service.validate_path(path + ["nested"], 1.0).valid
    assert nested_service.get_path_value(path) == 2.0


@pytest.mark.parametrize("sensitive_parent", [False, True])
def test_nested_sensitive_values_use_exact_schema_metadata(nested_service, sensitive_parent):
    yaw = nested_service._schema["sections"]["Follower"]["parameters"]["General"]["properties"]["YAW_SMOOTHING"]
    sensitive = yaw if sensitive_parent else yaw["properties"]["SMOOTHING_ALPHA"]
    sensitive["sensitive"] = True
    plan = build_defaults_sync_plan(nested_service, [
        ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=GENERAL_ALPHA)
    ])
    public = routes._public_sync_plan(nested_service, plan)
    assert public["operations"][0]["target_value"] == "[REDACTED]"


def test_report_preserves_present_null_false_zero_and_atomic_arrays(nested_service):
    report = build_defaults_sync_report(nested_service)
    new_paths = [row["path"] for row in report["new_parameters"]]
    assert ["GM_VELOCITY_VECTOR", "REQUESTED_SPEED"] not in new_paths
    assert ["GM_VELOCITY_VECTOR", "INITIAL_VELOCITY"] not in new_paths
    assert ["Follower", "General", "ENABLE_ALTITUDE_CONTROL"] not in new_paths
    assert not any("0" in path for path in new_paths)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [
    "config.yaml", "config_default.yaml", "config_schema.yaml",
    "config_retirements.yaml", "config_sync_meta.json", "audit_log.json",
])
async def test_nested_preview_rejects_any_changed_persistence_source(nested_service, source):
    service = nested_service
    request = _request(service, [ConfigSyncOperation(op_type="ADD_NEW", path=OVERRIDE_ALPHA, value=0.25)])
    path = service._project_root / "configs" / source
    payload = path.read_bytes() if path.exists() else (b"[]" if source == "audit_log.json" else b"{}")
    path.write_bytes(payload + b"\n")
    before = path.read_bytes()
    response = await routes.apply_defaults_sync(FakeHandler(service), request)
    assert response.status_code == 409
    assert path.read_bytes() == before
    assert not service.get_backup_history()
    assert service.get_path_value(["Follower", "FollowerOverrides"]) == {}
