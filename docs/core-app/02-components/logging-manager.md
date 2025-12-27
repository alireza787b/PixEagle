# LoggingManager

Professional logging with spam reduction and periodic summaries.

## Overview

`LoggingManager` (`src/classes/logging_manager.py`) provides:

- Spam reduction for repetitive messages
- Connection status tracking
- Periodic polling summaries
- System status reports
- Operation counting

## Class Definition

```python
class LoggingManager:
    """
    Professional logging manager that provides:
    - Spam reduction for repetitive messages
    - Periodic summary reports
    - Status-at-a-glance logging
    - Connection state tracking
    """
```

## Features

### Spam Reduction

Prevents log flooding from repetitive messages:

```python
def _should_log_operation(self, operation: str) -> bool:
    """Determine if we should log an operation (spam reduction)."""
    current_time = time.time()
    last_log = self._spam_filter.get(operation, 0)

    if current_time - last_log >= self._spam_cooldown:
        self._spam_filter[operation] = current_time
        return True
    return False
```

### Connection Status Tracking

```python
@dataclass
class ConnectionStatus:
    """Track connection status for clean logging."""
    is_connected: bool = False
    last_connected_time: Optional[float] = None
    last_disconnected_time: Optional[float] = None
    connection_attempts: int = 0
    successful_connections: int = 0
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    last_log_time: float = 0.0
```

### Polling Statistics

```python
self._polling_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
    'total_polls': 0,
    'successful_polls': 0,
    'failed_polls': 0,
    'last_poll_time': 0.0,
    'last_success_time': 0.0,
    'last_failure_time': 0.0,
    'last_summary_time': 0.0,
    'current_status': 'unknown'
})
```

## Usage

### Connection Logging

```python
def log_connection_status(
    self,
    logger: logging.Logger,
    service_name: str,
    is_connected: bool,
    details: str = ""
) -> None:
    """Log connection status with spam reduction."""
    status = self._connections.get(service_name, ConnectionStatus())

    # Check if status actually changed
    status_changed = status.is_connected != is_connected

    if is_connected:
        if status_changed:
            logger.info(f"[{service_name}] Connected {details}")
    else:
        if status_changed:
            logger.warning(f"[{service_name}] Disconnected {details}")
        elif self._should_log_failure(service_name, time.time()):
            uptime = int(time.time() - status.last_connected_time)
            logger.warning(
                f"[{service_name}] Still disconnected "
                f"({status.consecutive_failures} attempts, {uptime}s)"
            )
```

**Example Output:**
```
[MAVLink] Connected (udp://localhost:14551)
[MAVLink] Disconnected (timeout)
[MAVLink] Still disconnected (3 attempts, 15s)
```

### Polling Activity Logging

```python
def log_polling_activity(
    self,
    logger: logging.Logger,
    service_name: str,
    success: bool,
    details: str = ""
) -> None:
    """Log polling activity with periodic summaries."""
    stats = self._polling_stats[service_name]

    stats['total_polls'] += 1

    if success:
        stats['successful_polls'] += 1
        stats['current_status'] = 'healthy'
    else:
        stats['failed_polls'] += 1
        if stats['failed_polls'] > stats['successful_polls']:
            stats['current_status'] = 'degraded'

    # Log periodic summary
    if time.time() - stats['last_summary_time'] >= self.summary_interval:
        self._log_polling_summary(logger, service_name, stats)
        stats['last_summary_time'] = time.time()
```

**Example Output:**
```
[MAVLink2REST] Poll Summary: HEALTHY (99.5% success, 300 polls in 15.0s)
[MAVLink2REST] Poll Summary: DEGRADED (45.0% success, 100 polls in 15.0s)
```

### Operation Logging

```python
def log_operation(
    self,
    logger: logging.Logger,
    operation: str,
    level: str = 'info',
    details: str = ""
) -> None:
    """Log operations with spam reduction."""
    if self._should_log_operation(operation):
        message = f"[{operation}] {details}".strip()
        log_func = getattr(logger, level, logger.info)
        log_func(message)

        self._operation_counters[operation] += 1
```

**Example:**
```python
# Only logs once per 5 seconds even if called repeatedly
logging_manager.log_operation(logger, "FRAME_PROCESS", "info", "Processing frame")
```

### System Summary

```python
def log_system_summary(self, logger: logging.Logger) -> None:
    """Log a comprehensive system status summary."""
    logger.info("=== SYSTEM STATUS SUMMARY ===")

    # Connection status
    if self._connections:
        logger.info("Connection Status:")
        for service, status in self._connections.items():
            if status.is_connected:
                uptime = int(time.time() - status.last_connected_time)
                logger.info(f"  {service}: CONNECTED ({uptime}s uptime)")
            else:
                downtime = int(time.time() - status.last_disconnected_time)
                logger.info(
                    f"  {service}: DISCONNECTED "
                    f"({downtime}s down, {status.consecutive_failures} failures)"
                )

    # Polling status
    if self._polling_stats:
        logger.info("Polling Status:")
        for service, stats in self._polling_stats.items():
            success_rate = (stats['successful_polls'] / max(stats['total_polls'], 1)) * 100
            logger.info(
                f"  {service}: {stats['current_status'].upper()} "
                f"({success_rate:.1f}% success, {stats['total_polls']} total)"
            )

    # Top operations
    if self._operation_counters:
        top_ops = sorted(self._operation_counters.items(), key=lambda x: x[1], reverse=True)[:5]
        logger.info("Top Operations:")
        for op, count in top_ops:
            logger.info(f"  {op}: {count}")

    logger.info("=============================")
```

**Example Output:**
```
=== SYSTEM STATUS SUMMARY ===
Connection Status:
  MAVLink: CONNECTED (120s uptime)
  MAVSDK: CONNECTED (118s uptime)
Polling Status:
  MAVLink2REST: HEALTHY (99.5% success, 2400 total)
  Telemetry: HEALTHY (100.0% success, 1200 total)
Top Operations:
  FRAME_PROCESS: 3600
  TRACKER_UPDATE: 3600
  OSD_RENDER: 3600
=============================
```

## Configuration

```python
logging_manager = LoggingManager(
    summary_interval=15.0  # Seconds between summaries
)

# Adjust spam cooldown
logging_manager._spam_cooldown = 10.0  # 10 seconds
```

## Global Instance

```python
# Global logging manager instance
logging_manager = LoggingManager()

# Usage
from classes.logging_manager import logging_manager

logging_manager.log_connection_status(logger, "MAVLink", True)
```

## Integration Example

```python
class MavlinkDataManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def poll(self):
        try:
            data = await self._fetch_data()
            logging_manager.log_polling_activity(
                self.logger, "MAVLink2REST", True
            )
            return data
        except Exception as e:
            logging_manager.log_polling_activity(
                self.logger, "MAVLink2REST", False, str(e)
            )
            return None

    async def connect(self):
        connected = await self._try_connect()
        logging_manager.log_connection_status(
            self.logger,
            "MAVLink2REST",
            connected,
            f"http://{self.host}:{self.port}"
        )
```

## Benefits

| Problem | Solution |
|---------|----------|
| Log flooding | Spam reduction with cooldown |
| Missing context | Connection status tracking |
| Noise from polling | Periodic summaries instead of per-poll |
| System visibility | Comprehensive status summaries |
| Debugging | Operation counters |

## Related Components

- [AppController](app-controller.md) - Uses logging manager
- [MavlinkDataManager](../../drone-interface/02-components/mavlink-data-manager.md) - Polling logging
