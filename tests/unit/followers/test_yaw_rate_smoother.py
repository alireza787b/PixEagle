"""
Unit tests for YawRateSmoother (WP9 extraction from gm_velocity_chase_follower).

Tests cover:
- Deadzone suppresses low-rate jitter
- Rate limiting prevents jerky yaw acceleration
- EMA smoothing reduces noise
- Speed-adaptive scaling at low/high speeds
- Reset clears internal state
- from_config() factory method
- Both import paths work (canonical + backward-compat re-export)

Run with: pytest tests/unit/followers/test_yaw_rate_smoother.py -v
"""

import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.followers.yaw_rate_smoother import YawRateSmoother


# =============================================================================
# Factory
# =============================================================================

class TestFromConfig:
    def test_from_config_defaults(self):
        s = YawRateSmoother.from_config({})
        assert s.enabled is True
        assert s.deadzone_deg_s == pytest.approx(0.5)
        assert s.max_rate_change_deg_s2 == pytest.approx(90.0)
        assert s.smoothing_alpha == pytest.approx(0.7)

    def test_from_config_custom(self):
        s = YawRateSmoother.from_config({
            'ENABLED': False,
            'DEADZONE_DEG_S': 1.0,
            'MAX_RATE_CHANGE_DEG_S2': 45.0,
            'SMOOTHING_ALPHA': 0.5,
        })
        assert s.enabled is False
        assert s.deadzone_deg_s == pytest.approx(1.0)
        assert s.max_rate_change_deg_s2 == pytest.approx(45.0)
        assert s.smoothing_alpha == pytest.approx(0.5)


# =============================================================================
# Disabled passthrough
# =============================================================================

class TestDisabledMode:
    def test_disabled_returns_raw_rate(self):
        s = YawRateSmoother(enabled=False)
        assert s.apply(15.0, 0.05) == pytest.approx(15.0)

    def test_disabled_passes_zero(self):
        s = YawRateSmoother(enabled=False)
        assert s.apply(0.0, 0.05) == pytest.approx(0.0)


# =============================================================================
# Deadzone
# =============================================================================

class TestDeadzone:
    def test_below_deadzone_returns_zero(self):
        s = YawRateSmoother(
            deadzone_deg_s=2.0,
            max_rate_change_deg_s2=1000.0,  # no rate limiting interference
            smoothing_alpha=1.0,             # no EMA interference
            enable_speed_scaling=False,
        )
        assert s.apply(1.9, 0.05) == pytest.approx(0.0)

    def test_above_deadzone_non_zero(self):
        s = YawRateSmoother(
            deadzone_deg_s=2.0,
            max_rate_change_deg_s2=1000.0,
            smoothing_alpha=1.0,
            enable_speed_scaling=False,
        )
        result = s.apply(3.0, 0.05)
        assert result > 0.0  # Should pass through

    def test_deadzone_smooth_transition(self):
        """Output = |rate| - deadzone (smooth transition, not hard cut)."""
        s = YawRateSmoother(
            deadzone_deg_s=2.0,
            max_rate_change_deg_s2=1000.0,
            smoothing_alpha=1.0,
            enable_speed_scaling=False,
        )
        result = s.apply(5.0, 0.05)
        # After deadzone subtraction: 5 - 2 = 3.0 (before rate limit and EMA)
        assert result == pytest.approx(3.0, abs=0.1)


# =============================================================================
# Rate limiting
# =============================================================================

class TestRateLimiting:
    def test_large_step_is_rate_limited(self):
        """A step from 0 to 90 deg/s with 90 deg/s² limit over 0.05s → max 4.5."""
        s = YawRateSmoother(
            deadzone_deg_s=0.0,
            max_rate_change_deg_s2=90.0,
            smoothing_alpha=1.0,  # no EMA
            enable_speed_scaling=False,
        )
        result = s.apply(100.0, 0.05)  # max_change = 90 * 0.05 = 4.5
        assert result == pytest.approx(4.5, abs=0.1)

    def test_small_step_not_limited(self):
        """A step within the rate limit passes through fully."""
        s = YawRateSmoother(
            deadzone_deg_s=0.0,
            max_rate_change_deg_s2=90.0,
            smoothing_alpha=1.0,
            enable_speed_scaling=False,
        )
        result = s.apply(1.0, 0.05)  # max_change = 4.5, step = 1.0 → no limit
        assert result == pytest.approx(1.0, abs=0.1)

    def test_zero_dt_returns_target(self):
        """Zero dt should not divide by zero — return target directly."""
        s = YawRateSmoother(
            deadzone_deg_s=0.0,
            max_rate_change_deg_s2=90.0,
            smoothing_alpha=1.0,
            enable_speed_scaling=False,
        )
        result = s.apply(5.0, 0.0)
        assert math.isfinite(result)


