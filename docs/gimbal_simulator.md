# PixEagle Gimbal Simulator Documentation

Complete documentation for the PixEagle Gimbal Simulator - a single-file solution for testing gimbal tracking functionality without physical hardware.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [PixEagle Configuration](#pixeagle-configuration)
4. [Simulator Interface](#simulator-interface)
5. [Manual Target Control](#manual-target-control)
6. [Testing Workflows](#testing-workflows)
7. [Development Guide](#development-guide)
8. [Protocol Implementation](#protocol-implementation)
9. [Troubleshooting](#troubleshooting)
10. [Advanced Usage](#advanced-usage)

## Overview

The PixEagle Gimbal Simulator is a comprehensive testing tool that emulates real gimbal hardware for development and testing purposes. It provides:

- **Complete SIP Protocol Implementation**: Full compatibility with PixEagle's GimbalTracker
- **Manual Target Positioning**: Precise control for testing specific scenarios
- **Auto Tracking Patterns**: Realistic movement simulation
- **Real-time GUI Control**: Intuitive interface for all parameters
- **Zero Hardware Dependencies**: Test complete gimbal tracking workflows

### Architecture

```
┌─────────────────┐    UDP Commands     ┌──────────────────┐
│                 │◄────────────────────┤                  │
│ Gimbal Simulator│                     │    PixEagle      │
│                 ├────────────────────►│  GimbalTracker   │
└─────────────────┘    UDP Broadcast    └──────────────────┘
     gimbal_simulator.py                   classes/trackers/gimbal_tracker.py

Protocol: SIP (Session Initiation Protocol) for Gimbal Control
Ports: 9003 (commands), 9004 (broadcast data)
```

## Quick Start

### 1. Start the Simulator

```bash
cd /path/to/PixEagle
python gimbal_simulator.py
```

The GUI will open automatically with all controls ready.

### 2. Configure PixEagle

Edit your PixEagle configuration file (`configs/config.yaml`):

```yaml
# Gimbal Simulator Configuration (replace existing gimbal settings)
GIMBAL_UDP_HOST: "127.0.0.1"       # Localhost instead of real gimbal IP
GIMBAL_LISTEN_PORT: 9004           # Port where PixEagle receives gimbal data
GIMBAL_CONTROL_PORT: 9003          # Port where PixEagle sends commands

# Keep existing gimbal behavior settings
GIMBAL_COORDINATE_SYSTEM: "SPATIAL_FIXED"
GIMBAL_DISABLE_ESTIMATOR: true
```

### 3. Test Integration

1. **Start PixEagle**: Run normally
2. **Select GimbalTracker**: In PixEagle UI
3. **Set State to "Active"**: In simulator GUI
4. **Move Controls**: Adjust gimbal angles or targets
5. **Verify Data Flow**: Check PixEagle receives angle data

## PixEagle Configuration

### Required Configuration Changes

To use the simulator instead of real hardware, modify these specific settings in your PixEagle configuration:

#### Original Configuration (Real Hardware)
```yaml
# Example real gimbal configuration
GIMBAL_UDP_HOST: "192.168.0.108"   # Real gimbal IP
GIMBAL_LISTEN_PORT: 9004           # Real gimbal broadcast port
GIMBAL_CONTROL_PORT: 9003          # Real gimbal command port
```

#### Simulator Configuration
```yaml
# Simulator configuration (replace the above)
GIMBAL_UDP_HOST: "127.0.0.1"       # Simulator runs on localhost
GIMBAL_LISTEN_PORT: 9004           # Simulator broadcast port
GIMBAL_CONTROL_PORT: 9003          # Simulator command port
```

### Complete Configuration Example

```yaml
# configs/config.yaml - Complete gimbal section for simulator

# =============================================================================
# GIMBAL SIMULATOR CONFIGURATION
# =============================================================================

# Network settings (CRITICAL - must match simulator)
GIMBAL_UDP_HOST: "127.0.0.1"           # Simulator host
GIMBAL_LISTEN_PORT: 9004               # Data from simulator to PixEagle
GIMBAL_CONTROL_PORT: 9003              # Commands from PixEagle to simulator

# Gimbal behavior settings (keep your existing values)
GIMBAL_COORDINATE_SYSTEM: "SPATIAL_FIXED"  # or "GIMBAL_BODY"
GIMBAL_DISABLE_ESTIMATOR: true            # Use direct gimbal angles
GIMBAL_TRACKING_TIMEOUT: 5.0              # Seconds before data considered stale

# Angle limits (should match simulator capabilities)
GIMBAL_YAW_MIN: -180.0                    # Degrees
GIMBAL_YAW_MAX: 180.0
GIMBAL_PITCH_MIN: -90.0
GIMBAL_PITCH_MAX: 90.0
GIMBAL_ROLL_MIN: -45.0
GIMBAL_ROLL_MAX: 45.0

# Tracking parameters (keep your existing values)
TRACKING_UPDATE_RATE: 10                  # Hz
TRACKING_NOISE_THRESHOLD: 0.5             # Degrees

# =============================================================================
# OTHER SETTINGS (unchanged)
# =============================================================================
# Keep all your other PixEagle settings as they were
```

### Configuration Validation

After updating the configuration:

1. **Check File Syntax**: Ensure YAML is valid
2. **Restart PixEagle**: Load new configuration
3. **Verify Connection**: Look for log messages like:
   ```
   INFO - GimbalInterface ready - listening on port 9004
   INFO - Gimbal tracking state change: DISABLED → TRACKING_ACTIVE
   ```

## Simulator Interface

### GUI Layout

```
┌─ Gimbal Control ─────────────────────────────────────────┐
│  Yaw:   [-180° ────●──── +180°]  +15.0°                 │
│  Pitch: [-90°  ────●──── +90° ]  -10.0°                 │
│  Roll:  [-45°  ────●──── +45° ]  +0.0°                  │
└──────────────────────────────────────────────────────────┘

┌─ Tracking State ─────────────────────────────────────────┐
│  ○ Disabled  ○ Selection  ●Active  ○ Lost               │
└──────────────────────────────────────────────────────────┘

┌─ Target Control ─────────────────────────────────────────┐
│  ●Auto Patterns  ○Manual Target                         │
│  Pattern: [Circular  ▼]                                 │
│                                                          │
│  Target Yaw:   [-180° ────●──── +180°]  +30.0°         │
│  Target Pitch: [-90°  ────●──── +90° ]  -15.0°         │
└──────────────────────────────────────────────────────────┘

┌─ Status ─────────────────────────────────────────────────┐
│  Gimbal: Y=+15.0° P=-10.0° R=+0.0° | State: TRACKING_   │
│  ACTIVE | Target(Manual): Y=+30.0° P=-15.0° | Packets:  │
│  1250                                                    │
└──────────────────────────────────────────────────────────┘
```

### Control Elements

#### Gimbal Position Controls
- **Yaw Slider**: Horizontal gimbal rotation (-180° to +180°)
- **Pitch Slider**: Vertical gimbal tilt (-90° to +90°)
- **Roll Slider**: Camera roll rotation (-45° to +45°)
- **Real-time Display**: Shows exact angles as you adjust

#### Tracking State Controls
- **Disabled**: Gimbal idle, no tracking active
- **Selection**: Waiting for target selection (intermediate state)
- **Active**: Actively tracking target (main testing state)
- **Lost**: Target lost, testing recovery scenarios

#### Target Control Modes

**Auto Patterns Mode**:
- **Circular**: Target moves in smooth circular pattern
- **Figure8**: Target follows figure-8 trajectory
- **Random**: Target moves with random walk pattern

**Manual Target Mode**:
- **Target Yaw Slider**: Set exact horizontal target position
- **Target Pitch Slider**: Set exact vertical target position
- **Real-time Tracking**: Gimbal smoothly moves toward target

## Manual Target Control

Manual target control allows precise positioning for specific test scenarios.

### Enabling Manual Mode

1. **Set Tracking State**: Select "Active" to enable tracking
2. **Select Mode**: Choose "Manual Target" radio button
3. **Position Target**: Use target sliders to set position
4. **Observe Tracking**: Watch gimbal smoothly track to target

### Use Cases

#### Precision Testing
```
Test Case: Follower Accuracy
1. Set manual target to +45° yaw, -20° pitch
2. Wait for gimbal to reach target
3. Measure follower response accuracy
4. Verify PixEagle reports correct position
```

#### Boundary Testing
```
Test Case: Gimbal Limits
1. Set target beyond gimbal limits (+200° yaw)
2. Verify gimbal stops at maximum (+180°)
3. Test follower boundary handling
4. Ensure no crashes or invalid states
```

#### Response Time Testing
```
Test Case: Dynamic Response
1. Start at center position (0°, 0°)
2. Rapidly change target to (+90°, +45°)
3. Measure time for gimbal to reach target
4. Evaluate follower response lag
```

### Manual Target Parameters

- **Range**: Full gimbal range (-180° to +180° yaw, -90° to +90° pitch)
- **Resolution**: 0.1° precision via sliders
- **Update Rate**: Real-time, immediate response
- **Tracking Speed**: Realistic gimbal movement simulation
- **Smoothing**: Natural acceleration/deceleration curves

## Testing Workflows

### Basic Integration Test

**Objective**: Verify PixEagle can receive gimbal data

```
Steps:
1. Start simulator: python gimbal_simulator.py
2. Configure PixEagle with simulator settings
3. Start PixEagle and select GimbalTracker
4. Set simulator state to "Active"
5. Move gimbal sliders
6. Verify angles appear in PixEagle interface

Expected Result:
- PixEagle shows live angle updates
- No connection errors in logs
- Smooth data flow
```

### Tracking State Workflow Test

**Objective**: Test all tracking state transitions

```
Test Sequence:
1. DISABLED → TARGET_SELECTION:
   - PixEagle should show "waiting for target"
   - Follower should be idle

2. TARGET_SELECTION → TRACKING_ACTIVE:
   - PixEagle should begin active tracking
   - Follower should start responding

3. TRACKING_ACTIVE → TARGET_LOST:
   - PixEagle should handle loss gracefully
   - Follower should maintain last known position

4. TARGET_LOST → TRACKING_ACTIVE:
   - PixEagle should resume tracking
   - Follower should re-engage smoothly
```

### Auto Pattern Testing

**Objective**: Validate follower response to moving targets

```
Circular Pattern Test:
1. Set tracking to "Active"
2. Select "Auto Patterns" → "Circular"
3. Observe continuous circular motion
4. Monitor follower tracking accuracy
5. Measure maximum tracking error

Figure-8 Pattern Test:
1. Select "Figure8" pattern
2. Observe complex trajectory
3. Test follower adaptation to direction changes
4. Verify smooth tracking through pattern crossings

Random Pattern Test:
1. Select "Random" pattern
2. Observe unpredictable movement
3. Test follower robustness to sudden changes
4. Validate tracking stability with noise
```

### Manual Target Testing

**Objective**: Test precise positioning and response

```
Step Response Test:
1. Enable Manual Target mode
2. Set initial target: 0°, 0°
3. Step change to: +45°, -30°
4. Measure:
   - Gimbal response time
   - Follower response time
   - Final position accuracy
   - Overshoot/settling behavior

Tracking Accuracy Test:
1. Set specific target positions:
   - Corner positions: (±180°, ±90°)
   - Center positions: (0°, 0°)
   - Off-center: (+45°, -20°)
2. For each position:
   - Verify gimbal reaches target
   - Check PixEagle position reporting
   - Validate follower accuracy
```

## Development Guide

### Simulator Architecture

The simulator consists of several key components:

#### Core Classes

```python
class GimbalSimulator:
    """Main simulator engine"""
    - Network communication (UDP sockets)
    - SIP protocol implementation
    - State management
    - Auto tracking patterns
    - Manual target control

class GimbalSimulatorGUI:
    """GUI interface"""
    - Tkinter-based interface
    - Real-time control binding
    - Status display
    - Event handling
```

#### Threading Model

```
Main Thread: GUI event loop
├── Command Thread: Process incoming SIP commands
├── Broadcast Thread: Send angle data to PixEagle
└── Auto Track Thread: Generate automatic movement patterns
```

### Extending the Simulator

#### Adding Custom Tracking Patterns

```python
def _update_custom_pattern(self, dt: float):
    """Custom tracking pattern implementation"""
    elapsed = time.time() - self.tracking_start_time

    # Your pattern logic here
    self.target_yaw = custom_yaw_function(elapsed)
    self.target_pitch = custom_pitch_function(elapsed)

    # Apply to gimbal
    self.current_yaw += (self.target_yaw - self.current_yaw) * dt * 2.0
    self.current_pitch += (self.target_pitch - self.current_pitch) * dt * 2.0
```

#### Modifying Protocol Responses

```python
def _process_custom_command(self, command: str) -> Optional[str]:
    """Handle custom SIP commands"""
    if 'CUSTOM' in command:
        # Your custom response logic
        return self._build_custom_response()
    return None
```

#### Adding New GUI Controls

```python
def add_custom_control(self, parent_frame):
    """Add custom GUI control"""
    custom_frame = ttk.LabelFrame(parent_frame, text="Custom Control")

    # Add your controls here
    custom_slider = ttk.Scale(custom_frame, from_=0, to=100,
                             command=self.on_custom_change)
    custom_slider.pack()
```

### Configuration Customization

#### Network Settings

```python
# In gimbal_simulator.py, modify SimulatorConfig:
@dataclass
class SimulatorConfig:
    listen_port: int = 9003        # Change for different port
    broadcast_port: int = 9004     # Change for different port
    broadcast_host: str = "127.0.0.1"  # Change for remote host
    broadcast_interval: float = 0.1     # Change update rate
```

#### Gimbal Limits

```python
# Modify angle limits:
yaw_min: float = -180.0      # Minimum yaw angle
yaw_max: float = 180.0       # Maximum yaw angle
pitch_min: float = -90.0     # Minimum pitch angle
pitch_max: float = 90.0      # Maximum pitch angle
roll_min: float = -45.0      # Minimum roll angle
roll_max: float = 45.0       # Maximum roll angle
```

#### Tracking Behavior

```python
# Modify tracking characteristics:
tracking_noise: float = 0.2        # Random noise amplitude
auto_track_radius: float = 20.0    # Pattern size
auto_track_speed: float = 10.0     # Movement speed
```

### Integration with PixEagle

#### GimbalTracker Integration

The simulator works with PixEagle's existing `GimbalTracker` class:

```python
# classes/trackers/gimbal_tracker.py
class GimbalTracker(BaseTracker):
    def __init__(self):
        # Connects to simulator automatically
        self.gimbal_interface = GimbalInterface(
            listen_port=9004,    # Receives simulator broadcasts
            gimbal_ip="127.0.0.1",
            control_port=9003    # Sends commands to simulator
        )
```

#### Data Flow

```
Simulator → UDP Broadcast → GimbalInterface → GimbalTracker → PixEagle UI
     ↑                                                              ↓
   SIP Commands ← GimbalInterface ← GimbalTracker ← User Controls ←─┘
```

### Testing Infrastructure

#### Automated Testing

```python
def automated_test_sequence():
    """Run automated test sequence"""
    simulator = GimbalSimulator()
    simulator.start()

    try:
        # Test basic functionality
        simulator.set_gimbal_angles(30, -15, 0)
        time.sleep(1)

        # Test tracking states
        simulator.set_tracking_state(SimulatedTrackingState.TRACKING_ACTIVE)
        time.sleep(1)

        # Test manual targets
        simulator.set_manual_target(45, 20)
        time.sleep(2)

        # Verify final state
        state = simulator.get_state()
        assert abs(state['angles']['yaw'] - 45) < 1.0

    finally:
        simulator.stop()
```

#### Performance Testing

```python
def performance_test():
    """Test simulator performance"""
    start_time = time.time()
    packet_count = 0

    # Monitor for 30 seconds
    while time.time() - start_time < 30:
        packet_count += 1
        time.sleep(0.1)

    rate = packet_count / 30.0
    print(f"Update rate: {rate} Hz")
    assert rate >= 9.0  # Should be close to 10 Hz
```

## Protocol Implementation

### SIP Protocol Details

The simulator implements the complete SIP (Session Initiation Protocol) for gimbal control:

#### Command Types

**GAC (Gimbal Angle Command) - Body Coordinates**
```
Request:  #tpPG2rGAC00XX
Response: #tpUG2rGACYYYYPPPPRRRRXX

Where:
- YYYY = Yaw angle in hex (0.01° units)
- PPPP = Pitch angle in hex (0.01° units)
- RRRR = Roll angle in hex (0.01° units)
- XX = Checksum
```

**GIC (Gimbal Information Command) - Spatial Coordinates**
```
Request:  #tpPG2rGIC00XX
Response: #tpUG2rGICYYYYPPPPRRRRXX

Same format as GAC but in spatial reference frame
```

**TRC (Tracking Command) - Status Query**
```
Request:  #tpDG2rTRC00XX
Response: #tpUD2rTRC0SXX

Where:
- S = Tracking state (0=DISABLED, 1=SELECTION, 2=ACTIVE, 3=LOST)
```

#### Broadcast Format

**Continuous Angle Broadcast**
```
Format: #tpDP9wOFTYYYYPPPPRRRR

Sent every 100ms (10 Hz) containing current gimbal angles
```

#### Angle Encoding

Angles are encoded in 16-bit signed integers representing 0.01° units:

```python
def angle_to_hex(angle_degrees: float) -> str:
    """Convert angle to hex format"""
    # Convert to 0.01° units
    angle_units = int(round(angle_degrees * 100))

    # Handle negative values (two's complement)
    if angle_units < 0:
        angle_units = 65536 + angle_units

    # Clamp to 16-bit range
    angle_units = max(0, min(65535, angle_units))

    return f"{angle_units:04X}"

# Examples:
# +45.67° → 4567 units → 0x11D7
# -12.34° → -1234 units → 0xFB2E (65536 - 1234)
```

### Error Handling

The simulator includes comprehensive error handling:

#### Network Errors
- Socket binding failures
- Port conflicts
- Network timeouts
- Malformed packets

#### Protocol Errors
- Invalid command format
- Checksum mismatches
- Out-of-range values
- Unsupported commands

#### State Errors
- Invalid state transitions
- Angle limit violations
- Threading synchronization

## Troubleshooting

### Common Issues

#### Simulator Won't Start

**Problem**: Error on startup
```
Solutions:
1. Check Python version (requires 3.6+)
2. Install tkinter:
   - Ubuntu/Debian: sudo apt-get install python3-tk
   - CentOS/RHEL: sudo yum install tkinter
3. Check port availability:
   - netstat -an | grep 9003
   - netstat -an | grep 9004
4. Try different ports if occupied
```

#### PixEagle Can't Connect

**Problem**: No gimbal data in PixEagle
```
Solutions:
1. Verify configuration:
   - GIMBAL_UDP_HOST: "127.0.0.1"
   - GIMBAL_LISTEN_PORT: 9004
   - GIMBAL_CONTROL_PORT: 9003

2. Check simulator status:
   - Status should show increasing packet count
   - State should be "Active" for data flow

3. Test network connectivity:
   - ping 127.0.0.1
   - telnet 127.0.0.1 9003

4. Check firewall settings:
   - Temporarily disable firewall
   - Add exceptions for ports 9003, 9004
```

#### No Angle Data Flow

**Problem**: PixEagle shows no gimbal angles
```
Solutions:
1. Set tracking state to "Active" in simulator
2. Select "GimbalTracker" in PixEagle interface
3. Check PixEagle logs for connection messages
4. Verify configuration file syntax (YAML format)
5. Restart both simulator and PixEagle
```

#### GUI Issues

**Problem**: Interface problems or crashes
```
Solutions:
1. Linux: Install python3-tk package
2. Windows: Usually works out of box
3. Mac: Install tkinter via homebrew
4. Check Python GUI support: python -m tkinter
5. Run from command line to see error messages
```

### Debug Information

#### Enable Verbose Logging

```python
# In gimbal_simulator.py, change logging level:
logging.basicConfig(level=logging.DEBUG,
                   format='%(asctime)s - %(levelname)s - %(message)s')
```

#### Monitor Network Traffic

```bash
# Windows
netstat -an | findstr 9003
netstat -an | findstr 9004

# Linux/Mac
ss -ulnp | grep 9003
ss -ulnp | grep 9004

# Monitor packets
tcpdump -i lo -p udp port 9003 or udp port 9004
```

#### Check PixEagle Logs

Look for these log messages:
```
INFO - GimbalInterface ready - listening on port 9004
INFO - Gimbal tracking state change: DISABLED → TRACKING_ACTIVE
INFO - Gimbal angles: Y=15.0° P=-10.0° R=0.0° | spatial_fixed
```

### Performance Issues

#### High CPU Usage

```
Causes:
- Very high update rates
- GUI update frequency too high
- Multiple simulator instances

Solutions:
- Reduce broadcast_interval (increase from 0.1)
- Optimize GUI update frequency
- Check for multiple instances running
```

#### Network Latency

```
Causes:
- Network congestion
- Firewall processing
- High system load

Solutions:
- Use localhost (127.0.0.1) for local testing
- Adjust network buffer sizes
- Reduce update frequency if needed
```

## Advanced Usage

### Multi-Instance Testing

Run multiple simulators for complex scenarios:

```bash
# Primary gimbal (default ports)
python gimbal_simulator.py

# Secondary gimbal (modified ports)
# Edit gimbal_simulator.py:
# listen_port: int = 9013
# broadcast_port: int = 9014
python gimbal_simulator.py
```

### Automated Testing Scripts

Create Python scripts for automated validation:

```python
#!/usr/bin/env python3
"""Automated gimbal simulator test suite"""

import time
import sys
import os

# Add simulator to path
sys.path.append(os.path.dirname(__file__))
from gimbal_simulator import GimbalSimulator, SimulatedTrackingState

def run_test_suite():
    """Run complete test suite"""
    simulator = GimbalSimulator()

    if not simulator.start():
        print("FAIL: Simulator failed to start")
        return False

    try:
        # Test 1: Basic angle setting
        print("Test 1: Basic angle control...")
        simulator.set_gimbal_angles(30, -15, 5)
        time.sleep(1)

        state = simulator.get_state()
        if abs(state['angles']['yaw'] - 30) > 0.1:
            print("FAIL: Angle setting incorrect")
            return False
        print("PASS: Basic angle control")

        # Test 2: Tracking state changes
        print("Test 2: Tracking state control...")
        simulator.set_tracking_state(SimulatedTrackingState.TRACKING_ACTIVE)
        time.sleep(0.5)

        state = simulator.get_state()
        if state['tracking_state'] != 'TRACKING_ACTIVE':
            print("FAIL: Tracking state not updated")
            return False
        print("PASS: Tracking state control")

        # Test 3: Manual target control
        print("Test 3: Manual target control...")
        simulator.set_manual_target(45, 20)
        time.sleep(2)  # Allow time for tracking

        state = simulator.get_state()
        if not state['manual_target_mode']:
            print("FAIL: Manual target mode not enabled")
            return False
        print("PASS: Manual target control")

        # Test 4: Auto pattern switching
        print("Test 4: Auto pattern control...")
        simulator.set_auto_pattern("circular")
        time.sleep(1)

        state = simulator.get_state()
        if state['auto_pattern'] != 'circular':
            print("FAIL: Auto pattern not updated")
            return False
        print("PASS: Auto pattern control")

        print("ALL TESTS PASSED!")
        return True

    except Exception as e:
        print(f"ERROR: Test failed with exception: {e}")
        return False

    finally:
        simulator.stop()

if __name__ == "__main__":
    success = run_test_suite()
    sys.exit(0 if success else 1)
```

### Custom Protocol Extensions

Extend the simulator for custom testing needs:

```python
def _process_custom_command(self, command: str) -> Optional[str]:
    """Handle custom test commands"""
    if 'TEST' in command:
        # Extract test parameters
        if 'STRESS' in command:
            # Enable stress test mode
            self.config.broadcast_interval = 0.01  # 100Hz
            return "#tpTEST_STRESS_ENABLED"

        elif 'NOISE' in command:
            # Enable high noise mode
            self.config.tracking_noise = 2.0  # High noise
            return "#tpTEST_NOISE_ENABLED"

    return None
```

### Performance Optimization

For high-performance testing scenarios:

```python
# High-speed configuration
@dataclass
class HighSpeedConfig(SimulatorConfig):
    broadcast_interval: float = 0.02    # 50Hz updates
    tracking_noise: float = 0.05        # Minimal noise
    auto_track_speed: float = 30.0      # Fast movement
```

### Integration with CI/CD

Use the simulator in automated testing pipelines:

```yaml
# .github/workflows/gimbal_test.yml
name: Gimbal Integration Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.8

    - name: Install dependencies
      run: |
        sudo apt-get install python3-tk
        pip install -r requirements.txt

    - name: Run gimbal simulator tests
      run: |
        python test_gimbal_simulator.py

    - name: Run PixEagle integration test
      run: |
        python gimbal_simulator.py &
        sleep 2
        python test_pixeagle_gimbal_integration.py
        pkill -f gimbal_simulator
```

---

## Summary

The PixEagle Gimbal Simulator provides a complete testing environment for gimbal tracking development:

- **Simple Setup**: Single file, auto-configuring
- **Complete Protocol**: Full SIP compatibility
- **Comprehensive Testing**: Manual and automatic modes
- **Development Ready**: Extensible architecture
- **Production Quality**: Robust error handling

This documentation provides everything needed for effective use of the simulator in development, testing, and demonstration scenarios.