# src/classes/circuit_breaker.py

"""
Follower Circuit Breaker Module
==============================

This module provides a global circuit breaker system for testing followers
without sending actual commands to the drone. When activated, all follower
commands are logged instead of executed, allowing safe testing of follower
logic, coordinate transformations, and UI integration.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
-------------
- Global circuit breaker for all followers
- Command logging instead of execution
- Telemetry integration for UI visualization
- Zero-impact on follower logic when disabled
- Thread-safe singleton pattern

Usage:
------
```python
# Check if circuit breaker is active
if FollowerCircuitBreaker.is_active():
    # Log command instead of executing
    FollowerCircuitBreaker.log_command_instead_of_execute(
        command_type="velocity_command",
        vel_body_fwd=2.0,
        vel_body_right=0.5
    )
else:
    # Execute normal command
    px4_controller.set_velocity_body(...)
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
    Global circuit breaker for follower testing and validation.

    This singleton class provides a centralized way to intercept and log
    follower commands instead of executing them. Useful for:
    - Testing follower logic without drone movement
    - Validating coordinate transformations
    - UI development and debugging
    - Safety testing of new followers

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
            bool: True if commands should be logged instead of executed
        """
        # Check configuration parameter
        return getattr(Parameters, 'FOLLOWER_CIRCUIT_BREAKER', False)

    @classmethod
    def log_command_instead_of_execute(cls, command_type: str,
                                     follower_name: str = "Unknown",
                                     **command_data) -> bool:
        """
        Log follower command instead of executing it.

        This method is called when circuit breaker is active to log what
        would have been executed, providing visibility into follower behavior
        without actually moving the drone.

        Args:
            command_type (str): Type of command (e.g., "velocity_body", "velocity_ned")
            follower_name (str): Name of the follower making the command
            **command_data: Command parameters as keyword arguments

        Returns:
            bool: True (simulates successful command execution)
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