"""Registered native-image FW contract; declaration is not flight qualification."""

from copy import deepcopy
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
import yaml

from classes.bearing_geometry_policy import BearingGeometryPolicy
from classes.config_service import ConfigService
from classes.config_sync import ConfigSyncOperation, build_defaults_sync_plan, build_defaults_sync_report
from classes.follower import FollowerFactory
from classes.follower_catalog import evaluate_aircraft, evaluate_input, get_follower_profile
from classes.followers.fw_navigation_chase_follower import FWNavigationChaseFollower
from classes.parameters import Parameters
from classes.schema_manager import get_schema_manager
from classes.setpoint_handler import SetpointHandler


ROOT = Path(__file__).resolve().parents[3]
PROFILE = 'fw_navigation_chase'
SECTION = 'FW_NAVIGATION_CHASE'
GEOMETRY = dict(VERTICAL_ENTER_HORIZONTAL_NORM=.2, VERTICAL_EXIT_HORIZONTAL_NORM=.3,
                REARWARD_ENTRY_BEARING_DEG=100., FORWARD_REENTRY_BEARING_DEG=80.)


@pytest.fixture
def defaults():
    return yaml.safe_load((ROOT / 'configs/config_default.yaml').read_text())


@pytest.fixture
def published(defaults):
    previous = Parameters.get_runtime_config_snapshot()
    Parameters.publish_config_mapping(defaults)
    try:
        yield defaults
    finally:
        Parameters.publish_config_mapping(previous)


def test_factory_constructs_native_image_profile_without_extra_arguments(published):
    controller = SimpleNamespace(is_command_preview=False)
    follower = FollowerFactory.create_follower(PROFILE, controller, (0., 0.))
    assert isinstance(follower, FWNavigationChaseFollower)
    assert controller.setpoint_handler is follower.setpoint_handler
    assert follower.geometry_policy == BearingGeometryPolicy(.2, .3, 100., 80.)
    assert follower.setpoint_handler.get_transport() == 'px4_native'
    assert follower.get_control_type() == 'fixed_wing_external'
    assert follower.get_airframe_phase() == 'fixed_wing'
    assert follower.setpoint_handler.get_fields() == {}
    assert follower.get_last_command_intent() is None
    assert follower.session_controls() == []
    assert follower.enable_altitude_control is False


def test_default_geometry_comes_from_its_own_group_without_gimbal_reads(published, monkeypatch):
    config = {**GEOMETRY, 'VERTICAL_ENTER_HORIZONTAL_NORM': .1, 'FORWARD_REENTRY_BEARING_DEG': 65.}
    with monkeypatch.context() as patch:
        patch.setattr(Parameters, SECTION, config)
        patch.setattr(Parameters, 'GimbalTracker', {'GUIDANCE': {'VERTICAL_ENTER_HORIZONTAL_NORM': .9}})
        follower = FollowerFactory.create_follower(PROFILE, SimpleNamespace(is_command_preview=False), (.5, -.5))
    assert follower.geometry_policy == BearingGeometryPolicy(.1, .3, 100., 65.)


@pytest.mark.parametrize('configured', [None, {}, {**GEOMETRY, 'extra': 1}])
def test_missing_or_malformed_profile_geometry_has_no_constructor_fallback(published, monkeypatch, configured):
    with monkeypatch.context() as patch:
        patch.setattr(Parameters, SECTION, configured)
        with pytest.raises(ValueError, match='bearing_geometry_configuration_invalid'):
            FollowerFactory.create_follower(PROFILE, SimpleNamespace(is_command_preview=False), (0., 0.))


