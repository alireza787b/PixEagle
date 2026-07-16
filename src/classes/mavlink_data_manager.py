from collections import deque
import threading
import time
import requests
import logging
import asyncio
from typing import Dict, Optional
from .parameters import Parameters
from .logging_manager import logging_manager
import math

class MavlinkDataManager:
    MAX_STALE_TIMEOUT_S = 5.0
    MALFORMED_PAYLOAD_WARNING_INTERVAL_S = 10.0
    REQUIRED_FOLLOWER_MESSAGES = ("attitude", "altitude", "ground_speed")
    FOLLOWER_MESSAGE_NAMES = REQUIRED_FOLLOWER_MESSAGES + ("throttle",)

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
        self.request_timeout_s = self._validate_float_config(
            "MAVLINK_REQUEST_TIMEOUT_S",
            getattr(Parameters, "MAVLINK_REQUEST_TIMEOUT_S", 5.0),
            default=5.0,
            minimum=0.1,
            maximum=30.0,
        )
        self.request_retries = self._validate_int_config(
            "MAVLINK_REQUEST_RETRIES",
            getattr(Parameters, "MAVLINK_REQUEST_RETRIES", 0),
            default=0,
            minimum=0,
            maximum=5,
        )
        self.stale_timeout_s = self._validate_float_config(
            "MAVLINK_STALE_TIMEOUT_S",
            getattr(Parameters, "MAVLINK_STALE_TIMEOUT_S", 2.0),
            default=2.0,
            minimum=0.1,
            maximum=self.MAX_STALE_TIMEOUT_S,
        )
        self.data = {}  # Stores the fetched data
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.RLock()
        self.velocity_buffer = deque(maxlen=10)  # Buffer for velocity smoothing
        self.min_velocity_threshold = 0.5  # m/s, adjust based on your drone's characteristics
        self.gamma = 0

        # Connection state tracking
        self.connection_state = "disconnected"  # disconnected, connecting, connected, error
        self.last_successful_connection = None
        self.last_successful_fetch_monotonic_s = None
        self.last_fetch_attempt_monotonic_s = None
        self.last_request_result = "not_attempted"
        self.last_aggregate_payload_monotonic_s = None
        self.aggregate_payload_sample_count = 0
        self.aggregate_payload_last_error = None
        self._follower_message_status = {
            name: {
                "valid": False,
                "last_valid_monotonic_s": None,
                "last_attempt_monotonic_s": None,
                "last_result": "not_attempted",
                "last_error": None,
                "valid_sample_count": 0,
                "invalid_sample_count": 0,
                "suppressed_warning_count": 0,
            }
            for name in self.FOLLOWER_MESSAGE_NAMES
        }
        self._last_malformed_warning_monotonic_s = {}
        self.connection_error_count = 0
        self.last_error = None
        self.last_status_log = 0  # For throttling status messages
        self._validation_timeout_until_monotonic_s = None
        self._validation_timeout_reason = None

        # Flight mode monitoring for Offboard exit detection
        self.last_flight_mode = None
        self.offboard_mode_code = 393216  # PX4 Offboard mode
        self._offboard_exit_callback = None  # Callback for app_controller

        # Setup logging
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _validate_float_config(name, value, *, default, minimum, maximum):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            logging.getLogger(__name__).warning(
                "Invalid %s=%r; using default %.3f",
                name,
                value,
                default,
            )
            return default
        if not math.isfinite(parsed) or parsed < minimum:
            logging.getLogger(__name__).warning(
                "%s must be finite and >= %.3f, got %r; using default %.3f",
                name,
                minimum,
                value,
                default,
            )
            return default
        if parsed > maximum:
            logging.getLogger(__name__).warning(
                "%s %.3f exceeds %.3f; clamping",
                name,
                parsed,
                maximum,
            )
            return maximum
        return parsed

    @staticmethod
    def _validate_int_config(name, value, *, default, minimum, maximum):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            logging.getLogger(__name__).warning(
                "Invalid %s=%r; using default %d",
                name,
                value,
                default,
            )
            return default
        if parsed < minimum:
            logging.getLogger(__name__).warning(
                "%s must be >= %d, got %r; using default %d",
                name,
                minimum,
                value,
                default,
            )
            return default
        return min(parsed, maximum)

    def start_polling(self):
        """
        Start the polling thread if enabled.
        """
        if self.enabled:
            if self._thread is not None and self._thread.is_alive():
                return True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._poll_data,
                name="PixEagleMAVLink2RESTPolling",
            )
            self._thread.start()
            logging_manager.log_operation(self.logger, "MAVLink Polling", "info", "Started")
            return True
        else:
            logging_manager.log_operation(self.logger, "MAVLink Polling", "info", "Disabled in configuration")
            return False

    def stop_polling(self):
        """
        Stop the polling thread.
        """
        thread = self._thread
        if not self.enabled or thread is None:
            return True

        self._stop_event.set()
        join_timeout_s = (
            self.request_timeout_s * (self.request_retries + 1)
        ) + 1.0
        thread.join(timeout=join_timeout_s)
        stopped = not thread.is_alive()
        if stopped:
            logging_manager.log_operation(
                self.logger,
                "MAVLink Polling",
                "info",
                "Stopped",
            )
        else:
            self.logger.error(
                "MAVLink2REST polling thread did not stop within %.2f seconds",
                join_timeout_s,
            )
        return stopped

    def _poll_data(self):
        """
        Poll data at regular intervals and store it in a dictionary.
        """
        while not self._stop_event.is_set():
            self._fetch_and_parse_all_data()
            self._stop_event.wait(self.polling_interval)

    def _fetch_and_parse_all_data(self):
        """
        Fetch all MAVLink data in a single request and parse it into the data dictionary.
        """
        try:
            # Update connection state
            with self._lock:
                if self.connection_state in ("disconnected", "error"):
                    self.connection_state = "connecting"

            json_data = self._request_json("/v1/mavlink")

            # Log polling activity
            logging_manager.log_polling_activity(self.logger, "MAVLink", True)

            with self._lock:
                # Iterate through the data points defined in Parameters
                for point_name, json_path in self.data_points.items():
                    if point_name in ["vn", "ve", "vd"]:
                        value = self._extract_data_from_json(json_data, json_path)
                        try:
                            parsed_value = float(value)
                            self.data[point_name] = (
                                parsed_value if math.isfinite(parsed_value) else None
                            )
                        except (TypeError, ValueError):
                            self.data[point_name] = None
                    elif point_name == "flight_path_angle":
                        self.data[point_name] = self._calculate_flight_path_angle()
                        self.gamma = self.data[point_name] #temporary we might need this
                    elif point_name == "arm_status":
                        base_mode = self._extract_data_from_json(json_data, "/vehicles/1/components/191/messages/HEARTBEAT/message/base_mode/bits")
                        self.data[point_name] = self._determine_arm_status(base_mode)
                    else:
                        value = self._extract_data_from_json(json_data, json_path)
                        if value is None:
                            value = "N/A"
                        else:
                            if point_name in ["latitude", "longitude"]:
                                try:
                                    value = float(value) / 1e7
                                except (ValueError, TypeError) as e:
                                    self.logger.error(f"Failed to convert {point_name} value to float for division: {e}")
                                    value = "N/A"
                            elif point_name == "voltage":
                                try:
                                    # SYS_STATUS.voltage_battery is in millivolts per MAVLink spec
                                    mv = float(value)
                                    value = mv / 1000.0
                                except (ValueError, TypeError) as e:
                                    self.logger.error(f"Failed to convert voltage from millivolts: {e}")
                                    value = "N/A"
                        self.data[point_name] = value

            self._record_aggregate_payload_success()

            # Monitor flight mode transitions for Offboard exit detection
            if 'flight_mode' in self.data:
                current_flight_mode = self.data.get('flight_mode')
                if current_flight_mode != self.last_flight_mode and self.last_flight_mode is not None:
                    # Flight mode has changed
                    self._handle_flight_mode_change(self.last_flight_mode, current_flight_mode)
                self.last_flight_mode = current_flight_mode

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
            self._record_aggregate_payload_failure("Connection refused - server not running")
            self._handle_connection_error("Connection refused - server not running")
        except requests.exceptions.Timeout:
            self._record_aggregate_payload_failure("Connection timeout - server not responding")
            self._handle_connection_error("Connection timeout - server not responding")
        except requests.RequestException as e:
            self._record_aggregate_payload_failure(f"Request failed: {str(e)[:50]}...")
            self._handle_connection_error(f"Request failed: {str(e)[:50]}...")
        except Exception as e:
            self._record_aggregate_payload_failure(f"Unexpected error: {str(e)[:50]}...")
            self._handle_connection_error(f"Unexpected error: {str(e)[:50]}...")
    
    def _handle_connection_error(self, error_reason):
        """Handle connection errors with clean, throttled logging."""
        with self._lock:
            self.last_fetch_attempt_monotonic_s = time.monotonic()
            self.connection_state = "error"
            self.last_request_result = "failure"
            self.connection_error_count += 1
            self.last_error = error_reason
        
        # Log connection status and polling activity
        logging_manager.log_connection_status(
            self.logger, "MAVLink", False, 
            f"{error_reason} ({self.mavlink_host}:{self.mavlink_port})"
        )
        logging_manager.log_polling_activity(self.logger, "MAVLink", False, error_reason)

    def inject_timeout_for_validation(
        self,
        *,
        failure_count=1,
        reason="sitl_mavlink2rest_timeout",
        force_stale=True,
        timeout_window_s=2.0,
    ):
        """
        Record validation-only MAVLink2REST timeout state without touching services.

        This hook exercises PixEagle's local telemetry freshness/status contract.
        It does not stop MAVLink2REST, PX4, Docker, MAVLink routing, or network
        interfaces. During the bounded timeout window, PixEagle's own
        MAVLink2REST client requests fail locally before calling `requests.get`.
        """
        try:
            count = int(failure_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("failure_count must be an integer") from exc

        if count < 1 or count > 100:
            raise ValueError("failure_count must be between 1 and 100")

        try:
            window_s = float(timeout_window_s)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout_window_s must be a number") from exc
        if not math.isfinite(window_s) or window_s < 0.0 or window_s > 30.0:
            raise ValueError("timeout_window_s must be finite and between 0 and 30")

        now = time.monotonic()
        with self._lock:
            self.last_fetch_attempt_monotonic_s = now
            self._validation_timeout_reason = reason
            self._validation_timeout_until_monotonic_s = (
                now + window_s if window_s > 0.0 else None
            )
            if force_stale and self.last_successful_fetch_monotonic_s is not None:
                stale_age_s = self.stale_timeout_s + 0.001
                stale_timestamp = now - stale_age_s
                self.last_successful_fetch_monotonic_s = min(
                    self.last_successful_fetch_monotonic_s,
                    stale_timestamp,
                )
                if self.last_aggregate_payload_monotonic_s is not None:
                    self.last_aggregate_payload_monotonic_s = min(
                        self.last_aggregate_payload_monotonic_s,
                        stale_timestamp,
                    )
                for status in self._follower_message_status.values():
                    if status["last_valid_monotonic_s"] is not None:
                        status["last_valid_monotonic_s"] = min(
                            status["last_valid_monotonic_s"],
                            stale_timestamp,
                        )

        error_reason = f"Connection timeout - {reason}"
        for _ in range(count):
            self._handle_connection_error(error_reason)

        return {
            "applied_failure_count": count,
            "failure_reason": reason,
            "force_stale": bool(force_stale),
            "timeout_window_s": window_s,
            "mavlink_telemetry": self.get_connection_status(),
        }

    def _validation_timeout_active(self, now=None):
        """Return whether a validation-only local timeout window is active."""
        with self._lock:
            deadline = self._validation_timeout_until_monotonic_s
            if deadline is None:
                return False

            now = time.monotonic() if now is None else now
            if now <= deadline:
                return True

            self._validation_timeout_until_monotonic_s = None
            self._validation_timeout_reason = None
            return False

    def _validation_timeout_exception(self):
        if not self._validation_timeout_active():
            return None

        with self._lock:
            reason = self._validation_timeout_reason or "sitl_mavlink2rest_timeout"
        timeout_cls = getattr(getattr(requests, "exceptions", None), "Timeout", None)
        if not isinstance(timeout_cls, type) or not issubclass(timeout_cls, BaseException):
            timeout_cls = TimeoutError
        return timeout_cls(f"Validation MAVLink2REST timeout - {reason}")

    def _record_successful_fetch(self):
        """Record transport success without claiming any payload is usable."""
        with self._lock:
            was_connected = self.connection_state == "connected"
            self.connection_state = "connected"
            self.last_successful_connection = time.time()
            self.last_successful_fetch_monotonic_s = time.monotonic()
            self.last_fetch_attempt_monotonic_s = self.last_successful_fetch_monotonic_s
            self.last_request_result = "success"
            self.connection_error_count = 0
            self.last_error = None
        if not was_connected:
            logging_manager.log_connection_status(
                self.logger,
                "MAVLink",
                True,
                f"to {self.mavlink_host}:{self.mavlink_port}",
            )

    def _record_aggregate_payload_success(self):
        """Record successful parsing of the aggregate `/v1/mavlink` payload."""
        with self._lock:
            self.last_aggregate_payload_monotonic_s = time.monotonic()
            self.aggregate_payload_sample_count += 1
            self.aggregate_payload_last_error = None

    def _record_aggregate_payload_failure(self, reason):
        """Record aggregate payload failure independently of transport history."""
        with self._lock:
            self.aggregate_payload_last_error = str(reason)

    def _record_follower_message_result(
        self,
        name,
        *,
        valid,
        reason=None,
        malformed=False,
        completed_at_monotonic_s=None,
    ):
        """Record follower-message validity without conflating it with HTTP health."""
        if name not in self._follower_message_status:
            raise ValueError(f"Unknown follower message health key: {name}")
        now = (
            time.monotonic()
            if completed_at_monotonic_s is None
            else float(completed_at_monotonic_s)
        )
        with self._lock:
            status = self._follower_message_status[name]
            status["last_attempt_monotonic_s"] = now
            status["valid"] = bool(valid)
            if valid:
                status["last_valid_monotonic_s"] = now
                status["last_result"] = "valid"
                status["last_error"] = None
                status["valid_sample_count"] += 1
            else:
                status["last_result"] = "invalid"
                status["last_error"] = str(reason or "payload unavailable")
                status["invalid_sample_count"] += 1

        if malformed:
            self._warn_malformed_payload(name, str(reason or "invalid payload"), now)

    def _warn_malformed_payload(self, name, reason, now=None):
        """Rate-limit malformed-payload warnings independently per message type."""
        now = time.monotonic() if now is None else now
        should_log = False
        with self._lock:
            last_warning = self._last_malformed_warning_monotonic_s.get(name)
            if (
                last_warning is None
                or now - last_warning >= self.MALFORMED_PAYLOAD_WARNING_INTERVAL_S
            ):
                self._last_malformed_warning_monotonic_s[name] = now
                should_log = True
            else:
                self._follower_message_status[name][
                    "suppressed_warning_count"
                ] += 1
        if should_log:
            self.logger.warning(
                "MAVLink2REST %s payload is incomplete or invalid: %s",
                name,
                reason,
            )

    def _request_json(self, uri):
        """Fetch one MAVLink2REST URI with configured timeout and retry policy."""
        url = f"http://{self.mavlink_host}:{self.mavlink_port}{uri}"
        attempts = self.request_retries + 1
        last_error = None
        for attempt in range(1, attempts + 1):
            with self._lock:
                self.last_fetch_attempt_monotonic_s = time.monotonic()
            try:
                validation_timeout = self._validation_timeout_exception()
                if validation_timeout is not None:
                    raise validation_timeout
                response = requests.get(url, timeout=self.request_timeout_s)
                response.raise_for_status()
                json_data = response.json()
                self._record_successful_fetch()
                return json_data
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    self.logger.debug(
                        "MAVLink2REST request failed on attempt %d/%d for %s: %s",
                        attempt,
                        attempts,
                        uri,
                        exc,
                    )
                    continue
                raise
        raise last_error
            
            
    def _calculate_flight_path_angle(self):
        vn = self.data.get("vn")
        ve = self.data.get("ve")
        vd = self.data.get("vd")
        if not all(
            isinstance(value, (int, float)) and math.isfinite(float(value))
            for value in (vn, ve, vd)
        ):
            return None

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
            return self.data.get(point)

    async def fetch_data_from_uri(self, uri):
        """
        Fetch data from a specific URI and return the parsed JSON response.

        Args:
            uri (str): The URI to fetch the data from.

        Returns:
            dict: The parsed JSON data from the response.
        """
        try:
            return await asyncio.to_thread(self._request_json, uri)
        except Exception as e:
            self._handle_connection_error(f"Request failed: {str(e)[:50]}...")
            self.logger.error(f"Error fetching data from MAVLink2REST URI {uri}: {e}")
            return None

    def get_connection_status(self):
        """Return MAVLink2REST connection and telemetry freshness diagnostics."""
        now = time.monotonic()
        with self._lock:
            validation_timeout_active = self._validation_timeout_active(now)
            age_s = None
            fresh = False
            if self.last_successful_fetch_monotonic_s is not None:
                age_s = max(0.0, now - self.last_successful_fetch_monotonic_s)
                fresh = age_s <= self.stale_timeout_s

            connection_state = "error" if validation_timeout_active else self.connection_state
            last_error = (
                f"Connection timeout - {self._validation_timeout_reason}"
                if validation_timeout_active
                else self.last_error
            )

            if not self.enabled:
                status = "disabled"
                fresh = False
            elif validation_timeout_active and self.last_successful_fetch_monotonic_s is not None:
                status = "stale"
                fresh = False
            elif validation_timeout_active:
                status = "error"
                fresh = False
            elif connection_state == "connected" and fresh:
                status = "fresh"
            elif connection_state == "connected":
                status = "stale"
            elif connection_state == "error" and self.last_successful_fetch_monotonic_s is not None:
                status = "stale"
            else:
                status = connection_state

            aggregate_age_s = (
                max(0.0, now - self.last_aggregate_payload_monotonic_s)
                if self.last_aggregate_payload_monotonic_s is not None
                else None
            )
            aggregate_fresh = bool(
                self.enabled
                and aggregate_age_s is not None
                and aggregate_age_s <= self.stale_timeout_s
            )
            follower_health = self._build_follower_message_health(now)

            return {
                "enabled": self.enabled,
                "status": status,
                "connection_state": connection_state,
                "fresh": fresh,
                "last_success_age_s": age_s,
                "stale_timeout_s": self.stale_timeout_s,
                "request_timeout_s": self.request_timeout_s,
                "request_retries": self.request_retries,
                "connection_error_count": self.connection_error_count,
                "last_error": last_error,
                "endpoint": f"http://{self.mavlink_host}:{self.mavlink_port}",
                "validation_timeout_active": validation_timeout_active,
                "transport_fresh": fresh,
                "aggregate_payload_fresh": aggregate_fresh,
                "aggregate_payload_age_s": aggregate_age_s,
                "follower_messages_fresh": follower_health["complete_and_fresh"],
            }

    def _build_follower_message_health(self, now):
        """Build follower-message freshness while the manager lock is held."""
        messages = {}
        fresh_timestamps = []
        for name, source in self._follower_message_status.items():
            last_valid = source["last_valid_monotonic_s"]
            last_attempt = source["last_attempt_monotonic_s"]
            valid_age_s = (
                max(0.0, now - last_valid) if last_valid is not None else None
            )
            attempt_age_s = (
                max(0.0, now - last_attempt) if last_attempt is not None else None
            )
            fresh = bool(
                self.enabled
                and source["last_result"] == "valid"
                and valid_age_s is not None
                and valid_age_s <= self.stale_timeout_s
            )
            if fresh and name in self.REQUIRED_FOLLOWER_MESSAGES:
                fresh_timestamps.append(last_valid)
            messages[name] = {
                "valid": bool(source["valid"]),
                "fresh": fresh,
                "last_result": source["last_result"],
                "last_valid_age_s": valid_age_s,
                "last_attempt_age_s": attempt_age_s,
                "last_error": source["last_error"],
                "valid_sample_count": source["valid_sample_count"],
                "invalid_sample_count": source["invalid_sample_count"],
                "suppressed_warning_count": source["suppressed_warning_count"],
            }

        complete_and_fresh = all(
            messages[name]["fresh"] for name in self.REQUIRED_FOLLOWER_MESSAGES
        )
        temporal_skew_s = (
            max(fresh_timestamps) - min(fresh_timestamps)
            if complete_and_fresh and fresh_timestamps
            else None
        )
        return {
            "required": list(self.REQUIRED_FOLLOWER_MESSAGES),
            "complete_and_fresh": complete_and_fresh,
            "temporal_skew_s": temporal_skew_s,
            "messages": messages,
        }

    def get_telemetry_health(self):
        """Return typed MAVLink2REST health separated by request and payload state."""
        legacy_status = self.get_connection_status()
        now = time.monotonic()

        with self._lock:
            latest_request_age_s = None
            if self.last_fetch_attempt_monotonic_s is not None:
                latest_request_age_s = max(0.0, now - self.last_fetch_attempt_monotonic_s)

            validation_timeout_active = legacy_status["validation_timeout_active"]
            latest_request_result = self.last_request_result or "not_attempted"
            if validation_timeout_active:
                latest_request_result = "failure"

            data_keys = sorted(str(key) for key in self.data.keys())
            has_payload = bool(data_keys)
            last_success_age_s = legacy_status["last_success_age_s"]
            fresh = bool(legacy_status["fresh"])
            has_success = last_success_age_s is not None
            connection_state = legacy_status["connection_state"]
            aggregate_age_s = (
                max(0.0, now - self.last_aggregate_payload_monotonic_s)
                if self.last_aggregate_payload_monotonic_s is not None
                else None
            )
            aggregate_fresh = bool(
                self.enabled
                and aggregate_age_s is not None
                and aggregate_age_s <= self.stale_timeout_s
            )
            follower_health = self._build_follower_message_health(now)

            if not self.enabled:
                health_status = "disabled"
                consumer_guidance = "disabled"
            elif not has_success and connection_state == "connecting":
                health_status = "connecting"
                consumer_guidance = "connecting"
            elif not has_success:
                health_status = "error" if connection_state == "error" else "disconnected"
                consumer_guidance = "unavailable"
            elif not fresh:
                health_status = "stale"
                consumer_guidance = "stale"
            elif latest_request_result == "failure" or connection_state == "error":
                health_status = "degraded"
                consumer_guidance = "degraded_latest_request_failed"
            else:
                health_status = "healthy"
                consumer_guidance = "usable"

            return {
                "schema_version": 1,
                "source": "mavlink2rest",
                "enabled": self.enabled,
                "status": health_status,
                "consumer_guidance": consumer_guidance,
                "transport": {
                    "state": connection_state,
                    "latest_request_ok": self.enabled
                    and latest_request_result == "success"
                    and not validation_timeout_active,
                    "latest_request_result": latest_request_result,
                    "latest_request_age_s": latest_request_age_s,
                    "fresh": fresh,
                    "last_success_age_s": last_success_age_s,
                    "last_error": legacy_status["last_error"],
                    "error_count": self.connection_error_count,
                    "validation_timeout_active": validation_timeout_active,
                    "request_timeout_s": self.request_timeout_s,
                    "request_retries": self.request_retries,
                    "endpoint": legacy_status["endpoint"],
                },
                "request_freshness": {
                    "fresh": fresh,
                    "last_success_age_s": last_success_age_s,
                    "stale_timeout_s": self.stale_timeout_s,
                    "last_success_monotonic_available": has_success,
                },
                "payload": {
                    "has_payload": has_payload,
                    "sample_count": len(data_keys),
                    "available_keys": data_keys,
                    "flight_mode": self.data.get("flight_mode"),
                    "arm_status": self.data.get("arm_status"),
                    "fresh": has_payload and fresh,
                    "payload_age_s": last_success_age_s if has_payload else None,
                    "freshness_basis": "legacy_transport_success",
                },
                "aggregate_payload": {
                    "available": self.last_aggregate_payload_monotonic_s is not None,
                    "fresh": aggregate_fresh,
                    "last_success_age_s": aggregate_age_s,
                    "sample_count": self.aggregate_payload_sample_count,
                    "last_error": self.aggregate_payload_last_error,
                    "available_keys": data_keys,
                },
                "follower_messages": follower_health,
                "claim_boundary": (
                    "PixEagle local MAVLink2REST client health only; not PX4, SITL, "
                    "HIL, field, or follower-response proof."
                ),
                "timestamp": time.time(),
            }

    @staticmethod
    def _finite_message_values(message, field_names) -> Optional[Dict[str, float]]:
        """Parse required finite numeric fields without inventing defaults."""
        if not isinstance(message, dict):
            return None

        parsed = {}
        for field_name in field_names:
            if field_name not in message:
                return None
            try:
                value = float(message[field_name])
            except (TypeError, ValueError):
                return None
            if not math.isfinite(value):
                return None
            parsed[field_name] = value
        return parsed

    async def fetch_attitude_data(self) -> Optional[Dict[str, float]]:
        """
        Fetch attitude data (roll, pitch, yaw) from MAVLink2Rest.

        These values are specifically for follower usage and are independent of OSD data.
        If USE_MAVLINK2REST = True is enabled in parameters, these values are required.
        Missing, malformed, or non-finite payloads are unavailable. A measured
        zero remains a valid value and is never used as an error sentinel.

        Returns:
            A complete dictionary with roll, pitch, and yaw in degrees, or None.
        """
        attitude_data = await self.fetch_data_from_uri("/v1/mavlink/vehicles/1/components/1/messages/ATTITUDE")
        completed_at = time.monotonic()
        message = attitude_data.get("message") if isinstance(attitude_data, dict) else None
        values = self._finite_message_values(message, ("roll", "pitch", "yaw"))
        if values is None:
            reason = (
                "transport unavailable"
                if attitude_data is None
                else "required roll/pitch/yaw fields are incomplete or non-finite"
            )
            self._record_follower_message_result(
                "attitude",
                valid=False,
                reason=reason,
                malformed=attitude_data is not None,
                completed_at_monotonic_s=completed_at,
            )
            return None
        result = {
            "roll": math.degrees(values["roll"]),
            "pitch": math.degrees(values["pitch"]),
            "yaw": math.degrees(values["yaw"]),
        }
        self._record_follower_message_result(
            "attitude",
            valid=True,
            completed_at_monotonic_s=completed_at,
        )
        return result

    async def fetch_altitude_data(self) -> Optional[Dict[str, float]]:
        """
        Fetch altitude data from MAVLink2Rest.

        These values are specifically for follower usage and are independent of OSD data.
        If USE_MAVLINK2REST = True is enabled in parameters, these values are required.
        Missing, malformed, or non-finite values are unavailable. Safety limits
        are command constraints and are not telemetry substitutes.

        Returns:
            A complete dictionary with relative and AMSL altitudes, or None.
        """
        altitude_data = await self.fetch_data_from_uri("/v1/mavlink/vehicles/1/components/1/messages/ALTITUDE")
        completed_at = time.monotonic()
        message = altitude_data.get("message") if isinstance(altitude_data, dict) else None
        values = self._finite_message_values(
            message,
            ("altitude_relative", "altitude_amsl"),
        )
        if values is None:
            reason = (
                "transport unavailable"
                if altitude_data is None
                else "required relative/AMSL altitude fields are incomplete or non-finite"
            )
            self._record_follower_message_result(
                "altitude",
                valid=False,
                reason=reason,
                malformed=altitude_data is not None,
                completed_at_monotonic_s=completed_at,
            )
            return None
        self._record_follower_message_result(
            "altitude",
            valid=True,
            completed_at_monotonic_s=completed_at,
        )
        return values

    async def fetch_ground_speed(self) -> Optional[float]:
        """
        Fetch ground speed data from MAVLink2Rest. (onyl speed in horizontal plane)

        This value is critical for calculating the drone's speed over the ground, which is important for various control algorithms.

        Returns:
            Ground speed in m/s, or None when the payload is unavailable.
        """
        velocity_data = await self.fetch_data_from_uri("/v1/mavlink/vehicles/1/components/1/messages/LOCAL_POSITION_NED")
        completed_at = time.monotonic()
        message = velocity_data.get("message") if isinstance(velocity_data, dict) else None
        values = self._finite_message_values(message, ("vx", "vy"))
        if values is None:
            reason = (
                "transport unavailable"
                if velocity_data is None
                else "required vx/vy fields are incomplete or non-finite"
            )
            self._record_follower_message_result(
                "ground_speed",
                valid=False,
                reason=reason,
                malformed=velocity_data is not None,
                completed_at_monotonic_s=completed_at,
            )
            return None
        ground_speed = math.hypot(values["vx"], values["vy"])
        self._record_follower_message_result(
            "ground_speed",
            valid=True,
            completed_at_monotonic_s=completed_at,
        )
        return ground_speed
    
    async def fetch_throttle_percent(self) -> Optional[int]:
        """
        Fetch throttle percent data from MAVLink2Rest.

        This value is critical for calculating the drone's inital throttle when switching to offboard.

        Returns:
            Current throttle setting from 0 to 100, or None when unavailable.
        """
        throttle_data = await self.fetch_data_from_uri("/v1/mavlink/vehicles/1/components/1/messages/VFR_HUD")
        completed_at = time.monotonic()
        message = throttle_data.get("message") if isinstance(throttle_data, dict) else None
        values = self._finite_message_values(message, ("throttle",))
        if values is None:
            reason = (
                "transport unavailable"
                if throttle_data is None
                else "required throttle field is missing or non-finite"
            )
            self._record_follower_message_result(
                "throttle",
                valid=False,
                reason=reason,
                malformed=throttle_data is not None,
                completed_at_monotonic_s=completed_at,
            )
            return None
        throttle_percent = values["throttle"]
        if throttle_percent < 0.0 or throttle_percent > 100.0:
            self._record_follower_message_result(
                "throttle",
                valid=False,
                reason=f"value {throttle_percent} is outside 0..100",
                malformed=True,
                completed_at_monotonic_s=completed_at,
            )
            return None
        self._record_follower_message_result(
            "throttle",
            valid=True,
            completed_at_monotonic_s=completed_at,
        )
        return int(round(throttle_percent))

    def _handle_flight_mode_change(self, old_mode, new_mode):
        """
        Handle flight mode transitions and detect Offboard exit.

        This method detects when the drone exits Offboard mode (transitions from
        Offboard to any other flight mode). This can happen due to:
        - Pilot manual mode switch
        - RC override
        - Failsafe trigger (RTL, Land, etc.)
        - Any other mode change

        Args:
            old_mode: Previous flight mode code
            new_mode: Current flight mode code
        """
        try:
            # Check if we exited Offboard mode
            if old_mode == self.offboard_mode_code and new_mode != self.offboard_mode_code:
                # Offboard mode was exited - this is critical for follow mode
                self.logger.warning(f"Flight mode changed: Offboard (393216) → {new_mode}")

                # Notify registered callback (app_controller) about Offboard exit
                if self._offboard_exit_callback is not None:
                    try:
                        # Call the callback asynchronously
                        self._offboard_exit_callback(old_mode, new_mode)
                    except Exception as e:
                        self.logger.error(f"Error in Offboard exit callback: {e}")
            else:
                # Log other mode changes at debug level
                self.logger.debug(f"Flight mode changed: {old_mode} → {new_mode}")

        except Exception as e:
            self.logger.error(f"Error handling flight mode change: {e}")

    def register_offboard_exit_callback(self, callback):
        """
        Register a callback to be notified when the drone exits Offboard mode.

        The callback will be invoked when flight mode transitions from Offboard
        to any other mode. This allows the app_controller to automatically disable
        follow mode when Offboard is exited.

        Args:
            callback: Callable that accepts (old_mode, new_mode) parameters.
                     Should be async-aware or handle async execution internally.

        Example:
            mavlink_data_manager.register_offboard_exit_callback(
                lambda old, new: asyncio.create_task(app_controller._handle_offboard_mode_exit(old, new))
            )
        """
        self._offboard_exit_callback = callback
        self.logger.info("Offboard exit callback registered - automatic follow mode disablement enabled")
