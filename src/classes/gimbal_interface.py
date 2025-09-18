# src/classes/gimbal_interface.py

"""
GimbalInterface Module
=====================

This module provides a clean, thread-safe interface for communicating with gimbal systems
via UDP protocol. It's designed as a black box that PixEagle can use without knowing
the details of the gimbal communication protocol.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The GimbalInterface class handles:
- UDP socket management with automatic reconnection
- Real-time angle data reception (yaw, pitch, roll)
- Thread-safe data access with proper locking
- Connection health monitoring
- Support for both GIMBAL_BODY and SPATIAL_FIXED coordinate systems

Usage:
------
```python
gimbal = GimbalInterface('192.168.1.100', 8080, 5.0)
gimbal.start()

angles = gimbal.get_current_angles()
if angles:
    yaw, pitch, roll = angles
    # Use angles for navigation

gimbal.stop()
```

Integration with PixEagle:
-------------------------
This module is designed to be used by GimbalTracker as a data source.
The tracker doesn't need to know about UDP, sockets, or protocol details.
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
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

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

class GimbalInterface:
    """
    Thread-safe interface for gimbal UDP communication.

    This class provides a clean abstraction over the gimbal protocol,
    allowing PixEagle components to get angle data without dealing with
    UDP socket management, protocol parsing, or connection handling.
    """

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        """
        Initialize gimbal interface.

        Args:
            host (str): Gimbal IP address
            port (int): Gimbal UDP port
            timeout (float): Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout

        # Network setup
        self.control_socket: Optional[socket.socket] = None
        self.listen_socket: Optional[socket.socket] = None
        self.listen_port = port + 1  # Use port+1 for listening

        # Thread management
        self.running = False
        self.listener_thread: Optional[threading.Thread] = None
        self.query_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

        # Current state
        self.current_angles: Optional[GimbalAngles] = None
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.last_data_time: Optional[float] = None
        self.connection_attempts = 0
        self.max_connection_attempts = 3

        # Statistics
        self.total_packets_received = 0
        self.invalid_packets_received = 0
        self.last_status_log_time = 0.0

        logger.info(f"GimbalInterface initialized: {host}:{port} (listen port: {self.listen_port})")

    def start(self) -> bool:
        """
        Start gimbal communication threads.

        Returns:
            bool: True if started successfully, False otherwise
        """
        if self.running:
            logger.warning("GimbalInterface already running")
            return True

        try:
            logger.info("Starting gimbal interface...")

            # Initialize sockets
            if not self._init_sockets():
                return False

            # Start background threads
            self.running = True

            self.listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
            self.listener_thread.start()

            self.query_thread = threading.Thread(target=self._query_loop, daemon=True)
            self.query_thread.start()

            # Allow threads to start
            time.sleep(0.1)

            # Set initial connection status
            with self.lock:
                self.connection_status = ConnectionStatus.CONNECTING

            logger.info("GimbalInterface started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start gimbal interface: {e}")
            self.stop()
            return False

    def stop(self) -> None:
        """Stop gimbal communication and cleanup resources."""
        if not self.running:
            return

        logger.info("Stopping gimbal interface...")
        self.running = False

        # Wait for threads to finish
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=2.0)

        if self.query_thread and self.query_thread.is_alive():
            self.query_thread.join(timeout=2.0)

        # Close sockets
        self._cleanup_sockets()

        # Reset state
        with self.lock:
            self.connection_status = ConnectionStatus.DISCONNECTED
            self.current_angles = None

        logger.info("GimbalInterface stopped")

    def get_current_angles(self) -> Optional[Tuple[float, float, float]]:
        """
        Get current gimbal angles as tuple.

        Returns:
            Optional[Tuple[float, float, float]]: (yaw, pitch, roll) in degrees or None
        """
        with self.lock:
            if self.current_angles and self._is_data_fresh():
                return self.current_angles.to_tuple()
            return None

    def get_current_angles_detailed(self) -> Optional[GimbalAngles]:
        """
        Get current gimbal angles with metadata.

        Returns:
            Optional[GimbalAngles]: Complete angle data or None
        """
        with self.lock:
            if self.current_angles and self._is_data_fresh():
                return self.current_angles
            return None

    def get_connection_status(self) -> str:
        """
        Get current connection status.

        Returns:
            str: Connection status string
        """
        with self.lock:
            return self.connection_status.value

    def is_connected(self) -> bool:
        """
        Check if gimbal is connected and providing fresh data.

        Returns:
            bool: True if connected with fresh data
        """
        with self.lock:
            return (
                self.connection_status == ConnectionStatus.CONNECTED and
                self._is_data_fresh()
            )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get connection and data statistics.

        Returns:
            Dict[str, Any]: Statistics dictionary
        """
        with self.lock:
            data_age = (
                (time.time() - self.last_data_time)
                if self.last_data_time else float('inf')
            )

            return {
                'connection_status': self.connection_status.value,
                'total_packets_received': self.total_packets_received,
                'invalid_packets_received': self.invalid_packets_received,
                'data_age_seconds': data_age,
                'connection_attempts': self.connection_attempts,
                'has_current_data': self.current_angles is not None,
                'data_fresh': self._is_data_fresh()
            }

    def _init_sockets(self) -> bool:
        """Initialize UDP sockets for communication."""
        try:
            # Control socket for sending commands
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_socket.settimeout(self.timeout)

            # Listen socket for receiving responses
            self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.listen_socket.bind(('0.0.0.0', self.listen_port))
            self.listen_socket.settimeout(0.1)  # Short timeout for non-blocking

            logger.debug(f"Sockets initialized - Control: {self.host}:{self.port}, Listen: {self.listen_port}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize sockets: {e}")
            self._cleanup_sockets()
            return False

    def _cleanup_sockets(self) -> None:
        """Clean up socket resources."""
        try:
            if self.control_socket:
                self.control_socket.close()
                self.control_socket = None

            if self.listen_socket:
                self.listen_socket.close()
                self.listen_socket = None

        except Exception as e:
            logger.debug(f"Socket cleanup error (expected): {e}")

    def _build_command(self, address_dest: str, control: str, command: str, data: str = "00") -> str:
        """Build protocol command according to SIP specification."""
        frame = "#TP"  # Fixed length command
        src = "P"      # Network source address
        length = "2"   # Fixed length

        # Build command string
        cmd = f"{frame}{src}{address_dest}{length}{control}{command}{data}"

        # Calculate CRC (sum of all bytes mod 256)
        crc = sum(cmd.encode('ascii')) & 0xFF
        cmd += f"{crc:02X}"

        return cmd

    def _send_command(self, command: str) -> bool:
        """Send UDP command to gimbal."""
        try:
            if not self.control_socket:
                return False

            self.control_socket.sendto(
                command.encode('ascii'),
                (self.host, self.port)
            )
            logger.debug(f"Sent command: {command}")
            return True

        except Exception as e:
            logger.debug(f"Command send failed: {e}")
            return False

    def _query_gimbal_angles(self) -> bool:
        """Query gimbal angles using the preferred coordinate system."""
        # Query both coordinate systems to get comprehensive data
        # Start with GIMBAL_BODY (relative to aircraft)
        cmd1 = self._build_command("G", "r", "GAC", "00")  # Gimbal body angles
        cmd2 = self._build_command("G", "r", "GIC", "00")  # Spatial fixed angles

        success1 = self._send_command(cmd1)
        time.sleep(0.01)  # Small delay between commands
        success2 = self._send_command(cmd2)

        return success1 or success2

    def _parse_angle_response(self, response: str) -> Optional[GimbalAngles]:
        """Parse angle data from gimbal response."""
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
            angles = GimbalAngles(
                yaw=yaw_raw / 100.0,
                pitch=pitch_raw / 100.0,
                roll=roll_raw / 100.0,
                coordinate_system=coord_sys,
                timestamp=datetime.now()
            )

            # Validate angles
            if not angles.is_valid():
                logger.warning(f"Invalid angles received: {angles.yaw}, {angles.pitch}, {angles.roll}")
                return None

            return angles

        except Exception as e:
            logger.debug(f"Angle parse error: {e}")
            return None

    def _listener_loop(self) -> None:
        """Background thread to receive gimbal responses."""
        logger.debug("Gimbal listener thread started")

        while self.running:
            try:
                if not self.listen_socket:
                    time.sleep(0.1)
                    continue

                data, addr = self.listen_socket.recvfrom(4096)
                response = data.decode('utf-8', errors='replace').strip()

                if not response:
                    continue

                logger.debug(f"Received: {response}")

                # Update statistics
                with self.lock:
                    self.total_packets_received += 1

                # Parse angle data
                angles = self._parse_angle_response(response)
                if angles:
                    with self.lock:
                        self.current_angles = angles
                        self.last_data_time = time.time()
                        self.connection_status = ConnectionStatus.CONNECTED
                        self.connection_attempts = 0  # Reset on successful data

                    logger.debug(f"Updated angles: yaw={angles.yaw:.1f}°, pitch={angles.pitch:.1f}°, roll={angles.roll:.1f}°")
                else:
                    with self.lock:
                        self.invalid_packets_received += 1

            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"Listener error: {e}")

        logger.debug("Gimbal listener thread stopped")

    def _query_loop(self) -> None:
        """Background thread to periodically query angles."""
        logger.debug("Gimbal query thread started")

        while self.running:
            try:
                # Query angles at regular intervals
                if not self._query_gimbal_angles():
                    with self.lock:
                        self.connection_attempts += 1
                        if self.connection_attempts >= self.max_connection_attempts:
                            self.connection_status = ConnectionStatus.ERROR
                        else:
                            self.connection_status = ConnectionStatus.CONNECTING

                # Check for stale data
                if self._is_data_stale():
                    with self.lock:
                        if self.connection_status == ConnectionStatus.CONNECTED:
                            self.connection_status = ConnectionStatus.ERROR
                            logger.warning("Gimbal data is stale, marking as disconnected")

                # Log status periodically
                self._log_status_periodically()

                # Query every 100ms for real-time performance
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Query loop error: {e}")
                time.sleep(1.0)  # Longer sleep on error

        logger.debug("Gimbal query thread stopped")

    def _is_data_fresh(self) -> bool:
        """Check if current data is fresh (within timeout period)."""
        if not self.last_data_time:
            return False
        return (time.time() - self.last_data_time) < (self.timeout * 2)

    def _is_data_stale(self) -> bool:
        """Check if data is stale and connection should be considered lost."""
        if not self.last_data_time:
            return True
        return (time.time() - self.last_data_time) > (self.timeout * 3)

    def _log_status_periodically(self) -> None:
        """Log connection status and statistics periodically."""
        current_time = time.time()
        if current_time - self.last_status_log_time > 30.0:  # Every 30 seconds
            stats = self.get_statistics()
            logger.info(
                f"Gimbal Status: {stats['connection_status']} | "
                f"Packets: {stats['total_packets_received']} "
                f"(Invalid: {stats['invalid_packets_received']}) | "
                f"Data Age: {stats['data_age_seconds']:.1f}s"
            )
            self.last_status_log_time = current_time