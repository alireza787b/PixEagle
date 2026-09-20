# src/classes/gimbal_interface.py

"""
GimbalInterface Module - Topotek SIP-over-UDP Client
====================================================

This module implements the current Topotek SIP-series UDP integration used by
GimbalTracker. It sends query commands for angles/tracking status and listens for
UDP responses or broadcasts from the gimbal.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The GimbalInterface class is designed for the workflow where:
1. External camera UI application controls gimbal tracking (start/stop)
2. PixEagle queries/listens for gimbal angles and tracking status
3. GimbalTracker normalizes that data into TrackerOutput
4. Followers consume TrackerOutput, not vendor packets

Key Features:
- Topotek SIP-series frame handling over UDP
- Active queries for GAC, GIC, and TRC status frames
- Tracking status detection from the vendor protocol
- Authoritative GIMBAL_BODY angles and separate spatial diagnostics
- Thread-safe data access with proper locking
- Connection health monitoring
- Automatic activation based on gimbal tracking state

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
This module is used by GimbalTracker to receive normalized data from the current
vendor protocol. It is not a MAVLink Gimbal Protocol v2 implementation.
"""

import socket
import time
import threading
import logging
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, Union
from enum import Enum
from classes.gimbal_types import (
    CoordinateSystem,
    GimbalAngles,
    GimbalData,
    TrackingState,
    TrackingStatus,
)

logger = logging.getLogger(__name__)

class ConnectionStatus(Enum):
    """Connection status states"""
    DISCONNECTED = "disconnected"
    LISTENING = "listening"
    RECEIVING = "receiving"
    ERROR = "error"

