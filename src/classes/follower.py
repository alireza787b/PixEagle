from .parameters import Parameters
from classes.followers.ground_target_follower import GroundTargetFollower
from classes.followers.front_view_target_follower import FrontViewTargetFollower
from typing import Tuple

class Follower:
    """
    Follower class to manage different follower modes for the drone.
    It initializes the appropriate follower mode based on the configuration
    and delegates the target following tasks to the specific follower class.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the Follower with the given PX4 controller and initial target coordinates.

        Args:
            px4_controller (PX4Controller): Instance of PX4Controller to control the drone.
            initial_target_coords (tuple): Initial target coordinates to set for the follower.
        """
        self.px4_controller = px4_controller
        self.mode = Parameters.FOLLOWER_MODE
        self.initial_target_coords = initial_target_coords
        self.follower = self.get_follower_mode()

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
            return mode_map[self.mode](self.px4_controller, self.initial_target_coords)
        else:
            raise ValueError("Invalid follower mode")

    async def follow_target(self, target_coords: Tuple[float, float]):
        """
        Asynchronously sends velocity commands to follow a target based on its coordinates.

        Args:
            target_coords (tuple): The current target coordinates to follow.
        """
        return await self.follower.follow_target(target_coords)

    def get_follower_telemetry(self):
        """Returns the latest velocity telemetry data."""
        return self.follower.get_follower_telemetry()
