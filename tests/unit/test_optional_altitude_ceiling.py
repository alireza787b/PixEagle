"""An absent mission ceiling preserves the floor and finite native authority."""

import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from classes.config_validator import normalize_safety_config
from classes.following_readiness import evaluate_following_start_altitude
from classes.parameters import Parameters
from classes import parameters
from classes.safety_manager import SafetyManager
from classes.safety_types import AltitudeLimits, SafetyAction
from classes.sih_visualization import _read_limits
from classes.followers.fw_attitude_rate_follower import FWAttitudeRateFollower
from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower
from classes.followers.mc_attitude_rate_follower import MCAttitudeRateFollower
from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower


@pytest.fixture
def config():
    path = Path(__file__).resolve().parents[2] / "configs/config_default.yaml"
    saved = yaml.safe_load(path.read_text())
    saved["Safety"]["GlobalLimits"]["MIN_ALTITUDE"] = 3.0
    return saved


@pytest.fixture
def manager():
    SafetyManager.reset_instance()
    yield SafetyManager.get_instance()
    SafetyManager.reset_instance()


def test_explicit_global_null_survives_normalization_and_serialization(config):
    assert config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] == 120.0
    config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] = None
    normalized = normalize_safety_config(config, require_safety=True)
    assert "MAX_ALTITUDE" in normalized["Safety"]["GlobalLimits"]
    assert yaml.safe_load(yaml.safe_dump(normalized))["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] is None


def test_generated_schema_only_allows_null_on_the_global_ceiling():
    path = Path(__file__).resolve().parents[2] / "configs/config_schema.yaml"
    safety = yaml.safe_load(path.read_text())["sections"]["Safety"]["parameters"]
    ceiling = safety["GlobalLimits"]["properties"]["MAX_ALTITUDE"]
    assert ceiling["nullable"] is True
    assert ceiling["default"] == 120.0
    assert ceiling["null_label"] == "No mission ceiling"
    override = safety["FollowerOverrides"]["properties"]["MC_VELOCITY_CHASE"]["properties"]["MAX_ALTITUDE"]
    assert not override.get("nullable", False)


def test_finite_follower_cap_tightens_absent_global_ceiling(config, manager):
    config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] = None
    config["Safety"]["FollowerOverrides"]["MC_VELOCITY_CHASE"] = {"MAX_ALTITUDE": 75.0}
    normalized = normalize_safety_config(config, require_safety=True)
    manager.load_from_config(normalized)
    assert manager.get_altitude_limits("MC_VELOCITY_CHASE").max_altitude == 75.0
    summary = manager.get_effective_limits_summary("MC_VELOCITY_CHASE")["MAX_ALTITUDE"]
    assert summary["effective_value"] == 75.0
    assert summary["global_value"] is None
    assert summary["source"] == "FollowerOverrides.MC_VELOCITY_CHASE"
    assert summary["is_overridden"] is True


def test_follower_null_still_requires_omission_for_inheritance(config):
    config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] = None
    config["Safety"]["FollowerOverrides"]["MC_VELOCITY_CHASE"] = {"MAX_ALTITUDE": None}
    with pytest.raises(ValueError, match="may not be null"):
        normalize_safety_config(config, require_safety=True)


def test_finite_global_still_rejects_weakening_override(config):
    config["Safety"]["FollowerOverrides"]["MC_VELOCITY_CHASE"] = {"MAX_ALTITUDE": 150.0}
    with pytest.raises(ValueError, match="weakens"):
        normalize_safety_config(config, require_safety=True)


@pytest.mark.parametrize("invalid", [True, "120", 0.0, float("nan"), float("inf")])
def test_only_explicit_null_extends_existing_numeric_contract(config, manager, invalid):
    config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] = invalid
    with pytest.raises(ValueError):
        normalize_safety_config(config, require_safety=True)
    manager.load_from_config(config)
    assert manager.get_limit("MAX_ALTITUDE") == 120.0


def test_missing_required_global_key_is_not_an_unbounded_setting(config, manager):
    del config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"]
    with pytest.raises(ValueError, match="MAX_ALTITUDE"):
        normalize_safety_config(config, require_safety=True)
    manager.load_from_config(config)
    assert manager.get_limit("MAX_ALTITUDE") == 120.0


