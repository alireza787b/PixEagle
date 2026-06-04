# MavlinkDataManager

> HTTP polling client for MAVLink2REST telemetry data.

**Source**: `src/classes/mavlink_data_manager.py` (~435 lines)

## Overview

MavlinkDataManager provides telemetry data from the PX4 autopilot via MAVLink2REST HTTP API. It's the primary telemetry source when `USE_MAVLINK2REST = True`.

Key responsibilities:
- Background thread polling of MAVLink2REST endpoints
- Shared timeout/retry handling for aggregate and per-message requests
- Data parsing and normalization
- Flight mode monitoring and offboard exit detection
- Connection/freshness state tracking with error recovery and `/status`
  diagnostics exposed as `mavlink_telemetry`

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MavlinkDataManager                           │
├─────────────────────────────────────────────────────────────────┤
│  Configuration:                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ mavlink_host: str       # "127.0.0.1"                    │    │
│  │ mavlink_port: int       # 8088                           │    │
│  │ polling_interval: float # seconds                        │    │
│  │ request_timeout_s: float # MAVLINK_REQUEST_TIMEOUT_S      │    │
│  │ request_retries: int     # MAVLINK_REQUEST_RETRIES        │    │
│  │ stale_timeout_s: float   # MAVLINK_STALE_TIMEOUT_S        │    │
│  │ data_points: dict       # JSON paths to extract          │    │
│  │ enabled: bool           # polling enabled                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  State:                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ data: dict              # latest telemetry values        │    │
│  │ connection_state: str   # disconnected/connecting/...    │    │
│  │ last_flight_mode: int   # for change detection          │    │
│  │ velocity_buffer: deque  # for smoothing                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Threading:                                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ _thread: Thread         # polling thread                 │    │
│  │ _stop_event: Event      # shutdown signal                │    │
│  │ _lock: RLock            # data/status protection         │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Key Methods:                                                    │
│  • start_polling() / stop_polling()                             │
│  • fetch_attitude_data() → dict                                 │
│  • fetch_altitude_data() → dict                                 │
│  • fetch_ground_speed() → float                                 │
│  • fetch_throttle_percent() → uint16                            │
│  • get_data(point_name) → any                                   │
│  • register_offboard_exit_callback(callback)                    │
└─────────────────────────────────────────────────────────────────┘
```

## Initialization

```python
def __init__(
    self,
    mavlink_host: str,      # MAVLink2REST host
    mavlink_port: int,      # MAVLink2REST port (8088)
    polling_interval: int,  # Poll interval in seconds
    data_points: dict,      # JSON paths to extract
    enabled: bool = True    # Enable polling
):
```

### Data Points Configuration

The `data_points` parameter defines JSON paths to extract from MAVLink2REST:

```python
# Example from config
data_points = {
    'latitude': '/vehicles/1/components/1/messages/GLOBAL_POSITION_INT/message/lat',
    'longitude': '/vehicles/1/components/1/messages/GLOBAL_POSITION_INT/message/lon',
    'altitude': '/vehicles/1/components/1/messages/ALTITUDE/message/altitude_relative',
    'vn': '/vehicles/1/components/1/messages/LOCAL_POSITION_NED/message/vx',
    've': '/vehicles/1/components/1/messages/LOCAL_POSITION_NED/message/vy',
    'vd': '/vehicles/1/components/1/messages/LOCAL_POSITION_NED/message/vz',
    'flight_mode': '/vehicles/1/components/191/messages/HEARTBEAT/message/custom_mode',
    'arm_status': '/vehicles/1/components/191/messages/HEARTBEAT/message/base_mode/bits',
}
```

## Timeout, Retry, And Freshness

MavlinkDataManager reads these typed config keys from the `MAVLink` section:

```yaml
MAVLink:
  MAVLINK_REQUEST_TIMEOUT_S: 5.0
  MAVLINK_REQUEST_RETRIES: 0
  MAVLINK_STALE_TIMEOUT_S: 2.0
