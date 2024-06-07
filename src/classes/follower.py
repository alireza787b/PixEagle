import asyncio
from simple_pid import PID
from classes.parameters import Parameters
from classes.px4_controller import PX4Controller
import logging

# Configure logging to help in debugging and operation verification
logging.basicConfig(level=logging.INFO)

class Follower:
    def __init__(self, px4_controller):
        """
        Initialize the Follower class with reference to a PX4Controller instance.
        
        Args:
        px4_controller (PX4Controller): An instance of the PX4Controller to interact with the drone.
        """
        self.px4_controller = px4_controller
        # Initialize PID controllers with output limits set from Parameters
        self.pid_x = PID(*self.get_pid_gains('x'), setpoint=0, output_limits=(-Parameters.VELOCITY_LIMITS['x'], Parameters.VELOCITY_LIMITS['x']))
        self.pid_y = PID(*self.get_pid_gains('y'), setpoint=0, output_limits=(-Parameters.VELOCITY_LIMITS['y'], Parameters.VELOCITY_LIMITS['y']))
        self.pid_z = PID(*self.get_pid_gains('z'), setpoint=Parameters.MIN_DESCENT_HEIGHT, output_limits=(-Parameters.MAX_RATE_OF_DESCENT, Parameters.MAX_RATE_OF_DESCENT))

    def get_pid_gains(self, axis):
        """
        Fetch the appropriate PID gains from the Parameters class based on current altitude.
        
        Args:
        axis (str): The axis ('x', 'y', or 'z') for which to get the PID gains.

        Returns:
        tuple: A tuple containing the PID gains (p, i, d).
        """
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
        """Update the PID gains based on the current environment conditions."""
        self.pid_x.tunings = self.get_pid_gains('x')
        self.pid_y.tunings = self.get_pid_gains('y')
        self.pid_z.tunings = self.get_pid_gains('z')

    def calculate_velocity_commands(self, target_coords):
        """
        Calculate velocity commands based on the drone's current target position.
        
        Args:
        target_coords (tuple): The current target coordinates as a tuple (x, y).

        Returns:
        tuple: The calculated velocity commands (vel_x, vel_y, vel_z).
        """
        self.update_pid_gains()
        
        # Ensure error calculation is performed element-wise
        error_x = Parameters.DESIRE_AIM[0] - target_coords[0]
        error_y = Parameters.DESIRE_AIM[1] - (-1)*target_coords[1]
        #remember!!!!! X: Possitive to Right  Y: Possitive to down (in 2D ) for coordinates of tracker
        # PX4 Body: +X goes back, +Y goes right
        logging.debug(f"Calculating PID for errors - X: {error_x}, Y: {error_y}")

        # PID controllers now automatically apply the velocity limits
        vel_x = self.pid_x(error_y)
        vel_y = self.pid_y(error_x)
        vel_z = self.control_descent()

        return (vel_x, vel_y, vel_z)

    def control_descent(self):
        """
        Control the drone's descent to ensure it does not go below the minimum safe altitude.

        Returns:
        float: The controlled descent velocity.
        """
        # Directly compute controlled descent using the z-axis PID controller
        if self.px4_controller.current_altitude > Parameters.MIN_DESCENT_HEIGHT:
            return self.pid_z(-self.px4_controller.current_altitude)
        return 0

    async def follow_target(self, target_coords):
        """
        Asynchronously command the drone to follow the target using calculated velocity commands.
        
        Args:
        target_coords (tuple): The current target coordinates as a tuple (x, y).
        """
        vel_x, vel_y, vel_z = self.calculate_velocity_commands(target_coords)
        await self.px4_controller.send_body_velocity_commands(vel_x, vel_y, vel_z)
