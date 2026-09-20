"""Unknown mount settings must never silently choose a different installation."""
from unittest.mock import MagicMock

import pytest

from classes.parameters import Parameters
from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower


@pytest.mark.parametrize("follower,section", [
    (GMVelocityChaseFollower, "GM_VELOCITY_CHASE"),
    (GMVelocityVectorFollower, "GM_VELOCITY_VECTOR"),
])
@pytest.mark.parametrize("mount", ["SIDEWAYS", "vertical", "", None])
def test_unknown_mount_rejected_before_controller_setup(monkeypatch, follower, section, mount):
    monkeypatch.setattr(Parameters, section, {"MOUNT_TYPE": mount})
    controller = MagicMock()
    with pytest.raises(ValueError, match="MOUNT_TYPE"):
        follower(controller, (0, 0))
    assert not controller.mock_calls


def test_vector_unknown_runtime_mount_cannot_produce_vertical_vector():
    follower = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)
    follower.mount_type = "SIDEWAYS"
    with pytest.raises(ValueError, match="MOUNT_TYPE"):
        follower._gimbal_to_body_vector(0, 90, 0)
