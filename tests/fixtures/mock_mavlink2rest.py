# tests/fixtures/mock_mavlink2rest.py
"""
Mock MAVLink2REST client for testing MavlinkDataManager.

Provides mock implementations of the MAVLink2REST HTTP API for unit testing
without requiring actual MAVLink connections.
"""

import asyncio
import time
import threading
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch
import math


# ============================================================================
# Mock Data Structures
# ============================================================================

@dataclass
class MockAttitudeData:
    """Mock attitude data from ATTITUDE message."""
    roll: float = 0.0      # radians
    pitch: float = 0.0     # radians
    yaw: float = 0.0       # radians
    rollspeed: float = 0.0
    pitchspeed: float = 0.0
    yawspeed: float = 0.0
    time_boot_ms: int = 0


@dataclass
class MockAltitudeData:
    """Mock altitude data from ALTITUDE message."""
    altitude_relative: float = 50.0   # meters
    altitude_amsl: float = 488.0      # meters
    altitude_local: float = 50.0
    altitude_terrain: float = 0.0
    bottom_clearance: float = 50.0


@dataclass
class MockLocalPositionNED:
    """Mock local position NED from LOCAL_POSITION_NED message."""
    x: float = 0.0     # North (m)
    y: float = 0.0     # East (m)
    z: float = -50.0   # Down (m, negative = up)
    vx: float = 0.0    # North velocity (m/s)
    vy: float = 0.0    # East velocity (m/s)
    vz: float = 0.0    # Down velocity (m/s)


@dataclass
class MockVFRHUD:
    """Mock VFR HUD data."""
    airspeed: float = 0.0
    groundspeed: float = 0.0
    heading: int = 0
    throttle: int = 50      # 0-100
    alt: float = 50.0
    climb: float = 0.0


@dataclass
class MockHeartbeat:
    """Mock heartbeat data."""
    type: int = 2           # MAV_TYPE_QUADROTOR
    autopilot: int = 12     # MAV_AUTOPILOT_PX4
    base_mode: int = 157    # Armed + custom mode
    custom_mode: int = 393216  # Offboard mode (PX4)
    system_status: int = 4  # MAV_STATE_ACTIVE
    mavlink_version: int = 3


@dataclass
class MockGlobalPositionInt:
    """Mock global position from GLOBAL_POSITION_INT message."""
    lat: int = 473977419      # degE7
    lon: int = 85455938       # degE7
    alt: int = 488000         # mm
    relative_alt: int = 50000 # mm
    vx: int = 0               # cm/s
    vy: int = 0               # cm/s
    vz: int = 0               # cm/s
    hdg: int = 0              # cdeg


@dataclass
class RequestRecord:
    """Record of an HTTP request for verification."""
    endpoint: str
    method: str = "GET"
    timestamp: float = field(default_factory=time.time)


# ============================================================================
# Mock MAVLink2REST Client
# ============================================================================

