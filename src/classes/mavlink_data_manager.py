import threading
import time
import requests
import logging
import asyncio
from .parameters import Parameters


class MavlinkDataManager:
    def __init__(self, mavlink_host, mavlink_port, polling_interval, data_points, enabled=True):
        """
        Initialize the MavlinkDataManager with necessary parameters.
        """
        self.mavlink_host = mavlink_host
        self.mavlink_port = mavlink_port
        self.polling_interval = polling_interval
        self.data_points = data_points  # Dictionary of data points to extract
        self.enabled = enabled
        self.data = {}  # Stores the fetched data
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Setup logging
        logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG for detailed logging
        self.logger = logging.getLogger(__name__)

    def start_polling(self):
        """
        Start the polling thread if enabled.
        """
        if self.enabled:
            self._thread = threading.Thread(target=self._poll_data)
            self._thread.start()
            self.logger.info("Started polling MAVLink data.")
        else:
            self.logger.info("MAVLink polling is disabled.")

    def stop_polling(self):
        """
        Stop the polling thread.
        """
        if self.enabled:
            self._stop_event.set()
            self._thread.join()
            self.logger.info("Stopped polling MAVLink data.")

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
        try:
            url = f"http://{self.mavlink_host}:{self.mavlink_port}/v1/mavlink"
            response = requests.get(url)
            response.raise_for_status()
            json_data = response.json()

            with self._lock:
                # Iterate through the data points defined in Parameters
                for point_name, json_path in self.data_points.items():
                    if point_name == "arm_status":
                        base_mode = self._extract_data_from_json(json_data, "/vehicles/1/components/191/messages/HEARTBEAT/message/base_mode/bits")
                        self.data[point_name] = self._determine_arm_status(base_mode)
                    else:
                        value = self._extract_data_from_json(json_data, json_path)
                        if value is None:
                            self.logger.warning(f"Failed to retrieve data for {point_name} using path {json_path}. Assigning 'N/A'.")
                            value = "N/A"
                        else:
                            if point_name in ["latitude", "longitude"]:
                                try:
                                    value = float(value) / 1e7
                                except (ValueError, TypeError) as e:
                                    self.logger.error(f"Failed to convert {point_name} value to float for division: {e}")
                                    value = "N/A"
                        self.data[point_name] = value
        except requests.RequestException as e:
            self.logger.error(f"Error fetching data from {url}: {e}")

    def _determine_arm_status(self, base_mode_bits):
        """
        Determine if the system is armed based on the base_mode bits.
        """
        ARM_BIT_MASK = 128  # Example mask, update with the correct one
        if base_mode_bits is None:
            return "Unknown"
        return "Armed" if base_mode_bits & ARM_BIT_MASK else "Disarmed"

    def _extract_data_from_json(self, data, json_path):
        """
        Helper function to extract a value from a nested JSON structure using a json_path.
        """
        keys = json_path.strip("/").split('/')
        for key in keys:
            if key in data:
                data = data[key]
            else:
                self.logger.debug(f"Key {key} not found in the current JSON level.")
                return None
        return data

    def get_data(self, point):
        """
        Retrieve the most recent data for a specified point.
        """
        with self._lock:
            if not self.enabled:
                return None  # Avoid unnecessary logging and simply return None
            return self.data.get(point, "N/A")

    async def fetch_data_from_uri(self, uri):
        """
        Fetch data from a specific URI and return the parsed JSON response.
        This method allows for more modular and targeted data retrieval.
        """
        url = f"http://{self.mavlink_host}:{self.mavlink_port}{uri}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Error fetching data from {url}: {e}")
            return None

    async def fetch_data_from_uri(self, uri):
        """
        Fetch data from a specific URI and return the parsed JSON response.
        This method allows for more modular and targeted data retrieval.
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
        """
        attitude_data = await self.fetch_data_from_uri("/v1/mavlink/vehicles/1/components/1/messages/ATTITUDE")
        if attitude_data:
            message = attitude_data.get("message", {})
            try:
                # Attempt to convert to float and fall back to 0 if invalid
                roll = float(message.get("roll", 0))
                pitch = float(message.get("pitch", 0))
                yaw = float(message.get("yaw", 0))
            except (ValueError, TypeError):
                # Log the error and use fallback values
                print("Warning: Invalid attitude data received, falling back to default values (0).")
                roll, pitch, yaw = 0, 0, 0
            return {
                "roll": roll,
                "pitch": pitch,
                "yaw": yaw
            }
        # Fallback if no data is retrieved
        return {"roll": 0, "pitch": 0, "yaw": 0}

    async def fetch_altitude_data(self):
        """
        Fetch altitude data from MAVLink2Rest.
        
        These values are specifically for follower usage and are independent of OSD data.
        If USE_MAVLINK2REST = True is enabled in parameters, these values are required.
        In case REST requests send invalid data, the altitude_relative will fall back to Parameters.MIN_DESCENT_HEIGHT.
        """
        altitude_data = await self.fetch_data_from_uri("/v1/mavlink/vehicles/1/components/1/messages/ALTITUDE")
        if altitude_data:
            message = altitude_data.get("message", {})
            try:
                # Attempt to convert to float and fall back to default altitude if invalid
                altitude_relative = float(message.get("altitude_relative", Parameters.MIN_DESCENT_HEIGHT))
                altitude_amsl = float(message.get("altitude_amsl", Parameters.MIN_DESCENT_HEIGHT))
            except (ValueError, TypeError):
                # Log the error and use fallback values
                print("Warning: Invalid altitude data received, falling back to default values (Parameters.MIN_DESCENT_HEIGHT).")
                altitude_relative, altitude_amsl = Parameters.MIN_DESCENT_HEIGHT, Parameters.MIN_DESCENT_HEIGHT
            return {
                "altitude_relative": altitude_relative,
                "altitude_amsl": altitude_amsl
            }
        # Fallback if no data is retrieved
        return {"altitude_relative": Parameters.MIN_DESCENT_HEIGHT, "altitude_amsl": Parameters.MIN_DESCENT_HEIGHT}
