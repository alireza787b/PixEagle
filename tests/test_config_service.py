"""
Tests for ConfigService
========================

Comprehensive test suite for the ConfigService class.
Uses pytest for testing.

Run with: pytest tests/test_config_service.py -v
"""

import copy
import math
import os
import sys
import pytest
import tempfile
import shutil
import threading
from pathlib import Path
import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from classes.config_service import (
    ConfigService,
    ValidationResult,
    ValidationStatus,
    DiffEntry,
    ConfigBackup
)
from classes.parameters import Parameters


class TestConfigServiceSingleton:
    """Test singleton pattern."""

    def test_get_instance_returns_same_object(self):
        """Singleton should always return the same instance."""
        instance1 = ConfigService.get_instance()
        instance2 = ConfigService.get_instance()
        assert instance1 is instance2

    def test_singleton_is_not_none(self):
        """Singleton should return a valid instance."""
        instance = ConfigService.get_instance()
        assert instance is not None


class TestConfigServiceSchema:
    """Test schema-related methods."""

    @pytest.fixture
    def service(self):
        """Get ConfigService instance."""
        return ConfigService.get_instance()

    def test_get_schema_returns_dict(self, service):
        """Schema should be a dictionary."""
        schema = service.get_schema()
        assert isinstance(schema, dict)

    def test_get_schema_has_sections(self, service):
        """Schema should have sections."""
        schema = service.get_schema()
        assert 'sections' in schema

    def test_get_schema_by_section(self, service):
        """Get schema for a specific section."""
        schema = service.get_schema('VideoSource')
        assert isinstance(schema, dict)
        if schema:  # May be empty if schema not loaded
            assert 'parameters' in schema or 'display_name' in schema

    def test_get_categories(self, service):
        """Should return category definitions."""
        cats = service.get_categories()
        assert isinstance(cats, dict)
        # Common categories
        expected_cats = ['video', 'tracking', 'follower', 'safety']
        for cat in expected_cats:
            if cats:  # May be empty if schema not loaded
                assert cat in cats

    def test_get_sections(self, service):
        """Should return list of section metadata."""
        sections = service.get_sections()
        assert isinstance(sections, list)
        if sections:
            first = sections[0]
            assert 'name' in first
            assert 'display_name' in first
            assert 'category' in first

    def test_get_parameter_schema(self, service):
        """Should return schema for specific parameter."""
        param_schema = service.get_parameter_schema('VideoSource', 'CAPTURE_WIDTH')
        if param_schema:
            assert 'type' in param_schema
            assert 'default' in param_schema


class TestConfigServiceRead:
    """Test config read methods."""

    @pytest.fixture
    def service(self):
        return ConfigService.get_instance()

    def test_get_config_returns_dict(self, service):
        """Config should be a dictionary."""
        config = service.get_config()
        assert isinstance(config, dict)

    def test_get_config_by_section(self, service):
        """Get config for specific section."""
        config = service.get_config('VideoSource')
        assert isinstance(config, dict)

    def test_get_default_returns_dict(self, service):
        """Default config should be a dictionary."""
        default = service.get_default()
        assert isinstance(default, dict)

    def test_get_parameter(self, service):
        """Should get specific parameter value."""
        val = service.get_parameter('VideoSource', 'VIDEO_SOURCE_TYPE')
        # Value could be None if config not loaded
        assert val is None or isinstance(val, str)

    def test_get_default_parameter(self, service):
        """Should get default value for parameter."""
        val = service.get_default_parameter('VideoSource', 'VIDEO_SOURCE_TYPE')
        assert val is None or isinstance(val, str)

    def test_public_state_getters_return_defensive_snapshots(self, service):
        config = service.get_config()
        defaults = service.get_default()
        schema = service.get_schema()

        config['VideoSource']['CAPTURE_WIDTH'] = -1
        defaults['VideoSource']['CAPTURE_WIDTH'] = -1
        schema['sections']['VideoSource']['parameters']['CAPTURE_WIDTH']['min'] = -1

        assert service.get_parameter('VideoSource', 'CAPTURE_WIDTH') != -1
        assert service.get_default_parameter('VideoSource', 'CAPTURE_WIDTH') != -1
        assert service.get_parameter_schema(
            'VideoSource',
            'CAPTURE_WIDTH',
        )['min'] != -1

    def test_missing_path_preserves_caller_sentinel_identity(self, service):
        marker = object()

        assert service.get_path_value(
            ['Missing', 'VALUE'],
            default=marker,
        ) is marker
        assert service.path_exists(['Missing', 'VALUE']) is False

    def test_state_reader_cannot_observe_in_progress_mutation(self, service):
        original = service._config
        mutation_entered = threading.Event()
        release_mutation = threading.Event()
        reader_done = threading.Event()
        observations = []

        def mutate_then_rollback():
            with service.mutation_guard():
                service._config = {'Transient': {'VALUE': 1}}
                mutation_entered.set()
                assert release_mutation.wait(2.0)
                service._config = original

        def read_snapshot():
            observations.append(service.get_config())
            reader_done.set()

        writer = threading.Thread(target=mutate_then_rollback)
        reader = threading.Thread(target=read_snapshot)
        writer.start()
        try:
            assert mutation_entered.wait(1.0)
            reader.start()
            assert not reader_done.wait(0.05)
            release_mutation.set()
            writer.join(timeout=2.0)
            reader.join(timeout=2.0)
        finally:
            release_mutation.set()
            writer.join(timeout=2.0)
            if reader.ident is not None:
                reader.join(timeout=2.0)
            service._config = original

        assert observations == [original]


