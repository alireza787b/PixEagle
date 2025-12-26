# tests/fixtures/mock_mavsdk.py
"""
Mock MAVSDK System for testing PX4InterfaceManager.

Provides comprehensive mock implementations of MAVSDK's System class
and its components (Offboard, Telemetry, Action) for unit testing
without requiring actual drone connections.
"""

import asyncio
import time
from typing import Optional, List, Dict, Any, Callable, AsyncIterator
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock
from enum import Enum


# ============================================================================
# Mock Data Structures (matching MAVSDK types)
# ============================================================================

@dataclass
class MockPosition:
    """Mock position data."""
    latitude_deg: float = 47.3977419
    longitude_deg: float = 8.5455938
    absolute_altitude_m: float = 488.0
    relative_altitude_m: float = 50.0


@dataclass
class MockEulerAngle:
    """Mock Euler angle data (all in degrees)."""
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    timestamp_us: int = field(default_factory=lambda: int(time.time() * 1e6))


@dataclass
class MockVelocityBody:
    """Mock body-frame velocity."""
    forward_m_s: float = 0.0
    right_m_s: float = 0.0
    down_m_s: float = 0.0


@dataclass
class MockVelocityNed:
    """Mock NED-frame velocity."""
    north_m_s: float = 0.0
    east_m_s: float = 0.0
    down_m_s: float = 0.0


@dataclass
class MockBattery:
    """Mock battery status."""
    remaining_percent: float = 100.0
    voltage_v: float = 16.8


class MockFlightMode(Enum):
    """Mock flight modes matching PX4."""
    UNKNOWN = 0
    READY = 1
    TAKEOFF = 2
    HOLD = 3
    MISSION = 4
    RETURN_TO_LAUNCH = 5
    LAND = 6
    OFFBOARD = 7
    FOLLOW_ME = 8
    MANUAL = 9
    ALTCTL = 10
    POSCTL = 11
    ACRO = 12
    STABILIZED = 13


@dataclass
class MockHealth:
    """Mock system health."""
    is_gyrometer_calibration_ok: bool = True
    is_accelerometer_calibration_ok: bool = True
    is_magnetometer_calibration_ok: bool = True
    is_local_position_ok: bool = True
    is_global_position_ok: bool = True
    is_home_position_ok: bool = True
    is_armable: bool = True


@dataclass
class MockVelocityBodyYawspeed:
    """Mock VelocityBodyYawspeed for offboard commands."""
    forward_m_s: float = 0.0
    right_m_s: float = 0.0
    down_m_s: float = 0.0
    yawspeed_deg_s: float = 0.0


@dataclass
class MockAttitudeRate:
    """Mock AttitudeRate for offboard commands."""
    roll_rate_deg_s: float = 0.0
    pitch_rate_deg_s: float = 0.0
    yaw_rate_deg_s: float = 0.0
    thrust_value: float = 0.5


@dataclass
class CommandRecord:
    """Record of a command sent for verification."""
    command_type: str
    values: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


# ============================================================================
# Mock Offboard Component
# ============================================================================

