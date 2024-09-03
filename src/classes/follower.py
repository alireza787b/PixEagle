#src\classes\follower.py
from .parameters import Parameters
from classes.followers.ground_target_follower import GroundTargetFollower
from classes.followers.constant_distance_follower import ConstantDistanceFollower
from classes.followers.constant_position_follower import ConstantPositionFollower
from classes.followers.chase_follower import ChaseFollower
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class Follower:
    """
    Manages different follower modes for the drone, delegating tasks to specific follower classes
    based on the configured mode.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the Follower with the PX4 controller and initial target coordinates.

        Args:
            px4_controller (PX4Controller): The PX4 controller instance for controlling the drone.
            initial_target_coords (tuple): Initial target coordinates for the follower.

        Raises:
            ValueError: If the initial_target_coords are not valid.
        """
        # Validate initial target coordinates
        if not isinstance(initial_target_coords, tuple) or len(initial_target_coords) != 2:
            raise ValueError(f"Invalid initial_target_coords: {initial_target_coords}. Must be a tuple of (x, y) coordinates.")

        self.px4_controller = px4_controller
        self.mode = Parameters.FOLLOWER_MODE
        self.initial_target_coords = initial_target_coords
        self.follower = self.get_follower_mode()
        logger.info(f"Initialized Follower with mode: {self.mode}")

    def get_follower_mode(self):
        """
        Determines and returns the appropriate follower mode based on the configuration.

        Returns:
            BaseFollower: An instance of the appropriate follower class.

        Raises:
            ValueError: If an invalid follower mode is specified in the parameters.
        """
        mode_map = {
            'ground_view': GroundTargetFollower,
            'constant_distance': ConstantDistanceFollower,
            'constant_position': ConstantPositionFollower,
            'chase_follower': ChaseFollower
        }

        if self.mode in mode_map:
            logger.debug(f"Selected follower mode: {self.mode}")
            return mode_map[self.mode](self.px4_controller, self.initial_target_coords)
        else:
            logger.error(f"Invalid follower mode specified: {self.mode}")
            raise ValueError(f"Invalid follower mode: {self.mode}")

    def follow_target(self, target_coords: Tuple[float, float]):
        """
        Asynchronously sends velocity commands to follow a target based on its coordinates.

        Args:
            target_coords (tuple): The current target coordinates to follow.

        Returns:
            The result of the follower's `follow_target` method.
        """
        logger.debug(f"Following target at coordinates: {target_coords}")
        try:
            self.follower.follow_target(target_coords)
        except Exception as e:
            logger.error(f"Failed to follow target at coordinates {target_coords}: {e}")
            raise

    def get_follower_telemetry(self):
        """
        Returns the latest velocity telemetry data from the current follower.

        Returns:
            dict: The latest telemetry data from the follower.
        """
        try:
            telemetry = self.follower.get_follower_telemetry()
            logger.debug(f"Follower telemetry: {telemetry}")
            return telemetry
        except Exception as e:
            logger.error(f"Failed to retrieve telemetry data: {e}")
            return {}


    def get_control_type(self) -> str:
        """
        Determines the type of control command to send based on the current follower mode.
        
        Returns:
            str: 'attitude_rate' if the follower mode uses attitude rate control, 
                'velocity_body' if it uses velocity body control.
        """
        if isinstance(self.follower, ChaseFollower):  # Assuming ChaseFollower uses attitude rate control
            return 'attitude_rate'
        else:
            return 'velocity_body'
