# src/classes/front_view_target_follower.py

from .base_follower import BaseFollower
from .custom_pid import CustomPID
from classes.parameters import Parameters
import logging
from datetime import datetime
import math

class FrontViewTargetFollower(BaseFollower):
    """
    FrontViewTargetFollower class manages PID control to keep a target in the front view of the drone.
    It utilizes advanced PID features and allows different control strategies.
    """
    def __init__(self, px4_controller, initial_target_coords):
        """
        Initializes the FrontViewTargetFollower with the given PX4 controller and initial target coordinates.

        Args:
            px4_controller (PX4Controller): Instance of PX4Controller to control the drone.
            initial_target_coords (tuple): Initial target coordinates to set for the follower.
        """
        super().__init__(px4_controller)
        self.control_strategy = Parameters.CONTROL_STRATEGY
        self.target_position_mode = Parameters.TARGET_POSITION_MODE
        self.initial_target_coords = initial_target_coords if self.target_position_mode == 'initial' else Parameters.DESIRE_AIM
        self.initialize_pids()

    def initialize_pids(self):
        """Initializes the PID controllers based on the control strategy and initial target coordinates."""
        setpoint_x, setpoint_y = self.initial_target_coords
        self.pid_y = CustomPID(*self.get_pid_gains('y'), setpoint=setpoint_x, output_limits=(-Parameters.VELOCITY_LIMITS['y'], Parameters.VELOCITY_LIMITS['y']))
        
        if self.control_strategy == 'constant_altitude':
            self.pid_x = CustomPID(*self.get_pid_gains('x'), setpoint=setpoint_y, output_limits=(-Parameters.VELOCITY_LIMITS['x'], Parameters.VELOCITY_LIMITS['x']))
            self.pid_z = CustomPID(*self.get_pid_gains('z'), setpoint=Parameters.MIN_DESCENT_HEIGHT, output_limits=(-Parameters.MAX_RATE_OF_DESCENT, Parameters.MAX_RATE_OF_DESCENT))
        else:  # constant_distance
            self.pid_z = CustomPID(*self.get_pid_gains('z'), setpoint=setpoint_y, output_limits=(-Parameters.VELOCITY_LIMITS['z'], Parameters.VELOCITY_LIMITS['z']))
            self.pid_x = CustomPID(*self.get_pid_gains('x'), setpoint=0, output_limits=(0, 0))  # vx will be controlled separately, for now set to zero
        
        self.latest_velocities = {'vel_x': 0, 'vel_y': 0, 'vel_z': 0, 'timestamp': None, 'status': 'idle'}

    def get_pid_gains(self, axis):
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
        self.pid_x.tunings = self.get_pid_gains('x')
        self.pid_y.tunings = self.get_pid_gains('y')
        self.pid_z.tunings = self.get_pid_gains('z')

    def calculate_velocity_commands(self, target_coords):
        """Calculates and returns the velocity commands based on the target coordinates and current drone status."""
        self.update_pid_gains()
        current_altitude = self.px4_controller.current_altitude
        
        # Calculate dynamic adjustment factors based on altitude
        adj_factor_x = Parameters.BASE_ADJUSTMENT_FACTOR_X / (1 + Parameters.ALTITUDE_FACTOR * current_altitude)
        adj_factor_y = Parameters.BASE_ADJUSTMENT_FACTOR_Y / (1 + Parameters.ALTITUDE_FACTOR * current_altitude)

        # Apply orientation-based adjustments if the camera is not gimbaled
        if not Parameters.IS_CAMERA_GIMBALED:
            orientation = self.px4_controller.get_orientation()  # (yaw, pitch, roll)
            roll = orientation[2]
            pitch = orientation[1]
            adjusted_target_x = target_coords[0] + adj_factor_x * roll  # roll affects x
            adjusted_target_y = target_coords[1] - adj_factor_y * pitch  # pitch affects y
            
            # Additional adjustments for non-gimbaled camera roll
            r = math.sqrt(target_coords[0]**2 + target_coords[1]**2)
            adjusted_target_x += r * math.cos(roll)
            adjusted_target_y += r * math.sin(roll)
        else:
            adjusted_target_x = target_coords[0]
            adjusted_target_y = target_coords[1]

        # Calculate errors
        error_x = self.pid_x.setpoint - adjusted_target_x
        error_y = self.pid_y.setpoint - adjusted_target_y
        
        # Apply control strategies based on the selected control strategy
        if self.control_strategy == 'constant_altitude':
            return self.calculate_velocity_constant_altitude(error_x, error_y)
        else:  # constant_distance
            return self.calculate_velocity_constant_distance(error_x, error_y)

    def calculate_velocity_constant_altitude(self, error_x, error_y):
        """Calculate velocity commands for constant altitude strategy."""
        vel_x = self.pid_x(error_y)  # error_y controls vel_x due to coordinate system differences
        vel_y = self.pid_y(error_x)  # error_x controls vel_y due to coordinate system differences
        vel_z = self.control_descent()
        
        self.latest_velocities = {
            'vel_x': vel_x,
            'vel_y': vel_y,
            'vel_z': vel_z,
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'active'
        }
        
        return vel_x, vel_y, vel_z

    def calculate_velocity_constant_distance(self, error_x, error_y):
        """Calculate velocity commands for constant distance strategy."""
        vel_x = 0  # Set to zero for now, later can be controlled separately
        vel_y = self.pid_y(error_x)  # error_x controls vel_y due to coordinate system differences
        vel_z = self.pid_z(error_y)  # error_y controls vel_z due to coordinate system differences
        
        self.latest_velocities = {
            'vel_x': vel_x,
            'vel_y': vel_y,
            'vel_z': vel_z,
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'active'
        }
        
        return vel_x, vel_y, vel_z

    def control_descent(self):
        """
        Controls the descent of the drone based on current altitude, ensuring it doesn't go below the minimum descent height.
        """
        current_altitude = self.px4_controller.current_altitude
        logging.debug(f"Current Altitude: {current_altitude}m, Minimum Descent Height: {Parameters.MIN_DESCENT_HEIGHT}m")

        if current_altitude > Parameters.MIN_DESCENT_HEIGHT:
            return self.pid_z(-current_altitude)
        else:
            logging.info("Altitude is at or below the minimum descent height. Descent halted.")
            return 0

    async def follow_target(self, target_coords):
        """Asynchronously sends velocity commands to follow a target based on its coordinates."""
        vel_x, vel_y, vel_z = self.calculate_velocity_commands(target_coords)
        await self.px4_controller.send_body_velocity_commands(vel_x, vel_y, vel_z)