class TestConfigServiceValidation:
    """Test validation methods."""

    @pytest.fixture
    def service(self):
        return ConfigService.get_instance()

    def test_validate_integer_valid(self, service):
        """Valid integer should pass validation."""
        result = service.validate_value('VideoSource', 'CAPTURE_WIDTH', 640)
        assert result.valid is True

    @pytest.mark.parametrize('invalid_value', [None, '0.5', True, math.nan, math.inf])
    def test_validate_global_limits_rejects_unsafe_nested_values(
        self,
        service,
        invalid_value,
    ):
        global_limits = service.get_default_parameter('Safety', 'GlobalLimits')
        global_limits['MAX_VELOCITY_FORWARD'] = invalid_value

        result = service.validate_value('Safety', 'GlobalLimits', global_limits)

        assert result.valid is False

    def test_validate_integer_below_min(self, service):
        """Integer below min should fail."""
        result = service.validate_value('VideoSource', 'CAPTURE_WIDTH', -100)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_validate_boolean_valid(self, service):
        """Valid boolean should pass."""
        result = service.validate_value('Streaming', 'ENABLE_STREAMING', True)
        assert result.valid is True

    def test_validate_string_valid(self, service):
        """Valid string should pass."""
        result = service.validate_value('VideoSource', 'VIDEO_FILE_PATH', 'test.mp4')
        assert result.valid is True

    def test_validate_unknown_parameter(self, service):
        """Unknown sections are not implicit extension points."""
        result = service.validate_value('NonExistent', 'PARAM', 'value')
        assert result.valid is False
        assert 'not declared' in result.errors[0]

    def test_validate_unknown_parameter_in_schema_owned_section_rejects(self, service):
        result = service.validate_value(
            'MC_VELOCITY_CHASE',
            'MAX_VELOCITY_FORWARD',
            0.75,
        )

        assert result.valid is False
        assert 'not declared' in result.errors[0]

    def test_whole_config_rejects_unknown_root_and_known_section_parameter(
        self,
        service,
    ):
        unknown_root = copy.deepcopy(service.get_default())
        unknown_root['UnregisteredPlugin'] = {'enabled': True}
        unknown_parameter = copy.deepcopy(service.get_default())
        unknown_parameter['VideoSource']['LEGACY_CAPTURE_MODE'] = 'unsafe'

        root_result = service.validate_config_mapping(
            unknown_root,
            require_safety=True,
        )
        parameter_result = service.validate_config_mapping(
            unknown_parameter,
            require_safety=True,
        )

        assert root_result.valid is False
        assert any('UnregisteredPlugin' in error for error in root_result.errors)
        assert parameter_result.valid is False
        assert any(
            'VideoSource.LEGACY_CAPTURE_MODE' in error
            for error in parameter_result.errors
        )

    def test_whole_config_preserves_only_declared_extension_sections(
        self,
        service,
    ):
        original_schema = service._schema
        service._schema = copy.deepcopy(original_schema)
        service._schema['meta']['extension_sections'] = {
            'VendorTelemetry': {
                'type': 'object',
                'properties': {
                    'endpoint': {'type': 'string'},
                },
                'required': ['endpoint'],
                'additional_properties': False,
            },
        }
        try:
            candidate = copy.deepcopy(service.get_default())
            candidate['VendorTelemetry'] = {'endpoint': 'udp://127.0.0.1:9000'}
            valid_result = service.validate_config_mapping(
                candidate,
                require_safety=True,
            )
            candidate['VendorTelemetry']['hidden'] = True
            invalid_result = service.validate_config_mapping(
                candidate,
                require_safety=True,
            )
        finally:
            service._schema = original_schema

        assert valid_result.valid is True
        assert invalid_result.valid is False
        assert any('hidden' in error for error in invalid_result.errors)

    def test_whole_config_preserves_exact_registered_retirement(self, service):
        candidate = copy.deepcopy(service.get_default())
        candidate['GM_VELOCITY_CHASE']['CONTROL_MODE'] = 'BODY'

        result = service.validate_config_mapping(candidate, require_safety=True)

        assert result.valid is True
        assert any(
            'GM_VELOCITY_CHASE.CONTROL_MODE' in warning
            for warning in result.warnings
        )
        direct_write = service.validate_value(
            'GM_VELOCITY_CHASE',
            'CONTROL_MODE',
            'BODY',
        )
        assert direct_write.valid is False

    def test_validate_recommended_range_warning(self, service):
        """Value outside recommended range should produce warning, not error."""
        # SMART_TRACKER_CONFIDENCE_THRESHOLD has recommended_min=0.15, recommended_max=0.7
        result = service.validate_value(
            'SmartTracker', 'SMART_TRACKER_CONFIDENCE_THRESHOLD', 0.05
        )
        # Should be valid (within hard limits 0.0-1.0)
        assert result.valid is True
        # Should have a recommended range warning
        rec_warnings = [w for w in result.warnings if 'recommended' in w.lower()]
        assert len(rec_warnings) > 0, "Should warn about being below recommended minimum"

    def test_validate_within_recommended_range_no_warning(self, service):
        """Value within recommended range should not trigger recommended warnings."""
        result = service.validate_value(
            'SmartTracker', 'SMART_TRACKER_CONFIDENCE_THRESHOLD', 0.3
        )
        assert result.valid is True
        rec_warnings = [w for w in result.warnings if 'recommended' in w.lower()]
        assert len(rec_warnings) == 0, "No recommended range warning expected"

    def test_mavlink_request_retries_uses_integer_schema_bounds(self, service):
        """MAVLink retry count must be validated by ConfigService and dashboard editors."""
        param_schema = service.get_parameter_schema('MAVLink', 'MAVLINK_REQUEST_RETRIES')

        assert param_schema['type'] == 'integer'
        assert service.validate_value('MAVLink', 'MAVLINK_REQUEST_RETRIES', 1).valid is True
        assert service.validate_value('MAVLink', 'MAVLINK_REQUEST_RETRIES', 'bad').valid is False
        assert service.validate_value('MAVLink', 'MAVLINK_REQUEST_RETRIES', 99).valid is False

    @pytest.mark.parametrize('value', [math.inf, -math.inf, math.nan])
    def test_non_finite_numbers_are_rejected(self, service, value):
        result = service._validate_value_against_schema(
            'Synthetic.NUMBER', value, {'type': 'number'}
        )

        assert result.valid is False
        assert 'finite' in result.errors[0]

    def test_options_arrays_and_nested_properties_are_enforced(self, service):
        option_result = service._validate_value_against_schema(
            'Synthetic.MODE',
            'invalid',
            {
                'type': 'string',
                'options': [{'value': 'valid', 'label': 'Valid'}],
            },
        )
        array_result = service._validate_value_against_schema(
            'Synthetic.VALUES',
            [1, 'invalid'],
            {'type': 'array', 'item_type': 'number', 'min_items': 2, 'max_items': 3},
        )
        object_result = service._validate_value_against_schema(
            'Synthetic.NESTED',
            {'limit': -1},
            {
                'type': 'object',
                'properties': {'limit': {'type': 'integer', 'min': 0}},
            },
        )

        assert option_result.valid is False
        assert array_result.valid is False
        assert object_result.valid is False

    def test_runtime_legacy_alias_is_non_persistent_and_not_writable(self, service):
        candidate = copy.deepcopy(service.get_default())
        candidate['Segmentation']['DEFAULT_SEGMENTATION_ALGORITHM'] = 'yolov11n.pt'

        normalized, warnings = service.normalize_declared_legacy_values(candidate)

        assert candidate['Segmentation']['DEFAULT_SEGMENTATION_ALGORITHM'] == 'yolov11n.pt'
        assert normalized['Segmentation']['DEFAULT_SEGMENTATION_ALGORITHM'] == 'disabled'
        assert len(warnings) == 1
        assert 'sync persisted configuration' in warnings[0]
        assert service.validate_config_mapping(normalized, require_safety=True).valid is True
        assert service.validate_value(
            'Segmentation',
            'DEFAULT_SEGMENTATION_ALGORITHM',
            'yolov11n.pt',
        ).valid is False

    def test_strict_mapping_requires_complete_safety_limits(self, service):
        candidate = copy.deepcopy(service.get_default())
        candidate['Safety']['GlobalLimits'].pop('MIN_ALTITUDE')

        result = service.validate_config_mapping(candidate, require_safety=True)

        assert result.valid is False
        assert any('MIN_ALTITUDE' in error for error in result.errors)

    def test_safety_follower_override_keys_and_limits_are_strict(self, service):
        lowercase = copy.deepcopy(service.get_default())
        lowercase['Safety']['FollowerOverrides']['mc_velocity_chase'] = {
            'MAX_VELOCITY_FORWARD': 0.25,
        }
        unknown_limit = copy.deepcopy(service.get_default())
        unknown_limit['Safety']['FollowerOverrides']['MC_VELOCITY_CHASE'] = {
            'MAX_SPEED': 0.25,
        }

        lowercase_result = service.validate_config_mapping(
            lowercase,
            require_safety=True,
        )
        unknown_limit_result = service.validate_config_mapping(
            unknown_limit,
            require_safety=True,
        )

        assert lowercase_result.valid is False
        assert any('mc_velocity_chase' in error for error in lowercase_result.errors)
        assert unknown_limit_result.valid is False
        assert any('MAX_SPEED' in error for error in unknown_limit_result.errors)

    def test_safety_follower_override_cannot_weaken_global_envelope(self, service):
        candidate = copy.deepcopy(service.get_default())
        candidate['Safety']['FollowerOverrides']['MC_VELOCITY_CHASE'] = {
            'MAX_VELOCITY_FORWARD': 0.75,
            'RTL_ON_VIOLATION': False,
        }

        result = service.validate_config_mapping(candidate, require_safety=True)

        assert result.valid is False
        assert any(
            'weakens the hard global safety envelope' in error
            for error in result.errors
        )


