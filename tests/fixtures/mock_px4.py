# tests/fixtures/mock_px4.py
"""
Mock PX4 Controller for testing follower implementations.

Provides a lightweight mock that simulates PX4 telemetry and control
without requiring actual MAVSDK connections.
"""

from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field
from unittest.mock import AsyncMock
import time


@dataclass
class MockAttitude:
    """Mock attitude data."""
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    yaw_deg: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class CommandRecord:
    """Record of a sent command for verification."""
    command_type: str
    values: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class MockPX4Controller:
    """
    Lightweight mock PX4 controller for follower testing.

    Simulates telemetry data and records commands for verification.
    All async methods are implemented as AsyncMocks.

    Attributes:
        current_altitude: Simulated altitude (meters)
        current_pitch: Pitch angle (radians)
        current_roll: Roll angle (radians)
        current_yaw: Yaw angle (radians)
        current_airspeed: Airspeed (m/s)
        current_ground_speed: Ground speed (m/s)
    """

    def __init__(
        self,
        altitude: float = 50.0,
        pitch: float = 0.0,
        roll: float = 0.0,
        yaw: float = 0.0,
        airspeed: float = 18.0,
        ground_speed: float = 18.0
    ):
        # Telemetry state
        self.current_altitude = altitude
        self.current_pitch = pitch
        self.current_roll = roll
        self.current_yaw = yaw
        self.current_airspeed = airspeed
        self.current_ground_speed = ground_speed

        # Attitude object for compatibility
        self.attitude = MockAttitude(
            pitch_deg=pitch * 57.2958,
            roll_deg=roll * 57.2958,
            yaw_deg=yaw * 57.2958
        )
        self.attitude_timestamp = time.time()

        # SetpointHandler placeholder (set by follower)
        self.setpoint_handler = None

        # Command tracking
        self._commands_sent: List[CommandRecord] = []
        self._rtl_triggered: bool = False
        self._emergency_stop: bool = False

        # Async mocks for controller methods
        self.trigger_return_to_launch = AsyncMock(side_effect=self._on_rtl)
        self.send_velocity_body_offboard = AsyncMock(side_effect=self._on_velocity_cmd)
        self.send_attitude_rate = AsyncMock(side_effect=self._on_attitude_rate_cmd)
        self.connect = AsyncMock()
        self.disconnect = AsyncMock()

    async def _on_rtl(self) -> None:
        """Internal handler for RTL trigger."""
        self._rtl_triggered = True
        self._commands_sent.append(CommandRecord(
            command_type='rtl',
            values={}
        ))

    async def _on_velocity_cmd(
        self,
        vel_fwd: float = 0.0,
        vel_right: float = 0.0,
        vel_down: float = 0.0,
        yawspeed: float = 0.0
    ) -> None:
        """Internal handler for velocity commands."""
        self._commands_sent.append(CommandRecord(
            command_type='velocity_body_offboard',
            values={
                'vel_fwd': vel_fwd,
                'vel_right': vel_right,
                'vel_down': vel_down,
                'yawspeed': yawspeed
            }
        ))

    async def _on_attitude_rate_cmd(
        self,
        rollspeed: float = 0.0,
        pitchspeed: float = 0.0,
        yawspeed: float = 0.0,
        thrust: float = 0.5
    ) -> None:
        """Internal handler for attitude rate commands."""
        self._commands_sent.append(CommandRecord(
            command_type='attitude_rate',
            values={
                'rollspeed': rollspeed,
                'pitchspeed': pitchspeed,
                'yawspeed': yawspeed,
                'thrust': thrust
            }
        ))

    def get_orientation(self) -> Tuple[float, float, float]:
        """
        Returns current orientation as (yaw, pitch, roll) in radians.

        Returns:
            Tuple[float, float, float]: (yaw, pitch, roll)
        """
        return (self.current_yaw, self.current_pitch, self.current_roll)

    def get_attitude(self) -> MockAttitude:
        """Returns attitude object."""
        return self.attitude

    # Command verification methods
    @property
    def rtl_triggered(self) -> bool:
        """Check if RTL was triggered."""
        return self._rtl_triggered

    @property
    def commands_sent(self) -> List[CommandRecord]:
        """Get list of all commands sent."""
        return self._commands_sent.copy()

    def get_last_command(self) -> Optional[CommandRecord]:
        """Get the most recent command, if any."""
        return self._commands_sent[-1] if self._commands_sent else None

    def get_commands_of_type(self, command_type: str) -> List[CommandRecord]:
        """Get all commands of a specific type."""
        return [cmd for cmd in self._commands_sent if cmd.command_type == command_type]

    def clear_commands(self) -> None:
        """Clear command history."""
        self._commands_sent.clear()
        self._rtl_triggered = False

    # Telemetry simulation methods
    def set_altitude(self, altitude: float) -> None:
        """Set simulated altitude."""
        self.current_altitude = altitude

    def set_attitude(self, pitch: float = 0.0, roll: float = 0.0, yaw: float = 0.0) -> None:
        """Set simulated attitude (radians)."""
        self.current_pitch = pitch
        self.current_roll = roll
        self.current_yaw = yaw
        self.attitude = MockAttitude(
            pitch_deg=pitch * 57.2958,
            roll_deg=roll * 57.2958,
            yaw_deg=yaw * 57.2958
        )
        self.attitude_timestamp = time.time()

    def set_airspeed(self, airspeed: float) -> None:
        """Set simulated airspeed."""
        self.current_airspeed = airspeed

    def simulate_low_altitude(self, min_altitude: float = 3.0) -> None:
        """Simulate altitude below safety limit."""
        self.current_altitude = min_altitude - 1.0

    def simulate_high_altitude(self, max_altitude: float = 120.0) -> None:
        """Simulate altitude above safety limit."""
        self.current_altitude = max_altitude + 10.0

    def simulate_stall(self, stall_speed: float = 12.0) -> None:
        """Simulate stall condition for fixed-wing."""
        self.current_airspeed = stall_speed - 2.0
