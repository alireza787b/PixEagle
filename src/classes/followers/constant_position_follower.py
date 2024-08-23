#src/classes/followers/constant_position_follower.py
from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
import logging
from typing import Tuple

class ConstantPositionFollower(BaseFollower):
    """
    ConstantPositionFollower manages the drone to maintain a constant position relative to the target.
    Yaw control is always enabled in this mode, and altitude control is optional.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the ConstantPositionFollower with the given PX4 controller and initial target coordinates.

        Args:
            px4_controller (PX4Controller): Instance of PX4Controller to control the drone.
            initial_target_coords (tuple): Initial target coordinates to set for the follower.
        """
        super().__init__(px4_controller, "Constant Position")  # Initialize with "Constant Position" profile
        self.yaw_enabled = True  # Yaw control is always enabled in this mode
        self.altitude_control_enabled = Parameters.ENABLE_ALTITUDE_CONTROL
        self.initial_target_coords = initial_target_coords
        self.initialize_pids()

    def initialize_pids(self):
        """
        Initializes the PID controllers for maintaining a constant position relative to the target.
        """
        setpoint_x, setpoint_y = self.initial_target_coords

        # Initialize yaw PID controller
        self.pid_yaw_rate = CustomPID(
            *self.get_pid_gains('yaw_rate'),
            setpoint=setpoint_x, 
            output_limits=(-Parameters.MAX_YAW_RATE, Parameters.MAX_YAW_RATE)
        )

        # Initialize Z axis PID controller if altitude control is enabled
        if self.altitude_control_enabled:
            self.pid_z = CustomPID(
                *self.get_pid_gains('z'), 
                setpoint=setpoint_y, 
                output_limits=(-Parameters.VELOCITY_LIMITS['z'], Parameters.VELOCITY_LIMITS['z'])
            )

        logging.info("PID controllers initialized for ConstantPositionFollower.")

    def get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves the PID gains for the specified axis.

        Args:
            axis (str): The axis for which to retrieve the PID gains ('x', 'y', 'z', 'yaw_rate').

        Returns:
            Tuple[float, float, float]: The proportional, integral, and derivative gains for the axis.
        """
        # Return the PID gains from the parameters
        return Parameters.PID_GAINS[axis]['p'], Parameters.PID_GAINS[axis]['i'], Parameters.PID_GAINS[axis]['d']

    def update_pid_gains(self):
        """
        Updates the PID gains for Z and Yaw Rate controllers based on the current settings.
        """
        self.pid_yaw_rate.tunings = self.get_pid_gains('yaw_rate')
        if self.altitude_control_enabled:
            self.pid_z.tunings = self.get_pid_gains('z')

        logging.debug("PID gains updated for ConstantPositionFollower.")

    def calculate_velocity_commands(self, target_coords: Tuple[float, float]) -> None:
        """
        Calculates and updates velocity commands based on the target coordinates.

        Args:
            target_coords (Tuple[float, float]): The target coordinates from image processing.
        """
        # Update PID gains
        self.update_pid_gains()

        # Calculate yaw control
        error_x = self.pid_yaw_rate.setpoint - target_coords[0]
        yaw_velocity = self.pid_yaw_rate(error_x) if abs(error_x) > Parameters.YAW_CONTROL_THRESHOLD else 0

        # Calculate altitude control if enabled
        vel_z = 0
        if self.altitude_control_enabled:
            error_y = self.pid_z.setpoint - target_coords[1]
            vel_z = self.control_descent_constant_distance(error_y)

        # Update the setpoint handler
        self.setpoint_handler.set_field('vel_z', vel_z)
        self.setpoint_handler.set_field('yaw_rate', yaw_velocity)

        # Log the calculated velocity commands
        logging.debug(f"Calculated velocities - Vz: {vel_z}, Yaw rate: {yaw_velocity}")

    async def follow_target(self, target_coords: Tuple[float, float]):
        """
        Sends velocity commands to follow the target based on the coordinates.

        Args:
            target_coords (Tuple[float, float]): The target coordinates to follow.
        """
        self.calculate_velocity_commands(target_coords)
        await self.px4_controller.send_body_velocity_commands(self.setpoint_handler.get_fields())

    def control_descent_constant_distance(self, error_y: float) -> float:
        """
        Controls the descent or climb of the drone based on the error in the y-axis (vertical position error),
        considering altitude limits.

        Args:
            error_y (float): Error in the y-axis (vertical position error).

        Returns:
            float: The calculated Z-axis velocity (descent or climb command).
        """
        current_altitude = self.px4_controller.current_altitude
        logging.debug(f"Current Altitude: {current_altitude}m, "
                      f"Minimum Descent Height: {Parameters.MIN_DESCENT_HEIGHT}m, "
                      f"Maximum Climb Height: {Parameters.MAX_CLIMB_HEIGHT}m")

        # Calculate the PID-controlled vertical command (Z velocity)
        command = self.pid_z(error_y)

        # Handle descent command
        if command > 0:  # Descending
            if current_altitude >= Parameters.MIN_DESCENT_HEIGHT:
                return command
            else:
                logging.info("Altitude is at or above the minimum descent height. Descent halted.")
                return 0

        # Handle climb command
        else:  # Climbing
            if current_altitude < Parameters.MAX_CLIMB_HEIGHT:
                return command
            else:
                logging.info("Already at maximum altitude. No further climb allowed.")
                return 0
