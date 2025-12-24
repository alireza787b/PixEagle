# src/classes/safety_types.py
"""
Safety Types Module - Type Definitions for Safety System
=========================================================

This module defines the type structures used by the SafetyManager for
centralized safety limit management in PixEagle.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi

Design Philosophy:
- All limits stored and returned as proper SI units
- Rates in rad/s internally (converted from deg/s in config)
- Velocities in m/s
- Altitudes in m
- Named tuples for type safety and immutability
"""

from typing import NamedTuple, Optional, Dict, Any
from enum import Enum
from math import radians


class VehicleType(Enum):
    """Vehicle type classification for safety profiles."""
    MULTICOPTER = "MULTICOPTER"
    FIXED_WING = "FIXED_WING"
    GIMBAL = "GIMBAL"


class TargetLossAction(Enum):
    """Action to take when target is lost."""
    HOVER = "hover"       # Multicopter: stop and hover
    ORBIT = "orbit"       # Fixed-wing: orbit last position
    STOP = "stop"         # Gimbal: zero velocities
    RTL = "rtl"           # Return to launch
    CONTINUE = "continue" # Continue last command


class SafetyAction(Enum):
    """Action recommended by safety check."""
    NONE = "none"              # No action needed
    WARN = "warn"              # Warning only
    CLAMP = "clamp"            # Clamp value to limit
    ZERO_VELOCITY = "zero"     # Zero all velocities
    RTL = "rtl"                # Return to launch
    EMERGENCY_STOP = "estop"   # Emergency stop


class VelocityLimits(NamedTuple):
    """Velocity limits in m/s."""
    forward: float      # MAX_VELOCITY_FORWARD
    lateral: float      # MAX_VELOCITY_LATERAL
    vertical: float     # MAX_VELOCITY_VERTICAL
    max_magnitude: float = 15.0  # Overall magnitude limit


class AltitudeLimits(NamedTuple):
    """Altitude limits in meters."""
    min_altitude: float        # MIN_ALTITUDE
    max_altitude: float        # MAX_ALTITUDE
    warning_buffer: float      # ALTITUDE_WARNING_BUFFER
    safety_enabled: bool = True


class RateLimits(NamedTuple):
    """Rate limits in rad/s (converted from deg/s in config)."""
    yaw: float    # MAX_YAW_RATE in rad/s
    pitch: float  # MAX_PITCH_RATE in rad/s
    roll: float   # MAX_ROLL_RATE in rad/s


class SafetyBehavior(NamedTuple):
    """Safety behavior configuration."""
    emergency_stop_enabled: bool
    rtl_on_violation: bool
    target_loss_action: TargetLossAction
    max_safety_violations: int = 5


class SafetyStatus(NamedTuple):
    """Result of a safety check."""
    safe: bool
    reason: str = ""
    action: SafetyAction = SafetyAction.NONE
    details: Optional[Dict[str, Any]] = None

    @classmethod
    def ok(cls) -> 'SafetyStatus':
        """Create a safe status."""
        return cls(safe=True, reason="ok", action=SafetyAction.NONE)

    @classmethod
    def violation(cls, reason: str, action: SafetyAction,
                  details: Optional[Dict[str, Any]] = None) -> 'SafetyStatus':
        """Create a violation status."""
        return cls(safe=False, reason=reason, action=action, details=details)


class FollowerLimits(NamedTuple):
    """Complete set of limits for a follower."""
    velocity: VelocityLimits
    altitude: AltitudeLimits
    rates: RateLimits
    behavior: SafetyBehavior
    vehicle_type: VehicleType


# Field to limit mapping for SetpointHandler validation
FIELD_LIMIT_MAPPING = {
    # Velocity fields
    'vel_x': 'MAX_VELOCITY_FORWARD',
    'vel_y': 'MAX_VELOCITY_LATERAL',
    'vel_z': 'MAX_VELOCITY_VERTICAL',
    'vel_body_fwd': 'MAX_VELOCITY_FORWARD',
    'vel_body_right': 'MAX_VELOCITY_LATERAL',
    'vel_body_down': 'MAX_VELOCITY_VERTICAL',
    # Rate fields
    'yawspeed_deg_s': 'MAX_YAW_RATE',
    'pitchspeed_deg_s': 'MAX_PITCH_RATE',
    'rollspeed_deg_s': 'MAX_ROLL_RATE',
    # Fixed-wing specific
    'airspeed': 'MAX_AIRSPEED',
}


# Follower name to vehicle type mapping
FOLLOWER_VEHICLE_TYPE = {
    # Multicopter followers
    'MC_VELOCITY': VehicleType.MULTICOPTER,
    'MC_VELOCITY_CHASE': VehicleType.MULTICOPTER,
    'MC_VELOCITY_POSITION': VehicleType.MULTICOPTER,
    'MC_VELOCITY_DISTANCE': VehicleType.MULTICOPTER,
    'MC_VELOCITY_GROUND': VehicleType.MULTICOPTER,
    'MC_ATTITUDE_RATE': VehicleType.MULTICOPTER,
    # Gimbal followers
    'GM_VELOCITY_VECTOR': VehicleType.GIMBAL,
    'GM_PID_PURSUIT': VehicleType.GIMBAL,
    # Fixed-wing followers
    'FW_ATTITUDE_RATE': VehicleType.FIXED_WING,
}


