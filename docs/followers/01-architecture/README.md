# Follower Architecture

> System design and component relationships

The follower system uses a layered architecture with schema-driven configuration and centralized safety management.

---

## Component Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Application Layer                              │
│  main.py → Follower (manager) → FollowerFactory → Concrete Follower    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Core Framework                                 │
│  BaseFollower (ABC) ← SetpointHandler ← follower_commands.yaml         │
│         ↓                                                               │
│  SafetyManager ← config.yaml (Safety.GlobalLimits section)             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           PX4 Interface                                  │
│  PX4Controller → MAVSDK → MAVLink → Flight Controller                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Documents

| Document | Description |
|----------|-------------|
| [BaseFollower](base-follower.md) | Abstract base class, safety integration |
| [Factory Pattern](factory-pattern.md) | FollowerFactory registry system |
| [SetpointHandler](setpoint-handler.md) | Schema-aware configuration |

---

## Design Principles

### 1. Schema-Driven Configuration

All follower profiles are defined in `configs/follower_commands.yaml`:

```yaml
follower_profiles:
  mc_velocity_chase:
    display_name: "MC Velocity Chase"
    control_type: "velocity_body_offboard"
    required_fields: ["vel_body_fwd", "vel_body_right", "vel_body_down"]
    optional_fields: ["yawspeed_deg_s"]
```

Benefits:
- No hardcoded profile definitions in code
- Dashboard auto-discovers available modes
- Validation rules defined declaratively

### 2. Factory Registration Pattern

Followers register with the factory at module load:

```python
# In FollowerFactory._initialize_registry()
cls._follower_registry = {
    'mc_velocity_chase': MCVelocityChaseFollower,
    'fw_attitude_rate': FWAttitudeRateFollower,
    # ...
}
```

Benefits:
- Lazy loading prevents circular imports
- Easy to add new followers
- Removed aliases raise ValueError with v5.0.0 migration hint

### 3. Centralized Safety

All limits flow through SafetyManager:

```python
# SafetyManager provides limits to all followers
velocity_limits = safety_manager.get_velocity_limits('MC_VELOCITY_CHASE')
# VelocityLimits(forward=10.0, lateral=5.0, vertical=3.0)
```

Benefits:
- Single source of truth for limits
- Per-follower overrides supported
- Hot-reload from config changes

### 4. Rate-Limited Logging

High-frequency control loops use rate-limited logging:

```python
# Only logs once per 5 seconds for same message
self._rate_limiter.log_rate_limited(
    logger, 'warning',
    'velocity_clamp',
    f"Velocity clamped: {vel} -> {clamped}"
)
```

Benefits:
- Prevents log flooding at 20Hz
- Error aggregation for summaries
- Debug visibility without spam

---

## Data Flow

```
TrackerOutput              # From SmartTracker or ClassicTracker
     │
     ▼
validate_tracker_compatibility()  # BaseFollower checks requirements
     │
     ▼
extract_target_coordinates()      # Extract position/angles
     │
     ▼
calculate_control_commands()      # Concrete follower computes setpoints
     │
     ▼
SetpointHandler                   # Schema validation, field storage
     │
     ▼
clamp_velocity() / clamp_rate()   # SafetyManager limits
     │
     ▼
PX4Controller                     # MAVSDK command transmission
     │
     ▼
Flight Controller                 # PX4 autopilot
```

---

## Control Type Mapping

| Control Type | MAVSDK Method | Use Case |
|--------------|---------------|----------|
| `velocity_body` | `set_velocity_body()` | Legacy body velocity |
| `velocity_body_offboard` | `set_velocity_body_offboard()` | Multicopter offboard |
| `attitude_rate` | `set_attitude_rate()` | Fixed-wing, aggressive MC |

---

## Class Hierarchy

```
BaseFollower (ABC)
├── MCVelocityChaseFollower
├── MCVelocityGroundFollower
├── MCVelocityDistanceFollower
├── MCVelocityPositionFollower
├── MCAttitudeRateFollower
├── FWAttitudeRateFollower
├── GMVelocityChaseFollower
└── GMVelocityVectorFollower
```

All concrete followers inherit from `BaseFollower` and must implement:

```python
@abstractmethod
def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
    """Compute setpoints from tracker data."""
    pass

@abstractmethod
def follow_target(self, tracker_data: TrackerOutput) -> bool:
    """Execute following behavior."""
    pass
```

---

## Source Files

| File | Lines | Description |
|------|-------|-------------|
| `src/classes/followers/base_follower.py` | 1,142 | Abstract base class |
| `src/classes/follower.py` | 521 | Factory and manager |
| `src/classes/follower_types.py` | ~40 | `FollowerType` enum (WP9) |
| `src/classes/followers/yaw_rate_smoother.py` | ~130 | `YawRateSmoother` (WP9) |
| `src/classes/setpoint_handler.py` | ~300 | Schema configuration |
| `src/classes/safety_manager.py` | ~400 | Centralized limits |
| `configs/follower_commands.yaml` | 368 | Profile definitions |
