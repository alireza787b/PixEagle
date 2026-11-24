"""Config publication uses the same manager instances as its consumers."""

from pathlib import Path

import pytest
import yaml

from classes import parameters
from classes.follower_config_manager import FollowerConfigManager
from classes.parameters import Parameters
from classes.safety_manager import SafetyManager


@pytest.mark.parametrize("manager_type,getter", [
    (FollowerConfigManager, parameters._get_follower_config_manager),
    (SafetyManager, parameters._get_safety_manager),
])
def test_lazy_getter_follows_the_authoritative_manager_registry(manager_type, getter, monkeypatch):
    original = getter()
    with monkeypatch.context() as patch:
        patch.setattr(manager_type, '_instance', None)
        replacement = manager_type.get_instance()
        assert replacement is not original
        assert getter() is replacement


def test_publication_initializes_the_instances_read_by_followers_after_registry_reset(monkeypatch):
    previous = Parameters.get_runtime_config_snapshot()
    # Warm both lazy access paths before replacing their registered instances.
    parameters._get_follower_config_manager()
    parameters._get_safety_manager()
    defaults = Path(__file__).resolve().parents[3] / 'configs/config_default.yaml'
    try:
        with monkeypatch.context() as patch:
            patch.setattr(FollowerConfigManager, '_instance', None)
            patch.setattr(SafetyManager, '_instance', None)
            Parameters.publish_config_mapping(yaml.safe_load(defaults.read_text()))
            follower = FollowerConfigManager.get_instance()
            safety = SafetyManager.get_instance()
            assert follower._initialized
            assert safety.is_initialized()
            assert follower.get_param('ENABLE_ALTITUDE_CONTROL', 'MC_VELOCITY_POSITION') is False
    finally:
        Parameters.publish_config_mapping(previous)
