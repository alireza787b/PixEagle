"""Canonical config and migration behavior for dormant fixed-camera geometry."""

from copy import deepcopy
from pathlib import Path
import shutil

import pytest
import yaml

from classes.config_service import ConfigService
from classes.config_sync import ConfigSyncOperation, build_defaults_sync_plan, build_defaults_sync_report
from classes.fixed_camera_calibration import FixedCameraCalibration
from classes.parameters import Parameters
from scripts.generate_schema import generate_parameter_schema


ROOT = Path(__file__).resolve().parents[3]
PATH = ['VideoSource', 'FIXED_CAMERA_CALIBRATION']


@pytest.fixture
def calibration_mapping():
    return {
        'source_signature': 'sha256-v1:' + 'a'*64,
        'revision': 'synthetic-1', 'pixel_grid': 'decoder_pre_orientation',
        'image_size_px': [640, 480], 'focal_length_px': [500., 500.],
        'principal_point_px': [319.5, 239.5], 'optical_to_body_frd_wxyz': [.5, .5, .5, .5],
        'distortion_model': 'none', 'mount_kind': 'fixed',
    }


@pytest.fixture
def make_service(tmp_path):
    def make(current_calibration='missing'):
        configs = tmp_path / 'configs'
        configs.mkdir()
        for filename in ('config_default.yaml', 'config_schema.yaml', 'config_retirements.yaml'):
            shutil.copyfile(ROOT / 'configs' / filename, configs / filename)
        current = yaml.safe_load((configs / 'config_default.yaml').read_text(encoding='utf-8'))
        if current_calibration == 'missing':
            current['VideoSource'].pop(PATH[1])
        else:
            current['VideoSource'][PATH[1]] = current_calibration
        (configs / 'config.yaml').write_text(yaml.safe_dump(current, sort_keys=False), encoding='utf-8')
        return ConfigService(tmp_path)
    return make


def test_generated_nullable_object_is_closed_and_has_no_measured_defaults(make_service):
    service = make_service()
    parameter = service.get_parameter_schema(*PATH)
    generated = generate_parameter_schema(PATH[1], None, full_path='.'.join(PATH))
    assert parameter == generated
    assert parameter['type'] == 'object' and parameter['nullable'] is True
    assert parameter['default'] is None
    assert parameter['additional_properties'] is False
    assert set(parameter['required']) == set(parameter['properties'])
    assert all('default' not in child for child in parameter['properties'].values())
    assert service.get_reload_tier(*PATH) == 'system_restart'


@pytest.mark.parametrize('value', [None, 'missing'])
def test_missing_or_null_geometry_does_not_call_parser_or_rewrite_saved_config(make_service, monkeypatch, value):
    service = make_service(value)
    path = service._get_path(service.CONFIG_PATH)
    before = path.read_bytes()
    candidate = service.get_config()
    monkeypatch.setattr(ConfigService, 'get_instance', classmethod(lambda cls: service))

    def unexpected_parse(cls, value):
        raise AssertionError('Uncalibrated ordinary config must not parse geometry')
    monkeypatch.setattr(FixedCameraCalibration, 'from_mapping', classmethod(unexpected_parse))
    assert service.validate_config_mapping(candidate, require_safety=True).valid
    normalized = Parameters._validate_dependent_config(candidate, strict=True)
    assert normalized['VideoSource'] == candidate['VideoSource']
    assert service.get_effective_section('VideoSource')[PATH[1]] is None
    build_defaults_sync_report(service)
    assert path.read_bytes() == before
    if value == 'missing':
        assert PATH[1] not in service.get_config('VideoSource')


def test_valid_optional_geometry_passes_canonical_validation_and_runtime_validation(make_service, calibration_mapping, monkeypatch):
    service = make_service()
    assert service.set_path(PATH, calibration_mapping).valid
    monkeypatch.setattr(ConfigService, 'get_instance', classmethod(lambda cls: service))
    candidate = service.get_config()
    normalized = Parameters._validate_dependent_config(candidate, strict=True)
    assert normalized['VideoSource'][PATH[1]] == calibration_mapping


@pytest.mark.parametrize('changes', [
    {'source_signature': 'not-a-digest'}, {'revision': ''},
    {'image_size_px': [0, 480]}, {'focal_length_px': [0, 500]},
    {'optical_to_body_frd_wxyz': [1, 1, 0, 0]},
    {'mount_kind': 'gimbal'}, {'distortion_model': 'opencv'}, {'extra': 'undeclared'},
])
def test_invalid_opt_in_geometry_cannot_partially_change_config(make_service, calibration_mapping, changes):
    service = make_service()
    before = service.get_config()
    result = service.set_path(PATH, {**calibration_mapping, **changes})
    assert not result.valid
    assert service.get_config() == before


def test_strict_runtime_validation_rejects_invalid_supplied_geometry(make_service, calibration_mapping, monkeypatch):
    service = make_service()
    monkeypatch.setattr(ConfigService, 'get_instance', classmethod(lambda cls: service))
    candidate = service.get_config()
    candidate['VideoSource'][PATH[1]] = {**calibration_mapping, 'optical_to_body_frd_wxyz': [0, 0, 0, 0]}
    with pytest.raises(RuntimeError, match='fixed-camera calibration validation failed'):
        Parameters._validate_dependent_config(candidate, strict=True)


def test_config_sync_offers_only_null_for_missing_calibration_without_applying(make_service):
    service = make_service()
    original = service.get_config()
    disk = service._get_path(service.CONFIG_PATH).read_bytes()
    report = build_defaults_sync_report(service)
    new_entry = next(item for item in report['new_parameters'] if item['path'] == PATH)
    assert new_entry['default_value'] is None
    plan = build_defaults_sync_plan(service, [ConfigSyncOperation(op_type='ADD_NEW', path=PATH)])
    assert plan['valid']
    assert plan['operations'][0]['target_value'] is None
    assert plan['summary'] == {'requested': 1, 'applicable': 1, 'skipped': 0}
    assert service.get_config() == original
    assert service._get_path(service.CONFIG_PATH).read_bytes() == disk


def test_config_sync_preserves_existing_explicit_calibration(make_service, calibration_mapping):
    service = make_service(calibration_mapping)
    before = deepcopy(service.get_config())
    report = build_defaults_sync_report(service)
    assert all(item['path'] != PATH for item in report['new_parameters'])
    assert not any(item['path'][:2] == PATH for item in report['unknown_extensions'])
    plan = build_defaults_sync_plan(service, [ConfigSyncOperation(op_type='ADD_NEW', path=PATH)])
    assert plan['valid']
    assert plan['operations'][0]['skip']
    assert service.get_config() == before
    assert service.get_effective_section('VideoSource')[PATH[1]] == calibration_mapping


def test_explicit_null_adoption_and_saved_geometry_round_trip_use_canonical_service(make_service, calibration_mapping):
    service = make_service()
    assert service.set_path(PATH, None).valid
    assert service.save_config(backup=False)
    assert yaml.safe_load(service._get_path(service.CONFIG_PATH).read_text(encoding='utf-8'))['VideoSource'][PATH[1]] is None
    assert service.set_path(PATH, calibration_mapping).valid
    assert service.save_config(backup=False)
    loaded = ConfigService(service._project_root)
    assert loaded.get_parameter(*PATH) == calibration_mapping