class TestConfigServiceWrite:
    """Test config write methods."""

    @pytest.fixture
    def service(self):
        return ConfigService.get_instance()

    def test_set_parameter_valid(self, service):
        """Setting valid parameter should succeed."""
        result = service.set_parameter('VideoSource', 'CAPTURE_WIDTH', 800)
        assert result.valid is True
        assert service.get_parameter('VideoSource', 'CAPTURE_WIDTH') == 800

    def test_set_parameter_invalid(self, service):
        """Setting invalid parameter should fail."""
        result = service.set_parameter('VideoSource', 'CAPTURE_WIDTH', -100)
        assert result.valid is False

    def test_set_parameter_without_validation(self, service):
        """Should be able to skip validation."""
        original = service.get_parameter('VideoSource', 'CAPTURE_WIDTH')
        try:
            result = service.set_parameter(
                'VideoSource',
                'CAPTURE_WIDTH',
                -100,
                validate=False,
            )
            assert result.valid is True
        finally:
            service.set_parameter(
                'VideoSource',
                'CAPTURE_WIDTH',
                original,
                validate=False,
            )

    def test_set_parameter_rejects_safety_invalid_complete_candidate(self, service):
        original = service.get_parameter('Safety', 'FollowerOverrides')
        invalid = copy.deepcopy(original)
        invalid['MC_VELOCITY_CHASE'] = {
            'MAX_VELOCITY_FORWARD': 0.75,
        }

        result = service.set_parameter(
            'Safety',
            'FollowerOverrides',
            invalid,
        )

        assert result.valid is False
        assert any(
            'weakens the hard global safety envelope' in error
            for error in result.errors
        )
        assert service.get_parameter('Safety', 'FollowerOverrides') == original

    def test_set_section_rejects_safety_invalid_complete_candidate(self, service):
        original = service.get_config('Safety')
        invalid = copy.deepcopy(original['FollowerOverrides'])
        invalid['MC_VELOCITY_CHASE'] = {
            'RTL_ON_VIOLATION': False,
        }

        result = service.set_section(
            'Safety',
            {
                'FollowerOverrides': invalid,
            },
        )

        assert result.valid is False
        assert service.get_config('Safety') == original

    def test_set_section(self, service):
        """Setting multiple parameters in section."""
        values = {'CAPTURE_WIDTH': 1280, 'CAPTURE_HEIGHT': 720}
        result = service.set_section('VideoSource', values)
        assert result.valid is True
        assert service.get_parameter('VideoSource', 'CAPTURE_WIDTH') == 1280
        assert service.get_parameter('VideoSource', 'CAPTURE_HEIGHT') == 720


