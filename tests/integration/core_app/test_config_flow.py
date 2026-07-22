"""
Config Service Integration Tests

Tests for configuration loading, saving, validation, and schema management.
"""

import copy
import hashlib
import json
import os

import pytest
import shutil
import yaml
from pathlib import Path

from classes.config_service import ConfigService


pytestmark = [pytest.mark.integration, pytest.mark.core_app]


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset ConfigService singleton between tests."""
    yield
    ConfigService._instance = None


@pytest.fixture
def config_service(tmp_path):
    """Get an isolated config service instance backed by a temporary project root."""
    project_root = tmp_path / "project"
    config_dir = project_root / "configs"
    config_dir.mkdir(parents=True)

    repo_root = Path(__file__).resolve().parents[3]
    shutil.copy2(repo_root / "configs" / "config_default.yaml", config_dir / "config_default.yaml")
    shutil.copy2(repo_root / "configs" / "config_schema.yaml", config_dir / "config_schema.yaml")
    shutil.copy2(repo_root / "configs" / "config_retirements.yaml", config_dir / "config_retirements.yaml")

    return ConfigService(project_root=project_root)


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

    def test_startup_filters_nested_registered_retirements(self, tmp_path):
        """An upgraded operator config remains loadable before migration is saved."""
        project_root = tmp_path / "nested-retirement-project"
        config_dir = project_root / "configs"
        config_dir.mkdir(parents=True)
        repo_root = Path(__file__).resolve().parents[3]
        for name in (
            "config_default.yaml",
            "config_schema.yaml",
            "config_retirements.yaml",
        ):
            shutil.copy2(repo_root / "configs" / name, config_dir / name)

        operator_config = yaml.safe_load(
            (config_dir / "config_default.yaml").read_text(encoding="utf-8")
        )
        operator_config["DLIB_Tracker"]["appearance"][
            "reference_update_interval"
        ] = 30
        operator_config["DLIB_Tracker"]["adaptive"] = {"enable": True}
        (config_dir / "config.yaml").write_text(
            yaml.safe_dump(operator_config, sort_keys=False),
            encoding="utf-8",
        )

        service = ConfigService(project_root=project_root)

        runtime_dlib = service.get_config("DLIB_Tracker")
        assert "adaptive" not in runtime_dlib
        assert "reference_update_interval" not in runtime_dlib["appearance"]
        assert "adaptive" in service._config_raw["DLIB_Tracker"]
        assert (
            "reference_update_interval"
            in service._config_raw["DLIB_Tracker"]["appearance"]
        )


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

    def test_retirement_registry_rejects_duplicate_paths(self, config_service):
        registry_path = config_service._project_root / "configs" / "config_retirements.yaml"
        registry_path.write_text(
            """
registry_version: 1
retirements:
  - id: first
    path: [GStreamer, OLD_KEY]
    action: remove
    retired_in_schema_version: 1.1.0
    reason: First
    replacement: null
  - id: second
    path: [GStreamer, OLD_KEY]
    action: remove
    retired_in_schema_version: 1.1.0
    reason: Duplicate
    replacement: null
""",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Duplicate config retirement path"):
            config_service.get_retirement_registry()

    def test_retirement_registry_rejects_active_paths(self, config_service):
        registry_path = config_service._project_root / "configs" / "config_retirements.yaml"
        registry_path.write_text(
            """
registry_version: 1
retirements:
  - id: active-default
    path: [VideoSource, DEFAULT_FPS]
    action: remove
    retired_in_schema_version: 1.1.0
    reason: Must fail closed
    replacement: null
""",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="still active in defaults/schema"):
            config_service.get_retirement_registry()

    def test_retirement_registry_rejects_incomplete_entries(self, config_service):
        registry_path = config_service._project_root / "configs" / "config_retirements.yaml"
        registry_path.write_text(
            """
registry_version: 1
retirements:
  - id: incomplete
    path: [GStreamer, OLD_KEY]
    action: remove
    retired_in_schema_version: 1.1.0
    reason: Missing replacement key
""",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="missing replacement"):
            config_service.get_retirement_registry()

    def test_retirement_registry_rejects_future_schema_versions(self, config_service):
        registry_path = config_service._project_root / "configs" / "config_retirements.yaml"
        registry_path.write_text(
            """
registry_version: 1
retirements:
  - id: future
    path: [GStreamer, OLD_KEY]
    action: remove
    retired_in_schema_version: 99.0.0
    reason: Must not activate early
    replacement: null
""",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="targets future schema"):
            config_service.get_retirement_registry()

    def test_nested_retirement_is_validated_and_removed_exactly(self, config_service):
        registry_path = config_service._project_root / "configs" / "config_retirements.yaml"
        registry_path.write_text(
            """
