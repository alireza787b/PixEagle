"""
Tests for ConfigService
========================

Comprehensive test suite for the ConfigService class.
Uses pytest for testing.

Run with: pytest tests/test_config_service.py -v
"""

import os
import sys
import pytest
import tempfile
import shutil
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


class TestConfigServiceValidation:
    """Test validation methods."""

    @pytest.fixture
    def service(self):
        return ConfigService.get_instance()

    def test_validate_integer_valid(self, service):
        """Valid integer should pass validation."""
        result = service.validate_value('VideoSource', 'CAPTURE_WIDTH', 640)
        assert result.valid is True

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
        original_config = service.export_config()
        data = {'VideoSource': {'CAPTURE_WIDTH': 1920}}
        success, diffs = service.import_config(data, merge_mode='replace')
        assert success is True
        # Restore original for other tests
        service.import_config(original_config, merge_mode='replace')


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

    def test_archive_and_remove_parameter(self, service):
        """archive_and_remove_parameter should move key to archive and remove active key."""
        section = 'VideoSource'
        param = '_TEST_ARCHIVE_PARAMETER'
        service.set_parameter(section, param, 'value', validate=False)
        assert service.archive_and_remove_parameter(section, param) is True
        assert service.get_parameter(section, param) is None
        archived = service.get_parameter(service.SYNC_ARCHIVE_SECTION, f'{section}.{param}')
        assert isinstance(archived, dict)
        assert archived.get('value') == 'value'

    def test_refresh_defaults_snapshot(self, service, tmp_path):
        """refresh_defaults_snapshot should persist defaults snapshot metadata."""
        original_root = service._project_root
        try:
            service._project_root = tmp_path
            assert service.refresh_defaults_snapshot() is True
            meta = service.get_sync_meta()
            assert 'defaults_snapshot' in meta
            assert 'schema_version' in meta
        finally:
            service._project_root = original_root


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
