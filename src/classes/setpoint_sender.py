# src/classes/setpoint_sender.py
import threading
import time
import logging
import math
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler

logger = logging.getLogger(__name__)

class SetpointSender(threading.Thread):
    """
    Setpoint monitor that runs in its own thread at a fixed period.

    This class validates/logs setpoint state only. MAVSDK command publication
    is owned by OffboardCommander.
    """

    DEFAULT_LOOP_PERIOD_S = 0.1
    MIN_LOOP_PERIOD_S = 0.001
    MAX_LOOP_PERIOD_S = 1.0
    
    def __init__(self, px4_controller, setpoint_handler: SetpointHandler):
        super().__init__(daemon=True)
        self.px4_controller = px4_controller
        self.setpoint_handler = setpoint_handler
        self.running = True
        self.error_count = 0
        self.max_consecutive_errors = 5
        
        # Cache control type to avoid repeated schema lookups
        self._control_type = None
        self._last_schema_check = 0
        self._schema_check_interval = 10  # seconds
        
        logger.info(f"SetpointSender initialized for profile: {setpoint_handler.get_display_name()}")

    def validate_configuration(self) -> bool:
        """
        Validate that the setpoint sender is properly configured.

        Returns:
            bool: True if configuration is valid
        """
        try:
            # Check if we have a valid control type
            if not hasattr(self.setpoint_handler, 'get_control_type'):
                logger.error("SetpointHandler missing get_control_type method")
                return False

            control_type = self.setpoint_handler.get_control_type()
            if not control_type:
                logger.error("Invalid control type from setpoint handler")
                return False

            # Check if we have required fields
            fields = self.setpoint_handler.get_fields()
            if not fields:
                logger.error("No fields available from setpoint handler")
                return False

            logger.info(f"SetpointSender validation passed: {control_type} with {len(fields)} fields")
            return True

        except Exception as e:
            logger.error(f"SetpointSender validation failed: {e}")
            return False

    def run(self):
        """
        Main thread loop that validates/logs setpoints at the configured period.
        """
        logger.info("SetpointSender thread started")
        
        try:
            loop_count = 0
            while self.running:
                try:
                    loop_count += 1

                    # DEBUG: Log every 20 loops.
                    if loop_count % 20 == 0:
                        logger.info(f"SetpointSender loop #{loop_count} - thread running normally")

                    # Update control type periodically
                    self._update_control_type()

                    # Validate/log current setpoint state. MAVSDK publication is
                    # owned by OffboardCommander.
                    success = self._send_commands_sync()
                    
                    # Handle error counting
                    if success:
                        self.error_count = 0
                    else:
                        self.error_count += 1
                        if self.error_count >= self.max_consecutive_errors:
                            logger.error(f"Too many consecutive send failures ({self.error_count}), "
                                       f"but continuing to try...")
                    
                    # Debug output
                    if Parameters.ENABLE_SETPOINT_DEBUGGING:
                        self._print_current_setpoint()
                    
                    time.sleep(self.get_loop_period_s())
                    
                except Exception as e:
                    logger.error(f"Error in setpoint sender main loop: {e}")
                    self.error_count += 1
                    time.sleep(self.get_loop_period_s())
                    
        except Exception as e:
            logger.error(f"Fatal error in setpoint sender thread: {e}")
        finally:
            logger.info("SetpointSender thread stopped")

    def _update_control_type(self):
        """Updates the cached control type periodically."""
        current_time = time.time()
        if current_time - self._last_schema_check > self._schema_check_interval:
            try:
                new_control_type = self.setpoint_handler.get_control_type()
                if new_control_type != self._control_type:
                    logger.info(f"Control type changed: {self._control_type} → {new_control_type}")
                    self._control_type = new_control_type
                    
                self._last_schema_check = current_time
                
            except Exception as e:
                logger.error(f"Error updating control type: {e}")

    def _send_commands_sync(self) -> bool:
        """
        Validate/log current setpoint fields without sending MAVSDK commands.
        
        Returns:
            bool: True if command fields were readable, False otherwise.
        """
        try:
            # Get current control type
            control_type = self._control_type or self.setpoint_handler.get_control_type()
            
            # NOTE: We don't send commands directly from this thread to avoid async conflicts.
            # Instead, we just validate and log. OffboardCommander owns publication.
            
            setpoint = self.setpoint_handler.get_fields()

            # DEBUG: Log setpoint values periodically
            if hasattr(self, '_setpoint_debug_count'):
                self._setpoint_debug_count += 1
            else:
                self._setpoint_debug_count = 1

            if self._setpoint_debug_count % 20 == 0:  # Every 20 calls (about 4 seconds)
                logger.info(f"SetpointSender current values: {control_type} -> {setpoint}")

            if Parameters.ENABLE_SETPOINT_DEBUGGING:
                logger.debug(f"SetpointSender ready to send {control_type}: {setpoint}")

            return True
            
        except Exception as e:
            logger.error(f"Error in synchronous command preparation: {e}")
            return False

    def _print_current_setpoint(self):
        """Prints the current setpoints for debugging purposes."""
        try:
            setpoints = self.setpoint_handler.get_fields()
            control_type = self._control_type or 'unknown'
            if setpoints:
                logger.debug(f"Current {control_type} setpoints: {setpoints}")
        except Exception as e:
            logger.error(f"Error printing setpoints: {e}")

    def get_status(self) -> dict:
        """Return lightweight thread/status diagnostics for shutdown and API health."""
        return {
            "running": self.running,
            "thread_alive": self.is_alive(),
            "error_count": self.error_count,
            "max_consecutive_errors": self.max_consecutive_errors,
            "control_type": self._control_type or self.setpoint_handler.get_control_type(),
            "loop_period_s": self.get_loop_period_s(),
            "sends_mavsdk_commands": False,
            "command_publication_source": "offboard_commander",
        }

    @classmethod
    def get_loop_period_s(cls) -> float:
        """Return the validated SetpointSender monitor loop period in seconds."""
        raw_period = getattr(
            Parameters,
            'SETPOINT_PUBLISH_RATE_S',
            cls.DEFAULT_LOOP_PERIOD_S,
        )
        try:
            period_s = float(raw_period)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid SETPOINT_PUBLISH_RATE_S=%r; using default %.3f s",
                raw_period,
                cls.DEFAULT_LOOP_PERIOD_S,
            )
            return cls.DEFAULT_LOOP_PERIOD_S

        if not math.isfinite(period_s) or period_s <= 0.0:
            logger.warning(
                "SETPOINT_PUBLISH_RATE_S must be positive seconds, got %r; "
                "using default %.3f s",
                raw_period,
                cls.DEFAULT_LOOP_PERIOD_S,
            )
            return cls.DEFAULT_LOOP_PERIOD_S

        if period_s < cls.MIN_LOOP_PERIOD_S:
            logger.warning(
                "SETPOINT_PUBLISH_RATE_S %.6f s is below %.6f s; clamping",
                period_s,
                cls.MIN_LOOP_PERIOD_S,
            )
            return cls.MIN_LOOP_PERIOD_S
        if period_s > cls.MAX_LOOP_PERIOD_S:
            logger.warning(
                "SETPOINT_PUBLISH_RATE_S %.3f s is above %.3f s; clamping",
                period_s,
                cls.MAX_LOOP_PERIOD_S,
            )
            return cls.MAX_LOOP_PERIOD_S

        return period_s

    def stop(self):
        """Stops the setpoint sender thread gracefully."""
        logger.info("Stopping SetpointSender...")
        self.running = False
        
        # Wait for thread to finish with timeout
        self.join(timeout=5.0)
        
        if self.is_alive():
            logger.warning("SetpointSender thread did not stop gracefully within timeout")
        else:
            logger.info("SetpointSender stopped successfully")
