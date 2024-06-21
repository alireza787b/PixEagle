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
        self.pid_x.tunings = self.get_pid_gains('x')
        self.pid_y.tunings = self.get_pid_gains('y')
        self.pid_z.tunings = self.get_pid_gains('z')

    def calculate_velocity_commands(self, target_coords):
        self.update_pid_gains()
        error_x = Parameters.DESIRE_AIM[0] - target_coords[0]
        error_y = Parameters.DESIRE_AIM[1] - (-1)*target_coords[1]
        logging.debug(f"Calculating PID for errors - X: {error_x}, Y: {error_y}")
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
        if self.px4_controller.current_altitude > Parameters.MIN_DESCENT_HEIGHT:
            return self.pid_z(-self.px4_controller.current_altitude)
        return 0

    async def follow_target(self, target_coords):
        vel_x, vel_y, vel_z = self.calculate_velocity_commands(target_coords)
        await self.px4_controller.send_body_velocity_commands(vel_x, vel_y, vel_z)

    def get_follower_telemetry(self):
        return self.latest_velocities