class MockOffboard:
    """
    Mock MAVSDK Offboard interface for testing.

    Simulates offboard control with command tracking.
    """

    def __init__(self):
        self._is_active = False
        self._commands_sent: List[CommandRecord] = []
        self._start_count = 0
        self._stop_count = 0
        self._should_fail_start = False
        self._should_fail_command = False
        self._error_message = "Mock offboard error"

    async def start(self) -> None:
        """Start offboard mode."""
        if self._should_fail_start:
            from mavsdk.offboard import OffboardError
            raise OffboardError(None, self._error_message)
        self._is_active = True
        self._start_count += 1

    async def stop(self) -> None:
        """Stop offboard mode."""
        self._is_active = False
        self._stop_count += 1

    async def set_velocity_body(self, velocity: MockVelocityBodyYawspeed) -> None:
        """Set body-frame velocity setpoint."""
        if self._should_fail_command:
            from mavsdk.offboard import OffboardError
            raise OffboardError(None, self._error_message)

        self._commands_sent.append(CommandRecord(
            command_type='velocity_body',
            values={
                'forward_m_s': velocity.forward_m_s,
                'right_m_s': velocity.right_m_s,
                'down_m_s': velocity.down_m_s,
                'yawspeed_deg_s': velocity.yawspeed_deg_s
            }
        ))

    async def set_attitude_rate(self, attitude: MockAttitudeRate) -> None:
        """Set attitude rate setpoint."""
        if self._should_fail_command:
            from mavsdk.offboard import OffboardError
            raise OffboardError(None, self._error_message)

        self._commands_sent.append(CommandRecord(
            command_type='attitude_rate',
            values={
                'roll_rate_deg_s': attitude.roll_rate_deg_s,
                'pitch_rate_deg_s': attitude.pitch_rate_deg_s,
                'yaw_rate_deg_s': attitude.yaw_rate_deg_s,
                'thrust_value': attitude.thrust_value
            }
        ))

    async def set_velocity_ned(self, velocity) -> None:
        """Set NED-frame velocity setpoint."""
        self._commands_sent.append(CommandRecord(
            command_type='velocity_ned',
            values={
                'north_m_s': velocity.north_m_s,
                'east_m_s': velocity.east_m_s,
                'down_m_s': velocity.down_m_s,
                'yaw_deg': getattr(velocity, 'yaw_deg', 0.0)
            }
        ))

    # Test helper methods
    @property
    def is_active(self) -> bool:
        """Check if offboard is active."""
        return self._is_active

    def get_commands(self) -> List[CommandRecord]:
        """Get all commands sent."""
        return self._commands_sent.copy()

    def get_last_command(self) -> Optional[CommandRecord]:
        """Get most recent command."""
        return self._commands_sent[-1] if self._commands_sent else None

    def get_commands_of_type(self, command_type: str) -> List[CommandRecord]:
        """Get commands of specific type."""
        return [cmd for cmd in self._commands_sent if cmd.command_type == command_type]

    def clear_commands(self) -> None:
        """Clear command history."""
        self._commands_sent.clear()

    def set_fail_start(self, should_fail: bool, message: str = "Mock start error") -> None:
        """Configure start to fail."""
        self._should_fail_start = should_fail
        self._error_message = message

    def set_fail_command(self, should_fail: bool, message: str = "Mock command error") -> None:
        """Configure commands to fail."""
        self._should_fail_command = should_fail
        self._error_message = message


# ============================================================================
# Mock Telemetry Component
# ============================================================================

