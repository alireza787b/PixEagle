import asyncio
from datetime import datetime
import logging

# Ensure to import the CustomPID class
from classes.custom_pid import CustomPID
from classes.parameters import Parameters
from classes.px4_controller import PX4Controller

# Configure logging to help in debugging and operation verification
logging.basicConfig(level=logging.INFO)

class Follower:
    """
    Follower class manages PID control to track a target using a drone,
    utilizing advanced PID features such as Proportional on Measurement and Anti-Windup.
    """
    def __init__(self, px4_controller):
        self.px4_controller = px4_controller
        # Initialize PID controllers using the CustomPID class
        self.pid_x = CustomPID(*self.get_pid_gains('x'), setpoint=0, output_limits=(-Parameters.VELOCITY_LIMITS['x'], Parameters.VELOCITY_LIMITS['x']))
        self.pid_y = CustomPID(*self.get_pid_gains('y'), setpoint=0, output_limits=(-Parameters.VELOCITY_LIMITS['y'], Parameters.VELOCITY_LIMITS['y']))
        self.pid_z = CustomPID(*self.get_pid_gains('z'), setpoint=Parameters.MIN_DESCENT_HEIGHT, output_limits=(-Parameters.MAX_RATE_OF_DESCENT, Parameters.MAX_RATE_OF_DESCENT))
        
        self.latest_velocities = {'vel_x': 0, 'vel_y': 0, 'vel_z': 0, 'timestamp': None, 'status': 'idle'}

    def get_pid_gains(self, axis):
        """
        Retrieves the PID gains based on the current altitude from the PX4Controller,
        applying gain scheduling if enabled.

        Parameters:
            axis (str): The control axis ('x', 'y', or 'z') for which to retrieve the PID gains.

        Returns:
            tuple: A tuple containing the PID gains (P, I, D) for the specified axis.
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
        """Updates the PID gains based on current settings and altitude."""
        self.pid_x.tunings = self.get_pid_gains('x')
        self.pid_y.tunings = self.get_pid_gains('y')
        self.pid_z.tunings = self.get_pid_gains('z')

    def calculate_velocity_commands(self, target_coords):
        """
        Calculates and returns the velocity commands based on the target coordinates and current drone status.
        This method adjusts commands based on the drone's altitude and orientation adjustments if the camera is not gimbaled.
        
        Note:
        - The function maps the x-axis error from the image processing (camera view) to the y-axis control of the drone and vice versa.
        This non-standard mapping is necessary due to the difference in the coordinate systems between the image processing output
        and the drone's movement axes. Specifically, the output from image processing might interpret 'forward' differently than the drone's
        'forward' depending on camera mounting and orientation. This should be recalibrated if the camera setup or orientation is changed.

        Parameters:
            target_coords (tuple): Target coordinates (x, y) from image processing.

        Returns:
            tuple: Velocity commands (vel_x, vel_y, vel_z) for the drone where:
                - vel_x controls forward/backward movement,
                - vel_y controls lateral movement,
                - vel_z controls vertical movement.
        """
        self.update_pid_gains()
        current_altitude = self.px4_controller.current_altitude
        
        # Calculate dynamic adjustment factors based on altitude
        adj_factor_x = Parameters.BASE_ADJUSTMENT_FACTOR_X / (1 + Parameters.ALTITUDE_FACTOR * current_altitude)
        adj_factor_y = Parameters.BASE_ADJUSTMENT_FACTOR_Y / (1 + Parameters.ALTITUDE_FACTOR * current_altitude)

        # Apply orientation-based adjustments if the camera is not gimbaled
        if not Parameters.IS_CAMERA_GIMBALED:
            orientation = self.px4_controller.get_orientation()  # (yaw, pitch, roll)
            adjusted_target_x = target_coords[0] + adj_factor_x * orientation[2]  # roll affects x
            adjusted_target_y = target_coords[1] - adj_factor_y * orientation[1]  # pitch affects y
        else:
            adjusted_target_x = target_coords[0]
            adjusted_target_y = target_coords[1]

        # Mapping the error from image axes to control axes
        error_x = Parameters.DESIRE_AIM[0] - adjusted_target_x
        error_y = Parameters.DESIRE_AIM[1] - (-1) * adjusted_target_y
        
        # Applying the PID control where error_y is used for vel_x and error_x for vel_y due to axis differences
        vel_x = self.pid_y(error_y)  # error_y controls vel_x due to coordinate system differences
        vel_y = self.pid_x(error_x)  # error_x controls vel_y due to coordinate system differences
        vel_z = self.control_descent()

        self.latest_velocities = {
            'vel_x': vel_x,
            'vel_y': vel_y,
            'vel_z': vel_z,
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'active'
        }

        return (vel_x, vel_y, vel_z)


    def control_descent(self):
        """
        Controls the descent of the drone based on current altitude, ensuring it doesn't go below the minimum descent height.

        Returns:
            float: Descent velocity command.
        """
        current_altitude = self.px4_controller.current_altitude
        logging.debug(f"Current Altitude: {current_altitude}m, Minimum Descent Height: {Parameters.MIN_DESCENT_HEIGHT}m")

        if current_altitude > Parameters.MIN_DESCENT_HEIGHT:
            return self.pid_z(-current_altitude)
        else:
            logging.info("Altitude is at or below the minimum descent height. Descent halted.")
            return 0

    async def follow_target(self, target_coords):
        """
        Asynchronously sends velocity commands to follow a target based on its coordinates.

        Parameters:
            target_coords (tuple): Target coordinates (x, y).
        """
        vel_x, vel_y, vel_z = self.calculate_velocity_commands(target_coords)
        await self.px4_controller.send_body_velocity_commands(vel_x, vel_y, vel_z)

    def get_follower_telemetry(self):
        """Returns the latest velocity telemetry data."""
        return self.latest_velocities
