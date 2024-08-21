#src/classes/px4_interface_manager.py
import asyncio
import math
import logging
from mavsdk import System
from classes.parameters import Parameters
from mavsdk.offboard import OffboardError, VelocityNedYaw, VelocityBodyYawspeed
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
        self.camera_yaw_offset = Parameters.CAMERA_YAW_OFFSET
        self.update_task = None  # Task for telemetry updates
        self.setpoint_handler = SetpointHandler(Parameters.FOLLOWER_MODE.capitalize().replace("_", " "))  # Use the mode from Parameters
        self.active_mode = False

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

        except Exception as e:
            logger.error(f"Error updating telemetry via MAVLink2Rest: {e}")


    async def _update_telemetry_via_mavsdk(self):
        """
        Updates telemetry data using MAVSDK.
        Continuously retrieves position and attitude data from the MAVSDK API.
        """
        try:
            async for position in self.drone.telemetry.position():
                self.current_altitude = position.relative_altitude_m
            async for attitude in self.drone.telemetry.attitude_euler():
                self.current_yaw = attitude.yaw + self.camera_yaw_offset
                self.current_pitch = attitude.pitch
                self.current_roll = attitude.roll
        except Exception as e:
            logger.error(f"Error updating telemetry via MAVSDK: {e}")

    def get_orientation(self):
        """
        Returns the current orientation (yaw, pitch, roll) of the drone.
        """
        return self.current_yaw, self.current_pitch, self.current_roll

    async def send_ned_velocity_commands(self, setpoint):
        """
        Sends NED (North-East-Down) velocity commands to the drone in offboard mode.
        This operation uses MAVSDK.
        """
        vel_x, vel_y, vel_z = setpoint
        ned_vel_x, ned_vel_y = self.convert_to_ned(vel_x, vel_y, self.current_yaw)
        
        if Parameters.ENABLE_SETPOINT_DEBUGGING:
            logger.debug(f"sending NED velocity commands: Vx={ned_vel_x}, Vy={ned_vel_y}, Vz={vel_z}, Yaw={self.current_yaw}")
        
        try:
            next_setpoint = VelocityNedYaw(ned_vel_x, ned_vel_y, vel_z, self.current_yaw)
            await self.drone.offboard.set_velocity_ned(next_setpoint)
        except OffboardError as e:
            logger.error(f"Failed to send offboard command: {e}")

    async def send_body_velocity_commands(self, setpoint):
        """
        Sends body frame velocity commands to the drone in offboard mode.
        This operation uses MAVSDK.
        """
        vx, vy, vz = setpoint
        yaw_rate = 0  # No yaw change for now
        
        try:
            logger.debug(f"Setting VELOCITY_BODY setpoint: Vx={vx}, Vy={vy}, Vz={vz}, Yaw rate={yaw_rate}")
            next_setpoint = VelocityBodyYawspeed(vx, vy, vz, yaw_rate)
            await self.drone.offboard.set_velocity_body(next_setpoint)
        except OffboardError as e:
            logger.error(f"Failed to send offboard velocity command: {e}")

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
        Sends an initial setpoint to the drone to enable offboard mode start.
        """
        await self.send_body_velocity_commands((0, 0, 0))

    def update_setpoint(self, setpoint):
        """
        Updates the current setpoint for the drone.
        """
        self.last_command = setpoint

    def get_flight_mode_text(self, mode_code):
        """
        Convert the flight mode code to a text label.
        """
        return self.FLIGHT_MODES.get(mode_code, f"Unknown ({mode_code})")
