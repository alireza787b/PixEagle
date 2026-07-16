# SetpointSender

> Threaded setpoint monitoring at a configurable period.

**Source**: `src/classes/setpoint_sender.py` (~182 lines)

## Overview

SetpointSender runs in a dedicated thread to validate configuration and monitor
setpoint state at a fixed period.

**Note**: `SetpointSender` does not publish MAVSDK Offboard commands. Current
application-level MAVSDK setter refresh ownership belongs to
[OffboardCommander](offboard-commander.md), which runs as an async task outside
the camera/tracker frame loop.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      SetpointSender                              │
│                    (threading.Thread)                            │
├─────────────────────────────────────────────────────────────────┤
│  Configuration:                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ px4_controller: PX4InterfaceManager                      │    │
│  │ setpoint_handler: SetpointHandler                        │    │
│  │ running: bool                # thread control flag       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Error Tracking:                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ error_count: int             # consecutive errors        │    │
│  │ max_consecutive_errors: int  # threshold (5)             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Schema Caching:                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ _control_type: str           # cached control type       │    │
│  │ _last_schema_check: float    # timestamp                 │    │
│  │ _schema_check_interval: int  # 10 seconds                │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Key Methods:                                                    │
│  • run()              # main thread loop                        │
│  • stop()             # graceful shutdown                       │
│  • validate_configuration() → bool                              │
└─────────────────────────────────────────────────────────────────┘
```

## Initialization

```python
def __init__(self, px4_controller, setpoint_handler: SetpointHandler):
    """
    Initialize SetpointSender as daemon thread.

    Args:
        px4_controller: PX4InterfaceManager instance
        setpoint_handler: SetpointHandler instance
    """
    super().__init__(daemon=True)  # Daemon thread
    self.px4_controller = px4_controller
    self.setpoint_handler = setpoint_handler
    self.running = True
    self.error_count = 0
    self.max_consecutive_errors = 5
```

## Main Loop

### run()

```python
def run(self):
    """
    Main thread loop.

    Runs every SETPOINT_PUBLISH_RATE_S seconds.
    Validates setpoints and logs state periodically.
    """
    while self.running:
        try:
            # Update control type periodically
            self._update_control_type()

            # Validate and prepare commands (sync)
            success = self._send_commands_sync()

            # Handle error counting
            if success:
                self.error_count = 0
            else:
                self.error_count += 1
                if self.error_count >= self.max_consecutive_errors:
                    logger.error(f"Too many failures ({self.error_count})")

            # Debug output
            if Parameters.ENABLE_SETPOINT_DEBUGGING:
                self._print_current_setpoint()

            # Sleep for configured monitor period
            time.sleep(self.get_loop_period_s())

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            self.error_count += 1
```

### _send_commands_sync()

```python
def _send_commands_sync(self) -> bool:
    """
    Synchronous setpoint validation/logging.

    NOTE: Does not send MAVSDK commands. OffboardCommander owns publication.

    Returns:
        bool: True if setpoints are valid
    """
    control_type = self._control_type or self.setpoint_handler.get_control_type()
    setpoint = self.setpoint_handler.get_fields()

    # Periodic debug logging
    if self._setpoint_debug_count % 20 == 0:
        logger.info(f"SetpointSender values: {control_type} -> {setpoint}")

    return True
```

## Control Type Caching

```python
def _update_control_type(self):
    """
    Update cached control type periodically.

    Avoids repeated schema lookups.
    Interval: 10 seconds.
    """
    current_time = time.time()
    if current_time - self._last_schema_check > self._schema_check_interval:
        new_control_type = self.setpoint_handler.get_control_type()
        if new_control_type != self._control_type:
            logger.info(f"Control type: {self._control_type} → {new_control_type}")
            self._control_type = new_control_type
        self._last_schema_check = current_time
```

## Validation

### validate_configuration()

```python
def validate_configuration(self) -> bool:
    """
    Validate sender is properly configured.

    Checks:
    - SetpointHandler has get_control_type method
    - Control type is valid
    - Fields are available

    Returns:
        bool: True if valid
    """
    # Check control type method exists
    if not hasattr(self.setpoint_handler, 'get_control_type'):
        return False

    control_type = self.setpoint_handler.get_control_type()
    if not control_type:
        return False

    # Check fields
    fields = self.setpoint_handler.get_fields()
    if not fields:
        return False

    return True
```

## Lifecycle

### stop()

```python
def stop(self):
    """
    Stop thread gracefully.

    Sets running=False and waits for thread to finish.
    Timeout: 5 seconds.
    """
    logger.info("Stopping SetpointSender...")
    self.running = False

    self.join(timeout=5.0)

    if self.is_alive():
        logger.warning("Thread did not stop within timeout")
    else:
        logger.info("Stopped successfully")
```

## Debug Output

### _print_current_setpoint()

```python
def _print_current_setpoint(self):
    """
    Print current setpoints for debugging.

    Enabled by: Parameters.ENABLE_SETPOINT_DEBUGGING
    """
    setpoints = self.setpoint_handler.get_fields()
    control_type = self._control_type or 'unknown'
    logger.debug(f"Current {control_type} setpoints: {setpoints}")
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `SETPOINT_PUBLISH_RATE_S` | 0.1 | Monitor loop period in seconds. This does not publish MAVSDK Offboard commands. |
| `OFFBOARD_COMMAND_RATE_HZ` | 20.0 | OffboardCommander application-level MAVSDK setter refresh rate. |
| `OFFBOARD_COMMAND_TTL_S` | 0.5 | Maximum latest `CommandIntent` age before default setpoints are published. |
| `ENABLE_SETPOINT_DEBUGGING` | false | Enable debug output |

## Threading Model

```
┌─────────────────────────────────────────────────────────────────┐
│                      Main Async Loop                             │
│                                                                  │
│  AppController.follow_target()                                  │
│       │                                                          │
│       ▼                                                          │
│  follower.follow_target(tracker_output)                         │
│       │                                                          │
│       ▼                                                          │
│  BaseFollower.set_command_fields(...)                           │
│       │                                    │                     │
│       ▼                                    │                     │
│  OffboardCommander.submit_intent(...)     │ Reads from          │
└─────────────────────────────────────────────────────────────────┘
                                             │
┌─────────────────────────────────────────────────────────────────┐
│                   SetpointSender Thread                          │
│                                                                  │
│  while running:                                                  │
│       │                                                          │
│       ▼                                                          │
│  _update_control_type()                                         │
│       │                                                          │
│       ▼                                                          │
│  _send_commands_sync()  ────────────────────┘                   │
│       │  (validates and logs)                                   │
│       ▼                                                          │
│  time.sleep(SETPOINT_PUBLISH_RATE_S)                            │
└─────────────────────────────────────────────────────────────────┘
```

## Error Handling

- Consecutive monitor error counting with threshold
- Errors logged but thread continues
- Graceful shutdown with timeout
- Status reports `sends_mavsdk_commands: false` and
  `command_publication_source: offboard_commander`

## Usage Example

```python
# Create and start
setpoint_sender = SetpointSender(px4_interface, setpoint_handler)

# Validate before starting
if setpoint_sender.validate_configuration():
    setpoint_sender.start()

# ... application runs ...

# Stop gracefully
setpoint_sender.stop()
```

## Related Documentation

- [SetpointHandler](setpoint-handler.md) - Setpoint management
- [PX4InterfaceManager](px4-interface-manager.md) - Command dispatch
