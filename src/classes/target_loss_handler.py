# src/classes/target_loss_handler.py

"""
Target Loss Handling Architecture
=================================

Unified, tracker-agnostic target loss detection and response system.
Works with any tracker type through the standardized TrackerOutput interface.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- Tracker-agnostic: Works with CSRT, YOLO, gimbal, or any tracker
- Configurable timeout and response actions
- State machine for clean target loss/recovery transitions
- Circuit breaker integration for safe testing
- Comprehensive logging and monitoring
- Zero hardcoding - fully YAML configurable
"""

import time
import logging
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
from dataclasses import dataclass

# Import circuit breaker for integration
try:
    from classes.circuit_breaker import FollowerCircuitBreaker
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False

logger = logging.getLogger(__name__)

class TargetState(Enum):
    """Target tracking states for loss detection."""
    ACTIVE = "ACTIVE"           # Target being tracked successfully
    LOST = "LOST"               # Target lost, within timeout period
    TIMEOUT = "TIMEOUT"         # Target lost beyond timeout period
    RECOVERING = "RECOVERING"   # Target found again, transitioning back to active

class ResponseAction(Enum):
    """Available response actions for target loss."""
    CONTINUE_VELOCITY = "CONTINUE_VELOCITY"  # Continue last known velocity
    CONTINUE_PREDICTIVE = "CONTINUE_PREDICTIVE"  # Continue with predictive velocity
    HOLD_POSITION = "HOLD_POSITION"         # Stop and hover
    RETURN_TO_LAUNCH = "RETURN_TO_LAUNCH"   # Trigger RTL
    SEARCH_PATTERN = "SEARCH_PATTERN"       # Execute search pattern
    CUSTOM_ACTION = "CUSTOM_ACTION"         # Execute custom callback

@dataclass
class TargetLossEvent:
    """Container for target loss event data."""
    timestamp: float
    previous_state: TargetState
    new_state: TargetState
    loss_duration: float
    tracker_type: str
    follower_name: str
    metadata: Dict[str, Any]

