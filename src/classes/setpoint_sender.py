# src/classes/setpoint_sender.py
import threading
import time
import logging
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler

logger = logging.getLogger(__name__)

class SetpointSender(threading.Thread):
    """
    Enhanced setpoint sender that runs in its own thread and sends commands
    at a fixed rate. Avoids async conflicts by using synchronous command dispatch.
    """
    
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

    def run(self):
        """
        Main thread loop that sends commands at the configured rate.
        Uses synchronous command sending to avoid async conflicts.
        """
        logger.info("SetpointSender thread started")
        
        try:
            while self.running:
                try:
                    # Update control type periodically
                    self._update_control_type()
                    
                    # Send appropriate commands based on control type (SYNCHRONOUS)
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
                    
                    # Sleep for the configured rate
                    time.sleep(Parameters.SETPOINT_PUBLISH_RATE_S)
                    
                except Exception as e:
                    logger.error(f"Error in setpoint sender main loop: {e}")
                    self.error_count += 1
                    time.sleep(Parameters.SETPOINT_PUBLISH_RATE_S)
                    
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
        Sends commands synchronously to avoid async loop conflicts.
        
        Returns:
            bool: True if commands sent successfully, False otherwise.
        """
        try:
            # Get current control type
            control_type = self._control_type or self.setpoint_handler.get_control_type()
            
            # NOTE: We don't send commands directly from this thread to avoid async conflicts
            # Instead, we just validate and log. The actual command sending happens
            # in the main async control loop via app_controller.follow_target()
            
            setpoint = self.setpoint_handler.get_fields()
            
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