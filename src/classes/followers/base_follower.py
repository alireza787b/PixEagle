#src\classes\followers\base_follower.py
from abc import ABC, abstractmethod
from typing import Tuple, Dict
from classes.setpoint_handler import SetpointHandler
import logging

logger = logging.getLogger(__name__)

class BaseFollower(ABC):
    """
    Abstract base class for different follower modes.
    Defines the required methods that any follower mode should implement.
    """
    def __init__(self, px4_controller, profile_name: str):
        """
        Initializes the BaseFollower with the given PX4 controller and a SetpointHandler for managing setpoints.

        Args:
            px4_controller (PX4Controller): Instance of PX4Controller to control the drone.
            profile_name (str): The name of the setpoint profile to use (e.g., "Ground View", "Constant Position").
        """
        self.px4_controller = px4_controller
        self.profile_name = profile_name
        self.latest_velocities = {'timestamp': None, 'status': 'idle'}
        logger.info(f"BaseFollower initialized with profile: {profile_name}")

    @abstractmethod
    def calculate_control_commands(self, target_coords: Tuple[float, float]) -> None:
        """
        Calculate control commands based on target coordinates and update the setpoint handler.

        Args:
            target_coords (tuple): The coordinates of the target to follow.
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
            dict: The latest velocity telemetry data from the setpoint handler.
        """
        telemetry = self.px4_controller.setpoint_handler.get_fields()
        logger.debug(f"Telemetry data retrieved: {telemetry}")
        return telemetry
