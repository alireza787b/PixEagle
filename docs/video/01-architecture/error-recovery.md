# Error Recovery

> Robust connection handling and failure recovery strategies

## Overview

The video subsystem implements multi-level error recovery to maintain video feed during connection issues, especially important for RTSP streams from drones or IP cameras.

As of degraded-mode hardening, backend startup no longer fails when the video source is unavailable. The API and dashboard remain usable so operators can correct camera configuration and reconnect without losing control-plane access.

## Recovery Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                     ERROR RECOVERY PIPELINE                         │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Frame Read Attempt                                                │
│         │                                                           │
│         ▼                                                           │
│   ┌─────────────┐                                                  │
│   │  Success?   │──Yes──▶ Reset counters, return frame             │
│   └──────┬──────┘                                                  │
│          │ No                                                       │
│          ▼                                                          │
│   ┌─────────────────────┐                                          │
│   │ Increment failures  │                                          │
│   │ _consecutive_failures++                                        │
│   └──────────┬──────────┘                                          │
│              │                                                      │
│              ▼                                                      │
│   ┌─────────────────────────────────┐                              │
│   │ failures < max_failures?        │──Yes──▶ Return cached frame  │
│   └──────────────┬──────────────────┘                              │
│                  │ No                                               │
│                  ▼                                                  │
│   ┌─────────────────────────────────┐                              │
│   │ _attempt_recovery()             │                              │
│   │                                 │                              │
│   │ 1. Quick test (grab/retrieve)   │                              │
│   │ 2. Full reconnect if needed     │                              │
│   │ 3. Retry up to max_attempts     │                              │
│   └──────────────┬──────────────────┘                              │
│                  │                                                  │
│                  ▼                                                  │
│   ┌─────────────────────────────────┐                              │
│   │ Recovery successful?            │                              │
│   │                                 │                              │
│   │ Yes: Reset counters, continue   │                              │
│   │ No:  Return cached, log error   │                              │
│   └─────────────────────────────────┘                              │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

## Configuration Parameters

```yaml
VideoSource:
  # Recovery thresholds
  RTSP_MAX_CONSECUTIVE_FAILURES: 10   # Failures before recovery
  RTSP_CONNECTION_TIMEOUT: 5.0        # Seconds before timeout
  RTSP_MAX_RECOVERY_ATTEMPTS: 3       # Max reconnection tries
  RTSP_FRAME_CACHE_SIZE: 5            # Cached frames for fallback
```

## Recovery Levels

### Level 1: Graceful Degradation

On single frame failure, return cached frame:

```python
def _handle_frame_failure(self) -> Optional[np.ndarray]:
    self._consecutive_failures += 1

    # Below threshold - just return cached
    if self._consecutive_failures < self._max_consecutive_failures:
        logger.debug(f"Frame failure {self._consecutive_failures}, using cache")
        return self._get_cached_frame()

    # Above threshold - attempt recovery
    return self._attempt_recovery()
```

**Behavior:**
- Seamless to application - no visible disruption
- Cached frame may be 1-5 frames old
- Suitable for momentary glitches

### Level 2: Connection Recovery

When failures exceed threshold:

```python
def _attempt_recovery(self) -> Optional[np.ndarray]:
    self._is_recovering = True
    self._recovery_attempts += 1

    logger.warning(f"Attempting recovery ({self._recovery_attempts}/{self._max_recovery_attempts})")

    # Step 1: Quick connection test
    if self.cap and self.cap.isOpened():
        if self.cap.grab():
            ret, frame = self.cap.retrieve()
            if ret:
                logger.info("Quick recovery successful")
                self._reset_failure_counters()
                return frame

    # Step 2: Full reconnection
    if self._recovery_attempts <= self._max_recovery_attempts:
        success = self.reconnect()
        if success:
            ret, frame = self.cap.read()
            if ret:
                logger.info("Full reconnection successful")
                self._reset_failure_counters()
                return frame

    # Step 3: Give up, return cached
    logger.error("Recovery failed, using cached frame")
    return self._get_cached_frame()
```

### Level 3: Pipeline Fallback (RTSP)

For RTSP streams, multiple pipeline fallbacks:

```python
def _create_gstreamer_rtsp_with_fallback(self) -> cv2.VideoCapture:
    # Try primary optimized pipeline
    pipelines = [
        self._build_gstreamer_rtsp_pipeline(),      # Ultra-low latency
        *self._build_fallback_rtsp_pipelines()       # 4 fallbacks
    ]

    for i, pipeline in enumerate(pipelines):
        logger.debug(f"Trying RTSP pipeline {i+1}/{len(pipelines)}")
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

        if cap.isOpened():
            logger.info(f"RTSP connected with pipeline {i+1}")
            return cap

    # Final fallback: OpenCV default
    logger.warning("GStreamer failed, using OpenCV RTSP")
    return self._create_opencv_rtsp_optimized()
```

**Fallback Pipeline Order:**
1. Primary: TCP, 200ms latency, ultra-optimized
2. Fallback 1: Add queue, simplified
3. Fallback 2: Higher latency (500ms), more buffering
4. Fallback 3: Auto-detect protocol
5. Fallback 4: No scaling (coordinate warning)
6. Final: OpenCV FFMPEG backend

