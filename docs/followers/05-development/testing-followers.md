# Testing Followers

> Methodology for validating follower implementations

---

## Test Levels

1. **Unit Tests** - Isolated component testing
2. **Integration Tests** - System interaction
3. **SITL Tests** - Simulation validation
4. **Field Tests** - Real-world validation

---

## Unit Testing

### Test File Structure

```
tests/
├── test_followers/
│   ├── test_base_follower.py
│   ├── test_mc_velocity_chase.py
│   └── test_my_follower.py
```

### Basic Test Template

```python
# tests/test_followers/test_my_follower.py

import pytest
from unittest.mock import Mock, patch
from classes.followers.my_follower import MyFollower
from classes.tracker_output import TrackerOutput, TrackerDataType


class MockPX4Interface:
    """Mock PX4 interface for testing."""
    current_altitude = 50.0
    attitude = Mock(pitch=0.0, roll=0.0, yaw=0.0)


@pytest.fixture
def px4_controller():
    return MockPX4Interface()


@pytest.fixture
def follower(px4_controller):
    return MyFollower(px4_controller, (0.0, 0.0))


class TestMyFollowerInit:
    def test_initialization(self, follower):
        assert follower is not None
        assert follower.initial_target_coords == (0.0, 0.0)

    def test_invalid_coords_raises(self, px4_controller):
        with pytest.raises(ValueError):
            MyFollower(px4_controller, (999, 999))


class TestControlCommands:
    def test_centered_target_zero_command(self, follower):
        tracker_data = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            position_2d=(0.0, 0.0)
        )
        follower.calculate_control_commands(tracker_data)
        fields = follower.get_all_command_fields()
        assert abs(fields['vel_body_fwd']) < 0.01

    def test_offset_target_generates_command(self, follower):
        tracker_data = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            position_2d=(0.5, 0.0)
        )
        follower.calculate_control_commands(tracker_data)
        fields = follower.get_all_command_fields()
        assert abs(fields['vel_body_right']) > 0


class TestFollowTarget:
    def test_follow_returns_true_on_success(self, follower):
        tracker_data = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            position_2d=(0.1, 0.1)
        )
        result = follower.follow_target(tracker_data)
        assert result == True

    def test_follow_handles_invalid_data(self, follower):
        tracker_data = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            position_2d=None
        )
        result = follower.follow_target(tracker_data)
        assert result == False
```

### Running Unit Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_followers/test_my_follower.py

# Run with coverage
pytest --cov=src/classes/followers tests/
```

### Target-Loss Publication Tests

Follower tests must distinguish "target unavailable" from "no command should be
published." If a follower uses inactive tracker output to hover, stop, orbit,
coast, or decay a command, add tests that prove:

- `should_process_inactive_tracker_output()` returns `True` only for supported
  inactive tracker data types;
- `follow_target()` returns `True` when it produced or intentionally retained a
  `CommandIntent` that must be submitted to `OffboardCommander`;
- `follow_target()` returns `False` when the policy requests a mode change such
  as RTL and no further Offboard setpoint should be published;
- `AppController.follow_target()` submits the latest intent to
  `OffboardCommander` after that follower opt-in and does not call PX4 send
  methods from the frame loop.

Current regression coverage lives in
`tests/unit/followers/test_target_loss_safe_publication.py` and
`tests/unit/core_app/test_app_controller_offboard_safety.py`.
The coverage includes legacy multicopter velocity modes, gimbal-aware modes,
multicopter attitude-rate hover, and fixed-wing orbit/RTL/continue target-loss
policies. It also covers stale SmartTracker `MULTI_TARGET` output so multi-
target overlays cannot prevent fail-closed command publication.

### Command-Freshness Tests

Follower and controller tests must also cover stale vision inputs that still
carry coordinates:

- cached video frames from `VideoHandler` are marked
  `usable_for_following: false`;
- prediction-only tracker outputs keep diagnostic position data but set
  `data_is_stale: true` and `usable_for_following: false`;
- `AppController.follow_target()` converts those active-looking outputs into
  inactive fail-closed `TrackerOutput` before follower dispatch;
- a hard video stall calls `handle_video_frame_unavailable()` so PX4 following
  does not silently skip the safe target-loss command path.
- inactive output cannot reach a follower unless `AppController` confirms the
  concrete follower's explicit inactive-output opt-in, even if compatibility
  validation would otherwise pass.

Regression coverage for this contract is in
`tests/unit/video/test_video_handler.py`,
`tests/unit/trackers/test_base_tracker.py`, and
`tests/unit/core_app/test_app_controller_offboard_safety.py`. SmartTracker and
gimbal provider edge cases are covered by
`tests/unit/trackers/test_smart_tracker_freshness.py` and
`tests/unit/trackers/test_gimbal_tracker.py`.

---

## Circuit Breaker Testing

Use circuit breaker for safe command logging:

```python
from classes.circuit_breaker import FollowerCircuitBreaker

def test_with_circuit_breaker(follower):
    # Enable circuit breaker (commands logged, not executed)
    FollowerCircuitBreaker.enable()

    tracker_data = TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        position_2d=(0.5, 0.5)
    )

    follower.follow_target(tracker_data)

    # Check logged commands
    log = FollowerCircuitBreaker.get_command_log()
    assert len(log) > 0

    # Disable
    FollowerCircuitBreaker.disable()
```

---

## SITL Testing

### Setup PX4 SITL

```bash
# Terminal 1: PX4 SITL
cd PX4-Autopilot
make px4_sitl gazebo

# Terminal 2: PixEagle
cd PixEagle
export FOLLOWER_MODE=my_follower
bash scripts/run.sh
```

### SITL Test Scenarios

1. **Stationary Target**
   - Target fixed in frame
   - Verify position hold

2. **Moving Target**
   - Move target across frame
   - Verify pursuit behavior

3. **Target Loss**
   - Remove target from view
   - Verify loss handling

4. **Boundary Conditions**
   - Target at frame edges
   - Verify no runaway commands

---

## Test Utilities

### TrackerOutput Factory

```python
def create_tracker_output(x=0.0, y=0.0, confidence=1.0):
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        position_2d=(x, y),
        confidence=confidence,
        timestamp=time.time()
    )
```

### Velocity Verification

```python
def verify_velocity_limits(follower, tracker_data):
    follower.calculate_control_commands(tracker_data)
    fields = follower.get_all_command_fields()

    limits = follower.velocity_limits
    assert abs(fields['vel_body_fwd']) <= limits.forward
    assert abs(fields['vel_body_right']) <= limits.lateral
    assert abs(fields['vel_body_down']) <= limits.vertical
```

---

## Field Testing Checklist

### Pre-Flight

- [ ] SITL tests pass
- [ ] Configuration reviewed
- [ ] Safety limits appropriate
- [ ] Emergency procedures known

### During Flight

- [ ] Monitor telemetry
- [ ] Record video
- [ ] Ready to take over

### Post-Flight

- [ ] Review logs
- [ ] Analyze telemetry
- [ ] Document issues
- [ ] Update configuration
