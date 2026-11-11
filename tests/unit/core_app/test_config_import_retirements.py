"""Merge imports preserve inert retirement review without publishing legacy data."""

import copy
from pathlib import Path

from fastapi import HTTPException
import pytest
import yaml

from classes import api_legacy_config_routes as routes
from classes.config_service import ConfigService
from classes.config_sync import ConfigSyncOperation
from tests.unit.core_app.test_api_legacy_config_routes import FakeHandler, response_body
from tests.unit.core_app.test_config_nested_sync import _request


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[3]
LEGACY = ['GimbalTracker', 'GUIDANCE', 'CAPABILITIES']
ALLOWED = ['GimbalTracker', 'GUIDANCE', 'ALLOWED_MANOEUVRES']
LIMITS = ['GimbalTracker', 'GUIDANCE', 'OBSERVATION_LIMITS']
CUSTOM = dict(KNOWN=True, SUPPORTS_VERTICAL=True, SUPPORTS_REVERSE=False,
              SUPPORTS_YAW_FALLBACK=False, AZIMUTH_LIMITS_DEG=[-60., 60.],
              DEPRESSION_LIMITS_DEG=[-90., 90.])


def pending_retirements(service):
    saved = service.get_sync_config()
    return {
        tuple(item['path']): copy.deepcopy(ConfigService._get_mapping_path(saved, item['path']))
        for item in service.get_retirement_registry()['retirements']
        if ConfigService._mapping_path_exists(saved, item['path'])
    }