registry_version: 1
retirements:
  - id: retired-nested-setting
    path: [DLIB_Tracker, appearance, reference_update_interval]
    action: remove
    retired_in_schema_version: 1.6.0
    reason: No runtime consumer remains
    replacement: null
""",
            encoding="utf-8",
        )
        config_service._config["DLIB_Tracker"]["appearance"][
            "reference_update_interval"
        ] = 30
        config_service._config_raw = copy.deepcopy(config_service._config)

        retirement = config_service.get_registered_retirement(
            ["DLIB_Tracker", "appearance", "reference_update_interval"]
        )
        assert retirement is not None
        assert config_service.remove_registered_retirement(retirement["path"]) is True
        assert config_service.path_exists(retirement["path"]) is False
        assert config_service.get_path_value(
            ["DLIB_Tracker", "appearance", "use_adaptive_learning"]
        ) is True
        assert (
            "reference_update_interval"
            not in config_service._config_raw["DLIB_Tracker"]["appearance"]
        )

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
        assert config_service.save_config() is True
        assert (config_service._project_root / "configs" / "config.yaml").exists()

    def test_config_persistence_roundtrip(self, config_service):
        """Test config survives save and read."""
        original_config = config_service.get_config()

        assert config_service.save_config() is True
        config_service.reload()

        # Read should return same config
        current_config = config_service.get_config()
        # Keys should match
        assert set(original_config.keys()) == set(current_config.keys())

    def test_config_and_backups_are_owner_only_and_collision_safe(self, config_service):
        assert config_service.save_config() is True
        config_path = config_service._project_root / "configs" / "config.yaml"
        assert config_path.stat().st_mode & 0o777 == 0o600

        first_backup = Path(config_service.create_backup())
        second_backup = Path(config_service.create_backup())

        assert first_backup != second_backup
        assert first_backup.stat().st_mode & 0o777 == 0o600
        assert second_backup.stat().st_mode & 0o777 == 0o600

    def test_persistence_snapshot_restores_exact_managed_backup_inventory(
        self,
        config_service,
    ):
        assert config_service.save_config(backup=False) is True
        original_backup = Path(config_service.create_backup())
        before = {original_backup.name: original_backup.read_bytes()}
        snapshot = config_service.capture_persistence_snapshot()

        original_backup.unlink()
        transient_backup = Path(config_service.create_backup())
        assert transient_backup.name not in before

        config_service.restore_persistence_snapshot(snapshot)

        backup_dir = config_service._project_root / 'configs' / 'backups'
        after = {
            path.name: path.read_bytes()
            for path in backup_dir.iterdir()
            if path.is_file()
        }
        assert after == before

    def test_conditional_rollback_preserves_external_runtime_edit(self, config_service):
        assert config_service.save_config(backup=False) is True
        snapshot = config_service.capture_persistence_snapshot()
        config_service.set_parameter(
            "VideoSource",
            "DEFAULT_FPS",
            19,
            validate=False,
        )
        assert config_service.save_config(backup=False) is True
        owned_digest = config_service.get_persistence_state_digests()["runtime_config"]
        config_path = config_service._project_root / "configs" / "config.yaml"
        external_bytes = config_path.read_bytes() + b"\n# external edit after write\n"
        config_path.write_bytes(external_bytes)

        with pytest.raises(RuntimeError, match="externally changed"):
            config_service.restore_persistence_snapshot(
                snapshot,
                expected_current_state={"runtime_config": owned_digest},
            )

        assert config_path.read_bytes() == external_bytes

    def test_conditional_rollback_skips_unowned_runtime_config(self, config_service):
        assert config_service.save_config(backup=False) is True
        snapshot = config_service.capture_persistence_snapshot()
        config_path = config_service._project_root / "configs" / "config.yaml"
        external_bytes = config_path.read_bytes() + b"\n# unowned external edit\n"
        config_path.write_bytes(external_bytes)

        config_service.restore_persistence_snapshot(
            snapshot,
            expected_current_state={},
        )

        assert config_path.read_bytes() == external_bytes

    def test_legacy_backup_identifier_remains_restorable(self, config_service):
        assert config_service.save_config(backup=False) is True
        expected_fps = config_service.get_parameter('VideoSource', 'DEFAULT_FPS')
        backup_dir = config_service._project_root / 'configs' / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        legacy_backup = backup_dir / 'config_20200101_010203.yaml'
        shutil.copyfile(
            config_service._project_root / 'configs' / 'config.yaml',
            legacy_backup,
        )
        config_service._restrict_path_permissions(legacy_backup)
        config_service.set_parameter(
            'VideoSource',
            'DEFAULT_FPS',
            expected_fps + 1,
            validate=False,
        )
        assert config_service.save_config(backup=False) is True

        assert config_service.restore_backup('config_20200101_010203') is True
        assert config_service.get_parameter('VideoSource', 'DEFAULT_FPS') == expected_fps

    def test_required_backup_failure_prevents_config_replacement(
        self,
        config_service,
        monkeypatch,
    ):
        assert config_service.save_config() is True
        config_path = config_service._project_root / "configs" / "config.yaml"
        before = config_path.read_bytes()
        config_service.set_parameter("VideoSource", "DEFAULT_FPS", 19, validate=False)
        monkeypatch.setattr(config_service, "_create_backup", lambda **kwargs: None)

        assert config_service.save_config(backup=True) is False
        assert config_path.read_bytes() == before

    def test_malformed_runtime_reload_preserves_last_known_good_state(
        self,
        config_service,
    ):
        assert config_service.save_config() is True
        before = copy.deepcopy(config_service.get_config())
        config_path = config_service._project_root / "configs" / "config.yaml"
        config_path.write_text("Broken: [unterminated\n", encoding="utf-8")

        with pytest.raises(RuntimeError, match="load configuration safely"):
            config_service.reload()

        assert config_service.get_config() == before

    def test_undeclared_runtime_reload_preserves_last_known_good_state(
        self,
        config_service,
    ):
        assert config_service.save_config() is True
        before = copy.deepcopy(config_service.get_config())
        invalid = json.loads(json.dumps(before))
        invalid['VideoSource']['UNDECLARED_RELOAD_KEY'] = True
        config_path = config_service._project_root / 'configs' / 'config.yaml'
        config_path.write_text(
            yaml.safe_dump(invalid, sort_keys=False),
            encoding='utf-8',
        )

        with pytest.raises(RuntimeError, match='UNDECLARED_RELOAD_KEY'):
            config_service.reload()

        assert config_service.get_config() == before

    def test_save_rejects_undeclared_in_memory_parameter(
        self,
        config_service,
    ):
        assert config_service.save_config() is True
        config_path = config_service._project_root / 'configs' / 'config.yaml'
        before_disk = config_path.read_bytes()
        config_service.set_parameter(
            'VideoSource',
            'UNDECLARED_SAVE_KEY',
            True,
            validate=False,
        )

        assert config_service.save_config() is False
        assert config_path.read_bytes() == before_disk

    @pytest.mark.skipif(os.name == 'nt', reason='Windows symlink privileges vary')
    def test_runtime_config_symlink_is_rejected_before_read(
        self,
        config_service,
        tmp_path,
    ):
        config_path = config_service._project_root / 'configs' / 'config.yaml'
        target = tmp_path / 'operator-owned.yaml'
        target.write_text('External: true\n', encoding='utf-8')
        config_path.symlink_to(target)

        with pytest.raises(RuntimeError, match='non-symlink'):
            config_service.reload()

    @pytest.mark.skipif(os.name == 'nt', reason='Windows symlink privileges vary')
    def test_sync_metadata_symlink_is_rejected_before_read(
        self,
        config_service,
        tmp_path,
    ):
        meta_path = (
            config_service._project_root / 'configs' / 'config_sync_meta.json'
        )
        target = tmp_path / 'operator-owned.json'
        target.write_text('{}', encoding='utf-8')
        meta_path.symlink_to(target)

        with pytest.raises(RuntimeError, match='symlink'):
            config_service.get_sync_meta()

    def test_round_trip_save_removes_deleted_raw_yaml_keys(self, config_service):
        assert config_service.save_config() is True
        config_service.reload()
        config_service._config_raw = copy.deepcopy(config_service._config_raw)
        config_service._config_raw["VideoSource"]["_TEST_STALE_RAW_KEY"] = 1
        assert config_service.save_config() is True
        config_service.reload()

        assert config_service.get_parameter(
            "VideoSource",
            "_TEST_STALE_RAW_KEY",
        ) is None

    def test_compare_and_swap_rejects_external_runtime_edit(self, config_service):
        assert config_service.save_config() is True
        config_path = config_service._project_root / "configs" / "config.yaml"
        expected_digest = config_service.get_source_state_digests()["runtime_config"]
        config_service.set_parameter(
            "VideoSource",
            "DEFAULT_FPS",
            19,
            validate=False,
        )
        external_bytes = config_path.read_bytes() + b"\n# external edit\n"
        config_path.write_bytes(external_bytes)

        assert config_service.save_config(
            expected_config_digest=expected_digest,
        ) is False
        assert config_path.read_bytes() == external_bytes

    def test_final_replace_cas_rechecks_after_backup_and_returns_write_receipt(
        self,
        config_service,
        monkeypatch,
    ):
        assert config_service.save_config(backup=False) is True
        config_path = config_service._project_root / "configs" / "config.yaml"
        expected_digest = config_service.get_source_state_digests()["runtime_config"]
        original_create_backup = config_service._create_backup
        external_bytes = config_path.read_bytes() + b"\n# edit during backup window\n"

        def create_backup_then_edit(**kwargs):
            result = original_create_backup(**kwargs)
            config_path.write_bytes(external_bytes)
            return result

        monkeypatch.setattr(
            config_service,
            "_create_backup",
            create_backup_then_edit,
        )
        config_service.set_parameter(
            "VideoSource",
            "DEFAULT_FPS",
            19,
            validate=False,
        )
        failed_receipt = {}

        assert config_service.save_config(
            backup=True,
            expected_config_digest=expected_digest,
            write_receipt=failed_receipt,
        ) is False
        assert config_path.read_bytes() == external_bytes
        assert "runtime_config" not in failed_receipt

        monkeypatch.setattr(
            config_service,
            "_create_backup",
            original_create_backup,
        )
        config_service.reload()
        successful_receipt = {}
        current_digest = config_service.get_source_state_digests()["runtime_config"]
        assert config_service.save_config(
            backup=False,
            expected_config_digest=current_digest,
            write_receipt=successful_receipt,
        ) is True
        assert successful_receipt["runtime_config"] == (
            config_service.get_source_state_digests()["runtime_config"]
        )

    def test_post_replace_failure_keeps_receipt_for_conditional_rollback(
        self,
        config_service,
        monkeypatch,
    ):
        assert config_service.save_config(backup=False) is True
        config_path = config_service._project_root / "configs" / "config.yaml"
        original_bytes = config_path.read_bytes()
        source_digest = config_service.get_source_state_digests()["runtime_config"]
        snapshot = config_service.capture_persistence_snapshot()
        original_restrict = config_service._restrict_path_permissions

        config_service.set_parameter(
            "VideoSource",
            "DEFAULT_FPS",
            19,
            validate=False,
        )

        def fail_after_replace(path, *, directory=False):
            if Path(path) == config_path:
                raise PermissionError("injected final permission failure")
            return original_restrict(path, directory=directory)

        monkeypatch.setattr(
            config_service,
            "_restrict_path_permissions",
            fail_after_replace,
        )
        write_receipt = {}

        assert config_service.save_config(
            backup=False,
            expected_config_digest=source_digest,
            write_receipt=write_receipt,
        ) is False
        replaced_bytes = config_path.read_bytes()
        assert replaced_bytes != original_bytes
        assert write_receipt["runtime_config"] == hashlib.sha256(
            replaced_bytes
        ).hexdigest()

        monkeypatch.setattr(
            config_service,
            "_restrict_path_permissions",
            original_restrict,
        )
        config_service.restore_persistence_snapshot(
            snapshot,
            expected_current_state=write_receipt,
        )
        assert config_path.read_bytes() == original_bytes

    def test_corrupt_sync_metadata_is_not_overwritten(self, config_service):
        meta_path = config_service._project_root / "configs" / "config_sync_meta.json"
        meta_path.write_text("{broken", encoding="utf-8")
        before = meta_path.read_bytes()

        with pytest.raises(RuntimeError, match="sync metadata safely"):
            config_service.initialize_defaults_snapshot()

        assert meta_path.read_bytes() == before

    def test_staged_baseline_records_provenance_and_preserves_existing(
        self,
        config_service,
    ):
        first = {"OldDefaults": {"VALUE": 1}}
        assert config_service.initialize_defaults_snapshot_from(
            first,
            provenance="pre_update_staged_defaults",
            source_digest="a" * 64,
        ) is True
        assert config_service.initialize_defaults_snapshot_from(
            {"NewDefaults": {"VALUE": 2}},
            provenance="pre_update_staged_defaults",
            source_digest="b" * 64,
        ) is True

        meta_path = config_service._project_root / "configs" / "config_sync_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["defaults_snapshot"] == first
        assert meta["defaults_snapshot_provenance"] == "pre_update_staged_defaults"
        assert meta["defaults_snapshot_source_digest"] == "a" * 64
        assert meta_path.stat().st_mode & 0o777 == 0o600

    def test_audit_values_are_redacted_and_owner_only(self, config_service):
        config_service.log_audit_entry(
            action="update",
            section="Streaming",
            parameter="TURN_CREDENTIAL",
            old_value="old-secret",
            new_value="new-secret",
            source="test",
        )

        audit_path = config_service._project_root / "configs" / "audit_log.json"
        payload = audit_path.read_text(encoding="utf-8")
        assert "old-secret" not in payload
        assert "new-secret" not in payload
        assert payload.count("[REDACTED]") == 2
        assert audit_path.stat().st_mode & 0o777 == 0o600
