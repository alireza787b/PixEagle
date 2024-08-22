
# WILL BE DELETED!!!!!!
from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
import logging
from typing import Tuple

class FrontViewTargetFollower(BaseFollower):
    """
    FrontViewTargetFollower manages PID control to keep a target in the front view of the drone.
    This class supports advanced PID features and allows different control strategies, such as yaw control
    and vertical error recalculation.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initialize the FrontViewTargetFollower with the given PX4 controller and initial target coordinates.

        Args:
            px4_controller (PX4Controller): Instance of PX4Controller to control the drone.
            initial_target_coords (tuple): Initial target coordinates to set for the follower.
        """
        super().__init__(px4_controller, "Front View")  # Initialize with "Front View" profile
        self.control_strategy = Parameters.CONTROL_STRATEGY
        self.target_position_mode = Parameters.TARGET_POSITION_MODE
        self.yaw_enabled = Parameters.ENABLE_YAW_CONTROL  # Initialize yaw control flag from parameters
        self.initial_target_coords = (
            initial_target_coords if self.target_position_mode == 'initial' else Parameters.DESIRE_AIM
        )
        self.initialize_pids()

    def initialize_pids(self):
        """
        Initializes the PID controllers based on the selected control strategy and target coordinates.
        """
        setpoint_x, setpoint_y = self.initial_target_coords

        # For constant distance strategy, initialize X and Z axis PID controllers
        if self.control_strategy == 'constant_distance':
            self.pid_y = CustomPID(
                *self.get_pid_gains('y'), 
                setpoint=setpoint_x, 
                output_limits=(-Parameters.VELOCITY_LIMITS['y'], Parameters.VELOCITY_LIMITS['y'])
            )
            self.pid_z = CustomPID(
                *self.get_pid_gains('z'), 
                setpoint=setpoint_y, 
                output_limits=(-Parameters.VELOCITY_LIMITS['z'], Parameters.VELOCITY_LIMITS['z'])
            )

        # Initialize the yaw PID controller if yaw control is enabled
        if self.yaw_enabled:  # TODO: Test and fine-tune yaw control logic
            self.pid_yaw = CustomPID(
                *self.get_pid_gains('yaw'),
                setpoint=setpoint_x,  # Yaw setpoint relates to horizontal positioning
                output_limits=(-Parameters.MAX_YAW_RATE, Parameters.MAX_YAW_RATE)
            )

    def get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves the PID gains for a specific axis, optionally applying gain scheduling based on altitude.

        Args:
            axis (str): The axis for which to retrieve the PID gains ('x', 'y', 'z', 'yaw').

        Returns:
            Tuple[float, float, float]: The proportional, integral, and derivative gains for the axis.
        """
        # Apply gain scheduling if enabled
        if Parameters.ENABLE_GAIN_SCHEDULING:
            current_value = getattr(self.px4_controller, Parameters.GAIN_SCHEDULING_PARAMETER, None)
            if current_value is None:
                logging.error(f"Parameter {Parameters.GAIN_SCHEDULING_PARAMETER} not available in PX4Controller.")
                return Parameters.PID_GAINS[axis]['p'], Parameters.PID_GAINS[axis]['i'], Parameters.PID_GAINS[axis]['d']
            
            for (lower_bound, upper_bound), gains in Parameters.ALTITUDE_GAIN_SCHEDULE.items():
                if lower_bound <= current_value < upper_bound:
                    return gains[axis]['p'], gains[axis]['i'], gains[axis]['d']

        # Return default gains if gain scheduling is not applied
        return Parameters.PID_GAINS[axis]['p'], Parameters.PID_GAINS[axis]['i'], Parameters.PID_GAINS[axis]['d']

    def update_pid_gains(self):
        """
        Updates the PID gains based on the current settings and altitude, adjusting for each axis as needed.
        """
        if self.control_strategy == 'constant_distance':
            self.pid_y.tunings = self.get_pid_gains('y')
            self.pid_z.tunings = self.get_pid_gains('z')

        # Update yaw PID gains if yaw control is enabled
        if self.yaw_enabled:
            self.pid_yaw.tunings = self.get_pid_gains('yaw')

    def calculate_velocity_commands(self, target_coords: Tuple[float, float]) -> None:
        """
        Calculates and updates velocity commands based on the target coordinates.

        Args:
            target_coords (Tuple[float, float]): The target coordinates from image processing, typically normalized.
        """
        # Update the PID gains before calculating velocities
        self.update_pid_gains()

        # Calculate errors for the X (horizontal) and Y (vertical) axes
        if self.control_strategy == 'constant_distance':
            error_x = self.pid_y.setpoint - target_coords[0]
            error_y = self.pid_z.setpoint - target_coords[1]  # Frame up is negative in many image processing contexts

            # Calculate velocities using the constant distance control strategy
            vel_x, vel_y, vel_z = self.calculate_velocity_constant_distance(error_x=error_x, error_y=error_y)

        # Handle yaw control if enabled
        yaw_velocity = 0
        if self.yaw_enabled and abs(error_x) > Parameters.YAW_CONTROL_THRESHOLD:
            yaw_velocity = self.pid_yaw(error_x)

        # Update the setpoint handler with calculated velocities and yaw rate
        self.setpoint_handler.set_field('vel_x', vel_x)
        self.setpoint_handler.set_field('vel_y', vel_y)
        self.setpoint_handler.set_field('vel_z', vel_z)
        self.setpoint_handler.set_field('yaw_rate', yaw_velocity)

    async def follow_target(self, target_coords: Tuple[float, float]):
        """
        Calculates and sends velocity and yaw rate commands to follow a target based on its coordinates.

        Args:
            target_coords (Tuple[float, float]): The target coordinates from image processing.

        Returns:
            dict: The current setpoint fields after calculation.
        """
        # Calculate the velocity commands for the target
        self.calculate_velocity_commands(target_coords)

        # Send the calculated velocity commands to the drone
        await self.px4_controller.send_body_velocity_commands(self.setpoint_handler.get_fields())

        # Return the current setpoint fields for logging or further processing
        return self.setpoint_handler.get_fields()

    def calculate_velocity_constant_distance(self, error_x: float, error_y: float) -> Tuple[float, float, float]:
        """
        Calculates velocity commands for constant distance strategy, ensuring the drone maintains a constant distance from the target.

        Args:
            error_x (float): Error in the x-axis (lateral position error).
            error_y (float): Error in the y-axis (vertical position error).

        Returns:
            Tuple[float, float, float]: The calculated velocities for the X, Y, and Z axes.
        """
        # Currently, X-axis velocity is set to zero. It can be controlled separately in future improvements.
        vel_x = 0  
        vel_y = self.pid_y(error_x)  # Lateral velocity is controlled by the Y PID
        vel_z = self.control_descent_constant_distance(error_y)  # Vertical velocity is controlled by the Z PID
        
        return vel_x, vel_y, vel_z

    def control_descent_constant_distance(self, error_y: float) -> float:
        """
        Controls the descent or climb of the drone based on the error in the y-axis (vertical position error), considering altitude limits.

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