def test_catalog_separates_declared_phase_permission_from_native_vtol_and_input_gates():
    profile = get_follower_profile(PROFILE)
    assert profile.implementation_available
    assert profile.family == 'fixed_wing' and profile.visibility == 'experimental'
    assert profile.phase_command_contracts == {'fixed_wing': 'fixed_wing_external'}
    assert profile.live_qualified_phases == ('fixed_wing',)
    assert evaluate_aircraft(profile, 'fixed_wing').eligible
    assert evaluate_aircraft(profile, 'vtol', observed_phase='fixed_wing', native_vtol_verified=True).eligible
    assert evaluate_aircraft(profile, 'multicopter').reason_code == 'follower_aircraft_incompatible'
    assert evaluate_aircraft(profile, 'vtol', observed_phase='fixed_wing').reason_code == 'vtol_transition_release_unqualified'
    assert evaluate_input(profile, get_schema_manager(), 'POSITION_2D', tracker_name='CSRTTracker').eligible
    assert not evaluate_input(profile, get_schema_manager(), 'GIMBAL_ANGLES', tracker_name='GimbalTracker').eligible
    declaration = SetpointHandler.get_profile_info(PROFILE)['session_controls']['requested_speed']
    assert declaration == {'label': 'Airspeed', 'unit': 'm/s', 'step': .5}


def test_registration_preserves_public_starter_settings(defaults):
    assert defaults[SECTION] == GEOMETRY
    assert defaults['VideoSource']['VIDEO_SOURCE_TYPE'] == 'VIDEO_FILE'
    assert defaults['Tracking']['DEFAULT_TRACKING_ALGORITHM'] == 'CSRT'
    assert defaults['Follower']['FOLLOWER_MODE'] == 'mc_velocity_position'
    assert defaults['Follower']['General']['ENABLE_ALTITUDE_CONTROL'] is False
    assert defaults['FOLLOWER_CIRCUIT_BREAKER'] is True
    assert defaults['Safety']['GlobalLimits']['ALTITUDE_SAFETY_ENABLED'] is True
    assert SECTION not in defaults['Follower']['FollowerOverrides']
    assert SECTION not in defaults['Safety']['FollowerOverrides']


def test_registered_profile_uses_shared_altitude_permission_and_safety_identity(published):
    config = deepcopy(published)
    config['Follower']['FollowerOverrides'][SECTION] = {'ENABLE_ALTITUDE_CONTROL': True}
    config['Safety']['FollowerOverrides'][SECTION] = {'MIN_ALTITUDE': 12.0}
    Parameters.publish_config_mapping(config)
    follower = FollowerFactory.create_follower(PROFILE, SimpleNamespace(is_command_preview=False), (0., 0.))
    assert follower.enable_altitude_control is True
    assert follower.altitude_limits.min_altitude == 12.0
    assert follower.altitude_limits.safety_enabled is True


def test_fixed_wing_safety_display_type_does_not_change_the_resolved_limits(published):
    from classes.safety_manager import get_safety_manager
    from classes.safety_types import VehicleType

    manager = get_safety_manager()
    limits = manager.get_follower_limits(SECTION)
    assert limits.vehicle_type is VehicleType.FIXED_WING
    assert limits.altitude == manager.get_altitude_limits(None)
    assert limits.velocity == manager.get_velocity_limits(None)
    assert limits.rates == manager.get_rate_limits(None)


def test_visualizer_resolves_native_image_contract_from_canonical_metadata():
    from classes.sih_visualization import _expected_contract

    assert _expected_contract(PROFILE, 'fixed_wing') == ('fixed_wing', 'image_position_2d', 'fixed_wing_external')


def test_generated_settings_and_sparse_override_catalogs_share_profile_identity():
    schema = yaml.safe_load((ROOT / 'configs/config_schema.yaml').read_text())['sections']
    assert set(schema[SECTION]['parameters']) == set(GEOMETRY)
    for key in GEOMETRY:
        parameter = schema[SECTION]['parameters'][key]
        assert parameter['default'] == GEOMETRY[key]
        assert parameter['reload_tier'] == 'follower_restart'
    for group in ('Follower', 'Safety', 'TargetContinuity'):
        overrides = schema[group]['parameters']['FollowerOverrides']
        assert SECTION in overrides['properties']
        assert overrides['properties'][SECTION]['required'] == []
        assert overrides['properties'][SECTION]['default'] == {}
    options = schema['Follower']['parameters']['FOLLOWER_MODE']['options']
    assert any(option['value'] == PROFILE for option in options)