class TargetLossHandler:
    """
    Unified target loss detection and response system.

    Provides tracker-agnostic target loss handling through the standardized
    TrackerOutput interface. Supports configurable timeouts and response actions.
    """

    def __init__(self, config: Dict[str, Any], follower_name: str = "Unknown"):
        """
        Initialize target loss handler with configuration.

        Args:
            config: Configuration dictionary from YAML (e.g., TARGET_LOSS_HANDLING section)
            follower_name: Name of the follower using this handler
        """
        self.follower_name = follower_name
        self.config = config

        # Timeout configuration
        self.continue_velocity_timeout = config.get('CONTINUE_VELOCITY_TIMEOUT', 3.0)
        self.total_timeout = config.get('TOTAL_TIMEOUT', 10.0)
        self.recovery_confirmation_time = config.get('RECOVERY_CONFIRMATION_TIME', 0.5)

        # Response configuration
        self.enable_rtl_on_timeout = config.get('ENABLE_RTL_ON_TIMEOUT', True)
        self.rtl_altitude = config.get('RTL_ALTITUDE', 50.0)
        self.continue_velocity_enabled = config.get('CONTINUE_VELOCITY_ENABLED', True)

        # Advanced configuration
        self.min_loss_duration = config.get('MIN_LOSS_DURATION', 0.1)  # Ignore brief losses
        self.enable_velocity_decay = config.get('ENABLE_VELOCITY_DECAY', True)
        self.velocity_decay_rate = config.get('VELOCITY_DECAY_RATE', 0.9)  # Per second
        self.max_continue_velocity = config.get('MAX_CONTINUE_VELOCITY', 5.0)

        # Enhanced timeout behaviors (PHASE 3.2)
        self.enable_adaptive_timeout = config.get('ENABLE_ADAPTIVE_TIMEOUT', False)
        self.adaptive_timeout_factor = config.get('ADAPTIVE_TIMEOUT_FACTOR', 1.5)  # Multiplier based on movement
        self.enable_predictive_velocity = config.get('ENABLE_PREDICTIVE_VELOCITY', True)
        self.prediction_history_size = config.get('PREDICTION_HISTORY_SIZE', 5)
        self.confidence_timeout_adjustment = config.get('CONFIDENCE_TIMEOUT_ADJUSTMENT', True)
        self.high_confidence_threshold = config.get('HIGH_CONFIDENCE_THRESHOLD', 0.8)
        self.low_confidence_threshold = config.get('LOW_CONFIDENCE_THRESHOLD', 0.3)

        # Target tracking history for prediction
        self.target_history = []  # Store recent target positions/velocities
        self.velocity_history = []  # Store recent velocity estimates

        # State tracking
        self.current_state = TargetState.ACTIVE
        self.target_lost_time: Optional[float] = None
        self.target_recovered_time: Optional[float] = None
        self.last_valid_tracker_output = None
        self.velocity_continuation_active = False

        # Statistics and monitoring
        self.total_loss_events = 0
        self.total_loss_duration = 0.0
        self.last_loss_event: Optional[TargetLossEvent] = None

        # Callbacks for response actions
        self.response_callbacks: Dict[ResponseAction, Callable] = {}

        logger.info(f"TargetLossHandler initialized for {follower_name}")
        logger.info(f"  Continue velocity timeout: {self.continue_velocity_timeout}s")
        logger.info(f"  Total timeout: {self.total_timeout}s")
        logger.info(f"  RTL on timeout: {self.enable_rtl_on_timeout}")

    def register_response_callback(self, action: ResponseAction, callback: Callable):
        """
        Register a callback for a specific response action.

        Args:
            action: The response action type
            callback: Function to call when action is triggered
        """
        self.response_callbacks[action] = callback
        logger.debug(f"Registered {action.value} callback for {self.follower_name}")

    def update_tracker_status(self, tracker_output) -> Dict[str, Any]:
        """
        Update target loss handler with latest tracker output.

        Args:
            tracker_output: TrackerOutput object from any tracker type

        Returns:
            Dict containing target loss status and recommended actions
        """
        current_time = time.time()

        # Extract tracking status - works with ANY tracker type
        tracking_active = getattr(tracker_output, 'tracking_active', False)
        tracker_type = getattr(tracker_output, 'data_type', 'Unknown')

        if hasattr(tracker_type, 'value'):
            tracker_type = tracker_type.value

        previous_state = self.current_state

        # State machine logic
        if tracking_active:
            if self.current_state in [TargetState.LOST, TargetState.TIMEOUT]:
                # Target recovery detected
                if self.target_recovered_time is None:
                    self.target_recovered_time = current_time
                    self.current_state = TargetState.RECOVERING
                    logger.info(f"Target recovery detected for {self.follower_name}")
                elif current_time - self.target_recovered_time >= self.recovery_confirmation_time:
                    # Recovery confirmed
                    self._handle_target_recovery(current_time, tracker_type)
            elif self.current_state == TargetState.RECOVERING:
                # Continue recovery process
                if current_time - self.target_recovered_time >= self.recovery_confirmation_time:
                    self._handle_target_recovery(current_time, tracker_type)
            else:
                # Target is active - normal operation
                self.current_state = TargetState.ACTIVE
                self.last_valid_tracker_output = tracker_output
                self.target_recovered_time = None
                self.velocity_continuation_active = False

                # Update tracking history for prediction (PHASE 3.2)
                self._update_tracking_history(tracker_output, current_time)

        else:
            # Target not active
            if self.current_state == TargetState.ACTIVE:
                # Target loss detected
                self.target_lost_time = current_time
                self.current_state = TargetState.LOST
                self.target_recovered_time = None
                logger.warning(f"Target loss detected for {self.follower_name}")

            elif self.current_state == TargetState.LOST:
                # Check if we've exceeded timeout
                loss_duration = current_time - self.target_lost_time
                if loss_duration >= self.total_timeout:
                    self.current_state = TargetState.TIMEOUT
                    logger.error(f"Target loss timeout exceeded for {self.follower_name} ({loss_duration:.1f}s)")

        # Generate response based on current state
        response = self._generate_response(current_time, tracker_type, previous_state != self.current_state)

        # Log state changes
        if previous_state != self.current_state:
            self._log_state_change(previous_state, self.current_state, current_time, tracker_type)

        return response

    def _handle_target_recovery(self, current_time: float, tracker_type: str):
        """Handle confirmed target recovery."""
        if self.target_lost_time is not None:
            loss_duration = current_time - self.target_lost_time
            self.total_loss_duration += loss_duration
            self.total_loss_events += 1

        self.current_state = TargetState.ACTIVE
        self.target_lost_time = None
        self.target_recovered_time = None
        self.velocity_continuation_active = False

        logger.info(f"Target recovery confirmed for {self.follower_name}")

    def _generate_response(self, current_time: float, tracker_type: str, state_changed: bool) -> Dict[str, Any]:
        """Generate response based on current target state."""
        response = {
            'target_state': self.current_state.value,
            'tracking_active': self.current_state == TargetState.ACTIVE,
            'state_changed': state_changed,
            'timestamp': current_time,
            'recommended_actions': [],
            'velocity_continuation': False,
            'trigger_rtl': False,
            'metadata': {
                'tracker_type': tracker_type,
                'follower_name': self.follower_name,
                'loss_duration': self._get_current_loss_duration(current_time)
            }
        }

        if self.current_state == TargetState.LOST:
            loss_duration = current_time - self.target_lost_time

            # Check if loss duration is significant enough to act on
            if loss_duration >= self.min_loss_duration:
                # Calculate adaptive timeout if enabled (PHASE 3.2)
                effective_timeout = self._calculate_effective_timeout(current_time)

                if self.continue_velocity_enabled and loss_duration <= effective_timeout:
                    # Determine velocity continuation strategy
                    if self.enable_predictive_velocity and len(self.velocity_history) >= 2:
                        # Use predictive velocity based on movement history
                        response['velocity_continuation'] = True
                        response['recommended_actions'].append(ResponseAction.CONTINUE_PREDICTIVE.value)
                        predicted_velocity = self._calculate_predicted_velocity()
                        response['predicted_velocity'] = predicted_velocity
                        response['prediction_confidence'] = self._calculate_prediction_confidence()
                    else:
                        # Standard velocity continuation
                        response['velocity_continuation'] = True
                        response['recommended_actions'].append(ResponseAction.CONTINUE_VELOCITY.value)

                    self.velocity_continuation_active = True

                    # Apply velocity decay if enabled
                    if self.enable_velocity_decay and self.last_valid_tracker_output:
                        decay_factor = self.velocity_decay_rate ** loss_duration
                        response['velocity_decay_factor'] = decay_factor

                elif loss_duration > effective_timeout:
                    # Exceeded continue velocity timeout - hold position or search
                    if loss_duration < effective_timeout * 2:
                        # Try search pattern before giving up
                        response['recommended_actions'].append(ResponseAction.SEARCH_PATTERN.value)
                    else:
                        # Give up and hold position
                        response['recommended_actions'].append(ResponseAction.HOLD_POSITION.value)
                    self.velocity_continuation_active = False

                # Add timeout information to response
                response['effective_timeout'] = effective_timeout
                response['timeout_reason'] = self._get_timeout_reason()

        elif self.current_state == TargetState.TIMEOUT:
            # Total timeout exceeded
            if self.enable_rtl_on_timeout:
                response['trigger_rtl'] = True
                response['recommended_actions'].append(ResponseAction.RETURN_TO_LAUNCH.value)
                response['rtl_altitude'] = self.rtl_altitude

                # Circuit breaker integration - don't actually trigger RTL in test mode
                if CIRCUIT_BREAKER_AVAILABLE and FollowerCircuitBreaker.is_active():
                    FollowerCircuitBreaker.log_command_instead_of_execute(
                        command_type="return_to_launch",
                        follower_name=self.follower_name,
                        reason="target_loss_timeout",
                        loss_duration=self._get_current_loss_duration(current_time),
                        rtl_altitude=self.rtl_altitude
                    )
                    response['trigger_rtl'] = False  # Override for circuit breaker mode
                    response['circuit_breaker_blocked'] = True

        # Execute registered callbacks
        for action_str in response['recommended_actions']:
            try:
                action = ResponseAction(action_str)
                if action in self.response_callbacks:
                    callback_result = self.response_callbacks[action](response)
                    response[f'{action.value.lower()}_callback_result'] = callback_result
            except Exception as e:
                logger.error(f"Error executing {action_str} callback: {e}")

        return response

    def _get_current_loss_duration(self, current_time: float) -> float:
        """Get current loss duration or 0.0 if not lost."""
        if self.target_lost_time is None:
            return 0.0
        return current_time - self.target_lost_time

    def _log_state_change(self, previous_state: TargetState, new_state: TargetState,
                         current_time: float, tracker_type: str):
        """Log target state changes for monitoring."""
        loss_duration = self._get_current_loss_duration(current_time)

        event = TargetLossEvent(
            timestamp=current_time,
            previous_state=previous_state,
            new_state=new_state,
            loss_duration=loss_duration,
            tracker_type=tracker_type,
            follower_name=self.follower_name,
            metadata={
                'velocity_continuation_active': self.velocity_continuation_active,
                'total_loss_events': self.total_loss_events,
                'config': {
                    'continue_velocity_timeout': self.continue_velocity_timeout,
                    'enable_rtl_on_timeout': self.enable_rtl_on_timeout
                }
            }
        )

        self.last_loss_event = event

        logger.info(f"Target state change: {previous_state.value} -> {new_state.value} "
                   f"({self.follower_name}, {tracker_type}, {loss_duration:.1f}s)")

    def get_current_state(self) -> str:
        """
        Get current target loss state as string.

        Returns:
            str: Current state name (ACTIVE, LOST, TIMEOUT, RECOVERING)
        """
        return self.current_state.value

    def get_timeout_remaining(self) -> float:
        """
        Get remaining timeout duration in seconds.

        Returns:
            float: Seconds remaining until timeout (0.0 if not applicable)
        """
        if self.current_state != TargetState.LOST or self.target_lost_time is None:
            return 0.0

        current_time = time.time()
        elapsed = current_time - self.target_lost_time
        remaining = self.continue_velocity_timeout - elapsed
        return max(0.0, remaining)

    def is_continuing_velocity(self) -> bool:
        """
        Check if velocity continuation is currently active.

        Returns:
            bool: True if currently continuing velocity, False otherwise
        """
        return self.should_continue_velocity()

    def get_statistics(self) -> Dict[str, Any]:
        """Get target loss handling statistics."""
        current_time = time.time()
        return {
            'follower_name': self.follower_name,
            'current_state': self.current_state.value,
            'current_loss_duration': self._get_current_loss_duration(current_time),
            'timeout_remaining': self.get_timeout_remaining(),
            'total_loss_events': self.total_loss_events,
            'total_loss_duration': self.total_loss_duration,
            'velocity_continuation_active': self.velocity_continuation_active,
            'configuration': {
                'continue_velocity_timeout': self.continue_velocity_timeout,
                'total_timeout': self.total_timeout,
                'enable_rtl_on_timeout': self.enable_rtl_on_timeout,
                'rtl_altitude': self.rtl_altitude
            },
            'last_event': (
                {
                    'timestamp': self.last_loss_event.timestamp,
                    'state_change': f"{self.last_loss_event.previous_state.value} -> {self.last_loss_event.new_state.value}",
                    'loss_duration': self.last_loss_event.loss_duration,
                    'tracker_type': self.last_loss_event.tracker_type
                } if self.last_loss_event else None
            )
        }

    def reset_state(self):
        """Reset target loss handler state (useful for follower restart)."""
        logger.info(f"Resetting target loss handler state for {self.follower_name}")
        self.current_state = TargetState.ACTIVE
        self.target_lost_time = None
        self.target_recovered_time = None
        self.last_valid_tracker_output = None
        self.velocity_continuation_active = False

    def is_target_lost(self) -> bool:
        """Check if target is currently lost."""
        return self.current_state in [TargetState.LOST, TargetState.TIMEOUT]

    def should_continue_velocity(self) -> bool:
        """Check if velocity continuation should be active."""
        return self.velocity_continuation_active and self.current_state == TargetState.LOST

    def should_trigger_rtl(self) -> bool:
        """Check if RTL should be triggered."""
        return (self.current_state == TargetState.TIMEOUT and
                self.enable_rtl_on_timeout and
                not (CIRCUIT_BREAKER_AVAILABLE and FollowerCircuitBreaker.is_active()))

    # ==================== Enhanced Timeout Methods (PHASE 3.2) ====================

    def _update_tracking_history(self, tracker_output, current_time: float):
        """Update tracking history for predictive analysis."""
        # Store position data if available
        if hasattr(tracker_output, 'position_2d') and tracker_output.position_2d is not None:
            position_entry = {
                'timestamp': current_time,
                'position_2d': tracker_output.position_2d,
                'confidence': getattr(tracker_output, 'confidence', 1.0)
            }
            self.target_history.append(position_entry)

            # Calculate velocity if we have previous position
            if len(self.target_history) >= 2:
                prev = self.target_history[-2]
                curr = self.target_history[-1]
                dt = curr['timestamp'] - prev['timestamp']
                if dt > 0:
                    dx = curr['position_2d'][0] - prev['position_2d'][0]
                    dy = curr['position_2d'][1] - prev['position_2d'][1]
                    velocity = (dx / dt, dy / dt)

                    velocity_entry = {
                        'timestamp': current_time,
                        'velocity': velocity,
                        'confidence': min(prev['confidence'], curr['confidence'])
                    }
                    self.velocity_history.append(velocity_entry)

            # Limit history size
            if len(self.target_history) > self.prediction_history_size:
                self.target_history.pop(0)
            if len(self.velocity_history) > self.prediction_history_size:
                self.velocity_history.pop(0)

    def _calculate_effective_timeout(self, current_time: float) -> float:
        """Calculate adaptive timeout based on tracking confidence and movement."""
        base_timeout = self.continue_velocity_timeout

        if not self.enable_adaptive_timeout:
            return base_timeout

        # Adjust based on confidence if available
        if self.confidence_timeout_adjustment and self.last_valid_tracker_output:
            confidence = getattr(self.last_valid_tracker_output, 'confidence', 0.5)

            if confidence >= self.high_confidence_threshold:
                # High confidence - extend timeout slightly
                base_timeout *= 1.2
            elif confidence <= self.low_confidence_threshold:
                # Low confidence - reduce timeout
                base_timeout *= 0.8

        # Adjust based on target movement history
        if len(self.velocity_history) >= 2:
            recent_velocities = [entry['velocity'] for entry in self.velocity_history[-3:]]
            avg_speed = sum(abs(v[0]) + abs(v[1]) for v in recent_velocities) / len(recent_velocities)

            # Fast moving targets get longer timeout (harder to predict)
            if avg_speed > 0.5:  # Fast movement threshold
                base_timeout *= self.adaptive_timeout_factor
            elif avg_speed < 0.1:  # Slow movement threshold
                base_timeout *= 0.8

        return min(base_timeout, self.total_timeout * 0.8)  # Cap at 80% of total timeout

    def _calculate_predicted_velocity(self) -> tuple:
        """Calculate predicted velocity based on movement history."""
        if len(self.velocity_history) < 2:
            return (0.0, 0.0)

        # Use weighted average of recent velocities with trend analysis
        recent_velocities = self.velocity_history[-3:]

        if len(recent_velocities) == 1:
            return recent_velocities[0]['velocity']

        # Calculate trend
        weights = [1.0, 1.5, 2.0][:len(recent_velocities)]
        total_weight = sum(weights)

        weighted_vx = sum(v['velocity'][0] * w for v, w in zip(recent_velocities, weights)) / total_weight
        weighted_vy = sum(v['velocity'][1] * w for v, w in zip(recent_velocities, weights)) / total_weight

        return (weighted_vx, weighted_vy)

    def _calculate_prediction_confidence(self) -> float:
        """Calculate confidence in velocity prediction."""
        if len(self.velocity_history) < 2:
            return 0.0

        # Base confidence on consistency of recent velocities
        recent_velocities = [entry['velocity'] for entry in self.velocity_history[-3:]]
        if len(recent_velocities) < 2:
            return 0.5

        # Calculate velocity consistency
        avg_vx = sum(v[0] for v in recent_velocities) / len(recent_velocities)
        avg_vy = sum(v[1] for v in recent_velocities) / len(recent_velocities)

        variance_x = sum((v[0] - avg_vx) ** 2 for v in recent_velocities) / len(recent_velocities)
        variance_y = sum((v[1] - avg_vy) ** 2 for v in recent_velocities) / len(recent_velocities)

        # Lower variance = higher confidence
        total_variance = variance_x + variance_y
        confidence = max(0.1, min(1.0, 1.0 - (total_variance * 10)))

        # Factor in tracking confidence
        if len(self.velocity_history) > 0:
            avg_tracking_confidence = sum(entry['confidence'] for entry in self.velocity_history[-3:]) / min(3, len(self.velocity_history))
            confidence *= avg_tracking_confidence

        return confidence

    def _get_timeout_reason(self) -> str:
        """Get human-readable reason for current timeout value."""
        if not self.enable_adaptive_timeout:
            return "fixed_timeout"

        reasons = []

        if self.confidence_timeout_adjustment and self.last_valid_tracker_output:
            confidence = getattr(self.last_valid_tracker_output, 'confidence', 0.5)
            if confidence >= self.high_confidence_threshold:
                reasons.append("high_confidence")
            elif confidence <= self.low_confidence_threshold:
                reasons.append("low_confidence")

        if len(self.velocity_history) >= 2:
            recent_velocities = [entry['velocity'] for entry in self.velocity_history[-3:]]
            avg_speed = sum(abs(v[0]) + abs(v[1]) for v in recent_velocities) / len(recent_velocities)

            if avg_speed > 0.5:
                reasons.append("fast_movement")
            elif avg_speed < 0.1:
                reasons.append("slow_movement")

        return "_".join(reasons) if reasons else "standard"

