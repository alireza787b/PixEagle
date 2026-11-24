"""The obsolete transition timeout remains saved until explicit Config Sync."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from classes import api_legacy_config_routes as routes
from classes.config_service import ConfigService
from classes.config_sync import ConfigSyncOperation, build_defaults_sync_plan, build_defaults_sync_report
from tests.unit.core_app.test_api_legacy_config_routes import FakeHandler, response_body
from tests.unit.core_app.test_config_nested_sync import _request


ROOT = Path(__file__).resolve().parents[3]
RETIRED = ["Follower", "VTOL_TRANSITION_TIMEOUT_S"]


@pytest.fixture
def service(tmp_path, monkeypatch):
    directory = tmp_path / "configs"
    directory.mkdir()
    for name in ("config_default.yaml", "config_schema.yaml", "config_retirements.yaml"):
        (directory / name).write_bytes((ROOT / "configs" / name).read_bytes())
    saved = yaml.safe_load((directory / "config_default.yaml").read_text())
    saved["Follower"]["VTOL_TRANSITION_TIMEOUT_S"] = 71.
    saved["Follower"]["AIRFRAME_PHASE_CONFIRMATION_S"] = 1.7
    (directory / "config.yaml").write_text(yaml.safe_dump(saved, sort_keys=False))
    before = (directory / "config.yaml").read_bytes()
    result = ConfigService(project_root=tmp_path)
    runtime = result.get_config()
    monkeypatch.setattr(result, "get_applied_runtime_config", lambda: deepcopy(runtime))
    monkeypatch.setattr(result, "apply_runtime_config_tiers", lambda *a, **k: {
        "applied": False, "applied_paths": [], "pending_paths": ["Follower"]})
    monkeypatch.setattr(result, "publish_runtime_config_snapshot", lambda *a, **k: None)
    return result, saved, before


def test_transition_timeout_is_inert_without_a_saved_config_rewrite(service):
    config, saved, before = service
    assert config.get_schema()["schema_version"] == "1.11.0"
    assert "VTOL_TRANSITION_TIMEOUT_S" not in config.get_schema("Follower")["parameters"]
    assert "VTOL_TRANSITION_TIMEOUT_S" not in config.get_effective_defaults()["Follower"]
    assert "VTOL_TRANSITION_TIMEOUT_S" not in config.get_config("Follower")
    assert config.get_config("Follower")["AIRFRAME_PHASE_CONFIRMATION_S"] == 1.7
    assert config.get_sync_config() == saved
    retirement = config.get_registered_retirement(RETIRED)
    assert retirement["replacement"] is None
    assert retirement["retired_in_schema_version"] == "1.9.0"
    report = build_defaults_sync_report(config)
    assert RETIRED in [row["path"] for row in report["registered_retirements"]]
    assert build_defaults_sync_plan(config, [ConfigSyncOperation(op_type="REMOVE_RETIRED", path=RETIRED)])["valid"]
    assert (config._project_root / "configs/config.yaml").read_bytes() == before
    assert not config.get_backup_history()


def test_supported_velocity_switch_is_not_retired_or_stripped():
    service = ConfigService.get_instance()
    candidate = deepcopy(service.get_default())
    candidate["Safety"]["ALLOW_SESSION_VELOCITY_OVERRIDE"] = False
    assert service.get_registered_retirement(["Safety", "ALLOW_SESSION_VELOCITY_OVERRIDE"]) is None
    assert service.validate_config_mapping(candidate, require_safety=True).valid
    normalized = service._normalize_effective_config_locked(candidate)
    assert normalized["Safety"]["ALLOW_SESSION_VELOCITY_OVERRIDE"] is False
    assert candidate["Safety"]["ALLOW_SESSION_VELOCITY_OVERRIDE"] is False


@pytest.mark.asyncio
async def test_explicit_transition_cleanup_removes_only_the_retired_timeout_with_backup(service):
    config, saved, before = service
    operation = ConfigSyncOperation(op_type="REMOVE_RETIRED", path=RETIRED)
    response = response_body(await routes.apply_defaults_sync(FakeHandler(config), _request(config, [operation])))
    assert response["success"] and response["applied_count"] == 1
    expected = deepcopy(saved)
    del expected["Follower"]["VTOL_TRANSITION_TIMEOUT_S"]
    assert yaml.safe_load((config._project_root / "configs/config.yaml").read_text()) == expected
    assert config.get_config("Follower")["AIRFRAME_PHASE_CONFIRMATION_S"] == 1.7
    backups = config.get_backup_history()
    assert len(backups) == 1
    assert (config._project_root / config.BACKUP_DIR / backups[0].filename).read_bytes() == before
