#!/usr/bin/env python3
"""
========================================================================
GIMBAL PROTOCOL DEMO - SAMPLE CODE FOR DEVELOPERS
========================================================================

This is a complete working example demonstrating the SIP series gimbal protocol.
Use this code to understand how to integrate gimbal control into your application.

WHAT THIS CODE DEMONSTRATES:
- Real-time angle reading (Camera vs Gimbal Body coordinate systems)
- Tracking status monitoring  
- Protocol command structure
- Error handling and connection management

COORDINATE SYSTEMS EXPLAINED:
- MAGNETIC MODE: Camera angles relative to gimbal body/aircraft
  └─ If aircraft tilts, camera maintains same angle relative to aircraft
- GYROSCOPE MODE: Camera angles relative to fixed spatial coordinates  
  └─ Camera maintains absolute orientation regardless of aircraft movement

TRACKING STATES:
- 0: Tracking disabled
- 1: Target selection mode (waiting for target)
- 2: Actively tracking target
- 3: Target temporarily lost

========================================================================
"""

import socket
import time
import struct
import threading
from datetime import datetime
from typing import Optional, Dict, Tuple
from enum import Enum
from dataclasses import dataclass

# ========================================================================
# CONFIGURATION - MODIFY THESE VALUES FOR YOUR SETUP
# ========================================================================

GIMBAL_CONFIG = {
    'camera_ip': '192.168.0.108',    # Replace with your gimbal IP
    'control_port': 9003,              # Gimbal control port (standard)
    'listen_port': 9004                # Our listening port (standard)
}

# ========================================================================
# DATA STRUCTURES
# ========================================================================

class CoordinateSystem(Enum):
    """Camera coordinate system modes"""
    GIMBAL_BODY = "gimbal_body"       # Relative to gimbal body (Magnetic mode)
    SPATIAL_FIXED = "spatial_fixed"   # Absolute spatial coordinates (Gyro mode)

class TrackingState(Enum):
    """Tracking system states"""
    DISABLED = 0          # Tracking not enabled
    TARGET_SELECTION = 1  # Waiting for target selection
    TRACKING_ACTIVE = 2   # Actively tracking target
    TARGET_LOST = 3       # Target temporarily lost

@dataclass
class CameraAngles:
    """Real-time camera angle data"""
    yaw: float                      # Horizontal rotation (-180 to +180 degrees)
    pitch: float                    # Vertical tilt (-90 to +90 degrees)  
    roll: float                     # Camera roll (-180 to +180 degrees)
    coordinate_system: CoordinateSystem
    timestamp: datetime
    
    def __str__(self) -> str:
        return (f"YAW: {self.yaw:+7.2f}° | PITCH: {self.pitch:+7.2f}° | "
                f"ROLL: {self.roll:+7.2f}° | System: {self.coordinate_system.value}")

@dataclass 
class TrackingStatus:
    """Current tracking system status"""
    state: TrackingState
    target_x: Optional[int] = None    # Target X coordinate (if tracking)
    target_y: Optional[int] = None    # Target Y coordinate (if tracking)
    target_width: Optional[int] = None
    target_height: Optional[int] = None
    timestamp: datetime = None
    
    def __str__(self) -> str:
        status = f"TRACKING: {self.state.name}"
        if self.state == TrackingState.TRACKING_ACTIVE and self.target_x is not None:
            status += f" | Target: ({self.target_x}, {self.target_y}) {self.target_width}x{self.target_height}"
        return status

# ========================================================================
# MAIN GIMBAL INTERFACE CLASS
# ========================================================================

