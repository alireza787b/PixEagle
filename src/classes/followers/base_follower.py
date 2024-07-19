# src/classes/base_follower.py

from abc import ABC, abstractmethod

class BaseFollower(ABC):
    """
    Abstract base class for different follower modes.
    Defines the required methods that any follower mode should implement.
    """
    def __init__(self, px4_controller):
        """
        Initializes the BaseFollower with the given PX4 controller.

        Args:
            px4_controller (PX4Controller): Instance of PX4Controller to control the drone.
        """
        self.px4_controller = px4_controller

    @abstractmethod
    def initialize(self):
        """Initialize the follower mode"""
        pass

    @abstractmethod
    def calculate_velocity_commands(self, target_coords):
        """
        Calculate velocity commands based on target coordinates.

        Args:
            target_coords (tuple): The coordinates of the target to follow.

        Returns:
            tuple: The calculated velocity commands for the drone.
        """
        pass

    @abstractmethod
    async def follow_target(self, target_coords):
        """
        Asynchronously sends velocity commands to follow the target.

        Args:
            target_coords (tuple): The coordinates of the target to follow.
        """
        pass
