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

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from classes.config_service import (
    ConfigService,
    ValidationResult,
    ValidationStatus,
    DiffEntry,
    ConfigBackup
)


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
        result = service.validate_value('Streaming', 'ENABLE_HTTP_STREAM', True)
        assert result.valid is True

    def test_validate_string_valid(self, service):
        """Valid string should pass."""
        result = service.validate_value('VideoSource', 'VIDEO_FILE_PATH', 'test.mp4')
        assert result.valid is True

    def test_validate_unknown_parameter(self, service):
        """Unknown parameter should warn but pass."""
        result = service.validate_value('NonExistent', 'PARAM', 'value')
        assert result.valid is True  # No schema = allow
        assert len(result.warnings) > 0

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

    def test_strict_mapping_requires_complete_safety_limits(self, service):
        candidate = copy.deepcopy(service.get_default())
        candidate['Safety']['GlobalLimits'].pop('MIN_ALTITUDE')

        result = service.validate_config_mapping(candidate, require_safety=True)

        assert result.valid is False
        assert any('MIN_ALTITUDE' in error for error in result.errors)


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
        result = service.set_parameter('VideoSource', 'CAPTURE_WIDTH', -100, validate=False)
        assert result.valid is True

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
            service._config = original_config
            service._config_raw = original_raw


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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