class MockMAVLink2RESTClient:
    """
    Mock MAVLink2REST HTTP client for testing.

    Simulates the REST API endpoints used by MavlinkDataManager.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8088
    ):
        """
        Initialize mock client.

        Args:
            host: Host address (for compatibility)
            port: Port number (for compatibility)
        """
        self.host = host
        self.port = port

        # Mock data state
        self._attitude = MockAttitudeData()
        self._altitude = MockAltitudeData()
        self._local_position = MockLocalPositionNED()
        self._vfr_hud = MockVFRHUD()
        self._heartbeat = MockHeartbeat()
        self._global_position = MockGlobalPositionInt()

        # Request tracking
        self._request_history: List[RequestRecord] = []
        self._request_count = 0

        # Connection simulation
        self._connected = True
        self._should_fail = False
        self._fail_endpoints: List[str] = []
        self._response_delay = 0.0

        # Flight mode tracking
        self._flight_mode_code = 393216  # Offboard

    def get_url(self, endpoint: str) -> str:
        """Get full URL for endpoint."""
        return f"http://{self.host}:{self.port}{endpoint}"

    async def get(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """
        Simulate GET request to MAVLink2REST.

        Args:
            endpoint: API endpoint path

        Returns:
            JSON response dict or None on failure
        """
        if self._response_delay > 0:
            await asyncio.sleep(self._response_delay)

        self._request_history.append(RequestRecord(endpoint=endpoint))
        self._request_count += 1

        if not self._connected:
            raise ConnectionError("Mock connection refused")

        if self._should_fail or endpoint in self._fail_endpoints:
            raise Exception(f"Mock request failed for {endpoint}")

        return self._get_response_for_endpoint(endpoint)

    def get_sync(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Synchronous GET for threading contexts."""
        self._request_history.append(RequestRecord(endpoint=endpoint))
        self._request_count += 1

        if not self._connected:
            raise ConnectionError("Mock connection refused")

        if self._should_fail or endpoint in self._fail_endpoints:
            raise Exception(f"Mock request failed for {endpoint}")

        return self._get_response_for_endpoint(endpoint)

    def _get_response_for_endpoint(self, endpoint: str) -> Dict[str, Any]:
        """Get mock response for specific endpoint."""

        # Full MAVLink data dump
        if endpoint == "/v1/mavlink":
            return self._get_full_mavlink_data()

        # Attitude message
        if "ATTITUDE" in endpoint:
            return {
                "message": {
                    "roll": self._attitude.roll,
                    "pitch": self._attitude.pitch,
                    "yaw": self._attitude.yaw,
                    "rollspeed": self._attitude.rollspeed,
                    "pitchspeed": self._attitude.pitchspeed,
                    "yawspeed": self._attitude.yawspeed,
                    "time_boot_ms": self._attitude.time_boot_ms
                }
            }

        # Altitude message
        if "ALTITUDE" in endpoint:
            return {
                "message": {
                    "altitude_relative": self._altitude.altitude_relative,
                    "altitude_amsl": self._altitude.altitude_amsl,
                    "altitude_local": self._altitude.altitude_local,
                    "altitude_terrain": self._altitude.altitude_terrain,
                    "bottom_clearance": self._altitude.bottom_clearance
                }
            }

        # Local position NED
        if "LOCAL_POSITION_NED" in endpoint:
            return {
                "message": {
                    "x": self._local_position.x,
                    "y": self._local_position.y,
                    "z": self._local_position.z,
                    "vx": self._local_position.vx,
                    "vy": self._local_position.vy,
                    "vz": self._local_position.vz
                }
            }

        # VFR HUD
        if "VFR_HUD" in endpoint:
            return {
                "message": {
                    "airspeed": self._vfr_hud.airspeed,
                    "groundspeed": self._vfr_hud.groundspeed,
                    "heading": self._vfr_hud.heading,
                    "throttle": self._vfr_hud.throttle,
                    "alt": self._vfr_hud.alt,
                    "climb": self._vfr_hud.climb
                }
            }

        # Heartbeat
        if "HEARTBEAT" in endpoint:
            return {
                "message": {
                    "type": self._heartbeat.type,
                    "autopilot": self._heartbeat.autopilot,
                    "base_mode": {
                        "bits": self._heartbeat.base_mode
                    },
                    "custom_mode": self._flight_mode_code,
                    "system_status": self._heartbeat.system_status,
                    "mavlink_version": self._heartbeat.mavlink_version
                }
            }

        # Global position
        if "GLOBAL_POSITION_INT" in endpoint:
            return {
                "message": {
                    "lat": self._global_position.lat,
                    "lon": self._global_position.lon,
                    "alt": self._global_position.alt,
                    "relative_alt": self._global_position.relative_alt,
                    "vx": self._global_position.vx,
                    "vy": self._global_position.vy,
                    "vz": self._global_position.vz,
                    "hdg": self._global_position.hdg
                }
            }

        # Unknown endpoint
        return {}

    def _get_full_mavlink_data(self) -> Dict[str, Any]:
        """Get full MAVLink data structure (used by polling)."""
        return {
            "vehicles": {
                "1": {
                    "components": {
                        "1": {
                            "messages": {
                                "ATTITUDE": {
                                    "message": {
                                        "roll": self._attitude.roll,
                                        "pitch": self._attitude.pitch,
                                        "yaw": self._attitude.yaw
                                    }
                                },
                                "ALTITUDE": {
                                    "message": {
                                        "altitude_relative": self._altitude.altitude_relative,
                                        "altitude_amsl": self._altitude.altitude_amsl
                                    }
                                },
                                "LOCAL_POSITION_NED": {
                                    "message": {
                                        "vx": self._local_position.vx,
                                        "vy": self._local_position.vy,
                                        "vz": self._local_position.vz
                                    }
                                },
                                "VFR_HUD": {
                                    "message": {
                                        "throttle": self._vfr_hud.throttle
                                    }
                                }
                            }
                        },
                        "191": {
                            "messages": {
                                "HEARTBEAT": {
                                    "message": {
                                        "base_mode": {
                                            "bits": self._heartbeat.base_mode
                                        },
                                        "custom_mode": self._flight_mode_code
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

    # ========================================================================
    # Test Helper Methods - Telemetry State
    # ========================================================================

    def set_attitude(
        self,
        roll: float = None,
        pitch: float = None,
        yaw: float = None
    ) -> None:
        """
        Set attitude data (in radians).

        Args:
            roll: Roll angle in radians
            pitch: Pitch angle in radians
            yaw: Yaw angle in radians
        """
        if roll is not None:
            self._attitude.roll = roll
        if pitch is not None:
            self._attitude.pitch = pitch
        if yaw is not None:
            self._attitude.yaw = yaw

    def set_attitude_degrees(
        self,
        roll_deg: float = None,
        pitch_deg: float = None,
        yaw_deg: float = None
    ) -> None:
        """
        Set attitude data (in degrees, converted to radians).

        Args:
            roll_deg: Roll angle in degrees
            pitch_deg: Pitch angle in degrees
            yaw_deg: Yaw angle in degrees
        """
        if roll_deg is not None:
            self._attitude.roll = math.radians(roll_deg)
        if pitch_deg is not None:
            self._attitude.pitch = math.radians(pitch_deg)
        if yaw_deg is not None:
            self._attitude.yaw = math.radians(yaw_deg)

    def set_altitude(
        self,
        relative: float = None,
        amsl: float = None
    ) -> None:
        """
        Set altitude data.

        Args:
            relative: Relative altitude in meters
            amsl: AMSL altitude in meters
        """
        if relative is not None:
            self._altitude.altitude_relative = relative
        if amsl is not None:
            self._altitude.altitude_amsl = amsl

    def set_velocity(
        self,
        vx: float = None,
        vy: float = None,
        vz: float = None
    ) -> None:
        """
        Set velocity data (NED frame).

        Args:
            vx: North velocity in m/s
            vy: East velocity in m/s
            vz: Down velocity in m/s
        """
        if vx is not None:
            self._local_position.vx = vx
        if vy is not None:
            self._local_position.vy = vy
        if vz is not None:
            self._local_position.vz = vz

    def set_throttle(self, throttle: int) -> None:
        """Set throttle percentage (0-100)."""
        self._vfr_hud.throttle = max(0, min(100, throttle))

    def set_flight_mode(self, mode_code: int) -> None:
        """
        Set flight mode code.

        Common PX4 mode codes:
        - 393216: Offboard
        - 196608: Position
        - 458752: Stabilized
        - 84148224: Return (RTL)
        - 50593792: Hold
        """
        self._flight_mode_code = mode_code

    def set_armed(self, armed: bool) -> None:
        """Set armed state via base_mode bits."""
        if armed:
            self._heartbeat.base_mode |= 128  # ARM bit
        else:
            self._heartbeat.base_mode &= ~128

    def set_ground_speed(self, speed: float) -> None:
        """Set ground speed (adjusts vx/vy accordingly)."""
        self._vfr_hud.groundspeed = speed
        # Set vx to speed, vy to 0 (simple approximation)
        self._local_position.vx = speed
        self._local_position.vy = 0.0

    # ========================================================================
    # Test Helper Methods - Connection Simulation
    # ========================================================================

    def simulate_connection_loss(self) -> None:
        """Simulate connection loss."""
        self._connected = False

    def simulate_connection_restore(self) -> None:
        """Restore connection."""
        self._connected = True

    def set_fail_all(self, should_fail: bool) -> None:
        """Set all requests to fail."""
        self._should_fail = should_fail

    def set_fail_endpoint(self, endpoint: str) -> None:
        """Set specific endpoint to fail."""
        if endpoint not in self._fail_endpoints:
            self._fail_endpoints.append(endpoint)

    def clear_fail_endpoints(self) -> None:
        """Clear failed endpoints list."""
        self._fail_endpoints.clear()

    def set_response_delay(self, delay: float) -> None:
        """Set response delay for timeout testing."""
        self._response_delay = delay

    # ========================================================================
    # Test Helper Methods - Request Tracking
    # ========================================================================

    def get_request_count(self) -> int:
        """Get total request count."""
        return self._request_count

    def get_request_history(self) -> List[RequestRecord]:
        """Get request history."""
        return self._request_history.copy()

    def get_requests_for_endpoint(self, endpoint_pattern: str) -> List[RequestRecord]:
        """Get requests matching endpoint pattern."""
        return [
            req for req in self._request_history
            if endpoint_pattern in req.endpoint
        ]

    def clear_request_history(self) -> None:
        """Clear request history."""
        self._request_history.clear()
        self._request_count = 0

    def reset(self) -> None:
        """Reset all state for test isolation."""
        self._attitude = MockAttitudeData()
        self._altitude = MockAltitudeData()
        self._local_position = MockLocalPositionNED()
        self._vfr_hud = MockVFRHUD()
        self._heartbeat = MockHeartbeat()
        self._global_position = MockGlobalPositionInt()
        self._request_history.clear()
        self._request_count = 0
        self._connected = True
        self._should_fail = False
        self._fail_endpoints.clear()
        self._response_delay = 0.0
        self._flight_mode_code = 393216


# ============================================================================
# Mock for requests library (used by MavlinkDataManager)
# ============================================================================

class MockRequestsResponse:
    """Mock requests.Response for testing."""

    def __init__(self, json_data: Dict[str, Any], status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code
        self.ok = status_code == 200

    def json(self) -> Dict[str, Any]:
        """Return JSON data."""
        return self._json_data

    def raise_for_status(self) -> None:
        """Raise exception if status code indicates error."""
        if self.status_code >= 400:
            raise Exception(f"HTTP Error {self.status_code}")


class MockRequestsSession:
    """
    Mock requests session for patching MavlinkDataManager.

    Can be used with unittest.mock.patch to intercept requests.get calls.
    """

    def __init__(self, client: MockMAVLink2RESTClient):
        """
        Initialize with a mock client.

        Args:
            client: MockMAVLink2RESTClient instance
        """
        self._client = client

    def get(self, url: str, timeout: float = None) -> MockRequestsResponse:
        """Mock GET request."""
        # Extract endpoint from URL
        endpoint = url.split(str(self._client.port))[-1]

        if not self._client._connected:
            import requests
            raise requests.exceptions.ConnectionError("Mock connection refused")

        if self._client._should_fail:
            import requests
            raise requests.exceptions.RequestException("Mock request failed")

        data = self._client._get_response_for_endpoint(endpoint)
        return MockRequestsResponse(data)


# ============================================================================
# Factory Functions
# ============================================================================

def create_mock_mavlink2rest_client() -> MockMAVLink2RESTClient:
    """Create a new mock MAVLink2REST client."""
    return MockMAVLink2RESTClient()


def create_mock_client_with_telemetry(
    altitude: float = 50.0,
    roll_deg: float = 0.0,
    pitch_deg: float = 0.0,
    yaw_deg: float = 0.0,
    ground_speed: float = 0.0,
    armed: bool = True
) -> MockMAVLink2RESTClient:
    """
    Create mock client with preset telemetry values.

    Args:
        altitude: Relative altitude in meters
        roll_deg: Roll angle in degrees
        pitch_deg: Pitch angle in degrees
        yaw_deg: Yaw angle in degrees
        ground_speed: Ground speed in m/s
        armed: Armed state
    """
    client = MockMAVLink2RESTClient()
    client.set_altitude(relative=altitude)
    client.set_attitude_degrees(roll_deg=roll_deg, pitch_deg=pitch_deg, yaw_deg=yaw_deg)
    client.set_ground_speed(ground_speed)
    client.set_armed(armed)
    return client


def create_requests_patch(client: MockMAVLink2RESTClient):
    """
    Create a patch context manager for requests.get.

    Usage:
        client = create_mock_mavlink2rest_client()
        with create_requests_patch(client):
            # requests.get will use mock client
            response = requests.get("http://127.0.0.1:8088/v1/mavlink")
    """
    session = MockRequestsSession(client)
    return patch('requests.get', side_effect=session.get)


# ============================================================================
# PX4 Flight Mode Constants
# ============================================================================

class PX4FlightModes:
    """PX4 flight mode codes for testing."""
    MANUAL = 65536
    ALTITUDE = 131072
    POSITION = 196608
    ACRO = 327680
    OFFBOARD = 393216
    STABILIZED = 458752
    HOLD = 50593792
    MISSION = 67371008
    RETURN = 84148224
    LAND = 100925440
    TAKEOFF = 33816576
