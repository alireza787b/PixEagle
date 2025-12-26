# tests/conftest.py
"""
Root pytest configuration and fixtures for PixEagle testing.

Provides shared fixtures for mock infrastructure, schema caching,
and test isolation. All fixtures here are available to all test modules.
"""

import pytest
import sys
import os
from typing import Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tests.fixtures.mock_px4 import MockPX4Controller, MockAttitude
from tests.fixtures.mock_tracker import TrackerOutputFactory
from tests.fixtures.mock_safety import (
    MockSafetyManager,
    MockVelocityLimits,
    MockAltitudeLimits,
    MockRateLimits,
    create_test_safety_config,
    create_mock_safety_manager,
    TEST_SCHEMA_CACHE
)


# =============================================================================
# PX4 Controller Fixtures
# =============================================================================

@pytest.fixture
def mock_px4():
    """
    Create a MockPX4Controller with default telemetry values.

    Default state:
        - Altitude: 50m
        - Attitude: level (pitch=0, roll=0, yaw=0)
        - Airspeed: 18 m/s

    Usage:
        def test_something(mock_px4):
            mock_px4.set_altitude(100.0)
            # ... test code
    """
    controller = MockPX4Controller()
    yield controller
    controller.clear_commands()


@pytest.fixture
def mock_px4_low_altitude():
    """Create MockPX4Controller at minimum safe altitude."""
    return MockPX4Controller(altitude=5.0)


@pytest.fixture
def mock_px4_high_altitude():
    """Create MockPX4Controller at high altitude."""
    return MockPX4Controller(altitude=100.0)


@pytest.fixture
def mock_px4_banked():
    """Create MockPX4Controller in a banked turn (30 deg roll)."""
    import math
    return MockPX4Controller(roll=math.radians(30))


@pytest.fixture
def mock_px4_pitched():
    """Create MockPX4Controller with nose-down pitch (10 deg)."""
    import math
    return MockPX4Controller(pitch=math.radians(-10))


# =============================================================================
# Tracker Output Fixtures
# =============================================================================

@pytest.fixture
def tracker_factory():
    """
    Factory for creating TrackerOutput test instances.

    Provides static methods for common test scenarios.

    Usage:
        def test_tracking(tracker_factory):
            output = tracker_factory.centered()
            # ... test code
    """
    return TrackerOutputFactory


@pytest.fixture
def tracker_centered():
    """TrackerOutput with target at image center."""
    return TrackerOutputFactory.centered()


@pytest.fixture
def tracker_offset_right():
    """TrackerOutput with target offset to the right."""
    return TrackerOutputFactory.offset(0.5, 0.0)


@pytest.fixture
def tracker_offset_left():
    """TrackerOutput with target offset to the left."""
    return TrackerOutputFactory.offset(-0.5, 0.0)


@pytest.fixture
def tracker_offset_up():
    """TrackerOutput with target offset upward."""
    return TrackerOutputFactory.offset(0.0, -0.5)


@pytest.fixture
def tracker_offset_down():
    """TrackerOutput with target offset downward."""
    return TrackerOutputFactory.offset(0.0, 0.5)


@pytest.fixture
def tracker_lost():
    """TrackerOutput for lost target scenario."""
    return TrackerOutputFactory.lost()


@pytest.fixture
def tracker_low_confidence():
    """TrackerOutput with low tracking confidence."""
    return TrackerOutputFactory.low_confidence()


@pytest.fixture
def tracker_3d():
    """TrackerOutput with 3D position data."""
    return TrackerOutputFactory.position_3d(0.0, 0.0, 15.0)


@pytest.fixture
def tracker_gimbal():
    """TrackerOutput with gimbal angle data."""
    return TrackerOutputFactory.gimbal_angles(pan=10.0, tilt=-5.0)


# =============================================================================
# Safety Manager Fixtures
# =============================================================================

@pytest.fixture
def mock_safety_manager():
    """
    Create a fresh MockSafetyManager instance.

    Resets the singleton to ensure test isolation.

    Usage:
        def test_safety(mock_safety_manager):
            limits = mock_safety_manager.get_velocity_limits()
            # ... test code
    """
    MockSafetyManager.reset_instance()
    manager = MockSafetyManager.get_instance()
    yield manager
    MockSafetyManager.reset_instance()


@pytest.fixture
def safety_config():
    """
    Get test safety configuration dictionary.

    Returns a config structure matching SafetyManager.load_from_config().
    """
    return create_test_safety_config()


@pytest.fixture
def mock_velocity_limits():
    """Default velocity limits for testing."""
    return MockVelocityLimits()


@pytest.fixture
def mock_altitude_limits():
    """Default altitude limits for testing."""
    return MockAltitudeLimits()


@pytest.fixture
def mock_rate_limits():
    """Default rate limits for testing."""
    return MockRateLimits()


# =============================================================================
# Schema Cache Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def setup_schema_cache(monkeypatch):
    """
    Pre-populate SetpointHandler schema cache to avoid file I/O.

    This fixture runs automatically for all tests, ensuring
    SetpointHandler doesn't try to read YAML files during tests.
    """
    # Patch at module level where SetpointHandler might be imported
    try:
        from classes.setpoint_handler import SetpointHandler
        monkeypatch.setattr(
            SetpointHandler,
            '_schema_cache',
            TEST_SCHEMA_CACHE.copy(),
            raising=False
        )
    except ImportError:
        # SetpointHandler not available, skip patching
        pass


@pytest.fixture
def schema_cache():
    """Get a copy of the test schema cache."""
    return TEST_SCHEMA_CACHE.copy()


