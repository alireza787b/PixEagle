# tests/fixtures/mock_safety.py
"""
Safety Manager mocks and test configuration.

Provides mock SafetyManager and test configuration dictionaries
for isolated follower testing.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import yaml


@dataclass
class MockVelocityLimits:
    """Mock velocity limits for testing."""
    forward: float = 10.0
    lateral: float = 5.0
    vertical: float = 3.0
    min_forward: float = 0.0
    default_forward: float = 5.0
    max_magnitude: float = 15.0


@dataclass
class MockAltitudeLimits:
    """Mock altitude limits for testing."""
    min_altitude: float = 5.0
    max_altitude: float = 120.0
    warning_buffer: float = 5.0
    home_relative: bool = True
    safety_enabled: bool = True


@dataclass
class MockRateLimits:
    """Mock rate limits for testing (radians/sec)."""
    yaw: float = 0.785  # ~45 deg/s
    pitch: float = 0.524  # ~30 deg/s
    roll: float = 1.047  # ~60 deg/s


class MockSafetyManager:
    """
    Mock SafetyManager for testing.

    Provides configurable limits and tracks safety checks.
    """

    _instance = None

    def __init__(self):
        self.velocity_limits = MockVelocityLimits()
        self.altitude_limits = MockAltitudeLimits()
        self.rate_limits = MockRateLimits()

        # Tracking
        self._altitude_checks = []
        self._safety_violations = 0

        # Follower-specific overrides
        self._follower_overrides: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> 'MockSafetyManager':
        """Singleton access."""
        if cls._instance is None:
            cls._instance = MockSafetyManager()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton for test isolation."""
        cls._instance = None

    def get_velocity_limits(self, follower_name: Optional[str] = None) -> MockVelocityLimits:
        """Get velocity limits, optionally with follower-specific overrides."""
        if follower_name and follower_name in self._follower_overrides:
            overrides = self._follower_overrides[follower_name]
            return MockVelocityLimits(
                forward=overrides.get('MAX_VELOCITY_FORWARD', self.velocity_limits.forward),
                lateral=overrides.get('MAX_VELOCITY_LATERAL', self.velocity_limits.lateral),
                vertical=overrides.get('MAX_VELOCITY_VERTICAL', self.velocity_limits.vertical),
                min_forward=self.velocity_limits.min_forward,
                default_forward=self.velocity_limits.default_forward,
                max_magnitude=self.velocity_limits.max_magnitude
            )
        return self.velocity_limits

    def get_altitude_limits(self, follower_name: Optional[str] = None) -> MockAltitudeLimits:
        """Get altitude limits."""
        return self.altitude_limits

    def get_rate_limits(self, follower_name: Optional[str] = None) -> MockRateLimits:
        """Get rate limits in rad/s."""
        return self.rate_limits

    def check_altitude_safety(self, altitude: float, follower_name: Optional[str] = None) -> bool:
        """
        Check if altitude is within safety limits.

        Returns:
            bool: True if safe, False if violation
        """
        self._altitude_checks.append(altitude)
        limits = self.altitude_limits

        if altitude < limits.min_altitude or altitude > limits.max_altitude:
            self._safety_violations += 1
            return False
        return True

    def set_follower_override(self, follower_name: str, overrides: Dict[str, Any]) -> None:
        """Set follower-specific limit overrides."""
        self._follower_overrides[follower_name] = overrides

    def clear_overrides(self) -> None:
        """Clear all follower overrides."""
        self._follower_overrides.clear()

    @property
    def safety_violations(self) -> int:
        """Get count of safety violations."""
        return self._safety_violations

    def reset_tracking(self) -> None:
        """Reset tracking counters."""
        self._altitude_checks.clear()
        self._safety_violations = 0


def create_test_safety_config() -> Dict[str, Any]:
    """
    Create a test safety configuration dictionary.

    Returns:
        Dict matching the structure expected by SafetyManager.load_from_config()
    """
    return {
        'Safety': {
            'GlobalLimits': {
                'MAX_VELOCITY_FORWARD': 10.0,
                'MAX_VELOCITY_LATERAL': 5.0,
                'MAX_VELOCITY_VERTICAL': 3.0,
                'MIN_VELOCITY_FORWARD': 0.0,
                'DEFAULT_VELOCITY_FORWARD': 5.0,
                'MAX_YAW_RATE': 45.0,
                'MAX_PITCH_RATE': 30.0,
                'MAX_ROLL_RATE': 60.0,
                'MIN_ALTITUDE': 5.0,
                'MAX_ALTITUDE': 120.0,
                'ALTITUDE_WARNING_BUFFER': 5.0,
                'USE_HOME_RELATIVE_ALTITUDE': True
            },
            'FollowerOverrides': {
                'MC_VELOCITY_CHASE': {
                    'MAX_VELOCITY_FORWARD': 12.0,
                    'MAX_VELOCITY_VERTICAL': 4.0
                },
                'FW_ATTITUDE_RATE': {
                    'MAX_VELOCITY_FORWARD': 30.0
                }
            }
        }
    }


def create_mock_safety_manager() -> MagicMock:
    """
    Create a MagicMock configured as SafetyManager.

    Useful for patching when full MockSafetyManager isn't needed.
    """
    mock = MagicMock()
    mock.get_velocity_limits.return_value = MockVelocityLimits()
    mock.get_altitude_limits.return_value = MockAltitudeLimits()
    mock.get_rate_limits.return_value = MockRateLimits()
    mock.check_altitude_safety.return_value = True
    return mock


# Tests consume the canonical command contract rather than maintaining a second
# profile/field/dispatch catalog that can drift from production.
_FOLLOWER_COMMAND_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / 'configs' / 'follower_commands.yaml'
)
TEST_SCHEMA_CACHE = yaml.safe_load(
    _FOLLOWER_COMMAND_SCHEMA_PATH.read_text(encoding='utf-8')
)
