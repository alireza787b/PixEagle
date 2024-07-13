import asyncio
from simple_pid import PID
from classes.parameters import Parameters
from classes.px4_controller import PX4Controller
import logging
from datetime import datetime

# Configure logging to help in debugging and operation verification
logging.basicConfig(level=logging.INFO)

class Follower:
    def __init__(self, px4_controller):
        self.px4_controller = px4_controller
        self.pid_x = PID(*self.get_pid_gains('x'), setpoint=0, output_limits=(-Parameters.VELOCITY_LIMITS['x'], Parameters.VELOCITY_LIMITS['x']))
        self.pid_y = PID(*self.get_pid_gains('y'), setpoint=0, output_limits=(-Parameters.VELOCITY_LIMITS['y'], Parameters.VELOCITY_LIMITS['y']))
        self.pid_z = PID(*self.get_pid_gains('z'), setpoint=Parameters.MIN_DESCENT_HEIGHT, output_limits=(-Parameters.MAX_RATE_OF_DESCENT, Parameters.MAX_RATE_OF_DESCENT))
        
        self.latest_velocities = {'vel_x': 0, 'vel_y': 0, 'vel_z': 0, 'timestamp': None, 'status': 'idle'}

    def get_pid_gains(self, axis):
        """
        Retrieves the PID gains based on the current altitude from the PX4Controller.
        
        This method first checks if gain scheduling is enabled. If it is, it attempts to fetch the current altitude.
        It then determines the appropriate PID gains by finding the altitude range that the current altitude falls into.
        If the current altitude does not fall within any defined range or if gain scheduling is disabled,
        default gains defined in Parameters.PID_GAINS are returned.

        Parameters:
            axis (str): The control axis ('x', 'y', or 'z') for which to retrieve the PID gains.

        Returns:
            tuple: A tuple containing the PID gains (P, I, D) for the specified axis.

        Raises:
            logs an error if the current altitude parameter is not available in PX4Controller.
        """
        if Parameters.ENABLE_GAIN_SCHEDULING:
            current_value = getattr(self.px4_controller, Parameters.GAIN_SCHEDULING_PARAMETER, None)
            if current_value is None:
                logging.error(f"Parameter {Parameters.GAIN_SCHEDULING_PARAMETER} not available in PX4Controller.")
                return Parameters.PID_GAINS[axis]['p'], Parameters.PID_GAINS[axis]['i'], Parameters.PID_GAINS[axis]['d']
            
            for (lower_bound, upper_bound), gains in Parameters.ALTITUDE_GAIN_SCHEDULE.items():
                if lower_bound <= current_value < upper_bound:
                    return gains[axis]['p'], gains[axis]['i'], gains[axis]['d']
        
        # Return default gains if no range matches or if gain scheduling is disabled
        return Parameters.PID_GAINS[axis]['p'], Parameters.PID_GAINS[axis]['i'], Parameters.PID_GAINS[axis]['d']


    def update_pid_gains(self):
        self.pid_x.tunings = self.get_pid_gains('x')
        self.pid_y.tunings = self.get_pid_gains('y')
        self.pid_z.tunings = self.get_pid_gains('z')

    def calculate_velocity_commands(self, target_coords):
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

        error_x = Parameters.DESIRE_AIM[0] - adjusted_target_x
        error_y = Parameters.DESIRE_AIM[1] - (-1)*adjusted_target_y
        vel_x = self.pid_x(error_y)
        vel_y = self.pid_y(error_x)
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
        current_altitude = self.px4_controller.current_altitude
        # Log the current altitude and minimum descent height
        logging.debug(f"Current Altitude: {current_altitude}m, Minimum Descent Height: {Parameters.MIN_DESCENT_HEIGHT}m")

        if current_altitude > Parameters.MIN_DESCENT_HEIGHT:
            descent_velocity = self.pid_z(-current_altitude)
            # Log the descent velocity calculated by the PID controller
            #logging.info(f"Descent Velocity Command: {descent_velocity} m/s")
            return descent_velocity
        else:
            # Log when the altitude is at or below the minimum descent height
            logging.info("Altitude is at or below the minimum descent height. Descent halted.")
            return 0


    async def follow_target(self, target_coords):
        vel_x, vel_y, vel_z = self.calculate_velocity_commands(target_coords)
        await self.px4_controller.send_body_velocity_commands(vel_x, vel_y, vel_z)

    def get_follower_telemetry(self):
        return self.latest_velocities