# =============================================================================
# EMA smoothing
# =============================================================================

class TestEMASmoothing:
    def test_ema_converges_over_calls(self):
        """Repeated calls with same input should converge towards that input."""
        s = YawRateSmoother(
            deadzone_deg_s=0.0,
            max_rate_change_deg_s2=10000.0,  # no rate limit
            smoothing_alpha=0.5,
            enable_speed_scaling=False,
        )
        target = 10.0
        result = None
        for _ in range(30):
            result = s.apply(target, 0.05)
        assert result == pytest.approx(target, rel=0.01)

    def test_alpha_1_means_no_smoothing(self):
        """smoothing_alpha=1.0 → output equals input each call."""
        s = YawRateSmoother(
            deadzone_deg_s=0.0,
            max_rate_change_deg_s2=10000.0,
            smoothing_alpha=1.0,
            enable_speed_scaling=False,
        )
        result = s.apply(7.0, 0.05)
        assert result == pytest.approx(7.0, abs=0.01)


# =============================================================================
# Speed-adaptive scaling
# =============================================================================

class TestSpeedScaling:
    def test_high_speed_full_authority(self):
        """Above max_speed_threshold, yaw rate is unchanged."""
        s = YawRateSmoother(
            deadzone_deg_s=0.0,
            max_rate_change_deg_s2=10000.0,
            smoothing_alpha=1.0,
            enable_speed_scaling=True,
            min_speed_threshold=0.5,
            max_speed_threshold=5.0,
            low_speed_yaw_factor=0.5,
        )
        result = s.apply(10.0, 0.05, forward_speed=10.0)
        assert result == pytest.approx(10.0, abs=0.1)

    def test_low_speed_reduced_authority(self):
        """Below min_speed_threshold, yaw rate is multiplied by low_speed_yaw_factor."""
        s = YawRateSmoother(
            deadzone_deg_s=0.0,
            max_rate_change_deg_s2=10000.0,
            smoothing_alpha=1.0,
            enable_speed_scaling=True,
            min_speed_threshold=0.5,
            max_speed_threshold=5.0,
            low_speed_yaw_factor=0.5,
        )
        result = s.apply(10.0, 0.05, forward_speed=0.0)
        assert result == pytest.approx(5.0, abs=0.2)

    def test_mid_speed_interpolated(self):
        """At midpoint speed, factor should be between low_speed_factor and 1.0."""
        s = YawRateSmoother(
            deadzone_deg_s=0.0,
            max_rate_change_deg_s2=10000.0,
            smoothing_alpha=1.0,
            enable_speed_scaling=True,
            min_speed_threshold=0.0,
            max_speed_threshold=10.0,
            low_speed_yaw_factor=0.0,
        )
        result = s.apply(10.0, 0.05, forward_speed=5.0)  # midpoint → factor = 0.5
        assert 4.0 < result < 6.0


# =============================================================================
# Reset
# =============================================================================

class TestReset:
    def test_reset_clears_state(self):
        """After reset(), the smoother forgets history and starts fresh."""
        s = YawRateSmoother(
            deadzone_deg_s=0.0,
            max_rate_change_deg_s2=10000.0,
            smoothing_alpha=0.5,
            enable_speed_scaling=False,
        )
        # Build up state
        for _ in range(10):
            s.apply(20.0, 0.05)
        assert s.last_yaw_rate != 0.0

        s.reset()
        assert s.last_yaw_rate == pytest.approx(0.0)
        assert s.filtered_yaw_rate == pytest.approx(0.0)


# =============================================================================
# Backward-compat re-export from gm_velocity_chase
# =============================================================================

class TestBackwardCompatImport:
    def test_import_from_gm_velocity_chase(self):
        """YawRateSmoother must still be importable from gm_velocity_chase_follower."""
        from classes.followers.gm_velocity_chase_follower import YawRateSmoother as YRS_compat
        assert YRS_compat is YawRateSmoother  # Same object (not a copy)

    def test_canonical_import(self):
        """Canonical import from yaw_rate_smoother module works."""
        from classes.followers.yaw_rate_smoother import YawRateSmoother as YRS_canon
        assert YRS_canon is YawRateSmoother
