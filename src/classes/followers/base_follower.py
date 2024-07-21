from abc import ABC, abstractmethod
from typing import Tuple, Dict

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
        self.latest_velocities = {'vel_x': 0, 'vel_y': 0, 'vel_z': 0, 'timestamp': None, 'status': 'idle'}

    @abstractmethod
    def calculate_velocity_commands(self, target_coords: Tuple[float, float]) -> Tuple[float, float, float]:
        """
        Calculate velocity commands based on target coordinates.

        Args:
            target_coords (tuple): The coordinates of the target to follow.

        Returns:
            tuple: The calculated velocity commands for the drone.
        """
        pass

    @abstractmethod
    async def follow_target(self, target_coords: Tuple[float, float]):
        """
        Asynchronously sends velocity commands to follow the target.

        Args:
            target_coords (tuple): The coordinates of the target to follow.
        """
        pass
    
    def get_follower_telemetry(self) -> Dict[str, any]:
        """
        Returns the latest velocity telemetry data.

        Returns:
            dict: The latest velocity telemetry data.
        """
        return self.latest_velocities