class TestConfigServiceDiff:
    """Test diff/comparison methods."""

    @pytest.fixture
    def service(self):
        return ConfigService.get_instance()

    def test_get_diff_no_changes(self, service):
        """Same configs should have no diff."""
        config = {'Section': {'param': 'value'}}
        diffs = service.get_diff(config, config)
        assert len(diffs) == 0

    def test_get_diff_with_changes(self, service):
        """Different configs should show diff."""
        config1 = {'Section': {'param': 'value1'}}
        config2 = {'Section': {'param': 'value2'}}
        diffs = service.get_diff(config1, config2)
        assert len(diffs) == 1
        assert diffs[0].change_type == 'changed'

    def test_get_diff_with_additions(self, service):
        """New params should show as added."""
        config1 = {'Section': {}}
        config2 = {'Section': {'new_param': 'value'}}
        diffs = service.get_diff(config1, config2)
        assert len(diffs) == 1
        assert diffs[0].change_type == 'added'

    def test_get_diff_with_removals(self, service):
        """Removed params should show as removed."""
        config1 = {'Section': {'old_param': 'value'}}
        config2 = {'Section': {}}
        diffs = service.get_diff(config1, config2)
        assert len(diffs) == 1
        assert diffs[0].change_type == 'removed'

    def test_get_changed_from_default(self, service):
        """Should return differences from default."""
        diffs = service.get_changed_from_default()
        assert isinstance(diffs, list)


class TestConfigServiceImportExport:
    """Test import/export functionality."""

    @pytest.fixture
    def service(self):
        return ConfigService.get_instance()

    def test_export_config_all(self, service):
        """Should export full config."""
        exported = service.export_config()
        assert isinstance(exported, dict)

    def test_export_config_sections(self, service):
        """Should export specific sections."""
        exported = service.export_config(sections=['VideoSource', 'Streaming'])
        assert 'VideoSource' in exported or len(exported) == 0

    def test_import_config_merge(self, service):
        """Import with merge mode."""
        data = {'VideoSource': {'CAPTURE_WIDTH': 1920}}
        success, diffs = service.import_config(data, merge_mode='merge')
        assert success is True
        assert service.get_parameter('VideoSource', 'CAPTURE_WIDTH') == 1920

    def test_import_config_replace(self, service):
        """Import with replace mode."""
        original_config = copy.deepcopy(service.export_config())
        data = copy.deepcopy(original_config)
        data['VideoSource']['CAPTURE_WIDTH'] = 1920
        try:
            success, diffs = service.import_config(data, merge_mode='replace')
            assert success is True
        finally:
            service.import_config(original_config, merge_mode='replace')

    def test_import_config_replace_resolves_sparse_input_over_defaults(self, service):
        original_config = service._config
        original_raw = service._config_raw
        success, diffs = service.import_config(
            {'VideoSource': {'CAPTURE_WIDTH': 1920}},
            merge_mode='replace',
        )
        try:
            assert success is True
            assert diffs
            assert service.get_parameter('VideoSource', 'CAPTURE_WIDTH') == 1920
            assert service.get_config()['Safety'] == service.get_default()['Safety']
            assert set(service.get_default()).issubset(service.get_config())
        finally:
            service._config = original_config
            service._config_raw = original_raw

    def test_import_config_recursively_preserves_nested_siblings(self, service):
        original_config = service._config
        original_raw = service._config_raw
        original_schema = service._schema
        service._schema = copy.deepcopy(original_schema)
        service._schema['meta']['extension_sections'] = {
            'Extension': {
                'type': 'object',
                'properties': {},
                'additional_properties': True,
            },
        }
        service._config = {
            'Extension': {
                'Nested': {'keep': 1, 'change': 1},
                'sibling': True,
            }
        }
        service._config_raw = None
        try:
            success, _ = service.import_config(
                {'Extension': {'Nested': {'change': 2}}},
                merge_mode='merge',
            )
            assert success is True
            assert service._config == {
                'Extension': {
                    'Nested': {'keep': 1, 'change': 2},
                    'sibling': True,
                }
            }
        finally:
            service._schema = original_schema
            service._config = original_config
            service._config_raw = original_raw

    def test_import_rejects_undeclared_parameter_without_mutating_state(
        self,
        service,
    ):
        before = service.get_config()

        success, diffs = service.import_config(
            {'VideoSource': {'UNDECLARED_IMPORT_KEY': 1}},
            merge_mode='merge',
        )

        assert success is False
        assert diffs == []
        assert service.get_config() == before

    def test_restore_rejects_undeclared_parameter_without_mutating_state(
        self,
        tmp_path,
    ):
        (tmp_path / 'configs').mkdir()
        for filename in (
            'config_default.yaml',
            'config_schema.yaml',
            'config_retirements.yaml',
        ):
            shutil.copyfile(
                Path('configs') / filename,
                tmp_path / 'configs' / filename,
            )
        default_config = yaml.safe_load(
            (tmp_path / 'configs' / 'config_default.yaml').read_text(
                encoding='utf-8'
            )
        )
        config_path = tmp_path / 'configs' / 'config.yaml'
        config_path.write_text(
            yaml.safe_dump(default_config, sort_keys=False),
            encoding='utf-8',
        )
        service = ConfigService(project_root=tmp_path)
        backup_config = copy.deepcopy(default_config)
        backup_config['Streaming']['UNDECLARED_BACKUP_KEY'] = True
        backup_dir = tmp_path / 'configs' / 'backups'
        backup_dir.mkdir()
        backup_id = 'config_20260715_120000'
        (backup_dir / f'{backup_id}.yaml').write_text(
            yaml.safe_dump(backup_config, sort_keys=False),
            encoding='utf-8',
        )
        before_memory = service.get_config()
        before_disk = config_path.read_bytes()

        assert service.restore_backup(backup_id) is False
        assert service.get_config() == before_memory
        assert config_path.read_bytes() == before_disk


