# src/classes/gimbal_interface.py

"""
GimbalInterface Module - Passive UDP Listener
=============================================

This module provides a passive UDP listener for gimbal systems that are controlled
by external applications. It receives real-time gimbal data including angles and
tracking status without sending any commands to the gimbal.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The GimbalInterface class is designed for the workflow where:
1. External camera UI application controls gimbal tracking (start/stop)
2. Gimbal broadcasts UDP data containing angles and tracking status
3. PixEagle passively listens and activates following when tracking is active
4. No control commands are sent from PixEagle to gimbal

Key Features:
- ✅ Passive UDP listening only (no command sending)
- ✅ Tracking status detection from gimbal protocol
- ✅ Support for both GIMBAL_BODY and SPATIAL_FIXED coordinate systems
- ✅ Thread-safe data access with proper locking
- ✅ Connection health monitoring
- ✅ Automatic activation based on gimbal tracking state

Usage:
------
```python
gimbal = GimbalInterface(listen_port=9004)
gimbal.start_listening()

data = gimbal.get_current_data()
if data and data.tracking_status == TrackingState.TRACKING_ACTIVE:
    # Use data.angles for drone control
    yaw, pitch, roll = data.angles
```

Integration with PixEagle:
-------------------------
This module is used by GimbalTracker to receive data from external gimbal systems.
It never sends commands - all gimbal control happens through external applications.
"""

import socket
import time
import threading
import logging
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class CoordinateSystem(Enum):
    """Gimbal coordinate system modes"""
    GIMBAL_BODY = "gimbal_body"       # Relative to gimbal body (Magnetic mode)
    SPATIAL_FIXED = "spatial_fixed"   # Absolute spatial coordinates (Gyro mode)

class ConnectionStatus(Enum):
    """Connection status states"""
    DISCONNECTED = "disconnected"
    LISTENING = "listening"
    RECEIVING = "receiving"
    ERROR = "error"

class TrackingState(Enum):
    """Tracking system states from gimbal protocol"""
    DISABLED = 0          # Tracking not enabled
    TARGET_SELECTION = 1  # Waiting for target selection
    TRACKING_ACTIVE = 2   # Actively tracking target
    TARGET_LOST = 3       # Target temporarily lost

@dataclass
class GimbalAngles:
    """Container for gimbal angle data"""
    yaw: float                        # Horizontal rotation (-180 to +180 degrees)
    pitch: float                      # Vertical tilt (-90 to +90 degrees)
    roll: float                       # Camera roll (-180 to +180 degrees)
    coordinate_system: CoordinateSystem
    timestamp: datetime

    def is_valid(self) -> bool:
        """Check if angles are within valid ranges"""
        return (
            -180.0 <= self.yaw <= 180.0 and
            -90.0 <= self.pitch <= 90.0 and
            -180.0 <= self.roll <= 180.0
        )

    def to_tuple(self) -> Tuple[float, float, float]:
        """Convert to tuple format (yaw, pitch, roll)"""
        return (self.yaw, self.pitch, self.roll)

@dataclass
class TrackingStatus:
    """Current tracking system status from gimbal"""
    state: TrackingState
    target_x: Optional[int] = None    # Target X coordinate (if tracking)
    target_y: Optional[int] = None    # Target Y coordinate (if tracking)
    target_width: Optional[int] = None
    target_height: Optional[int] = None
    timestamp: datetime = None

    def is_tracking_active(self) -> bool:
        """Check if gimbal is actively tracking a target"""
        return self.state == TrackingState.TRACKING_ACTIVE

@dataclass
class GimbalData:
    """Complete gimbal data package"""
    angles: Optional[GimbalAngles] = None
    tracking_status: Optional[TrackingStatus] = None
    coordinate_system: Optional[CoordinateSystem] = None
    timestamp: datetime = None
    raw_packet: str = ""

    def is_tracking_active(self) -> bool:
        """Check if gimbal is actively tracking"""
        return (self.tracking_status and
                self.tracking_status.is_tracking_active())

