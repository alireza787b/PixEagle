"""Exact Ground heuristic retirement using the existing S2 persistence workflow."""

from copy import deepcopy

import pytest
import yaml

from classes import api_legacy_config_routes as routes
from classes.config_service import ConfigService
from classes.config_sync import ConfigSyncOperation, build_defaults_sync_plan, build_defaults_sync_report
from tests.unit.core_app.test_api_legacy_config_routes import FakeHandler, response_body
from tests.unit.core_app.test_config_nested_sync import _request
from tests.unit.core_app.test_config_nested_sync import nested_service  # noqa: F401 - shared pytest fixture


pytestmark = pytest.mark.unit
LEGACY = {
    "COORDINATE_CORRECTIONS_ENABLED": True,
    "IS_CAMERA_GIMBALED": False,
    "BASE_ADJUSTMENT_FACTOR_X": .37,
    "BASE_ADJUSTMENT_FACTOR_Y": .51,
    "ALTITUDE_FACTOR": .025,
}


@pytest.fixture
def ground_service(nested_service, monkeypatch):
    path = nested_service._project_root / "configs/config.yaml"
    persisted = yaml.safe_load(path.read_text())
    persisted["MC_VELOCITY_GROUND"].update(LEGACY)
    persisted["MC_VELOCITY_GROUND"].update({
        "MAX_RATE_OF_DESCENT": .7, "ENABLE_DESCEND_TO_TARGET": True,
        "ERROR_LOGGING_ENABLED": False,
    })
    path.write_text(yaml.safe_dump(persisted, sort_keys=False))
    before = path.read_bytes()
    service = ConfigService(project_root=nested_service._project_root)
    assert path.read_bytes() == before
    runtime = service.get_config()
    monkeypatch.setattr(service, "get_applied_runtime_config", lambda: deepcopy(runtime))
    monkeypatch.setattr(service, "apply_runtime_config_tiers", lambda *args, **kwargs: {
        "applied": False, "applied_paths": [], "pending_paths": ["MC_VELOCITY_GROUND"]})
    monkeypatch.setattr(service, "publish_runtime_config_snapshot", lambda *args, **kwargs: None)
    return service, persisted, before


def test_ground_retirements_preserve_saved_values_until_explicit_cleanup(ground_service):
    service, persisted, before = ground_service
    defaults = service.get_effective_defaults()["MC_VELOCITY_GROUND"]
    schema = service.get_schema("MC_VELOCITY_GROUND")["parameters"]
    runtime = service.get_config("MC_VELOCITY_GROUND")
    raw = service.get_sync_config()["MC_VELOCITY_GROUND"]
    for name, value in LEGACY.items():
        assert name not in defaults and name not in schema and name not in runtime
        assert raw[name] == value
        retirement = service.get_registered_retirement(["MC_VELOCITY_GROUND", name])
        assert retirement and retirement["replacement"] is None
        assert "no runtime consumer" not in retirement["reason"]
    report = build_defaults_sync_report(service)
    retired = [row["path"] for row in report["registered_retirements"] if row["path"][0] == "MC_VELOCITY_GROUND"]
    assert sorted(retired) == sorted(["MC_VELOCITY_GROUND", name] for name in LEGACY)
    operations = [ConfigSyncOperation(op_type="REMOVE_RETIRED", path=path) for path in retired]
    assert build_defaults_sync_plan(service, operations)["valid"]
    assert (service._project_root / "configs/config.yaml").read_bytes() == before
    assert not service.get_backup_history()
    assert service.get_sync_config()["MC_VELOCITY_GROUND"] == persisted["MC_VELOCITY_GROUND"]


@pytest.mark.asyncio
@pytest.mark.parametrize("all_keys", [False, True])
async def test_ground_cleanup_removes_only_selected_leaves_with_backup(ground_service, all_keys):
    service, persisted, before = ground_service
    names = list(LEGACY) if all_keys else ["COORDINATE_CORRECTIONS_ENABLED"]
    operations = [ConfigSyncOperation(op_type="REMOVE_RETIRED", path=["MC_VELOCITY_GROUND", name]) for name in names]
    request = _request(service, operations)
    body = response_body(await routes.apply_defaults_sync(FakeHandler(service), request))
    assert body["success"] and body["applied_count"] == len(names)
    expected = deepcopy(persisted)
    for name in names:
        del expected["MC_VELOCITY_GROUND"][name]
    saved = yaml.safe_load((service._project_root / "configs/config.yaml").read_text())
    assert saved == expected
    backups = service.get_backup_history()
    assert len(backups) == 1
    assert (service._project_root / service.BACKUP_DIR / backups[0].filename).read_bytes() == before


def test_whole_ground_section_is_not_a_retirement(ground_service):
    service, _, _ = ground_service
    plan = build_defaults_sync_plan(service, [ConfigSyncOperation(op_type="REMOVE_RETIRED", path=["MC_VELOCITY_GROUND"])])
    assert not plan["valid"]
    assert "not authorized" in plan["errors"][0]["error"]
