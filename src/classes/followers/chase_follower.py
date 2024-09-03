# src/classes/followers/chase_follower.py
from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
import logging
from typing import Tuple

class ChaseFollower(BaseFollower):
    """
    ChaseFollower manages PID control to maintain a dynamic chase of the target.
    It controls the roll, pitch, yaw rates, and thrust based on the target's position.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the ChaseFollower with the given PX4 controller and initial target coordinates.

        Args:
            px4_controller (PX4Controller): Instance of PX4Controller to control the drone.
            initial_target_coords (tuple): Initial target coordinates to set for the follower.
        """
        super().__init__(px4_controller, "Chase Follower")  # Initialize with "Chase Follower" profile
        self.initial_target_coords = initial_target_coords
        self.initialize_pids()

    def initialize_pids(self):
        """
        Initializes the PID controllers for roll, pitch, yaw rates, and thrust.
        """
        setpoint_x, setpoint_y = self.initial_target_coords

        # Initialize pitch, roll, yaw rate, and thrust PID controllers
        self.pid_pitch_rate = CustomPID(
            *self.get_pid_gains('pitch_rate'),
            setpoint=setpoint_y,  # Vertical control
            output_limits=(-Parameters.MAX_PITCH_RATE, Parameters.MAX_PITCH_RATE)
        )
        self.pid_yaw_rate = CustomPID(
            *self.get_pid_gains('yaw_rate'),
            setpoint=setpoint_x,  # Horizontal control
            output_limits=(-Parameters.MAX_YAW_RATE, Parameters.MAX_YAW_RATE)
        )
        self.pid_roll_rate = CustomPID(
            *self.get_pid_gains('roll_rate'),
            setpoint=0,  # Roll for coordination based on yaw
            output_limits=(-Parameters.MAX_ROLL_RATE, Parameters.MAX_ROLL_RATE)
        )
        self.pid_thrust = CustomPID(
            *self.get_pid_gains('thrust'),
            setpoint=Parameters.TARGET_SPEED,  # Target airspeed control
            output_limits=(0, Parameters.MAX_THRUST)
        )

        logging.info("PID controllers initialized for ChaseFollower.")

    def get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves the PID gains for the specified axis.

        Args:
            axis (str): The axis for which to retrieve the PID gains ('roll_rate', 'pitch_rate', 'yaw_rate', 'thrust').

        Returns:
            Tuple[float, float, float]: The proportional, integral, and derivative gains for the axis.
        """
        # Return the PID gains from the parameters
        return Parameters.PID_GAINS[axis]['p'], Parameters.PID_GAINS[axis]['i'], Parameters.PID_GAINS[axis]['d']

    def update_pid_gains(self):
        """
        Updates the PID gains for pitch, roll, yaw rates, and thrust controllers based on the current settings.
        """
        self.pid_pitch_rate.tunings = self.get_pid_gains('pitch_rate')
        self.pid_yaw_rate.tunings = self.get_pid_gains('yaw_rate')
        self.pid_roll_rate.tunings = self.get_pid_gains('roll_rate')
        self.pid_thrust.tunings = self.get_pid_gains('thrust')

        logging.debug("PID gains updated for ChaseFollower.")

    def calculate_control_commands(self, target_coords: Tuple[float, float]) -> None:
        """
        Calculates and updates control commands based on the target coordinates and tracking quality.

        Args:
            target_coords (Tuple[float, float]): The target coordinates from image processing.
        """
        # Update PID gains
        self.update_pid_gains()

        # Calculate errors for pitch (vertical) and yaw (horizontal)
        error_x = self.pid_pitch_rate.setpoint - target_coords[0] * (-1)
        error_y = (self.pid_yaw_rate.setpoint - target_coords[1]) * (-1)

        # Calculate control rates using the PID controllers
        pitch_rate = self.pid_pitch_rate(error_x)
        yaw_rate = self.pid_yaw_rate(error_y)

        # Roll rate for coordinated flight, proportional to yaw rate
        roll_rate = self.pid_roll_rate(-1 * yaw_rate)

        # Thrust control: Adjust thrust based on tracking quality and airspeed control
        thrust = self.control_thrust(self.px4_controller.current_ground_speed)

        # Update the setpoint handler
        self.px4_controller.setpoint_handler.set_field('roll_rate', roll_rate)
        self.px4_controller.setpoint_handler.set_field('pitch_rate', pitch_rate)
        self.px4_controller.setpoint_handler.set_field('yaw_rate', yaw_rate)
        self.px4_controller.setpoint_handler.set_field('thrust', thrust)

        # Log the calculated control commands
        logging.debug(f"Calculated commands - Roll rate: {roll_rate}, Pitch rate: {pitch_rate}, "
                      f"Yaw rate: {yaw_rate}, Thrust: {thrust}")

    def follow_target(self, target_coords: Tuple[float, float]):
        """
        Sends control commands to follow the target based on the coordinates.

        Args:
            target_coords (Tuple[float, float]): The target coordinates to follow.
        """
        self.calculate_control_commands(target_coords)

    def control_thrust(self, ground_speed) -> float:
        """
        Controls the thrust based on the current ground speed.

        Args:
            ground_speed (float): The current ground speed of the drone.

        Returns:
            float: The calculated thrust command.
        """
        # Normalize ground speed
        min_speed = Parameters.MIN_GROUND_SPEED
        max_speed = Parameters.MAX_GROUND_SPEED
        normalized_speed = (ground_speed - min_speed) / (max_speed - min_speed)
        normalized_speed = max(0.0, min(1.0, normalized_speed))  # Ensure it's between 0 and 1

        # Use normalized speed as setpoint for thrust PID
        current_thrust = self.pid_thrust(normalized_speed)

        return current_thrust