```

`MAVLINK_REQUEST_TIMEOUT_S` is the HTTP timeout for each MAVLink2REST request.
`MAVLINK_REQUEST_RETRIES` is the number of additional attempts after the first
request fails. `MAVLINK_STALE_TIMEOUT_S` is the maximum age since the last
successful aggregate or per-message MAVLink2REST request before `/status`
reports `mavlink_telemetry.fresh = false`.

`get_connection_status()` returns the local request-health view used by the
legacy `/status` response. It reports `status`, `fresh`,
`last_success_age_s`, `request_timeout_s`, `request_retries`,
`stale_timeout_s`, `connection_error_count`, `last_error`, and `endpoint`.
This is MAVLink2REST transport freshness, not proof that a follower scenario
has run against PX4.

## Validation Timeout Injection

`inject_timeout_for_validation()` is a SITL-only test hook used through
`POST /api/v1/sitl/injections/mavlink2rest-timeout` when
`PIXEAGLE_ENABLE_SITL_INJECTIONS=1`. It records a bounded PixEagle-local
MAVLink2REST client timeout without stopping MAVLink2REST, PX4, Docker,
MavlinkAnywhere, routing, or network interfaces.

During the timeout window:

- `_request_json()` raises locally before calling `requests.get()`;
- `get_connection_status()` reports `connection_state = error`,
  `status = stale` when a prior successful sample exists, `fresh = false`, and
  `validation_timeout_active = true`;
- optional `force_stale` ages the last successful fetch beyond
  `MAVLINK_STALE_TIMEOUT_S` so follower/status consumers see stale telemetry.
  It never creates a fake prior success; if no successful MAVLink2REST fetch
  has happened, the timeout status remains `error` with
  `last_success_age_s = null`.

This hook proves PixEagle's stale/error telemetry response path. It does not
prove a real MAVLink2REST process failure, network outage, MAVLink route break,
or PX4 disconnect.

## Polling Thread

### start_polling() / stop_polling()

```python
def start_polling(self):
    """Start background polling thread if enabled."""
    if self.enabled:
        self._thread = threading.Thread(target=self._poll_data)
        self._thread.start()

def stop_polling(self):
    """Stop polling thread gracefully."""
    if self.enabled:
        self._stop_event.set()
        self._thread.join()
```

### _poll_data()

```python
def _poll_data(self):
    """
    Background polling loop.
    Runs at polling_interval rate until stop_event is set.
    """
    while not self._stop_event.is_set():
        self._fetch_and_parse_all_data()
        time.sleep(self.polling_interval)
```

### _fetch_and_parse_all_data()

```python
def _fetch_and_parse_all_data(self):
    """
    Fetch all MAVLink data in single request and parse.

    Endpoint: GET http://{host}:{port}/v1/mavlink

    Updates:
    - self.data dict (lock-protected)
    - connection_state and last_successful_fetch_monotonic_s
    - flight mode monitoring
    """
```

**Flow**:
```
_fetch_and_parse_all_data()
       │
       ▼
   GET /v1/mavlink
       │
       ├─► Success
       │      │
       │      ▼
       │   Update freshness diagnostics
       │      │
       │      ▼
       │   Parse JSON paths
       │      │
       │      ▼
       │   Update self.data (with lock)
       │      │
       │      ▼
       │   Check flight mode changes
       │      │
       │      ▼
       │   Log status periodically
       │
       └─► Error
              │
              ▼
           _handle_connection_error()
              │
              ▼
           Update connection_state
           Increment error_count
           Log (throttled)
```

## Async Fetch Methods

These methods are used by PX4InterfaceManager for on-demand telemetry:

Per-message fetches call the same timeout/retry helper as the aggregate polling
thread. A successful per-message request updates `mavlink_telemetry` freshness
even if the aggregate poll has not run recently.

### fetch_attitude_data()

```python
async def fetch_attitude_data(self) -> dict:
    """
    Fetch attitude (roll, pitch, yaw) from MAVLink2REST.

    Endpoint: /v1/mavlink/vehicles/1/components/1/messages/ATTITUDE

    Returns:
        dict: {"roll": deg, "pitch": deg, "yaw": deg}

    Note: Values converted from radians to degrees.
    Fallback: Returns zeros on error.
    """
```

**Conversion**:
```python
roll_deg = math.degrees(message.get("roll", 0))
pitch_deg = math.degrees(message.get("pitch", 0))
yaw_deg = math.degrees(message.get("yaw", 0))
```

### fetch_altitude_data()

```python
async def fetch_altitude_data(self) -> dict:
    """
    Fetch altitude data from MAVLink2REST.

    Endpoint: /v1/mavlink/vehicles/1/components/1/messages/ALTITUDE

    Returns:
        dict: {"altitude_relative": m, "altitude_amsl": m}

    Fallback: Returns SafetyLimits.MIN_ALTITUDE on error.
    """
