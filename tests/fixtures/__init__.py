# tests/fixtures/__init__.py
"""
Test fixtures package for PixEagle follower testing.

Provides reusable mocks, factories, and test utilities.
"""

from tests.fixtures.mock_px4 import MockPX4Controller
from tests.fixtures.mock_tracker import TrackerOutputFactory
from tests.fixtures.mock_safety import MockSafetyManager, create_test_safety_config

__all__ = [
    'MockPX4Controller',
    'TrackerOutputFactory',
    'MockSafetyManager',
    'create_test_safety_config',
]