class TestConfigServiceUtility:
    """Test utility methods."""

    @pytest.fixture
    def service(self):
        return ConfigService.get_instance()

    def test_is_reboot_required(self, service):
        """Should check reboot requirement."""
        result = service.is_reboot_required('VideoSource', 'VIDEO_SOURCE_TYPE')
        assert isinstance(result, bool)

    def test_search_parameters(self, service):
        """Should search across parameters with pagination."""
        result = service.search_parameters('velocity')
        assert isinstance(result, dict)
        assert 'results' in result
        assert 'total' in result
        assert 'limit' in result
        assert 'offset' in result
        for item in result['results']:
            assert 'section' in item
            assert 'parameter' in item

    def test_search_parameters_empty_query(self, service):
        """Empty query should return all parameters."""
        result = service.search_parameters('')
        assert isinstance(result, dict)
        assert 'results' in result
        assert result['total'] > 0

    @pytest.mark.parametrize(
        'value',
        [
            'rtsp://user:password@camera.local/live',
            '//user:password@camera.local/live',
            'user:password@camera.local/live',
            'rtsp://user:password@[broken/live',
            'https://camera.local/live?access_token=do-not-return',
            'https://[broken/live?access_token=do-not-return',
            'https://[broken/live?sig=do-not-return',
            'https://[broken/live?auth=do-not-return',
            'https://[broken/live?policy=do-not-return',
            'https://[broken/live?key=do-not-return',
            'https://[broken/live?access%5Ftoken=do-not-return',
            'https://camera.local/live?sig=do-not-return',
            'https://camera.local/live?X-Amz-Signature=do-not-return',
            'https://camera.local/live?Key-Pair-Id=id&Signature=do-not-return',
            'https://camera.local/callback#access_token=do-not-return',
            'https://[broken/callback#sig=do-not-return',
        ],
    )
    def test_redact_value_catches_credentials_embedded_in_urls(self, service, value):
        assert service.redact_value(value, ['Streaming', 'HTTP_STREAM_URL']) == (
            '[REDACTED]'
        )

    def test_redact_value_recurses_through_nested_secret_keys(self, service):
        public = service.redact_value(
            {
                'safe': 1,
                'nested': {
                    'TURN_CREDENTIAL': 'do-not-return',
                },
            }
        )

        assert public == {
            'safe': 1,
            'nested': {'TURN_CREDENTIAL': '[REDACTED]'},
        }

    def test_search_parameters_redacts_current_and_default_values(self, service):
        original_schema = service._schema
        original_config = service._config
        original_default = service._default
        service._schema = {
            'sections': {
                'Secrets': {
                    'parameters': {
                        'API_TOKEN': {
                            'type': 'string',
                            'description': 'Credential',
                            'sensitive': True,
                        }
                    }
                }
            }
        }
        service._config = {'Secrets': {'API_TOKEN': 'current-secret'}}
        service._default = {'Secrets': {'API_TOKEN': 'default-secret'}}
        try:
            result = service.search_parameters('token')
        finally:
            service._schema = original_schema
            service._config = original_config
            service._default = original_default

        assert result['results'][0]['current_value'] == '[REDACTED]'
        assert result['results'][0]['default_value'] == '[REDACTED]'


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        result = ValidationResult(
            valid=True,
            status=ValidationStatus.VALID,
            errors=[],
            warnings=['test warning']
        )
        d = result.to_dict()
        assert d['valid'] is True
        assert d['status'] == 'valid'
        assert d['warnings'] == ['test warning']


class TestDiffEntry:
    """Test DiffEntry dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        entry = DiffEntry(
            path='Section.param',
            section='Section',
            parameter='param',
            old_value='old',
            new_value='new',
            change_type='changed'
        )
        d = entry.to_dict()
        assert d['path'] == 'Section.param'
        assert d['old_value'] == 'old'
        assert d['new_value'] == 'new'


class TestConfigBackup:
    """Test ConfigBackup dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        backup = ConfigBackup(
            id='config_20231225_120000',
            filename='config_20231225_120000.yaml',
            timestamp=1703505600.0,
            size=1024
        )
        d = backup.to_dict()
        assert d['id'] == 'config_20231225_120000'
        assert d['size'] == 1024


class TestReloadTier:
    """Test reload tier functionality (v5.3.0+)."""

    @pytest.fixture
    def service(self):
        return ConfigService.get_instance()

    def test_get_reload_tier_returns_valid_tier(self, service):
        """Should return a valid reload tier string."""
        valid_tiers = ['immediate', 'follower_restart', 'tracker_restart', 'system_restart']
        # Test with a known parameter
        tier = service.get_reload_tier('Tracker', 'DEFAULT_TRACKING_ALGORITHM')
        assert tier in valid_tiers

    def test_get_reload_tier_defaults_to_system_restart(self, service):
        """Unknown parameters should default to system_restart for safety."""
        tier = service.get_reload_tier('NonExistent', 'FAKE_PARAM')
        assert tier == 'system_restart'

    def test_get_reload_tier_unknown_section(self, service):
        """Unknown section should return system_restart."""
        tier = service.get_reload_tier('InvalidSection', 'InvalidParam')
        assert tier == 'system_restart'

    def test_get_reload_message_immediate(self, service):
        """Should return appropriate message for immediate tier."""
        message = service.get_reload_message('immediate')
        assert 'immediate' in message.lower() or 'applied' in message.lower()

    def test_get_reload_message_follower_restart(self, service):
        """Should return appropriate message for follower_restart tier."""
        message = service.get_reload_message('follower_restart')
        assert 'follower' in message.lower() or 'restart' in message.lower()

    def test_get_reload_message_tracker_restart(self, service):
        """Should return appropriate message for tracker_restart tier."""
        message = service.get_reload_message('tracker_restart')
        assert 'tracker' in message.lower() or 'restart' in message.lower()

    def test_get_reload_message_system_restart(self, service):
        """Should return appropriate message for system_restart tier."""
        message = service.get_reload_message('system_restart')
        assert 'system' in message.lower() or 'restart' in message.lower()

    def test_get_reload_message_unknown_tier(self, service):
        """Should handle unknown tier gracefully."""
        message = service.get_reload_message('unknown_tier')
        assert message is not None
        assert len(message) > 0

    def test_is_reboot_required_consistency(self, service):
        """is_reboot_required should be True only for system_restart tier."""
        # For a system_restart tier param
        tier = service.get_reload_tier('VideoSource', 'VIDEO_SOURCE_TYPE')
        is_reboot = service.is_reboot_required('VideoSource', 'VIDEO_SOURCE_TYPE')

        if tier == 'system_restart':
            assert is_reboot is True
        else:
            assert is_reboot is False

    def test_reload_tier_in_schema(self, service):
        """Parameters in schema should have reload_tier field."""
        schema = service.get_schema()
        # Schema structure: { 'sections': { 'SectionName': { 'parameters': {...} } } }
        sections = schema.get('sections', {})

        # Check that at least some parameters have reload_tier
        found_reload_tier = False
        valid_tiers = ['immediate', 'follower_restart', 'tracker_restart', 'system_restart']

        for section_name, section in sections.items():
            if isinstance(section, dict) and 'parameters' in section:
                for param_name, param_schema in section['parameters'].items():
                    if isinstance(param_schema, dict) and 'reload_tier' in param_schema:
                        found_reload_tier = True
                        # Validate the tier value
                        assert param_schema['reload_tier'] in valid_tiers, \
                            f"Invalid reload_tier '{param_schema['reload_tier']}' in {section_name}.{param_name}"

        assert found_reload_tier, "No reload_tier found in any schema parameter"


