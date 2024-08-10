# src/classes/px4_interface_manager.py
import asyncio
import math
import logging
from mavsdk import System
from classes.parameters import Parameters
from mavsdk.offboard import OffboardError, VelocityNedYaw, VelocityBodyYawspeed

# Configure logging
logger = logging.getLogger(__name__)

class PX4InterfaceManager:
    def __init__(self):
        """
        Initializes the PX4InterfaceManager and sets up the connection to the PX4 drone.
        """
        if Parameters.EXTERNAL_MAVSDK_SERVER:
            self.drone = System(mavsdk_server_address='localhost', port=50051)
        else:
            self.drone = System()
        
        self.current_yaw = 0.0  # Current yaw in radians
        self.current_pitch = 0.0  # Current pitch in radians
        self.current_roll = 0.0  # Current roll in radians
        self.current_altitude = 0.0  # Current altitude in meters
        self.camera_yaw_offset = Parameters.CAMERA_YAW_OFFSET
        self.update_task = None  # Task for telemetry updates
        self.last_command = (0, 0, 0)  # Default to hover (0 velocity)
        self.active_mode = False

    async def connect(self):
        """
        Connects to the drone and starts telemetry updates.
        """
        await self.drone.connect(system_address=Parameters.SYSTEM_ADDRESS)
        self.active_mode = True
        logger.info("Connected to the drone.")
        self.update_task = asyncio.create_task(self.update_drone_data())

    async def update_drone_data(self):
        """
        Continuously updates the drone's telemetry data.
        """
        while self.active_mode:
            try:
                async for position in self.drone.telemetry.position():
                    self.current_altitude = position.relative_altitude_m
                async for attitude in self.drone.telemetry.attitude_euler():
                    self.current_yaw = attitude.yaw + self.camera_yaw_offset
                    self.current_pitch = attitude.pitch
                    self.current_roll = attitude.roll
            except asyncio.CancelledError:
                logger.warning("Telemetry update task was cancelled.")
                break
            except Exception as e:
                logger.error(f"Error updating telemetry: {e}")
                await asyncio.sleep(1)  # Wait before retrying

    def get_orientation(self):
        """
        Returns the current orientation (yaw, pitch, roll) of the drone.
        """
        return self.current_yaw, self.current_pitch, self.current_roll

    async def send_ned_velocity_commands(self, setpoint):
        """
        Sends NED (North-East-Down) velocity commands to the drone in offboard mode.
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
        Attempts to start offboard mode on the drone.
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
        Stops offboard mode on the drone.
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
