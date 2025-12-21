# src/classes/follower_logger.py
"""
Unified logging utility for follower classes.
Provides spam reduction, consistent formatting, and summary reporting.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, Optional
from datetime import datetime


class FollowerLogger:
    """
    Professional logging utility for follower classes.

    Features:
    - Spam reduction for repeated messages
    - Periodic summary reports
    - Consistent formatting across all followers
    - State change tracking
    """

    def __init__(self, follower_name: str, logger: logging.Logger,
                 spam_cooldown: float = 5.0, summary_interval: float = 30.0):
        """
        Initialize follower logger.

        Args:
            follower_name: Name of the follower (e.g., "MCVelocityChase")
            logger: Python logger instance
            spam_cooldown: Seconds between logging same message
            summary_interval: Seconds between summary reports
        """
        self.follower_name = follower_name
        self.logger = logger
        self.spam_cooldown = spam_cooldown
        self.summary_interval = summary_interval

        # Spam tracking
        self._last_log_time: Dict[str, float] = defaultdict(float)

        # Summary tracking
        self._operation_counts: Dict[str, int] = defaultdict(int)
        self._last_summary_time = time.time()

        # State tracking
        self._last_state: Optional[str] = None
        self._state_change_time: Optional[float] = None

    def log_state_change(self, new_state: str, details: str = "") -> None:
        """
        Log major state changes (always logged, spam-proof).

        Args:
            new_state: New state (e.g., "engaged", "disengaged", "tracking")
            details: Optional additional details
        """
        if new_state != self._last_state:
            duration = ""
            if self._last_state and self._state_change_time:
                elapsed = time.time() - self._state_change_time
                duration = f" (was {self._last_state} for {elapsed:.1f}s)"

            msg = f"[{self.follower_name}] State: {new_state}{duration}"
            if details:
                msg += f" - {details}"

            self.logger.info(msg)
            self._last_state = new_state
            self._state_change_time = time.time()

    def log_operation(self, operation: str, level: str = "debug",
                     details: str = "", throttle: bool = True) -> None:
        """
        Log follower operation with automatic throttling.

        Args:
            operation: Operation name (e.g., "follow_target", "calculate_control")
            level: Log level (debug, info, warning, error)
            details: Optional details
            throttle: Apply spam reduction (True) or always log (False)
        """
        self._operation_counts[operation] += 1

        if not throttle:
            msg = f"[{self.follower_name}] {operation}"
            if details:
                msg += f": {details}"
            getattr(self.logger, level)(msg)
            return

        # Throttled logging
        key = f"{operation}_{level}"
        current_time = time.time()

        if current_time - self._last_log_time[key] >= self.spam_cooldown:
            msg = f"[{self.follower_name}] {operation}"
            if details:
                msg += f": {details}"
            getattr(self.logger, level)(msg)
            self._last_log_time[key] = current_time

    def log_safety_event(self, event_type: str, severity: str,
                        details: str, action_taken: str = "") -> None:
        """
        Log safety events (altitude violations, emergency stops, etc.).

        Args:
            event_type: Type of event (e.g., "altitude_violation", "emergency_stop")
            severity: "warning", "error", or "critical"
            details: Event details
            action_taken: Action taken in response
        """
        msg = f"[{self.follower_name}] SAFETY {event_type.upper()}: {details}"
        if action_taken:
            msg += f" | Action: {action_taken}"

        getattr(self.logger, severity)(msg)

    def log_summary(self, force: bool = False) -> None:
        """
        Log periodic summary of follower operations.

        Args:
            force: Force summary even if interval hasn't elapsed
        """
        current_time = time.time()
        elapsed = current_time - self._last_summary_time

        if not force and elapsed < self.summary_interval:
            return

        if self._operation_counts:
            total_ops = sum(self._operation_counts.values())
            top_ops = sorted(self._operation_counts.items(),
                           key=lambda x: x[1], reverse=True)[:3]

            summary = f"[{self.follower_name}] Summary ({elapsed:.0f}s): {total_ops} operations"
            if top_ops:
                top_str = ", ".join([f"{op}={count}" for op, count in top_ops])
                summary += f" | Top: {top_str}"

            if self._last_state:
                summary += f" | State: {self._last_state}"

            self.logger.info(summary)
            self._operation_counts.clear()
            self._last_summary_time = current_time
