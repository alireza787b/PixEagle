# tests/integration/test_follower_factory.py
"""
Integration tests for FollowerFactory.

Tests the follower factory pattern including:
- Registry initialization
- Available modes listing
- Follower creation
- Deprecated alias handling
- Profile validation
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_px4_controller():
    """Create a mock PX4Controller."""
    mock = MagicMock()
    mock.current_altitude = 50.0
    mock.current_pitch = 0.0
    mock.current_roll = 0.0
    mock.current_yaw = 0.0
    mock.current_airspeed = 18.0
    mock.setpoint_handler = None
    return mock


@pytest.fixture
def reset_factory():
    """Reset FollowerFactory registry before and after each test."""
    from classes.follower import FollowerFactory
    FollowerFactory._registry_initialized = False
    yield
    FollowerFactory._registry_initialized = False


# =============================================================================
# Test: Registry Initialization
# =============================================================================

class TestRegistryInitialization:
    """Test follower registry initialization."""

    @pytest.mark.integration
    def test_registry_initializes_on_first_access(self, reset_factory):
        """Registry initializes on first access."""
        from classes.follower import FollowerFactory

        assert FollowerFactory._registry_initialized is False
        FollowerFactory._initialize_registry()
        assert FollowerFactory._registry_initialized is True

    @pytest.mark.integration
    def test_registry_not_reinitialized(self, reset_factory):
        """Registry not reinitialized on subsequent access."""
        from classes.follower import FollowerFactory

        FollowerFactory._initialize_registry()
        initial_registry = FollowerFactory._follower_registry.copy()

        FollowerFactory._initialize_registry()

        assert FollowerFactory._follower_registry == initial_registry

    @pytest.mark.integration
    def test_registry_contains_expected_followers(self, reset_factory):
        """Registry contains expected follower implementations."""
        from classes.follower import FollowerFactory

        FollowerFactory._initialize_registry()

        expected_profiles = [
            'mc_velocity',
            'mc_velocity_chase',
            'mc_velocity_position',
            'mc_velocity_distance',
            'mc_velocity_ground',
            'mc_attitude_rate',
            'fw_attitude_rate',
            'gm_velocity_vector',
            'gm_pid_pursuit',
        ]

        for profile in expected_profiles:
            assert profile in FollowerFactory._follower_registry, \
                f"Missing profile: {profile}"


# =============================================================================
# Test: Available Modes
# =============================================================================

class TestAvailableModes:
    """Test available modes listing."""

    @pytest.mark.integration
    def test_get_available_modes_returns_list(self, reset_factory):
        """get_available_modes returns a list."""
        from classes.follower import FollowerFactory

        modes = FollowerFactory.get_available_modes()
        assert isinstance(modes, list)

    @pytest.mark.integration
    def test_available_modes_excludes_deprecated(self, reset_factory):
        """Available modes excludes deprecated aliases."""
        from classes.follower import FollowerFactory

        modes = FollowerFactory.get_available_modes()

        # Deprecated aliases should not be in the list
        for deprecated in FollowerFactory._deprecated_aliases.keys():
            assert deprecated not in modes, \
                f"Deprecated alias should not be in available modes: {deprecated}"

    @pytest.mark.integration
    def test_available_modes_not_empty(self, reset_factory):
        """Available modes list is not empty."""
        from classes.follower import FollowerFactory

        modes = FollowerFactory.get_available_modes()
        assert len(modes) > 0


# =============================================================================
# Test: Deprecated Alias Handling
# =============================================================================

class TestDeprecatedAliasHandling:
    """Test deprecated alias handling."""

    @pytest.mark.integration
    def test_deprecated_aliases_mapped(self, reset_factory):
        """Deprecated aliases are mapped to new implementations."""
        from classes.follower import FollowerFactory

        FollowerFactory._initialize_registry()

        # Check that aliases point to the same class as the new name
        for old_name, new_name in FollowerFactory._deprecated_aliases.items():
            if new_name in FollowerFactory._follower_registry:
                assert old_name in FollowerFactory._follower_registry
                assert FollowerFactory._follower_registry[old_name] == \
                       FollowerFactory._follower_registry[new_name]

    @pytest.mark.integration
    def test_deprecated_alias_count(self, reset_factory):
        """Expected number of deprecated aliases."""
        from classes.follower import FollowerFactory

        # Should have aliases for legacy naming
        assert len(FollowerFactory._deprecated_aliases) > 0


# =============================================================================
# Test: Profile Info
# =============================================================================

class TestFollowerInfo:
    """Test follower info retrieval."""

    @pytest.mark.integration
    def test_get_follower_info_returns_dict(self, reset_factory):
        """get_follower_info returns a dictionary."""
        from classes.follower import FollowerFactory

        info = FollowerFactory.get_follower_info('mc_velocity')
        assert isinstance(info, dict)

    @pytest.mark.integration
    def test_follower_info_has_implementation_available(self, reset_factory):
        """Follower info has implementation_available field."""
        from classes.follower import FollowerFactory

        info = FollowerFactory.get_follower_info('mc_velocity')
        assert 'implementation_available' in info

    @pytest.mark.integration
    def test_follower_info_for_known_profile(self, reset_factory):
        """Follower info for known profile shows available."""
        from classes.follower import FollowerFactory

        info = FollowerFactory.get_follower_info('mc_velocity_chase')
        assert info.get('implementation_available') is True
        assert info.get('implementation_class') is not None


# =============================================================================
# Test: Follower Creation
# =============================================================================

class TestFollowerCreation:
    """Test follower instance creation."""

    @pytest.mark.integration
    def test_create_known_follower(self, reset_factory, mock_px4_controller):
        """Creating a known follower succeeds."""
        from classes.follower import FollowerFactory

        try:
            follower = FollowerFactory.create_follower(
                'mc_velocity',
                mock_px4_controller,
                (0.0, 0.0)
            )
            assert follower is not None
        except Exception as e:
            # May fail due to missing schema files in test environment
            if 'schema' in str(e).lower() or 'profile' in str(e).lower():
                pytest.skip(f"Schema not available in test environment: {e}")
            raise

    @pytest.mark.integration
    def test_create_unknown_follower_raises(self, reset_factory, mock_px4_controller):
        """Creating unknown follower raises ValueError."""
        from classes.follower import FollowerFactory

        with pytest.raises(ValueError) as exc_info:
            FollowerFactory.create_follower(
                'nonexistent_profile',
                mock_px4_controller,
                (0.0, 0.0)
            )

        assert 'nonexistent_profile' in str(exc_info.value).lower() or \
               'not found' in str(exc_info.value).lower() or \
               'available' in str(exc_info.value).lower()

    @pytest.mark.integration
    def test_normalized_profile_name(self, reset_factory):
        """Profile names are normalized (lowercase, underscores)."""
        from classes.follower import FollowerFactory

        FollowerFactory._initialize_registry()

        # All keys should be lowercase with underscores
        for profile_name in FollowerFactory._follower_registry.keys():
            if profile_name not in FollowerFactory._deprecated_aliases:
                assert profile_name == profile_name.lower()
                assert ' ' not in profile_name


# =============================================================================
# Test: Follower Class Registration
# =============================================================================

class TestFollowerClassRegistration:
    """Test follower class types in registry."""

    @pytest.mark.integration
    def test_mc_velocity_class(self, reset_factory):
        """MC Velocity class is registered."""
        from classes.follower import FollowerFactory
        from classes.followers.mc_velocity_follower import MCVelocityFollower

        FollowerFactory._initialize_registry()

        assert FollowerFactory._follower_registry.get('mc_velocity') == MCVelocityFollower

    @pytest.mark.integration
    def test_mc_velocity_chase_class(self, reset_factory):
        """MC Velocity Chase class is registered."""
        from classes.follower import FollowerFactory
        from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower

        FollowerFactory._initialize_registry()

        assert FollowerFactory._follower_registry.get('mc_velocity_chase') == MCVelocityChaseFollower

    @pytest.mark.integration
    def test_fw_attitude_rate_class(self, reset_factory):
        """FW Attitude Rate class is registered."""
        from classes.follower import FollowerFactory
        from classes.followers.fw_attitude_rate_follower import FWAttitudeRateFollower

        FollowerFactory._initialize_registry()

        assert FollowerFactory._follower_registry.get('fw_attitude_rate') == FWAttitudeRateFollower

    @pytest.mark.integration
    def test_gm_pid_pursuit_class(self, reset_factory):
        """GM PID Pursuit class is registered."""
        from classes.follower import FollowerFactory
        from classes.followers.gm_pid_pursuit_follower import GMPIDPursuitFollower

        FollowerFactory._initialize_registry()

        assert FollowerFactory._follower_registry.get('gm_pid_pursuit') == GMPIDPursuitFollower

    @pytest.mark.integration
    def test_gm_velocity_vector_class(self, reset_factory):
        """GM Velocity Vector class is registered."""
        from classes.follower import FollowerFactory
        from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower

        FollowerFactory._initialize_registry()

        assert FollowerFactory._follower_registry.get('gm_velocity_vector') == GMVelocityVectorFollower
