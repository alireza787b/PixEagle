from collections import deque
import threading
import time
from numpy import uint16
import requests
import logging
import asyncio
from .parameters import Parameters
from .logging_manager import logging_manager
import math

class MavlinkDataManager:
    def __init__(self, mavlink_host, mavlink_port, polling_interval, data_points, enabled=True):
        """
        Initialize the MavlinkDataManager with necessary parameters.

        Args:
            mavlink_host (str): The host address of the MAVLink server.
            mavlink_port (int): The port number of the MAVLink server.
            polling_interval (int): The interval at which data should be polled in seconds.
            data_points (dict): A dictionary of data points to extract from MAVLink.
            enabled (bool): Whether the polling should be enabled or not.
        """
        self.mavlink_host = mavlink_host
        self.mavlink_port = mavlink_port
        self.polling_interval = polling_interval
        self.data_points = data_points  # Dictionary of data points to extract
        self.enabled = enabled
        self.data = {}  # Stores the fetched data
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.velocity_buffer = deque(maxlen=10)  # Buffer for velocity smoothing
        self.min_velocity_threshold = 0.5  # m/s, adjust based on your drone's characteristics
        self.gamma = 0

        # Connection state tracking
        self.connection_state = "disconnected"  # disconnected, connecting, connected, error
        self.last_successful_connection = None
        self.connection_error_count = 0
        self.last_status_log = 0  # For throttling status messages

        # Setup logging
        self.logger = logging.getLogger(__name__)

    def start_polling(self):
        """
        Start the polling thread if enabled.
        """
        if self.enabled:
            self._thread = threading.Thread(target=self._poll_data)
            self._thread.start()
            logging_manager.log_operation(self.logger, "MAVLink Polling", "info", "Started")
        else:
            logging_manager.log_operation(self.logger, "MAVLink Polling", "info", "Disabled in configuration")

    def stop_polling(self):
        """
        Stop the polling thread.
        """
        if self.enabled:
            self._stop_event.set()
            self._thread.join()
            logging_manager.log_operation(self.logger, "MAVLink Polling", "info", "Stopped")

    def _poll_data(self):
        """
        Poll data at regular intervals and store it in a dictionary.
        """
        while not self._stop_event.is_set():
            self._fetch_and_parse_all_data()
            time.sleep(self.polling_interval)

    def _fetch_and_parse_all_data(self):
        """
        Fetch all MAVLink data in a single request and parse it into the data dictionary.
        """
        url = f"http://{self.mavlink_host}:{self.mavlink_port}/v1/mavlink"
        
        try:
            # Update connection state
            if self.connection_state != "connecting":
                self.connection_state = "connecting"
            
            response = requests.get(url, timeout=5)  # Add timeout
            response.raise_for_status()
            json_data = response.json()

            # Connection successful
            was_disconnected = self.connection_state != "connected"
            if was_disconnected:
                self.connection_state = "connected"
                self.last_successful_connection = time.time()
                self.connection_error_count = 0
                logging_manager.log_connection_status(
                    self.logger, "MAVLink", True, 
                    f"to {self.mavlink_host}:{self.mavlink_port}"
                )
            
            # Log polling activity
            logging_manager.log_polling_activity(self.logger, "MAVLink", True)

            with self._lock:
                # Iterate through the data points defined in Parameters
                for point_name, json_path in self.data_points.items():
                    if point_name in ["vn", "ve", "vd"]:
                        value = self._extract_data_from_json(json_data, json_path)
                        self.data[point_name] = float(value) if value is not None else 0.0
                    elif point_name == "flight_path_angle":
                        self.data[point_name] = self._calculate_flight_path_angle()
                        self.gamma = self.data[point_name] #temporary we might need this
                    elif point_name == "arm_status":
                        base_mode = self._extract_data_from_json(json_data, "/vehicles/1/components/191/messages/HEARTBEAT/message/base_mode/bits")
                        self.data[point_name] = self._determine_arm_status(base_mode)
                    else:
                        value = self._extract_data_from_json(json_data, json_path)
                        if value is None:
                            #self.logger.warning(f"Failed to retrieve data for {point_name} using path {json_path}. Assigning 'N/A'.")
                            value = "N/A"
                        else:
                            if point_name in ["latitude", "longitude"]:
                                try:
                                    value = float(value) / 1e7
                                except (ValueError, TypeError) as e:
                                    self.logger.error(f"Failed to convert {point_name} value to float for division: {e}")
                                    value = "N/A"
                        self.data[point_name] = value
                        
            # Log status periodically when connected
            current_time = time.time()
            if current_time - self.last_status_log > 30:  # Every 30 seconds
                arm_status = self.data.get('arm_status', 'Unknown')
                altitude = self.data.get('altitude', 'N/A')
                lat = self.data.get('latitude', 'N/A')
                lon = self.data.get('longitude', 'N/A')
                
                # Format coordinates for display
                coord_str = f"GPS: {lat:.6f},{lon:.6f}" if lat != 'N/A' and lon != 'N/A' else "GPS: N/A"
                
                self.logger.info(f"MAVLINK: Connected | Armed: {arm_status} | Alt: {altitude}m | {coord_str}")
                self.last_status_log = current_time
                
        except requests.exceptions.ConnectionError:
            self._handle_connection_error("Connection refused - server not running")
        except requests.exceptions.Timeout:
            self._handle_connection_error("Connection timeout - server not responding")
        except requests.RequestException as e:
            self._handle_connection_error(f"Request failed: {str(e)[:50]}...")
        except Exception as e:
            self._handle_connection_error(f"Unexpected error: {str(e)[:50]}...")
    
    def _handle_connection_error(self, error_reason):
        """Handle connection errors with clean, throttled logging."""
        self.connection_state = "error"
        self.connection_error_count += 1
        
        # Log connection status and polling activity
        logging_manager.log_connection_status(
            self.logger, "MAVLink", False, 
            f"{error_reason} ({self.mavlink_host}:{self.mavlink_port})"
        )
        logging_manager.log_polling_activity(self.logger, "MAVLink", False, error_reason)
            
            
    def _calculate_flight_path_angle(self):
        vn = self.data.get("vn", 0.0)
        ve = self.data.get("ve", 0.0)
        vd = self.data.get("vd", 0.0)

        # Calculate total velocity
        v_total = math.sqrt(vn**2 + ve**2 + vd**2)

        # Add to buffer for smoothing
        self.velocity_buffer.append((vn, ve, vd))

        # Calculate average velocity over the buffer
        avg_vn = sum(v[0] for v in self.velocity_buffer) / len(self.velocity_buffer)
        avg_ve = sum(v[1] for v in self.velocity_buffer) / len(self.velocity_buffer)
        avg_vd = sum(v[2] for v in self.velocity_buffer) / len(self.velocity_buffer)

        # Calculate horizontal speed using averaged values
        v_horizontal = math.sqrt(avg_vn**2 + avg_ve**2)

        # Check if the total velocity is above the threshold
        if v_total < self.min_velocity_threshold:
            return 0.0  # Return 0 when the drone is effectively stationary

        # Calculate flight path angle using averaged values
        if v_horizontal == 0:
            return 90.0 if avg_vd < 0 else -90.0  # Vertical up or down

        flight_path_angle = math.degrees(math.atan2(-avg_vd, v_horizontal))

        # Apply additional smoothing
        flight_path_angle = round(flight_path_angle, 1)  # Round to one decimal place

        return flight_path_angle


    def _determine_arm_status(self, base_mode_bits):
        """
        Determine if the system is armed based on the base_mode bits.

        Args:
            base_mode_bits (int): The base mode bits from the MAVLink HEARTBEAT message.

        Returns:
            str: "Armed" if the system is armed, otherwise "Disarmed".
        """
        ARM_BIT_MASK = 128  # Example mask, update with the correct one
        if base_mode_bits is None:
            return "Unknown"
        return "Armed" if base_mode_bits & ARM_BIT_MASK else "Disarmed"

    def _extract_data_from_json(self, data, json_path):
        """
        Helper function to extract a value from a nested JSON structure using a json_path.

        Args:
            data (dict): The JSON data dictionary.
            json_path (str): The path to the desired data within the JSON.

        Returns:
            any: The value found at the JSON path, or None if not found.
        """
        keys = json_path.strip("/").split('/')
        for key in keys:
            if key in data:
                data = data[key]
            else:
                #self.logger.debug(f"Key {key} not found in the current JSON level.")
                return None
        return data

    def get_data(self, point):
        """
        Retrieve the most recent data for a specified point.

        Args:
            point (str): The name of the data point to retrieve.

        Returns:
            any: The latest value of the specified data point, or "N/A" if not available.
        """
        with self._lock:
            if not self.enabled:
                return None  # Avoid unnecessary logging and simply return None
            return self.data.get(point, 0)

    async def fetch_data_from_uri(self, uri):
        """
        Fetch data from a specific URI and return the parsed JSON response.

        Args:
            uri (str): The URI to fetch the data from.

        Returns:
            dict: The parsed JSON data from the response.
        """
        url = f"http://{self.mavlink_host}:{self.mavlink_port}{uri}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Error fetching data from {url}: {e}")
            return None

    async def fetch_attitude_data(self):
        """
        Fetch attitude data (roll, pitch, yaw) from MAVLink2Rest.

        These values are specifically for follower usage and are independent of OSD data.
        If USE_MAVLINK2REST = True is enabled in parameters, these values are required.
        In case REST requests send invalid data, the roll, pitch, and yaw will fall back to 0.

        Returns:
            dict: A dictionary with roll, pitch, and yaw values in degrees.
        """
        attitude_data = await self.fetch_data_from_uri("/v1/mavlink/vehicles/1/components/1/messages/ATTITUDE")
        if attitude_data:
            message = attitude_data.get("message", {})
            try:
                roll = float(message.get("roll", 0))
                pitch = float(message.get("pitch", 0))
                yaw = float(message.get("yaw", 0))

                # Convert radians to degrees
                roll_deg = math.degrees(roll)
                pitch_deg = math.degrees(pitch)
                yaw_deg = math.degrees(yaw)
                
            except (ValueError, TypeError):
                self.logger.warning("Invalid attitude data received, falling back to default values (0).")
                roll_deg, pitch_deg, yaw_deg = 0, 0, 0

            return {"roll": roll_deg, "pitch": pitch_deg, "yaw": yaw_deg}
        
        return {"roll": 0, "pitch": 0, "yaw": 0}

    async def fetch_altitude_data(self):
        """
        Fetch altitude data from MAVLink2Rest.

        These values are specifically for follower usage and are independent of OSD data.
        If USE_MAVLINK2REST = True is enabled in parameters, these values are required.
        In case REST requests send invalid data, the altitude_relative will fall back to Parameters.MIN_DESCENT_HEIGHT.

        Returns:
            dict: A dictionary with relative and AMSL altitudes.
        """
        altitude_data = await self.fetch_data_from_uri("/v1/mavlink/vehicles/1/components/1/messages/ALTITUDE")
        if altitude_data:
            message = altitude_data.get("message", {})
            try:
                altitude_relative = float(message.get("altitude_relative", Parameters.MIN_DESCENT_HEIGHT))
                altitude_amsl = float(message.get("altitude_amsl", Parameters.MIN_DESCENT_HEIGHT))
            except (ValueError, TypeError):
                self.logger.warning("Invalid altitude data received, falling back to default values (Parameters.MIN_DESCENT_HEIGHT).")
                altitude_relative, altitude_amsl = Parameters.MIN_DESCENT_HEIGHT, Parameters.MIN_DESCENT_HEIGHT
            return {"altitude_relative": altitude_relative, "altitude_amsl": altitude_amsl}
        return {"altitude_relative": Parameters.MIN_DESCENT_HEIGHT, "altitude_amsl": Parameters.MIN_DESCENT_HEIGHT}

    async def fetch_ground_speed(self):
        """
        Fetch ground speed data from MAVLink2Rest. (onyl speed in horizontal plane)

        This value is critical for calculating the drone's speed over the ground, which is important for various control algorithms.

        Returns:
            float: The ground speed in m/s.
        """
        velocity_data = await self.fetch_data_from_uri("/v1/mavlink/vehicles/1/components/1/messages/LOCAL_POSITION_NED")
        if velocity_data:
            message = velocity_data.get("message", {})
            try:
                vx = float(message.get("vx", 0))
                vy = float(message.get("vy", 0))
                ground_speed = float(math.sqrt(vx**2+vy**2))
            except (ValueError, TypeError):
                self.logger.warning("Invalid ground speed data received, falling back to 0.")
                ground_speed = 0.0
            return ground_speed
        return 0.0
    
    async def fetch_throttle_percent(self):
        """
        Fetch throttle percent data from MAVLink2Rest.

        This value is critical for calculating the drone's inital throttle when switching to offboard.

        Returns:
            uint16_t: Current throttle setting (0 to 100).
        """
        throttle_data = await self.fetch_data_from_uri("/v1/mavlink/vehicles/1/components/1/messages/VFR_HUD")
        if throttle_data:
            message = throttle_data.get("message", {})
            try:
                throttle_percent = uint16(message.get("throttle", 50))
            except (ValueError, TypeError):
                self.logger.warning("Invalid throttle data received, falling back to 50.")
                throttle_percent = uint16(50)
            return throttle_percent
        return 0.0