class GimbalProtocolDemo:
    """
    Complete gimbal interface demonstration
    
    This class shows how to:
    - Connect to the gimbal via UDP
    - Read real-time camera angles
    - Monitor tracking status
    - Send control commands
    """
    
    def __init__(self, config: Dict = None):
        """Initialize gimbal connection"""
        config = config or GIMBAL_CONFIG
        
        self.camera_ip = config['camera_ip']
        self.control_port = config['control_port']
        self.listen_port = config['listen_port']
        
        # Network setup
        self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
        self.listen_socket.bind(('0.0.0.0', self.listen_port))
        self.listen_socket.settimeout(0.1)
        
        # Current state
        self.current_angles: Optional[CameraAngles] = None
        self.tracking_status: Optional[TrackingStatus] = None
        self.running = False
        self.lock = threading.Lock()
        
        # Threads
        self.listener_thread: Optional[threading.Thread] = None
        self.angle_query_thread: Optional[threading.Thread] = None
        
        print(f"🔗 Gimbal connection configured: {self.camera_ip}:{self.control_port}")

    # ========================================================================
    # PROTOCOL COMMAND METHODS
    # ========================================================================
    
    def _build_command(self, address_dest: str, control: str, command: str, data: str = "00") -> str:
        """Build protocol command according to SIP specification"""
        frame = f"#TP"  # Fixed length command
        src = "P"       # Network source address
        length = "2"    # Fixed length
        
        # Build command string
        cmd = f"{frame}{src}{address_dest}{length}{control}{command}{data}"
        
        # Calculate CRC (sum of all bytes mod 256)
        crc = sum(cmd.encode('ascii')) & 0xFF
        cmd += f"{crc:02X}"
        
        return cmd
    
    def _send_command(self, command: str) -> bool:
        """Send UDP command to gimbal"""
        try:
            self.control_socket.sendto(command.encode('ascii'), 
                                     (self.camera_ip, self.control_port))
            print(f"📤 Sent: {command}")
            return True
        except Exception as e:
            print(f"❌ Command failed: {e}")
            return False
    
    # ========================================================================
    # ANGLE READING METHODS
    # ========================================================================
    
    def query_gimbal_body_angles(self) -> bool:
        """
        Read camera angles relative to gimbal body (Magnetic Coding)
        
        Use this when you want angles relative to the aircraft/gimbal mount.
        Example: If aircraft tilts 30°, camera at 0° pitch relative to aircraft.
        """
        command = self._build_command("G", "r", "GAC", "00")
        return self._send_command(command)
    
    def query_spatial_fixed_angles(self) -> bool:
        """
        Read camera angles in absolute spatial coordinates (Gyroscope) 
        
        Use this when you want absolute world coordinates.
        Example: Camera pointing straight down = -90° pitch regardless of aircraft attitude.
        """
        command = self._build_command("G", "r", "GIC", "00")
        return self._send_command(command)
        
    def enable_continuous_angle_updates(self, coordinate_system: CoordinateSystem) -> bool:
        """
        Enable automatic angle streaming for real-time updates
        
        Args:
            coordinate_system: Choose GIMBAL_BODY or SPATIAL_FIXED
        """
        if coordinate_system == CoordinateSystem.GIMBAL_BODY:
            command = self._build_command("G", "w", "GAA", "01")  # Enable magnetic
        else:
            command = self._build_command("G", "w", "GIA", "01")  # Enable gyro
            
        success = self._send_command(command)
        if success:
            print(f"✅ Continuous updates enabled: {coordinate_system.value}")
        return success
    
    # ========================================================================
    # TRACKING CONTROL METHODS  
    # ========================================================================
    
    def query_tracking_status(self) -> bool:
        """Query current tracking status"""
        command = self._build_command("D", "r", "TRC", "00")
        return self._send_command(command)
    
    def enable_tracking_mode(self) -> bool:
        """Enable tracking mode (allows target selection)"""
        command = self._build_command("D", "w", "TRC", "02")
        success = self._send_command(command)
        if success:
            print("🎯 Tracking mode enabled - ready for target selection")
        return success
    
    def disable_tracking(self) -> bool:
        """Completely disable tracking"""
        command = self._build_command("D", "w", "TRC", "00")
        success = self._send_command(command)
        if success:
            print("⏹️ Tracking disabled")
        return success
    
    # ========================================================================
    # DATA PARSING METHODS
    # ========================================================================
    
    def _parse_angle_response(self, response: str) -> Optional[CameraAngles]:
        """Parse angle data from gimbal response"""
        try:
            response = response.strip()
            
            # Determine coordinate system and find angle data
            if "GAC" in response:  # Magnetic coding response
                coord_sys = CoordinateSystem.GIMBAL_BODY
                data_start = response.find("GAC") + 3
            elif "GIC" in response:  # Gyroscope response  
                coord_sys = CoordinateSystem.SPATIAL_FIXED
                data_start = response.find("GIC") + 3
            else:
                return None
                
            # Extract 12-character angle data: YYYYPPPPRRRR
            angle_data = response[data_start:data_start + 12]
            if len(angle_data) != 12:
                return None
                
            # Parse hex values (4 chars each, signed 16-bit, 0.01° units)
            yaw_hex = angle_data[0:4]
            pitch_hex = angle_data[4:8]  
            roll_hex = angle_data[8:12]
            
            # Convert to signed integers
            yaw_raw = int(yaw_hex, 16)
            pitch_raw = int(pitch_hex, 16)
            roll_raw = int(roll_hex, 16)
            
            # Handle 16-bit signed values
            if yaw_raw > 32767: yaw_raw -= 65536
            if pitch_raw > 32767: pitch_raw -= 65536  
            if roll_raw > 32767: roll_raw -= 65536
            
            # Convert to degrees (protocol uses 0.01° resolution)
            return CameraAngles(
                yaw=yaw_raw / 100.0,
                pitch=pitch_raw / 100.0,
                roll=roll_raw / 100.0, 
                coordinate_system=coord_sys,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            print(f"⚠️ Angle parse error: {e}")
            return None
    
    def _parse_tracking_response(self, response: str) -> Optional[TrackingStatus]:
        """Parse tracking status from gimbal response"""
        try:
            response = response.strip()
            
            if "TRC" not in response:
                return None
                
            # Find tracking data after TRC identifier
            trc_pos = response.find("TRC") + 3
            if trc_pos + 2 > len(response):
                return None
                
            # Extract tracking state (2 characters)  
            state_data = response[trc_pos:trc_pos + 2]
            
            # Parse state value
            try:
                state_val = int(state_data[1])  # Second character is the state
                state = TrackingState(state_val)
            except (ValueError, KeyError):
                state = TrackingState.DISABLED
                
            return TrackingStatus(
                state=state,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            print(f"⚠️ Tracking parse error: {e}")
            return None
    
    # ========================================================================
    # BACKGROUND THREADS
    # ========================================================================
    
    def _listener_loop(self):
        """Background thread to receive gimbal responses"""
        print("🔄 Starting response listener...")
        
        while self.running:
            try:
                data, addr = self.listen_socket.recvfrom(4096)
                response = data.decode('utf-8', errors='replace').strip()
                
                if not response:
                    continue
                    
                print(f"📥 Received: {response}")
                
                # Parse angle data
                angles = self._parse_angle_response(response)
                if angles:
                    with self.lock:
                        self.current_angles = angles
                
                # Parse tracking data
                tracking = self._parse_tracking_response(response)
                if tracking:
                    with self.lock:
                        self.tracking_status = tracking
                        
            except socket.timeout:
                continue
            except Exception as e:
                print(f"⚠️ Listener error: {e}")
                
        print("🔄 Response listener stopped")
    
    def _angle_query_loop(self):
        """Background thread to periodically query angles"""
        print("🔄 Starting angle query loop...")
        
        while self.running:
            # Query both coordinate systems periodically
            self.query_gimbal_body_angles()
            time.sleep(0.5)
            
            self.query_spatial_fixed_angles() 
            time.sleep(0.5)
            
            # Query tracking status
            self.query_tracking_status()
            time.sleep(1.0)
            
        print("🔄 Angle query loop stopped")
    
    # ========================================================================
    # MAIN CONTROL METHODS
    # ========================================================================
    
    def start_monitoring(self, enable_continuous: bool = True, 
                        coordinate_system: CoordinateSystem = CoordinateSystem.SPATIAL_FIXED):
        """
        Start real-time monitoring
        
        Args:
            enable_continuous: Enable automatic streaming for better performance
            coordinate_system: Choose coordinate system for continuous updates
        """
        if self.running:
            print("⚠️ Already running!")
            return
            
        print("🚀 Starting gimbal monitoring...")
        self.running = True
        
        # Start background threads
        self.listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
        self.listener_thread.start()
        
        self.angle_query_thread = threading.Thread(target=self._angle_query_loop, daemon=True) 
        self.angle_query_thread.start()
        
        # Enable continuous updates if requested
        if enable_continuous:
            time.sleep(1)  # Let threads start
            self.enable_continuous_angle_updates(coordinate_system)
            
        print("✅ Monitoring started successfully!")
    
    def stop_monitoring(self):
        """Stop all monitoring"""
        if not self.running:
            return
            
        print("🛑 Stopping gimbal monitoring...")
        self.running = False
        
        # Wait for threads
        if self.listener_thread:
            self.listener_thread.join(timeout=2)
        if self.angle_query_thread:
            self.angle_query_thread.join(timeout=2)
            
        # Close sockets
        try:
            self.control_socket.close()
            self.listen_socket.close()
        except:
            pass
            
        print("✅ Monitoring stopped")
    
    def get_current_status(self) -> Tuple[Optional[CameraAngles], Optional[TrackingStatus]]:
        """Get current angles and tracking status"""
        with self.lock:
            return self.current_angles, self.tracking_status

# ========================================================================
# DEMONSTRATION / EXAMPLE USAGE
# ========================================================================

def display_realtime_data(gimbal: GimbalProtocolDemo):
    """Display real-time gimbal data in a clean format"""
    print("\n" + "="*80)
    print("🎥 REAL-TIME GIMBAL DATA DISPLAY")
    print("="*80)
    print("📊 Data will update automatically below...")
    print("🎯 Tracking status will show when available")
    print("⏸️  Press Ctrl+C to stop")
    print("="*80)
    
    try:
        last_update = time.time()
        
        while True:
            angles, tracking = gimbal.get_current_status()
            current_time = time.time()
            
            # Clear screen area for updates (simple approach)
            if current_time - last_update > 1.0:
                print(f"\n{'='*20} {datetime.now().strftime('%H:%M:%S')} {'='*20}")
                
                # Display camera angles
                if angles:
                    age = (datetime.now() - angles.timestamp).total_seconds()
                    print(f"📐 CAMERA ANGLES: {angles}")
                    print(f"   └─ Data age: {age:.1f}s | System: {angles.coordinate_system.value}")
                else:
                    print("📐 CAMERA ANGLES: No data received yet...")
                
                # Display tracking status  
                if tracking:
                    age = (datetime.now() - tracking.timestamp).total_seconds()
                    print(f"🎯 {tracking}")
                    print(f"   └─ Status age: {age:.1f}s")
                else:
                    print("🎯 TRACKING STATUS: Querying...")
                    
                last_update = current_time
                
            time.sleep(0.1)  # Update check frequency
            
    except KeyboardInterrupt:
        print("\n\n👋 Display stopped by user")

def main():
    """
    MAIN DEMONSTRATION FUNCTION
    
    This shows a complete example of how to use the gimbal in your application.
    Modify this code for your specific needs.
    """
    print("="*80)
    print("🎥 GIMBAL PROTOCOL DEMONSTRATION")
    print("="*80)
    print("This demo shows real-time camera angles and tracking status.")
    print("Perfect for learning the protocol and integrating into your app!")
    print("="*80)
    
    # Create gimbal interface
    gimbal = GimbalProtocolDemo(GIMBAL_CONFIG)
    
    try:
        # Start monitoring with spatial coordinates (absolute positioning)
        gimbal.start_monitoring(
            enable_continuous=True,
            coordinate_system=CoordinateSystem.SPATIAL_FIXED
        )
        
        # Optional: Enable tracking mode
        print("\n🎯 Enabling tracking mode for demonstration...")
        gimbal.enable_tracking_mode()
        
        # Start real-time display
        display_realtime_data(gimbal)
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Demonstration stopped by user")
    except Exception as e:
        print(f"\n❌ Error during demonstration: {e}")
    finally:
        gimbal.stop_monitoring()
        print("👋 Goodbye! Use this code as a starting point for your application.")

# ========================================================================
# INTEGRATION EXAMPLES FOR DEVELOPERS
# ========================================================================

def example_basic_integration():
    """
    EXAMPLE: Basic integration for your application
    """
    gimbal = GimbalProtocolDemo()
    
    # Start monitoring
    gimbal.start_monitoring()
    
    # Your application loop
    for i in range(100):  # Example: 100 iterations
        angles, tracking = gimbal.get_current_status()
        
        if angles:
            print(f"Camera pointing: Yaw={angles.yaw:.1f}°, Pitch={angles.pitch:.1f}°")
            
            # YOUR CODE HERE: Use angles for navigation, stabilization, etc.
            
        if tracking and tracking.state == TrackingState.TRACKING_ACTIVE:
            print("🎯 Target is being tracked!")
            
            # YOUR CODE HERE: React to tracking state
            
        time.sleep(0.1)
    
    gimbal.stop_monitoring()

def example_callback_integration():
    """
    EXAMPLE: Using callbacks for event-driven integration
    """
    def on_angle_update(angles: CameraAngles):
        """Called whenever new angle data arrives"""
        if angles.coordinate_system == CoordinateSystem.SPATIAL_FIXED:
            print(f"Absolute position: {angles.yaw:.1f}°, {angles.pitch:.1f}°, {angles.roll:.1f}°")
            
            # YOUR CODE: Update UI, log data, trigger actions, etc.
    
    def on_tracking_update(tracking: TrackingStatus):
        """Called whenever tracking status changes"""
        if tracking.state == TrackingState.TARGET_LOST:
            print("⚠️ Target lost! Taking corrective action...")
            
            # YOUR CODE: Handle tracking events
    
    # Set up gimbal with custom handlers
    gimbal = GimbalProtocolDemo()
    # Note: In a real implementation, you'd extend the class to support callbacks

if __name__ == "__main__":
    main()