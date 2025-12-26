# tests/fixtures/mock_drone_interface.py
"""
Combined mock drone interface for integration testing.

Provides a unified mock that combines MAVSDK and MAVLink2REST mocks
for testing the complete drone interface stack.
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

from .mock_mavsdk import (
    MockMAVSDKSystem,
    MockOffboard,
    MockTelemetry,
    MockAction,
    MockFlightMode,
    CommandRecord,
    create_mock_mavsdk_system
)
from .mock_mavlink2rest import (
    MockMAVLink2RESTClient,
    MockRequestsSession,
    PX4FlightModes,
    create_mock_mavlink2rest_client
)


# ============================================================================
# Combined Drone Interface Mock
# ============================================================================

class MockDroneInterface:
    """
    Combined mock for complete drone interface testing.

    Provides coordinated MAVSDK and MAVLink2REST mocks with
    synchronized state for integration testing.
    """

    def __init__(
        self,
        altitude: float = 50.0,
        roll_deg: float = 0.0,
        pitch_deg: float = 0.0,
        yaw_deg: float = 0.0,
        ground_speed: float = 0.0,
        armed: bool = True,
        flight_mode: int = PX4FlightModes.OFFBOARD
    ):
        """
        Initialize combined mock interface.

        Args:
            altitude: Initial altitude in meters
            roll_deg: Initial roll in degrees
            pitch_deg: Initial pitch in degrees
            yaw_deg: Initial yaw in degrees
            ground_speed: Initial ground speed in m/s
            armed: Initial armed state
            flight_mode: Initial flight mode code
        """
        # Create individual mocks
        self.mavsdk = MockMAVSDKSystem()
        self.mavlink2rest = MockMAVLink2RESTClient()

        # Set initial state
        self._altitude = altitude
        self._roll_deg = roll_deg
        self._pitch_deg = pitch_deg
        self._yaw_deg = yaw_deg
        self._ground_speed = ground_speed
        self._armed = armed
        self._flight_mode = flight_mode

        # Synchronize initial state
        self._sync_state()

        # Connection state
        self._connected = False

        # Event callbacks
        self._on_command_sent: Optional[Callable] = None
        self._on_telemetry_update: Optional[Callable] = None

    def _sync_state(self) -> None:
        """Synchronize state between MAVSDK and MAVLink2REST mocks."""
        import math

        # MAVSDK telemetry
        self.mavsdk.telemetry.set_position(rel_alt=self._altitude)
        self.mavsdk.telemetry.set_attitude(
            roll_deg=self._roll_deg,
            pitch_deg=self._pitch_deg,
            yaw_deg=self._yaw_deg
        )
        self.mavsdk.telemetry.set_velocity_body(forward=self._ground_speed)
        self.mavsdk.telemetry.set_armed(self._armed)

        # MAVLink2REST data
        self.mavlink2rest.set_altitude(relative=self._altitude)
        self.mavlink2rest.set_attitude_degrees(
            roll_deg=self._roll_deg,
            pitch_deg=self._pitch_deg,
            yaw_deg=self._yaw_deg
        )
        self.mavlink2rest.set_ground_speed(self._ground_speed)
        self.mavlink2rest.set_armed(self._armed)
        self.mavlink2rest.set_flight_mode(self._flight_mode)

    async def connect(self) -> None:
        """Simulate connection to drone."""
        await self.mavsdk.connect()
        self.mavlink2rest.simulate_connection_restore()
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from drone."""
        await self.mavsdk.disconnect()
        self.mavlink2rest.simulate_connection_loss()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected and self.mavsdk.is_connected

    # ========================================================================
    # Unified State Setters
    # ========================================================================

    def set_altitude(self, altitude: float) -> None:
        """Set altitude (synced to both mocks)."""
        self._altitude = altitude
        self.mavsdk.telemetry.set_position(rel_alt=altitude)
        self.mavlink2rest.set_altitude(relative=altitude)

    def set_attitude(
        self,
        roll_deg: float = None,
        pitch_deg: float = None,
        yaw_deg: float = None
    ) -> None:
        """Set attitude in degrees (synced to both mocks)."""
        if roll_deg is not None:
            self._roll_deg = roll_deg
        if pitch_deg is not None:
            self._pitch_deg = pitch_deg
        if yaw_deg is not None:
            self._yaw_deg = yaw_deg

        self.mavsdk.telemetry.set_attitude(
            roll_deg=self._roll_deg,
            pitch_deg=self._pitch_deg,
            yaw_deg=self._yaw_deg
        )
        self.mavlink2rest.set_attitude_degrees(
            roll_deg=self._roll_deg,
            pitch_deg=self._pitch_deg,
            yaw_deg=self._yaw_deg
        )

    def set_ground_speed(self, speed: float) -> None:
        """Set ground speed (synced to both mocks)."""
        self._ground_speed = speed
        self.mavsdk.telemetry.set_velocity_body(forward=speed)
        self.mavlink2rest.set_ground_speed(speed)

    def set_armed(self, armed: bool) -> None:
        """Set armed state (synced to both mocks)."""
        self._armed = armed
        self.mavsdk.telemetry.set_armed(armed)
        self.mavlink2rest.set_armed(armed)

    def set_flight_mode(self, mode_code: int) -> None:
        """Set flight mode (MAVLink2REST only, MAVSDK uses enum)."""
        self._flight_mode = mode_code
        self.mavlink2rest.set_flight_mode(mode_code)

        # Map to MAVSDK enum
        mode_map = {
            PX4FlightModes.OFFBOARD: MockFlightMode.OFFBOARD,
            PX4FlightModes.POSITION: MockFlightMode.POSCTL,
            PX4FlightModes.STABILIZED: MockFlightMode.STABILIZED,
            PX4FlightModes.RETURN: MockFlightMode.RETURN_TO_LAUNCH,
            PX4FlightModes.HOLD: MockFlightMode.HOLD,
            PX4FlightModes.LAND: MockFlightMode.LAND,
            PX4FlightModes.MANUAL: MockFlightMode.MANUAL,
        }
        if mode_code in mode_map:
            self.mavsdk.telemetry.set_flight_mode(mode_map[mode_code])

    # ========================================================================
    # Scenario Simulation
    # ========================================================================

    def simulate_low_altitude(self, altitude: float = 2.0) -> None:
        """Simulate low altitude scenario."""
        self.set_altitude(altitude)

    def simulate_high_altitude(self, altitude: float = 130.0) -> None:
        """Simulate high altitude scenario."""
        self.set_altitude(altitude)

    def simulate_aggressive_maneuver(
        self,
        roll_deg: float = 30.0,
        pitch_deg: float = 20.0
    ) -> None:
        """Simulate aggressive maneuver with bank angle."""
        self.set_attitude(roll_deg=roll_deg, pitch_deg=pitch_deg)

    def simulate_high_speed(self, speed: float = 15.0) -> None:
        """Simulate high-speed flight."""
        self.set_ground_speed(speed)

    def simulate_hover(self) -> None:
        """Simulate hover (zero velocity, level attitude)."""
        self.set_ground_speed(0.0)
        self.set_attitude(roll_deg=0.0, pitch_deg=0.0)

    def simulate_offboard_exit(self) -> None:
        """Simulate exit from offboard mode (e.g., to Position)."""
        self.set_flight_mode(PX4FlightModes.POSITION)

    def simulate_rtl(self) -> None:
        """Simulate Return to Launch mode."""
        self.set_flight_mode(PX4FlightModes.RETURN)

    def simulate_emergency_land(self) -> None:
        """Simulate emergency landing."""
        self.set_flight_mode(PX4FlightModes.LAND)
        self.set_ground_speed(0.0)

    def simulate_disarm(self) -> None:
        """Simulate disarm."""
        self.set_armed(False)
        self.set_ground_speed(0.0)

    def simulate_connection_loss(self) -> None:
        """Simulate connection loss."""
        self.mavlink2rest.simulate_connection_loss()
        self.mavsdk._connected = False
        self._connected = False

    def simulate_connection_restore(self) -> None:
        """Simulate connection restore."""
        self.mavlink2rest.simulate_connection_restore()
        self.mavsdk._connected = True
        self._connected = True

    # ========================================================================
    # Command Tracking
    # ========================================================================

    def get_all_commands(self) -> List[CommandRecord]:
        """Get all commands sent via MAVSDK offboard."""
        return self.mavsdk.offboard.get_commands()

    def get_velocity_commands(self) -> List[CommandRecord]:
        """Get velocity body commands."""
        return self.mavsdk.offboard.get_commands_of_type('velocity_body')

    def get_attitude_commands(self) -> List[CommandRecord]:
        """Get attitude rate commands."""
        return self.mavsdk.offboard.get_commands_of_type('attitude_rate')

    def get_last_command(self) -> Optional[CommandRecord]:
        """Get most recent command."""
        return self.mavsdk.offboard.get_last_command()

    def clear_commands(self) -> None:
        """Clear command history."""
        self.mavsdk.offboard.clear_commands()

    def get_action_history(self) -> List[str]:
        """Get action history (arm, takeoff, land, RTL)."""
        return self.mavsdk.action.get_action_history()

    # ========================================================================
    # Request Tracking
    # ========================================================================

    def get_mavlink_request_count(self) -> int:
        """Get MAVLink2REST request count."""
        return self.mavlink2rest.get_request_count()

    def get_mavlink_request_history(self):
        """Get MAVLink2REST request history."""
        return self.mavlink2rest.get_request_history()

    def clear_request_history(self) -> None:
        """Clear request history."""
        self.mavlink2rest.clear_request_history()

    # ========================================================================
    # Test Utilities
    # ========================================================================

    def reset(self) -> None:
        """Reset all state for test isolation."""
        self.mavsdk.reset()
        self.mavlink2rest.reset()
        self._connected = False
        self._altitude = 50.0
        self._roll_deg = 0.0
        self._pitch_deg = 0.0
        self._yaw_deg = 0.0
        self._ground_speed = 0.0
        self._armed = True
        self._flight_mode = PX4FlightModes.OFFBOARD
        self._sync_state()

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Get current state snapshot for debugging."""
        return {
            'connected': self._connected,
            'altitude': self._altitude,
            'roll_deg': self._roll_deg,
            'pitch_deg': self._pitch_deg,
            'yaw_deg': self._yaw_deg,
            'ground_speed': self._ground_speed,
            'armed': self._armed,
            'flight_mode': self._flight_mode,
            'offboard_active': self.mavsdk.offboard.is_active,
            'commands_sent': len(self.get_all_commands()),
            'mavlink_requests': self.get_mavlink_request_count()
        }


# ============================================================================
# Mock SetpointHandler for Testing
# ============================================================================

class MockSetpointHandler:
    """
    Mock SetpointHandler for testing PX4InterfaceManager.

    Simulates the schema-driven setpoint handler without YAML dependencies.
    """

    def __init__(
        self,
        profile_name: str = "mc_velocity_offboard",
        control_type: str = "velocity_body_offboard"
    ):
        """
        Initialize mock setpoint handler.

        Args:
            profile_name: Follower profile name
            control_type: Control type (velocity_body, attitude_rate, etc.)
        """
        self._profile_name = profile_name
        self._control_type = control_type
        self._display_name = profile_name.replace("_", " ").title()

        # Field storage
        self._fields: Dict[str, float] = self._get_default_fields()

    def _get_default_fields(self) -> Dict[str, float]:
        """Get default fields based on control type."""
        if self._control_type == "velocity_body_offboard":
            return {
                'vel_body_fwd': 0.0,
                'vel_body_right': 0.0,
                'vel_body_down': 0.0,
                'yawspeed_deg_s': 0.0
            }
        elif self._control_type == "attitude_rate":
            return {
                'rollspeed_deg_s': 0.0,
                'pitchspeed_deg_s': 0.0,
                'yawspeed_deg_s': 0.0,
                'thrust': 0.5
            }
        elif self._control_type == "velocity_body":
            return {
                'vel_x': 0.0,
                'vel_y': 0.0,
                'vel_z': 0.0,
                'yaw_rate': 0.0
            }
        return {}

    def get_fields(self) -> Dict[str, float]:
        """Get current field values."""
        return self._fields.copy()

    def set_field(self, field_name: str, value: float) -> bool:
        """Set a field value."""
        if field_name in self._fields:
            self._fields[field_name] = float(value)
            return True
        return False

    def get_control_type(self) -> str:
        """Get control type."""
        return self._control_type

    def get_display_name(self) -> str:
        """Get display name."""
        return self._display_name

    def reset_setpoints(self) -> None:
        """Reset all fields to defaults."""
        self._fields = self._get_default_fields()

    def validate_profile_consistency(self) -> bool:
        """Validate profile consistency."""
        return True

    @staticmethod
    def normalize_profile_name(name: str) -> str:
        """Normalize profile name."""
        return name.lower().replace("-", "_").replace(" ", "_")


# ============================================================================
# Factory Functions
# ============================================================================

def create_mock_drone_interface(
    altitude: float = 50.0,
    roll_deg: float = 0.0,
    pitch_deg: float = 0.0,
    yaw_deg: float = 0.0,
    armed: bool = True
) -> MockDroneInterface:
    """Create a mock drone interface with initial state."""
    return MockDroneInterface(
        altitude=altitude,
        roll_deg=roll_deg,
        pitch_deg=pitch_deg,
        yaw_deg=yaw_deg,
        armed=armed
    )


def create_connected_drone_interface(**kwargs) -> MockDroneInterface:
    """Create a connected mock drone interface."""
    interface = MockDroneInterface(**kwargs)
    interface._connected = True
    interface.mavsdk._connected = True
    interface.mavlink2rest._connected = True
    return interface


def create_mock_setpoint_handler(
    control_type: str = "velocity_body_offboard"
) -> MockSetpointHandler:
    """Create a mock setpoint handler."""
    return MockSetpointHandler(control_type=control_type)


# ============================================================================
# Pytest Fixtures (importable)
# ============================================================================

def pytest_drone_interface_fixture():
    """
    Creates pytest fixture for drone interface.

    Usage in conftest.py:
        from tests.fixtures.mock_drone_interface import pytest_drone_interface_fixture
        mock_drone_interface = pytest_drone_interface_fixture()
    """
    import pytest

    @pytest.fixture
    def mock_drone_interface():
        """Create mock drone interface for testing."""
        interface = create_connected_drone_interface()
        yield interface
        interface.reset()

    return mock_drone_interface