## Health Monitoring

### get_connection_health()

```python
def get_connection_health(self) -> dict:
    current_time = time.time()
    time_since_last = current_time - self._last_successful_frame_time

    # Determine status
    if self._is_recovering:
        status = "recovering"
    elif self._consecutive_failures >= self._max_consecutive_failures:
        status = "failed"
    elif self._consecutive_failures > 0:
        status = "degraded"
    else:
        status = "healthy"

    return {
        'status': status,
        'consecutive_failures': self._consecutive_failures,
        'time_since_last_frame': time_since_last,
        'is_recovering': self._is_recovering,
        'recovery_attempts': self._recovery_attempts,
        'cached_frames_available': len(self._frame_cache),
        'connection_open': self.cap.isOpened() if self.cap else False,
        'video_source_type': Parameters.VIDEO_SOURCE_TYPE,
        'use_gstreamer': Parameters.USE_GSTREAMER,
    }
```

### Status Meanings

| Status | Meaning | Action |
|--------|---------|--------|
| `healthy` | Normal operation | None |
| `degraded` | Some failures, using cache | Monitor |
| `recovering` | Active recovery in progress | Wait |
| `failed` | Recovery failed | Force recovery or alert |

## Timeout Detection

Time-based failure detection in addition to count:

```python
# In get_frame()
current_time = time.time()
time_since_last = current_time - self._last_successful_frame_time

if time_since_last >= self._connection_timeout:
    logger.warning(f"Connection timeout ({time_since_last:.1f}s)")
    return self._attempt_recovery()
```

## Frame Cache Strategy

```python
# Cache configuration
self._frame_cache = deque(maxlen=getattr(Parameters, 'RTSP_FRAME_CACHE_SIZE', 5))

# On successful read
self._frame_cache.append(frame.copy())  # Deep copy for safety

# On failure - get most recent
def _get_cached_frame(self) -> Optional[np.ndarray]:
    if self._frame_cache:
        return self._frame_cache[-1]
    return None
```

**Cache Considerations:**
- Deep copies prevent mutation issues
- Oldest frames auto-removed (deque)
- Size configurable per use case

## Manual Recovery

### force_recovery()

```python
def force_recovery(self) -> bool:
    """Force immediate recovery attempt."""
    logger.info("Forcing recovery...")
    return self.reconnect()
```

### API-triggered recovery

Operators can trigger and observe recovery via API:

- `GET /api/video/health` - current video health state (`healthy`, `degraded`, `recovering`, `failed`, `unavailable`)
- `POST /api/video/reconnect` - force a reconnect attempt and return updated health

**Use Cases:**
- User-triggered reconnection
- After network change detected
- Dashboard reconnect button

### reconnect()

```python
def reconnect(self) -> bool:
    """Full reconnection to video source."""
    logger.info(f"Reconnecting to {Parameters.VIDEO_SOURCE_TYPE}...")

    # Release current
    self.release()

    # Reinitialize
    try:
        self.delay_frame = self.init_video_source(max_retries=3)
        self._reset_failure_counters()
        return True
    except Exception as e:
        logger.error(f"Reconnection failed: {e}")
        return False
```

## Best Practices

### 1. Configure for Your Network

```yaml
# Stable network (local)
RTSP_MAX_CONSECUTIVE_FAILURES: 5
RTSP_CONNECTION_TIMEOUT: 3.0
RTSP_LATENCY: 100

# Unstable network (drone)
RTSP_MAX_CONSECUTIVE_FAILURES: 15
RTSP_CONNECTION_TIMEOUT: 10.0
RTSP_LATENCY: 500
```

### 2. Monitor Health

```python
# Periodic health check
health = handler.get_connection_health()
if health['status'] != 'healthy':
    logger.warning(f"Video degraded: {health}")
    metrics.record('video_health', health['status'])
```

### 3. Handle Recovery in UI

```python
# Dashboard integration
@app.get("/api/video/health")
async def video_health():
    return video_handler.get_connection_health()

@app.post("/api/video/reconnect")
async def video_reconnect():
    success = video_handler.force_recovery()
    return {"success": success}
```

### 4. Log for Debugging

Recovery events are logged at appropriate levels:
- DEBUG: Individual failures, cache access
- INFO: Successful recovery
- WARNING: Recovery attempts, timeouts
- ERROR: Recovery failures

## Common Issues

### Issue: Frequent Recovery Attempts

**Cause:** Threshold too low for network conditions

**Solution:**
```yaml
RTSP_MAX_CONSECUTIVE_FAILURES: 20  # Increase
RTSP_CONNECTION_TIMEOUT: 10.0      # More time
```

### Issue: Stale Cached Frames

**Cause:** Cache size too large, frames too old

**Solution:**
```yaml
RTSP_FRAME_CACHE_SIZE: 3  # Reduce cache
```

### Issue: Recovery Never Succeeds

**Cause:** Underlying network/source issue

**Solution:**
1. Check source availability
2. Try TCP instead of UDP
3. Check firewall rules
4. Verify RTSP URL