@pytest.fixture
def service(tmp_path, monkeypatch):
    directory = tmp_path / 'configs'
    directory.mkdir()
    for name in ['config_default.yaml', 'config_schema.yaml', 'config_retirements.yaml']:
        (directory / name).write_bytes((ROOT / 'configs' / name).read_bytes())
    config = yaml.safe_load((directory / 'config_default.yaml').read_text())
    guidance = config['GimbalTracker']['GUIDANCE']
    guidance.pop('ALLOWED_MANOEUVRES')
    guidance.pop('OBSERVATION_LIMITS')
    guidance['CAPABILITIES'] = copy.deepcopy(CUSTOM)
    config['GM_VELOCITY_CHASE']['DEFAULT_THRUST'] = .8
    config['GM_VELOCITY_CHASE']['REQUIRED_TRACKER_FIELDS'] = ['angular']
    config['Follower']['General']['TARGET_LOSS_TIMEOUT'] = 9.
    (directory / 'config.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
    value = ConfigService(project_root=tmp_path)
    runtime = value.get_config()
    monkeypatch.setattr(value, 'get_applied_runtime_config', lambda: copy.deepcopy(runtime))
    monkeypatch.setattr(value, 'apply_runtime_config_tiers', lambda *a, **k: {
        'applied': False, 'applied_paths': [], 'pending_paths': ['GimbalTracker.GUIDANCE'],
    })
    monkeypatch.setattr(value, 'publish_runtime_config_snapshot', lambda *a, **k: None)
    return value


def assert_retained_after_reload(service, expected):
    assert pending_retirements(service) == expected
    runtime = service.get_config()
    for path in expected:
        assert not ConfigService._mapping_path_exists(runtime, path)
    assert service.get_gimbal_guidance_migration()['review_required']
    assert service.save_config(backup=False)
    service.reload()
    assert pending_retirements(service) == expected
    assert service.get_gimbal_guidance_migration()['review_required']


def test_unrelated_merge_save_reload_keeps_all_pending_retirements(service):
    expected = pending_retirements(service)
    assert len(expected) == 4
    success, _ = service.import_config({'GM_VELOCITY_VECTOR': {'REQUESTED_SPEED': 0.}}, 'merge')
    assert success
    assert_retained_after_reload(service, expected)


@pytest.mark.parametrize('path', [['GimbalTracker'], ['GimbalTracker', 'GUIDANCE'], ['GM_VELOCITY_CHASE']])
def test_ancestor_update_preserves_inert_retirements(service, path):
    expected = pending_retirements(service)
    replacement = ConfigService._get_mapping_path(service.get_default(), path)
    assert service.set_path(path, replacement).valid
    assert_retained_after_reload(service, expected)


@pytest.mark.parametrize('path,value', [(LEGACY, {**CUSTOM, 'SUPPORTS_REVERSE': True}),
    (['GM_VELOCITY_CHASE', 'DEFAULT_THRUST'], .2)])
def test_merge_cannot_overwrite_pending_retirement(service, path, value, caplog):
    before = service.get_sync_config()
    disk = service.capture_persistence_snapshot()
    payload = {}
    ConfigService._set_mapping_path(payload, path, value)
    success, diffs = service.import_config(payload, 'merge')
    assert not success and not diffs
    assert 'Config Sync preview/apply' in caplog.text
    assert service.get_sync_config() == before
    assert service.capture_persistence_snapshot() == disk


@pytest.mark.parametrize('path,existing,supplied', [
    (LEGACY, {**CUSTOM, 'KNOWN': 1, 'SUPPORTS_REVERSE': True,
              'SUPPORTS_YAW_FALLBACK': True, 'AZIMUTH_LIMITS_DEG': [-180., 180.]},
     {**CUSTOM, 'KNOWN': True, 'SUPPORTS_REVERSE': True,
      'SUPPORTS_YAW_FALLBACK': True, 'AZIMUTH_LIMITS_DEG': [-180., 180.]}),
    (['GM_VELOCITY_CHASE', 'DEFAULT_THRUST'], 0, False),
    (['GM_VELOCITY_CHASE', 'DEFAULT_THRUST'], False, 0),
    (['GM_VELOCITY_CHASE', 'REQUIRED_TRACKER_FIELDS'], [1], [True]),
])
def test_merge_cannot_retype_equal_pending_values(service, tmp_path, path, existing, supplied, caplog):
    from classes.config_sync import _digest

    config_path = tmp_path / 'configs' / 'config.yaml'
    saved = yaml.safe_load(config_path.read_text())
    ConfigService._set_mapping_path(saved, path, existing)
    config_path.write_text(yaml.safe_dump(saved, sort_keys=False))
    service.reload()
    before = service.capture_persistence_snapshot()
    saved_digest = _digest(service.get_sync_config())
    if path == LEGACY:
        assert service.get_gimbal_guidance_migration()['review_required']
    payload = {}
    ConfigService._set_mapping_path(payload, path, supplied)
    assert service.import_config(payload, 'merge') == (False, [])
    assert 'Config Sync preview/apply' in caplog.text
    assert _digest(service.get_sync_config()) == saved_digest
    assert service.capture_persistence_snapshot() == before
    if path == LEGACY:
        assert service.get_gimbal_guidance_migration()['review_required']


def test_matching_retired_data_in_merge_is_read_only_and_retained(service):
    expected = pending_retirements(service)
    assert service.import_config({'GimbalTracker': {'GUIDANCE': {'CAPABILITIES': copy.deepcopy(CUSTOM)}}}, 'merge')[0]
    assert_retained_after_reload(service, expected)


def test_matching_retirement_accepts_roundtrip_yaml_scalar_subclass(service):
    from io import StringIO
    from ruamel.yaml import YAML

    payload = YAML().load(StringIO('GM_VELOCITY_CHASE:\n  DEFAULT_THRUST: 0.8\n'))
    value = payload['GM_VELOCITY_CHASE']['DEFAULT_THRUST']
    assert isinstance(value, float) and type(value) is not float
    expected = pending_retirements(service)
    assert service.import_config(payload, 'merge') == (True, [])
    assert_retained_after_reload(service, expected)


def test_new_imported_retirement_is_inert_and_saved(service):
    path = ['MC_VELOCITY_GROUND', 'COORDINATE_CORRECTIONS_ENABLED']
    expected = {**pending_retirements(service), tuple(path): True}
    success, diffs = service.import_config({'MC_VELOCITY_GROUND': {'COORDINATE_CORRECTIONS_ENABLED': True}}, 'merge')
    assert success
    assert len(diffs) == 1
    assert diffs[0].path == '.'.join(path)
    assert diffs[0].change_type == 'added'
    assert diffs[0].new_value is True
    assert_retained_after_reload(service, expected)


@pytest.mark.asyncio
async def test_retired_only_api_import_reports_saved_change_without_runtime_change(service):
    before_runtime = service.get_config()
    result = response_body(await routes.import_config(FakeHandler(service), routes.ConfigImportRequest(
        data={'MC_VELOCITY_GROUND': {'COORDINATE_CORRECTIONS_ENABLED': True}}, merge_mode='merge',
    )))
    assert result['success']
    assert result['changes_count'] == 1
    assert result['changes'][0]['path'] == 'MC_VELOCITY_GROUND.COORDINATE_CORRECTIONS_ENABLED'
    assert service.get_config() == before_runtime
    service.reload()
    assert service.get_config() == before_runtime
    assert pending_retirements(service)[('MC_VELOCITY_GROUND', 'COORDINATE_CORRECTIONS_ENABLED')] is True


def test_invalid_ancestor_import_leaves_review_and_state_intact(service):
    before = service.get_sync_config()
    assert service.import_config({'GimbalTracker': None}, 'merge') == (False, [])
    assert service.get_sync_config() == before


def test_explicit_whole_replace_discards_previous_retirements(service):
    assert service.import_config({'VideoSource': {'CAPTURE_WIDTH': 1280}}, 'replace')[0]
    assert pending_retirements(service) == {}
    assert service.get_gimbal_guidance_migration() is None
    assert service.save_config(backup=False)
    service.reload()
    assert pending_retirements(service) == {}


def test_replace_with_legacy_input_keeps_it_inert_for_review(service):
    assert service.import_config({'GimbalTracker': {'GUIDANCE': {'CAPABILITIES': copy.deepcopy(CUSTOM)}}}, 'replace')[0]
    assert_retained_after_reload(service, {tuple(LEGACY): CUSTOM})


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['audit', 'publication'])
async def test_failed_merge_import_restores_review_bytes_and_state(service, monkeypatch, failure):
    before = service.capture_persistence_snapshot()
    pending = pending_retirements(service)

    def fail(*a, **k):
        raise RuntimeError('injected merge import failure')

    monkeypatch.setattr(service, 'log_audit_entry' if failure == 'audit' else 'apply_runtime_config_tiers', fail)
    with pytest.raises(HTTPException):
        await routes.import_config(FakeHandler(service), routes.ConfigImportRequest(
            data={'GM_VELOCITY_VECTOR': {'REQUESTED_SPEED': 0.}}, merge_mode='merge',
        ))
    assert service.capture_persistence_snapshot() == before
    assert pending_retirements(service) == pending
    assert service.get_gimbal_guidance_migration()['review_required']


@pytest.mark.asyncio
async def test_explicit_retirement_after_merge_clears_only_selected_review(service):
    pending = pending_retirements(service)
    assert service.import_config({'GM_VELOCITY_VECTOR': {'REQUESTED_SPEED': 0.}}, 'merge')[0]
    assert service.save_config(backup=False)
    operations = [
        ConfigSyncOperation(op_type='ADD_NEW', path=ALLOWED, value=['vertical']),
        ConfigSyncOperation(op_type='ADD_NEW', path=LIMITS, value={
            'AZIMUTH_LIMITS_DEG': [-60., 60.], 'DEPRESSION_LIMITS_DEG': None}),
        ConfigSyncOperation(op_type='REMOVE_RETIRED', path=LEGACY),
    ]
    result = response_body(await routes.apply_defaults_sync(FakeHandler(service), _request(service, operations)))
    assert result['success']
    service.reload()
    assert service.get_gimbal_guidance_migration() is None
    assert pending_retirements(service) == {path: value for path, value in pending.items() if path != tuple(LEGACY)}
