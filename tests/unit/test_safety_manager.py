# tests/unit/test_safety_manager.py
"""
Unit tests for SafetyManager and safety types.

Tests the centralized safety limit management including:
- Singleton pattern
- Configuration loading
- Limit resolution hierarchy
- Caching behavior
- Altitude safety checks
- Command validation
"""

import pytest
import sys
import os
from math import radians

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from classes.safety_manager import SafetyManager, get_safety_manager, get_limit
from classes.safety_types import (
    VelocityLimits, AltitudeLimits, RateLimits, SafetyBehavior,
    SafetyStatus, SafetyAction, FollowerLimits,
    VehicleType, TargetLossAction, FOLLOWER_VEHICLE_TYPE, FIELD_LIMIT_MAPPING
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def safety_manager():
    """Create a fresh SafetyManager instance for each test."""
    SafetyManager.reset_instance()
    manager = SafetyManager.get_instance()
    yield manager
    SafetyManager.reset_instance()


@pytest.fixture
def config_with_global_limits():
    """Configuration with GlobalLimits section."""
    return {
        'Safety': {
            'GlobalLimits': {
                'MIN_ALTITUDE': 5.0,
                'MAX_ALTITUDE': 100.0,
                'ALTITUDE_WARNING_BUFFER': 3.0,
                'MAX_VELOCITY_FORWARD': 10.0,
                'MAX_VELOCITY_LATERAL': 6.0,
                'MAX_VELOCITY_VERTICAL': 4.0,
                'MAX_VELOCITY': 12.0,
                'MAX_YAW_RATE': 60.0,
                'MAX_PITCH_RATE': 45.0,
                'MAX_ROLL_RATE': 90.0,
                'EMERGENCY_STOP_ENABLED': True,
                'RTL_ON_VIOLATION': True,
                'ALTITUDE_SAFETY_ENABLED': True,
            },
            'FollowerOverrides': {
                'MC_VELOCITY_CHASE': {
                    'MAX_VELOCITY_FORWARD': 15.0,
                    'MAX_VELOCITY_VERTICAL': 5.0,
                },
                'FW_ATTITUDE_RATE': {
                    'MAX_VELOCITY_FORWARD': 25.0,
                    'ALTITUDE_SAFETY_ENABLED': False,
                }
            }
        }
    }


# =============================================================================
# Test: Singleton Pattern
# =============================================================================

class TestSingletonPattern:
    """Test SafetyManager singleton behavior."""

    def test_get_instance_returns_same_object(self):
        """Multiple get_instance calls return same object."""
        SafetyManager.reset_instance()
        instance1 = SafetyManager.get_instance()
        instance2 = SafetyManager.get_instance()
        assert instance1 is instance2

    def test_reset_instance_creates_new_object(self):
        """reset_instance creates a new instance."""
        instance1 = SafetyManager.get_instance()
        SafetyManager.reset_instance()
        instance2 = SafetyManager.get_instance()
        assert instance1 is not instance2

    def test_get_safety_manager_convenience(self, safety_manager):
        """get_safety_manager returns singleton."""
        result = get_safety_manager()
        assert result is safety_manager


# =============================================================================
# Test: Configuration Loading
# =============================================================================

class TestConfigurationLoading:
    """Test configuration loading."""

    def test_load_from_config_global_limits(self, safety_manager, config_with_global_limits):
        """GlobalLimits are loaded correctly."""
        safety_manager.load_from_config(config_with_global_limits)

        assert safety_manager.get_limit('MIN_ALTITUDE') == 5.0
        assert safety_manager.get_limit('MAX_ALTITUDE') == 100.0
        assert safety_manager.get_limit('MAX_VELOCITY_FORWARD') == 10.0

    def test_load_from_config_follower_overrides(self, safety_manager, config_with_global_limits):
        """FollowerOverrides are loaded correctly."""
        safety_manager.load_from_config(config_with_global_limits)

        # MC_VELOCITY_CHASE has override
        assert safety_manager.get_limit('MAX_VELOCITY_FORWARD', 'MC_VELOCITY_CHASE') == 15.0
        # But uses global for non-overridden
        assert safety_manager.get_limit('MAX_YAW_RATE', 'MC_VELOCITY_CHASE') == 60.0

    def test_load_empty_config_uses_fallbacks(self, safety_manager):
        """Empty config uses hardcoded fallbacks."""
        safety_manager.load_from_config({})

        # Should use fallbacks
        assert safety_manager.get_limit('MIN_ALTITUDE') == 3.0
        assert safety_manager.get_limit('MAX_ALTITUDE') == 120.0

    def test_initialized_flag_set(self, safety_manager, config_with_global_limits):
        """_initialized flag is set after loading."""
        assert safety_manager._initialized is False
        safety_manager.load_from_config(config_with_global_limits)
        assert safety_manager._initialized is True


# =============================================================================
# Test: Limit Resolution Hierarchy
# =============================================================================

class TestLimitResolutionHierarchy:
    """Test limit resolution order: Override -> Global -> Fallback."""

    def test_follower_override_takes_precedence(self, safety_manager, config_with_global_limits):
        """Follower-specific override takes precedence over global."""
        safety_manager.load_from_config(config_with_global_limits)

        # MC_VELOCITY_CHASE has override
        result = safety_manager.get_limit('MAX_VELOCITY_FORWARD', 'MC_VELOCITY_CHASE')
        assert result == 15.0  # Override value, not global 10.0

    def test_global_used_when_no_override(self, safety_manager, config_with_global_limits):
        """Global limit used when no follower override exists."""
        safety_manager.load_from_config(config_with_global_limits)

        # MC_VELOCITY_GROUND has no per-follower overrides — uses global
        result = safety_manager.get_limit('MAX_VELOCITY_FORWARD', 'MC_VELOCITY_GROUND')
        assert result == 10.0  # Global value

    def test_fallback_used_when_not_configured(self, safety_manager):
        """Fallback used when limit not in config."""
        safety_manager.load_from_config({'Safety': {'GlobalLimits': {}}})

        result = safety_manager.get_limit('MIN_ALTITUDE')
        assert result == 3.0  # Fallback value

    def test_alias_max_forward_velocity(self, safety_manager):
        """MAX_FORWARD_VELOCITY alias works."""
        config = {
            'Safety': {
                'GlobalLimits': {},
                'FollowerOverrides': {
                    'MC_VELOCITY_CHASE': {
                        'MAX_FORWARD_VELOCITY': 20.0  # Alias
                    }
                }
            }
        }
        safety_manager.load_from_config(config)

        result = safety_manager.get_limit('MAX_VELOCITY_FORWARD', 'MC_VELOCITY_CHASE')
        assert result == 20.0

    def test_case_insensitive_follower_lookup(self, safety_manager):
        """Follower names should be case-insensitive for override lookup."""
        config = {
            'Safety': {
                'GlobalLimits': {
                    'MIN_ALTITUDE': 3.0,
                    'MAX_VELOCITY_FORWARD': 10.0
                },
                'FollowerOverrides': {
                    'MC_VELOCITY_CHASE': {  # Config uses UPPERCASE
                        'MIN_ALTITUDE': 5.0,
                        'MAX_VELOCITY_FORWARD': 0.5
                    }
                }
            }
        }
        safety_manager.load_from_config(config)

        # Test lowercase lookup (common from frontend/config)
        result_lower = safety_manager.get_limit('MIN_ALTITUDE', 'mc_velocity_chase')
        assert result_lower == 5.0, "Lowercase follower name should find uppercase override"

        # Test uppercase lookup
        result_upper = safety_manager.get_limit('MIN_ALTITUDE', 'MC_VELOCITY_CHASE')
        assert result_upper == 5.0, "Uppercase follower name should find uppercase override"

        # Test mixed case lookup
        result_mixed = safety_manager.get_limit('MIN_ALTITUDE', 'Mc_Velocity_Chase')
        assert result_mixed == 5.0, "Mixed case follower name should find uppercase override"

        # Velocity limits should also work case-insensitively
        velocity_lower = safety_manager.get_limit('MAX_VELOCITY_FORWARD', 'mc_velocity_chase')
        assert velocity_lower == 0.5, "Velocity override should work with lowercase lookup"


# =============================================================================
# Test: Velocity Limits
# =============================================================================

class TestVelocityLimits:
    """Test velocity limit retrieval."""

    def test_get_velocity_limits_returns_named_tuple(self, safety_manager, config_with_global_limits):
        """get_velocity_limits returns VelocityLimits."""
        safety_manager.load_from_config(config_with_global_limits)

        limits = safety_manager.get_velocity_limits('MC_VELOCITY_CHASE')
        assert isinstance(limits, VelocityLimits)

    def test_velocity_limits_values(self, safety_manager, config_with_global_limits):
        """Velocity limits have correct values from global limits."""
        safety_manager.load_from_config(config_with_global_limits)

        # Use a follower without overrides to test global values
        limits = safety_manager.get_velocity_limits('MC_VELOCITY_GROUND')
        assert limits.forward == 10.0
        assert limits.lateral == 6.0
        assert limits.vertical == 4.0
        assert limits.max_magnitude == 12.0

    def test_velocity_limits_with_override(self, safety_manager, config_with_global_limits):
        """Velocity limits include follower overrides."""
        safety_manager.load_from_config(config_with_global_limits)

        limits = safety_manager.get_velocity_limits('MC_VELOCITY_CHASE')
        assert limits.forward == 15.0  # Override
        assert limits.vertical == 5.0  # Override
        assert limits.lateral == 6.0   # Global (no override)


# =============================================================================
# Test: Altitude Limits
# =============================================================================

class TestAltitudeLimits:
    """Test altitude limit retrieval."""

    def test_get_altitude_limits_returns_named_tuple(self, safety_manager, config_with_global_limits):
        """get_altitude_limits returns AltitudeLimits."""
        safety_manager.load_from_config(config_with_global_limits)

        limits = safety_manager.get_altitude_limits('MC_VELOCITY_CHASE')
        assert isinstance(limits, AltitudeLimits)

    def test_altitude_limits_values(self, safety_manager, config_with_global_limits):
        """Altitude limits have correct values."""
        safety_manager.load_from_config(config_with_global_limits)

        limits = safety_manager.get_altitude_limits('MC_VELOCITY_CHASE')
        assert limits.min_altitude == 5.0
        assert limits.max_altitude == 100.0
        assert limits.warning_buffer == 3.0
        assert limits.safety_enabled is True


# =============================================================================
# Test: Rate Limits
# =============================================================================

class TestRateLimits:
    """Test rate limit retrieval."""

    def test_get_rate_limits_returns_named_tuple(self, safety_manager, config_with_global_limits):
        """get_rate_limits returns RateLimits."""
        safety_manager.load_from_config(config_with_global_limits)

        limits = safety_manager.get_rate_limits('MC_VELOCITY_CHASE')
        assert isinstance(limits, RateLimits)

    def test_rate_limits_converted_to_radians(self, safety_manager, config_with_global_limits):
        """Rate limits are converted from deg/s to rad/s."""
        safety_manager.load_from_config(config_with_global_limits)

        limits = safety_manager.get_rate_limits('MC_VELOCITY_CHASE')
        assert limits.yaw == pytest.approx(radians(60.0))
        assert limits.pitch == pytest.approx(radians(45.0))
        assert limits.roll == pytest.approx(radians(90.0))


# =============================================================================
# Test: Caching
# =============================================================================

class TestCaching:
    """Test limit caching behavior."""

    def test_repeated_calls_use_cache(self, safety_manager, config_with_global_limits):
        """Repeated calls return cached values."""
        safety_manager.load_from_config(config_with_global_limits)

        # First call populates cache
        limits1 = safety_manager.get_velocity_limits('MC_VELOCITY_CHASE')
        # Second call should return same object
        limits2 = safety_manager.get_velocity_limits('MC_VELOCITY_CHASE')

        assert limits1 is limits2

    def test_clear_cache_resets_cache(self, safety_manager, config_with_global_limits):
        """clear_cache clears the cache."""
        safety_manager.load_from_config(config_with_global_limits)

        _ = safety_manager.get_velocity_limits('MC_VELOCITY_CHASE')
        assert len(safety_manager._cache) > 0

        safety_manager.clear_cache()
        assert len(safety_manager._cache) == 0

    def test_load_from_config_clears_cache(self, safety_manager, config_with_global_limits):
        """Loading config clears existing cache."""
        safety_manager.load_from_config(config_with_global_limits)
        _ = safety_manager.get_velocity_limits('MC_VELOCITY_CHASE')

        # Load new config
        new_config = {'Safety': {'GlobalLimits': {'MAX_VELOCITY_FORWARD': 20.0}}}
        safety_manager.load_from_config(new_config)

        # Cache should be cleared
        limits = safety_manager.get_velocity_limits('MC_VELOCITY_CHASE')
        assert limits.forward == 20.0


# =============================================================================
# Test: Altitude Safety Checks
# =============================================================================

class TestAltitudeSafetyChecks:
    """Test altitude safety check functionality."""

    def test_altitude_safe(self, safety_manager, config_with_global_limits):
        """Normal altitude returns safe status."""
        safety_manager.load_from_config(config_with_global_limits)

        status = safety_manager.check_altitude_safety(50.0, 'MC_VELOCITY_CHASE')
        assert status.safe is True
        assert status.action == SafetyAction.NONE

    def test_altitude_too_low(self, safety_manager, config_with_global_limits):
        """Altitude below minimum returns violation."""
        safety_manager.load_from_config(config_with_global_limits)

        status = safety_manager.check_altitude_safety(2.0, 'MC_VELOCITY_CHASE')  # Below 5.0
        assert status.safe is False
        assert 'too_low' in status.reason

    def test_altitude_too_high(self, safety_manager, config_with_global_limits):
        """Altitude above maximum returns violation."""
        safety_manager.load_from_config(config_with_global_limits)

        status = safety_manager.check_altitude_safety(150.0, 'MC_VELOCITY_CHASE')  # Above 100.0
        assert status.safe is False
        assert 'too_high' in status.reason

    def test_altitude_warning_low(self, safety_manager, config_with_global_limits):
        """Altitude near minimum returns warning."""
        safety_manager.load_from_config(config_with_global_limits)

        status = safety_manager.check_altitude_safety(6.0, 'MC_VELOCITY_CHASE')  # Near 5.0 + 3.0 buffer
        assert status.safe is True
        assert status.action == SafetyAction.WARN

    def test_altitude_warning_high(self, safety_manager, config_with_global_limits):
        """Altitude near maximum returns warning."""
        safety_manager.load_from_config(config_with_global_limits)

        status = safety_manager.check_altitude_safety(98.0, 'MC_VELOCITY_CHASE')  # Near 100.0 - 3.0 buffer
        assert status.safe is True
        assert status.action == SafetyAction.WARN

    def test_altitude_safety_disabled(self, safety_manager, config_with_global_limits):
        """Altitude check returns safe when disabled."""
        safety_manager.load_from_config(config_with_global_limits)

        # FW_ATTITUDE_RATE has ALTITUDE_SAFETY_ENABLED: False
        status = safety_manager.check_altitude_safety(2.0, 'FW_ATTITUDE_RATE')
        assert status.safe is True
        assert 'disabled' in status.reason


# =============================================================================
# Test: Command Validation
# =============================================================================

class TestCommandValidation:
    """Test command validation and clamping."""

    def test_validate_command_within_limits(self, safety_manager, config_with_global_limits):
        """Value within limits unchanged."""
        safety_manager.load_from_config(config_with_global_limits)

        result = safety_manager.validate_command('vel_body_fwd', 5.0, 'MC_VELOCITY_GROUND')
        assert result == 5.0

    def test_validate_command_exceeds_positive(self, safety_manager, config_with_global_limits):
        """Value exceeding positive limit is clamped."""
        safety_manager.load_from_config(config_with_global_limits)

        # Use follower without overrides to test global limit clamping
        result = safety_manager.validate_command('vel_body_fwd', 15.0, 'MC_VELOCITY_GROUND')
        assert result == 10.0  # MAX_VELOCITY_FORWARD (global)

    def test_validate_command_exceeds_negative(self, safety_manager, config_with_global_limits):
        """Value exceeding negative limit is clamped."""
        safety_manager.load_from_config(config_with_global_limits)

        result = safety_manager.validate_command('vel_body_fwd', -15.0, 'MC_VELOCITY_GROUND')
        assert result == -10.0  # -MAX_VELOCITY_FORWARD (global)

    def test_validate_command_unknown_field(self, safety_manager, config_with_global_limits):
        """Unknown field returns value unchanged."""
        safety_manager.load_from_config(config_with_global_limits)

        result = safety_manager.validate_command('unknown_field', 100.0, 'MC_VELOCITY_GROUND')
        assert result == 100.0


# =============================================================================
# Test: Safety Types
# =============================================================================

class TestSafetyTypes:
    """Test safety type structures."""

    def test_vehicle_type_enum(self):
        """VehicleType enum values."""
        assert VehicleType.MULTICOPTER.value == "MULTICOPTER"
        assert VehicleType.FIXED_WING.value == "FIXED_WING"
        assert VehicleType.GIMBAL.value == "GIMBAL"

    def test_target_loss_action_enum(self):
        """TargetLossAction enum values."""
        assert TargetLossAction.HOVER.value == "hover"
        assert TargetLossAction.ORBIT.value == "orbit"
        assert TargetLossAction.RTL.value == "rtl"

    def test_safety_action_enum(self):
        """SafetyAction enum values."""
        assert SafetyAction.NONE.value == "none"
        assert SafetyAction.WARN.value == "warn"
        assert SafetyAction.RTL.value == "rtl"
        assert SafetyAction.CLAMP.value == "clamp"

    def test_safety_status_ok(self):
        """SafetyStatus.ok() creates safe status."""
        status = SafetyStatus.ok()
        assert status.safe is True
        assert status.action == SafetyAction.NONE

    def test_safety_status_violation(self):
        """SafetyStatus.violation() creates violation status."""
        status = SafetyStatus.violation(
            reason="test_violation",
            action=SafetyAction.RTL,
            details={'key': 'value'}
        )
        assert status.safe is False
        assert status.reason == "test_violation"
        assert status.action == SafetyAction.RTL
        assert status.details == {'key': 'value'}

    def test_velocity_limits_named_tuple(self):
        """VelocityLimits is a NamedTuple."""
        limits = VelocityLimits(forward=10.0, lateral=5.0, vertical=3.0)
        assert limits.forward == 10.0
        assert limits.lateral == 5.0
        assert limits.vertical == 3.0
        assert limits.max_magnitude == 15.0  # Default

    def test_follower_vehicle_type_mapping(self):
        """FOLLOWER_VEHICLE_TYPE contains expected mappings."""
        assert FOLLOWER_VEHICLE_TYPE['MC_VELOCITY_CHASE'] == VehicleType.MULTICOPTER
        assert FOLLOWER_VEHICLE_TYPE['FW_ATTITUDE_RATE'] == VehicleType.FIXED_WING
        assert FOLLOWER_VEHICLE_TYPE['GM_VELOCITY_CHASE'] == VehicleType.GIMBAL

    def test_field_limit_mapping(self):
        """FIELD_LIMIT_MAPPING contains expected mappings."""
        assert FIELD_LIMIT_MAPPING['vel_body_fwd'] == 'MAX_VELOCITY_FORWARD'
        assert FIELD_LIMIT_MAPPING['yawspeed_deg_s'] == 'MAX_YAW_RATE'


# =============================================================================
# Test: Callbacks
# =============================================================================

class TestCallbacks:
    """Test callback registration and notification."""

    def test_register_callback(self, safety_manager):
        """Callback can be registered."""
        called = []

        def callback():
            called.append(True)

        safety_manager.register_callback(callback)
        safety_manager._notify_callbacks()

        assert len(called) == 1

    def test_unregister_callback(self, safety_manager):
        """Callback can be unregistered."""
        called = []

        def callback():
            called.append(True)

        safety_manager.register_callback(callback)
        safety_manager.unregister_callback(callback)
        safety_manager._notify_callbacks()

        assert len(called) == 0

    def test_clear_cache_notifies_callbacks(self, safety_manager):
        """clear_cache notifies registered callbacks."""
        called = []

        def callback():
            called.append(True)

        safety_manager.register_callback(callback)
        safety_manager.clear_cache()

        assert len(called) == 1


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_get_limit_function(self, safety_manager, config_with_global_limits):
        """get_limit() convenience function works."""
        safety_manager.load_from_config(config_with_global_limits)

        result = get_limit('MAX_VELOCITY_FORWARD')
        assert result == 10.0

    def test_get_limit_function_with_follower(self, safety_manager, config_with_global_limits):
        """get_limit() with follower name works."""
        safety_manager.load_from_config(config_with_global_limits)

        result = get_limit('MAX_VELOCITY_FORWARD', 'MC_VELOCITY_CHASE')
        assert result == 15.0