class TestRuntimeConfigStatus:
    """Process-start versus persisted configuration contract tests."""

    @pytest.fixture
    def service(self, tmp_path):
        configs = tmp_path / "configs"
        configs.mkdir()
        source_configs = Path(__file__).parent.parent / "configs"
        for filename in (
            "config_default.yaml",
            "config_schema.yaml",
            "config_retirements.yaml",
        ):
            shutil.copy2(source_configs / filename, configs / filename)
        return ConfigService(project_root=tmp_path)

    def test_reports_only_system_restart_changes_and_redacts_secrets(self, service):
        startup_timestamp = service._startup_snapshot_timestamp
        startup_policy = service.get_startup_system_restart_policy()
        secret_path = "/tmp/private-api-token-records.json"

        assert service.set_parameter(
            "Streaming",
            "API_BEARER_TOKEN_FILE",
            secret_path,
        ).valid
        assert service.set_parameter(
            "SmartTracker",
            "SMART_TRACKER_HUD_STYLE",
            "classic",
        ).valid
        assert service.save_config(backup=False)

        status = service.get_runtime_config_status()

        assert status["startup_snapshot_timestamp"] == startup_timestamp
        assert status["startup_snapshot_immutable"] is True
        assert status["system_restart_policy"] == startup_policy
        assert status["restart_required"] is True
        assert status["pending_change_count"] == 1
        assert status["pending_changes"] == [{
            "path": "Streaming.API_BEARER_TOKEN_FILE",
            "section": "Streaming",
            "parameter": "API_BEARER_TOKEN_FILE",
            "change_type": "changed",
            "reload_tier": "system_restart",
            "sensitive": True,
            "startup_value": "[REDACTED]",
            "persisted_value": "[REDACTED]",
        }]
        assert secret_path not in repr(status)

        service.reload()
        reloaded_status = service.get_runtime_config_status()
        assert reloaded_status["restart_required"] is True
        assert reloaded_status["startup_snapshot_timestamp"] == startup_timestamp

    def test_startup_snapshot_getter_is_defensive(self, service):
        snapshot = service.get_startup_effective_config()
        original = service.get_startup_effective_config()["Streaming"][
            "API_SYSTEM_RESTART_POLICY"
        ]

        snapshot["Streaming"]["API_SYSTEM_RESTART_POLICY"] = "lab_admin_browser"

        assert service.get_startup_effective_config()["Streaming"][
            "API_SYSTEM_RESTART_POLICY"
        ] == original

    def test_startup_status_uses_normalized_alias_and_retirement_state(self, tmp_path):
        configs = tmp_path / "configs"
        configs.mkdir()
        source_configs = Path(__file__).parent.parent / "configs"
        for filename in (
            "config_default.yaml",
            "config_schema.yaml",
            "config_retirements.yaml",
        ):
            shutil.copy2(source_configs / filename, configs / filename)

        with open(configs / "config_default.yaml", encoding="utf-8") as source:
            runtime_config = yaml.safe_load(source)
        runtime_config["Segmentation"]["DEFAULT_SEGMENTATION_ALGORITHM"] = (
            "yolov11n.pt"
        )
        runtime_config["GStreamer"]["GSTREAMER_CONTRAST"] = 1.0
        with open(configs / "config.yaml", "w", encoding="utf-8") as target:
            yaml.safe_dump(runtime_config, target, sort_keys=False)

        normalized_service = ConfigService(project_root=tmp_path)
        startup = normalized_service.get_startup_effective_config()
        status = normalized_service.get_runtime_config_status()

        assert startup["Segmentation"]["DEFAULT_SEGMENTATION_ALGORITHM"] == "disabled"
        assert "GSTREAMER_CONTRAST" not in startup["GStreamer"]
        assert status["restart_required"] is False
        assert status["pending_changes"] == []


