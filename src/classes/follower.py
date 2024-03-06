# follower.py
import asyncio
from simple_pid import PID
from classes.parameters import Parameters  # Adjust the import path as necessary
from classes.px4_controller import PX4Controller  # Ensure this import path is correct

class Follower:
    def __init__(self, px4_controller):
        self.px4_controller = px4_controller
        # Initialize PID controllers with gains from Parameters
        self.pid_x = PID(Parameters.PID_GAINS["x"]["p"], Parameters.PID_GAINS["x"]["i"], Parameters.PID_GAINS["x"]["d"], setpoint=0)
        self.pid_y = PID(Parameters.PID_GAINS["y"]["p"], Parameters.PID_GAINS["y"]["i"], Parameters.PID_GAINS["y"]["d"], setpoint=0)
        self.pid_z = PID(Parameters.PID_GAINS["z"]["p"], Parameters.PID_GAINS["z"]["i"], Parameters.PID_GAINS["z"]["d"], setpoint=Parameters.MIN_DESCENT_HEIGHT)
        self.vel_x = 0.0
        self.vel_y = 0.0
        self.vel_z = 0.0
        

    def calculate_velocity_commands(self, target_coords):
        """
        Calculates velocity commands based on the target's position.
        
        :param target_coords: A tuple (x, y) representing the target's normalized position in the camera frame.
        :return: A tuple (vel_x, vel_y) with the calculated velocity commands.
        """
        error_x, error_y = target_coords
        vel_x = self.pid_x(error_x)
        vel_y = self.pid_y(error_y)
        vel_z = self.control_descent()
        self.vel_x = vel_x
        self.vel_y = vel_y
        self.vel_z = vel_z
        return (vel_x, vel_y, vel_z)

    def control_descent(self):
        """
        Controls the drone's descent rate, ensuring it doesn't descend below the minimum safe altitude.
        
        :return: The calculated vertical speed (vel_z).
        """
        if self.px4_controller.current_altitude > Parameters.MIN_DESCENT_HEIGHT:
            vel_z = self.pid_z(PX4Controller.current_altitude)
            vel_z = max(vel_z, Parameters.RATE_OF_DESCENT)
        else:
            vel_z = 0
        return vel_z

    async def follow_target(self, target_coords):
        """
        Main loop to follow the target using calculated velocity commands.
        
        :param target_coords: The target's normalized position in the camera frame.
        """
        vel_x, vel_y = self.calculate_velocity_commands(target_coords)
        vel_z = self.control_descent()
        
        # Use the PX4Controller to send velocity commands
        await self.px4_controller.send_velocity_commands(vel_x, vel_y, vel_z)