# =============================================================================
# PID Controller Fixtures
# =============================================================================

@pytest.fixture
def pid_gains():
    """Default PID gains for testing."""
    return {'Kp': 1.0, 'Ki': 0.1, 'Kd': 0.05}


@pytest.fixture
def aggressive_pid_gains():
    """Aggressive PID gains for testing responsive behavior."""
    return {'Kp': 2.5, 'Ki': 0.5, 'Kd': 0.1}


@pytest.fixture
def conservative_pid_gains():
    """Conservative PID gains for testing stable behavior."""
    return {'Kp': 0.5, 'Ki': 0.05, 'Kd': 0.02}


# =============================================================================
# Follower Configuration Fixtures
# =============================================================================

@pytest.fixture
def mc_velocity_config():
    """Configuration for MC Velocity follower testing."""
    return {
        'Follower': {
            'PROFILE': 'mc_velocity',
            'GAINS': {
                'YAW_KP': 30.0,
                'YAW_KI': 0.5,
                'YAW_KD': 0.1,
                'VERTICAL_KP': 2.0,
                'VERTICAL_KI': 0.1,
                'VERTICAL_KD': 0.05
            }
        }
    }


@pytest.fixture
def mc_velocity_chase_config():
    """Configuration for MC Velocity Chase follower testing."""
    return {
        'Follower': {
            'PROFILE': 'mc_velocity_chase',
            'GAINS': {
                'YAW_KP': 35.0,
                'YAW_KI': 0.3,
                'YAW_KD': 0.08,
                'VERTICAL_KP': 2.5,
                'VERTICAL_KI': 0.15,
                'VERTICAL_KD': 0.05,
                'FORWARD_KP': 3.0,
                'FORWARD_KI': 0.1,
                'FORWARD_KD': 0.05
            },
            'FORWARD_RAMPING': {
                'RAMP_UP_RATE': 2.0,
                'RAMP_DOWN_RATE': 3.0,
                'MIN_TRACKING_CONFIDENCE': 0.7
            }
        }
    }


@pytest.fixture
def fw_attitude_rate_config():
    """Configuration for FW Attitude Rate follower testing."""
    return {
        'Follower': {
            'PROFILE': 'fw_attitude_rate',
            'L1_GUIDANCE': {
                'L1_PERIOD': 20.0,
                'L1_DAMPING': 0.75,
                'MIN_L1_DISTANCE': 30.0,
                'MAX_L1_DISTANCE': 200.0
            },
            'TECS': {
                'CRUISE_THROTTLE': 0.6,
                'MIN_THROTTLE': 0.1,
                'MAX_THROTTLE': 1.0,
                'PITCH_SPEED_WEIGHT': 1.0,
                'SPEED_WEIGHT': 2.0
            },
            'BANK_LIMITS': {
                'MAX_BANK_ANGLE': 45.0,
                'LOAD_FACTOR_LIMIT': 2.5
            }
        }
    }


# =============================================================================
# Async Testing Utilities
# =============================================================================

@pytest.fixture
def event_loop_policy():
    """Get the default event loop policy for async tests."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


# =============================================================================
# Test Isolation Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def isolate_singletons():
    """
    Reset all singletons before each test to ensure isolation.

    This runs automatically for all tests.
    """
    # Reset SafetyManager singleton
    MockSafetyManager.reset_instance()

    yield

    # Cleanup after test
    MockSafetyManager.reset_instance()


@pytest.fixture
def temp_config_file(tmp_path):
    """
    Create a temporary config file for testing.

    Usage:
        def test_config_loading(temp_config_file):
            config_path = temp_config_file({'key': 'value'})
            # ... test code
    """
    import yaml

    def _create_config(content: Dict[str, Any]) -> str:
        config_file = tmp_path / "test_config.yaml"
        with open(config_file, 'w') as f:
            yaml.safe_dump(content, f)
        return str(config_file)

    return _create_config


# =============================================================================
# Assertion Helpers
# =============================================================================

@pytest.fixture
def assert_velocity_clamped():
    """
    Fixture providing velocity clamping assertion helper.

    Usage:
        def test_velocity(assert_velocity_clamped):
            assert_velocity_clamped(vel, max_vel=10.0)
    """
    def _assert(velocity: float, max_vel: float, min_vel: float = 0.0):
        assert min_vel <= velocity <= max_vel, \
            f"Velocity {velocity} not in range [{min_vel}, {max_vel}]"
    return _assert


@pytest.fixture
def assert_angle_normalized():
    """
    Fixture providing angle normalization assertion helper.

    Checks that angle is within [-180, 180] degrees or [-pi, pi] radians.
    """
    import math

    def _assert(angle: float, use_radians: bool = False):
        limit = math.pi if use_radians else 180.0
        assert -limit <= angle <= limit, \
            f"Angle {angle} not normalized to [{-limit}, {limit}]"
    return _assert


@pytest.fixture
def assert_commands_sent(mock_px4):
    """
    Fixture providing command verification helper.

    Usage:
        def test_commands(mock_px4, assert_commands_sent):
            # ... trigger commands
            assert_commands_sent('velocity_body_offboard', count=1)
    """
    def _assert(command_type: str, count: int = None, min_count: int = None):
        commands = mock_px4.get_commands_of_type(command_type)
        if count is not None:
            assert len(commands) == count, \
                f"Expected {count} {command_type} commands, got {len(commands)}"
        if min_count is not None:
            assert len(commands) >= min_count, \
                f"Expected at least {min_count} {command_type} commands, got {len(commands)}"
    return _assert
