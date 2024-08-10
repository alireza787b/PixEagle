import logging
from .parameters import Parameters
from classes.followers.ground_target_follower import GroundTargetFollower
from classes.followers.front_view_target_follower import FrontViewTargetFollower
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
        """
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
            'front_view': FrontViewTargetFollower
        }

        if self.mode in mode_map:
            logger.debug(f"Selected follower mode: {self.mode}")
            return mode_map[self.mode](self.px4_controller, self.initial_target_coords)
        else:
            logger.error(f"Invalid follower mode specified: {self.mode}")
            raise ValueError(f"Invalid follower mode: {self.mode}")

    async def follow_target(self, target_coords: Tuple[float, float]):
        """
        Asynchronously sends velocity commands to follow a target based on its coordinates.

        Args:
            target_coords (tuple): The current target coordinates to follow.

        Returns:
            The result of the follower's `follow_target` method.
        """
        logger.debug(f"Following target at coordinates: {target_coords}")
        return await self.follower.follow_target(target_coords)

    def get_follower_telemetry(self):
        """
        Returns the latest velocity telemetry data from the current follower.

        Returns:
            dict: The latest telemetry data from the follower.
        """
        telemetry = self.follower.get_follower_telemetry()
        logger.debug(f"Follower telemetry: {telemetry}")
        return telemetry
