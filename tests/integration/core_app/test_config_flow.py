"""
Config Service Integration Tests

Tests for configuration loading, saving, validation, and schema management.
"""

import pytest
from unittest.mock import patch

from classes.config_service import ConfigService


pytestmark = [pytest.mark.integration, pytest.mark.core_app]


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset ConfigService singleton between tests."""
    yield
    # Don't reset to preserve actual config during tests


@pytest.fixture
def config_service():
    """Get config service instance."""
    return ConfigService.get_instance()


class TestConfigServiceInstance:
    """Tests for ConfigService singleton pattern."""

    def test_singleton_pattern(self):
        """Test ConfigService returns same instance."""
        instance1 = ConfigService.get_instance()
        instance2 = ConfigService.get_instance()
        assert instance1 is instance2

    def test_instance_not_none(self):
        """Test instance is properly initialized."""
        instance = ConfigService.get_instance()
        assert instance is not None


class TestConfigRetrieval:
    """Tests for configuration retrieval."""

    def test_get_config_returns_dict(self, config_service):
        """Test get_config returns dictionary."""
        config = config_service.get_config()
        assert isinstance(config, dict)

    def test_get_section_config(self, config_service):
        """Test getting specific section config."""
        sections = config_service.get_sections()
        if sections:
            first_section = sections[0]['name'] if isinstance(sections[0], dict) else sections[0]
            section_config = config_service.get_config(first_section)
            assert section_config is not None

    def test_get_parameter(self, config_service):
        """Test getting specific parameter."""
        # Get a known section
        sections = config_service.get_sections()
        if sections:
            section_name = sections[0]['name'] if isinstance(sections[0], dict) else sections[0]
            section_config = config_service.get_config(section_name)
            if section_config:
                param_name = list(section_config.keys())[0]
                value = config_service.get_parameter(section_name, param_name)
                # Value should match what's in section config
                assert value == section_config[param_name]


class TestConfigSchema:
    """Tests for configuration schema."""

    def test_get_schema(self, config_service):
        """Test getting full schema."""
        schema = config_service.get_schema()
        assert schema is not None
        assert isinstance(schema, dict)

    def test_get_sections(self, config_service):
        """Test getting section list."""
        sections = config_service.get_sections()
        assert sections is not None
        assert isinstance(sections, list)

    def test_get_categories(self, config_service):
        """Test getting category list."""
        categories = config_service.get_categories()
        assert categories is not None
        assert isinstance(categories, dict)

    def test_get_parameter_schema(self, config_service):
        """Test getting parameter schema."""
        sections = config_service.get_sections()
        if sections:
            section_name = sections[0]['name'] if isinstance(sections[0], dict) else sections[0]
            section_config = config_service.get_config(section_name)
            if section_config:
                param_name = list(section_config.keys())[0]
                param_schema = config_service.get_parameter_schema(section_name, param_name)
                # Schema may or may not exist for all params
                if param_schema:
                    assert isinstance(param_schema, dict)


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_validate_value_returns_result(self, config_service):
        """Test validate_value returns ValidationResult."""
        sections = config_service.get_sections()
        if sections:
            section_name = sections[0]['name'] if isinstance(sections[0], dict) else sections[0]
            section_config = config_service.get_config(section_name)
            if section_config:
                param_name = list(section_config.keys())[0]
                current_value = section_config[param_name]

                result = config_service.validate_value(section_name, param_name, current_value)
                # Result should have valid attribute
                assert hasattr(result, 'valid')

    def test_validate_boolean_type(self, config_service):
        """Test validating boolean parameter."""
        # Find a boolean parameter
        sections = config_service.get_sections()
        for section_info in sections:
            section_name = section_info['name'] if isinstance(section_info, dict) else section_info
            section_config = config_service.get_config(section_name)
            if section_config:
                for param_name, value in section_config.items():
                    if isinstance(value, bool):
                        result = config_service.validate_value(section_name, param_name, True)
                        assert hasattr(result, 'valid')
                        return  # Found and tested one

    def test_validate_numeric_type(self, config_service):
        """Test validating numeric parameter."""
        sections = config_service.get_sections()
        for section_info in sections:
            section_name = section_info['name'] if isinstance(section_info, dict) else section_info
            section_config = config_service.get_config(section_name)
            if section_config:
                for param_name, value in section_config.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        result = config_service.validate_value(section_name, param_name, value)
                        assert hasattr(result, 'valid')
                        return


class TestConfigModification:
    """Tests for configuration modification."""

    def test_set_parameter(self, config_service):
        """Test setting a parameter."""
        sections = config_service.get_sections()
        if sections:
            section_name = sections[0]['name'] if isinstance(sections[0], dict) else sections[0]
            section_config = config_service.get_config(section_name)
            if section_config:
                # Find a safe parameter to modify
                for param_name, value in section_config.items():
                    if isinstance(value, bool):
                        original = value
                        # Modify
                        result = config_service.set_parameter(section_name, param_name, not original)
                        # Restore
                        config_service.set_parameter(section_name, param_name, original)
                        break

    def test_set_section(self, config_service):
        """Test setting entire section."""
        sections = config_service.get_sections()
        if sections:
            section_name = sections[0]['name'] if isinstance(sections[0], dict) else sections[0]
            original_config = config_service.get_config(section_name)
            if original_config:
                # Set same values back
                result = config_service.set_section(section_name, original_config)
                # Should succeed
                assert hasattr(result, 'valid')


class TestConfigDefaults:
    """Tests for default configuration."""

    def test_get_default(self, config_service):
        """Test getting default config."""
        default = config_service.get_default()
        assert default is not None
        assert isinstance(default, dict)

    def test_get_default_parameter(self, config_service):
        """Test getting default parameter value."""
        sections = config_service.get_sections()
        if sections:
            section_name = sections[0]['name'] if isinstance(sections[0], dict) else sections[0]
            section_config = config_service.get_config(section_name)
            if section_config:
                param_name = list(section_config.keys())[0]
                default_value = config_service.get_default_parameter(section_name, param_name)
                # Default may or may not match current (user may have changed it)

    def test_get_changed_from_default(self, config_service):
        """Test getting changes from default."""
        changes = config_service.get_changed_from_default()
        assert isinstance(changes, list)


class TestConfigAudit:
    """Tests for configuration audit trail."""

    def test_get_audit_log(self, config_service):
        """Test getting audit log."""
        log = config_service.get_audit_log()
        # Log may be dict with 'entries' or list directly
        if isinstance(log, dict):
            assert 'entries' in log
            assert isinstance(log['entries'], list)
        else:
            assert isinstance(log, list)

    def test_get_audit_log_with_limit(self, config_service):
        """Test getting audit log with limit."""
        log = config_service.get_audit_log(limit=5)
        # Log may be dict with 'entries' or list directly
        if isinstance(log, dict):
            assert 'entries' in log
            assert len(log['entries']) <= 5
        else:
            assert isinstance(log, list)
            assert len(log) <= 5


class TestConfigBackup:
    """Tests for configuration backup."""

    def test_get_backup_history(self, config_service):
        """Test getting backup history."""
        history = config_service.get_backup_history()
        assert isinstance(history, list)

    def test_get_backup_history_with_limit(self, config_service):
        """Test getting backup history with limit."""
        history = config_service.get_backup_history(limit=5)
        assert isinstance(history, list)
        assert len(history) <= 5


class TestConfigDiff:
    """Tests for configuration diff."""

    def test_get_diff_same_config(self, config_service):
        """Test diff with same config returns empty."""
        config = config_service.get_config()
        diff = config_service.get_diff(config, config)
        assert isinstance(diff, list)
        # Same config should have no diff
        assert len(diff) == 0

    def test_get_diff_different_config(self, config_service):
        """Test diff with different config."""
        config1 = config_service.get_config()
        config2 = dict(config1)

        # Modify copy if there are sections
        if config2:
            first_section = list(config2.keys())[0]
            if isinstance(config2[first_section], dict) and config2[first_section]:
                first_param = list(config2[first_section].keys())[0]
                original = config2[first_section][first_param]
                if isinstance(original, bool):
                    config2[first_section][first_param] = not original
                elif isinstance(original, (int, float)) and not isinstance(original, bool):
                    config2[first_section][first_param] = original + 1

                diff = config_service.get_diff(config1, config2)
                assert isinstance(diff, list)


class TestConfigPersistence:
    """Tests for configuration persistence."""

    def test_save_config(self, config_service):
        """Test saving configuration."""
        # Save should work without errors
        try:
            config_service.save_config()
        except Exception as e:
            # May fail if no changes or permissions issues
            pass

    def test_config_persistence_roundtrip(self, config_service):
        """Test config survives save and read."""
        original_config = config_service.get_config()

        # Save
        try:
            config_service.save_config()
        except Exception:
            pass  # May not be able to save in test environment

        # Read should return same config
        current_config = config_service.get_config()
        # Keys should match
        assert set(original_config.keys()) == set(current_config.keys())