def create_target_loss_handler(config: Dict[str, Any], follower_name: str) -> TargetLossHandler:
    """
    Factory function to create target loss handler.

    Args:
        config: Configuration dictionary (typically from TARGET_LOSS_HANDLING section)
        follower_name: Name of the follower using this handler

    Returns:
        Configured TargetLossHandler instance
    """
    return TargetLossHandler(config, follower_name)

if __name__ == "__main__":
    # Test the target loss handler
    print("Target Loss Handler Test")
    print("=" * 30)

    # Test configuration
    test_config = {
        'CONTINUE_VELOCITY_TIMEOUT': 3.0,
        'TOTAL_TIMEOUT': 10.0,
        'ENABLE_RTL_ON_TIMEOUT': True,
        'RTL_ALTITUDE': 50.0,
        'RECOVERY_CONFIRMATION_TIME': 0.5,
        'MIN_LOSS_DURATION': 0.1,
        'ENABLE_VELOCITY_DECAY': True,
        'VELOCITY_DECAY_RATE': 0.9
    }

    # Create handler
    handler = create_target_loss_handler(test_config, "TestFollower")

    # Simulate tracker outputs
    from classes.tracker_output import TrackerOutput, TrackerDataType
    import time

    print("\nSimulating tracker behavior:")

    # Active tracking
    active_output = TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        position_2d=(0.5, 0.3)
    )

    response = handler.update_tracker_status(active_output)
    print(f"Active tracking: {response['target_state']}")

    # Lost tracking
    lost_output = TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=False
    )

    response = handler.update_tracker_status(lost_output)
    print(f"Target lost: {response['target_state']}, actions: {response['recommended_actions']}")

    # Statistics
    stats = handler.get_statistics()
    print(f"\nStatistics: {stats['total_loss_events']} loss events, current state: {stats['current_state']}")

    print("\nTarget Loss Handler Test Complete!")