# SetpointSender

> Threaded command publishing at configurable rates.

**Source**: `src/classes/setpoint_sender.py` (~182 lines)

## Overview

SetpointSender runs in a dedicated thread to ensure consistent command publishing rate. It validates configuration and monitors the setpoint state.

**Note**: The actual command sending happens in the main async control loop via `app_controller.follow_target()`. SetpointSender primarily handles rate-limited validation and logging to avoid async loop conflicts.

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

    Runs at SETPOINT_PUBLISH_RATE_S (e.g., 0.05s = 20 Hz).
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

            # Sleep for configured rate
            time.sleep(Parameters.SETPOINT_PUBLISH_RATE_S)

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            self.error_count += 1
```

### _send_commands_sync()

```python
def _send_commands_sync(self) -> bool:
    """
    Synchronous command preparation.

    NOTE: Does not send commands directly to avoid async conflicts.
    Actual sending happens in main async loop.

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
| `SETPOINT_PUBLISH_RATE_S` | 0.05 | Loop rate (20 Hz) |
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
│  setpoint_handler.set_field(...)  ◄───────┐                     │
│       │                                    │                     │
│       ▼                                    │                     │
│  px4_interface.send_commands_unified()    │ Reads from          │
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

- Consecutive error counting with threshold
- Errors logged but thread continues
- Graceful shutdown with timeout
- No fatal errors - always tries to continue

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
