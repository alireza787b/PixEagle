# GIMBAL FOLLOWER IMPLEMENTATION PLAN
## Saved Details - Do Not Lose

### User Requirements:
1. **Gimbal follower** that uses gimbal angle data to control drone movement
2. **Zero hardcoding** - everything configurable via YAML
3. **Circuit breaker system** for testing without actual drone commands
4. **Target loss handling** (continue velocity for X seconds, then RTL)
5. **Safety integration** matching existing followers
6. **Clean architecture** following existing follower patterns

### Technical Analysis:
- **User's gimbal**: Operates in "active tracking mode" where angles represent target direction
- **Vertical mount**: pitch=90° at startup, roll controls azimuth, pitch controls elevation
- **Horizontal mount**: direct 1:1 mapping with drone coordinates
- **Need**: Mount-aware coordinate transformations

### Implementation Phases:
- **PHASE 1**: ✅ COMPLETE - Circuit breaker infrastructure and configuration
- **PHASE 2**: Implement mount-aware coordinate transformation pipeline
- **PHASE 3**: Rewrite GimbalFollower with new architecture
- **PHASE 4**: UI integration and app controller integration
- **PHASE 5**: Final testing and validation

### Key Configuration (Already Added):
```yaml
GimbalFollower:
  MOUNT_TYPE: "VERTICAL"
  CONTROL_MODE: "BODY"
  REQUIRED_TRACKER_FIELDS: ["angular"]
  TARGET_LOSS_HANDLING:
    CONTINUE_VELOCITY_TIMEOUT: 3.0
    ENABLE_RTL_ON_TIMEOUT: true
  # ... rest of config
```

### Current Status:
Phase 1 complete with circuit breaker working. User wants to test existing followers first before continuing with gimbal implementation.