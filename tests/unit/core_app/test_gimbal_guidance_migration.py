"""Reviewable nested migration without using retired settings as runtime policy."""

import copy

import pytest
import yaml
from fastapi import HTTPException

from classes import api_legacy_config_routes as routes
from classes.config_service import ConfigService
from classes.config_sync import ConfigSyncOperation, build_defaults_sync_plan, build_defaults_sync_report
from classes.gimbal_guidance_config_migration import (
    ALLOWED_PATH, LEGACY_PATH, LIMITS_PATH, assess_gimbal_guidance_migration,
    canonical_guidance_restrictions,
)
from tests.unit.core_app.test_api_legacy_config_routes import FakeHandler, response_body
from tests.unit.core_app.test_config_nested_sync import nested_service, _request


pytestmark = pytest.mark.unit
FACTORY = dict(KNOWN=False, SUPPORTS_VERTICAL=False, SUPPORTS_REVERSE=False,
               SUPPORTS_YAW_FALLBACK=False, AZIMUTH_LIMITS_DEG=[-180., 180.],
               DEPRESSION_LIMITS_DEG=[-90., 90.])
UNRESTRICTED = dict(AZIMUTH_LIMITS_DEG=None, DEPRESSION_LIMITS_DEG=None)


def saved(legacy=None, provider="topotek_sip_udp"):
    return {"GimbalTracker": {"PROVIDER": provider, "GUIDANCE": {
        "CAPABILITIES": copy.deepcopy(FACTORY if legacy is None else legacy)}}}


def candidate(config, allowed=None, **limits):
    result = copy.deepcopy(config)
    result["GimbalTracker"]["GUIDANCE"] = {
        "ALLOWED_MANOEUVRES": allowed,
        "OBSERVATION_LIMITS": {**UNRESTRICTED, **limits},
    }
    return result


@pytest.mark.parametrize("known,flags", [(False, False), (True, True)])
def test_only_known_provider_equivalent_policy_needs_no_review(known, flags):
    config = saved({**FACTORY, "KNOWN": known, "SUPPORTS_VERTICAL": flags,
                    "SUPPORTS_REVERSE": flags, "SUPPORTS_YAW_FALLBACK": flags})
    original = copy.deepcopy(config)
    result = assess_gimbal_guidance_migration(config)
    assert not result["review_required"]
    assert result["effective_before"]["origin"] == "legacy_topotek_provider_override"
    assert result["effective_before"]["mechanical_qualification"] == "unqualified"
    assert result["effective_after"]["special_manoeuvres"] == ["vertical", "reverse_translation", "yaw_recovery"]
    assert config == original


@pytest.mark.parametrize("legacy,provider", [
    ({**FACTORY, "AZIMUTH_LIMITS_DEG": [-45., 45.]}, "topotek"),
    ({**FACTORY, "SUPPORTS_VERTICAL": True}, "topotek"),
    ({**FACTORY, "KNOWN": True}, "topotek"),
    ({**FACTORY, "TOKEN": "do-not-serialize"}, "unknown"),
    (FACTORY, "future_provider"),
    ({"KNOWN": "false"}, "topotek"),
])
def test_custom_unknown_and_malformed_declarations_require_review_without_secrets(legacy, provider):
    result = assess_gimbal_guidance_migration(saved(legacy, provider))
    assert result["review_required"]
    assert "do-not-serialize" not in str(result)
    if provider not in ("topotek", "topotek_sip_udp"):
        assert result["effective_before"]["special_manoeuvres"] is None


def test_recommendation_intersects_current_and_saved_restrictions():
    config = saved({**FACTORY, "KNOWN": True, "SUPPORTS_VERTICAL": True,
                    "AZIMUTH_LIMITS_DEG": [-60., 60.]})
    proposed = candidate(config, ["vertical", "reverse_translation"], AZIMUTH_LIMITS_DEG=[-30., 90.])
    result = assess_gimbal_guidance_migration(config, candidate=proposed)
    assert result["recommended_operations"][0]["value"] == ["vertical"]
    assert result["recommended_operations"][1]["value"]["AZIMUTH_LIMITS_DEG"] == [-30., 60.]
    assert len(result["restriction_errors"]) == 2
    preserved = candidate(config, ["vertical"], AZIMUTH_LIMITS_DEG=[-30., 50.])
    assert not assess_gimbal_guidance_migration(config, candidate=preserved)["restriction_errors"]