class GimbalInterface:
    """
    Passive UDP listener for gimbal data reception.

    This class ONLY receives data from gimbal systems. It never sends commands
    or tries to control the gimbal. All gimbal control is handled by external
    camera UI applications.
    """

    def __init__(self, listen_port: int = 9004, gimbal_ip: str = "192.168.1.108"):
        """
        Initialize gimbal passive UDP listener.

        Args:
            listen_port (int): UDP port to listen on for gimbal data
            gimbal_ip (str): Expected gimbal IP for validation (optional)
        """
        self.listen_port = listen_port
        self.gimbal_ip = gimbal_ip

        # Network setup - only listening socket
        self.listen_socket: Optional[socket.socket] = None

        # Thread management
        self.running = False
        self.listener_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

        # Current state
        self.current_data: Optional[GimbalData] = None
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.last_data_time: Optional[float] = None

        # Statistics
        self.total_packets_received = 0
        self.invalid_packets_received = 0
        self.tracking_state_changes = 0
        self.last_tracking_state = TrackingState.DISABLED
        self.last_status_log_time = 0.0

        logger.info(f"GimbalInterface initialized as passive listener on port {listen_port}")

    def start_listening(self) -> bool:
        """
        Start passive UDP listening for gimbal data.

        Returns:
            bool: True if listening started successfully, False otherwise
        """
        if self.running:
            logger.warning("GimbalInterface already listening")
            return True

        try:
            logger.info("Starting passive gimbal UDP listener...")

            # Initialize listening socket only
            if not self._init_listening_socket():
                return False

            # Start background listener thread
            self.running = True
            self.listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
            self.listener_thread.start()

            # Allow thread to start
            time.sleep(0.1)

            # Set connection status
            with self.lock:
                self.connection_status = ConnectionStatus.LISTENING

            logger.info("Passive gimbal listener started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start gimbal listener: {e}")
            self.stop_listening()
            return False

    def stop_listening(self) -> None:
        """Stop gimbal data reception and cleanup resources."""
        if not self.running:
            return

        logger.info("Stopping gimbal listener...")
        self.running = False

        # Wait for listener thread to finish
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=2.0)

        # Close socket
        self._cleanup_socket()

        # Reset state
        with self.lock:
            self.connection_status = ConnectionStatus.DISCONNECTED
            self.current_data = None

        logger.info("Gimbal listener stopped")

    def get_current_data(self) -> Optional[GimbalData]:
        """
        Get current gimbal data including angles and tracking status.

        Returns:
            Optional[GimbalData]: Complete gimbal data or None if no recent data
        """
        with self.lock:
            if self.current_data and self._is_data_fresh():
                return self.current_data
            return None

    def get_current_angles(self) -> Optional[Tuple[float, float, float]]:
        """
        Get current gimbal angles as tuple (for backward compatibility).

        Returns:
            Optional[Tuple[float, float, float]]: (yaw, pitch, roll) in degrees or None
        """
        data = self.get_current_data()
        if data and data.angles:
            return data.angles.to_tuple()
        return None

    def get_tracking_status(self) -> Optional[TrackingState]:
        """
        Get current tracking status from gimbal.

        Returns:
            Optional[TrackingState]: Current tracking state or None
        """
        data = self.get_current_data()
        if data and data.tracking_status:
            return data.tracking_status.state
        return None

    def is_tracking_active(self) -> bool:
        """
        Check if gimbal is actively tracking a target.

        Returns:
            bool: True if gimbal is in TRACKING_ACTIVE state
        """
        data = self.get_current_data()
        return data.is_tracking_active() if data else False

    def get_connection_status(self) -> str:
        """
        Get current connection status.

        Returns:
            str: Connection status string
        """
        with self.lock:
            return self.connection_status.value

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about gimbal data reception.

        Returns:
            Dict[str, Any]: Statistics dictionary
        """
        with self.lock:
            data_age = (
                (time.time() - self.last_data_time)
                if self.last_data_time else float('inf')
            )

            current_data = self.current_data

            return {
                'connection_status': self.connection_status.value,
                'total_packets_received': self.total_packets_received,
                'invalid_packets_received': self.invalid_packets_received,
                'data_age_seconds': data_age,
                'has_current_data': current_data is not None,
                'data_fresh': self._is_data_fresh(),
                'tracking_state_changes': self.tracking_state_changes,
                'current_tracking_state': (
                    current_data.tracking_status.state.name
                    if current_data and current_data.tracking_status else 'UNKNOWN'
                ),
                'is_tracking_active': self.is_tracking_active(),
                'listen_port': self.listen_port
            }

    def _init_listening_socket(self) -> bool:
        """Initialize UDP listening socket."""
        try:
            # Create UDP socket for listening only
            self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listen_socket.bind(('0.0.0.0', self.listen_port))
            self.listen_socket.settimeout(0.1)  # Non-blocking with short timeout

            logger.debug(f"Listening socket initialized on port {self.listen_port}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize listening socket: {e}")
            self._cleanup_socket()
            return False

    def _cleanup_socket(self) -> None:
        """Clean up socket resources."""
        try:
            if self.listen_socket:
                self.listen_socket.close()
                self.listen_socket = None
        except Exception as e:
            logger.debug(f"Socket cleanup error (expected): {e}")

    def _listener_loop(self) -> None:
        """Background thread to receive gimbal data packets."""
        logger.debug("Gimbal passive listener thread started")

        while self.running:
            try:
                if not self.listen_socket:
                    time.sleep(0.1)
                    continue

                # Receive UDP packet (passive listening)
                data, addr = self.listen_socket.recvfrom(4096)
                packet = data.decode('utf-8', errors='replace').strip()

                if not packet:
                    continue

                logger.debug(f"Received gimbal packet from {addr}: {packet}")

                # Update statistics
                with self.lock:
                    self.total_packets_received += 1
                    self.connection_status = ConnectionStatus.RECEIVING

                # Parse complete gimbal data
                gimbal_data = self._parse_gimbal_packet(packet)
                if gimbal_data:
                    with self.lock:
                        self.current_data = gimbal_data
                        self.last_data_time = time.time()

                        # Track tracking state changes
                        if (gimbal_data.tracking_status and
                            gimbal_data.tracking_status.state != self.last_tracking_state):
                            self.tracking_state_changes += 1
                            old_state = self.last_tracking_state
                            new_state = gimbal_data.tracking_status.state
                            self.last_tracking_state = new_state
                            logger.info(f"Gimbal tracking state changed: {old_state.name} → {new_state.name}")

                    logger.debug(f"Updated gimbal data: tracking={gimbal_data.is_tracking_active()}")
                else:
                    with self.lock:
                        self.invalid_packets_received += 1

            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"Listener error: {e}")

        logger.debug("Gimbal passive listener thread stopped")

    def _parse_gimbal_packet(self, packet: str) -> Optional[GimbalData]:
        """
        Parse complete gimbal packet including angles and tracking status.

        Args:
            packet (str): Raw packet data from gimbal

        Returns:
            Optional[GimbalData]: Parsed gimbal data or None if invalid
        """
        try:
            gimbal_data = GimbalData(
                timestamp=datetime.now(),
                raw_packet=packet
            )

            # Parse angle data
            angles = self._parse_angle_response(packet)
            if angles:
                gimbal_data.angles = angles
                gimbal_data.coordinate_system = angles.coordinate_system

            # Parse tracking status
            tracking_status = self._parse_tracking_response(packet)
            if tracking_status:
                gimbal_data.tracking_status = tracking_status

            # Return data if we got at least one valid component
            if gimbal_data.angles or gimbal_data.tracking_status:
                return gimbal_data

            return None

        except Exception as e:
            logger.debug(f"Error parsing gimbal packet: {e}")
            return None

    def _parse_angle_response(self, response: str) -> Optional[GimbalAngles]:
        """Parse angle data from gimbal response (existing logic enhanced)."""
        try:
            response = response.strip()

            # Determine coordinate system and find angle data
            if "GAC" in response:  # Magnetic coding response
                coord_sys = CoordinateSystem.GIMBAL_BODY
                data_start = response.find("GAC") + 3
                # Extract 12-character angle data: YYYYPPPPRRRR
                angle_data = response[data_start:data_start + 12]
                if len(angle_data) != 12:
                    return None
                return self._parse_hex_angles(angle_data, coord_sys)

            elif "GIC" in response:  # Gyroscope response
                coord_sys = CoordinateSystem.SPATIAL_FIXED
                data_start = response.find("GIC") + 3
                # Extract 12-character angle data: YYYYPPPPRRRR
                angle_data = response[data_start:data_start + 12]
                if len(angle_data) != 12:
                    return None
                return self._parse_hex_angles(angle_data, coord_sys)

            else:
                return None

        except Exception as e:
            logger.debug(f"Angle parse error: {e}")
            return None

    def _parse_hex_angles(self, angle_data: str, coord_sys: CoordinateSystem) -> Optional[GimbalAngles]:
        """Parse hex-encoded angle data."""
        try:
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
            angles = GimbalAngles(
                yaw=yaw_raw / 100.0,
                pitch=pitch_raw / 100.0,
                roll=roll_raw / 100.0,
                coordinate_system=coord_sys,
                timestamp=datetime.now()
            )

            # Validate angles
            if not angles.is_valid():
                logger.warning(f"Invalid hex angles: {angles.yaw}, {angles.pitch}, {angles.roll}")
                return None

            return angles

        except Exception as e:
            logger.debug(f"Error parsing hex angles: {e}")
            return None


    def _parse_tracking_response(self, response: str) -> Optional[TrackingStatus]:
        """Parse tracking status from gimbal response (NEW FUNCTIONALITY)."""
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

            # Parse state value from protocol
            try:
                # The demo code shows states as single digit in second character
                state_val = int(state_data[1])
                state = TrackingState(state_val)
            except (ValueError, IndexError):
                # Fallback parsing if format is different
                try:
                    state_val = int(state_data)
                    state = TrackingState(state_val)
                except (ValueError, IndexError):
                    logger.debug(f"Could not parse tracking state from: {state_data}")
                    return None

            return TrackingStatus(
                state=state,
                timestamp=datetime.now()
            )

        except Exception as e:
            logger.debug(f"Tracking parse error: {e}")
            return None

    def _is_data_fresh(self) -> bool:
        """Check if current data is fresh (within reasonable timeout)."""
        if not self.last_data_time:
            return False
        return (time.time() - self.last_data_time) < 5.0  # 5 second timeout

    def _log_status_periodically(self) -> None:
        """Log status periodically for monitoring."""
        current_time = time.time()
        if current_time - self.last_status_log_time > 30.0:  # Every 30 seconds
            stats = self.get_statistics()
            logger.info(
                f"Gimbal Listener Status: {stats['connection_status']} | "
                f"Packets: {stats['total_packets_received']} "
                f"(Invalid: {stats['invalid_packets_received']}) | "
                f"Tracking: {stats['current_tracking_state']} | "
                f"Data Age: {stats['data_age_seconds']:.1f}s"
            )
            self.last_status_log_time = current_time