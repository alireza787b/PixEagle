# src/classes/circuit_breaker.py

"""
Follower Circuit Breaker Module
==============================

This module provides a global fail-closed command-dispatch inhibit. It prevents
follower commands from reaching PX4 when active. It is not a follower preview,
PX4 simulator, or substitute for a reviewed SITL/SIH command sink.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
-------------
- Global circuit breaker for all followers
- Fail-closed PX4 command-dispatch inhibition
- Audit logging for commands intercepted after activation
- Telemetry integration for UI visualization
- Following-start preflight rejection while active or unavailable
- Thread-safe singleton pattern

Usage:
------
```python
# Check if circuit breaker is active
state = FollowerCircuitBreaker.get_activation_state()
if state["active"]:
    FollowerCircuitBreaker.log_command_instead_of_execute(
        command_type="velocity_command",
        vel_body_fwd=2.0,
        vel_body_right=0.5,
    )
    return False  # The caller must not dispatch this command to PX4.
```

Integration:
-----------
This system integrates with:
- BaseFollower class for automatic command interception
- Parameters system for configuration
- FastAPI handler for UI control
- Telemetry system for visualization
"""

import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime

# Import Parameters for configuration access
from classes.parameters import Parameters

logger = logging.getLogger(__name__)

class FollowerCircuitBreaker:
    """
    Global fail-closed inhibit for follower command dispatch.

    Following startup is rejected while this state is active or unavailable.
    The lower PX4 command gate also intercepts and records attempted dispatches
    if the breaker is activated after Following has already started. That audit
    path is defense in depth, not a follower preview or simulator.

    Thread-safe implementation using class-level synchronization.
    """

    _instance: Optional['FollowerCircuitBreaker'] = None
    _initialized: bool = False

    def __init__(self):
        """Initialize circuit breaker - use get_instance() instead."""
        if FollowerCircuitBreaker._initialized:
            return

        # Command logging state
        self._command_count = 0
        self._commands_blocked = 0  # Commands blocked (when CB active)
        self._commands_allowed = 0  # Commands allowed (when CB inactive)
        self._start_time = time.time()
        self._last_command_time = None
        self._last_blocked_command = None

        # Statistics for debugging
        self._command_types = {}
        self._followers_tested = set()

        FollowerCircuitBreaker._initialized = True
        logger.info("FollowerCircuitBreaker initialized")

    @classmethod
    def get_instance(cls) -> 'FollowerCircuitBreaker':
        """Get singleton instance of circuit breaker."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def is_active(cls) -> bool:
        """
        Check if circuit breaker is currently active.

        Returns:
            bool: True if PX4 command dispatch must remain inhibited
        """
        return cls.get_activation_state()["active"]

    @classmethod
    def get_activation_state(cls) -> Dict[str, Any]:
        """Return validated command-inhibit state, failing closed on bad config."""
        configured = getattr(Parameters, "FOLLOWER_CIRCUIT_BREAKER", None)
        if type(configured) is bool:
            return {
                "available": True,
                "active": configured,
                "reason": None,
            }

        logger.error(
            "FOLLOWER_CIRCUIT_BREAKER is missing or non-boolean; "
            "PX4 command dispatch remains inhibited"
        )
        return {
            "available": False,
            "active": True,
            "reason": "circuit_breaker_state_unavailable",
        }

    @classmethod
    def log_command_instead_of_execute(cls, command_type: str,
                                     follower_name: str = "Unknown",
                                     **command_data) -> bool:
        """
        Log follower command instead of executing it.

        This method records a command intercepted by the lower PX4 command
        gate. It does not prove that a follower session ran or that PX4 would
        have accepted or responded to the command.

        Args:
            command_type (str): Type of command (e.g., "velocity_body", "velocity_ned")
            follower_name (str): Name of the follower making the command
            **command_data: Command parameters as keyword arguments

        Returns:
            bool: True after the blocked-command audit record is updated
        """
        instance = cls.get_instance()
        current_time = time.time()

        # Update statistics
        instance._command_count += 1
        instance._commands_blocked += 1  # This method is only called when CB is active (blocking)
        instance._last_command_time = current_time
        instance._followers_tested.add(follower_name)

        if command_type not in instance._command_types:
            instance._command_types[command_type] = 0
        instance._command_types[command_type] += 1

        # Format command data for logging
        command_str = ", ".join([f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
                                for k, v in command_data.items()])

        # Store last blocked command for UI display
        instance._last_blocked_command = f"{command_type}({command_str})"

        # Log the intercepted command
        logger.info(f"[CIRCUIT BREAKER] {follower_name} → {command_type}: {command_str}")

        # Log periodic statistics for monitoring
        if instance._command_count % 50 == 0:
            elapsed_time = current_time - instance._start_time
            rate = instance._command_count / max(elapsed_time, 1)
            logger.info(f"[CIRCUIT BREAKER] Stats: {instance._command_count} commands, "
                       f"Rate: {rate:.1f} Hz, Types: {list(instance._command_types.keys())}")

        return True

    @classmethod
    def log_command_allowed(cls, command_type: str, follower_name: str = "Unknown", **command_data) -> None:
        """
        Log that a command was allowed to execute (when circuit breaker is inactive).

        Args:
            command_type (str): Type of command being allowed
            follower_name (str): Name of the follower executing the command
            **command_data: Command parameters for tracking
        """
        instance = cls.get_instance()
        current_time = time.time()

        # Update allowed command statistics
        instance._commands_allowed += 1
        instance._last_command_time = current_time
        instance._followers_tested.add(follower_name)

        # Track command types
        if command_type not in instance._command_types:
            instance._command_types[command_type] = 0
        instance._command_types[command_type] += 1

        # Log occasionally for monitoring (less verbose than blocked commands)
        if instance._commands_allowed % 100 == 0:
            logger.debug(f"[CIRCUIT BREAKER] Allowed {instance._commands_allowed} commands from {follower_name}")

    @classmethod
    def get_statistics(cls) -> Dict[str, Any]:
        """
        Get circuit breaker statistics for monitoring and debugging.

        Returns:
            Dict[str, Any]: Statistics including command counts, types, and timing
        """
        instance = cls.get_instance()
        current_time = time.time()
        elapsed_time = current_time - instance._start_time

        return {
            'circuit_breaker_active': cls.is_active(),
            'total_commands': instance._command_count,
            'total_commands_blocked': instance._commands_blocked,
            'total_commands_allowed': instance._commands_allowed,
            'last_blocked_command': getattr(instance, '_last_blocked_command', None),
            'command_types': dict(instance._command_types),
            'followers_tested': list(instance._followers_tested),
            'elapsed_time_seconds': elapsed_time,
            'command_rate_hz': instance._command_count / max(elapsed_time, 1),
            'last_command_time': instance._last_command_time,
            'session_start_time': instance._start_time,
            'system_status': 'testing' if cls.is_active() else 'operational'
        }

    @classmethod
    def should_skip_safety_checks(cls) -> bool:
        """
        Check whether the explicit bench-only safety bypass is effective.

        Safety checks (altitude limits, velocity limits, etc.) are skipped ONLY when:
        1. Circuit breaker is active (PX4 command dispatch is inhibited)
        2. AND the explicit safety disable flag is set in config

        The normal Following-start path rejects an active circuit breaker. This
        bypass therefore exists only for explicitly constructed bench/test
        sinks and must not be treated as an operator preview mode.

        Returns:
            bool: True if circuit breaker is active AND safety disable flag is set
        """
        from classes.parameters import Parameters

        # Safety checks are skipped ONLY if both conditions are met
        return (cls.is_active() and
                getattr(Parameters, "CIRCUIT_BREAKER_DISABLE_SAFETY", False))

    @classmethod
    def reset_statistics(cls) -> None:
        """Reset circuit breaker statistics."""
        instance = cls.get_instance()
        instance._command_count = 0
        instance._commands_blocked = 0
        instance._commands_allowed = 0
        instance._start_time = time.time()
        instance._last_command_time = None
        instance._last_blocked_command = None
        instance._command_types.clear()
        instance._followers_tested.clear()

        logger.info("Circuit breaker statistics reset")

    @classmethod
    def log_follower_event(cls, event_type: str, follower_name: str, **event_data) -> None:
        """
        Log follower events for debugging when circuit breaker is active.

        Args:
            event_type (str): Type of event (e.g., "target_acquired", "safety_stop")
            follower_name (str): Name of the follower
            **event_data: Event-specific data
        """
        if cls.is_active():
            event_str = ", ".join([f"{k}={v}" for k, v in event_data.items()])
            logger.info(f"[CIRCUIT BREAKER] {follower_name} EVENT: {event_type} - {event_str}")