def test_null_and_empty_manoeuvre_choices_have_distinct_canonical_meaning():
    all_support, limits = canonical_guidance_restrictions(candidate(saved()))
    no_special, _ = canonical_guidance_restrictions(candidate(saved(), []))
    assert len(all_support.to_mapping()["special_manoeuvres"]) == 3
    assert no_special.to_mapping()["special_manoeuvres"] == []
    assert limits.azimuth_limits_deg is None and limits.depression_limits_deg is None
    assert canonical_guidance_restrictions(saved())[0] == all_support


def test_disjoint_saved_and_current_windows_refuse_cleanup():
    config = saved({**FACTORY, 'AZIMUTH_LIMITS_DEG': [-60., -30.]})
    result = assess_gimbal_guidance_migration(config, candidate=candidate(
        config, AZIMUTH_LIMITS_DEG=[30., 60.]))
    assert result['recommendation_error'] == 'gimbal_observation_limits_disjoint'
    assert result['restriction_errors']


@pytest.mark.parametrize("allowed", [["not_implemented"], ["vertical", "vertical"], True, "vertical"])
def test_canonical_restrictions_reject_invalid_lists(allowed):
    with pytest.raises(ValueError):
        canonical_guidance_restrictions(candidate(saved(), allowed))


@pytest.mark.parametrize('bounds', [
    [20., -20.], [-181., 0.], [0., 181.], [True, 20.],
    ['0', 20.], [0., float('nan')], [0., float('inf')], [0.],
])
def test_canonical_observed_ray_windows_reject_invalid_numeric_bounds(bounds):
    with pytest.raises(ValueError, match='gimbal_observation_limits_invalid'):
        canonical_guidance_restrictions(candidate(saved(), AZIMUTH_LIMITS_DEG=bounds))


@pytest.fixture
def legacy_service(nested_service, monkeypatch):
    path = nested_service._project_root / "configs/config.yaml"
    current = yaml.safe_load(path.read_text())
    current["GimbalTracker"]["GUIDANCE"].pop("ALLOWED_MANOEUVRES")
    current["GimbalTracker"]["GUIDANCE"].pop("OBSERVATION_LIMITS")
    current["GimbalTracker"]["GUIDANCE"]["CAPABILITIES"] = {
        **FACTORY, "KNOWN": True, "SUPPORTS_VERTICAL": True,
        "AZIMUTH_LIMITS_DEG": [-60., 60.],
    }
    path.write_text(yaml.safe_dump(current, sort_keys=False))
    service = ConfigService(project_root=nested_service._project_root)
    runtime = service.get_config()
    monkeypatch.setattr(service, "get_applied_runtime_config", lambda: copy.deepcopy(runtime))
    monkeypatch.setattr(service, "apply_runtime_config_tiers", lambda *a, **k: {
        "applied": False, "applied_paths": [], "pending_paths": ["GimbalTracker.GUIDANCE"]})
    monkeypatch.setattr(service, "publish_runtime_config_snapshot", lambda *a, **k: None)
    return service


def migration_operations(allowed=None, limits=None):
    return [
        ConfigSyncOperation(op_type="ADD_NEW", path=ALLOWED_PATH, value=["vertical"] if allowed is None else allowed),
        ConfigSyncOperation(op_type="ADD_NEW", path=LIMITS_PATH, value={
            **UNRESTRICTED, "AZIMUTH_LIMITS_DEG": [-60., 60.]} if limits is None else limits),
        ConfigSyncOperation(op_type="REMOVE_RETIRED", path=LEGACY_PATH),
    ]


def test_startup_available_retirement_inert_and_unrelated_save_retains_review(legacy_service):
    service = legacy_service
    assert "CAPABILITIES" not in service.get_config("GimbalTracker")["GUIDANCE"]
    assert service.get_gimbal_guidance_migration()["review_required"]
    assert service.set_path(["GM_VELOCITY_VECTOR", "REQUESTED_SPEED"], 0.).valid
    assert service.save_config()
    persisted = yaml.safe_load((service._project_root / "configs/config.yaml").read_text())
    assert persisted["GimbalTracker"]["GUIDANCE"]["CAPABILITIES"]["AZIMUTH_LIMITS_DEG"] == [-60., 60.]
    report = build_defaults_sync_report(service)
    retirement = next(row for row in report["registered_retirements"] if row["path"] == LEGACY_PATH)
    assert retirement["migration"]["review_required"]