class MockTelemetry:
    """
    Mock MAVSDK Telemetry interface for testing.

    Provides async generators for telemetry streams.
    """

    def __init__(self):
        # Telemetry state
        self._position = MockPosition()
        self._attitude = MockEulerAngle()
        self._velocity_body = MockVelocityBody()
        self._velocity_ned = MockVelocityNed()
        self._battery = MockBattery()
        self._flight_mode = MockFlightMode.OFFBOARD
        self._health = MockHealth()
        self._armed = False
        self._in_air = False

        # Stream control
        self._stream_interval = 0.1  # seconds
        self._streams_running = True

    async def position(self) -> AsyncIterator[MockPosition]:
        """Stream position updates."""
        while self._streams_running:
            yield self._position
            await asyncio.sleep(self._stream_interval)

    async def attitude_euler(self) -> AsyncIterator[MockEulerAngle]:
        """Stream attitude updates."""
        while self._streams_running:
            yield self._attitude
            await asyncio.sleep(self._stream_interval)

    async def velocity_body(self) -> AsyncIterator[MockVelocityBody]:
        """Stream body velocity updates."""
        while self._streams_running:
            yield self._velocity_body
            await asyncio.sleep(self._stream_interval)

    async def velocity_ned(self) -> AsyncIterator[MockVelocityNed]:
        """Stream NED velocity updates."""
        while self._streams_running:
            yield self._velocity_ned
            await asyncio.sleep(self._stream_interval)

    async def battery(self) -> AsyncIterator[MockBattery]:
        """Stream battery updates."""
        while self._streams_running:
            yield self._battery
            await asyncio.sleep(self._stream_interval)

    async def flight_mode(self) -> AsyncIterator[MockFlightMode]:
        """Stream flight mode updates."""
        while self._streams_running:
            yield self._flight_mode
            await asyncio.sleep(self._stream_interval)

    async def health(self) -> AsyncIterator[MockHealth]:
        """Stream health updates."""
        while self._streams_running:
            yield self._health
            await asyncio.sleep(self._stream_interval)

    async def armed(self) -> AsyncIterator[bool]:
        """Stream armed state."""
        while self._streams_running:
            yield self._armed
            await asyncio.sleep(self._stream_interval)

    async def in_air(self) -> AsyncIterator[bool]:
        """Stream in-air state."""
        while self._streams_running:
            yield self._in_air
            await asyncio.sleep(self._stream_interval)

    # Test helper methods
    def set_position(
        self,
        lat: float = None,
        lon: float = None,
        abs_alt: float = None,
        rel_alt: float = None
    ) -> None:
        """Set position data."""
        if lat is not None:
            self._position.latitude_deg = lat
        if lon is not None:
            self._position.longitude_deg = lon
        if abs_alt is not None:
            self._position.absolute_altitude_m = abs_alt
        if rel_alt is not None:
            self._position.relative_altitude_m = rel_alt

    def set_attitude(
        self,
        roll_deg: float = None,
        pitch_deg: float = None,
        yaw_deg: float = None
    ) -> None:
        """Set attitude data."""
        if roll_deg is not None:
            self._attitude.roll_deg = roll_deg
        if pitch_deg is not None:
            self._attitude.pitch_deg = pitch_deg
        if yaw_deg is not None:
            self._attitude.yaw_deg = yaw_deg

    def set_velocity_body(
        self,
        forward: float = None,
        right: float = None,
        down: float = None
    ) -> None:
        """Set body velocity data."""
        if forward is not None:
            self._velocity_body.forward_m_s = forward
        if right is not None:
            self._velocity_body.right_m_s = right
        if down is not None:
            self._velocity_body.down_m_s = down

    def set_flight_mode(self, mode: MockFlightMode) -> None:
        """Set flight mode."""
        self._flight_mode = mode

    def set_armed(self, armed: bool) -> None:
        """Set armed state."""
        self._armed = armed

    def set_in_air(self, in_air: bool) -> None:
        """Set in-air state."""
        self._in_air = in_air

    def stop_streams(self) -> None:
        """Stop all telemetry streams."""
        self._streams_running = False


# ============================================================================
# Mock Action Component
# ============================================================================

class MockAction:
    """
    Mock MAVSDK Action interface for testing.

    Simulates drone actions (arm, takeoff, land, RTL).
    """

    def __init__(self):
        self._armed = False
        self._in_air = False
        self._action_history: List[str] = []
        self._should_fail = False
        self._error_message = "Mock action error"

    async def arm(self) -> None:
        """Arm the drone."""
        if self._should_fail:
            raise Exception(self._error_message)
        self._armed = True
        self._action_history.append('arm')

    async def disarm(self) -> None:
        """Disarm the drone."""
        if self._should_fail:
            raise Exception(self._error_message)
        self._armed = False
        self._action_history.append('disarm')

    async def takeoff(self) -> None:
        """Takeoff."""
        if self._should_fail:
            raise Exception(self._error_message)
        self._in_air = True
        self._action_history.append('takeoff')

    async def land(self) -> None:
        """Land."""
        if self._should_fail:
            raise Exception(self._error_message)
        self._in_air = False
        self._action_history.append('land')

    async def return_to_launch(self) -> None:
        """Return to launch."""
        if self._should_fail:
            raise Exception(self._error_message)
        self._action_history.append('return_to_launch')

    async def hold(self) -> None:
        """Hold position."""
        self._action_history.append('hold')

    async def kill(self) -> None:
        """Emergency kill."""
        self._armed = False
        self._action_history.append('kill')

    # Test helper methods
    @property
    def is_armed(self) -> bool:
        """Check if armed."""
        return self._armed

    @property
    def is_in_air(self) -> bool:
        """Check if in air."""
        return self._in_air

    def get_action_history(self) -> List[str]:
        """Get action history."""
        return self._action_history.copy()

    def clear_history(self) -> None:
        """Clear action history."""
        self._action_history.clear()

    def set_fail(self, should_fail: bool, message: str = "Mock action error") -> None:
        """Configure actions to fail."""
        self._should_fail = should_fail
        self._error_message = message