def test_resolution_summary_parameters_and_reload_agree(config, manager, monkeypatch):
    config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] = None
    manager.load_from_config(config)
    monkeypatch.setattr(parameters, "_get_safety_manager", lambda: manager)
    assert manager.get_limit("MAX_ALTITUDE", "FW_NAVIGATION_CHASE") is None
    assert Parameters.get_altitude_limits("FW_NAVIGATION_CHASE") == (3.0, None)
    summary = manager.get_effective_limits_summary("FW_NAVIGATION_CHASE")["MAX_ALTITUDE"]
    assert summary["effective_value"] is None
    assert summary["source"] == "GlobalLimits"
    assert summary["is_overridden"] is False
    bounded = copy.deepcopy(config)
    bounded["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] = 80.0
    manager.load_from_config(bounded)
    assert Parameters.get_altitude_limits("FW_NAVIGATION_CHASE") == (3.0, 80.0)


@pytest.mark.parametrize("altitude,safe,action", [
    (2.99, False, SafetyAction.RTL), (3.0, True, SafetyAction.WARN),
    (4.99, True, SafetyAction.WARN), (5.0, True, SafetyAction.NONE),
    (1000.0, True, SafetyAction.NONE),
])
def test_floor_three_and_warning_remain_active(config, manager, altitude, safe, action):
    config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] = None
    manager.load_from_config(config)
    status = manager.check_altitude_safety(altitude, "FW_NAVIGATION_CHASE")
    assert (status.safe, status.action) == (safe, action)


@pytest.mark.parametrize("altitude,ready", [(4.99, False), (5.0, True), (1000.0, True), (float("nan"), False)])
def test_start_margin_keeps_floor_and_requires_real_height(altitude, ready):
    app = SimpleNamespace(px4_interface=SimpleNamespace(current_altitude=altitude))
    result = evaluate_following_start_altitude(app, limits=AltitudeLimits(3.0, None, 2.0))
    assert result["ready"] is ready


@pytest.mark.parametrize("altitude", [None, True, float("nan"), float("inf"), -float("inf")])
def test_absent_ceiling_does_not_treat_invalid_height_as_unbounded(config, manager, altitude):
    config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] = None
    manager.load_from_config(config)
    status = manager.check_altitude_safety(altitude, "FW_NAVIGATION_CHASE")
    assert status.safe is False
    assert status.reason == "altitude_unavailable"
    assert status.action is SafetyAction.EMERGENCY_STOP


def test_optional_bounds_reject_nonfinite_height_and_evidence_preserves_null():
    limits = AltitudeLimits(3.0, None, 2.0)
    assert limits.contains(1000.0)
    assert not limits.contains(2.99)
    assert not limits.contains(float("inf"))
    assert not limits.contains(float("nan"))
    assert _read_limits({"altitude": {"min": 3.0, "max": None}}) == {
        "altitude_min": 3.0, "altitude_max": None,
    }


@pytest.mark.parametrize("kind", [FWAttitudeRateFollower, MCAttitudeRateFollower,
                                 MCVelocityChaseFollower, GMVelocityChaseFollower, GMVelocityVectorFollower])
def test_legacy_follower_checks_do_not_report_ceiling_or_type_errors(kind, caplog):
    follower = kind.__new__(kind)
    follower._safety_checks_bypassed_for_testing = lambda: False
    follower.is_altitude_safety_enabled = lambda: True
    follower.px4_controller = SimpleNamespace(current_altitude=1000.)
    follower._follower_config_name = "TEST"
    follower.min_altitude_limit = follower.min_altitude_safety = 3.
    follower.max_altitude_limit = follower.max_altitude_safety = None
    follower.altitude_warning_buffer = 2.
    follower.last_altitude_check_time = follower.altitude_check_interval = 0.
    follower.altitude_violation_count = 0
    follower.emergency_stop_active = False
    follower.safety_manager = SimpleNamespace(get_safety_behavior=lambda _: SimpleNamespace(rtl_on_violation=False))
    follower.update_telemetry_metadata = Mock()
    result = follower._check_altitude_safety()
    assert (result["safe"] if isinstance(result, dict) else result) is True
    assert follower.altitude_violation_count == 0
    assert not follower.emergency_stop_active
    assert not [record for record in caplog.records if record.levelname == "ERROR"]
