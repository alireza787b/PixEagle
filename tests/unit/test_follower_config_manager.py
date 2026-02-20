# tests/unit/test_follower_config_manager.py
"""
Unit tests for FollowerConfigManager.

Tests the centralized follower operational config including:
- Singleton pattern
- Configuration loading
- Parameter resolution hierarchy (override -> general -> fallback)
- Legacy backward compatibility with deprecation warning
- YAW_SMOOTHING merge logic
- Caching behavior
- Provenance summary for dashboard UI
- Callbacks
"""

import pytest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from classes.follower_config_manager import (
    FollowerConfigManager, get_follower_config_manager, get_follower_param,
    GENERAL_PARAMS
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def fcm():
    """Create a fresh FollowerConfigManager instance for each test."""
    FollowerConfigManager.reset_instance()
    manager = FollowerConfigManager.get_instance()
    yield manager
    FollowerConfigManager.reset_instance()


@pytest.fixture
def config_with_general():
    """Configuration with Follower.General and FollowerOverrides."""
    return {
        'Follower': {
            'FOLLOWER_MODE': 'mc_velocity_position',
            'USE_MAVLINK2REST': True,
            'General': {
                'CONTROL_UPDATE_RATE': 20.0,
                'COMMAND_SMOOTHING_ENABLED': True,
                'SMOOTHING_FACTOR': 0.8,
                'TARGET_LOSS_TIMEOUT': 3.0,
                'TARGET_LOSS_COORDINATE_THRESHOLD': 1.5,
                'LATERAL_GUIDANCE_MODE': 'coordinated_turn',
                'ENABLE_AUTO_MODE_SWITCHING': False,
                'GUIDANCE_MODE_SWITCH_VELOCITY': 3.0,
                'MODE_SWITCH_HYSTERESIS': 0.5,
                'MIN_MODE_SWITCH_INTERVAL': 2.0,
                'ENABLE_ALTITUDE_CONTROL': False,
                'ALTITUDE_CHECK_INTERVAL': 0.1,
                'YAW_SMOOTHING': {
                    'ENABLED': True,
                    'DEADZONE_DEG_S': 0.5,
                    'MAX_RATE_CHANGE_DEG_S2': 90.0,
                    'SMOOTHING_ALPHA': 0.7,
                    'ENABLE_SPEED_SCALING': True,
                    'MIN_SPEED_THRESHOLD': 0.5,
                    'MAX_SPEED_THRESHOLD': 5.0,
                    'LOW_SPEED_YAW_FACTOR': 0.5,
                },
            },
            'FollowerOverrides': {
                'MC_VELOCITY_CHASE': {
                    'TARGET_LOSS_TIMEOUT': 2.0,
                },
                'MC_ATTITUDE_RATE': {
                    'CONTROL_UPDATE_RATE': 50.0,
                    'SMOOTHING_FACTOR': 0.85,
                    'TARGET_LOSS_TIMEOUT': 2.0,
                },
                'FW_ATTITUDE_RATE': {
                    'SMOOTHING_FACTOR': 0.85,
                },
                'GM_VELOCITY_VECTOR': {
                    'LATERAL_GUIDANCE_MODE': 'sideslip',
                },
                'MC_VELOCITY_GROUND': {
                    'YAW_SMOOTHING': {
                        'ENABLED': False,
                    },
                },
            },
        }
    }


# =============================================================================
# Test: Singleton Pattern
# =============================================================================

class TestSingletonPattern:
    """Test FollowerConfigManager singleton behavior."""

    def test_get_instance_returns_same_object(self):
        """Multiple get_instance calls return same object."""
        FollowerConfigManager.reset_instance()
        instance1 = FollowerConfigManager.get_instance()
        instance2 = FollowerConfigManager.get_instance()
        assert instance1 is instance2

    def test_reset_instance_creates_new_object(self):
        """reset_instance creates a new instance."""
        instance1 = FollowerConfigManager.get_instance()
        FollowerConfigManager.reset_instance()
        instance2 = FollowerConfigManager.get_instance()
        assert instance1 is not instance2

    def test_convenience_function(self, fcm):
        """get_follower_config_manager returns singleton."""
        result = get_follower_config_manager()
        assert result is fcm


# =============================================================================
# Test: Configuration Loading
# =============================================================================

class TestConfigurationLoading:
    """Test configuration loading."""

    def test_load_general_params(self, fcm, config_with_general):
        """General params are loaded correctly."""
        fcm.load_from_config(config_with_general)

        assert fcm.get_param('CONTROL_UPDATE_RATE') == 20.0
        assert fcm.get_param('TARGET_LOSS_TIMEOUT') == 3.0
        assert fcm.get_param('SMOOTHING_FACTOR') == 0.8

    def test_load_follower_overrides(self, fcm, config_with_general):
        """FollowerOverrides are loaded correctly."""
        fcm.load_from_config(config_with_general)

        # MC_ATTITUDE_RATE has override for CONTROL_UPDATE_RATE
        assert fcm.get_param('CONTROL_UPDATE_RATE', 'MC_ATTITUDE_RATE') == 50.0
        # But uses General for non-overridden params
        assert fcm.get_param('ENABLE_AUTO_MODE_SWITCHING', 'MC_ATTITUDE_RATE') is False

    def test_load_empty_config_uses_fallbacks(self, fcm):
        """Empty config uses hardcoded fallbacks."""
        fcm.load_from_config({})

        assert fcm.get_param('CONTROL_UPDATE_RATE') == 20.0
        assert fcm.get_param('SMOOTHING_FACTOR') == 0.8

    def test_initialized_flag_set(self, fcm, config_with_general):
        """_initialized flag is set after loading."""
        assert fcm._initialized is False
        fcm.load_from_config(config_with_general)
        assert fcm._initialized is True

    def test_non_general_params_ignored(self, fcm, config_with_general):
        """Follower interface params (FOLLOWER_MODE etc.) are not in General."""
        fcm.load_from_config(config_with_general)
        # FOLLOWER_MODE is not a general operational param
        assert fcm.get_param('FOLLOWER_MODE') is None


# =============================================================================
# Test: Parameter Resolution Hierarchy
# =============================================================================

class TestResolutionHierarchy:
    """Test resolution order: Override -> General -> Fallback."""

    def test_override_takes_precedence(self, fcm, config_with_general):
        """Follower-specific override takes precedence over General."""
        fcm.load_from_config(config_with_general)

        result = fcm.get_param('TARGET_LOSS_TIMEOUT', 'MC_VELOCITY_CHASE')
        assert result == 2.0  # Override value, not General 3.0

    def test_general_used_when_no_override(self, fcm, config_with_general):
        """General value used when no follower override exists."""
        fcm.load_from_config(config_with_general)

        # MC_VELOCITY_POSITION has no overrides
        result = fcm.get_param('CONTROL_UPDATE_RATE', 'MC_VELOCITY_POSITION')
        assert result == 20.0  # General value

    def test_fallback_used_when_not_configured(self, fcm):
        """Fallback used when param not in General or overrides."""
        fcm.load_from_config({'Follower': {'General': {}}})

        result = fcm.get_param('CONTROL_UPDATE_RATE')
        assert result == 20.0  # Fallback value

    def test_case_insensitive_follower_lookup(self, fcm, config_with_general):
        """Follower names are case-insensitive for override lookup."""
        fcm.load_from_config(config_with_general)

        # Config has 'MC_VELOCITY_CHASE' (uppercase)
        result_lower = fcm.get_param('TARGET_LOSS_TIMEOUT', 'mc_velocity_chase')
        assert result_lower == 2.0

        result_upper = fcm.get_param('TARGET_LOSS_TIMEOUT', 'MC_VELOCITY_CHASE')
        assert result_upper == 2.0

        result_mixed = fcm.get_param('TARGET_LOSS_TIMEOUT', 'Mc_Velocity_Chase')
        assert result_mixed == 2.0

    def test_multiple_overrides_independent(self, fcm, config_with_general):
        """Different followers get their own override values."""
        fcm.load_from_config(config_with_general)

        # MC_VELOCITY_CHASE: timeout=2.0
        assert fcm.get_param('TARGET_LOSS_TIMEOUT', 'MC_VELOCITY_CHASE') == 2.0
        # MC_ATTITUDE_RATE: timeout=2.0, rate=50.0
        assert fcm.get_param('TARGET_LOSS_TIMEOUT', 'MC_ATTITUDE_RATE') == 2.0
        assert fcm.get_param('CONTROL_UPDATE_RATE', 'MC_ATTITUDE_RATE') == 50.0
        # FW_ATTITUDE_RATE: smoothing=0.85, timeout=General(3.0)
        assert fcm.get_param('SMOOTHING_FACTOR', 'FW_ATTITUDE_RATE') == 0.85
        assert fcm.get_param('TARGET_LOSS_TIMEOUT', 'FW_ATTITUDE_RATE') == 3.0

    def test_unknown_param_returns_none(self, fcm, config_with_general):
        """Unknown parameter returns None."""
        fcm.load_from_config(config_with_general)

        result = fcm.get_param('NONEXISTENT_PARAM', 'MC_VELOCITY_CHASE')
        assert result is None

    def test_lateral_guidance_override(self, fcm, config_with_general):
        """String param override works (GM_VELOCITY_VECTOR -> sideslip)."""
        fcm.load_from_config(config_with_general)

        assert fcm.get_param('LATERAL_GUIDANCE_MODE', 'GM_VELOCITY_VECTOR') == 'sideslip'
        assert fcm.get_param('LATERAL_GUIDANCE_MODE', 'MC_VELOCITY_CHASE') == 'coordinated_turn'


# =============================================================================
# Test: YAW_SMOOTHING Merge
# =============================================================================

class TestYawSmoothingMerge:
    """Test YAW_SMOOTHING config merging."""

    def test_general_yaw_smoothing(self, fcm, config_with_general):
        """General YAW_SMOOTHING is returned for follower without override."""
        fcm.load_from_config(config_with_general)

        yaw_cfg = fcm.get_yaw_smoothing_config('MC_VELOCITY_CHASE')
        assert yaw_cfg['ENABLED'] is True
        assert yaw_cfg['DEADZONE_DEG_S'] == 0.5
        assert yaw_cfg['SMOOTHING_ALPHA'] == 0.7

    def test_override_merges_with_general(self, fcm, config_with_general):
        """Per-follower YAW_SMOOTHING override merges with General base."""
        fcm.load_from_config(config_with_general)

        # MC_VELOCITY_GROUND overrides only ENABLED=False
        yaw_cfg = fcm.get_yaw_smoothing_config('MC_VELOCITY_GROUND')
        assert yaw_cfg['ENABLED'] is False  # Overridden
        assert yaw_cfg['DEADZONE_DEG_S'] == 0.5  # From General
        assert yaw_cfg['SMOOTHING_ALPHA'] == 0.7  # From General

    def test_fallback_yaw_smoothing(self, fcm):
        """Fallback YAW_SMOOTHING when no config at all."""
        fcm.load_from_config({})

        yaw_cfg = fcm.get_yaw_smoothing_config('MC_VELOCITY_CHASE')
        assert yaw_cfg['ENABLED'] is True
        assert yaw_cfg['DEADZONE_DEG_S'] == 0.5

    def test_yaw_smoothing_has_all_keys(self, fcm, config_with_general):
        """YAW_SMOOTHING always has all 8 keys regardless of override."""
        fcm.load_from_config(config_with_general)

        expected_keys = {
            'ENABLED', 'DEADZONE_DEG_S', 'MAX_RATE_CHANGE_DEG_S2',
            'SMOOTHING_ALPHA', 'ENABLE_SPEED_SCALING', 'MIN_SPEED_THRESHOLD',
            'MAX_SPEED_THRESHOLD', 'LOW_SPEED_YAW_FACTOR',
        }

        # Follower with no yaw override
        yaw_cfg = fcm.get_yaw_smoothing_config('MC_VELOCITY_CHASE')
        assert set(yaw_cfg.keys()) == expected_keys

        # Follower with partial override
        yaw_cfg = fcm.get_yaw_smoothing_config('MC_VELOCITY_GROUND')
        assert set(yaw_cfg.keys()) == expected_keys


# =============================================================================
# Test: Caching
# =============================================================================

class TestCaching:
    """Test config caching behavior."""

    def test_repeated_calls_use_cache(self, fcm, config_with_general):
        """Repeated calls return cached values."""
        fcm.load_from_config(config_with_general)

        _ = fcm.get_param('CONTROL_UPDATE_RATE', 'MC_VELOCITY_CHASE')
        assert len(fcm._cache) > 0

        # Second call should hit cache
        val2 = fcm.get_param('CONTROL_UPDATE_RATE', 'MC_VELOCITY_CHASE')
        assert val2 == 20.0

    def test_clear_cache_resets_cache(self, fcm, config_with_general):
        """clear_cache clears the cache."""
        fcm.load_from_config(config_with_general)

        _ = fcm.get_param('CONTROL_UPDATE_RATE')
        assert len(fcm._cache) > 0

        fcm.clear_cache()
        assert len(fcm._cache) == 0

    def test_load_from_config_clears_cache(self, fcm, config_with_general):
        """Loading config clears existing cache."""
        fcm.load_from_config(config_with_general)
        _ = fcm.get_param('CONTROL_UPDATE_RATE', 'MC_ATTITUDE_RATE')
        assert fcm.get_param('CONTROL_UPDATE_RATE', 'MC_ATTITUDE_RATE') == 50.0

        # Load new config with different value
        new_config = {
            'Follower': {
                'General': {'CONTROL_UPDATE_RATE': 30.0},
                'FollowerOverrides': {},
            }
        }
        fcm.load_from_config(new_config)

        # MC_ATTITUDE_RATE should now get General value (no more override)
        assert fcm.get_param('CONTROL_UPDATE_RATE', 'MC_ATTITUDE_RATE') == 30.0

    def test_yaw_smoothing_cached(self, fcm, config_with_general):
        """YAW_SMOOTHING is cached."""
        fcm.load_from_config(config_with_general)

        yaw1 = fcm.get_yaw_smoothing_config('MC_VELOCITY_CHASE')
        yaw2 = fcm.get_yaw_smoothing_config('MC_VELOCITY_CHASE')
        assert yaw1 is yaw2  # Same object from cache


# =============================================================================
# Test: Provenance Summary
# =============================================================================

class TestProvenanceSummary:
    """Test get_effective_config_summary for dashboard UI."""

    def test_general_source(self, fcm, config_with_general):
        """Params without override show source='General'."""
        fcm.load_from_config(config_with_general)

        summary = fcm.get_effective_config_summary('MC_VELOCITY_POSITION')
        entry = summary['CONTROL_UPDATE_RATE']
        assert entry['effective_value'] == 20.0
        assert entry['source'] == 'General'
        assert entry['is_overridden'] is False
        assert entry['override_value'] is None

    def test_override_source(self, fcm, config_with_general):
        """Params with override show source='FollowerOverrides.{name}'."""
        fcm.load_from_config(config_with_general)

        summary = fcm.get_effective_config_summary('MC_ATTITUDE_RATE')
        entry = summary['CONTROL_UPDATE_RATE']
        assert entry['effective_value'] == 50.0
        assert entry['source'] == 'FollowerOverrides.MC_ATTITUDE_RATE'
        assert entry['is_overridden'] is True
        assert entry['override_value'] == 50.0
        assert entry['general_value'] == 20.0

    def test_fallback_source(self, fcm):
        """Params without config show source='Fallback'."""
        fcm.load_from_config({})

        summary = fcm.get_effective_config_summary()
        entry = summary['CONTROL_UPDATE_RATE']
        assert entry['effective_value'] == 20.0
        assert entry['source'] == 'Fallback'
        assert entry['general_value'] is None
        assert entry['override_value'] is None

    def test_summary_includes_all_general_params(self, fcm, config_with_general):
        """Summary includes all GENERAL_PARAMS + YAW_SMOOTHING."""
        fcm.load_from_config(config_with_general)

        summary = fcm.get_effective_config_summary('MC_VELOCITY_CHASE')
        for param in GENERAL_PARAMS:
            assert param in summary, f"Missing {param} in summary"
        assert 'YAW_SMOOTHING' in summary

    def test_yaw_smoothing_provenance(self, fcm, config_with_general):
        """YAW_SMOOTHING provenance shows override status."""
        fcm.load_from_config(config_with_general)

        # MC_VELOCITY_GROUND has YAW_SMOOTHING override
        summary = fcm.get_effective_config_summary('MC_VELOCITY_GROUND')
        yaw_entry = summary['YAW_SMOOTHING']
        assert yaw_entry['is_overridden'] is True
        assert yaw_entry['effective_value']['ENABLED'] is False

        # MC_VELOCITY_CHASE has no YAW_SMOOTHING override
        summary2 = fcm.get_effective_config_summary('MC_VELOCITY_CHASE')
        yaw_entry2 = summary2['YAW_SMOOTHING']
        assert yaw_entry2['is_overridden'] is False
        assert yaw_entry2['effective_value']['ENABLED'] is True

    def test_no_follower_returns_general_only(self, fcm, config_with_general):
        """Summary without follower_name returns General values."""
        fcm.load_from_config(config_with_general)

        summary = fcm.get_effective_config_summary()
        for param in GENERAL_PARAMS:
            assert summary[param]['is_overridden'] is False
            assert summary[param]['source'] == 'General'


# =============================================================================
# Test: Callbacks
# =============================================================================

class TestCallbacks:
    """Test callback registration and notification."""

    def test_register_callback(self, fcm):
        """Callback can be registered and fired."""
        called = []

        def callback():
            called.append(True)

        fcm.register_callback(callback)
        fcm._notify_callbacks()

        assert len(called) == 1

    def test_unregister_callback(self, fcm):
        """Callback can be unregistered."""
        called = []

        def callback():
            called.append(True)

        fcm.register_callback(callback)
        fcm.unregister_callback(callback)
        fcm._notify_callbacks()

        assert len(called) == 0

    def test_clear_cache_notifies_callbacks(self, fcm):
        """clear_cache notifies registered callbacks."""
        called = []

        def callback():
            called.append(True)

        fcm.register_callback(callback)
        fcm.clear_cache()

        assert len(called) == 1

    def test_callback_error_does_not_crash(self, fcm):
        """A failing callback doesn't crash the manager."""
        def bad_callback():
            raise RuntimeError("test error")

        fcm.register_callback(bad_callback)
        # Should not raise
        fcm.clear_cache()


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_get_follower_param(self, fcm, config_with_general):
        """get_follower_param convenience function works."""
        fcm.load_from_config(config_with_general)

        result = get_follower_param('CONTROL_UPDATE_RATE')
        assert result == 20.0

    def test_get_follower_param_with_follower(self, fcm, config_with_general):
        """get_follower_param with follower name works."""
        fcm.load_from_config(config_with_general)

        result = get_follower_param('CONTROL_UPDATE_RATE', 'MC_ATTITUDE_RATE')
        assert result == 50.0


# =============================================================================
# Test: Available Followers
# =============================================================================

class TestAvailableFollowers:
    """Test get_available_followers."""

    def test_returns_followers_with_overrides(self, fcm, config_with_general):
        """Returns list of followers that have configured overrides."""
        fcm.load_from_config(config_with_general)

        followers = fcm.get_available_followers()
        assert 'MC_VELOCITY_CHASE' in followers
        assert 'MC_ATTITUDE_RATE' in followers
        assert 'FW_ATTITUDE_RATE' in followers
        assert 'GM_VELOCITY_VECTOR' in followers
        assert 'MC_VELOCITY_GROUND' in followers

    def test_empty_when_no_overrides(self, fcm):
        """Returns empty list when no overrides configured."""
        fcm.load_from_config({'Follower': {'General': {}, 'FollowerOverrides': {}}})
        assert fcm.get_available_followers() == []


# =============================================================================
# Test: Debug Summary
# =============================================================================

class TestDebugSummary:
    """Test get_all_config_summary for debugging."""

    def test_summary_structure(self, fcm, config_with_general):
        """Summary has expected keys."""
        fcm.load_from_config(config_with_general)

        summary = fcm.get_all_config_summary()
        assert 'general' in summary
        assert 'follower_overrides' in summary
        assert 'cache_size' in summary
        assert 'initialized' in summary
        assert summary['initialized'] is True