```

### fetch_ground_speed()

```python
async def fetch_ground_speed(self) -> float:
    """
    Fetch ground speed (horizontal plane only).

    Endpoint: /v1/mavlink/vehicles/1/components/1/messages/LOCAL_POSITION_NED

    Returns:
        float: Ground speed in m/s (sqrt(vx^2 + vy^2))

    Fallback: Returns 0.0 on error.
    """
```

### fetch_throttle_percent()

```python
async def fetch_throttle_percent(self) -> uint16:
    """
    Fetch current throttle setting.

    Endpoint: /v1/mavlink/vehicles/1/components/1/messages/VFR_HUD

    Returns:
        uint16: Throttle 0-100

    Used for initial hover throttle when entering offboard.
    """
```

## Flight Mode Monitoring

### Flight Mode Detection

```python
# PX4 Offboard mode code
offboard_mode_code = 393216

# Checked in _fetch_and_parse_all_data()
if current_flight_mode != self.last_flight_mode:
    self._handle_flight_mode_change(old_mode, new_mode)
```

### _handle_flight_mode_change()

```python
def _handle_flight_mode_change(self, old_mode, new_mode):
    """
    Handle flight mode transitions.

    Critical: Detects Offboard mode exit (pilot override, failsafe).
    Triggers callback to disable follow mode automatically.
    """
    if old_mode == self.offboard_mode_code and new_mode != self.offboard_mode_code:
        # Offboard exited!
        logger.warning(f"Flight mode: Offboard (393216) → {new_mode}")

        if self._offboard_exit_callback:
            self._offboard_exit_callback(old_mode, new_mode)
```

### register_offboard_exit_callback()

```python
def register_offboard_exit_callback(self, callback):
    """
    Register callback for Offboard exit detection.

    Args:
        callback: Callable(old_mode, new_mode)

    Example:
        mavlink_data_manager.register_offboard_exit_callback(
            lambda old, new: asyncio.create_task(
                app_controller._handle_offboard_mode_exit(old, new)
            )
        )
    """
    self._offboard_exit_callback = callback
```

## Data Access

### get_data()

```python
def get_data(self, point: str) -> any:
    """
    Retrieve latest value for a data point.

    Thread-safe access to self.data dict.

    Args:
        point: Data point name from data_points config

    Returns:
        Value or 0 if not available
    """
    with self._lock:
        return self.data.get(point, 0)
```

## Connection State

### States

| State | Description |
|-------|-------------|
| `disconnected` | Initial state, not polling |
| `connecting` | Request in progress |
| `connected` | Last request successful |
| `error` | Last request failed |

### Error Handling

```python
def _handle_connection_error(self, error_reason: str):
    """
    Handle connection errors with throttled logging.

    Errors logged via logging_manager (prevents spam).
    connection_error_count incremented for tracking.
    """
    self.connection_state = "error"
    self.connection_error_count += 1

    logging_manager.log_connection_status(
        self.logger, "MAVLink", False, error_reason
    )
```

## Velocity Smoothing

For flight path angle calculation:

```python
# Buffer for velocity smoothing
velocity_buffer = deque(maxlen=10)

# In _calculate_flight_path_angle()
self.velocity_buffer.append((vn, ve, vd))
avg_vn = sum(v[0] for v in self.velocity_buffer) / len(self.velocity_buffer)
```

## REST Endpoints Used

| Endpoint | Data | Fields |
|----------|------|--------|
| `/v1/mavlink` | Full data dump | All configured data_points |
| `.../ATTITUDE` | Attitude | roll, pitch, yaw (rad) |
| `.../ALTITUDE` | Altitude | altitude_relative, altitude_amsl |
| `.../LOCAL_POSITION_NED` | Velocity | vx, vy, vz |
| `.../VFR_HUD` | HUD data | throttle |
| `.../HEARTBEAT` | Status | base_mode, custom_mode |

## Thread Safety

All data access is protected by `_lock`:

```python
with self._lock:
    for point_name, json_path in self.data_points.items():
        value = self._extract_data_from_json(json_data, json_path)
        self.data[point_name] = value
```

## Configuration Example

```yaml
MAVLink:
  MAVLINK_ENABLED: true
  MAVLINK_HOST: "127.0.0.1"
  MAVLINK_PORT: 8088
  MAVLINK_POLLING_INTERVAL: 0.5  # seconds
```

## Related Documentation

- [PX4InterfaceManager](px4-interface-manager.md) - Consumes telemetry
- [MAVLink2REST API](../03-protocols/mavlink2rest-api.md) - REST endpoints
- [mavlink-router](../04-infrastructure/mavlink-router.md) - Stream routing
