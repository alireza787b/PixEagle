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
        """Check if angles are within valid ranges - relaxed for gimbal compatibility"""
        return (
            -180.0 <= self.yaw <= 180.0 and
            -180.0 <= self.pitch <= 180.0 and  # Extended pitch range for gimbal compatibility
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
    Active gimbal interface using SIP protocol for real-time angle reading and tracking status.

    This class implements the complete SIP protocol to:
    - Send commands to query camera angles and tracking status
    - Parse responses using the proper protocol format
    - Provide real-time gimbal data to PixEagle tracking system
    """

    def __init__(self, listen_port: int = 9004, gimbal_ip: str = "192.168.0.108", control_port: int = 9003):
        """
        Initialize gimbal interface with SIP protocol support.

        Args:
            listen_port (int): UDP port to listen on for gimbal responses
            gimbal_ip (str): Gimbal IP address for sending commands
            control_port (int): Gimbal control port for sending commands
        """
        self.listen_port = listen_port
        self.gimbal_ip = gimbal_ip
        self.control_port = control_port

        # Network setup - both control and listen sockets
        self.listen_socket: Optional[socket.socket] = None
        self.control_socket: Optional[socket.socket] = None

        # Thread management
        self.running = False
        self.listener_thread: Optional[threading.Thread] = None
        self.query_thread: Optional[threading.Thread] = None
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

        # Configuration constants
        self.DATA_FRESHNESS_TIMEOUT = 2.0  # seconds
        self.SOCKET_TIMEOUT = 0.05         # seconds
        self.QUERY_INTERVALS = {
            'tracking_status': 6,  # Every 6th cycle
            'spatial_angles': 2,   # Every 2nd cycle
            'gimbal_angles': 4,    # Every 4th cycle
            'base_interval': 0.3   # seconds between cycles
        }

        logger.info(f"GimbalInterface initialized with SIP protocol - port {listen_port}")
        logger.info(f"Gimbal source: {gimbal_ip}:{control_port}")


    def query_spatial_fixed_angles(self) -> bool:
        """Query camera angles in absolute spatial coordinates (Gyroscope mode)"""
        command = self._build_command("G", "r", "GIC", "00")
        return self._send_command(command)

    def query_gimbal_body_angles(self) -> bool:
        """Query camera angles relative to gimbal body (Magnetic mode)"""
        command = self._build_command("G", "r", "GAC", "00")
        return self._send_command(command)

    def query_tracking_status(self) -> bool:
        """Query current tracking status"""
        command = self._build_command("D", "r", "TRC", "00")
        return self._send_command(command)

    def _build_command(self, address_dest: str, control: str, command: str, data: str = "00") -> str:
        """Build SIP protocol command according to specification."""
        frame = "#TP"  # Fixed length command frame identifier
        src = "P"      # Network source address identifier
        length = "2"   # Fixed length field

        # Build command string following SIP protocol format
        cmd = f"{frame}{src}{address_dest}{length}{control}{command}{data}"

        # Calculate CRC checksum (sum of all bytes mod 256)
        crc = sum(cmd.encode('ascii')) & 0xFF
        cmd += f"{crc:02X}"

        return cmd

    def _send_command(self, command: str) -> bool:
        """Send UDP command to gimbal with automatic socket creation if needed."""
        try:
            if not hasattr(self, 'control_socket') or self.control_socket is None:
                self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            self.control_socket.sendto(command.encode('ascii'), (self.gimbal_ip, self.control_port))
            logger.debug(f"Sent gimbal command: {command}")
            return True
        except Exception as e:
            logger.error(f"Failed to send gimbal command: {e}")
            return False




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
            logger.info("Starting active gimbal SIP interface...")

            # Initialize both listen and control sockets
            if not self._init_listening_socket():
                return False

            # Start background threads
            self.running = True

            # Start listener thread for responses
            self.listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
            self.listener_thread.start()

            # Start query thread for active polling
            self.query_thread = threading.Thread(target=self._query_loop, daemon=True)
            self.query_thread.start()

            # Allow threads to start
            time.sleep(0.1)

            # Set connection status
            with self.lock:
                self.connection_status = ConnectionStatus.LISTENING
            logger.info(f"Gimbal interface ready - listening on port {self.listen_port}, expecting data from {self.gimbal_ip}:{self.control_port}")

            logger.info("Optimized gimbal SIP interface started successfully - ready for continuous data reception")
            return True

        except Exception as e:
            logger.error(f"Failed to start gimbal listener: {e}")
            self.stop_listening()
            return False

    def stop_listening(self) -> None:
        """Stop gimbal data reception and cleanup resources."""
        if not self.running:
            return

        logger.info("Stopping gimbal interface...")
        self.running = False

        # Wait for both threads to finish
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=2.0)
        if self.query_thread and self.query_thread.is_alive():
            self.query_thread.join(timeout=2.0)

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
        """Initialize UDP sockets for both listening and control."""
        try:
            # Create UDP socket for listening to gimbal responses
            self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listen_socket.bind(('0.0.0.0', self.listen_port))
            self.listen_socket.settimeout(self.SOCKET_TIMEOUT)  # Configurable timeout

            # Create UDP socket for sending commands to gimbal
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            logger.info(f"Gimbal sockets initialized - Listening: 0.0.0.0:{self.listen_port}, Control: {self.gimbal_ip}:{self.control_port}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize sockets: {e}")
            self._cleanup_socket()
            return False

    def _cleanup_socket(self) -> None:
        """Clean up socket resources safely."""
        try:
            if hasattr(self, 'listen_socket') and self.listen_socket:
                self.listen_socket.close()
                self.listen_socket = None
        except Exception as e:
            logger.debug(f"Error closing listen socket: {e}")

        try:
            if hasattr(self, 'control_socket') and self.control_socket:
                self.control_socket.close()
                self.control_socket = None
        except Exception as e:
            logger.debug(f"Error closing control socket: {e}")

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

                # Log packet details only for debugging when needed
                if logger.isEnabledFor(logging.DEBUG) and self.total_packets_received <= 3:
                    logger.debug(f"Received gimbal packet from {addr}: {packet[:60]}...")

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

                    # Log data updates periodically for monitoring
                    if self.total_packets_received % 100 == 0:
                        angles_info = f"yaw={gimbal_data.angles.yaw:.1f}° pitch={gimbal_data.angles.pitch:.1f}° roll={gimbal_data.angles.roll:.1f}°" if gimbal_data.angles else "angles=N/A"
                        tracking_info = gimbal_data.tracking_status.state.name if gimbal_data.tracking_status else "tracking=N/A"
                        logger.info(f"Gimbal status: {angles_info} | {tracking_info}")
                else:
                    with self.lock:
                        self.invalid_packets_received += 1

            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"Listener error: {e}")

        logger.debug("Gimbal passive listener thread stopped")

    def _query_loop(self) -> None:
        """Background thread to actively query gimbal for angles and tracking status."""
        logger.debug("Gimbal active query thread started")

        query_counter = 0
        while self.running:
            try:
                query_counter += 1

                # Active querying to supplement broadcast data
                intervals = self.QUERY_INTERVALS

                if query_counter % intervals['tracking_status'] == 0:
                    self.query_tracking_status()
                    time.sleep(0.2)
                elif query_counter % intervals['spatial_angles'] == 0:
                    self.query_spatial_fixed_angles()
                    time.sleep(0.2)
                elif query_counter % intervals['gimbal_angles'] == 0:
                    self.query_gimbal_body_angles()
                    time.sleep(0.2)
                else:
                    time.sleep(intervals['base_interval'])

            except Exception as e:
                logger.debug(f"Query loop error: {e}")
                time.sleep(1.0)  # Shorter recovery time

        logger.debug("Gimbal active query thread stopped")

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

            # Parse angle data from various formats
            angles = self._parse_angle_response(packet)
            if angles:
                gimbal_data.angles = angles
                gimbal_data.coordinate_system = angles.coordinate_system

            # Parse tracking status from TRC packets
            tracking_status = self._parse_tracking_response(packet)
            if tracking_status:
                gimbal_data.tracking_status = tracking_status

            # Return data if we have at least one valid component
            if gimbal_data.angles or gimbal_data.tracking_status:
                return gimbal_data

            return None

        except Exception as e:
            logger.debug(f"Error parsing gimbal packet: {e}")
            return None

    def _parse_angle_response(self, response: str) -> Optional[GimbalAngles]:
        """
        Parse gimbal angle response supporting both query responses and broadcast formats.

        Query Format: #tpUG C r GAC/GIC Y0Y1Y2Y3P0P1P2P3R0R1R2R3 CC
        Broadcast Format: #tpDP9wOFT<binary_angle_data>
        """
        try:
            response = response.strip()
            logger.debug(f"Parsing gimbal response: {response[:50]}...")

            # Validate basic frame format
            if not response.startswith('#tp'):
                logger.debug(f"Invalid frame start: {response[:10]}")
                return None

            # Handle broadcast format: #tpDP9wOFT<binary_data>
            if 'OFT' in response:
                logger.debug("Detected broadcast format with OFT marker")
                return self._parse_broadcast_format(response)

            # Handle query response formats: GAC/GIC
            if 'GAC' in response or 'GIC' in response:
                logger.debug("Detected query response format")
                return self._parse_query_response_format(response)

            logger.debug(f"Unrecognized packet format: {response[:50]}...")
            return None

        except Exception as e:
            logger.error(f"Failed to parse angle response '{response[:50]}...': {e}")
            return None

    def _parse_query_response_format(self, response: str) -> Optional[GimbalAngles]:
        """Parse GAC/GIC query response format (from test script)."""
        try:
            # Extract identifier to determine coordinate system mode
            coord_sys = None
            identifier = None

            if 'GAC' in response:
                coord_sys = CoordinateSystem.GIMBAL_BODY  # Magnetic coding
                identifier = 'GAC'
            elif 'GIC' in response:
                coord_sys = CoordinateSystem.SPATIAL_FIXED  # Gyroscope
                identifier = 'GIC'
            else:
                return None

            # Find the angle data section (12 hex characters after identifier)
            id_pos = response.find(identifier)
            if id_pos == -1:
                return None

            angle_start = id_pos + 3  # Skip 3-character identifier
            angle_data = response[angle_start:angle_start + 12]

            if len(angle_data) != 12:
                logger.debug(f"Invalid angle data length: {len(angle_data)} (expected 12)")
                return None

            return self._parse_hex_angles_direct(angle_data, coord_sys)

        except Exception as e:
            logger.error(f"Error parsing query response: {e}")
            return None

    def _parse_broadcast_format(self, response: str) -> Optional[GimbalAngles]:
        """Parse broadcast format: #tpDP9wOFT<hex_angle_data> (multi-strategy approach)"""
        try:
            # Find OFT marker
            oft_pos = response.find('OFT')
            if oft_pos == -1:
                return None

            # Extract data after OFT marker
            angle_start = oft_pos + 3
            raw_data = response[angle_start:]

            if not raw_data:
                return None

            # Strategy 1: Parse as hex string (most common format from debug_gimbal_packets.py)
            # Expected format: #tpDP9wOFT64025910 (8 hex chars = 3 angles × 2 bytes + 2 extra)
            result = self._parse_broadcast_hex_strategy(raw_data)
            if result:
                return result

            # Strategy 2: Parse as binary data (if hex fails)
            result = self._parse_broadcast_binary_strategy(raw_data)
            if result:
                return result

            # Strategy 3: Try to extract embedded hex patterns
            result = self._parse_broadcast_embedded_hex(raw_data)
            if result:
                return result
            return None

        except Exception as e:
            logger.error(f"Error parsing broadcast format: {e}")
            return None

    def _parse_broadcast_hex_strategy(self, raw_data: str) -> Optional[GimbalAngles]:
        """Strategy 1: Parse broadcast data as hex string (primary method)"""
        try:
            # Clean hex data (remove any non-hex characters)
            hex_chars = ''.join(c for c in raw_data if c in '0123456789ABCDEFabcdef')

            # From debug_gimbal_packets.py format: #tpDP9wOFT64025910
            # This suggests 8 hex chars after OFT, but we need 12 for 3 angles
            # Try both 12-char (standard) and other lengths

            if len(hex_chars) >= 12:
                # Standard 12-char format: YYYYPPPPRRRRR
                return self._parse_hex_angles_direct(hex_chars[:12], CoordinateSystem.SPATIAL_FIXED)

            elif len(hex_chars) >= 8:
                # 8-char format might be compressed or different encoding
                # Try parsing as 4 chars per angle with different interpretation
                if len(hex_chars) >= 8:
                    # Split into chunks and try to parse
                    chunk_size = len(hex_chars) // 3
                    if chunk_size >= 2:
                        yaw_hex = hex_chars[0:chunk_size]
                        pitch_hex = hex_chars[chunk_size:chunk_size*2]
                        roll_hex = hex_chars[chunk_size*2:chunk_size*3]

                        # Pad to 4 chars if needed
                        yaw_hex = yaw_hex.ljust(4, '0')
                        pitch_hex = pitch_hex.ljust(4, '0')
                        roll_hex = roll_hex.ljust(4, '0')

                        combined_hex = yaw_hex + pitch_hex + roll_hex
                        return self._parse_hex_angles_direct(combined_hex, CoordinateSystem.SPATIAL_FIXED)

            elif len(hex_chars) >= 6:
                # 6-char format: 2 chars per angle
                yaw_hex = hex_chars[0:2] + '00'  # Pad to 4 chars
                pitch_hex = hex_chars[2:4] + '00'
                roll_hex = hex_chars[4:6] + '00'

                combined_hex = yaw_hex + pitch_hex + roll_hex
                return self._parse_hex_angles_direct(combined_hex, CoordinateSystem.SPATIAL_FIXED)

            # Insufficient hex data
            return None

        except Exception as e:
            logger.debug(f"Hex parsing failed: {e}")
            return None

    def _parse_broadcast_binary_strategy(self, raw_data: str) -> Optional[GimbalAngles]:
        """Strategy 2: Parse broadcast data as binary values"""
        try:
            # Convert string to bytes preserving binary values
            if len(raw_data) >= 6:
                angle_bytes = raw_data.encode('latin1')[:6]

                # Parse as 3 × 16-bit signed integers (big-endian)
                yaw_raw = int.from_bytes(angle_bytes[0:2], byteorder='big', signed=True)
                pitch_raw = int.from_bytes(angle_bytes[2:4], byteorder='big', signed=True)
                roll_raw = int.from_bytes(angle_bytes[4:6], byteorder='big', signed=True)

                # Convert to degrees (0.01° units)
                yaw = yaw_raw / 100.0
                pitch = pitch_raw / 100.0
                roll = roll_raw / 100.0

                # Create and validate angles
                angles = GimbalAngles(
                    yaw=yaw, pitch=pitch, roll=roll,
                    coordinate_system=CoordinateSystem.SPATIAL_FIXED,
                    timestamp=datetime.now()
                )

                if angles.is_valid():
                    return angles

            return None

        except Exception as e:
            logger.debug(f"Binary parsing failed: {e}")
            return None

    def _parse_broadcast_embedded_hex(self, raw_data: str) -> Optional[GimbalAngles]:
        """Strategy 3: Extract embedded hex patterns from mixed data"""
        try:
            # Look for consecutive hex sequences
            import re
            hex_matches = re.findall(r'[0-9A-Fa-f]+', raw_data)

            for match in hex_matches:
                if len(match) >= 6:  # Minimum viable hex data
                    # Try to use this hex sequence
                    if len(match) >= 12:
                        return self._parse_hex_angles_direct(match[:12], CoordinateSystem.SPATIAL_FIXED)
                    else:
                        # Pad or repeat the pattern
                        padded = (match * 3)[:12]
                        result = self._parse_hex_angles_direct(padded, CoordinateSystem.SPATIAL_FIXED)
                        if result and result.is_valid():
                            return result

            return None

        except Exception as e:
            logger.debug(f"Embedded hex parsing failed: {e}")
            return None

    def _parse_hex_angles_direct(self, angle_data: str, coord_sys: CoordinateSystem) -> Optional[GimbalAngles]:
        """Parse 12-character hex angle data directly."""
        try:
            # Parse angles: Y0Y1Y2Y3 P0P1P2P3 R0R1R2R3
            yaw_hex = angle_data[0:4]
            pitch_hex = angle_data[4:8]
            roll_hex = angle_data[8:12]

            # Convert hex to signed integers (0.01 degree units)
            yaw_raw = int(yaw_hex, 16)
            pitch_raw = int(pitch_hex, 16)
            roll_raw = int(roll_hex, 16)

            # Handle signed 16-bit conversion
            if yaw_raw > 32767:
                yaw_raw -= 65536
            if pitch_raw > 32767:
                pitch_raw -= 65536
            if roll_raw > 32767:
                roll_raw -= 65536

            # Convert to degrees (protocol uses 0.01 degree units)
            yaw = yaw_raw / 100.0
            pitch = pitch_raw / 100.0
            roll = roll_raw / 100.0

            # Create GimbalAngles with parsed data
            angles = GimbalAngles(
                yaw=yaw,
                pitch=pitch,
                roll=roll,
                coordinate_system=coord_sys,
                timestamp=datetime.now()
            )

            # Validate angle ranges
            if not angles.is_valid():
                logger.debug(f"Hex angles out of valid range: yaw={yaw:.2f}°, pitch={pitch:.2f}°, roll={roll:.2f}°")
                return None

            return angles

        except ValueError as e:
            logger.debug(f"Hex conversion error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing hex angles: {e}")
            return None


    def _parse_tracking_response(self, response: str) -> Optional[TrackingStatus]:
        """Parse tracking status from gimbal response using exact logic from test script."""
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

            # Parse state value - exact logic from working demo
            try:
                state_val = int(state_data[1])  # Second character is the state
                state_names = {0: "DISABLED", 1: "TARGET_SELECTION", 2: "TRACKING_ACTIVE", 3: "TARGET_LOST"}
                state_name = state_names.get(state_val, f"UNKNOWN({state_val})")

                # Map to TrackingState enum
                state = TrackingState(state_val)

                # Log tracking state changes only
                if state != self.last_tracking_state:
                    logger.info(f"Tracking state: {state_name}")

            except (ValueError, IndexError) as e:
                logger.debug(f"Could not parse tracking state from: '{state_data}', error: {e}")
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
        return (time.time() - self.last_data_time) < self.DATA_FRESHNESS_TIMEOUT

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