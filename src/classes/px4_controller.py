import asyncio
import math
from mavsdk import System
from classes.parameters import Parameters
from mavsdk.offboard import OffboardError, VelocityNedYaw

class PX4Controller:
    def __init__(self):
        self.drone = System()
        self.current_yaw = 0.0  # Current yaw in radians
        self.current_altitude = 0.0  # Current altitude in meters
        self.camera_yaw_offset = Parameters.CAMERA_YAW_OFFSET
        self.update_task = None  # Task for telemetry updates
        self.last_command = (0, 0, 0)  # Default to hover (0 velocity)

    async def connect(self):
        """Connects to the drone using the system address from Parameters."""
        await self.drone.connect(system_address=Parameters.SYSTEM_ADDRESS)
        print("Connected to the drone.")
        self.update_task = asyncio.create_task(self.update_drone_data())

    async def update_drone_data(self):
        """Continuously updates current yaw and altitude."""
        while True:
            try:
                async for position in self.drone.telemetry.position():
                    self.current_altitude = position.relative_altitude_m
                async for attitude in self.drone.telemetry.attitude_euler():
                    self.current_yaw = attitude.yaw + self.camera_yaw_offset
            except asyncio.CancelledError:
                print("Telemetry update task was cancelled.")
                break
            except Exception as e:
                print(f"Error updating telemetry: {e}")
                await asyncio.sleep(1)  # Wait before retrying

    async def send_velocity_commands(self, setpoint):
        """Sends velocity commands to the drone in offboard mode."""
        vel_x, vel_y, vel_z = setpoint
        ned_vel_x, ned_vel_y = self.convert_to_ned(vel_x, vel_y, self.current_yaw)
        
        if Parameters.ENABLE_SETPOINT_DEBUGGING:
            print(f"sending NED velocity commands: Vx={ned_vel_x}, Vy={ned_vel_y}, Vz={vel_z}, Yaw={self.current_yaw}")
        
        try:
            next_setpoint = VelocityNedYaw(ned_vel_x, ned_vel_y, vel_z, self.current_yaw)
            await self.drone.offboard.set_velocity_ned(next_setpoint)
        except OffboardError as e:
            print(f"Failed to send offboard command: {e}")

    def convert_to_ned(self, vel_x, vel_y, yaw):
        """Converts local frame velocities to NED frame using the current yaw."""
        ned_vel_x = vel_x * math.cos(yaw) - vel_y * math.sin(yaw)
        ned_vel_y = vel_x * math.sin(yaw) + vel_y * math.cos(yaw)
        return ned_vel_x, ned_vel_y

    async def start_offboard_mode(self):
        """Attempts to start offboard mode."""
        print("Starting offboard mode...")
        try:
            await self.drone.offboard.start()
            print("Offboard mode started.")
        except Exception as e:
            print(f"Failed to start offboard mode: {e}")

    async def stop_offboard_mode(self):
        """Stops offboard mode."""
        print("Stopping offboard mode...")
        await self.drone.offboard.stop()

    async def stop(self):
        """Stops all operations and disconnects from the drone."""
        if self.update_task:
            self.update_task.cancel()
            await self.update_task
        await self.stop_offboard_mode()
        print("Disconnected from the drone.")

    async def send_initial_setpoint(self):
        """Sends an initial setpoint to enable offboard mode start."""
        await self.send_velocity_commands((0, 0, 0))

    def update_setpoint(self, setpoint):
        """Updates the current setpoint."""
        self.last_command = setpoint
