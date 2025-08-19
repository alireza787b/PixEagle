import asyncio
import math
import logging
from mavsdk import System
from classes.parameters import Parameters
from mavsdk.offboard import OffboardError, VelocityNedYaw, VelocityBodyYawspeed, AttitudeRate
from classes.setpoint_handler import SetpointHandler

# Configure logging
logger = logging.getLogger(__name__)

class PX4InterfaceManager:

    FLIGHT_MODES = {
        458752: 'Stabilized',
        196608: 'Position',
        100925440: 'Land',
        393216: 'Offboard',
        50593792: 'Hold',
        84148224: 'Return',
        131072: 'Altitude',
        65536: 'Manual',
        327680: 'Acro',
        33816576: 'Takeoff',
        67371008: 'Mission',
        151257088: 'Precission Land'
        
    }

    def __init__(self, app_controller=None):
        """
        Initializes the PX4InterfaceManager and sets up the connection to the PX4 drone.
        Uses MAVSDK for offboard control, and optionally uses MAVLink2Rest for telemetry data.
        """
        self.app_controller = app_controller
        self.current_yaw = 0.0  # Current yaw in radians
        self.current_pitch = 0.0  # Current pitch in radians
        self.current_roll = 0.0  # Current roll in radians
        self.current_altitude = 0.0  # Current altitude in meters
        self.current_ground_speed = 0.0  # Ground speed in m/s
        self.camera_yaw_offset = Parameters.CAMERA_YAW_OFFSET
        self.update_task = None  # Task for telemetry updates
        normalized_profile_name = SetpointHandler.normalize_profile_name(Parameters.FOLLOWER_MODE)
        self.setpoint_handler = SetpointHandler(normalized_profile_name)    
        self.active_mode = False
        self.hover_throttle = 0.0
        self.failsafe_active = False

        # Determine if we are using MAVLink2Rest for telemetry data
        if Parameters.USE_MAVLINK2REST and self.app_controller:
            self.mavlink_data_manager = self.app_controller.mavlink_data_manager
            logger.info("Using MAVLink2Rest for telemetry data.")
        else:
            logger.info("Using MAVSDK for telemetry and offboard control.")
        
        # Setup MAVSDK connection for both telemetry and offboard control
        if Parameters.EXTERNAL_MAVSDK_SERVER:
            self.drone = System(mavsdk_server_address='localhost', port=50051)
        else:
            self.drone = System()
            
            
    async def _safe_mavsdk_call(self, coro):
        """
        Safely execute MAVSDK coroutine calls with proper error handling.
        
        Args:
            coro: Coroutine to execute safely
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            await coro
            return True
        except Exception as e:
            # Check if it's the specific async loop error
            if "attached to a different loop" in str(e):
                logger.debug("Async loop conflict detected, retrying...")
                # Try once more after a brief delay
                try:
                    await asyncio.sleep(0.001)  # 1ms delay
                    await coro
                    return True
                except Exception as retry_error:
                    logger.warning(f"MAVSDK call failed after retry: {retry_error}")
                    return False
            else:
                logger.error(f"MAVSDK call error: {e}")
                return False

    async def connect(self):
        """
        Connects to the drone using MAVSDK and starts telemetry updates.
        Even when using MAVLink2Rest for telemetry, MAVSDK is still used for offboard control.
        """
        await self.drone.connect(system_address=Parameters.SYSTEM_ADDRESS)
        self.active_mode = True
        logger.info("Connected to the drone.")
        self.update_task = asyncio.create_task(self.update_drone_data())

    async def update_drone_data(self):
        """
        Continuously updates the drone's telemetry data using the selected source.
        Uses MAVLink2Rest for telemetry if enabled, otherwise uses MAVSDK.
        The refresh rate is controlled by FOLLOWER_DATA_REFRESH_RATE.
        """
        refresh_rate = Parameters.FOLLOWER_DATA_REFRESH_RATE if hasattr(Parameters, 'FOLLOWER_DATA_REFRESH_RATE') else 1

        while self.active_mode:
            try:
                if Parameters.USE_MAVLINK2REST:
                    await self._update_telemetry_via_mavlink2rest()
                else:
                    await self._update_telemetry_via_mavsdk()
            except asyncio.CancelledError:
                logger.warning("Telemetry update task was cancelled.")
                break
            except Exception as e:
                logger.error(f"Error updating telemetry: {e}")
            await asyncio.sleep(refresh_rate)  # Use the refresh rate to control the update frequency

    async def _update_telemetry_via_mavlink2rest(self):
        """
        Updates telemetry data using MAVLink2Rest.
        Retrieves telemetry data through the MAVLink data manager using modular methods.
        Default values are set to zero in case of data loss or missing data.
        """
        try:
            # Fetch attitude data (roll, pitch, yaw)
            attitude_data = await self.mavlink_data_manager.fetch_attitude_data()
            self.current_roll = attitude_data.get("roll", 0.0)
            self.current_pitch = attitude_data.get("pitch", 0.0)
            self.current_yaw = attitude_data.get("yaw", 0.0)
            
            # Fetch altitude data
            altitude_data = await self.mavlink_data_manager.fetch_altitude_data()
            self.current_altitude = altitude_data.get("altitude_relative", 0.0)  # Or use "altitude_amsl" if required
            self.current_ground_speed = await self.mavlink_data_manager.fetch_ground_speed()

        except Exception as e:
            logger.error(f"Error updating telemetry via MAVLink2Rest: {e}")

    async def _update_telemetry_via_mavsdk(self):
        try:
            async for position in self.drone.telemetry.position():
                self.current_altitude = position.relative_altitude_m
            async for attitude in self.drone.telemetry.attitude_euler():
                self.current_yaw = attitude.yaw + self.camera_yaw_offset
                self.current_pitch = attitude.pitch
                self.current_roll = attitude.roll

            async for velocity in self.drone.telemetry.velocity_body():
                self.current_ground_speed = velocity.x_m_s  # Forward speed in m/s

        except Exception as e:
            logger.error(f"Error updating telemetry via MAVSDK: {e}")

    def get_orientation(self):
        """
        Returns the current orientation (yaw, pitch, roll) of the drone.
        """
        return self.current_yaw, self.current_pitch, self.current_roll
    
    def get_ground_speed(self):
        return self.current_ground_speed


    async def send_body_velocity_commands(self):
        """
        Sends body frame velocity commands to the drone in offboard mode, based on the active profile.
        This operation uses MAVSDK.
        """
        setpoint = self.setpoint_handler.get_fields()
        try:
            if setpoint is None:
                logger.error("Setpoint is None, cannot send commands.")
                return

            # Initialize variables to zero for the fields that might not be present
            vx, vy, vz, yaw_rate = 0.0, 0.0, 0.0, 0.0
            
            # Update values only if they are present in the current profile's setpoints
            if 'vel_x' in setpoint:
                vx = float(setpoint['vel_x'])
            if 'vel_y' in setpoint:
                vy = float(setpoint['vel_y'])
            if 'vel_z' in setpoint:
                vz = float(setpoint['vel_z'])
            if 'yaw_rate' in setpoint:
                yaw_rate = float(setpoint['yaw_rate'])

            logger.debug(f"Setting VELOCITY_BODY setpoint: Vx={vx}, Vy={vy}, Vz={vz}, Yaw rate={yaw_rate}")
            
            # Send the velocity commands to the drone
            next_setpoint = VelocityBodyYawspeed(vx, vy, vz, yaw_rate)
            await self._safe_mavsdk_call(
                self.drone.offboard.set_velocity_body(next_setpoint)
            )

        except OffboardError as e:
            logger.error(f"Failed to send offboard velocity command: {e}")
        except ValueError as ve:
            logger.error(f"ValueError: An error occurred while processing setpoint: {ve}")
        except Exception as ex:
            logger.error(f"An unexpected error occurred: {ex}")
            
    async def send_attitude_rate_commands(self):
        """
        Sends attitude rate commands to the drone in offboard mode.
        This operation uses MAVSDK.
        """
        setpoint = self.setpoint_handler.get_fields()

        try:
            if not isinstance(setpoint, dict):
                logger.error("Setpoint is not a dictionary. Cannot send commands.")
                return

            # Initialize variables to zero for the fields that might not be present
            roll_rate, pitch_rate, yaw_rate, thrust = 0.0, 0.0, 0.0, self.hover_throttle

            # Update values only if they are present in the current profile's setpoints
            roll_rate = float(setpoint.get('roll_rate', 0.0))
            pitch_rate = float(setpoint.get('pitch_rate', 0.0))
            yaw_rate = float(setpoint.get('yaw_rate', 0.0))
            thrust = float(setpoint.get('thrust', self.hover_throttle))

            logger.debug(f"Setting ATTITUDE_RATE setpoint: Roll Rate={roll_rate}, Pitch Rate={pitch_rate}, Yaw Rate={yaw_rate}, Thrust={thrust}")
            
            # Send the attitude rate commands to the drone
            next_setpoint = AttitudeRate(roll_rate, pitch_rate, yaw_rate, thrust)
            await self.drone.offboard.set_attitude_rate(next_setpoint)

        except OffboardError as e:
            logger.error(f"Failed to send offboard attitude rate command: {e}")
        except ValueError as ve:
            logger.error(f"ValueError: An error occurred while processing setpoint: {ve}")
        except Exception as ex:
            logger.error(f"An unexpected error occurred: {ex}")


    async def send_velocity_body_offboard_commands(self):
        """
        Sends body velocity offboard commands for quadcopter control.
        Uses the new body velocity field names (vel_body_fwd, vel_body_right, vel_body_down, yawspeed_deg_s).
        This operation uses MAVSDK VelocityBodyYawspeed.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized")
                return
                
            # Verify this is the correct control type
            if self.setpoint_handler.get_control_type() != 'velocity_body_offboard':
                logger.warning(f"Attempting to send velocity_body_offboard commands but control type is: {self.setpoint_handler.get_control_type()}")
                
            setpoint = self.setpoint_handler.get_fields()
            if not setpoint:
                logger.error("No setpoint data available")
                return

            # Extract body velocity fields with safe defaults
            vel_fwd = float(setpoint.get('vel_body_fwd', 0.0))      # Forward velocity
            vel_right = float(setpoint.get('vel_body_right', 0.0))  # Right velocity  
            vel_down = float(setpoint.get('vel_body_down', 0.0))    # Down velocity
            yawspeed = float(setpoint.get('yawspeed_deg_s', 0.0))   # Yaw speed in deg/s

            # Convert yaw speed from degrees/s to radians/s for MAVSDK
            yawspeed_rad = math.radians(yawspeed)

            logger.debug(f"Sending VELOCITY_BODY_OFFBOARD: Fwd={vel_fwd:.3f}, Right={vel_right:.3f}, Down={vel_down:.3f}, YawSpeed={yawspeed:.1f}°/s")
            
            # Send the velocity commands to the drone using MAVSDK VelocityBodyYawspeed
            # Note: VelocityBodyYawspeed expects (forward, right, down, yawspeed_rad)
            next_setpoint = VelocityBodyYawspeed(vel_fwd, vel_right, vel_down, yawspeed_rad)
            await self._safe_mavsdk_call(
                self.drone.offboard.set_velocity_body(next_setpoint)
            )

        except OffboardError as e:
            logger.error(f"MAVSDK offboard velocity_body_offboard command failed: {e}")
        except ValueError as e:
            logger.error(f"Invalid setpoint values for velocity_body_offboard command: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in send_velocity_body_offboard_commands: {e}")


    def convert_to_ned(self, vel_x, vel_y, yaw):
        """
        Converts local frame velocities to NED frame using the current yaw.
        """
        ned_vel_x = vel_x * math.cos(yaw) - vel_y * math.sin(yaw)
        ned_vel_y = vel_x * math.sin(yaw) + vel_y * math.cos(yaw)
        return ned_vel_x, ned_vel_y

    async def start_offboard_mode(self):
        """
        Attempts to start offboard mode on the drone using MAVSDK.
        """
        result = {"steps": [], "errors": []}
        try:
            await self.drone.offboard.start()
            result["steps"].append("Offboard mode started.")
            logger.info("Offboard mode started.")
        except Exception as e:
            result["errors"].append(f"Failed to start offboard mode: {e}")
            logger.error(f"Failed to start offboard mode: {e}")
        return result

    async def stop_offboard_mode(self):
        """
        Stops offboard mode on the drone using MAVSDK.
        """
        logger.info("Stopping offboard mode...")
        await self.drone.offboard.stop()

    async def stop(self):
        """
        Stops all operations and disconnects from the drone.
        """
        if self.update_task:
            self.update_task.cancel()
            await self.update_task
        await self.stop_offboard_mode()
        self.active_mode = False
        logger.info("Disconnected from the drone.")

    async def send_initial_setpoint(self):
        """
        Sends an initial setpoint to the drone based on the current profile's control type.
        If the control type is 'velocity_body', send zero velocities.
        If the control type is 'attitude_rate', send zero rates and thrust.
        """
        try:
            control_type = self.app_controller.follower.get_control_type()

            if control_type == 'velocity_body':
                
                logger.debug("Sending initial velocity_body setpoint (all zeros).")
                await self.send_body_velocity_commands()

            elif control_type == 'attitude_rate':
                
                logger.debug("Sending initial attitude_rate setpoint (all zeros).")
                await self.send_attitude_rate_commands()

            else:
                logger.error(f"Unknown control type: {control_type}")
                return

        except Exception as e:
            logger.error(f"Error sending initial setpoint: {e}")


    def update_setpoint(self):
        """
        Updates the current setpoint for the drone.
        """
        self.last_command = self.setpoint_handler

    def get_flight_mode_text(self, mode_code):
        """
        Convert the flight mode code to a text label.
        """
        return self.FLIGHT_MODES.get(mode_code, f"Unknown ({mode_code})")
    
    async def trigger_return_to_launch(self):
        """
        Send Return to Launch as a failsafe action
        """
        await self.drone.action.return_to_launch()
        logger.info("Initiating RTL.")

    async def set_hover_throttle(self):
        hover_throttle_raw =await self.mavlink_data_manager.fetch_throttle_percent()
        self.hover_throttle = float(hover_throttle_raw) / 100.0
        
        
    async def trigger_failsafe(self):
        logging.critical("Initiating Return to Launch due to altitude safety violation")
        await self.trigger_return_to_launch()
        
    async def send_commands_unified(self):
        """
        Unified command dispatcher that automatically selects the appropriate 
        MAVSDK method based on the current follower's control type from schema.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized")
                return False
                
            # Get control type from schema
            control_type = self.setpoint_handler.get_control_type()
            
            # Dispatch to appropriate method
            if control_type == 'velocity_body':
                await self.send_body_velocity_commands()
            elif control_type == 'attitude_rate':
                await self.send_attitude_rate_commands()
            elif control_type == 'velocity_body_offboard':
                await self.send_velocity_body_offboard_commands()
            else:
                logger.error(f"Unknown control type from schema: {control_type}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error in unified command dispatch: {e}")
            return False

    async def send_body_velocity_commands(self):
        """
        Enhanced schema-aware body velocity command sender.
        Only sends velocity commands if the current profile supports them.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized")
                return
                
            # Verify this is the correct control type
            if self.setpoint_handler.get_control_type() != 'velocity_body':
                logger.warning(f"Attempting to send velocity commands but control type is: {self.setpoint_handler.get_control_type()}")
                
            setpoint = self.setpoint_handler.get_fields()
            if not setpoint:
                logger.error("No setpoint data available")
                return

            # Extract velocity fields with safe defaults
            vx = float(setpoint.get('vel_x', 0.0))
            vy = float(setpoint.get('vel_y', 0.0))
            vz = float(setpoint.get('vel_z', 0.0))
            yaw_rate = float(setpoint.get('yaw_rate', 0.0))

            logger.debug(f"Sending VELOCITY_BODY: Vx={vx:.3f}, Vy={vy:.3f}, Vz={vz:.3f}, Yaw_rate={yaw_rate:.3f}")
            
            # Send the velocity commands to the drone
            from mavsdk.offboard import VelocityBodyYawspeed, OffboardError
            next_setpoint = VelocityBodyYawspeed(vx, vy, vz, yaw_rate)
            await self._safe_mavsdk_call(
                self.drone.offboard.set_velocity_body(next_setpoint)
            )

        except OffboardError as e:
            logger.error(f"MAVSDK offboard velocity command failed: {e}")
        except ValueError as e:
            logger.error(f"Invalid setpoint values for velocity command: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in send_body_velocity_commands: {e}")

    async def send_attitude_rate_commands(self):
        """
        Enhanced schema-aware attitude rate command sender.
        Only sends attitude rate commands if the current profile supports them.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized")
                return
                
            # Verify this is the correct control type
            if self.setpoint_handler.get_control_type() != 'attitude_rate':
                logger.warning(f"Attempting to send attitude rate commands but control type is: {self.setpoint_handler.get_control_type()}")
                
            setpoint = self.setpoint_handler.get_fields()
            if not setpoint:
                logger.error("No setpoint data available")
                return

            # Extract attitude rate fields with safe defaults
            roll_rate = float(setpoint.get('roll_rate', 0.0))
            pitch_rate = float(setpoint.get('pitch_rate', 0.0))
            yaw_rate = float(setpoint.get('yaw_rate', 0.0))
            thrust = float(setpoint.get('thrust', getattr(self, 'hover_throttle', 0.5)))

            logger.debug(f"Sending ATTITUDE_RATE: Roll={roll_rate:.3f}, Pitch={pitch_rate:.3f}, Yaw={yaw_rate:.3f}, Thrust={thrust:.3f}")
            
            # Send the attitude rate commands to the drone
            from mavsdk.offboard import AttitudeRate, OffboardError
            next_setpoint = AttitudeRate(roll_rate, pitch_rate, yaw_rate, thrust)
            await self.drone.offboard.set_attitude_rate(next_setpoint)

        except OffboardError as e:
            logger.error(f"MAVSDK offboard attitude rate command failed: {e}")
        except ValueError as e:
            logger.error(f"Invalid setpoint values for attitude rate command: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in send_attitude_rate_commands: {e}")

    async def send_initial_setpoint(self):
        """
        Enhanced schema-aware initial setpoint sender.
        Automatically determines the correct command type from the schema.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized, cannot send initial setpoint")
                return
                
            # Get control type directly from setpoint handler schema
            control_type = self.setpoint_handler.get_control_type()
            
            logger.info(f"Sending initial {control_type} setpoint (all zeros)")
            
            # Reset all fields to defaults before sending
            self.setpoint_handler.reset_setpoints()
            
            # Send appropriate command type
            if control_type == 'velocity_body':
                await self.send_body_velocity_commands()
            elif control_type == 'attitude_rate':
                await self.send_attitude_rate_commands()
            elif control_type == 'velocity_body_offboard':
                await self.send_velocity_body_offboard_commands()
            else:
                logger.error(f"Unknown control type from schema: {control_type}")
                return
                
            logger.debug(f"Initial {control_type} setpoint sent successfully")

        except Exception as e:
            logger.error(f"Error sending initial setpoint: {e}")

    def validate_setpoint_compatibility(self) -> bool:
        """
        Validates that the current setpoint configuration is compatible 
        with the expected control type.
        
        Returns:
            bool: True if compatible, False otherwise.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized")
                return False
                
            # Validate profile consistency
            if hasattr(self.setpoint_handler, 'validate_profile_consistency'):
                if not self.setpoint_handler.validate_profile_consistency():
                    logger.error("Setpoint profile consistency validation failed")
                    return False
            
            # Check that we have the required fields for the control type
            control_type = self.setpoint_handler.get_control_type()
            available_fields = set(self.setpoint_handler.get_fields().keys())
            
            if control_type == 'velocity_body':
                # At minimum we need vel_z for any velocity control
                if not any(field in available_fields for field in ['vel_x', 'vel_y', 'vel_z']):
                    logger.error("Velocity control type but no velocity fields available")
                    return False
                    
            elif control_type == 'attitude_rate':
                # At minimum we need thrust for attitude rate control
                if 'thrust' not in available_fields:
                    logger.error("Attitude rate control type but no thrust field available")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Error validating setpoint compatibility: {e}")
            return False

    def get_command_summary(self) -> dict:
        """
        Returns a summary of the current command configuration for debugging.
        
        Returns:
            dict: Summary of command state and configuration.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                return {'error': 'Setpoint handler not initialized'}
                
            summary = {
                'control_type': self.setpoint_handler.get_control_type(),
                'profile_name': self.setpoint_handler.get_display_name(),
                'available_fields': list(self.setpoint_handler.get_fields().keys()),
                'current_values': self.setpoint_handler.get_fields(),
                'validation_status': self.validate_setpoint_compatibility(),
                'schema_version': getattr(self.setpoint_handler, '_schema_cache', {}).get('schema_version', 'unknown')
            }
            
            return summary
            
        except Exception as e:
            return {'error': f'Failed to generate command summary: {e}'}

    # Method to replace update_setpoint for better schema integration
    def update_setpoint_enhanced(self):
        """
        Enhanced setpoint update that validates compatibility and logs status.
        """
        try:
            if not hasattr(self, 'setpoint_handler'):
                logger.error("Setpoint handler not available for update")
                return
                
            # Validate before updating
            if not self.validate_setpoint_compatibility():
                logger.warning("Setpoint compatibility validation failed during update")
                
            # Update the last command reference
            self.last_command = self.setpoint_handler
            
            # Optional: Log current state for debugging
            if hasattr(self, 'debug_mode') and self.debug_mode:
                summary = self.get_command_summary()
                logger.debug(f"Setpoint updated: {summary}")
                
        except Exception as e:
            logger.error(f"Error updating setpoint: {e}")