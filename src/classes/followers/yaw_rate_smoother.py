# src/classes/followers/yaw_rate_smoother.py
"""
YawRateSmoother — Enterprise-grade yaw rate smoothing (WP9 extraction).

Extracted from gm_velocity_chase_follower.py so it can be shared by:
  - gm_velocity_chase_follower (original owner)
  - gm_velocity_vector_follower
  - mc_velocity_chase_follower

Import from here:
    from classes.followers.yaw_rate_smoother import YawRateSmoother
"""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class YawRateSmoother:
    """
    Enterprise-grade yaw rate smoothing with deadzone, rate limiting, and EMA.

    Features:
    - Configurable deadzone to prevent jitter at low rates
    - Rate-of-change limiting for smooth acceleration (prevents jerky movements)
    - EMA smoothing for noise reduction
    - Speed-adaptive scaling (works with slow AND fast forward speeds)

    All parameters are configurable via YAML — no hardcoded values.
    """

    # Configuration (loaded from YAML)
    enabled: bool = True
    deadzone_deg_s: float = 0.5           # deg/s — ignore rates below this
    max_rate_change_deg_s2: float = 90.0  # deg/s² — max yaw acceleration
    smoothing_alpha: float = 0.7          # EMA coefficient (0-1)
    enable_speed_scaling: bool = True     # Scale based on forward speed
    min_speed_threshold: float = 0.5      # m/s — below this, reduce authority
    max_speed_threshold: float = 5.0      # m/s — above this, full authority
    low_speed_yaw_factor: float = 0.5     # Reduce yaw by this factor at low speed

    # Internal state (not from config)
    last_yaw_rate: float = field(default=0.0, init=False)
    filtered_yaw_rate: float = field(default=0.0, init=False)

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'YawRateSmoother':
        """Create a YawRateSmoother from configuration dictionary."""
        return cls(
            enabled=config.get('ENABLED', True),
            deadzone_deg_s=config.get('DEADZONE_DEG_S', 0.5),
            max_rate_change_deg_s2=config.get('MAX_RATE_CHANGE_DEG_S2', 90.0),
            smoothing_alpha=config.get('SMOOTHING_ALPHA', 0.7),
            enable_speed_scaling=config.get('ENABLE_SPEED_SCALING', True),
            min_speed_threshold=config.get('MIN_SPEED_THRESHOLD', 0.5),
            max_speed_threshold=config.get('MAX_SPEED_THRESHOLD', 5.0),
            low_speed_yaw_factor=config.get('LOW_SPEED_YAW_FACTOR', 0.5),
        )

    def apply(self, raw_yaw_rate: float, dt: float, forward_speed: float = 0.0) -> float:
        """
        Apply full smoothing pipeline to yaw rate command.

        Args:
            raw_yaw_rate: Raw PID output (deg/s)
            dt: Time delta since last call (seconds)
            forward_speed: Current forward velocity (m/s) for speed-adaptive scaling

        Returns:
            Smoothed yaw rate (deg/s)
        """
        if not self.enabled:
            return raw_yaw_rate

        # 1. Apply deadzone (prevents jitter at low rates)
        yaw_rate = self._apply_deadzone(raw_yaw_rate)

        # 2. Apply speed-adaptive scaling (works with slow AND fast speeds)
        if self.enable_speed_scaling:
            yaw_rate = self._apply_speed_scaling(yaw_rate, forward_speed)

        # 3. Apply rate-of-change limiting (prevents jerky movements)
        yaw_rate = self._apply_rate_limiting(yaw_rate, dt)

        # 4. Apply EMA smoothing (noise reduction)
        yaw_rate = self._apply_ema_smoothing(yaw_rate)

        return yaw_rate

    def _apply_deadzone(self, rate: float) -> float:
        """Apply deadzone with smooth transition (not abrupt)."""
        if abs(rate) < self.deadzone_deg_s:
            return 0.0
        sign = 1.0 if rate > 0 else -1.0
        return sign * (abs(rate) - self.deadzone_deg_s)

    def _apply_speed_scaling(self, rate: float, speed: float) -> float:
        """Scale yaw authority based on forward speed (works for slow AND fast)."""
        if speed >= self.max_speed_threshold:
            return rate  # Full authority at high speed
        if speed <= self.min_speed_threshold:
            return rate * self.low_speed_yaw_factor  # Reduced at low speed
        # Linear interpolation between thresholds
        t = (speed - self.min_speed_threshold) / (self.max_speed_threshold - self.min_speed_threshold)
        factor = self.low_speed_yaw_factor + t * (1.0 - self.low_speed_yaw_factor)
        return rate * factor

    def _apply_rate_limiting(self, target_rate: float, dt: float) -> float:
        """Limit rate-of-change for smooth yaw acceleration."""
        if dt <= 0:
            return target_rate
        max_change = self.max_rate_change_deg_s2 * dt
        delta = target_rate - self.last_yaw_rate
        if abs(delta) > max_change:
            limited_rate = self.last_yaw_rate + (max_change if delta > 0 else -max_change)
        else:
            limited_rate = target_rate
        self.last_yaw_rate = limited_rate
        return limited_rate

    def _apply_ema_smoothing(self, rate: float) -> float:
        """Apply exponential moving average smoothing."""
        self.filtered_yaw_rate = (
            self.smoothing_alpha * rate + (1.0 - self.smoothing_alpha) * self.filtered_yaw_rate
        )
        return self.filtered_yaw_rate

    def reset(self):
        """Reset internal state (call when tracking starts/stops)."""
        self.last_yaw_rate = 0.0
        self.filtered_yaw_rate = 0.0