@pytest.mark.parametrize('values', [None, {}, {**GEOMETRY, 'extra': 1},
    {**GEOMETRY, 'VERTICAL_ENTER_HORIZONTAL_NORM': .4},
    {**GEOMETRY, 'REARWARD_ENTRY_BEARING_DEG': 70.},
    {**GEOMETRY, 'VERTICAL_ENTER_HORIZONTAL_NORM': True},
    {**GEOMETRY, 'FORWARD_REENTRY_BEARING_DEG': float('nan')}])
def test_geometry_parser_rejects_incomplete_unknown_and_contradictory_values(values):
    with pytest.raises(ValueError):
        BearingGeometryPolicy.from_mapping(values)


@pytest.fixture
def service(tmp_path, defaults):
    path = tmp_path / 'configs'
    path.mkdir()
    for name in ('config_default.yaml', 'config_schema.yaml', 'config_retirements.yaml'):
        shutil.copyfile(ROOT / 'configs' / name, path / name)
    current = deepcopy(defaults)
    current.pop(SECTION)
    (path / 'config.yaml').write_text(yaml.safe_dump(current, sort_keys=False))
    return ConfigService(tmp_path)


def test_missing_legacy_geometry_is_previewed_without_mutating_or_inventing_values(service, monkeypatch):
    monkeypatch.setattr(ConfigService, 'get_instance', classmethod(lambda cls: service))
    original = service.get_config()
    disk = service._get_path(service.CONFIG_PATH).read_bytes()
    assert SECTION not in Parameters._validate_dependent_config(original, strict=True)
    report = build_defaults_sync_report(service)
    new = [item for item in report['new_parameters'] if item['path'][0] == SECTION]
    assert {tuple(item['path']) for item in new} == {(SECTION, key) for key in GEOMETRY}
    plan = build_defaults_sync_plan(service, [ConfigSyncOperation(op_type='ADD_NEW', path=item['path']) for item in new])
    assert plan['valid']
    assert plan['summary']['applicable'] == len(GEOMETRY)
    assert service.get_config() == original
    assert service._get_path(service.CONFIG_PATH).read_bytes() == disk


def test_saved_geometry_and_general_altitude_override_are_preserved(service, monkeypatch):
    custom = {**GEOMETRY, 'VERTICAL_ENTER_HORIZONTAL_NORM': .1}
    candidate = service.get_config()
    candidate[SECTION] = custom
    candidate['Follower']['FollowerOverrides'][SECTION] = {'ENABLE_ALTITUDE_CONTROL': True}
    monkeypatch.setattr(ConfigService, 'get_instance', classmethod(lambda cls: service))
    assert service.validate_config_mapping(candidate, require_safety=True).valid
    assert Parameters._validate_dependent_config(candidate, strict=True)[SECTION] == custom
    assert candidate['Follower']['FollowerOverrides'][SECTION]['ENABLE_ALTITUDE_CONTROL'] is True


@pytest.mark.parametrize('changes', [
    {'VERTICAL_ENTER_HORIZONTAL_NORM': .4}, {'FORWARD_REENTRY_BEARING_DEG': 110.}, {'extra': 1},
])
def test_config_service_and_strict_runtime_use_the_same_semantic_parser(service, monkeypatch, changes):
    candidate = service.get_config()
    candidate[SECTION] = {**GEOMETRY, **changes}
    monkeypatch.setattr(ConfigService, 'get_instance', classmethod(lambda cls: service))
    assert not service.validate_config_mapping(candidate, require_safety=True).valid
    with pytest.raises(RuntimeError, match='FW navigation geometry validation failed'):
        Parameters._validate_dependent_config(candidate, strict=True)
