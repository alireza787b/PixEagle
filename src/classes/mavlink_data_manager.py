import threading
import time
import requests
import logging

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
            self.logger.debug(f"Fetching data from {url}")
            response = requests.get(url)
            response.raise_for_status()
            json_data = response.json()
            self.logger.debug(f"Raw data received: {json_data}")

            with self._lock:
                # Iterate through the data points defined in Parameters
                for point_name, json_path in self.data_points.items():
                    self.logger.debug(f"Extracting {point_name} using path {json_path}")
                    if point_name == "arm_status":
                        # Special handling for arm status
                        base_mode = self._extract_data_from_json(json_data, "/vehicles/1/components/191/messages/HEARTBEAT/message/base_mode/bits")
                        self.data[point_name] = self._determine_arm_status(base_mode)
                    else:
                        value = self._extract_data_from_json(json_data, json_path)
                        if value is None:
                            self.logger.warning(f"Failed to retrieve data for {point_name} using path {json_path}. Assigning 'N/A'.")
                            value = "N/A"
                        self.data[point_name] = value

                self.logger.debug(f"Updated MAVLink data: {self.data}")

        except requests.RequestException as e:
            self.logger.error(f"Error fetching data from {url}: {e}")




    def _determine_arm_status(self, base_mode_bits):
        """
        Determine if the system is armed based on the base_mode bits.
        Typically, the armed status is indicated by a specific bit in base_mode.
        """
        ARM_BIT_MASK = 128  # Example mask, update with the correct one
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
