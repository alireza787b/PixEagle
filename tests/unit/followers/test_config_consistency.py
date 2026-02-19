"""
Config Consistency Tests (WP11.2)
===================================

Verifies that the follower registry, enums, schema, and config files
are all internally consistent. These tests catch mismatches early,
before they cause runtime failures.

Run with: pytest tests/unit/followers/test_config_consistency.py -v
"""

import sys
import os
import pytest
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIGS_DIR = PROJECT_ROOT / 'configs'
CONFIG_DEFAULT = CONFIGS_DIR / 'config_default.yaml'
FOLLOWER_COMMANDS = CONFIGS_DIR / 'follower_commands.yaml'


# =============================================================================
# Helpers
# =============================================================================

def _load_yaml(path: Path) -> dict:
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


# =============================================================================
# FollowerType enum tests
# =============================================================================

class TestFollowerTypeEnum:
    """FollowerType enum must be consistent with the factory registry."""

    def test_follower_type_importable(self):
        """FollowerType must import cleanly."""
        from classes.follower_types import FollowerType
        assert FollowerType is not None

    def test_follower_type_values_match_factory_registry(self):
        """Every FollowerType value must be registered in FollowerFactory."""
        from classes.follower_types import FollowerType
        from classes.follower import FollowerFactory
        FollowerFactory._initialize_registry()
        registry_keys = set(FollowerFactory._follower_registry.keys())
        enum_values = {ft.value for ft in FollowerType}
        missing = enum_values - registry_keys
        assert not missing, (
            f"FollowerType members not in factory registry: {missing}. "
            "Either add them to the registry or remove from the enum."
        )

    def test_factory_registry_covered_by_enum(self):
        """Every factory registry key should have a corresponding FollowerType."""
        from classes.follower_types import FollowerType
        from classes.follower import FollowerFactory
        FollowerFactory._initialize_registry()
        registry_keys = set(FollowerFactory._follower_registry.keys())
        enum_values = {ft.value for ft in FollowerType}
        extra = registry_keys - enum_values
        assert not extra, (
            f"Factory registry keys missing from FollowerType enum: {extra}. "
            "Add them to follower_types.py."
        )

    def test_removed_aliases_have_string_messages(self):
        """_REMOVED_ALIASES values must be descriptive error strings (not class refs)."""
        from classes.follower import FollowerFactory
        for alias, message in FollowerFactory._REMOVED_ALIASES.items():
            assert isinstance(message, str), (
                f"_REMOVED_ALIASES['{alias}'] should be a string error message, "
                f"got {type(message)}"
            )
            assert len(message) > 0, f"_REMOVED_ALIASES['{alias}'] must not be empty"


# =============================================================================
# Config file consistency tests
# =============================================================================

class TestConfigDefaultConsistency:
    """config_default.yaml structural consistency checks."""

    def test_config_default_loads(self):
        """config_default.yaml must be valid YAML."""
        config = _load_yaml(CONFIG_DEFAULT)
        assert isinstance(config, dict)

    def test_safety_section_present(self):
        """Safety section must exist."""
        config = _load_yaml(CONFIG_DEFAULT)
        assert 'Safety' in config, "Safety section missing from config_default.yaml"

    def test_global_limits_present(self):
        """Safety.GlobalLimits must have required keys."""
        config = _load_yaml(CONFIG_DEFAULT)
        gl = config['Safety']['GlobalLimits']
        required = [
            'MIN_ALTITUDE', 'MAX_ALTITUDE', 'MAX_VELOCITY',
            'EMERGENCY_STOP_ENABLED', 'RTL_ON_VIOLATION',
            'TARGET_LOSS_ACTION', 'ALTITUDE_SAFETY_ENABLED',
        ]
        for key in required:
            assert key in gl, f"Safety.GlobalLimits missing required key: {key}"

    def test_follower_overrides_keys_are_valid_follower_names(self):
        """Safety.FollowerOverrides keys must be valid FollowerType values (upper snake)."""
        config = _load_yaml(CONFIG_DEFAULT)
        overrides = config.get('Safety', {}).get('FollowerOverrides', {})
        if not overrides:
            pytest.skip("FollowerOverrides is empty — nothing to validate")
        from classes.follower_types import FollowerType
        valid_upper = {ft.value.upper() for ft in FollowerType}
        for key in overrides:
            assert key in valid_upper, (
                f"Safety.FollowerOverrides key '{key}' is not a valid follower name. "
                f"Valid names (UPPER_SNAKE): {sorted(valid_upper)}"
            )

    def test_pid_gains_section_has_expected_keys(self):
        """PID.PID_GAINS must have the canonical mc_/fw_ prefixed keys."""
        config = _load_yaml(CONFIG_DEFAULT)
        pid_gains = config.get('PID', {}).get('PID_GAINS', {})
        expected_prefixes = ['mc_', 'fw_']
        for key in pid_gains:
            has_prefix = any(key.startswith(p) for p in expected_prefixes)
            assert has_prefix, (
                f"PID_GAINS key '{key}' lacks mc_ or fw_ prefix. "
                "All keys must use platform prefixes."
            )

    def test_no_orphaned_sections(self):
        """Orphaned sections from v5 must not exist."""
        config = _load_yaml(CONFIG_DEFAULT)
        orphaned = ['YawControl', 'VerticalErrorRecalculation', 'AdaptiveControl',
                    'ChaseFollower', 'GainScheduling']
        for section in orphaned:
            assert section not in config, (
                f"Orphaned config section '{section}' still present. "
                "It should have been removed in WP8."
            )

    def test_target_loss_timeout_not_target_lost_timeout(self):
        """Renamed key TARGET_LOST_TIMEOUT must not appear anywhere in config."""
        raw = CONFIG_DEFAULT.read_text(encoding='utf-8')
        assert 'TARGET_LOST_TIMEOUT' not in raw, (
            "Stale key 'TARGET_LOST_TIMEOUT' found in config_default.yaml. "
            "Rename to TARGET_LOSS_TIMEOUT (WP7)."
        )

    def test_control_update_rate_not_update_rate(self):
        """Renamed key UPDATE_RATE must not appear as a standalone follower config key."""
        config = _load_yaml(CONFIG_DEFAULT)
        # Check GM_VELOCITY_CHASE and GM_VELOCITY_VECTOR sections specifically
        for section in ['GM_VELOCITY_CHASE', 'GM_VELOCITY_VECTOR']:
            if section in config:
                assert 'UPDATE_RATE' not in config[section], (
                    f"Stale key 'UPDATE_RATE' found in {section}. "
                    "Rename to CONTROL_UPDATE_RATE (WP7)."
                )

    def test_command_smoothing_enabled_key_consistent(self):
        """All smoothing enable keys must use COMMAND_SMOOTHING_ENABLED."""
        config = _load_yaml(CONFIG_DEFAULT)
        stale_keys = ['VELOCITY_SMOOTHING_ENABLED', 'ENABLE_COMMAND_SMOOTHING',
                      'RATE_SMOOTHING_ENABLED']
        for section_name, section_data in config.items():
            if isinstance(section_data, dict):
                for stale in stale_keys:
                    assert stale not in section_data, (
                        f"Stale smoothing key '{stale}' found in section '{section_name}'. "
                        f"Rename to COMMAND_SMOOTHING_ENABLED (WP7)."
                    )


