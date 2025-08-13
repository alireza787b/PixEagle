# src/classes/setpoint_sender.py
import asyncio
import threading
import time
import logging
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler

logger = logging.getLogger(__name__)

class SetpointSender(threading.Thread):
    """
    Enhanced schema-aware setpoint sender that automatically dispatches 
    the correct MAVSDK commands based on the follower profile's control type.
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
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        logger.info("SetpointSender thread started")
        
        try:
            while self.running:
                try:
                    # Update control type periodically
                    self._update_control_type()
                    
                    # Send appropriate commands based on control type
                    success = loop.run_until_complete(self._send_commands())
                    
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
            loop.close()
            logger.info("SetpointSender thread stopped")

    def _update_control_type(self):
        """
        Updates the cached control type periodically to handle dynamic profile changes.
        """
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

    async def _send_commands(self) -> bool:
        """
        Sends the appropriate commands based on the current control type.
        
        Returns:
            bool: True if commands sent successfully, False otherwise.
        """
        try:
            # Get current control type
            control_type = self._control_type or self.setpoint_handler.get_control_type()
            
            # Validate setpoint data
            setpoints = self.setpoint_handler.get_fields()
            if not setpoints:
                logger.warning("No setpoint data available to send")
                return False
            
            # Send commands based on control type
            if control_type == 'velocity_body':
                await self.px4_controller.send_body_velocity_commands()
                
            elif control_type == 'attitude_rate':
                await self.px4_controller.send_attitude_rate_commands()
                
            else:
                logger.error(f"Unknown control type: {control_type}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error sending commands: {e}")
            return False

    def _print_current_setpoint(self):
        """
        Prints current setpoint information for debugging.
        """
        try:
            setpoints = self.setpoint_handler.get_fields()
            control_type = self._control_type or self.setpoint_handler.get_control_type()
            profile_name = self.setpoint_handler.get_display_name()
            
            if setpoints:
                # Format setpoint values for display
                formatted_setpoints = {k: f"{v:.3f}" for k, v in setpoints.items()}
                
                print(f"[{profile_name}] {control_type.upper()}: {formatted_setpoints}")
                
                # Additional debug info
                if hasattr(self, 'error_count') and self.error_count > 0:
                    print(f"  └─ Error count: {self.error_count}")
                    
            else:
                print(f"[{profile_name}] No setpoint data available")
                
        except Exception as e:
            print(f"Error printing setpoint debug info: {e}")

    def get_status(self) -> dict:
        """
        Returns current status information for monitoring.
        
        Returns:
            dict: Status information including error counts and configuration.
        """
        try:
            return {
                'running': self.running,
                'control_type': self._control_type,
                'profile_name': self.setpoint_handler.get_display_name(),
                'error_count': self.error_count,
                'max_errors': self.max_consecutive_errors,
                'send_rate_hz': 1.0 / Parameters.SETPOINT_PUBLISH_RATE_S,
                'last_schema_check': self._last_schema_check,
                'available_fields': list(self.setpoint_handler.get_fields().keys())
            }
        except Exception as e:
            return {'error': f'Failed to get status: {e}'}

    def update_setpoint_handler(self, new_setpoint_handler: SetpointHandler):
        """
        Updates the setpoint handler for dynamic profile switching.
        
        Args:
            new_setpoint_handler (SetpointHandler): New setpoint handler to use.
        """
        try:
            old_profile = self.setpoint_handler.get_display_name()
            self.setpoint_handler = new_setpoint_handler
            new_profile = new_setpoint_handler.get_display_name()
            
            # Reset control type cache to force update
            self._control_type = None
            self._last_schema_check = 0
            
            # Reset error count
            self.error_count = 0
            
            logger.info(f"SetpointSender profile switched: {old_profile} → {new_profile}")
            
        except Exception as e:
            logger.error(f"Error updating setpoint handler: {e}")

    def validate_configuration(self) -> bool:
        """
        Validates the current setpoint sender configuration.
        
        Returns:
            bool: True if configuration is valid, False otherwise.
        """
        try:
            # Check setpoint handler
            if not self.setpoint_handler:
                logger.error("No setpoint handler configured")
                return False
                
            # Check PX4 controller
            if not self.px4_controller:
                logger.error("No PX4 controller configured")
                return False
                
            # Check required methods exist
            control_type = self.setpoint_handler.get_control_type()
            
            if control_type == 'velocity_body':
                if not hasattr(self.px4_controller, 'send_body_velocity_commands'):
                    logger.error("PX4 controller missing send_body_velocity_commands method")
                    return False
                    
            elif control_type == 'attitude_rate':
                if not hasattr(self.px4_controller, 'send_attitude_rate_commands'):
                    logger.error("PX4 controller missing send_attitude_rate_commands method")
                    return False
                    
            # Validate setpoint handler profile
            if hasattr(self.setpoint_handler, 'validate_profile_consistency'):
                if not self.setpoint_handler.validate_profile_consistency():
                    logger.error("Setpoint handler profile validation failed")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Error validating configuration: {e}")
            return False

    def stop(self):
        """
        Stops the setpoint sender thread gracefully.
        """
        logger.info("Stopping SetpointSender...")
        self.running = False
        
        # Wait for thread to finish with timeout
        self.join(timeout=5.0)
        
        if self.is_alive():
            logger.warning("SetpointSender thread did not stop gracefully within timeout")
        else:
            logger.info("SetpointSender stopped successfully")