def test_custom_removal_requires_explicit_choices_and_cannot_widen(legacy_service):
    removal = [ConfigSyncOperation(op_type="REMOVE_RETIRED", path=LEGACY_PATH)]
    implicit = [ConfigSyncOperation(op_type="ADD_NEW", path=ALLOWED_PATH),
                ConfigSyncOperation(op_type="ADD_NEW", path=LIMITS_PATH), *removal]
    widening = migration_operations(["vertical", "reverse_translation"], UNRESTRICTED)
    assert not build_defaults_sync_plan(legacy_service, removal)["valid"]
    assert not build_defaults_sync_plan(legacy_service, implicit)["valid"]
    widening_plan = build_defaults_sync_plan(legacy_service, widening)
    assert not widening_plan["valid"], str(widening_plan['gimbal_guidance_migration'])
    plan = build_defaults_sync_plan(legacy_service, migration_operations())
    assert plan["valid"], plan["errors"]
    assert plan["gimbal_guidance_migration"]["effective_after"]["special_manoeuvres"] == ["vertical"]
    assert any("target-centre" in row["warning"] for row in plan["warnings"])


def test_factory_placeholder_cleanup_can_adopt_defaults_without_custom_question(legacy_service, monkeypatch):
    config = legacy_service.get_sync_config()
    config['GimbalTracker']['GUIDANCE']['CAPABILITIES'] = copy.deepcopy(FACTORY)
    monkeypatch.setattr(legacy_service, 'get_sync_config', lambda: copy.deepcopy(config))
    operations = [ConfigSyncOperation(op_type='ADD_NEW', path=ALLOWED_PATH),
                  ConfigSyncOperation(op_type='ADD_NEW', path=LIMITS_PATH),
                  ConfigSyncOperation(op_type='REMOVE_RETIRED', path=LEGACY_PATH)]
    plan = build_defaults_sync_plan(legacy_service, operations)
    assert plan['valid'], plan['errors']
    assert not plan['gimbal_guidance_migration']['review_required']


@pytest.mark.parametrize('path,value', [
    (ALLOWED_PATH, ['unimplemented']),
    (LIMITS_PATH, {'AZIMUTH_LIMITS_DEG': [30., -30.]}),
])
def test_clean_config_preview_validates_canonical_restrictions_without_legacy_object(nested_service, monkeypatch, path, value):
    config = nested_service.get_sync_config()
    ConfigService._remove_mapping_path(config, path)
    monkeypatch.setattr(nested_service, 'get_sync_config', lambda: copy.deepcopy(config))
    plan = build_defaults_sync_plan(nested_service, [ConfigSyncOperation(op_type='ADD_NEW', path=path, value=value)])
    assert not plan['valid']
    assert plan['gimbal_guidance_migration'] is None


@pytest.mark.asyncio
async def test_reviewed_migration_applies_atomically_and_clears_start_block(legacy_service):
    service = legacy_service
    operations = migration_operations()
    body = response_body(await routes.apply_defaults_sync(FakeHandler(service), _request(service, operations)))
    assert body["success"] and body["applied_count"] == 3
    assert service.get_gimbal_guidance_migration() is None
    assert service.get_path_value(ALLOWED_PATH) == ["vertical"]
    assert service.get_path_value(LIMITS_PATH)["AZIMUTH_LIMITS_DEG"] == [-60., 60.]
    assert len(service.get_backup_history()) == 1
    assert service.get_audit_log()["entries"]
    persisted = yaml.safe_load((service._project_root / "configs/config.yaml").read_text())
    assert "CAPABILITIES" not in persisted["GimbalTracker"]["GUIDANCE"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["audit", "publication"])
async def test_reviewed_migration_failure_restores_saved_review_and_choices(legacy_service, monkeypatch, failure):
    service = legacy_service
    request = _request(service, migration_operations())
    before = service.capture_persistence_snapshot()
    def fail(*a, **k):
        raise RuntimeError("migration failure")
    monkeypatch.setattr(service, "log_audit_entry" if failure == "audit" else "apply_runtime_config_tiers", fail)
    with pytest.raises(HTTPException, match="rolled back"):
        await routes.apply_defaults_sync(FakeHandler(service), request)
    assert service.capture_persistence_snapshot() == before
    assert service.get_gimbal_guidance_migration()["review_required"]
    assert service.get_path_value(ALLOWED_PATH) is None


@pytest.mark.asyncio
async def test_reviewed_migration_rejects_stale_preview(legacy_service):
    service = legacy_service
    request = _request(service, migration_operations())
    path = service._project_root / "configs/config.yaml"
    path.write_text(path.read_text() + "\n")
    response = await routes.apply_defaults_sync(FakeHandler(service), request)
    assert response.status_code == 409
    assert service.get_gimbal_guidance_migration()["review_required"]
    assert not service.get_backup_history()