# ============================================================================
# Mock MAVSDK System
# ============================================================================

class MockMAVSDKSystem:
    """
    Mock MAVSDK System for testing PX4InterfaceManager.

    Provides mock implementations of all MAVSDK components needed
    for testing drone control logic.
    """

    def __init__(self, mavsdk_server_address: str = None, port: int = None):
        """
        Initialize mock MAVSDK System.

        Args:
            mavsdk_server_address: Ignored (for API compatibility)
            port: Ignored (for API compatibility)
        """
        self.offboard = MockOffboard()
        self.telemetry = MockTelemetry()
        self.action = MockAction()

        # Connection state
        self._connected = False
        self._system_address = None
        self._connect_count = 0
        self._should_fail_connect = False
        self._connect_delay = 0.0

    async def connect(self, system_address: str = "udp://:14540") -> None:
        """
        Simulate connection to drone.

        Args:
            system_address: System address (stored for verification)
        """
        if self._connect_delay > 0:
            await asyncio.sleep(self._connect_delay)

        if self._should_fail_connect:
            raise ConnectionError("Mock connection failed")

        self._system_address = system_address
        self._connected = True
        self._connect_count += 1

    async def disconnect(self) -> None:
        """Disconnect from drone."""
        self._connected = False
        self.telemetry.stop_streams()

    # Test helper methods
    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    @property
    def system_address(self) -> Optional[str]:
        """Get connected system address."""
        return self._system_address

    def set_fail_connect(self, should_fail: bool) -> None:
        """Configure connect to fail."""
        self._should_fail_connect = should_fail

    def set_connect_delay(self, delay: float) -> None:
        """Set connection delay for timeout testing."""
        self._connect_delay = delay

    def reset(self) -> None:
        """Reset all state for test isolation."""
        self.offboard = MockOffboard()
        self.telemetry = MockTelemetry()
        self.action = MockAction()
        self._connected = False
        self._system_address = None
        self._connect_count = 0
        self._should_fail_connect = False
        self._connect_delay = 0.0


# ============================================================================
# Factory Functions
# ============================================================================

def create_mock_mavsdk_system() -> MockMAVSDKSystem:
    """Create a new mock MAVSDK System."""
    return MockMAVSDKSystem()


def create_connected_mock_system(address: str = "udp://:14540") -> MockMAVSDKSystem:
    """Create a mock system in connected state."""
    system = MockMAVSDKSystem()
    system._connected = True
    system._system_address = address
    return system


def create_mock_system_with_telemetry(
    altitude: float = 50.0,
    roll: float = 0.0,
    pitch: float = 0.0,
    yaw: float = 0.0,
    armed: bool = True
) -> MockMAVSDKSystem:
    """
    Create mock system with preset telemetry values.

    Args:
        altitude: Relative altitude in meters
        roll: Roll angle in degrees
        pitch: Pitch angle in degrees
        yaw: Yaw angle in degrees
        armed: Armed state
    """
    system = create_connected_mock_system()
    system.telemetry.set_position(rel_alt=altitude)
    system.telemetry.set_attitude(roll_deg=roll, pitch_deg=pitch, yaw_deg=yaw)
    system.telemetry.set_armed(armed)
    return system


# ============================================================================
# Compatibility with mavsdk.offboard types
# ============================================================================

# These can be used when tests need the actual type names
VelocityBodyYawspeed = MockVelocityBodyYawspeed
AttitudeRate = MockAttitudeRate
