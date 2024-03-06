# px4_controller.py
import asyncio
import math
from mavsdk import System
from classes.parameters import Parameters  # Adjust the import path as necessary
from mavsdk.offboard import (OffboardError, VelocityNedYaw)

class PX4Controller:
    def __init__(self):
        self.drone = System()
        self.current_yaw = 0.0  # Current yaw in radians
        self.current_altitude = 0.0  # Current altitude in meters
        self.camera_yaw_offset = Parameters.CAMERA_YAW_OFFSET  # Pre-installation yaw offset of the camera
        self.update_task = None  # Background task reference

    async def connect(self):
        """Connects to the drone using the system address from Parameters."""
        await self.drone.connect(system_address=Parameters.SYSTEM_ADDRESS)
        print("Connected to the drone.")
        # Start background tasks for telemetry updates
        self.update_task = asyncio.create_task(self.update_drone_data())

    async def update_drone_data(self):
        """Background task to continuously update current yaw and altitude."""
        try:
            async for position in self.drone.telemetry.position():
                self.current_altitude = position.relative_altitude_m
            async for attitude in self.drone.telemetry.attitude_euler():
                self.current_yaw = attitude.yaw + self.camera_yaw_offset
        except asyncio.CancelledError:
            print("Update task was cancelled, stopping cleanly.")
        except Exception as e:
            print(f"Error in update_yaw_and_altitude: {e}")

    async def send_velocity_commands(self, vel_x, vel_y, vel_z):
        """
        Converts local frame velocity commands to NED frame based on current yaw,
        and sends them to the drone in offboard mode.
        
        :param vel_x: Velocity along the X axis in the local frame.
        :param vel_y: Velocity along the Y axis in the local frame.
        :param vel_z: Velocity along the Z axis in the local frame.
        """
        # Convert local frame velocities (vel_x, vel_y) to NED frame
        ned_vel_x, ned_vel_y = self.convert_to_ned(vel_x, vel_y, self.current_yaw)
        
        next_setpoint = VelocityNedYaw(ned_vel_x,ned_vel_y,vel_z,self.current_yaw)
        #await self.drone.offboard.set_velocity_ned(next_setpoint)

    def convert_to_ned(self, vel_x, vel_y, yaw):
        """
        Converts local frame velocities to NED frame using the current yaw.
        
        :param vel_x: Velocity along the X axis in the local frame.
        :param vel_y: Velocity along the Y axis in the local frame.
        :param yaw: Current yaw of the drone in radians.
        :return: Tuple of (ned_vel_x, ned_vel_y) velocities in the NED frame.
        """
        ned_vel_x = vel_x * math.cos(yaw) - vel_y * math.sin(yaw)
        ned_vel_y = vel_x * math.sin(yaw) + vel_y * math.cos(yaw)
        return ned_vel_x, ned_vel_y
    
    async def start_offboard_mode(self):
        """Starts offboard mode to enable sending velocity commands."""
        print("Starting offboard mode...")
        try:
            await self.drone.offboard.start()
            print("Offboard mode started.")
        except Exception as e:
            print(f"Failed to start offboard mode: {e}")
            
    async def stop_offboard_mode(self):
        """Stops offboard mode and disarms the drone."""
        print("Stopping offboard mode...")
        try:
            await self.drone.offboard.stop()
            print("Offboard mode stopped.")
        except Exception as e:
            print(f"Failed to stop offboard mode")

    async def stop(self):
        """Stops all operations and disconnects from the drone."""
        if self.update_task is not None:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                print("Background task was cancelled.")
        await self.stop_offboard_mode()
        print("Disconnected from the drone.")