# =============================================================================
# follower_commands.yaml consistency tests
# =============================================================================

class TestFollowerCommandsConsistency:
    """follower_commands.yaml must stay in sync with the factory."""

    def test_follower_commands_loads(self):
        """follower_commands.yaml must be valid YAML."""
        data = _load_yaml(FOLLOWER_COMMANDS)
        assert isinstance(data, dict)

    def test_profiles_match_factory_registry(self):
        """Every profile in follower_commands.yaml must be in the factory registry."""
        data = _load_yaml(FOLLOWER_COMMANDS)
        profiles = data.get('profiles', {})

        from classes.follower import FollowerFactory
        FollowerFactory._initialize_registry()
        registry_keys = set(FollowerFactory._follower_registry.keys())

        for profile_name in profiles:
            assert profile_name in registry_keys, (
                f"Profile '{profile_name}' in follower_commands.yaml is not "
                f"registered in FollowerFactory. Add it or remove the profile."
            )

    def test_deprecated_aliases_not_registered(self):
        """Profiles listed in deprecated_profile_aliases must NOT be in the active registry."""
        data = _load_yaml(FOLLOWER_COMMANDS)
        deprecated = set(data.get('deprecated_profile_aliases', {}).keys())

        from classes.follower import FollowerFactory
        FollowerFactory._initialize_registry()
        registry_keys = set(FollowerFactory._follower_registry.keys())

        collision = deprecated & registry_keys
        assert not collision, (
            f"Deprecated aliases are also in active registry: {collision}. "
            "Remove from deprecated_profile_aliases or unregister from factory."
        )


# =============================================================================
# NaN/Inf guard smoke test
# =============================================================================

class TestNaNGuard:
    """BaseFollower.set_command_field must reject non-finite values."""

    def _make_stub(self):
        """Create a minimal follower stub with mocked internals."""
        from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower
        stub = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
        from unittest.mock import MagicMock
        stub.setpoint_handler = MagicMock()
        return stub

    def test_nan_is_rejected(self):
        import math
        stub = self._make_stub()
        result = stub.set_command_field('vel_body_right', float('nan'))
        assert result is False
        stub.setpoint_handler.set_field.assert_not_called()

    def test_pos_inf_is_rejected(self):
        stub = self._make_stub()
        result = stub.set_command_field('vel_body_right', float('inf'))
        assert result is False
        stub.setpoint_handler.set_field.assert_not_called()

    def test_neg_inf_is_rejected(self):
        stub = self._make_stub()
        result = stub.set_command_field('vel_body_right', float('-inf'))
        assert result is False
        stub.setpoint_handler.set_field.assert_not_called()

    def test_finite_value_passes_through(self):
        stub = self._make_stub()
        stub.setpoint_handler.set_field.return_value = None
        result = stub.set_command_field('vel_body_right', 1.5)
        assert result is True
        stub.setpoint_handler.set_field.assert_called_once_with('vel_body_right', 1.5)
