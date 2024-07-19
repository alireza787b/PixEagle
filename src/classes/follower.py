# src/classes/follower.py

from .parameters import Parameters
from .ground_target_follower import GroundTargetFollower
from .front_view_target_follower import FrontViewTargetFollower

class Follower:
    """
    Follower class to manage different follower modes for the drone.
    It initializes the appropriate follower mode based on the configuration
    and delegates the target following tasks to the specific follower class.
    """

    def __init__(self, px4_controller, initial_target_coords):
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
        if self.mode == 'ground_view':
            return GroundTargetFollower(self.px4_controller, self.initial_target_coords)
        elif self.mode == 'front_view':
            return FrontViewTargetFollower(self.px4_controller, self.initial_target_coords)
        else:
            raise ValueError("Invalid follower mode")

    async def follow_target(self, target_coords):
        """
        Asynchronously sends velocity commands to follow a target based on its coordinates.

        Args:
            target_coords (tuple): The current target coordinates to follow.
        """
        await self.follower.follow_target(target_coords)