class GimbalInterface:
    """
    Active gimbal interface using Topotek SIP-series UDP frames.

    This class implements the current protocol subset to:
    - Send commands to query camera angles and tracking status
    - Parse validated GAC/TRC responses and retain spatial diagnostics
    - Provide real-time gimbal data to PixEagle tracking system
    """

    def __init__(
        self,
        listen_port: int = 9004,
        gimbal_ip: str = "192.168.0.108",
        control_port: int = 9003,
        connection_timeout: Optional[float] = None,
        tracking_status_timeout: Optional[float] = None,
    ):
        """
        Initialize gimbal interface with Topotek SIP-series protocol support.

        Args:
            listen_port (int): UDP port to listen on for gimbal responses
            gimbal_ip (str): Gimbal IP address for sending commands
            control_port (int): Gimbal UDP port for sending query commands
        """
        self.listen_port = listen_port
        self.gimbal_ip = gimbal_ip
        self.control_port = control_port
        self.connection_timeout = connection_timeout

        # Network setup - both command/query and listen sockets
        self.listen_socket: Optional[socket.socket] = None
        self.control_socket: Optional[socket.socket] = None

        # Thread management
        self.running = False
        self.listener_thread: Optional[threading.Thread] = None
        self.query_thread: Optional[threading.Thread] = None
        self.lock = threading.RLock()

        # Current state
        self.current_data: Optional[GimbalData] = None
        self.current_angles: Optional[GimbalAngles] = None
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.last_data_time: Optional[float] = None
        self.last_raw_packet = ""
        self.last_spatial_packet = ""
        self.last_spatial_update_time: Optional[float] = None

        # Separate tracking status state (persisted across packets)
        self.current_tracking_status: Optional[TrackingStatus] = None
        self.last_tracking_update_time: Optional[float] = None
        self.last_tracking_state = TrackingState.DISABLED  # For change detection

        # Statistics
        self.total_packets_received = 0
        self.invalid_packets_received = 0
        self.tracking_state_changes = 0
        self.last_tracking_state = TrackingState.DISABLED
        self.last_status_log_time = 0.0

        # Configuration constants
        self.DATA_FRESHNESS_TIMEOUT = float(connection_timeout) if connection_timeout else 2.0
        self.SOCKET_TIMEOUT = 0.05         # seconds
        configured_tracking_timeout = (
            float(tracking_status_timeout)
            if tracking_status_timeout is not None
            else self.DATA_FRESHNESS_TIMEOUT
        )
        self.TRACKING_STATUS_FRESHNESS_TIMEOUT = (
            configured_tracking_timeout
            if configured_tracking_timeout > 0
            else self.DATA_FRESHNESS_TIMEOUT
        )
        self.QUERY_INTERVALS = {
            'tracking_status': 5,  # Every 5th cycle (more frequent)
            'spatial_angles': 1,   # Every cycle (continuous like camera UI)
            'gimbal_angles': 3,    # Every 3rd cycle
            'base_interval': 0.1   # Faster cycles (like camera UI)
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

    def _send_command(self, command: Union[str, bytes]) -> bool:
        """Send an ASCII or binary frame through the shared command socket."""
        try:
            payload = command.encode('ascii') if isinstance(command, str) else command
            if not isinstance(payload, bytes):
                raise TypeError("Gimbal commands must be str or bytes")
            with self.lock:
                if self.control_socket is None:
                    self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.control_socket.sendto(payload, (self.gimbal_ip, self.control_port))
            logger.debug("Sent gimbal command: %s", payload.hex())
            return True
        except Exception as e:
            logger.error("Failed to send gimbal command: %s", e)
            return False

    def start_listening(self) -> bool:
        """
        Start UDP command/query and response handling for gimbal data.

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
            self.current_angles = None
            self.last_data_time = None
            self.last_raw_packet = ""
            self.last_spatial_packet = ""
            self.last_spatial_update_time = None
            self.current_tracking_status = None
            self.last_tracking_update_time = None
            self.last_tracking_state = TrackingState.DISABLED

        logger.info("Gimbal listener stopped")

    def get_current_data(self) -> Optional[GimbalData]:
        """
        Get current gimbal data including angles and tracking status.

        Returns:
            Optional[GimbalData]: Complete gimbal data or None if no recent data
        """
        with self.lock:
            self.current_data = self._compose_current_data_locked()
            return self.current_data

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

            current_data = self._compose_current_data_locked()
            tracking_status_age = (
                (time.time() - self.last_tracking_update_time)
                if self.last_tracking_update_time else float('inf')
            )

            return {
                'connection_status': self.connection_status.value,
                'total_packets_received': self.total_packets_received,
                'invalid_packets_received': self.invalid_packets_received,
                'data_age_seconds': data_age,
                'has_current_data': current_data is not None,
                'data_fresh': self._is_data_fresh(),
                'tracking_status_age_seconds': tracking_status_age,
                'tracking_status_fresh': (
                    tracking_status_age < self.TRACKING_STATUS_FRESHNESS_TIMEOUT
                ),
                'tracking_status_freshness_timeout': (
                    self.TRACKING_STATUS_FRESHNESS_TIMEOUT
                ),
                'tracking_state_changes': self.tracking_state_changes,
                'current_tracking_state': (
                    current_data.tracking_status.state.name
                    if current_data and current_data.tracking_status else 'UNKNOWN'
                ),
                'is_tracking_active': self.is_tracking_active(),
                'listen_port': self.listen_port,
                'spatial_diagnostic_packet': self.last_spatial_packet,
                'spatial_diagnostic_age_seconds': (
                    time.time() - self.last_spatial_update_time
                    if self.last_spatial_update_time is not None else None
                ),
            }

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get gimbal connection health status for enterprise-grade monitoring.

        This method provides comprehensive health information including:
        - Connection status ('healthy', 'degraded', 'disconnected')
        - Data freshness and age
        - Consecutive timeout tracking
        - Recommendations for follower behavior

        Returns:
            Dict[str, Any]: Health status dictionary with fields:
                - status: 'healthy', 'degraded', or 'disconnected'
                - data_age_seconds: Time since last valid data
                - is_fresh: Whether data is within freshness timeout
                - last_data_time: Unix timestamp of last data
                - consecutive_timeouts: Count of consecutive timeouts (internal tracking)
                - recommendation: Suggested action ('proceed', 'reduce_velocity', 'emergency_hold')
        """
        with self.lock:
            current_time = time.time()
            data_age = (
                (current_time - self.last_data_time)
                if self.last_data_time else float('inf')
            )

            # Determine health status based on data freshness
            # DEGRADED_THRESHOLD: 2x freshness timeout
            # DISCONNECT_THRESHOLD: 5x freshness timeout
            degraded_threshold = self.DATA_FRESHNESS_TIMEOUT * 2
            disconnect_threshold = self.DATA_FRESHNESS_TIMEOUT * 5

            if data_age < self.DATA_FRESHNESS_TIMEOUT:
                status = 'healthy'
                recommendation = 'proceed'
            elif data_age < degraded_threshold:
                status = 'degraded'
                recommendation = 'reduce_velocity'
            elif data_age < disconnect_threshold:
                status = 'degraded'
                recommendation = 'reduce_velocity'
            else:
                status = 'disconnected'
                recommendation = 'emergency_hold'

            return {
                'status': status,
                'data_age_seconds': data_age,
                'is_fresh': data_age < self.DATA_FRESHNESS_TIMEOUT,
                'last_data_time': self.last_data_time,
                'freshness_timeout': self.DATA_FRESHNESS_TIMEOUT,
                'connection_status': self.connection_status.value,
                'recommendation': recommendation,
                'is_tracking_active': self.is_tracking_active()
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

                # Receive UDP packet from response/broadcast stream
                data, addr = self.listen_socket.recvfrom(4096)
                packet = data.hex()

                # Log packet details only for debugging when needed
                if logger.isEnabledFor(logging.DEBUG) and self.total_packets_received <= 3:
                    logger.debug(f"Received gimbal packet from {addr}: {packet[:60]}...")

                # Update statistics
                with self.lock:
                    self.total_packets_received += 1
                # Source ports change across restarts; validate the configured IP.
                gimbal_data = self._parse_gimbal_packet(data, source_ip=addr[0])
                if gimbal_data:
                    with self.lock:
                        self.connection_status = ConnectionStatus.RECEIVING
                        self._ingest_parsed_data_locked(
                            gimbal_data,
                            gimbal_data.raw_packet,
                            now=time.time(),
                        )

                    # Log data updates much less frequently to reduce log noise
                    if self.total_packets_received % 1000 == 0:  # Every 1000 packets instead of 100
                        current_data = self.get_current_data()
                        angles_info = f"yaw={current_data.angles.yaw:.1f}° pitch={current_data.angles.pitch:.1f}° roll={current_data.angles.roll:.1f}°" if current_data and current_data.angles else "angles=N/A"
                        tracking_info = current_data.tracking_status.state.name if current_data and current_data.tracking_status else "tracking=N/A"
                        logger.info(f"📡 Gimbal heartbeat: {angles_info} | {tracking_info} (packet #{self.total_packets_received})")
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

                # Each due family must run, even when intervals coincide.
                if query_counter % intervals['tracking_status'] == 0:
                    self.query_tracking_status()
                if query_counter % intervals['gimbal_angles'] == 0:
                    self.query_gimbal_body_angles()
                if query_counter % intervals['spatial_angles'] == 0:
                    self.query_spatial_fixed_angles()
                time.sleep(intervals['base_interval'])

            except Exception as e:
                logger.debug(f"Query loop error: {e}")
                time.sleep(1.0)  # Shorter recovery time

        logger.debug("Gimbal active query thread stopped")

    def _validated_frame(
        self, packet: Union[str, bytes], *, source_ip: Optional[str] = None,
    ) -> Optional[bytes]:
        """Validate exact supported response framing before decoding any payload."""
        if source_ip is not None and source_ip != self.gimbal_ip:
            return None
        try:
            frame = packet.encode('ascii') if isinstance(packet, str) else packet
            if not isinstance(frame, bytes) or len(frame) < 12:
                return None
            if frame[-2:] != f"{sum(frame[:-2]) & 0xFF:02X}".encode('ascii'):
                return None
            command = frame[7:10]
            if command == b'TRC':
                if (frame[:3] not in (b'#TP', b'#tp') or frame[3:6] != b'DP2'
                        or frame[6:7] not in (b'r', b'w') or len(frame) != 14):
                    return None
            elif command in (b'GAC', b'GIC', b'GIA'):
                if (frame[:6] != b'#tpGPC' or frame[6:7] not in (b'r', b'w')
                        or len(frame) != 24):
                    return None
                if any(value not in b'0123456789ABCDEFabcdef' for value in frame[10:22]):
                    return None
            else:
                # OFT is a tracking box, never angle telemetry. Other families
                # require their own documented codecs before use here.
                return None
            return frame
        except (UnicodeError, ValueError, TypeError):
            return None

    def _parse_gimbal_packet(
        self, packet: Union[str, bytes], *, source_ip: Optional[str] = None,
    ) -> Optional[GimbalData]:
        """Decode validated frames without mutating independently fresh state."""
        frame = self._validated_frame(packet, source_ip=source_ip)
        if frame is None:
            return None
        response = frame.decode('ascii')
        command = frame[7:10]
        data = GimbalData(timestamp=datetime.now(), raw_packet=response)
        if command == b'GAC':
            data.angles = self._parse_hex_angles_direct(
                response[10:22], CoordinateSystem.GIMBAL_BODY,
            )
            if data.angles is None:
                return None
            data.coordinate_system = CoordinateSystem.GIMBAL_BODY
        elif command == b'TRC':
            data.tracking_status = self._parse_tracking_response(response)
            if data.tracking_status is None:
                return None
        # GIC/GIA are retained only as diagnostics until their reference frame
        # is verified. They cannot replace body angles or refresh their age.
        return data

    def _compose_current_data_locked(
        self,
        now: Optional[float] = None,
    ) -> Optional[GimbalData]:
        """Compose one coherent snapshot from independently fresh components."""
        current_time = time.time() if now is None else now
        angles_fresh = bool(
            self.current_angles is not None
            and self.last_data_time is not None
            and current_time - self.last_data_time < self.DATA_FRESHNESS_TIMEOUT
        )
        tracking_fresh = bool(
            self.current_tracking_status is not None
            and self.last_tracking_update_time is not None
            and current_time - self.last_tracking_update_time
            < self.TRACKING_STATUS_FRESHNESS_TIMEOUT
        )
        if not angles_fresh and not tracking_fresh:
            return None

        angles = self.current_angles if angles_fresh else None
        return GimbalData(
            angles=angles,
            tracking_status=(
                self.current_tracking_status if tracking_fresh else None
            ),
            coordinate_system=angles.coordinate_system if angles else None,
            timestamp=datetime.now(),
            raw_packet=self.last_raw_packet,
        )

    def _ingest_parsed_data_locked(
        self,
        gimbal_data: GimbalData,
        packet: str,
        *,
        now: Optional[float] = None,
    ) -> Optional[GimbalData]:
        """Merge one partial protocol packet into the coherent provider state."""
        current_time = time.time() if now is None else now
        if gimbal_data.raw_packet[7:10] in ('GIC', 'GIA'):
            self.last_spatial_packet = gimbal_data.raw_packet
            self.last_spatial_update_time = current_time
            return self._compose_current_data_locked(current_time)
        self.last_raw_packet = packet
        if (gimbal_data.angles is not None
                and gimbal_data.angles.coordinate_system == CoordinateSystem.GIMBAL_BODY):
            self.current_angles = gimbal_data.angles
            self.last_data_time = current_time

        if gimbal_data.tracking_status is not None:
            self.current_tracking_status = gimbal_data.tracking_status
            self.last_tracking_update_time = current_time

        if (
            self.current_tracking_status
            and self.current_tracking_status.state != self.last_tracking_state
        ):
            self.tracking_state_changes += 1
            old_state = self.last_tracking_state
            new_state = self.current_tracking_status.state
            self.last_tracking_state = new_state
            logger.info(
                "Gimbal tracking state changed: %s \u2192 %s",
                old_state.name,
                new_state.name,
            )

        self.current_data = self._compose_current_data_locked(current_time)
        return self.current_data

    def _parse_angle_response(self, response: Union[str, bytes]) -> Optional[GimbalAngles]:
        """Return only validated body-angle responses; OFT is not angle data."""
        frame = self._validated_frame(response)
        if frame is None or frame[7:10] != b'GAC':
            return None
        return self._parse_hex_angles_direct(
            frame[10:22].decode('ascii'), CoordinateSystem.GIMBAL_BODY,
        )

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


    def _parse_tracking_response(self, response: Union[str, bytes]) -> Optional[TrackingStatus]:
        """Decode documented states, including explicit unsupported/inactive."""
        frame = self._validated_frame(response)
        if frame is None or frame[7:10] != b'TRC':
            return None
        # Qt recognizes general, vehicle and person modes; status semantics
        # are identical. Do not accept an arbitrary mode character.
        if frame[10:11] not in (b'0', b'1', b'2'):
            return None
        try:
            state = TrackingState(int(frame[11:12]))
        except ValueError:
            return None
        return TrackingStatus(state=state, timestamp=datetime.now())

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
            # Include persistent tracking status in status log
            with self.lock:
                persistent_status = self.current_tracking_status.state.name if self.current_tracking_status else 'None'
                status_age = (current_time - self.last_tracking_update_time) if self.last_tracking_update_time else float('inf')

            logger.info(
                f"Gimbal Status: {stats['connection_status']} | "
                f"Packets: {stats['total_packets_received']} (Invalid: {stats['invalid_packets_received']}) | "
                f"Tracking: {stats['current_tracking_state']} | Persistent: {persistent_status} | "
                f"Data Age: {stats['data_age_seconds']:.1f}s | Status Age: {status_age:.1f}s"
            )
            self.last_status_log_time = current_time
