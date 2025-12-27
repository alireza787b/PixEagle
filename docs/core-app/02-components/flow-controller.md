# FlowController

The main entry point that manages the application lifecycle and frame processing loop.

## Overview

`FlowController` (`src/classes/flow_controller.py`) is responsible for:

- Initializing the AppController and FastAPI server
- Running the main frame processing loop
- Handling signals for graceful shutdown
- Managing thread coordination

## Class Definition

```python
class FlowController:
    """
    Main entry point for PixEagle application.

    Manages:
    - AppController initialization
    - FastAPI server thread
    - Main processing loop
    - Signal handling for shutdown
    """
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FlowController                          │
│                                                              │
│  ┌──────────────────────┐    ┌──────────────────────────┐   │
│  │     Main Thread      │    │   FastAPI Server Thread  │   │
│  │  ┌────────────────┐  │    │  ┌────────────────────┐  │   │
│  │  │ main_loop()    │  │    │  │   Uvicorn Server   │  │   │
│  │  │ - get_frame()  │  │    │  │   - REST API       │  │   │
│  │  │ - update_loop()│  │    │  │   - WebSocket      │  │   │
│  │  │ - show_frame() │  │    │  │   - Streaming      │  │   │
│  │  └────────────────┘  │    │  └────────────────────┘  │   │
│  └──────────────────────┘    └──────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Signal Handlers                                      │   │
│  │  - SIGINT (Ctrl+C)                                   │   │
│  │  - SIGTERM (kill)                                    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Initialization

```python
def __init__(self):
    """
    Initialize FlowController with all subsystems.
    """
    logging.debug("Initializing FlowController...")

    # Initialize AppController (creates all subsystems)
    self.controller = AppController()

    # Start FastAPI server in separate thread
    self.server, self.server_thread = self.start_fastapi_server()

    # Setup signal handlers
    signal.signal(signal.SIGINT, self.shutdown_handler)
    signal.signal(signal.SIGTERM, self.shutdown_handler)

    self.controller.shutdown_flag = False
    self._shutdown_initiated = False
```

## FastAPI Server

```python
def start_fastapi_server(self):
    """
    Start FastAPI server in a separate thread.

    Returns:
        Tuple of (server, thread)
    """
    fastapi_handler = self.controller.api_handler

    def run_server():
        asyncio.run(fastapi_handler.start(
            host=Parameters.HTTP_STREAM_HOST,
            port=Parameters.HTTP_STREAM_PORT
        ))

    server_thread = threading.Thread(target=run_server)
    server_thread.start()

    return None, server_thread
```

## Main Loop

```python
def main_loop(self):
    """
    Main frame processing loop.

    Handles:
    - Frame capture from video source
    - Update loop execution (tracking, following)
    - Frame display (if GUI enabled)
    - Keyboard input handling
    - Frame timing
    """
    try:
        loop = asyncio.get_event_loop()

        while not self.controller.shutdown_flag:
            # Get frame
            frame = self.controller.video_handler.get_frame()
            if frame is None:
                logging.warning("No frame from video_handler")
                break

            # Process frame
            frame = loop.run_until_complete(
                self.controller.update_loop(frame)
            )

            # Display frame
            self.controller.show_current_frame()

            # Handle timing and input
            if Parameters.SHOW_VIDEO_WINDOW:
                # GUI mode: cv2.waitKey for timing and input
                key = cv2.waitKey(self.controller.video_handler.delay_frame)
                if key == ord('q'):
                    self.controller.shutdown_flag = True
                else:
                    loop.run_until_complete(
                        self.controller.handle_key_input_async(key, frame)
                    )
            else:
                # Headless mode: sleep for timing
                time.sleep(self.controller.video_handler.delay_frame / 1000.0)

    except KeyboardInterrupt:
        logging.info("Keyboard interrupt - shutting down")
        self.controller.shutdown_flag = True

    # Cleanup
    self._perform_shutdown(loop)
```

## Shutdown Sequence

### Signal Handler

```python
def shutdown_handler(self, signum, frame):
    """
    Handle shutdown signals (SIGINT, SIGTERM).

    Args:
        signum: Signal number
        frame: Stack frame
    """
    if self._shutdown_initiated:
        return  # Prevent multiple shutdown calls

    logging.info(f"Shutdown signal {signum} received")
    self._shutdown_initiated = True
    self.controller.shutdown_flag = True
```

### Cleanup Process

```python
def _perform_shutdown(self, loop):
    """Perform graceful shutdown with timeout."""
    logging.info("Starting graceful shutdown...")

    # Emergency timeout (10 seconds)
    shutdown_timer = threading.Timer(10.0, lambda: os._exit(1))
    shutdown_timer.daemon = True
    shutdown_timer.start()

    try:
        # Stop AppController
        loop.run_until_complete(self.controller.shutdown())

        # Stop FastAPI server
        if hasattr(self.controller.api_handler, 'stop'):
            loop.run_until_complete(self.controller.api_handler.stop())

        # Wait for server thread
        self.server_thread.join(timeout=3.0)

        # Close OpenCV windows
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.destroyAllWindows()

    finally:
        shutdown_timer.cancel()
        logging.info("Shutdown complete")
        os._exit(0)
```

## Frame Timing

### GUI Mode

```python
# cv2.waitKey provides both timing and keyboard input
delay_ms = video_handler.delay_frame  # e.g., 33ms for 30fps
key = cv2.waitKey(delay_ms) & 0xFF
```

### Headless Mode

```python
# time.sleep for timing (no keyboard input)
delay_seconds = video_handler.delay_frame / 1000.0
time.sleep(delay_seconds)
```

## Keyboard Commands

| Key | Action |
|-----|--------|
| `q` | Quit application |
| `t` | Toggle tracking |
| `o` | Toggle offboard |
| `s` | Toggle smart mode |
| `r` | Redetect target |

## Error Handling

```python
try:
    # Main loop
    while not shutdown_flag:
        frame = video_handler.get_frame()
        if frame is None:
            break  # Video source ended
        # ...

except KeyboardInterrupt:
    # Clean shutdown on Ctrl+C
    shutdown_flag = True

except Exception as e:
    logging.error(f"Unexpected error: {e}")
    shutdown_flag = True
```

## Thread Safety

### Thread Overview

| Thread | Responsibility |
|--------|---------------|
| Main | Frame processing, CV2 window |
| FastAPI | HTTP server, WebSocket |

### Coordination

- `shutdown_flag` is checked by main loop
- Signal handler sets flag, doesn't block
- Server thread is joined with timeout

## Configuration

```yaml
# config_default.yaml

http:
  host: "0.0.0.0"
  port: 8000

video:
  show_window: true  # GUI vs headless
  target_fps: 30
```

## Usage

```python
# main.py
from classes.flow_controller import FlowController

if __name__ == "__main__":
    controller = FlowController()
    controller.main_loop()
```

## Related Components

- [AppController](app-controller.md) - Orchestrates subsystems
- [FastAPIHandler](fastapi-handler.md) - HTTP server
- [VideoHandler](../../video/02-components/video-handler.md) - Frame capture
