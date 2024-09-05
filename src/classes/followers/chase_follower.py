# src/classes/followers/chase_follower.py
from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
import logging
from typing import Tuple
import numpy as np

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

        # Initialize pitch, yaw, roll rate, bank angle, and thrust PID controllers
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
            setpoint=0,  # This will be updated based on the bank angle
            output_limits=(-Parameters.MAX_ROLL_RATE, Parameters.MAX_ROLL_RATE)
        )
        self.pid_thrust = CustomPID(
            *self.get_pid_gains('thrust'),
            setpoint=self.normalize_speed(Parameters.TARGET_SPEED),  # Target airspeed control
            output_limits=(Parameters.MIN_THRUST, Parameters.MAX_THRUST)
        )

        logging.info("PID controllers initialized for ChaseFollower.")

    def get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves the PID gains for the specified axis.

        Args:
            axis (str): The axis for which to retrieve the PID gains ('roll_rate', 'pitch_rate', 'yaw_rate', 'bank_angle', 'thrust').

        Returns:
            Tuple[float, float, float]: The proportional, integral, and derivative gains for the axis.
        """
        # Return the PID gains from the parameters
        return Parameters.PID_GAINS[axis]['p'], Parameters.PID_GAINS[axis]['i'], Parameters.PID_GAINS[axis]['d']

    def update_pid_gains(self):
        """
        Updates the PID gains for pitch, roll, yaw rates, bank angle, and thrust controllers based on the current settings.
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
        error_y = (self.pid_pitch_rate.setpoint - target_coords[1]) * (-1)
        error_x = (self.pid_yaw_rate.setpoint - target_coords[0]) * (+1)

        # Calculate control rates using the PID controllers
        pitch_rate = self.pid_pitch_rate(error_y)
        yaw_rate = self.pid_yaw_rate(error_x)

        # Convert yaw rate from degrees/sec to radians/sec
        yaw_rate_rad = yaw_rate * (np.pi / 180)

        # Get current speed in meters per second
        current_speed = self.px4_controller.current_ground_speed
        current_roll = self.px4_controller.current_roll
        logging.debug(f"Current Roll: {current_roll:.2f}, Current Speed: {current_speed:.2f} ")
        # Calculate the desired bank angle from yaw rate and speed
        g = 9.81  # Acceleration due to gravity in m/s^2
        #current_speed = 5 ################################ TEST
        # Calculate the desired bank angle from yaw rate and speed
        target_bank_angle_rad = np.arctan((yaw_rate_rad * current_speed) / g)

        # Convert the bank angle from radians to degrees
        target_bank_angle = np.degrees(target_bank_angle_rad)


        # Calculate the error between desired and current bank angle
        bank_angle_error = (target_bank_angle - current_roll)

        # Use the bank angle error to calculate the required roll rate
        roll_rate = self.pid_roll_rate(bank_angle_error)

        
        # Thrust control: Adjust thrust based on tracking quality and airspeed control
        thrust = self.control_thrust(current_speed)

        # Update the setpoint handler
        self.px4_controller.setpoint_handler.set_field('roll_rate', roll_rate)
        self.px4_controller.setpoint_handler.set_field('pitch_rate', pitch_rate)
        self.px4_controller.setpoint_handler.set_field('yaw_rate', yaw_rate)
        self.px4_controller.setpoint_handler.set_field('thrust', thrust)

        # Log the calculated control commands for debugging
        logging.debug(f"Calculated commands - Roll rate: {roll_rate:.2f} degrees/sec to Bank angle: {target_bank_angle:.2f} degrees, "
                    f"Pitch rate: {pitch_rate:.2f} degrees/sec, "
                    f"Yaw rate: {yaw_rate:.2f} degrees/sec, "
                    f"Thrust: {thrust:.2f}")

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
        normalized_speed = self.normalize_speed(ground_speed)

        # Use normalized speed as setpoint for thrust PID
        current_thrust = self.pid_thrust(normalized_speed)

        return current_thrust
    
    
    def normalize_speed(self, speed, min_speed=Parameters.MIN_GROUND_SPEED, max_speed=Parameters.MAX_GROUND_SPEED):
        """
        Normalizes the given speed value between 0 and 1.

        Args:
            speed (float): The speed value to be normalized.
            min_speed (float): The minimum speed value.
            max_speed (float): The maximum speed value.

        Returns:
            float: The normalized speed value between 0 and 1.
        """
        normalized_speed = (speed - min_speed) / (max_speed - min_speed)
        return max(0.0, min(1.0, normalized_speed))