class TestConfigSyncUtilities:
    """Tests for config sync helper utilities."""

    @pytest.fixture
    def service(self):
        return ConfigService.get_instance()

    def test_get_default_config_alias(self, service):
        """get_default_config should mirror get_default."""
        assert service.get_default_config() == service.get_default()

    def test_remove_parameter(self, service):
        """remove_parameter should delete a key from current config."""
        section = 'VideoSource'
        param = '_TEST_REMOVE_PARAMETER'
        service.set_parameter(section, param, 123, validate=False)
        assert service.get_parameter(section, param) == 123
        assert service.remove_parameter(section, param) is True
        assert service.get_parameter(section, param) is None

    def test_remove_registered_retirement_is_exact(self, service, monkeypatch):
        """Only an exact registry match may remove a config parameter."""
        section = 'VideoSource'
        param = '_TEST_REGISTERED_RETIREMENT'
        service.set_parameter(section, param, 'value', validate=False)
        monkeypatch.setattr(
            service,
            'get_registered_retirement',
            lambda candidate_section, candidate_param: (
                {'id': 'test-retirement'}
                if (candidate_section, candidate_param) == (section, param)
                else None
            ),
        )
        assert service.remove_registered_retirement(section, '_NOT_REGISTERED') is False
        assert service.get_parameter(section, param) == 'value'
        assert service.remove_registered_retirement(section, param) is True
        assert service.get_parameter(section, param) is None

    def test_retirement_registry_contains_only_inactive_exact_paths(self, service):
        registry = service.get_retirement_registry()
        assert registry['registry_version'] == 1
        assert len(registry['registry_digest']) == 64
        paths = {tuple(item['path']) for item in registry['retirements']}
        assert {
            ('BOUNDARY_MARGIN_PIXELS',),
            ('GStreamer', 'GSTREAMER_CONTRAST'),
            ('GStreamer', 'GSTREAMER_BRIGHTNESS'),
            ('GStreamer', 'GSTREAMER_SATURATION'),
            ('Tracking', 'APPEARANCE_CONFIDENCE_THRESHOLD'),
            ('_ARCHIVED_OBSOLETE',),
        }.issubset(paths)
        assert all(
            entry['replacement'] is None or isinstance(entry['replacement'], list)
            for entry in registry['retirements']
        )

    def test_refresh_defaults_snapshot(self, service, tmp_path):
        """refresh_defaults_snapshot should persist defaults snapshot metadata."""
        original_root = service._project_root
        try:
            service._project_root = tmp_path
            assert service.refresh_defaults_snapshot() is True
            meta = service.get_sync_meta()
            assert 'defaults_snapshot' in meta
            assert 'schema_version' in meta
            assert meta['defaults_snapshot_provenance'] == (
                'explicit_current_defaults_refresh'
            )
            assert len(meta['defaults_snapshot_source_digest']) == 64
        finally:
            service._project_root = original_root

    def test_mutation_guard_uses_an_untracked_runtime_lock(self, service, tmp_path):
        original_root = service._project_root
        try:
            service._project_root = tmp_path
            with service.mutation_guard():
                lock_path = tmp_path / 'configs' / 'config.lock'
                assert lock_path.is_file()
                assert lock_path.stat().st_size == (1 if os.name == 'nt' else 0)
        finally:
            service._project_root = original_root

    @pytest.mark.skipif(os.name == 'nt', reason='Windows symlink privileges vary')
    def test_mutation_guard_rejects_symlink_lock_path(self, service, tmp_path):
        original_root = service._project_root
        config_dir = tmp_path / 'configs'
        config_dir.mkdir()
        target = tmp_path / 'operator-owned.lock'
        target.write_bytes(b'preserve')
        (config_dir / 'config.lock').symlink_to(target)
        try:
            service._project_root = tmp_path
            with pytest.raises(ValueError, match='non-symlink'):
                with service.mutation_guard():
                    pass
            assert target.read_bytes() == b'preserve'
        finally:
            service._project_root = original_root

    @pytest.mark.skipif(os.name == 'nt', reason='Windows symlink privileges vary')
    def test_backup_creation_rejects_symlink_directory(self, service, tmp_path):
        original_root = service._project_root
        config_dir = tmp_path / 'configs'
        config_dir.mkdir()
        (config_dir / 'config.yaml').write_text('Example: true\n', encoding='utf-8')
        external_dir = tmp_path / 'external-backups'
        external_dir.mkdir()
        (config_dir / 'backups').symlink_to(external_dir, target_is_directory=True)
        try:
            service._project_root = tmp_path
            assert service.create_backup() is None
            assert list(external_dir.iterdir()) == []
        finally:
            service._project_root = original_root

    def test_initialize_defaults_snapshot_preserves_existing_baseline(
        self,
        service,
        tmp_path,
    ):
        original_root = service._project_root
        original_default = service._default
        original_schema = service._schema
        try:
            service._project_root = tmp_path
            service._default = {"Example": {"VALUE": 1}}
            service._schema = {"schema_version": "1.1.0", "sections": {}}
            assert service.initialize_defaults_snapshot() is True
            original_metadata = (
                tmp_path / 'configs' / 'config_sync_meta.json'
            ).read_bytes()

            service._default = {"Example": {"VALUE": 2}}
            assert service.initialize_defaults_snapshot() is True
            assert (
                tmp_path / 'configs' / 'config_sync_meta.json'
            ).read_bytes() == original_metadata
            assert service.get_sync_meta()["defaults_snapshot"] == {
                "Example": {"VALUE": 1}
            }
        finally:
            service._project_root = original_root
            service._default = original_default
            service._schema = original_schema


