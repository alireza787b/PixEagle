# Known Issues and TODO

This file tracks verified, user-facing issues that are not fully solved yet.

## Open Items

### 1) OSD still too heavy on Jetson Nano in some real-time cases
- **Status**: Open
- **Observed**: Video becomes noticeably choppy when OSD is enabled, while OSD off is smooth.
- **Scope**: Jetson Nano / low-power ARM, especially with `professional` preset and active telemetry overlays.
- **Current Mitigation**:
  - Use `OSD_PERFORMANCE_MODE: fast` when smoothness is priority.
  - Reduce `OSD_DYNAMIC_FPS` (for example `4-6`).
  - Keep `OSD_TARGET_LAYER_RESOLUTION: stream`.
- **TODO (next iteration)**:
  - Add per-element OSD cost profiling (which element costs how much).
  - Split high-cost dynamic OSD elements into lower-frequency buckets.
  - Add optional lightweight preset for production low-power deployments.

### 2) WebSocket port health check messaging is confusing
- **Status**: Open
- **Observed**: Service status can show `WebSocket (port 5551) - not responding` while dashboard video works on backend WS endpoint (`/ws/video_feed` on API port).
- **Scope**: Service/operator UX and documentation consistency.
- **TODO (next iteration)**:
  - Unify terminology between telemetry socket port and video WebSocket endpoint.
  - Update `pixeagle-service status` checks to report both endpoints clearly.

### 3) Higher detection model load can trigger board instability on constrained setups
- **Status**: Open (environment + workload risk)
- **Observed**: Under heavier models (for example `yolo26s`) some runs may trigger abrupt reboot/reset on constrained power/thermal setups.
- **Scope**: Jetson deployment stability under peak load.
- **Current Mitigation**:
  - Start with `yolo26n`, then scale up.
  - Verify stable PSU and cooling before higher model profiles.
- **TODO (next iteration)**:
  - Add stress-test script that checks thermal/power headroom before enabling heavier models by default.
  - Add clearer runtime warning in UI when moving to heavier model families.
