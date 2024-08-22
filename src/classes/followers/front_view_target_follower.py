#src\classes\followers\front_view_target_follower.py
from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
import logging
from datetime import datetime
import math
from typing import Tuple
import asyncio
class FrontViewTargetFollower(BaseFollower):
    """
    FrontViewTargetFollower class manages PID control to keep a target in the front view of the drone.
    It utilizes advanced PID features and allows different control strategies, including yaw control and vertical error recalculation.
    """
    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the FrontViewTargetFollower with the given PX4 controller and initial target coordinates.

        Args:
            px4_controller (PX4Controller): Instance of PX4Controller to control the drone.
            initial_target_coords (tuple): Initial target coordinates to set for the follower.
        """
        super().__init__(px4_controller, "Front View")  # Initialize with "Front View" profile
        self.control_strategy = Parameters.CONTROL_STRATEGY
        self.target_position_mode = Parameters.TARGET_POSITION_MODE
        self.yaw_enabled = Parameters.ENABLE_YAW_CONTROL  # Initialize yaw_enabled from parameters
        self.initial_target_coords = initial_target_coords if self.target_position_mode == 'initial' else Parameters.DESIRE_AIM
        self.initialize_pids()

    def initialize_pids(self):
        """Initializes the PID controllers based on the control strategy and initial target coordinates."""
        
        if self.control_strategy == 'constant_distance':
            setpoint_x, setpoint_y = self.initial_target_coords
            self.pid_z = CustomPID(
                *self.get_pid_gains('z'), 
                setpoint=setpoint_y, 
                output_limits=(-Parameters.VELOCITY_LIMITS['z'], Parameters.VELOCITY_LIMITS['z'])
            )
            self.pid_y = CustomPID(
                *self.get_pid_gains('y'), 
                setpoint=setpoint_x, 
                output_limits=(-Parameters.VELOCITY_LIMITS['y'], Parameters.VELOCITY_LIMITS['y'])
            )   

        if self.yaw_enabled: #TODO
            self.pid_yaw = CustomPID(
                *self.get_pid_gains('yaw'),
                setpoint=setpoint_x,  # Yaw setpoint is related to horizontal positioning
                output_limits=(-Parameters.MAX_YAW_RATE, Parameters.MAX_YAW_RATE)
            )

    def get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """Retrieves the PID gains based on the current altitude from the PX4Controller, applying gain scheduling if enabled."""
        if Parameters.ENABLE_GAIN_SCHEDULING:
            current_value = getattr(self.px4_controller, Parameters.GAIN_SCHEDULING_PARAMETER, None)
            if current_value is None:
                logging.error(f"Parameter {Parameters.GAIN_SCHEDULING_PARAMETER} not available in PX4Controller.")
                return Parameters.PID_GAINS[axis]['p'], Parameters.PID_GAINS[axis]['i'], Parameters.PID_GAINS[axis]['d']
            
            for (lower_bound, upper_bound), gains in Parameters.ALTITUDE_GAIN_SCHEDULE.items():
                if lower_bound <= current_value < upper_bound:
                    return gains[axis]['p'], gains[axis]['i'], gains[axis]['d']
        
        return Parameters.PID_GAINS[axis]['p'], Parameters.PID_GAINS[axis]['i'], Parameters.PID_GAINS[axis]['d']

    def update_pid_gains(self):
        """Updates the PID gains based on current settings and altitude."""
        if self.control_strategy == 'constant_distance':
            self.pid_y.tunings = self.get_pid_gains('y')
            self.pid_z.tunings = self.get_pid_gains('z')
            if self.yaw_enabled:
                self.pid_yaw.tunings = self.get_pid_gains('yaw')


    def calculate_velocity_commands(self, target_coords: Tuple[float, float]) -> None:
        """Calculates and updates velocity commands based on the target coordinates."""
        self.update_pid_gains()

        # Calculate errors
        
        if self.control_strategy == 'constant_distance':
            error_x = self.pid_y.setpoint - target_coords[0]
            error_y = self.pid_z.setpoint - target_coords[1] #frame up is negative
            vel_x , vel_y , vel_z = self.calculate_velocity_constant_distance(error_x= error_x, error_y=error_y)

        # Handle Yaw Control if enabled
        yaw_velocity = 0
        if self.yaw_enabled and abs(error_x) > Parameters.YAW_CONTROL_THRESHOLD:
            yaw_velocity = self.pid_yaw(error_x)

        # Update setpoint handler with calculated velocities and yaw
        self.setpoint_handler.set_field('vel_x', vel_x)
        self.setpoint_handler.set_field('vel_y', vel_y)
        self.setpoint_handler.set_field('vel_z', vel_z)
        self.setpoint_handler.set_field('yaw_rate', yaw_velocity)

    async def follow_target(self, target_coords: Tuple[float, float]):
        """Calculates and sends velocity and yaw rate commands to follow a target based on its coordinates."""
        self.calculate_velocity_commands(target_coords)
        await self.px4_controller.send_body_velocity_commands(self.setpoint_handler.get_fields())
        return self.setpoint_handler.get_fields()

        
    def smooth_pitch_correction(self, error_y: float) -> float:
        """Smoothly adjusts pitch after yaw to correct vertical positioning."""
        return self.pid_x(error_y) * Parameters.YAW_PITCH_SYNC_FACTOR

    def calculate_velocity_constant_distance(self, error_x: float, error_y: float) -> Tuple[float, float, float]:
        """Calculate velocity commands for constant distance strategy."""
        vel_x = 0  # Set to zero for now, later can be controlled separately
        vel_y = self.pid_y(error_x)  # error_x controls vel_y due to coordinate system differences
        vel_z = self.control_descent_constant_distance(error_y)  # error_y controls vel_z due to coordinate system differences
        
        return vel_x, vel_y, vel_z


    def control_descent_constant_distance(self, error_y: float) -> float:
        """
        Controls the descent of the drone based on the error in the y-axis, considering altitude limits.

        Args:
            error_y (float): Error in the y-axis (e.g., lateral position error).

        Returns:
            float: Desired z velocity setpoint.

        Notes:  
            - Calculate the PID-controlled command using self.pid_z(error_y).
            - If the command is positive (descend), check if the drone is below the minimum descent height.
                - If above, allow descent.
                - If at or below the minimum descent height, log a message and return zero.
            - If the command is negative (climb), check if the drone is already at the maximum altitude.
                - If not, allow climbing.
                - If at maximum altitude, log a message and return zero.
        """
        current_altitude = self.px4_controller.current_altitude
        logging.debug(f"Current Altitude: {current_altitude}m, Minimum Descent Height: {Parameters.MIN_DESCENT_HEIGHT}m, Maximum Climb Height: {Parameters.MAX_CLIMB_HEIGHT}")

        # Calculate the PID-controlled command
        command = self.pid_z(error_y)

        if command > 0:  # Descend command
            if current_altitude >= Parameters.MIN_DESCENT_HEIGHT:
                return command
            else:
                logging.info("Altitude is at or above the minimum descent height. Descent halted.")
                return 0
        else:  # Climb command
            if current_altitude < Parameters.MAX_CLIMB_HEIGHT:
                return command
            else:
                logging.info("Already at maximum altitude. No further climb allowed.")
                return 0