class TestRuntimeTierPublication:
    """Runtime generations must never absorb unrelated persisted tiers."""

    @staticmethod
    def _install_runtime_stubs(monkeypatch, state):
        monkeypatch.setattr(
            Parameters,
            "get_runtime_config_snapshot",
            staticmethod(lambda: copy.deepcopy(state["config"])),
        )
        monkeypatch.setattr(
            Parameters,
            "get_runtime_config_generation",
            staticmethod(lambda: state["generation"]),
        )

        def publish(config, *, source, strict_dependents):
            assert strict_dependents is True
            state["config"] = copy.deepcopy(config)
            state["generation"] += 1
            state["sources"].append(source)

        monkeypatch.setattr(
            Parameters,
            "publish_config_mapping",
            staticmethod(publish),
        )

    def test_selective_tiers_preserve_pending_generations(self, monkeypatch):
        service = ConfigService.get_instance()
        state = {
            "config": {
                "Test": {"IMMEDIATE": 1, "FOLLOWER": 1, "SYSTEM": 1}
            },
            "generation": 7,
            "sources": [],
        }
        self._install_runtime_stubs(monkeypatch, state)
        monkeypatch.setattr(
            service,
            "_schema",
            {
                "schema_version": "6.2.0",
                "sections": {
                    "Test": {
                        "parameters": {
                            "IMMEDIATE": {"reload_tier": "immediate"},
                            "FOLLOWER": {"reload_tier": "follower_restart"},
                            "SYSTEM": {"reload_tier": "system_restart"},
                        }
                    }
                }
            },
        )
        persisted = {
            "Test": {"IMMEDIATE": 2, "FOLLOWER": 2, "SYSTEM": 2}
        }
        monkeypatch.setattr(
            service,
            "_read_persisted_effective_config_locked",
            lambda: (copy.deepcopy(persisted), "runtime_config", "d" * 64),
        )

        immediate = service.apply_runtime_config_tiers(
            {"immediate"},
            source="unit_immediate",
        )

        assert state["config"] == {
            "Test": {"IMMEDIATE": 2, "FOLLOWER": 1, "SYSTEM": 1}
        }
        assert immediate["applied_paths"] == ["Test.IMMEDIATE"]
        assert immediate["pending_paths"] == ["Test.FOLLOWER", "Test.SYSTEM"]
        assert immediate["generation_before"] == 7
        assert immediate["generation_after"] == 8

        follower = service.apply_runtime_config_tiers(
            {"immediate", "follower_restart"},
            source="unit_follower",
        )

        assert state["config"] == {
            "Test": {"IMMEDIATE": 2, "FOLLOWER": 2, "SYSTEM": 1}
        }
        assert follower["applied_paths"] == ["Test.FOLLOWER"]
        assert follower["pending_paths"] == ["Test.SYSTEM"]
        assert state["sources"] == ["unit_immediate", "unit_follower"]

    def test_selective_tier_applies_presence_changes(self, monkeypatch):
        service = ConfigService.get_instance()
        state = {
            "config": {"Test": {"REMOVE": 1}},
            "generation": 3,
            "sources": [],
        }
        self._install_runtime_stubs(monkeypatch, state)
        monkeypatch.setattr(
            service,
            "_schema",
            {
                "schema_version": "6.2.0",
                "sections": {
                    "Test": {
                        "parameters": {
                            "ADD": {"reload_tier": "immediate"},
                            "REMOVE": {"reload_tier": "immediate"},
                        }
                    }
                }
            },
        )
        monkeypatch.setattr(
            service,
            "_read_persisted_effective_config_locked",
            lambda: ({"Test": {"ADD": 2}}, "runtime_config", "e" * 64),
        )

        result = service.apply_runtime_config_tiers(
            {"immediate"},
            source="unit_presence",
        )

        assert state["config"] == {"Test": {"ADD": 2}}
        assert result["applied_paths"] == ["Test.ADD", "Test.REMOVE"]


class TestExactRuntimeConfigMutation:
    """Exact-path safety mutations are durable, audited, and isolated."""

    @pytest.fixture
    def service(self, tmp_path):
        configs = tmp_path / "configs"
        configs.mkdir()
        source_configs = Path(__file__).parent.parent / "configs"
        for filename in (
            "config_default.yaml",
            "config_schema.yaml",
            "config_retirements.yaml",
        ):
            shutil.copy2(source_configs / filename, configs / filename)
        shutil.copy2(
            source_configs / "config_default.yaml",
            configs / "config.yaml",
        )
        return ConfigService(project_root=tmp_path)

    def test_root_scalar_reload_tier_comes_from_section_schema(self, service):
        assert service.get_reload_tier(
            "FOLLOWER_CIRCUIT_BREAKER",
            "_value",
        ) == "immediate"
        assert service.get_reload_tier(
            "FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES",
            "_value",
        ) == "system_restart"

    def test_persist_and_apply_exact_root_path_only(
        self,
        service,
        monkeypatch,
    ):
        runtime = service.get_config()
        state = {
            "config": copy.deepcopy(runtime),
            "generation": 11,
            "sources": [],
        }
        TestRuntimeTierPublication._install_runtime_stubs(monkeypatch, state)

        assert service.set_parameter(
            "SmartTracker",
            "SMART_TRACKER_HUD_STYLE",
            "classic",
        ).valid
        assert service.save_config(backup=False)

        result = service.persist_and_apply_runtime_config_path(
            ["FOLLOWER_CIRCUIT_BREAKER"],
            False,
            source="unit_circuit_breaker_set",
        )

        assert result["changed"] is True
        assert result["applied"] is True
        assert result["reload_tier"] == "immediate"
        assert result["backup_id"]
        assert state["config"]["FOLLOWER_CIRCUIT_BREAKER"] is False
        assert state["config"]["SmartTracker"][
            "SMART_TRACKER_HUD_STYLE"
        ] == "military"
        assert state["sources"] == ["unit_circuit_breaker_set"]
        assert service.get_path_value(["FOLLOWER_CIRCUIT_BREAKER"]) is False
        assert service.get_parameter(
            "SmartTracker",
            "SMART_TRACKER_HUD_STYLE",
        ) == "classic"
        assert service.get_audit_log(limit=1)["entries"][0][
            "action"
        ] == "runtime_config_update"

    def test_exact_runtime_mutation_refuses_system_restart_path(
        self,
        service,
        monkeypatch,
    ):
        state = {
            "config": service.get_config(),
            "generation": 4,
            "sources": [],
        }
        TestRuntimeTierPublication._install_runtime_stubs(monkeypatch, state)

        with pytest.raises(ValueError, match="system_restart"):
            service.persist_and_apply_runtime_config_path(
                ["FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES"],
                True,
                source="unit_forbidden_bypass",
            )

        assert service.get_path_value(
            ["FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES"]
        ) is False
        assert state["sources"] == []

    def test_exact_runtime_mutation_reconciles_stale_runtime_value(
        self,
        service,
        monkeypatch,
    ):
        runtime = service.get_config()
        runtime["FOLLOWER_CIRCUIT_BREAKER"] = False
        state = {
            "config": runtime,
            "generation": 8,
            "sources": [],
        }
        TestRuntimeTierPublication._install_runtime_stubs(monkeypatch, state)

        result = service.persist_and_apply_runtime_config_path(
            ["FOLLOWER_CIRCUIT_BREAKER"],
            True,
            source="unit_circuit_breaker_reconcile",
        )

        assert result["changed"] is False
        assert result["applied"] is True
        assert result["backup_id"] is None
        assert state["config"]["FOLLOWER_CIRCUIT_BREAKER"] is True
        assert state["sources"] == ["unit_circuit_breaker_reconcile"]
        assert service.get_audit_log(limit=1)["entries"][0][
            "action"
        ] == "runtime_config_reconcile"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
