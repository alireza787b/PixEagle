# Estimators

> **Note**: This documentation is a placeholder. Comprehensive documentation will be added after code audit is complete.

## Overview

Estimators in PixEagle provide state estimation and filtering capabilities for smoothing tracker output and predicting target motion.

## Components

| Component | File | Status |
|-----------|------|--------|
| BaseEstimator | `src/classes/estimators/base_estimator.py` | Pending audit |
| EstimatorFactory | `src/classes/estimators/estimator_factory.py` | Pending audit |
| KalmanEstimator | `src/classes/estimators/kalman_estimator.py` | Pending audit |
| PositionEstimator | `src/classes/position_estimator.py` | Pending audit |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   EstimatorFactory                       │
│                  (Factory Pattern)                       │
└─────────────────────────┬───────────────────────────────┘
                          │ creates
                          ▼
┌─────────────────────────────────────────────────────────┐
│                     BaseEstimator                        │
│                   (Abstract Base)                        │
├─────────────────────────────────────────────────────────┤
│  + predict() -> State                                   │
│  + update(measurement) -> State                         │
│  + get_state() -> State                                 │
└─────────────────────────┬───────────────────────────────┘
                          │ extends
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ KalmanEstimator │ │PositionEstimator│ │  (Future)       │
│  (Kalman Filter)│ │(3D Position Est)│ │  EKF/UKF        │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Estimator Types

### Kalman Estimator
Standard Kalman filter for linear state estimation with Gaussian noise.

**State Vector**: `[x, y, vx, vy]` (position and velocity)

### Position Estimator
3D position estimation using camera geometry and drone telemetry.

**Inputs**:
- Pixel coordinates from tracker
- Camera intrinsics (FOV, resolution)
- Drone altitude and attitude
- Gimbal angles (if applicable)

## Usage

```python
from classes.estimators.estimator_factory import EstimatorFactory

# Create estimator
estimator = EstimatorFactory.create('kalman', config)

# Prediction step (time update)
predicted_state = estimator.predict()

# Update step (measurement update)
measurement = [x, y]  # from tracker
updated_state = estimator.update(measurement)

# Get current state estimate
state = estimator.get_state()
print(f"Position: ({state.x}, {state.y}), Velocity: ({state.vx}, {state.vy})")
```

## Configuration

```yaml
# config_default.yaml
estimator:
  type: "kalman"
  process_noise: 0.1
  measurement_noise: 1.0
  initial_covariance: 100.0

position_estimation:
  enabled: true
  camera_fov_horizontal: 82.0
  camera_fov_vertical: 52.0
```

## Integration with Trackers

```
Tracker → Raw Position → Estimator → Smoothed Position → Follower
                              │
                              └── Velocity Estimate
```

## TODO

- [ ] Complete code audit
- [ ] Add comprehensive documentation for each estimator
- [ ] Add unit tests (~50 tests)
- [ ] Add integration tests
- [ ] Document Kalman filter mathematics
- [ ] Document 3D position estimation geometry

## Related

- [Trackers Documentation](../trackers/README.md) - Provides measurements to estimators
- [Followers Documentation](../followers/README.md) - Consumes estimator output
